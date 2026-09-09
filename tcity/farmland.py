"""Live planar region → irregular farm parcels, lanes, irrigation and crop instances.

The Python below only constructs the graph and reusable assets. No evaluation
handlers, baked layouts or Python-dependent seeds are used.
"""
import math
import bpy
from .nodes import Graph, set_control
from .farm_assets import palette, ensure_farm_assets
from .roads import _join, _transform, _mat, _gate, _store, _named, _index_switch, _boolean_op, _self_union

GROUP_NAME='TCity • Taiwan Farmland v0.1'
SOCKETS=[
    ('Seed','NodeSocketInt',31,0,100000,'農地分割與作物變化 / Deterministic layout and crops'),
    ('Plot Width','NodeSocketFloat',22.,8.,80.,'田塊平均短邊，公尺 / Average parcel width'),
    ('Plot Length','NodeSocketFloat',42.,12.,120.,'田塊平均長邊，公尺 / Average parcel length'),
    ('Irregularity','NodeSocketFloat',.65,0,1,'共享邊界的偏移，不是互相重疊的隨機矩形 / Shared-edge displacement'),
    ('Field Angle','NodeSocketFloat',0.,-180,180,'整組田區相對區域的旋轉角度 / Field bearing in degrees'),
    ('Bund Width','NodeSocketFloat',1.1,.5,2.5,'田埂名目宽度；隨田形略有變化 / Nominal earth bund width'),
    ('Rice Mix','NodeSocketFloat',.72,0,1,'其他用途分配後，水稻相對蔬菜的比例 / Rice versus vegetables in remaining plots'),
    ('Ripening','NodeSocketFloat',.38,0,1,'稻田轉為金黃的比例 / Share of rice plots ripening'),
    ('Orchard Mix','NodeSocketFloat',.12,0,.8,'果園機率，設施之後分配 / Conditional orchard probability'),
    ('Fallow Mix','NodeSocketFloat',.12,0,.8,'休耕裸土機率 / Conditional fallow probability'),
    ('Flooded Mix','NodeSocketFloat',.06,0,.8,'整地蓄水田機率 / Conditional flooded-paddy probability'),
    ('Structure Mix','NodeSocketFloat',.07,0,.6,'農舍、鐵皮農用棚與栽培隧道用地機率 / Facility parcel probability'),
    ('Farm Roads','NodeSocketBool',True,None,None,'每三排與四列的農路 / Shared farm access lanes'),
    ('Road Width','NodeSocketFloat',3.2,2,6,'農路寬度，公尺 / Farm lane width'),
    ('Irrigation','NodeSocketBool',True,None,None,'具有槽底、側壁與水面的明渠 / Open concrete irrigation channels'),
    ('Crops','NodeSocketBool',True,None,None,'實例化稻叢、蔬菜與果樹 / Actual crop geometry'),
    ('Plant Spacing','NodeSocketFloat',.72,.45,2.,'稻菜取樣間距；大區域自動限制約十八萬點 / Crop spacing with automatic point budget'),
    ('Structures','NodeSocketBool',True,None,None,'顯示農業設施模型；關閉時保留用地 / Show facility models on allocated yards'),
]
PRESETS={
    'PADDY':{'Rice Mix':1.,'Ripening':.48,'Orchard Mix':0.,'Fallow Mix':.08,'Flooded Mix':.08,'Structure Mix':.025,'Plot Width':19.,'Plot Length':46.,'Irregularity':.7},
    'MIXED':{'Rice Mix':.48,'Ripening':.26,'Orchard Mix':.25,'Fallow Mix':.14,'Flooded Mix':.035,'Structure Mix':.07,'Plot Width':23.,'Plot Length':38.,'Irregularity':.7},
    'FRINGE':{'Rice Mix':.60,'Ripening':.32,'Orchard Mix':.07,'Fallow Mix':.22,'Flooded Mix':.025,'Structure Mix':.30,'Plot Width':25.,'Plot Length':40.,'Irregularity':.42},
}


