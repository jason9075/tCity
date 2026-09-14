"""Validate evaluated preview geometry and saved-scene portability in Blender."""

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tcity.rural_blender import build_rural_blockout
from tcity.rural_layout import (
    load_layout, plan_building_lots, plan_field_parcels, plan_housing, polygon_area,
    _footprint_clear_of_road, _polygons_intersect, convex_polygons_overlap,
)

source = ROOT / 'docs/rural_reference_layout.json'
layout = load_layout(source)
existing = tuple(bpy.context.scene.objects)
root = build_rural_blockout(source)
assert all(obj.name in bpy.context.scene.objects for obj in existing)


def verify(collection):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    roads = {o['source_id']: o for o in collection.all_objects if o.get('rural_role') == 'road'}
    zones = {o['source_id']: o for o in collection.all_objects if o.get('rural_role') == 'zone'}
    buildings = {(o['source_id'], o['building_part']): o for o in collection.all_objects if o.get('rural_role') == 'building'}
    surfaces = {(o['source_id'], o['rural_role']): o for o in collection.all_objects
                if o.get('rural_role') in ('yard', 'access', 'driveway')}
    fields = {o['source_id']: o for o in collection.all_objects if o.get('rural_role') == 'field_parcel'}
    assert len(roads) == len(layout.roads)
    assert len(zones) == len(layout.zones)
    housing = plan_housing(layout)
    assert len(buildings) == sum(len(home.buildings) for home in housing)
    assert len(fields) == len(plan_field_parcels(layout))
    road_faces = []
    for road in layout.roads:
        obj = roads[road.id]
        assert obj.type == 'CURVE'
        assert len(obj.data.splines[0].points) == len(road.points)
        evaluated = obj.evaluated_get(dg)
        mesh = evaluated.to_mesh()
        try:
            assert len(mesh.polygons) == len(road.points) - 1
            assert sum(p.area for p in mesh.polygons) > road.length * road.width * .85
            assert max(v.co.z for v in mesh.vertices) - min(v.co.z for v in mesh.vertices) < .001
            assert abs((mesh.vertices[0].co - mesh.vertices[1].co).length - road.width) < .001
            road_faces.extend(tuple((mesh.vertices[i].co.x, mesh.vertices[i].co.y) for i in face.vertices)
                              for face in mesh.polygons)
        finally:
            evaluated.to_mesh_clear()
    for zone in layout.zones:
        mesh = zones[zone.id].evaluated_get(dg).data
        assert abs(sum(p.area for p in mesh.polygons) - zone.area) < .02
        assert max(v.co.z for v in mesh.vertices) - min(v.co.z for v in mesh.vertices) < .001
    footprints, corridors = [], []
    for lot, home in zip(plan_building_lots(layout), housing):
        for volume in home.buildings:
            obj = buildings[lot.id, volume.role]
            mesh = obj.evaluated_get(dg).data
            assert len(mesh.vertices) == 8 and len(mesh.polygons) == 6
            assert obj['road_id'] == lot.road_id and obj['zone_id'] == lot.zone_id
            assert min(v.co.z for v in mesh.vertices) >= 0
            assert abs(max(v.co.z for v in mesh.vertices) - .03 - volume.height) < .001
            assert all(p.normal.z > .99 for p in mesh.polygons if all(i >= 4 for i in p.vertices))
            for vertex, point in zip(mesh.vertices[:4], volume.footprint):
                assert abs(vertex.co.x - point[0]) < .001 and abs(vertex.co.y - point[1]) < .001
            footprint = tuple((v.co.x, v.co.y) for v in mesh.vertices[:4])
            assert all(_footprint_clear_of_road(footprint, road, 1.999) for road in layout.roads)
            assert not any(_polygons_intersect(footprint, face) for face in road_faces), lot.id
            footprints.append(footprint)
        for role in ('yard', 'access', 'driveway'):
            polygon = getattr(home, role)
            if not polygon:
                continue
            mesh = surfaces[lot.id, role].evaluated_get(dg).data
            assert abs(sum(p.area for p in mesh.polygons) - polygon_area(polygon)) < .001
            for vertex, point in zip(mesh.vertices, polygon):
                assert abs(vertex.co.x - point[0]) < .001 and abs(vertex.co.y - point[1]) < .001
            if role != 'yard':
                corridors.append(tuple((v.co.x, v.co.y) for v in mesh.vertices))
    # Shrink by a few micrometres to tolerate float32 at shared wall edges.
    def inset(polygon):
        x = sum(p[0] for p in polygon) / len(polygon)
        y = sum(p[1] for p in polygon) / len(polygon)
        return tuple((x + (a - x) * .99999, y + (b - y) * .99999) for a, b in polygon)
    for index, first in enumerate(footprints):
        assert not any(convex_polygons_overlap(inset(first), inset(second)) for second in footprints[index + 1:])
    assert not any(convex_polygons_overlap(inset(path), inset(building)) for path in corridors for building in footprints)
    for parcel in plan_field_parcels(layout):
        obj = fields[parcel.id]
        mesh = obj.evaluated_get(dg).data
        assert obj['zone_id'] == parcel.zone_id
        assert abs(sum(p.area for p in mesh.polygons) - polygon_area(parcel.polygon)) < .02
        assert len(mesh.vertices) == len(parcel.polygon)
        for vertex, point in zip(mesh.vertices, parcel.polygon):
            assert abs(vertex.co.x - point[0]) < .001 and abs(vertex.co.y - point[1]) < .001
    return len(roads), len(zones), len(buildings), len(fields)


counts = verify(root)
road = next(o for o in root.all_objects if o.get('rural_role') == 'road')
before = road.data.splines[0].points[0].co.copy()
road.data.splines[0].points[0].co.x += 2
road.data.update_tag()
bpy.context.view_layer.update()
evaluated = road.evaluated_get(bpy.context.evaluated_depsgraph_get())
mesh = evaluated.to_mesh()
assert abs((mesh.vertices[0].co.x + mesh.vertices[1].co.x) / 2 - before.x - 2) < .001
evaluated.to_mesh_clear()
road.data.splines[0].points[0].co = before
road.data.update_tag()
name = root.name
destination = ROOT / 'build/rural_blockout_test.blend'
destination.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(destination))
bpy.ops.wm.open_mainfile(filepath=str(destination))
assert verify(bpy.data.collections[name]) == counts
report = {'result': 'PASS', 'blender': bpy.app.version_string,
          'roads': counts[0], 'zones': counts[1], 'buildings': counts[2], 'fields': counts[3],
          'homes': len(plan_housing(layout)), 'clear_access': True,
          'curve_edit_updates_surface': True, 'save_reload': True}
(ROOT / 'dist').mkdir(exist_ok=True)
(ROOT / 'dist/rural_blockout_test_results.json').write_text(json.dumps(report, indent=2) + '\n')
print('RURAL_BLOCKOUT_PASS', report, flush=True)
