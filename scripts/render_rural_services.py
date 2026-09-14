"""Open the saved settlement without addon imports; add a canal review camera."""

from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT / 'dist/TCity_Rural_Settlement.blend'))
scene = bpy.context.scene
root = next(c for c in bpy.data.collections if c.get('asset_scene') and c.get('housing_gn'))
canals = [o for o in root.all_objects if o.get('rural_role') == 'canal' and o['zone_id'] == 'field_southwest']
canal = max(canals, key=lambda o: o['length'])
coords = list(canal['footprint'])
target = Vector((sum(coords[::2]) / 4, sum(coords[1::2]) / 4, .2))
camera = bpy.data.objects.get('Rural irrigation detail')
if camera is None:
    data = bpy.data.cameras.new('Rural irrigation detail')
    camera = bpy.data.objects.new(data.name, data)
    root.objects.link(camera)
camera.location = target + Vector((15, -20, 16))
camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type = 'ORTHO'
camera.data.ortho_scale = 28
camera.data.clip_end = 5000
scene.camera = camera
scene.render.filepath = str(ROOT / 'renders/rural_scene_irrigation.png')
bpy.ops.render.render(write_still=True)
culverts = [o for o in root.all_objects if o.get('rural_role') == 'culvert']
if culverts:
    conduit = min(culverts, key=lambda o: o['length'])
    coords = list(conduit['footprint'])
    target = Vector((sum(coords[::2]) / 4, sum(coords[1::2]) / 4, .1))
    detail = bpy.data.objects.get('Rural culvert detail')
    if detail is None:
        data = bpy.data.cameras.new('Rural culvert detail')
        detail = bpy.data.objects.new(data.name, data)
        root.objects.link(detail)
    detail.location = target + Vector((10, -12, 14))
    detail.rotation_euler = (target - detail.location).to_track_quat('-Z', 'Y').to_euler()
    detail.data.type = 'ORTHO'
    detail.data.ortho_scale = max(16, conduit['length'] * 1.8)
    detail.data.clip_end = 5000
    scene.camera = detail
    scene.render.filepath = str(ROOT / 'renders/rural_scene_culvert.png')
    bpy.ops.render.render(write_still=True)
scene.camera = bpy.data.objects['Rural aerial']
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'dist/TCity_Rural_Settlement.blend'), compress=True)
print('RURAL_SERVICES', {key: root[key] for key in ('housing_instance_count', 'wire_spans', 'canal_runs', 'canal_gn_spline_count', 'canal_length', 'crop_count', 'culvert_count', 'culvert_length')}, flush=True)