class FarmGraph(Graph):
    def add(self,a,b):return self.math('ADD',a,b)
    def sub(self,a,b):return self.math('SUBTRACT',a,b)
    def mul(self,a,b):return self.math('MULTIPLY',a,b)
    def div(self,a,b):return self.math('DIVIDE',a,b)
    def switch(self,condition,a,b,dtype='INT'):
        n=self.node('GeometryNodeSwitch',input_type=dtype)
        self.put(condition,n.inputs['Switch']);self.put(a,n.inputs['False']);self.put(b,n.inputs['True']);return n.outputs[0]
    def prism(self,geo,bottom,top):
        base=_transform(self,geo,(0,0,bottom))
        e=self.node('GeometryNodeExtrudeMesh',mode='FACES');self.put(base,e.inputs['Mesh'])
        e.inputs['Individual'].default_value=False;self.put(self.vector(0,0,top-bottom),e.inputs['Offset']);e.inputs['Offset Scale'].default_value=1
        flip=self.node('GeometryNodeFlipFaces');self.put(base,flip.inputs['Mesh'])
        merge=self.node('GeometryNodeMergeByDistance');merge.inputs['Distance'].default_value=.00001
        self.put(_join(self,[e.outputs['Mesh'],flip.outputs[0]]),merge.inputs['Geometry']);return merge.outputs[0]
    def profile(self,xs,zs):
        line=self.node('GeometryNodeMeshLine',mode='OFFSET');line.inputs['Count'].default_value=len(xs)
        idx=self.node('GeometryNodeInputIndex').outputs[0]
        position=self.vector(_index_switch(self,idx,'FLOAT',xs),self.mul(_index_switch(self,idx,'FLOAT',zs),-1),0)
        sp=self.node('GeometryNodeSetPosition');self.put(line.outputs[0],sp.inputs['Geometry']);self.put(position,sp.inputs['Position'])
        curve=self.node('GeometryNodeMeshToCurve');self.put(sp.outputs[0],curve.inputs['Mesh'])
        close=self.node('GeometryNodeSetSplineCyclic');self.put(curve.outputs[0],close.inputs['Curve']);close.inputs['Cyclic'].default_value=True
        return close.outputs[0]
    def sweep(self,curve,x0,x1,z0,z1):
        profile=self.profile([x0,x0,x1,x1],[z0,z1,z1,z0])
        n=self.node('GeometryNodeCurveToMesh');self.put(curve,n.inputs['Curve']);self.put(profile,n.inputs['Profile Curve'])
        n.inputs['Fill Caps'].default_value=True;return n.outputs[0]
    def boundary(self,geo):
        nbr=self.node('GeometryNodeInputMeshEdgeNeighbors')
        n=self.node('GeometryNodeSeparateGeometry',domain='EDGE');self.put(geo,n.inputs['Geometry'])
        self.put(self.equal(nbr.outputs['Face Count'],1),n.inputs['Selection']);return n.outputs[0]
    def ray(self,target,position,attribute=None):
        n=self.node('GeometryNodeRaycast',data_type='INT')
        self.put(target,n.inputs['Target Geometry']);self.put(self.vmath('ADD',position,(0,0,50)),n.inputs['Source Position'])
        n.inputs['Ray Direction'].default_value=(0,0,-1);n.inputs['Ray Length'].default_value=100
        if attribute is not None:self.put(attribute,n.inputs['Attribute'])
        return n
    def distance(self,target,position):
        n=self.node('GeometryNodeProximity',target_element='EDGES');self.put(target,n.inputs['Geometry']);self.put(position,n.inputs['Sample Position'])
        return n.outputs['Distance']
    def instances(self,points,col,index,selection,scale=(1,1,1),rotation=(0,0,0)):
        info=self.node('GeometryNodeCollectionInfo');info.inputs['Collection'].default_value=col
        info.inputs['Separate Children'].default_value=True;info.inputs['Reset Children'].default_value=True
        n=self.node('GeometryNodeInstanceOnPoints');n.inputs['Pick Instance'].default_value=True
        # Blender 5.2 uses the implicit point Index on unlinked index sockets.
        if isinstance(index,int):index=self.add(index,0)
        for value,key in [(points,'Points'),(info.outputs[0],'Instance'),(index,'Instance Index'),(selection,'Selection'),(scale,'Scale'),(rotation,'Rotation')]:self.put(value,n.inputs[key])
        return n.outputs[0]


