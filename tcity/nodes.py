"""Live region-to-district Geometry Nodes graph (no frame handlers)."""
import math
import bpy
from .assets import PREFIX, ensure_assets, material

GROUP_NAME = 'TCity • Taiwan District v0.6'


class Graph:
    def __init__(self, tree):
        self.tree = tree
        self.frame = None
        self.serial = 0

    def section(self, title, location):
        self.frame = self.tree.nodes.new('NodeFrame')
        self.frame.label = title; self.frame.name = title
        self.frame.location = location; self.frame.use_custom_color = True
        self.frame.color = (.12,.23,.20); self.serial = 0

    def node(self, kind, label='', **attrs):
        n = self.tree.nodes.new(kind)
        if label: n.label = label; n.name = label
        for key,value in attrs.items(): setattr(n,key,value)
        n.parent = self.frame
        n.location = (self.serial%5*205,-self.serial//5*230)
        self.serial += 1
        n.width = 180
        return n

    def put(self, value, socket):
        if isinstance(value,bpy.types.NodeSocket): self.tree.links.new(value,socket)
        else: socket.default_value = value

    def math(self, op, a, b=0, label='', c=None):
        n = self.node('ShaderNodeMath',label or op.title(),operation=op)
        self.put(a,n.inputs[0]); self.put(b,n.inputs[1])
        if c is not None: self.put(c,n.inputs[2])
        return n.outputs[0]

    def equal(self, a, b, epsilon=.5):
        return self.math('COMPARE',a,b,'Equal',c=epsilon)

    def vector(self, x=0,y=0,z=0):
        n = self.node('ShaderNodeCombineXYZ')
        for v,s in zip((x,y,z),n.inputs): self.put(v,s)
        return n.outputs[0]

    def vmath(self, op, a, b):
        n = self.node('ShaderNodeVectorMath',operation=op)
        self.put(a,n.inputs[0]); self.put(b,n.inputs[1])
        return n.outputs['Vector']

    def boolean(self, op, a, b=False):
        n = self.node('FunctionNodeBooleanMath',operation=op)
        self.put(a,n.inputs[0])
        if len(n.inputs)>1:self.put(b,n.inputs[1])
        return n.outputs[0]

    def random(self, dtype, low, high, seed, id_socket, offset=0):
        n = self.node('FunctionNodeRandomValue', data_type=dtype)
        # INT and FLOAT sockets share display names. Only use enabled sockets.
        for name,val in [('Min',low),('Max',high),('ID',id_socket)]:
            self.put(val,next(s for s in n.inputs if s.name==name and s.enabled))
        self.put(self.math('ADD',seed,offset),n.inputs['Seed'])
        return next(s for s in n.outputs if s.enabled)


def road_material():
    name = PREFIX + 'v04 Asphalt + procedural road paint'
    if name in bpy.data.materials: return bpy.data.materials[name]
    m = material('v04 Asphalt + procedural road paint',(.07,.075,.07),roughness=.86)
    g=Graph(m.node_tree); bs=m.node_tree.nodes.get('Principled BSDF')
    tex=g.node('ShaderNodeTexCoord')
    attrs={}
    for key in ('origin','period_x','period_y','road_width','markings'):
        a=g.node('ShaderNodeAttribute'); a.attribute_name='tc_'+key
        attrs[key]=a.outputs['Vector' if key=='origin' else 'Fac']
    rel=g.vmath('SUBTRACT',tex.outputs['Object'],attrs['origin'])
    sep=g.node('ShaderNodeSeparateXYZ'); g.put(rel,sep.inputs[0])
    dx=g.math('PINGPONG',sep.outputs['X'],g.math('MULTIPLY',attrs['period_x'],.5))
    dy=g.math('PINGPONG',sep.outputs['Y'],g.math('MULTIPLY',attrs['period_y'],.5))
    half=g.math('MULTIPLY',attrs['road_width'],.5)
    # Two narrow yellow lines; remove them across intersecting roads.
    yellow=g.math('MULTIPLY',g.math('LESS_THAN',g.math('ABSOLUTE',g.math('SUBTRACT',dy,.15)),.05),
                  g.math('GREATER_THAN',dx,g.math('ADD',half,3.0)))
    yellow2=g.math('MULTIPLY',g.math('LESS_THAN',g.math('ABSOLUTE',g.math('SUBTRACT',dx,.15)),.05),g.math('GREATER_THAN',dy,g.math('ADD',half,3.0)))
    yellow=g.math('MAXIMUM',yellow,yellow2)
    # White stop bars and zebra markings on each approach to an intersection.
    crossing_x=g.math('LESS_THAN',g.math('ABSOLUTE',g.math('SUBTRACT',dx,g.math('ADD',half,1.5))),.95)
    crossing_y=g.math('LESS_THAN',dy,g.math('SUBTRACT',half,.55))
    stripes=g.math('LESS_THAN',g.math('PINGPONG',sep.outputs['Y'],.65),.30)
    white=g.math('MULTIPLY',g.math('MULTIPLY',crossing_x,crossing_y),stripes)
    crossing_y2=g.math('LESS_THAN',g.math('ABSOLUTE',g.math('SUBTRACT',dy,g.math('ADD',half,1.5))),.95)
    crossing_x2=g.math('LESS_THAN',dx,g.math('SUBTRACT',half,.55))
    stripes2=g.math('LESS_THAN',g.math('PINGPONG',sep.outputs['X'],.65),.30)
    white=g.math('MAXIMUM',white,g.math('MULTIPLY',g.math('MULTIPLY',crossing_y2,crossing_x2),stripes2))
    wear=g.node('ShaderNodeTexNoise');wear.inputs['Scale'].default_value=24;g.put(tex.outputs['Object'],wear.inputs['Vector'])
    worn=g.math('MULTIPLY',g.math('GREATER_THAN',wear.outputs['Fac'],.31),attrs['markings'])
    yellow=g.math('MULTIPLY',yellow,worn);white=g.math('MULTIPLY',white,worn)
    noise=g.node('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=95
    g.put(tex.outputs['Object'],noise.inputs['Vector'])
    base=g.node('ShaderNodeMixRGB')
    g.put(noise.outputs['Fac'],base.inputs[0])
    base.inputs[1].default_value=(.035,.043,.042,1); base.inputs[2].default_value=(.08,.09,.085,1)
    paint=g.node('ShaderNodeMixRGB'); g.put(yellow,paint.inputs[0]);g.put(base.outputs[0],paint.inputs[1])
    paint.inputs[2].default_value=(.9,.53,.055,1)
    final=g.node('ShaderNodeMixRGB');g.put(white,final.inputs[0]);g.put(paint.outputs[0],final.inputs[1])
    final.inputs[2].default_value=(.78,.77,.65,1)
    g.put(final.outputs[0],bs.inputs['Base Color'])
    bump=g.node('ShaderNodeBump');bump.inputs['Strength'].default_value=.20;bump.inputs['Distance'].default_value=.004
    g.put(noise.outputs['Fac'],bump.inputs['Height']);g.put(bump.outputs[0],bs.inputs['Normal'])
    return m


SOCKETS = [
    ('Seed','NodeSocketInt',17,0,100000,'Deterministic district variation / 隨機種子'),
    ('Density','NodeSocketFloat',.94,0,1,'Probability of occupied lots / 建築密度'),
    ('Frontage','NodeSocketFloat',7.2,5.2,10,'Lot frontage in metres / 面寬'),
    ('Depth','NodeSocketFloat',14,9,18,'Lot depth in metres / 進深'),
    ('Lots per Block','NodeSocketInt',4,2,10,'Shopfronts along each side / 每排戶數'),
    ('Road Width','NodeSocketFloat',6,4,20,'Street width in metres / 道路寬度'),
    ('Alley Width','NodeSocketFloat',2,1,6,'Rear service alley / 後巷寬度'),
    ('Min Floors','NodeSocketInt',4,2,7,'Minimum occupied storeys / 最低樓層'),
    ('Max Floors','NodeSocketInt',5,2,7,'Maximum occupied storeys / 最高樓層'),
    ('Townhouse Mix','NodeSocketFloat',.15,0,1,'Share of alternate facade variants / 第二組住宅立面比例'),
    ('Boundary Setback','NodeSocketFloat',.2,0,10,'Extra clearance inside region boundary / 邊界退縮'),
    ('Road Curves','NodeSocketObject',None,None,None,'選配的外部道路中心線曲線物件；留空則使用區域網格內畫的游離邊 / Optional external road centerline curve object; leave empty to draw free edges inside the region instead'),
    ('Smooth Streets','NodeSocketBool',True,None,None,'將道路邊平滑成 Catmull-Rom 曲線；關閉維持折角路口 / Smooth drawn road edges into a Catmull-Rom curve'),
    ('Road Resolution','NodeSocketFloat',1.,.25,5.,'道路中心線取樣間距，公尺 / Centerline resample spacing in metres'),
    ('Bend Buildings to Curve','NodeSocketBool',True,None,None,'讓曲線街道的街屋沿曲率彎折（需要 Realize Instances，較耗記憶體） / Bend curved-street rowhouses along the curve (Realize Instances; more memory)'),
    ('Signs','NodeSocketBool',True,None,None,'Shop signage / 店家招牌'),
    ('Rooftops','NodeSocketBool',True,None,None,'Water tanks and sheet metal additions / 屋頂設施'),
    ('Street Life','NodeSocketBool',True,None,None,'Potted plants and street props / 街邊物件與盆栽'),
    ('Buildings','NodeSocketBool',True,None,None,'Display buildings / 顯示建築'),
    ('Ground','NodeSocketBool',True,None,None,'Region surface and painted roads / 地面'),
    ('Metal Shed Mix','NodeSocketFloat',0.,0,1,'Share of one-storey corrugated metal workshops; exempt from floor range / 獨棟鐵皮屋比例'),
    ('Rooftop Addition Mix','NodeSocketFloat',.85,0,1,'Probability of inhabited rooftop extensions; tanks and stair cores remain / 住宅頂樓加蓋比例'),
    ('Road Surface','NodeSocketBool',True,None,None,'Solid asphalt carriageway and rear alleys / 實體道路面'),
    ('Sidewalks','NodeSocketBool',True,None,None,'Raised paved islands and curb faces / 人行道與路緣'),
    ('Sidewalk Width','NodeSocketFloat',1.25,.8,3.,'Reserved frontage/side pavement width in metres / 人行道寬度'),
    ('Curb Height','NodeSocketFloat',.14,.08,.25,'Pavement top above asphalt / 路緣高度'),
    ('Road Thickness','NodeSocketFloat',.18,.06,.6,'Asphalt volume below input surface / 路面厚度'),
    ('Road Markings','NodeSocketBool',True,None,None,'Worn center lines and crosswalks on both road axes / 雙向道路標線'),
    ('Road Details','NodeSocketBool',True,None,None,'Drain grates and road access covers / 排水溝蓋與人孔蓋'),
    ('Utility Poles','NodeSocketBool',True,None,None,'Taiwanese concrete utility poles / 混凝土電線桿'),
    ('Pole Spacing','NodeSocketFloat',30.,8.,60.,'Maximum span; each block segment includes end poles / 電桿最大跨距'),
    ('Pole Height','NodeSocketFloat',9.,7.,13.,'Pole and wire attachment height / 電桿高度'),
    ('Overhead Wires','NodeSocketBool',True,None,None,'Connect supported pole pairs within each block frontage / 架空線'),
    ('Cable Sag','NodeSocketFloat',.55,0,1.5,'Wire midspan sag, capped at 12 percent of pole height / 電線垂度'),
    ('Telecom Cabinets','NodeSocketBool',True,None,None,'Grounded roadside telecom cabinets / 電信交接箱'),
    ('Cabinet Density','NodeSocketFloat',.70,0,1,'Probability per block frontage / 電信箱出現比例'),
]


def ensure_group():
    if GROUP_NAME in bpy.data.node_groups: return bpy.data.node_groups[GROUP_NAME]
    cols=ensure_assets()
    tree=bpy.data.node_groups.new(GROUP_NAME,'GeometryNodeTree');tree.is_modifier=True
    tree.description='Planar filled region → Taiwanese mixed-use district. Units: metres.'
    tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    for name,kind,default,minimum,maximum,desc in SOCKETS:
        s=tree.interface.new_socket(name=name,in_out='INPUT',socket_type=kind)
        s.default_value=default;s.description=desc
        if minimum is not None: s.min_value=minimum;s.max_value=maximum
    tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    g=Graph(tree)
    inp=g.node('NodeGroupInput','District controls');inp.location=(-600,0)
    out=g.node('NodeGroupOutput','Taiwan district');out.location=(9800,0)
    p=inp.outputs
    g.section('01 / REGION · bounding box and boundary edges',(-200,0))
    bbox=g.node('GeometryNodeBoundBox');g.put(p['Geometry'],bbox.inputs['Geometry'])
    span=g.vmath('SUBTRACT',bbox.outputs['Max'],bbox.outputs['Min'])
    sep=g.node('ShaderNodeSeparateXYZ');g.put(span,sep.inputs[0])
    origin=bbox.outputs['Min']
    nbr=g.node('GeometryNodeInputMeshEdgeNeighbors')
    # Face Count == 1 is a true boundary edge; == 0 is a free edge drawn inside the
    # region, reserved for road centerlines (decision 1 / docs/PLAN.md §4.1).
    edge=g.equal(nbr.outputs['Face Count'],1)
    boundary=g.node('GeometryNodeSeparateGeometry',domain='EDGE')
    g.put(p['Geometry'],boundary.inputs['Geometry']);g.put(edge,boundary.inputs['Selection'])
    road_edge_sel=g.equal(nbr.outputs['Face Count'],0)
    road_edges=g.node('GeometryNodeSeparateGeometry','Road centerline edges',domain='EDGE')
    g.put(p['Geometry'],road_edges.inputs['Geometry']);g.put(road_edge_sel,road_edges.inputs['Selection'])
    g.section('02 / PARCELS · streets, paired rows and back alleys',(1000,0))
    extra=g.math('MULTIPLY',p['Sidewalk Width'],2)
    px=g.math('ADD',g.math('ADD',g.math('MULTIPLY',p['Frontage'],p['Lots per Block']),p['Road Width']),extra)
    py=g.math('ADD',g.math('ADD',g.math('ADD',g.math('MULTIPLY',p['Depth'],2),p['Alley Width']),p['Road Width']),extra)
    nx=g.math('MAXIMUM',g.math('CEIL',g.math('DIVIDE',sep.outputs['X'],px)),1)
    ny=g.math('MAXIMUM',g.math('CEIL',g.math('DIVIDE',sep.outputs['Y'],py)),1)
    slots=g.math('MULTIPLY',p['Lots per Block'],2)
    count=g.math('MINIMUM',g.math('MULTIPLY',g.math('MULTIPLY',nx,ny),slots),20000)
    line=g.node('GeometryNodeMeshLine',mode='OFFSET');g.put(count,line.inputs['Count'])
    idx=g.node('GeometryNodeInputIndex').outputs[0]
    block=g.math('FLOOR',g.math('DIVIDE',idx,slots))
    bx=g.math('MODULO',block,nx);by=g.math('FLOOR',g.math('DIVIDE',block,nx))
    col=g.math('MODULO',idx,p['Lots per Block'])
    row=g.math('MODULO',g.math('FLOOR',g.math('DIVIDE',idx,p['Lots per Block'])),2)
    x=g.math('ADD',g.math('ADD',g.math('MULTIPLY',bx,px),g.math('MULTIPLY',g.math('ADD',col,.5),p['Frontage'])),g.math('MULTIPLY',p['Road Width'],.5))
    y=g.math('ADD',g.math('ADD',g.math('MULTIPLY',by,py),g.math('MULTIPLY',row,g.math('ADD',p['Depth'],p['Alley Width']))),g.math('MULTIPLY',g.math('ADD',p['Depth'],p['Road Width']),.5))
    loc=g.vmath('ADD',origin,g.vector(g.math('ADD',x,p['Sidewalk Width']),g.math('ADD',y,p['Sidewalk Width']),0))
    positions=g.node('GeometryNodeSetPosition');g.put(line.outputs['Mesh'],positions.inputs['Geometry']);g.put(loc,positions.inputs['Position'])
    # Capture row direction before selections compact the point domain.
    capture=g.node('GeometryNodeCaptureAttribute',domain='POINT')
    capture.capture_items.new('FLOAT','Facing')
    g.put(positions.outputs['Geometry'],capture.inputs['Geometry'])
    g.put(g.math('MULTIPLY',row,math.pi),capture.inputs['Facing'])
    g.section('03 / BOUNDARY · inside test + full footprint clearance',(2300,0))
    pos=g.node('GeometryNodeInputPosition').outputs[0]
    ray=g.node('GeometryNodeRaycast',data_type='FLOAT')
    g.put(p['Geometry'],ray.inputs['Target Geometry'])
    g.put(g.vmath('ADD',pos,(0,0,100)),ray.inputs['Source Position'])
    ray.inputs['Ray Direction'].default_value=(0,0,-1);ray.inputs['Ray Length'].default_value=200
    prox=g.node('GeometryNodeProximity',target_element='EDGES')
    g.put(boundary.outputs['Selection'],prox.inputs['Geometry']);g.put(pos,prox.inputs['Sample Position'])
    radius=g.math('ADD',g.math('MULTIPLY',g.math('SQRT',g.math('ADD',g.math('MULTIPLY',p['Frontage'],p['Frontage']),g.math('MULTIPLY',p['Depth'],p['Depth']))),.5),p['Boundary Setback'])
    inside=g.boolean('AND',ray.outputs['Is Hit'],g.math('GREATER_THAN',prox.outputs['Distance'],radius))
    occupied=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],idx,43),p['Density'])
    choose=g.boolean('AND',inside,occupied)
    # Store inspection attributes before filtering, keeping IDs stable by parcel.
    floors=g.random('INT',g.math('MINIMUM',p['Min Floors'],p['Max Floors']),g.math('MAXIMUM',p['Min Floors'],p['Max Floors']),p['Seed'],idx,101)
    typ=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],idx,307),p['Townhouse Mix'])
    palette=g.random('INT',0,2,p['Seed'],idx,701)
    asset=g.math('ADD',g.math('MULTIPLY',g.math('SUBTRACT',floors,2),6),g.math('ADD',g.math('MULTIPLY',typ,3),palette))
    is_shed=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],idx,1103),p['Metal Shed Mix'])
    shed_asset=g.math('ADD',36,g.random('INT',0,5,p['Seed'],idx,1201))
    select=g.node('GeometryNodeSwitch','Rowhouse or metal workshop',input_type='INT')
    g.put(is_shed,select.inputs['Switch']);g.put(asset,select.inputs['False']);g.put(shed_asset,select.inputs['True'])
    asset=select.outputs[0]
    storeys=g.node('GeometryNodeSwitch','One-storey sheds',input_type='INT')
    g.put(is_shed,storeys.inputs['Switch']);g.put(floors,storeys.inputs['False']);storeys.inputs['True'].default_value=1
    floors=storeys.outputs[0]
    geo=capture.outputs['Geometry']
    for name,value,dtype in [('tc_parcel_id',idx,'INT'),('tc_floors',floors,'INT'),('tc_asset',asset,'INT'),('tc_is_shed',is_shed,'BOOLEAN')]:
        store=g.node('GeometryNodeStoreNamedAttribute',data_type=dtype,domain='POINT')
        store.inputs['Name'].default_value=name;g.put(geo,store.inputs['Geometry']);g.put(value,store.inputs['Value'])
        geo=store.outputs['Geometry']
    points=g.node('GeometryNodeMeshToPoints',mode='VERTICES')
    g.put(geo,points.inputs['Mesh']);g.put(choose,points.inputs['Selection'])
    g.section('04 / KIT · deterministic facade, roof, signage and props',(3700,0))
    named=g.node('GeometryNodeInputNamedAttribute',data_type='INT');named.inputs['Name'].default_value='tc_asset'
    shed_attr=g.node('GeometryNodeInputNamedAttribute',data_type='BOOLEAN');shed_attr.inputs['Name'].default_value='tc_is_shed'
    parcel_attr=g.node('GeometryNodeInputNamedAttribute',data_type='INT');parcel_attr.inputs['Name'].default_value='tc_parcel_id'
    addon_probability=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],parcel_attr.outputs['Attribute'],1601),p['Rooftop Addition Mix'])
    scale=g.vector(g.math('DIVIDE',p['Frontage'],6.4),g.math('DIVIDE',p['Depth'],12),1)
    rotation=g.vector(0,0,capture.outputs['Facing'])
    pieces=[]
    for key,toggle in [('Buildings','Buildings'),('Signs','Signs'),('Roofs','Rooftops'),('Street life','Street Life'),('Additions','Rooftops')]:
        collection=g.node('GeometryNodeCollectionInfo',key)
        collection.inputs['Collection'].default_value=cols[key]
        collection.inputs['Separate Children'].default_value=True
        collection.inputs['Reset Children'].default_value=True
        instance=g.node('GeometryNodeInstanceOnPoints',key+' on parcels')
        g.put(points.outputs['Points'],instance.inputs['Points'])
        g.put(collection.outputs['Instances'],instance.inputs['Instance'])
        instance.inputs['Pick Instance'].default_value=True
        g.put(named.outputs['Attribute'],instance.inputs['Instance Index'])
        g.put(rotation,instance.inputs['Rotation']);g.put(scale,instance.inputs['Scale'])
        selection=p[toggle] if key=='Buildings' else g.boolean('AND',p[toggle],p['Buildings'])
        if key=='Additions':selection=g.boolean('AND',selection,g.boolean('AND',addon_probability,g.boolean('NOT',shed_attr.outputs['Attribute'])))
        g.put(selection,instance.inputs['Selection'])
        pieces.append(instance.outputs['Instances'])
    from .infrastructure import infrastructure
    streets=infrastructure(g,p,origin,px,py,nx,ny,boundary.outputs['Selection'],road_material)
    grid_join=g.node('GeometryNodeJoinGeometry','Grid district layers')
    for geom in pieces+streets:g.put(geom,grid_join.inputs['Geometry'])
    g.section('08 / CURVED STREETS · dual branch (docs/PLAN.md 0.5.0)',(5100,1400))
    from .roads import curve_district
    curve_geo,has_curve=curve_district(g,p,cols,p['Geometry'],road_edges.outputs['Selection'],
                                        boundary.outputs['Selection'],road_material)
    branch=g.node('GeometryNodeSwitch','Grid or curved streets',input_type='GEOMETRY')
    g.put(has_curve,branch.inputs['Switch'])
    g.put(grid_join.outputs[0],branch.inputs['False']);g.put(curve_geo,branch.inputs['True'])
    g.put(branch.outputs[0],out.inputs[0])
    tree.use_fake_user=True
    tree.asset_mark()
    tree.asset_data.description=tree.description
    for tag in ('Taiwan','Architecture','Procedural','Geometry Nodes'):tree.asset_data.tags.new(tag)
    return tree


