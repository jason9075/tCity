"""TCity — Taiwanese districts for Blender Geometry Nodes."""
bl_info = {
    'name': 'TCity — Taiwan Districts',
    'author': 'TCity contributors',
    'version': (0,6,4),
    'blender': (5,2,0),
    'location': 'View3D > Sidebar > TCity',
    'description': 'Generate Taiwanese mixed-use streets from a filled planar region',
    'category': 'Add Mesh',
}

import math
import bpy
from .nodes import add_modifier, SOCKETS, set_control, get_control, draw_control, upgrade_modifier, GROUP_NAME
from .farmland import farmland_modifier
from .farm_ui import CLASSES as FARM_CLASSES
from .modern_ui import CLASSES as MODERN_CLASSES
from .modern import modern_modifier


def district_modifier(obj):
    if obj:
        return next((m for m in obj.modifiers if m.type=='NODES' and m.node_group and
                     m.node_group.name.startswith('TCity • Taiwan District')),None)


def curvature_warning(context,obj):
    """Read the GN-authored warning flag without duplicating curvature math in UI."""
    try:
        evaluated=obj.evaluated_get(context.evaluated_depsgraph_get())
        attribute=evaluated.data.attributes.get('tc_curvature_warning')
        if not attribute:return False
        values=bytearray(len(attribute.data));attribute.data.foreach_get('value',values)
        return any(values)
    except (AttributeError,ReferenceError,RuntimeError):
        return False


def validate_region(obj):
    if not obj or obj.type!='MESH': return 'Select a filled mesh region / 請選擇有面的平面網格'
    mesh=obj.data
    if not mesh.polygons: return 'Region needs faces: Edit Mode → select boundary → F / 區域必須填面'
    zs=[v.co.z for v in mesh.vertices]
    if max(zs)-min(zs)>.001: return 'Use a flat local XY region / 請使用局部 XY 平面區域'
    if abs(obj.scale.x-1)>.001 or abs(obj.scale.y-1)>.001 or abs(obj.scale.z-1)>.001:
        return 'Apply object scale first: Ctrl+A → Scale / 請先套用縮放'
    if len(mesh.vertices)>100000: return 'Simplify the boundary to fewer than 100,000 vertices'
    xs=[v.co.x for v in mesh.vertices];ys=[v.co.y for v in mesh.vertices]
    if max(xs)-min(xs)>1000 or max(ys)-min(ys)>1000:
        return 'Prototype limit: region extent 1,000 m / 第一版區域邊長上限 1,000 公尺'
    from collections import Counter
    usage=Counter(edge for face in mesh.polygons for edge in face.edge_keys)
    if max(usage.values())>2 or not any(n==1 for n in usage.values()):
        return 'Region needs a valid open boundary / 請使用具有有效外邊界的平面網格'
    # Road centerlines (docs/PLAN.md §4.1): loose edges belonging to no face. They
    # must not touch the region boundary, or boundary detection (Face Count == 1)
    # gets confused where a road edge and a boundary edge share a vertex.
    boundary_verts={v for edge,n in usage.items() if n==1 for v in edge}
    road_edges=[e for e in mesh.edges if e.key not in usage]
    if any(v in boundary_verts for e in road_edges for v in e.key):
        return 'Road centerline edges must not touch the region boundary / 道路邊不得與區域邊界共用頂點'
    total_road_length=sum((mesh.vertices[a].co-mesh.vertices[b].co).length for a,b in (e.key for e in road_edges))
    if total_road_length>5000:
        return 'Prototype limit: total road centerline length 5,000 m / 道路中心線總長上限 5,000 公尺'
    return None


def validate_road_curve(region_obj,curve_obj):
    """Optional external 'Road Curves' object (docs/PLAN.md §4.1 decision 1)."""
    if curve_obj is None: return None
    if curve_obj is region_obj: return 'Road curve object cannot be the region itself / 道路曲線不能是區域自己'
    if curve_obj.type!='CURVE': return 'Road curve object must be a Curve / 道路曲線物件必須是 Curve 類型'
    return None


def make_region(name='TCity • 台灣住商街區',width=118,depth=94):
    x,y=width/2,depth/2
    mesh=bpy.data.meshes.new(name+' Boundary')
    # A cut corner makes the live input boundary immediately apparent.
    mesh.from_pydata([(-x,-y,0),(x,-y,0),(x,y-16,0),(x-18,y,0),(-x,y,0)],[],[(0,1,2,3,4)])
    mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    add_modifier(obj)
    return obj


class TCITY_OT_generate(bpy.types.Operator):
    bl_idname='tcity.generate';bl_label='Generate on Selected Region';bl_options={'REGISTER','UNDO'}
    bl_description='選取已填面的 XY 平面網格，加入可即時編輯的台灣街區 Geometry Nodes'

    @classmethod
    def poll(cls,context): return context.mode=='OBJECT' and context.active_object is not None

    def execute(self,context):
        obj=context.active_object
        problem=validate_region(obj)
        if problem:self.report({'ERROR'},problem);return {'CANCELLED'}
        if district_modifier(obj):self.report({'INFO'},'This region already has TCity');return {'CANCELLED'}
        if obj.modifiers:
            self.report({'ERROR'},'Use a region without existing modifiers / 請先使用沒有修改器的區域網格')
            return {'CANCELLED'}
        add_modifier(obj)
        return {'FINISHED'}


