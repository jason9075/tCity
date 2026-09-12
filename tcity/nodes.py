"""Live region-to-district Geometry Nodes graph (no frame handlers)."""
import bpy
from .assets import PREFIX, ensure_assets, material

GROUP_NAME = 'TCity • Taiwan District v0.7'


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
    ('Open Spaces','NodeSocketBool',True,None,None,'Convert vacant valid lots to parking or pocket green / 空置基地轉為停車場或口袋綠地'),
    ('Parking Mix','NodeSocketFloat',.55,0,1,'Share of open lots used for parking; remainder becomes green / 空地中的停車場比例'),
    ('Parcel Guides','NodeSocketBool',False,None,None,'Show generated parcel faces for inspection / 顯示程序基地面供檢查'),
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
    ('Corner Buildings','NodeSocketBool',True,None,None,'Dual-frontage buildings at near-right-angle curved-road junctions instead of empty corner lots (curved streets only) / 轉角雙立面建築'),
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
    g.section('02 / ROAD GRID · unified centerline source',(1000,0))
    extra=g.math('MULTIPLY',p['Sidewalk Width'],2)
    px=g.math('ADD',g.math('ADD',g.math('MULTIPLY',p['Frontage'],p['Lots per Block']),p['Road Width']),extra)
    py=g.math('ADD',g.math('ADD',g.math('ADD',g.math('MULTIPLY',p['Depth'],2),p['Alley Width']),p['Road Width']),extra)
    from .roads import build_grid_network, curve_district
    grid_roads=build_grid_network(g,p,origin,sep.outputs['X'],sep.outputs['Y'],px,py)
    g.section('03–08 / DISTRICT · one road-driven pipeline',(2300,0))
    district=curve_district(g,p,cols,p['Geometry'],road_edges.outputs['Selection'],
                            grid_roads,boundary.outputs['Selection'])
    g.put(district,out.inputs[0])
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
