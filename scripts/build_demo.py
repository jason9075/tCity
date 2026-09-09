"""Build the portable Taipei residential demo; --render also produces camera images."""
import sys
import math
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import tcity


def aim(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


def environment(scene):
    world=bpy.data.worlds.new('Taipei • overcast daylight');scene.world=world;world.use_nodes=True
    n=world.node_tree.nodes;n.clear();link=world.node_tree.links.new
    out=n.new('ShaderNodeOutputWorld');mix=n.new('ShaderNodeMixShader');ray=n.new('ShaderNodeLightPath')
    sky=n.new('ShaderNodeBackground');sky.inputs[0].default_value=(.63,.69,.73,1);sky.inputs[1].default_value=.65
    lighting=n.new('ShaderNodeBackground');lighting.inputs[1].default_value=.7
    hdr=n.new('ShaderNodeTexEnvironment');hdr.image=bpy.data.images.load(str(ROOT/'tcity/environment/urban_street_03_2k.hdr'));hdr.image.pack()
    coord=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=math.radians(105)
    link(coord.outputs['Generated'],mapping.inputs['Vector']);link(mapping.outputs[0],hdr.inputs[0])
    link(hdr.outputs[0],lighting.inputs[0]);link(ray.outputs['Is Camera Ray'],mix.inputs[0]);link(lighting.outputs[0],mix.inputs[1]);link(sky.outputs[0],mix.inputs[2]);link(mix.outputs[0],out.inputs[0])
    for i,node in enumerate(n):node.location=(i%4*230,-i//4*180)


def build():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    tcity.register();obj=tcity.make_region();scene=bpy.context.scene
    obj.name='TCity • 台北住商混合街區'
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    stage=bpy.data.collections.new('Presentation');scene.collection.children.link(stage)
    from tcity.assets import MeshBuilder,material
    from tcity.surfaces import surface
    b=MeshBuilder();b.box((0,0,-.32),(2000,2000,.2),surface('Exterior ground',(.15,.16,.16)))
    b.object('Surrounding ground',stage)
    def camera(name,pos,target,lens):
        data=bpy.data.cameras.new(name);cam=bpy.data.objects.new(name,data);stage.objects.link(cam)
        cam.location=pos;aim(cam,target);data.lens=lens;data.clip_end=3000;return cam
    street=camera('01 • Street / 街道',(-17,-61,3.6),(-37,-27,6.5),33)
    roof=camera('02 • Roof homes / 頂加',(-19,-61,29),(-39,-28,15.6),43)
    overview=camera('03 • District / 全區',(98,-115,85),(0,-1,3),43)
    bpy.context.view_layer.update()
    cabinets=[i.matrix_world.translation.copy() for i in bpy.context.evaluated_depsgraph_get().object_instances
              if i.is_instance and i.parent and i.parent.original==obj and i.object.original.get('tc_infra_kind')=='Telecom']
    anchor=min(cabinets,key=lambda v:(v.y,v.x))
    utility=camera('04 • Utilities / 沿街細節',anchor+Vector((3,-5,2.4)),anchor+Vector((-.65,0,1.0)),47)
    scene.camera=street;environment(scene)
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.cycles.max_bounces=6
    scene.render.resolution_x=1400;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.view_settings.exposure=1.0
    scene.render.film_transparent=False
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    for screen in bpy.data.screens:
        for a in screen.areas:
            if a.type=='VIEW_3D':
                a.spaces.active.region_3d.view_distance=150;a.spaces.active.region_3d.view_location=(0,0,8)
                a.spaces.active.region_3d.view_rotation=overview.rotation_euler.to_quaternion();a.spaces.active.clip_end=5000
                a.spaces.active.shading.type='MATERIAL';a.spaces.active.overlay.show_overlays=False
            elif a.type=='PROPERTIES':a.spaces.active.context='MODIFIER'
    intro=bpy.data.texts.new('START HERE • 使用說明')
    intro.write('TCity 0.6 / 台北街區、道路路口與沿街設施\n\nRooftop Addition Mix：住宅頂樓加蓋比例。設為 0 仍保留樓梯間、水塔。\nMetal Shed Mix：地面獨棟鐵皮屋比例，與住宅頂加分開控制。\nRooftops：同時開關頂加與屋頂設備。\n\n選取街區物件，在修改器調整參數；Tab 編輯已填面的平面邊界。\n安裝 tcity-0.6.0.zip 後：N 側欄 > TCity，可新增或升級街區。\n舊版升級保留既有參數與區域；可自行調成 4～5 層、窄巷、低透天比例。\n\n四個相機：Street 街道 / Roof homes 頂加 / District 全區 / Utilities 沿街細節。\nHDRI 已封裝；僅供照明反射，背景為純色天空。\n原創程序化素材與 Geometry Nodes，並非 iCity 官方產品。\n目前使用正交街廓與有限套件變化；仍需貼圖與更多資產才能達到近景照片級品質。\nRoad Surface / Sidewalks：實體瀝青道路、人行道與路緣。\nUtility Poles / Overhead Wires / Telecom Cabinets：電桿、電線與電信箱。\nRoad Details：排水溝蓋與人孔蓋。可調電桿最大跨距、高度、電線垂度。\nN > TCity 提供住宅街巷、地下化街道與道路檢視三種預設。\n基礎設施獨立於建築密度；線路只連接同一段街廓上的電桿。\n\n操作與研究資料請看 README.md、docs/research/streets-infrastructure.md。\n')
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    instances=[i for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj]
    print('TCITY_BUILD instances:',len(instances),flush=True)
    dest=ROOT/'dist/TCity_Taiwan_District.blend';dest.parent.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(dest),compress=True)
    if '--render' in sys.argv:
        for cam,name in [(street,'streets_closeup'),(overview,'streets_overview'),(utility,'utilities_detail')]:
            scene.camera=cam;scene.render.filepath=str(ROOT/'renders'/f'{name}.png')
            print('TCITY_RENDER',name,flush=True);bpy.ops.render.render(write_still=True)
    return obj

if __name__=='__main__':build()
