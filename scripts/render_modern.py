"""Render the saved modern demo without importing the addon."""
import sys
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'dist/TCity_Modern_Communities.blend'))
scene=bpy.context.scene;quick='--quick' in sys.argv
scene.render.resolution_percentage=60 if quick else 100;scene.cycles.samples=12 if quick else 24
folder=ROOT/('build/modern' if quick else 'renders');folder.mkdir(parents=True,exist_ok=True)
for camera,name in [('01 • Modern communities / 社區全景','modern_overview'),('02 • Community entrance / 社區入口','modern_entrance'),('03 • Facade and balconies / 陽台立面','modern_balconies')]:
    requested=[arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--view=')]
    if requested and name.removeprefix('modern_') not in requested:continue
    scene.camera=bpy.data.objects[camera];scene.render.filepath=str(folder/(name+'.png'))
    print('MODERN_RENDER',name,flush=True);bpy.ops.render.render(write_still=True)
