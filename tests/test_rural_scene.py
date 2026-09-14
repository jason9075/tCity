"""Evaluated containment, entrances, crop exclusion and asset portability."""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tcity.rural_scene import build_rural_scene
from tcity.rural_layout import (
    load_layout, plan_building_lots, plan_housing, plan_field_parcels,
    _polygon_inside, _polygons_intersect, _footprint_clear_of_road, distance,
    _polyline_polygon_distance, point_in_polygon,
)

source = ROOT / 'docs/rural_reference_layout.json'
layout = load_layout(source)
lots = plan_building_lots(layout)
homes = plan_housing(layout, lots)
root = build_rural_scene(source)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
objects = list(root.all_objects)
buildings = {(o['source_id'], o['building_part']): o for o in objects if o.get('rural_role') == 'building'}
assert len(buildings) == sum(len(h.buildings) for h in homes)
housing_gn = [o for o in objects if o.get('rural_role') == 'housing_gn']
housing_sources = [o for o in objects if o.get('rural_role') == 'rural_asset_source']
assert len(housing_gn) == 1
assert len(housing_sources) == len(buildings)
assert housing_gn[0].modifiers and housing_gn[0].modifiers[0].node_group.name == 'Rural housing instancing'
bpy.context.view_layer.update()
housing_instance_count = 0
for item in dg.object_instances:
    if item.parent and item.parent.name == housing_gn[0].name:
        housing_instance_count += 1
assert housing_instance_count == len(buildings)
print('PASS Geometry Nodes housing layer instances all planned volumes', housing_instance_count, flush=True)
for lot, home in zip(lots, homes):
    angle = lot.heading + (math.pi if lot.side < 0 else 0)
    along = Vector((math.cos(angle), math.sin(angle), 0))
    inward = Vector((-math.sin(angle), math.cos(angle), 0))
    for volume in home.buildings:
        obj = buildings[lot.id, volume.role]
        mesh = obj.evaluated_get(dg).data
        assert len(mesh.polygons) > 50 and len(mesh.materials) >= 4
        bounds = [[Vector((*p, 0)).dot(axis) for p in volume.footprint] for axis in (along, inward)]
        for axis, values in zip((along, inward), bounds):
            actual = [v.co.dot(axis) for v in mesh.vertices]
            assert min(actual) >= min(values) - .001, (lot.id, volume.role, 'minimum', min(actual), min(values))
            assert max(actual) <= max(values) + .001, (lot.id, volume.role, 'maximum', max(actual), max(values))
        assert min(v.co.z for v in mesh.vertices) >= .029
        assert max(v.co.z for v in mesh.vertices) <= volume.height + .031
    # A ray at pedestrian height must reach the aligned door, not a side wing.
    main = buildings[lot.id, 'main'].evaluated_get(dg)
    origin = Vector((*home.door, 1.1)) - inward * .5
    hit, location, normal, index = main.ray_cast(origin, inward, distance=1.)
    assert hit, ('door missing', lot.id)
    assert abs((location - Vector((*home.door, 1.1))).dot(along)) < .001
    assert .15 <= (location - Vector((*home.door, 1.1))).dot(inward) <= .4
print('PASS Housing components fit all 82 reserved volumes; all 49 main entrances align', flush=True)

parcels = {p.id: p for p in plan_field_parcels(layout)}
poles = [o for o in objects if o.get('rural_role') == 'pole']
assert len(poles) == root['pole_count'] and len(poles) > 15
pole_gn = [o for o in objects if o.get('rural_role') == 'poles_gn']
assert len(pole_gn) == 1 and pole_gn[0].modifiers[0].node_group.name.endswith(' / GN')
pole_instances = sum(
    1 for item in dg.object_instances
    if item.parent and item.parent.name == pole_gn[0].name
)
assert pole_instances == len(poles)
wire_gn = [o for o in objects if o.get('rural_role') == 'wires_gn']
assert len(wire_gn) == 1 and wire_gn[0]['spline_count'] == root['wire_spans'] * 4
wire_gn_spline_count = wire_gn[0]['spline_count']
wire_evaluated = wire_gn[0].evaluated_get(dg)
wire_mesh = wire_evaluated.to_mesh()
assert len(wire_mesh.vertices) > root['wire_spans'] * 4 * 100
wire_evaluated.to_mesh_clear()
print('PASS Geometry Nodes utility layer instances poles and wire splines',
      pole_instances, wire_gn[0]['spline_count'], flush=True)
corridors = [p for h in homes for p in (h.access, h.driveway) if p]
occupied = [v.footprint for h in homes for v in h.buildings]
for obj in poles:
    mesh = obj.evaluated_get(dg).data
    vertices = [obj.matrix_world @ v.co for v in mesh.vertices]
    x0, x1 = min(v.x for v in vertices), max(v.x for v in vertices)
    y0, y1 = min(v.y for v in vertices), max(v.y for v in vertices)
    footprint = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    assert _polygon_inside(footprint, layout.boundary)
    assert not any(_polygons_intersect(footprint, p) for p in occupied + corridors)
    assert all(_footprint_clear_of_road(footprint, road, 0) for road in layout.roads)