def ensure_group():
    if GROUP_NAME in bpy.data.node_groups:return bpy.data.node_groups[GROUP_NAME]
    col=ensure_farm_assets();mats=palette()
    tree=bpy.data.node_groups.new(GROUP_NAME,'GeometryNodeTree');tree.is_modifier=True
    tree.description='平面區域 → 台灣農地；田埂、明渠、農路、作物與農舍。單位：公尺。'
    tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    for name,kind,default,minimum,maximum,desc in SOCKETS:
        s=tree.interface.new_socket(name=name,in_out='INPUT',socket_type=kind);s.default_value=default;s.description=desc
        if minimum is not None:s.min_value=minimum;s.max_value=maximum
    tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    g=FarmGraph(tree);inp=g.node('NodeGroupInput');out=g.node('NodeGroupOutput');p=inp.outputs
    inp.location=(-600,0);out.location=(9600,0)
    g.section('01 / PLAN · shared vertices make coherent field boundaries',(0,0))
    angle=g.mul(p['Field Angle'],math.pi/180)
    region=_transform(g,p['Geometry'],rotation=g.vector(0,0,g.mul(angle,-1)))
    # Only filled faces participate; loose city-road edges are not farmland roads.
    normal=g.node('GeometryNodeInputNormal').outputs[0]
    nz=g.node('ShaderNodeSeparateXYZ');g.put(normal,nz.inputs[0])
    flip=g.node('GeometryNodeFlipFaces');g.put(region,flip.inputs['Mesh']);g.put(g.math('LESS_THAN',nz.outputs['Z'],0),flip.inputs['Selection']);region=flip.outputs[0]
    box=g.node('GeometryNodeBoundBox');g.put(region,box.inputs['Geometry'])
    low=g.node('ShaderNodeSeparateXYZ');g.put(box.outputs['Min'],low.inputs[0])
    span=g.node('ShaderNodeSeparateXYZ');g.put(g.vmath('SUBTRACT',box.outputs['Max'],box.outputs['Min']),span.inputs[0])
    # Flatten at local input height; restore that height on the final output.
    region=_transform(g,region,g.vector(0,0,g.mul(low.outputs['Z'],-1)))
    W=p['Plot Width'];L=p['Plot Length'];seed=p['Seed']
    nx=g.add(g.math('CEIL',g.div(span.outputs['X'],W)),3);ny=g.add(g.math('CEIL',g.div(span.outputs['Y'],L)),3)
    grid=g.node('GeometryNodeMeshGrid');g.put(nx,grid.inputs['Vertices X']);g.put(ny,grid.inputs['Vertices Y'])
    idx=g.node('GeometryNodeInputIndex').outputs[0];pos=g.node('GeometryNodeInputPosition').outputs[0]
    ix=g.math('FLOOR',g.div(idx,ny));iy=g.math('MODULO',idx,ny)
    dx=g.add(g.random('FLOAT',-.24,.24,seed,ix,11),g.random('FLOAT',-.08,.08,seed,idx,12))
    dy=g.add(g.random('FLOAT',-.23,.23,seed,iy,13),g.random('FLOAT',-.12,.12,seed,ix,14))
    xx=g.add(low.outputs['X'],g.mul(g.add(g.sub(ix,1),g.mul(dx,p['Irregularity'])),W))
    yy=g.add(low.outputs['Y'],g.mul(g.add(g.sub(iy,1),g.mul(dy,p['Irregularity'])),L))
    tagged=_store(g,grid.outputs['Mesh'],'farm_ix',ix,'INT');tagged=_store(g,tagged,'farm_iy',iy,'INT')
    setpos=g.node('GeometryNodeSetPosition');g.put(tagged,setpos.inputs['Geometry']);g.put(g.vector(xx,yy,0),setpos.inputs['Position']);plan=setpos.outputs[0]
    # Sequential, independently seeded probabilities. Crop IDs survive clipping.
    def chance(control,offset):return g.math('LESS_THAN',g.random('FLOAT',0,1,seed,idx,offset),p[control])
    kind=g.switch(chance('Rice Mix',101),2,g.switch(chance('Ripening',103),0,1))
    for control,value,offset in [('Flooded Mix',5,107),('Fallow Mix',4,109),('Orchard Mix',3,113),('Structure Mix',6,127)]:
        kind=g.switch(chance(control,offset),kind,value)
    plan=_store(g,plan,'farm_kind',kind,'INT','FACE')
    plan=_store(g,plan,'farm_parcel',idx,'INT','FACE')
    centers=g.node('GeometryNodeMeshToPoints',mode='FACES');g.put(plan,centers.inputs['Mesh'])
    capture=g.node('GeometryNodeCaptureAttribute',domain='FACE');capture.capture_items.new('VECTOR','Center')
    g.put(plan,capture.inputs['Geometry']);g.put(pos,capture.inputs['Center'])
    split=g.node('GeometryNodeSplitEdges');g.put(capture.outputs[0],split.inputs['Mesh'])
    inset=g.node('GeometryNodeSetPosition');g.put(split.outputs[0],inset.inputs['Geometry'])
    shrink=g.vector(g.sub(1,g.div(p['Bund Width'],W)),g.sub(1,g.div(p['Bund Width'],L)),1)
    g.put(g.vmath('ADD',capture.outputs['Center'],g.vmath('MULTIPLY',g.vmath('SUBTRACT',pos,capture.outputs['Center']),shrink)),inset.inputs['Position'])
    field_plan=inset.outputs[0]
    g.section('02 / ACCESS · rural lanes and open irrigation channels',(1800,0))
    ev=g.node('GeometryNodeInputMeshEdgeVertices')
    def endpoint(name,which):
        sample=g.node('GeometryNodeSampleIndex',data_type='INT',domain='POINT')
        g.put(plan,sample.inputs['Geometry']);g.put(_named(g,name,'INT'),sample.inputs['Value']);g.put(ev.outputs['Vertex Index '+str(which)],sample.inputs['Index']);return sample.outputs[0]
    x1,x2=endpoint('farm_ix',1),endpoint('farm_ix',2)
    y1,y2=endpoint('farm_iy',1),endpoint('farm_iy',2)
    vertical=g.equal(x1,x2);horizontal=g.equal(y1,y2)
    vr=g.boolean('AND',vertical,g.equal(g.math('MODULO',x1,4),2))
    hr=g.boolean('AND',horizontal,g.equal(g.math('MODULO',y1,3),1))
    def segments(selection):
        sel=g.node('GeometryNodeSeparateGeometry',domain='EDGE');g.put(plan,sel.inputs['Geometry']);g.put(selection,sel.inputs['Selection'])
        split=g.node('GeometryNodeSplitEdges');g.put(sel.outputs[0],split.inputs['Mesh'])
        curve=g.node('GeometryNodeMeshToCurve');g.put(split.outputs[0],curve.inputs['Mesh']);return curve.outputs[0]
    roads_curve=segments(g.boolean('OR',vr,hr));half=g.mul(p['Road Width'],.5)
    road_void=_gate(g,_self_union(g,g.sweep(roads_curve,g.mul(half,-1),half,-.4,.3)),p['Farm Roads'])
    road_mesh=_gate(g,_self_union(g,g.sweep(roads_curve,g.mul(half,-1),half,-.22,.095)),p['Farm Roads'])
    clip=g.prism(region,-.3,.22)
    road_mesh=_gate(g,_boolean_op(g,road_mesh,clip,'INTERSECT'),p['Farm Roads'])
    canals_curve=segments(g.boolean('AND',vertical,g.boolean('NOT',vr)))
    ch=g.math('MINIMUM',g.mul(p['Bund Width'],.34),.42)
    canal_void=_gate(g,_self_union(g,g.sweep(canals_curve,g.mul(ch,-1),ch,-.28,.24)),p['Irrigation'])
    inner=g.math('MAXIMUM',g.sub(ch,.09),.075)
    canal_parts=[g.sweep(canals_curve,g.mul(ch,-1),ch,-.22,-.16),
                 g.sweep(canals_curve,g.mul(ch,-1),g.mul(inner,-1),-.20,.12),
                 g.sweep(canals_curve,inner,ch,-.20,.12)]
    canal=_self_union(g,_join(g,canal_parts))
    water=g.sweep(canals_curve,g.mul(inner,-1),inner,-.155,-.115)
    def canal_clip(geo):return _gate(g,_boolean_op(g,_boolean_op(g,geo,road_void,'DIFFERENCE'),clip,'INTERSECT'),p['Irrigation'])
    canal=canal_clip(canal);water=canal_clip(water)
    g.section('03 / LAND · solid clipped parcels, bunds and persistent crop IDs',(3600,0))
    field_void=g.prism(field_plan,-.4,.3)
    bund=g.prism(region,-.25,.13)
    for cut in (field_void,road_void,canal_void):bund=_boolean_op(g,bund,cut,'DIFFERENCE')
    fields=g.prism(field_plan,-.25,.02)
    fields=_boolean_op(g,fields,clip,'INTERSECT')
    for cut in (road_void,canal_void):fields=_boolean_op(g,fields,cut,'DIFFERENCE')
    field_kind=_named(g,'farm_kind','INT')
    for i,mat in enumerate(mats['fields']):
        n=g.node('GeometryNodeSetMaterial');g.put(fields,n.inputs['Geometry']);n.inputs['Material'].default_value=mat
        g.put(g.equal(field_kind,i),n.inputs['Selection']);fields=n.outputs[0]
    tops=g.node('GeometryNodeSeparateGeometry',domain='FACE');g.put(fields,tops.inputs['Geometry']);g.put(g.math('GREATER_THAN',nz.outputs['Z'],.5),tops.inputs['Selection']);tops=tops.outputs[0]
    edges=g.boundary(tops)
    pieces=[]
    for geo,mat,layer in [(fields,None,10),(bund,mats['bund'],11),(road_mesh,mats['road'],12),(canal,mats['concrete'],13),(water,mats['water'],14)]:
        if mat:geo=_mat(g,geo,mat)
        pieces.append(_store(g,geo,'farm_layer',layer,'INT'))
    g.section('04 / CROPS · ray-sampled field types, rows and boundary clearance',(5400,0))
    # Bounded candidate lattice; empty/off-boundary candidates are removed by rays.
    spacing=g.math('MAXIMUM',p['Plant Spacing'],g.math('SQRT',g.div(g.mul(span.outputs['X'],span.outputs['Y']),180000)))
    def crop_points(step,orchard=False):
        grid=g.node('GeometryNodeMeshGrid')
        sx=g.math('MAXIMUM',g.math('FLOOR',g.div(span.outputs['X'],step)),1)
        sy=g.math('MAXIMUM',g.math('FLOOR',g.div(span.outputs['Y'],step)),1)
        g.put(g.add(sx,1),grid.inputs['Vertices X']);g.put(g.add(sy,1),grid.inputs['Vertices Y'])
        g.put(g.mul(sx,step),grid.inputs['Size X']);g.put(g.mul(sy,step),grid.inputs['Size Y'])
        offset=g.vector(g.add(low.outputs['X'],g.mul(g.mul(sx,step),.5)),g.add(low.outputs['Y'],g.mul(g.mul(sy,step),.5)),.02)
        grid_geo=_transform(g,grid.outputs['Mesh'],offset)
        ray=g.ray(tops,pos,field_kind)
        typ=ray.outputs['Attribute']
        valid=g.boolean('AND',ray.outputs['Is Hit'],g.math('GREATER_THAN',g.distance(edges,pos),2.2 if orchard else .52))
        valid=g.boolean('AND',valid,g.equal(typ,3) if orchard else g.math('LESS_THAN',typ,3))
        valid=g.boolean('AND',valid,p['Crops'])
        geo=_store(g,grid_geo,'farm_crop',typ,'INT')
        points=g.node('GeometryNodeMeshToPoints',mode='VERTICES');g.put(geo,points.inputs['Mesh']);g.put(valid,points.inputs['Selection'])
        return points.outputs[0]
    crop=crop_points(spacing)
    typ=_named(g,'farm_crop','INT')
    scale=g.random('FLOAT',.85,1.12,seed,idx,223)
    rot=g.vector(0,0,g.random('FLOAT',0,math.tau,seed,idx,227))
    pieces.append(g.instances(crop,col,typ,True,g.vector(scale,scale,g.random('FLOAT',.8,1.16,seed,idx,229)),rot))
    trees=crop_points(4.2,True)
    pieces.append(g.instances(trees,col,3,True,g.vector(scale,scale,scale),rot))
    grass=g.node('GeometryNodeDistributePointsOnFaces',distribute_method='RANDOM')
    g.put(bund,grass.inputs['Mesh']);g.put(seed,grass.inputs['Seed'])
    grass.inputs['Density'].default_value=3.2
    g.put(g.math('GREATER_THAN',nz.outputs['Z'],.9),grass.inputs['Selection'])
    safe=g.boolean('AND',p['Crops'],g.math('GREATER_THAN',g.distance(g.boundary(region),pos),.20))
    pieces.append(g.instances(grass.outputs['Points'],col,7,safe,g.vector(scale,scale,scale),rot))
    g.section('05 / FACILITIES · grounded farm buildings on allocated yards',(7400,0))
    ray=g.ray(tops,pos,field_kind)
    valid=g.boolean('AND',ray.outputs['Is Hit'],g.equal(ray.outputs['Attribute'],6))
    asset=g.random('INT',4,6,seed,idx,271)
    radius=_index_switch(g,g.sub(asset,4),'FLOAT',[8.3,8.8,7.2])
    valid=g.boolean('AND',valid,g.math('GREATER_THAN',g.distance(edges,pos),radius))
    valid=g.boolean('AND',valid,p['Structures'])
    yard_points=_transform(g,centers.outputs[0],(0,0,.02))
    pieces.append(g.instances(yard_points,col,asset,valid))
    result=_transform(g,_join(g,pieces,'Taiwan farm landscape'),g.vector(0,0,low.outputs['Z']),g.vector(0,0,angle))
    g.put(result,out.inputs[0])
    # Swept lane segments overlap at bends/junctions. Resolve those volumes
    # before clipping, including coplanar caps; FLOAT self-union is insufficient.
    for n in tree.nodes:
        if n.bl_idname=='GeometryNodeMeshBoolean':
            n.solver='EXACT';n.inputs['Self Intersection'].default_value=True
            n.inputs['Hole Tolerant'].default_value=True
    tree.use_fake_user=True;tree.asset_mark();tree.asset_data.description=tree.description
    for tag in ('Taiwan','Farmland','Geometry Nodes'):tree.asset_data.tags.new(tag)
    return tree


def add_farmland_modifier(obj):
    mod=obj.modifiers.new('TCity • Taiwan Farmland','NODES');mod.node_group=ensure_group()
    for name,_,default,*_ in SOCKETS:set_control(mod,name,default)
    obj['tc_farmland']=True
    return mod


def farmland_modifier(obj):
    if obj:return next((m for m in obj.modifiers if m.type=='NODES' and m.node_group and m.node_group.name.startswith('TCity • Taiwan Farmland')),None)


def make_farmland(name='TCity • 台灣農地',width=240,depth=180):
    x,y=width/2,depth/2
    mesh=bpy.data.meshes.new(name+' Boundary');mesh.from_pydata([(-x,-y,0),(x,-y,0),(x,y-22,0),(x-26,y,0),(-x,y,0)],[],[(0,1,2,3,4)]);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj;add_farmland_modifier(obj)
    return obj
