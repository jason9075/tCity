"""Create a self-contained modern community demo with real Cycles previews."""
import sys
import math
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import tcity
from tcity.modern import make_modern_region,modern_modifier
from tcity.nodes import set_control
from build_demo import aim,environment


def build():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);tcity.register()
    obj=make_modern_region(width=228,depth=128);mod=modern_modifier(obj)
    for name,value in {'Seed':53,'Density':1.,'Min Floors':10,'Max Floors':18,'Green Balcony Mix':.35,'Twin Community Mix':.50}.items():set_control(mod,name,value)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC';stage=bpy.data.collections.new('Modern presentation');scene.collection.children.link(stage)
    def camera(name,location,target,lens):
        data=bpy.data.cameras.new(name);cam=bpy.data.objects.new(name,data);stage.objects.link(cam)
        cam.location=location;aim(cam,Vector(target));data.lens=lens;data.clip_end=3000;return cam
    aerial=camera('01 • Modern communities / 社區全景',(210,-238,155),(0,0,21),45)
    street=camera('02 • Community entrance / 社區入口',(-100,-83,7),(-77,-24,13),33)
    balcony=camera('03 • Facade and balconies / 陽台立面',(-90,-66,28),(-76,-25,26),48)
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    bases=[(i.object.original.get('tc_modern_style'),i.matrix_world.translation.copy(),i.object.original.get('tc_modern_floors')) for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj and i.object.original.get('tc_modern_role')=='Base']
    print('MODERN_BASES',[(k,tuple(v),f) for k,v,f in bases],flush=True)
    # Pick a front-row green-balcony community for the detailed view if present.
    green=next(((v,f) for k,v,f in bases if k==2 and v.y<0),None)
    if green:
        center,f=green;balcony.location=center+Vector((-24,-36,21));aim(balcony,center+Vector((-14,-2,22)))
    scene.camera=aerial;environment(scene)
    sun_data=bpy.data.lights.new('Daylight','SUN');sun_data.energy=1.6;sun_data.angle=.07
    sun=bpy.data.objects.new('Daylight',sun_data);stage.objects.link(sun);sun.rotation_euler=(.5,-.4,-.7)
    from tcity.assets import MeshBuilder,material
    b=MeshBuilder();b.box((0,0,-.4),(2500,2500,.2),material('Modern surrounding ground',(.19,.20,.19),roughness=.9));b.object('Presentation ground',stage)
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.cycles.max_bounces=6
    scene.render.resolution_x=1400;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.3
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                view=area.spaces.active;view.region_3d.view_distance=290;view.region_3d.view_location=(0,0,20)
                view.region_3d.view_rotation=aerial.rotation_euler.to_quaternion();view.clip_end=3000;view.shading.type='MATERIAL';view.show_region_ui=True
            elif area.type=='PROPERTIES':area.spaces.active.context='MODIFIER'
    intro=bpy.data.texts.new('START HERE • 新式台灣社區')
    intro.write('TCity 0.6.4 / Modern Taiwan Communities v0.1\n\n選取社區物件 → 修改器調整 Geometry Nodes；不需啟動 Python 或安裝外掛即可更新。\n安裝 tcity-0.6.4.zip 後，N → TCity → 新式住宅社區，提供新增、由選取區域生成及三種預設。\n\nSeed：配置與樓高種子。Density：整個社區基地的使用機率。\nCommunity Width / Depth：含棟距、公共庭院的社區模組尺寸。XY 尺度會一起調整，樓高不伸縮。\nMin / Max Floors：主要塔樓 6～24 層；1F 4.5m，住宅樓層 3.1m。雙棟類型的副棟可低兩層。\nTwin Community Mix / Green Balcony Mix：雙棟和大陽台類型。\nBuildings / Landscape：建築與基座、庭園樹木。\n道路、人行道、排水和電信箱有獨立控制。\n\nTab 可改外框與孔洞。完整社區基地放不下時會整組略過；不會切掉塔樓一半。\n這是獨立的新式社區生成器，可和原街區／農地物件放在同一場景；尚未自動混合舊街屋與新大樓，也尚未沿手繪曲線配置社區。\n原創模組，依真實建商完工照及社區街景觀察建模；不是實址複製、照片掃描或工程圖。來源見 docs/research/modern-residential.md。\n')
    dest=ROOT/'dist/TCity_Modern_Communities.blend';bpy.ops.wm.save_as_mainfile(filepath=str(dest),compress=True)
    if '--render' in sys.argv:
        quick='--quick' in sys.argv
        if quick:scene.render.resolution_percentage=60;scene.cycles.samples=12
        folder=ROOT/('build/modern' if quick else 'renders');folder.mkdir(parents=True,exist_ok=True)
        for cam,name in [(aerial,'modern_overview'),(street,'modern_entrance'),(balcony,'modern_balconies')]:
            scene.camera=cam;scene.render.filepath=str(folder/(name+'.png'));print('MODERN_RENDER',name,flush=True);bpy.ops.render.render(write_still=True)
    return obj

if __name__=='__main__':build()