print('PASS Poles avoid buildings, roads and pedestrian entrances', len(poles), flush=True)

from tcity.rural_services import ANCHORS
wires = [o for o in objects if o.get('rural_role') == 'wire']
canals = [o for o in objects if o.get('rural_role') == 'canal']
assert len(wires) == root['wire_spans'] * 4 and len(wires) > 20
assert len(canals) == root['canal_runs'] and len(canals) > 10
for obj in wires:
    first, second = (bpy.data.objects[obj[key]] for key in ('pole_start', 'pole_end'))
    across, height = ANCHORS[obj['anchor_index']]
    start, end = (pole.matrix_world @ Vector((0, across, height)) for pole in (first, second))
    assert (end - start).length < root['max_wire_span'] + 1
    mesh = obj.evaluated_get(dg).data
    vertices = [v.co for v in mesh.vertices]
    for anchor in (start, end):
        assert min((v - anchor).length for v in vertices) < .025
    assert abs(min(v.z for v in vertices) - (height + .03 - obj['sag'])) < .025
    for v in vertices:
        assert v.z > 4.5
        assert point_in_polygon((v.x, v.y), layout.boundary)
        assert not any(point_in_polygon((v.x, v.y), polygon) for polygon in occupied + corridors)
canal_guards = []
for obj in canals:
    coords = list(obj['footprint'])
    guard = tuple(zip(coords[::2], coords[1::2]))
    canal_guards.append(guard)
    assert _polygon_inside(guard, layout.boundary)
    assert all(_footprint_clear_of_road(guard, road, .499) for road in layout.roads)
    assert not any(_polygons_intersect(guard, polygon) for polygon in occupied + corridors)
    mesh = obj.evaluated_get(dg).data
    assert len(mesh.polygons) == 19
    assert abs(min(v.co.z for v in mesh.vertices) - .04) < .001
    assert abs(max(v.co.z for v in mesh.vertices) - .5) < .001
    water = [p for p in mesh.polygons if 'water' in mesh.materials[p.material_index].name.lower()]
    assert len(water) == 1 and water[0].normal.z > .99
    assert abs(water[0].area - obj['length'] * .56) < .01
    # Ray from above the center hits water below the open rim, not a lid.
    center = water[0].center.copy()
    hit, location, normal, index = obj.evaluated_get(dg).ray_cast(Vector((center.x, center.y, 2)), Vector((0, 0, -1)))
    assert hit and abs(location.z - .28) < .001
print('PASS Supported sagging wires and open irrigation troughs', len(wires), len(canals), flush=True)

# A corner connection is represented by two ordinary channel runs whose
# station intervals now meet at the source polygon vertex.  This keeps the
# channel editable without introducing a second, overlapping corner mesh.
corner_links = 0
for zone in layout.zones:
    if zone.kind != 'field':
        continue
    zone_edges = list(zip(zone.polygon, zone.polygon[1:] + zone.polygon[:1]))
    for vertex_index in range(len(zone_edges)):
        previous_edge = (vertex_index - 1) % len(zone_edges)
        previous_length = distance(*zone_edges[previous_edge])
        previous_closed = any(
            o.get('zone_id') == zone.id and o.get('edge_index') == previous_edge
            and abs(o['station_end'] - previous_length) < .001 for o in canals)
        following_closed = any(
            o.get('zone_id') == zone.id and o.get('edge_index') == vertex_index
            and abs(o['station_start']) < .001 for o in canals)
        corner_links += previous_closed and following_closed
assert root['canal_corner_connections'] == corner_links
assert corner_links >= 1
print('PASS Field-edge corner joins reach shared polygon vertices', corner_links, flush=True)

culverts = [o for o in objects if o.get('rural_role') == 'culvert']
chambers = [o for o in objects if o.get('rural_role') == 'culvert_chamber']
assert len(culverts) == root['culvert_count'] and len(culverts) >= 2
assert len(chambers) == len(culverts) * 2
for obj in culverts:
    mesh = obj.evaluated_get(dg).data
    assert max(v.co.z for v in mesh.vertices) < 0
    assert len(mesh.polygons) == 24
    a, b = (bpy.data.objects[obj[key]] for key in ('channel_start', 'channel_end'))
    assert a['zone_id'] == b['zone_id'] and a['edge_index'] == b['edge_index']
    assert abs(b['station_start'] - a['station_end'] - obj['length'] - 1.6) < .001
    coords = list(obj['footprint'])
    guard = tuple(zip(coords[::2], coords[1::2]))
    assert any(not _footprint_clear_of_road(guard, road, 0) for road in layout.roads)
    assert not any(_polygons_intersect(guard, polygon) for polygon in occupied + corridors)
