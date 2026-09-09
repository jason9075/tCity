"""Inspect v0.4 streets. Run in the saved demo; --quick for fast review."""
from pathlib import Path
import bpy,sys
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];s=bpy.context.scene
quick='--quick' in sys.argv
s.render.resolution_x=1400;s.render.resolution_y=1000;s.render.resolution_percentage=55 if quick else 100
s.cycles.samples=10 if quick else 24
views=[('streets_overview',(98,-115,85),(0,-1,3),43),
       ('streets_closeup',(-17,-61,3.6),(-37,-27,6.5),33)]
if '--close-only' in sys.argv:views=views[1:]
if '--overview-only' in sys.argv:views=views[:1]
if '--utilities-only' in sys.argv or '--all' in sys.argv:
    cam=next(o for o in bpy.data.objects if o.type=='CAMERA' and o.name.startswith('04'))
    detail=[('utilities_detail',cam.location.copy(),cam.location+cam.rotation_euler.to_quaternion()@Vector((0,0,-5)),cam.data.lens)]
    views=views+detail if '--all' in sys.argv else detail
for name,pos,target,lens in views:
    s.cycles.samples=10 if quick else (16 if name=='streets_overview' else 24)
    camera=s.camera;camera.location=pos;camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=lens
    s.render.filepath=str(ROOT/('build/v04' if quick else 'renders')/(name+'.png'))
    print('RENDER',name,flush=True);bpy.ops.render.render(write_still=True)
