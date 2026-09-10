"""Render the saved farm demo, without rebuilding or requiring the addon."""
import sys
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'dist/TCity_Taiwan_Farmland.blend'))
scene=bpy.context.scene
quick='--quick' in sys.argv
scene.render.resolution_percentage=60 if quick else 100
scene.cycles.samples=12 if quick else 24
views=[('01 • Farmland aerial / 農地空拍','farmland_aerial'),('04 • Rural home / 農舍與鄉間環境','farmland_rural')]
if '--all' in sys.argv:views += [('02 • Parcel plan / 田區配置','farmland_plan'),('03 • Field and canal / 田埂近景','farmland_detail')]
folder=ROOT/('build/farmland' if quick else 'renders');folder.mkdir(parents=True,exist_ok=True)
for camera,name in views:
    scene.camera=bpy.data.objects[camera];scene.render.filepath=str(folder/(name+'.png'))
    print('FARM_RENDER',name,flush=True);bpy.ops.render.render(write_still=True)
