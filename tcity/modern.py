"""Modern residential community placement with complete site-area containment.

Shared street infrastructure is reused at community-block scale. Candidate sites
are intersected with the input region and accepted only when their whole top
area survives, so concave cuts and interior holes cannot hide inside a site.
"""
import bpy
from .nodes import set_control,SOCKETS as CITY_SOCKETS,road_material
from .farmland import FarmGraph
from .roads import _store,_named,_transform,_join,_gate,_boolean_op
from .modern_assets import ensure_modern_assets,CATALOG,MIN_FLOORS,MAX_FLOORS,SITE_WIDTH,SITE_DEPTH

GROUP_NAME='TCity • Modern Taiwan Communities v0.1'
SOCKETS=[
    ('Seed','NodeSocketInt',41,0,100000,'配置、立面與樓高種子 / Deterministic variation'),
    ('Density','NodeSocketFloat',.92,0,1,'整個社區基地的使用機率 / Community occupancy'),
    ('Community Width','NodeSocketFloat',60.,52.,90.,'社區模組寬度，包含棟距與庭院 / Module width in metres'),
    ('Community Depth','NodeSocketFloat',48.,42.,80.,'社區模組進深 / Module depth in metres'),
    ('Min Floors','NodeSocketInt',12,MIN_FLOORS,MAX_FLOORS,'主要塔樓最低層數，包含一樓 / Minimum main-tower storeys'),
    ('Max Floors','NodeSocketInt',20,MIN_FLOORS,MAX_FLOORS,'主要塔樓最高層數 / Maximum main-tower storeys'),
    ('Twin Community Mix','NodeSocketFloat',.65,0,1,'非大陽台類型中的雙棟比例 / Twin towers among non-green types'),
    ('Green Balcony Mix','NodeSocketFloat',.28,0,1,'弧邊大陽台社區機率 / Deep-balcony community probability'),
    ('Buildings','NodeSocketBool',True,None,None,'大樓、基座與共用庭院 / Architecture and community hardscape'),
    ('Landscape','NodeSocketBool',True,None,None,'社區庭園樹木 / Shared garden trees'),
    ('Road Width','NodeSocketFloat',12.,6.,24.,'社區之間的道路寬度 / Carriageway width'),
    ('Sidewalk Width','NodeSocketFloat',2.,1.,4.,'社區外圍人行道寬度 / Pavement width'),
    ('Ground','NodeSocketBool',True,None,None,'實體道路與人行道 / Streets and paving'),
    ('Road Markings','NodeSocketBool',True,None,None,'道路標線 / Road markings'),
    ('Road Details','NodeSocketBool',True,None,None,'排水格柵與人孔蓋 / Drainage and access covers'),
    ('Telecom Cabinets','NodeSocketBool',True,None,None,'沿街電信設備 / Street telecom cabinets'),
]
PRESETS={
    'URBAN':{'Twin Community Mix':0.,'Green Balcony Mix':0.,'Min Floors':15,'Max Floors':24},
    'TWIN':{'Twin Community Mix':1.,'Green Balcony Mix':0.,'Min Floors':12,'Max Floors':20},
    'GREEN':{'Twin Community Mix':0.,'Green Balcony Mix':1.,'Min Floors':6,'Max Floors':12},
}


