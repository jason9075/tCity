"""Build and optionally render the self-contained Geometry Nodes farm demo.

blender -b --factory-startup --python-exit-code 1 --python scripts/build_farmland_demo.py -- --render
Add --quick for economical review images in build/farmland/.
"""
import math
import sys
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import tcity
from tcity.farmland import make_farmland, farmland_modifier
from tcity.nodes import set_control
from build_demo import environment, aim


def build():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    tcity.register();obj=make_farmland();mod=farmland_modifier(obj)
    set_control(mod,'Seed',31);set_control(mod,'Rice Mix',.62);set_control(mod,'Structure Mix',.22);set_control(mod,'Plot Width',27.);set_control(mod,'Woodland Mix',.16)
    scene=bpy.context.scene;scene.unit_settings.system='METRIC'
    stage=bpy.data.collections.new('Farm presentation');scene.collection.children.link(stage)
    def camera(name,location,target,lens):
        data=bpy.data.cameras.new(name);cam=bpy.data.objects.new(name,data);stage.objects.link(cam)
        cam.location=location;aim(cam,Vector(target));data.lens=lens;data.clip_end=5000;return cam
    aerial=camera('01 • Farmland aerial / 農地空拍',(174,-249,285),(0,2,0),43)
    top=camera('02 • Parcel plan / 田區配置',(0,-.01,400),(0,0,0),50);top.data.type='ORTHO';top.data.ortho_scale=270
    close=camera('03 • Field and canal / 田埂近景',(-40,-105,26),(-40,-42,.5),48)
    bpy.context.view_layer.update()
    homes=[(i.object.original.get('tc_farm_asset'),i.matrix_world.copy()) for i in bpy.context.evaluated_depsgraph_get().object_instances
           if i.is_instance and i.parent and i.parent.original==obj and i.object.original.get('tc_farm_asset') in (6,8,9)]
    home=next((m for k,m in homes if k==8),homes[0][1] if homes else None)
    rural=camera('04 • Rural home / 農舍與鄉間環境',home@Vector((17,-23,12)) if home else (40,-70,20),home@Vector((0,0,2)) if home else (0,0,1),43)
    scene.camera=aerial;environment(scene)
    sun_data=bpy.data.lights.new('Late morning sun','SUN');sun_data.energy=2.;sun_data.angle=.075
    sun=bpy.data.objects.new('Late morning sun',sun_data);stage.objects.link(sun);sun.rotation_euler=(.50,-.4,-.55)
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.cycles.max_bounces=5
    scene.render.resolution_x=1400;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.view_settings.exposure=.05
    scene.world.color=(.2,.2,.2)
    # A neutral ground supports the cut boundary without pretending to be more
    # procedurally generated countryside beyond the actual region.
    from tcity.assets import MeshBuilder,material
    b=MeshBuilder();b.box((0,0,-.43),(2000,2000,.2),material('Farm / Presentation ground',(.16,.17,.145),roughness=.95))
    ground=b.object('Presentation ground (not generated farmland)',stage)
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True);bpy.context.view_layer.objects.active=obj
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                view=area.spaces.active;view.region_3d.view_distance=310;view.region_3d.view_location=(0,0,0)
                view.region_3d.view_rotation=aerial.rotation_euler.to_quaternion();view.clip_end=5000
                view.shading.type='MATERIAL';view.overlay.show_overlays=False;view.show_region_ui=True
            elif area.type=='PROPERTIES':area.spaces.active.context='MODIFIER'
    intro=bpy.data.texts.new('START HERE • 台灣農地')
    intro.write('TCity 0.6.2 · Taiwan Farmland v0.2\n\n選取「TCity • 台灣農地」→ 修改器調整 Geometry Nodes。\n安裝 tcity-0.6.2.zip 後，N 側欄 > TCity > 台灣農地，有水稻田、混合耕作、農工交錯三種預設。\nTab 可修改已填面 XY 邊界和孔洞。旋轉 Field Angle 可改變整組田區方向。\nSeed 同時改變共享田界與作物分配；Plot Width / Length 調整田塊尺寸。\nRice Mix 是扣除設施、果園、休耕、蓄水田後的水稻／蔬菜比例。用途機率依序分配，並非加總為 100% 的面積百分比。\nRipening 改變綠稻／金黃稻田比例。Crops 顯示實際稻叢、蔬菜及果樹模型。\nFarm Roads / Irrigation 即時切換農路、具有槽底與水面的明渠。\nStructures 關閉只隱藏農舍、農用棚與栽培隧道；Structure Mix = 0 則還原其農地用途。\nPlant Spacing 提高可減少稻菜實例；大區域自動降低密度，果樹固定 4.2 m 間距。\n\n鄉間環境：Woodland Mix 配置自然樹林用地；Trees 顯示雜木與竹叢。Utility Poles / Overhead Wires 顯示農路電桿與有支撐的架空線。Pole Spacing 控制最大跨距，Cable Sag 控制垂度。\n\n本場景不需 Python handler 即可調參、存檔與重開；材質與照明 HDR 已封裝。\n四個相機：空拍、正上方配置、田埂近景、農舍環境。原始區域保留，實例可透過 Realize Instances 或「建立實體網格複本」匯出。\n\n範圍：平地的合成田區，未描摹真實地籍；農路自動沿田界生成，尚未支援手繪農路、坡地／梯田、高程或真實作物品種模擬。以中遠景為主，近景尚非照片級掃描資產。\n')
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    from collections import Counter
    print('FARM_ASSETS',dict(Counter(i.object.original.name for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj)),flush=True)
    print('FARM_WARNINGS',list(mod.node_warnings),flush=True)
    dest=ROOT/'dist/TCity_Taiwan_Farmland.blend';dest.parent.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(dest),compress=True)
    if '--render' in sys.argv:
        quick='--quick' in sys.argv
        if quick:scene.render.resolution_percentage=60;scene.cycles.samples=12
        folder=ROOT/('build/farmland' if quick else 'renders');folder.mkdir(parents=True,exist_ok=True)
        for cam,name in [(aerial,'farmland_aerial'),(top,'farmland_plan'),(close,'farmland_detail'),(rural,'farmland_rural')]:
            scene.camera=cam;scene.render.filepath=str(folder/(name+'.png'))
            print('FARM_RENDER',name,flush=True);bpy.ops.render.render(write_still=True)
    return obj

if __name__=='__main__':build()