class TCITY_OT_demo(bpy.types.Operator):
    bl_idname='tcity.add_demo';bl_label='Add Taiwan District';bl_options={'REGISTER','UNDO'}
    bl_description='新增 118 × 94 公尺的台灣住商混合街區範例'

    def execute(self,context):
        if context.mode!='OBJECT':self.report({'ERROR'},'Switch to Object Mode first');return {'CANCELLED'}
        obj=make_region();obj.location=context.scene.cursor.location
        context.scene.unit_settings.system='METRIC'
        return {'FINISHED'}


class TCITY_OT_seed(bpy.types.Operator):
    bl_idname='tcity.next_seed';bl_label='New Variation';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        mod=district_modifier(context.active_object)
        if not mod:return {'CANCELLED'}
        set_control(mod,'Seed',(get_control(mod,'Seed')+1)%100001)
        return {'FINISHED'}


class TCITY_OT_upgrade(bpy.types.Operator):
    bl_idname='tcity.upgrade';bl_label='Upgrade District to 0.7';bl_options={'REGISTER','UNDO'}
    bl_description='保留區域和既有控制值，升級為單一道路管線（原節點樹仍保留）'
    def execute(self,context):
        mod=district_modifier(context.active_object)
        if not mod:return {'CANCELLED'}
        upgrade_modifier(mod)
        return {'FINISHED'}


PRESETS={
    'RESIDENTIAL':{'Buildings':True,'Ground':True,'Road Surface':True,'Sidewalks':True,
                   'Road Width':6.,'Sidewalk Width':1.25,'Road Details':True,'Road Markings':True,
                   'Utility Poles':True,'Overhead Wires':True,'Telecom Cabinets':True},
    'URBAN':{'Buildings':True,'Ground':True,'Road Surface':True,'Sidewalks':True,
             'Road Width':10.,'Sidewalk Width':2.,'Road Details':True,'Road Markings':True,
             'Utility Poles':False,'Overhead Wires':False,'Telecom Cabinets':True},
    'ROAD_VIEW':{'Buildings':False,'Ground':True,'Road Surface':True,'Sidewalks':True,
                 'Road Details':True,'Road Markings':True,'Utility Poles':True,'Overhead Wires':True,'Telecom Cabinets':True},
}


class TCITY_OT_preset(bpy.types.Operator):
    bl_idname='tcity.street_preset';bl_label='Street Preset';bl_options={'REGISTER','UNDO'}
    bl_description='套用道路與設施預設，保留邊界、種子、樓層與頂加設定'
    preset:bpy.props.EnumProperty(items=[('RESIDENTIAL','住宅街巷',''),('URBAN','地下化街道',''),('ROAD_VIEW','道路檢視','')])

    def execute(self,context):
        mod=district_modifier(context.active_object)
        if not mod or mod.node_group.name!=GROUP_NAME:return {'CANCELLED'}
        for name,value in PRESETS[self.preset].items():set_control(mod,name,value)
        return {'FINISHED'}


class TCITY_OT_bake(bpy.types.Operator):
    bl_idname='tcity.bake_copy';bl_label='Bake Mesh Copy';bl_options={'REGISTER','UNDO'}
    bl_description='保留程序化來源，新增可供匯出的實體網格複本（大型區域會使用較多記憶體）'
    def execute(self,context):
        obj=context.active_object
        if not (district_modifier(obj) or farmland_modifier(obj) or modern_modifier(obj)):return {'CANCELLED'}
        # A temporary Realize Instances modifier leaves the original node tree intact.
        copy=obj.copy();copy.data=obj.data.copy();copy.name=obj.name+' • Baked'
        context.collection.objects.link(copy)
        tree=bpy.data.node_groups.new('_TC_Bake','GeometryNodeTree')
        tree.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
        tree.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        a=tree.nodes.new('NodeGroupInput');r=tree.nodes.new('GeometryNodeRealizeInstances');b=tree.nodes.new('NodeGroupOutput')
        tree.links.new(a.outputs[0],r.inputs[0]);tree.links.new(r.outputs[0],b.inputs[0])
        m=copy.modifiers.new('Realize for export','NODES');m.node_group=tree
        context.view_layer.update()
        old=copy.data
        dg=context.evaluated_depsgraph_get()
        copy.data=bpy.data.meshes.new_from_object(copy.evaluated_get(dg),preserve_all_data_layers=True,depsgraph=dg)
        copy.modifiers.clear();bpy.data.node_groups.remove(tree)
        if old.users==0:bpy.data.meshes.remove(old)
        copy['tc_region']=False;copy['tc_farmland']=False;copy['tc_modern']=False
        # Hide the copy initially to avoid overlapping the live source.
        copy.hide_set(True);copy.hide_render=True
        self.report({'INFO'},'Baked copy created (hidden) in Outliner / 已建立隱藏的網格複本')
        return {'FINISHED'}


