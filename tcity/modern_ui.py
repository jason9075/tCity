"""Sidebar for modern residential communities, alongside city and farm tools."""
import bpy
from .modern import make_modern_region,add_modern_modifier,modern_modifier,SOCKETS,PRESETS
from .nodes import draw_control,get_control,set_control


class TCITY_OT_modern_demo(bpy.types.Operator):
    bl_idname='tcity.add_modern';bl_label='Add Modern Taiwan Communities';bl_options={'REGISTER','UNDO'}
    bl_description='新增較新住宅大樓社區，包含完整基地、中庭與道路'
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT'
    def execute(self,context):
        obj=make_modern_region();obj.location=context.scene.cursor.location;context.scene.unit_settings.system='METRIC'
        return {'FINISHED'}


class TCITY_OT_modern_generate(bpy.types.Operator):
    bl_idname='tcity.generate_modern';bl_label='Generate Modern Communities on Region';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and context.active_object is not None
    def execute(self,context):
        from . import validate_region
        obj=context.active_object;problem=validate_region(obj)
        if problem:self.report({'ERROR'},problem);return {'CANCELLED'}
        if obj.modifiers:self.report({'ERROR'},'請使用沒有修改器的區域');return {'CANCELLED'}
        used={edge for face in obj.data.polygons for edge in face.edge_keys}
        if any(e.key not in used for e in obj.data.edges):
            self.report({'ERROR'},'新式社區目前自動配置道路，請使用純面區域');return {'CANCELLED'}
        add_modern_modifier(obj);return {'FINISHED'}


class TCITY_OT_modern_seed(bpy.types.Operator):
    bl_idname='tcity.modern_seed';bl_label='New Community Variation';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        mod=modern_modifier(context.active_object)
        if not mod:return {'CANCELLED'}
        set_control(mod,'Seed',(get_control(mod,'Seed')+1)%100001);return {'FINISHED'}


class TCITY_OT_modern_preset(bpy.types.Operator):
    bl_idname='tcity.modern_preset';bl_label='Modern Community Preset';bl_options={'REGISTER','UNDO'}
    preset:bpy.props.EnumProperty(items=[('URBAN','單棟大樓',''),('TWIN','雙棟社區',''),('GREEN','大陽台住宅','')])
    def execute(self,context):
        mod=modern_modifier(context.active_object)
        if not mod:return {'CANCELLED'}
        for name,value in PRESETS[self.preset].items():set_control(mod,name,value)
        return {'FINISHED'}


LABELS={'Seed':'隨機種子','Density':'社區基地密度','Community Width':'社區模組寬 (m)','Community Depth':'社區模組深 (m)',
        'Min Floors':'主要塔樓最低層數','Max Floors':'主要塔樓最高層數','Twin Community Mix':'雙棟社區比例','Green Balcony Mix':'大陽台住宅比例',
        'Buildings':'大樓、基座與庭院','Landscape':'庭園樹木','Road Width':'道路寬 (m)','Sidewalk Width':'人行道寬 (m)',
        'Ground':'道路與人行道','Road Markings':'道路標線','Road Details':'排水與人孔蓋','Telecom Cabinets':'電信設備'}


class TCITY_PT_modern(bpy.types.Panel):
    bl_label='TCity / 新式住宅社區';bl_idname='TCITY_PT_modern'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='TCity'
    def draw(self,context):
        layout=self.layout;layout.label(text='MODERN TAIWAN COMMUNITIES',icon='GEOMETRY_NODES')
        layout.operator('tcity.add_modern',text='新增住宅社區範例',icon='ADD')
        layout.operator('tcity.generate_modern',text='從選取區域生成新式社區',icon='MESH_GRID')
        mod=modern_modifier(context.active_object)
        if not mod:return
        row=layout.row(align=True)
        for key,label in [('URBAN','單棟'),('TWIN','雙棟'),('GREEN','大陽台')]:row.operator('tcity.modern_preset',text=label).preset=key
        layout.operator('tcity.modern_seed',text='換一組社區配置',icon='FILE_REFRESH')
        headers={'Seed':'配置','Community Width':'完整社區基地','Min Floors':'建築類型與高度','Buildings':'模型','Road Width':'街道'};box=layout
        for name,*_ in SOCKETS:
            if name in headers:box=layout.box();box.label(text=headers[name])
            draw_control(box,mod,name,LABELS[name])
        layout.label(text='基地必須完整放得下；小區域可能沒有大樓')
        layout.label(text='1F 4.5 m，上層 3.1 m；雙棟可有高低差')
        layout.operator('tcity.bake_copy',text='建立實體網格複本',icon='DUPLICATE')


CLASSES=(TCITY_OT_modern_demo,TCITY_OT_modern_generate,TCITY_OT_modern_seed,TCITY_OT_modern_preset,TCITY_PT_modern)