def ensure_group():
    if GROUP_NAME in bpy.data.node_groups:return bpy.data.node_groups[GROUP_NAME]
    catalog=ensure_modern_assets();gardens=bpy.data.collections[CATALOG+' • Landscape']
    tree=bpy.data.node_groups.new(GROUP_NAME,'GeometryNodeTree');tree.is_modifier=True
    tree.description='完整社區基地配置：較新台灣住宅大樓、双棟、大陽台、庭園與沿街設施。公尺。'
    tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    for name,kind,default,low,high,desc in SOCKETS:
        s=tree.interface.new_socket(name=name,in_out='INPUT',socket_type=kind);s.default_value=default;s.description=desc
        if low is not None:s.min_value=low;s.max_value=high
    tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    g=FarmGraph(tree);inp=g.node('NodeGroupInput');p=inp.outputs;out=g.node('NodeGroupOutput')
    inp.location=(-600,0);out.location=(8500,0)
    g.section('01 / COMMUNITY SITES · whole blocks, not individual shopfronts',(0,0))
    region=p['Geometry'];bbox=g.node('GeometryNodeBoundBox');g.put(region,bbox.inputs['Geometry'])
    origin=bbox.outputs['Min'];size=g.node('ShaderNodeSeparateXYZ');g.put(g.vmath('SUBTRACT',bbox.outputs['Max'],origin),size.inputs[0])
    boundary=g.boundary(region);W=p['Community Width'];D=p['Community Depth'];R=p['Road Width'];S=p['Sidewalk Width']
    px=g.add(W,g.add(R,g.mul(S,2)));py=g.add(D,g.add(R,g.mul(S,2)))
    nx=g.math('MAXIMUM',g.math('CEIL',g.div(size.outputs['X'],px)),1)
    ny=g.math('MAXIMUM',g.math('CEIL',g.div(size.outputs['Y'],py)),1)
    count=g.math('MINIMUM',g.mul(nx,ny),400)
    line=g.node('GeometryNodeMeshLine',mode='OFFSET');g.put(count,line.inputs['Count'])
    idx=g.node('GeometryNodeInputIndex').outputs[0];pos=g.node('GeometryNodeInputPosition').outputs[0]
    x=g.add(g.mul(g.math('MODULO',idx,nx),px),g.mul(px,.5))
    y=g.add(g.mul(g.math('FLOOR',g.div(idx,nx)),py),g.mul(py,.5))
    points=g.node('GeometryNodeSetPosition');g.put(line.outputs['Mesh'],points.inputs['Geometry'])
    g.put(g.vmath('ADD',origin,g.vector(x,y,.14)),points.inputs['Position'])
    sites=_store(g,points.outputs[0],'tc_community_id',g.add(idx,1),'INT')
    floors=g.random('INT',g.math('MINIMUM',p['Min Floors'],p['Max Floors']),g.math('MAXIMUM',p['Min Floors'],p['Max Floors']),p['Seed'],idx,911)
    twin=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],idx,919),p['Twin Community Mix'])
    green=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],idx,929),p['Green Balcony Mix'])
    style=g.switch(green,twin,2)
    sites=_store(g,sites,'tc_community_floors',floors,'INT');sites=_store(g,sites,'tc_community_style',style,'INT')
    g.section('02 / CONTAINMENT · accept only complete site footprints',(1600,0))
    cube=g.node('GeometryNodeMeshCube');g.put(g.vector(W,D,.12),cube.inputs['Size'])
    instance=g.node('GeometryNodeInstanceOnPoints');g.put(sites,instance.inputs['Points']);g.put(cube.outputs['Mesh'],instance.inputs['Instance'])
    realized=g.node('GeometryNodeRealizeInstances');g.put(instance.outputs[0],realized.inputs['Geometry'])
    normal=g.node('GeometryNodeInputNormal');nz=g.node('ShaderNodeSeparateXYZ');g.put(normal.outputs[0],nz.inputs[0])
    flip=g.node('GeometryNodeFlipFaces');g.put(region,flip.inputs['Mesh']);g.put(g.math('LESS_THAN',nz.outputs['Z'],0),flip.inputs['Selection'])
    volume=g.prism(flip.outputs[0],-.5,1.)
    owned=_store(g,realized.outputs[0],'tc_site_owner',_named(g,'tc_community_id','INT'),'INT','FACE')
    clipped=_boolean_op(g,owned,volume,'INTERSECT')
    facearea=g.node('GeometryNodeInputMeshFaceArea').outputs[0]
    accum=g.node('GeometryNodeAccumulateField',data_type='FLOAT',domain='FACE')
    g.put(g.mul(facearea,g.math('GREATER_THAN',nz.outputs['Z'],.99)),accum.inputs['Value'])
    g.put(_named(g,'tc_site_owner','INT'),accum.inputs['Group ID'])
    areas=_store(g,clipped,'tc_site_area',accum.outputs['Total'],'FLOAT','FACE')
    def sample(value,dtype):
        n=g.node('GeometryNodeSampleNearestSurface',data_type=dtype);g.put(areas,n.inputs['Mesh']);g.put(value,n.inputs['Value']);g.put(pos,n.inputs['Sample Position']);return n.outputs['Value']
    area=sample(_named(g,'tc_site_area'),'FLOAT')
    identity=sample(_named(g,'tc_site_owner','INT'),'INT')
    whole=g.equal(area,g.mul(W,D),.002)
    same=g.equal(identity,_named(g,'tc_community_id','INT'))
    occupied=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],_named(g,'tc_community_id','INT'),937),p['Density'])
    valid=g.boolean('AND',g.boolean('AND',whole,same),occupied)
    filtered=g.node('GeometryNodeMeshToPoints',mode='VERTICES');g.put(sites,filtered.inputs['Mesh']);g.put(valid,filtered.inputs['Selection'])
    g.section('03 / MODULAR ARCHITECTURE · shared floors and fixed storey height',(3200,0))
    style=_named(g,'tc_community_style','INT');floors=_named(g,'tc_community_floors','INT')
    asset=g.add(g.mul(g.sub(floors,MIN_FLOORS),3),style)
    scale=g.vector(g.div(W,SITE_WIDTH),g.div(D,SITE_DEPTH),1)
    architecture=g.instances(filtered.outputs[0],catalog,asset,p['Buildings'],scale)
    landscape=g.instances(filtered.outputs[0],gardens,style,g.boolean('AND',p['Buildings'],p['Landscape']),scale)
    # Reuse district roads, at community scale, with a continuous paved island.
    # Zero rear alley joins the two street-facing pavement halves under the site.
    q={name:default for name,_,default,*_ in CITY_SOCKETS}
    q.update({name:p[name] for name in ('Geometry','Seed','Ground','Road Width','Sidewalk Width','Road Markings','Road Details','Telecom Cabinets')})
    q.update({'Frontage':g.div(W,4),'Lots per Block':4,'Depth':g.mul(D,.5),'Alley Width':0.,
              'Sidewalks':True,'Road Surface':True,'Utility Poles':False,'Overhead Wires':False,
              'Curb Height':.14,'Cabinet Density':.75})
    from .infrastructure import infrastructure
    roads=infrastructure(g,q,origin,px,py,nx,ny,boundary,road_material)
    g.put(_join(g,[architecture,landscape]+roads,'Modern communities and streets'),out.inputs[0])
    tree.use_fake_user=True;tree.asset_mark();tree.asset_data.description=tree.description
    for tag in ('Taiwan','Modern housing','Geometry Nodes'):tree.asset_data.tags.new(tag)
    return tree


def modern_modifier(obj):
    if obj:return next((m for m in obj.modifiers if m.type=='NODES' and m.node_group and m.node_group.name.startswith('TCity • Modern Taiwan Communities')),None)


def add_modern_modifier(obj):
    mod=obj.modifiers.new('TCity • Modern Taiwan Communities','NODES');mod.node_group=ensure_group()
    for name,_,default,*_ in SOCKETS:set_control(mod,name,default)
    obj['tc_modern']=True
    return mod


def make_modern_region(name='TCity • 台灣新式住宅社區',width=228,depth=192):
    x,y=width/2,depth/2;mesh=bpy.data.meshes.new(name+' Boundary')
    mesh.from_pydata([(-x,-y,0),(x,-y,0),(x,y,0),(-x,y,0)],[],[(0,1,2,3)]);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj;add_modern_modifier(obj)
    return obj