LABELS={'Seed':'隨機種子 · Seed','Density':'建築密度','Open Spaces':'空置基地再利用','Parking Mix':'停車場比例',
        'Frontage':'面寬 (m)','Depth':'進深 (m)',
        'Lots per Block':'每排戶數','Road Width':'道路寬度 (m)','Alley Width':'後巷寬度 (m)',
        'Min Floors':'最低樓層','Max Floors':'最高樓層','Townhouse Mix':'第二組住宅立面比例',
        'Boundary Setback':'邊界退縮 (m)','Signs':'店家招牌','Rooftops':'頂樓增建與附加設備',
        'Street Life':'街邊物件與盆栽','Buildings':'建築','Ground':'地面與道路標線',
        'Metal Shed Mix':'獨棟鐵皮屋比例','Rooftop Addition Mix':'住宅頂樓加蓋比例',
        'Road Surface':'實體道路面','Sidewalks':'人行道與路緣','Sidewalk Width':'人行道寬度 (m)',
        'Curb Height':'路緣高度 (m)','Road Thickness':'路面厚度 (m)','Road Markings':'道路標線',
        'Road Details':'排水溝蓋與人孔蓋','Utility Poles':'電線桿','Pole Spacing':'電桿最大跨距 (m)',
        'Pole Height':'電桿高度 (m)','Overhead Wires':'架空線','Cable Sag':'電線垂度 (m)',
        'Telecom Cabinets':'電信交接箱','Cabinet Density':'電信箱出現比例',
        'Road Curves':'外部道路曲線物件（選配）','Smooth Streets':'平滑道路轉角',
        'Road Resolution':'道路取樣間距 (m)','Bend Buildings to Curve':'街屋沿曲線彎折'}


class TCITY_PT_panel(bpy.types.Panel):
    bl_label='TCity / 台灣街區';bl_idname='TCITY_PT_panel'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='TCity'
    def draw(self,context):
        layout=self.layout
        layout.label(text='TAIWAN STREETS / 0.7',icon='MOD_NODES')
        layout.operator('tcity.add_demo',text='新增範例街區',icon='ADD')
        layout.operator('tcity.generate',text='從選取區域生成',icon='MESH_GRID')
        mod=district_modifier(context.active_object)
        if not mod:
            layout.separator();layout.label(text='選取 XY 平面網格 · 先填面並套用縮放')
            return
        if mod.node_group.name!=GROUP_NAME:
            layout.operator('tcity.upgrade',text='升級街區 · 單一道路管線',icon='FILE_REFRESH')
            layout.label(text='升級後保留原本的區域與參數')
            return
        row=layout.row(align=True)
        for key,label in [('RESIDENTIAL','住宅街巷'),('URBAN','地下化'),('ROAD_VIEW','道路檢視')]:
            row.operator('tcity.street_preset',text=label).preset=key
        layout.separator();layout.operator('tcity.next_seed',text='換一個街區變化',icon='FILE_REFRESH')
        box=None
        headers={'Seed':'生成設定','Open Spaces':'空置基地','Frontage':'街廓尺寸','Road Curves':'道路曲線（選配）','Min Floors':'建築組成','Signs':'建築細節','Road Surface':'道路與人行道','Utility Poles':'沿街設施'}
        display=[s[0] for s in SOCKETS]
        display.remove('Metal Shed Mix');display.insert(display.index('Townhouse Mix')+1,'Metal Shed Mix')
        display.remove('Rooftop Addition Mix');display.insert(display.index('Metal Shed Mix')+1,'Rooftop Addition Mix')
        for name in display:
            if name in headers:
                box=layout.box();box.label(text=headers[name])
                if name=='Road Curves':
                    box.label(text='Tab 編輯區域網格內畫游離邊當道路中心線')
                    box.label(text='未指定時自動使用正交道路網')
            draw_control(box,mod,name,LABELS[name])
        if curvature_warning(context,context.active_object):
            warning=layout.box();warning.alert=True
            warning.label(text='彎道過急：已略過無法安全容納的基地',icon='ERROR')
            warning.label(text='可放緩道路曲線，或開啟街屋沿曲線彎折')
        layout.separator();layout.operator('tcity.bake_copy',text='建立實體網格複本',icon='DUPLICATE')
        layout.label(text='Tab 編輯邊界 · Geometry Nodes 可直接修改')


CLASSES=(TCITY_OT_generate,TCITY_OT_demo,TCITY_OT_seed,TCITY_OT_upgrade,TCITY_OT_preset,TCITY_OT_bake,TCITY_PT_panel)+FARM_CLASSES+MODERN_CLASSES

def register():
    for cls in CLASSES:bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)

if __name__=='__main__':register()