def socket_id(group,name):
    return next(s.identifier for s in group.interface.items_tree if s.item_type=='SOCKET' and s.in_out=='INPUT' and s.name==name)


def set_control(mod,name,value):
    key=socket_id(mod.node_group,name)
    if hasattr(mod,'properties'):
        getattr(mod.properties.inputs,key).value=value
    else:
        mod[key]=value
    mod.id_data.update_tag()


def get_control(mod,name):
    key=socket_id(mod.node_group,name)
    if hasattr(mod,'properties'):return getattr(mod.properties.inputs,key).value
    return mod[key]


def draw_control(layout,mod,name,label):
    key=socket_id(mod.node_group,name)
    if hasattr(mod,'properties'):layout.prop(getattr(mod.properties.inputs,key),'value',text=label)
    else:layout.prop(mod,'["'+key+'"]',text=label)


def add_modifier(obj):
    mod=obj.modifiers.new('TCity • Taiwan District','NODES');mod.node_group=ensure_group()
    for name,_,default,*_ in SOCKETS:set_control(mod,name,default)
    obj['tc_region']=True
    return mod


def upgrade_modifier(mod):
    """Create the versioned kit; keep old graphs and shared assets untouched."""
    old_names={s.name for s in mod.node_group.interface.items_tree
               if s.item_type=='SOCKET' and s.in_out=='INPUT'}
    values={name:get_control(mod,name) for name,*_ in SOCKETS if name in old_names}
    mod.node_group=ensure_group()
    for name,_,default,*_ in SOCKETS:set_control(mod,name,values.get(name,default))
