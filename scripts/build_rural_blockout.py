"""Build rural JSON preview; add --render for aerial, plan and housing PNGs."""

import argparse
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tcity.rural_blender import build_rural_blockout


def build():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', type=Path, default=ROOT / 'docs/rural_reference_layout.json')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--assets', action='store_true', help='Build the approved layout with rural assets')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if args.assets:
        from tcity.rural_scene import build_rural_scene
        root = build_rural_scene(args.layout)
    else:
        root = build_rural_blockout(args.layout)
    scene = bpy.context.scene
    # The demo owns presentation visibility, but never deletes unrelated objects.
    for obj in scene.objects:
        if obj not in tuple(root.all_objects):
            obj.hide_render = True
            obj.hide_set(True)
    scene.unit_settings.system = 'METRIC'
    points = [v.co for o in root.objects if o.get('rural_role') == 'boundary' for v in o.data.vertices]
    center = Vector(((min(p.x for p in points) + max(p.x for p in points)) / 2,
                     (min(p.y for p in points) + max(p.y for p in points)) / 2, 0))
    span = max(max(p.x for p in points) - min(p.x for p in points),
               (max(p.y for p in points) - min(p.y for p in points)) * 1.5) * 1.12
    cameras = []
    home_centers = [sum((v.co for v in obj.data.vertices), Vector()) / len(obj.data.vertices)
                    for obj in root.all_objects if obj.get('building_part') == 'main']
    housing_center = min(home_centers, key=lambda p: (p - center).length) if home_centers else center
    for name, offset in [('aerial', (0, -.95, .95)), ('plan', (0, 0, 1)), ('housing', (0, -.95, .95))]:
        data = bpy.data.cameras.new('Rural ' + name)
        camera = bpy.data.objects.new(data.name, data)
        root.objects.link(camera)
        target = housing_center if name == 'housing' else center
        camera.location = target + Vector(offset) * span
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        data.type = 'ORTHO'
        data.ortho_scale = span * .26 if name == 'housing' else span
        data.clip_end = span * 10
        cameras.append(camera)
    light = bpy.data.lights.new('Rural preview sun', 'SUN')
    light.energy = 2.5
    light.angle = .12
    sun = bpy.data.objects.new(light.name, light)
    root.objects.link(sun)
    sun.rotation_euler = (.4, -.5, -.4)
    scene.world = bpy.data.worlds.new('Rural preview world')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = (.35, .35, .35, 1)
    if args.assets:
        sys.path.insert(0, str(ROOT / 'scripts'))
        from build_demo import environment
        environment(scene)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 1000
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.camera = cameras[0]
    scene.view_settings.view_transform = 'AgX'
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
                area.spaces.active.clip_end = span * 10
                if args.assets:
                    area.spaces.active.shading.type = 'MATERIAL'
    destination = ROOT / ('dist/TCity_Rural_Settlement.blend' if args.assets else 'dist/TCity_Rural_Blockout.blend')
    destination.parent.mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(destination), compress=True)
    if args.render:
        (ROOT / 'renders').mkdir(exist_ok=True)
        for camera, suffix in zip(cameras, ('aerial', 'plan', 'housing')):
            scene.camera = camera
            prefix = 'rural_scene' if args.assets else 'rural_blockout'
            scene.render.filepath = str(ROOT / f'renders/{prefix}_{suffix}.png')
            bpy.ops.render.render(write_still=True)
    return root


if __name__ == '__main__':
    build()
