"""Render saved camera views. --quick gives inexpensive 800 px review frames."""
import bpy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
scene=bpy.context.scene
quick='--quick' in sys.argv
scene.cycles.samples=12 if quick else 64
scene.render.resolution_percentage=55 if quick else 100
for prefix,name in [('01','taipei_street'),('02','taipei_rooftops')]:
    if '--roof-only' in sys.argv and prefix=='01':continue
    scene.cycles.samples=12 if quick else (64 if prefix=='01' else 32)
    scene.camera=next(o for o in bpy.data.objects if o.type=='CAMERA' and o.name.startswith(prefix))
    scene.render.filepath=str(ROOT/('build/v03' if quick else 'renders')/(name+'.png'))
    print('RENDER_VIEW',name,flush=True)
    bpy.ops.render.render(write_still=True)