for obj in chambers:
    coords = list(obj['footprint'])
    guard = tuple(zip(coords[::2], coords[1::2]))
    canal_guards.append(guard)
    assert all(_footprint_clear_of_road(guard, road, .49) for road in layout.roads)
    center = Vector((sum(coords[::2]) / 4, sum(coords[1::2]) / 4, .1))
    hit, position, normal, index = obj.evaluated_get(dg).ray_cast(center, Vector((0, 0, -1)))
    assert hit and abs(position.z + .6) < .001
    # Ground below the water must actually have an opening.
    for ground in objects:
        if ground.get('rural_role') in ('boundary', 'zone', 'field_parcel'):
            assert not ground.evaluated_get(dg).ray_cast(center, Vector((0, 0, -1)), distance=.15)[0]
print('PASS Buried culverts, channel connections and ground openings', len(culverts), flush=True)

crop_count = 0
for instance in dg.object_instances:
    if not instance.is_instance or not instance.parent or instance.parent.original.get('rural_role') != 'crops':
        continue
    parent = instance.parent.original
    parcel = parcels[parent['source_id']]
    # Bounding rectangles contain every evaluated crop vertex at identity scale.
    points = [instance.matrix_world @ Vector(p) for p in instance.object.bound_box]
    x0, x1 = min(p.x for p in points), max(p.x for p in points)
    y0, y1 = min(p.y for p in points), max(p.y for p in points)
    footprint = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    assert _polygon_inside(footprint, parcel.polygon)
    assert all(_footprint_clear_of_road(footprint, road, .1) for road in layout.roads)
    assert not any(_polygons_intersect(footprint, guard) for guard in canal_guards)
    assert all(distance((instance.matrix_world.translation.x, instance.matrix_world.translation.y),
                        (pole.location.x, pole.location.y)) > parent['crop_radius'] + .6 for pole in poles)
    crop_count += 1
assert crop_count == root['crop_count'] and crop_count > 1000, crop_count
print('PASS Evaluated crop instances remain in fields and off roads', crop_count, flush=True)

name = root.name
destination = ROOT / 'build/rural_scene_test.blend'
destination.parent.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(destination), compress=True)
bpy.ops.wm.open_mainfile(filepath=str(destination))
root = bpy.data.collections[name]
bpy.context.view_layer.update()
reloaded = sum(i.is_instance and i.parent is not None and i.parent.original.get('rural_role') == 'crops'
               for i in bpy.context.evaluated_depsgraph_get().object_instances)
assert reloaded == crop_count
assert sum(o.get('rural_role') == 'building' for o in root.all_objects) == len(buildings)
assert sum(o.get('rural_role') == 'pole' for o in root.all_objects) == len(poles)
assert sum(o.get('rural_role') == 'wire' for o in root.all_objects) == len(wires)
assert sum(o.get('rural_role') == 'canal' for o in root.all_objects) == len(canals)
assert sum(o.get('rural_role') == 'culvert' for o in root.all_objects) == len(culverts)
assert sum(o.get('rural_role') == 'housing_gn' for o in root.all_objects) == 1
assert sum(o.get('rural_role') == 'rural_asset_source' for o in root.all_objects) == len(buildings)
assert sum(o.get('rural_role') == 'poles_gn' for o in root.all_objects) == 1
assert sum(o.get('rural_role') == 'wires_gn' for o in root.all_objects) == 1
housing_host = next(o for o in root.all_objects if o.get('rural_role') == 'housing_gn')
reloaded_housing = sum(
    int(item.parent is not None and item.parent.name == housing_host.name)
    for item in bpy.context.evaluated_depsgraph_get().object_instances
)
assert reloaded_housing == len(buildings)
pole_host = next(o for o in root.all_objects if o.get('rural_role') == 'poles_gn')
reloaded_poles = sum(
    int(item.parent is not None and item.parent.name == pole_host.name)
    for item in bpy.context.evaluated_depsgraph_get().object_instances
)
assert reloaded_poles == len(poles)
report = {'result': 'PASS', 'blender': bpy.app.version_string, 'homes': len(homes),
          'building_volumes': len(buildings), 'crops': crop_count, 'poles': len(poles),
          'housing_gn_instances': housing_instance_count,
          'pole_gn_instances': pole_instances, 'wire_gn_splines': wire_gn_spline_count,
          'wire_spans': root['wire_spans'], 'canal_runs': len(canals), 'canal_length': root['canal_length'],
          'canal_corner_connections': root['canal_corner_connections'],
          'culverts': len(culverts), 'culvert_length': root['culvert_length'],
          'door_alignment': True, 'save_reload': True}
(ROOT / 'dist').mkdir(exist_ok=True)
(ROOT / 'dist/rural_scene_test_results.json').write_text(json.dumps(report, indent=2) + '\n')
print('RURAL_SCENE_PASS', report, flush=True)
