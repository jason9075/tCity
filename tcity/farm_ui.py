"""Farmland operators and a separate sidebar; existing city controls stay intact."""
import bpy
from .farmland import make_farmland, add_farmland_modifier, farmland_modifier, SOCKETS, PRESETS, GROUP_NAME, ensure_group
from .nodes import get_control, set_control, draw_control


class TCITY_OT_farm_demo(bpy.types.Operator):
    bl_idname='tcity.add_farmland';bl_label='Add Taiwan Farmland';bl_options={'REGISTER','UNDO'}
    bl_description='新增可即時調整的台灣農地，240 × 180 公尺'
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT'
    def execute(self,context):
        obj=make_farmland();obj.location=context.scene.cursor.location;context.scene.unit_settings.system='METRIC'
        return {'FINISHED'}


class TCITY_OT_farm_generate(bpy.types.Operator):
    bl_idname='tcity.generate_farmland';bl_label='Generate Farmland on Region';bl_options={'REGISTER','UNDO'}
    bl_description='以選取且已填面的 XY 區域生成農地；Tab 編輯外框與孔洞會即時更新'
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and context.active_object is not None
    def execute(self,context):
        from . import validate_region
        obj=context.active_object;problem=validate_region(obj)
        if problem:self.report({'ERROR'},problem);return {'CANCELLED'}
        if obj.modifiers:
            self.report({'ERROR'},'請使用沒有修改器的已填面區域 / Use a region without modifiers');return {'CANCELLED'}
        # Farmland currently derives its own lanes. Avoid silently treating the
        # city's loose-road input convention as supported here.
        used={edge for face in obj.data.polygons for edge in face.edge_keys}
        if any(e.key not in used for e in obj.data.edges):
            self.report({'ERROR'},'農地目前自動配置農路；請移除游離道路邊');return {'CANCELLED'}
        add_farmland_modifier(obj);return {'FINISHED'}


class TCITY_OT_farm_seed(bpy.types.Operator):
    bl_idname='tcity.farmland_seed';bl_label='New Farmland Variation';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        mod=farmland_modifier(context.active_object)
        if not mod:return {'CANCELLED'}
        set_control(mod,'Seed',(get_control(mod,'Seed')+1)%100001);return {'FINISHED'}


class TCITY_OT_farm_preset(bpy.types.Operator):
    bl_idname='tcity.farmland_preset';bl_label='Farmland Preset';bl_options={'REGISTER','UNDO'}
    preset:bpy.props.EnumProperty(items=[('PADDY','水稻田',''),('MIXED','混合耕作',''),('FRINGE','農工交錯','')])
    def execute(self,context):
        mod=farmland_modifier(context.active_object)
        if not mod:return {'CANCELLED'}
        for name,value in PRESETS[self.preset].items():set_control(mod,name,value)
        return {'FINISHED'}


LABELS={'Woodland Mix':'自然樹林用地機率','Trees':'雜木與竹叢','Utility Poles':'鄉間電線桿','Pole Spacing':'電桿最大跨距 (m)','Overhead Wires':'架空線','Cable Sag':'電線垂度 (m)','Seed':'隨機種子','Plot Width':'田寬 (m)','Plot Length':'田長 (m)','Irregularity':'田形變化',
        'Field Angle':'田區方向 (°)','Bund Width':'田埂寬 (m)','Rice Mix':'水稻／蔬菜比','Ripening':'稻田成熟比例',
        'Orchard Mix':'果園機率','Fallow Mix':'休耕機率','Flooded Mix':'蓄水田機率','Structure Mix':'農業設施用地機率',
        'Farm Roads':'農路','Road Width':'農路寬 (m)','Irrigation':'灌溉明渠','Crops':'作物與果樹',
        'Plant Spacing':'稻菜間距 (m)','Structures':'農舍與農用棚'}


class TCITY_OT_farm_upgrade(bpy.types.Operator):
    bl_idname='tcity.upgrade_farmland';bl_label='Upgrade Farmland';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        mod=farmland_modifier(context.active_object)
        if not mod:return {'CANCELLED'}
        names={s.name for s in mod.node_group.interface.items_tree if s.item_type=='SOCKET' and s.in_out=='INPUT'}
        values={name:get_control(mod,name) for name,*_ in SOCKETS if name in names}
        mod.node_group=ensure_group()
        for name,_,default,*_ in SOCKETS:set_control(mod,name,values.get(name,default))
        return {'FINISHED'}


class TCITY_PT_farmland(bpy.types.Panel):
    bl_label='TCity / 台灣農地';bl_idname='TCITY_PT_farmland'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='TCity'
    def draw(self,context):
        layout=self.layout;layout.label(text='TAIWAN FARMLAND',icon='MOD_NODES')
        layout.operator('tcity.add_farmland',text='新增農地範例',icon='ADD')
        layout.operator('tcity.generate_farmland',text='從選取區域生成農地',icon='MESH_GRID')
        mod=farmland_modifier(context.active_object)
        if not mod:return
        if mod.node_group.name!=GROUP_NAME:
            layout.operator('tcity.upgrade_farmland',text='升級農地 · 農舍、樹林與電桿')
            return
        row=layout.row(align=True)
        for key,label in [('PADDY','水稻田'),('MIXED','混合耕作'),('FRINGE','農工交錯')]:row.operator('tcity.farmland_preset',text=label).preset=key
        layout.operator('tcity.farmland_seed',text='換一組農地',icon='FILE_REFRESH')
        headers={'Seed':'分割與田形','Rice Mix':'土地用途與生長階段','Woodland Mix':'鄉間環境','Farm Roads':'農路與灌溉','Crops':'模型與效能'};box=layout
        for name,*_ in SOCKETS:
            if name in headers:box=layout.box();box.label(text=headers[name])
            draw_control(box,mod,name,LABELS[name])
        layout.label(text='大區域自動降低稻菜密度；果樹間距 4.2 m')
        layout.label(text='Tab 編輯平面邊界；農路由田區自動配置')
        layout.operator('tcity.bake_copy',text='建立實體網格複本',icon='DUPLICATE')


CLASSES=(TCITY_OT_farm_demo,TCITY_OT_farm_generate,TCITY_OT_farm_seed,TCITY_OT_farm_preset,TCITY_OT_farm_upgrade,TCITY_PT_farmland)
