"""Populate the approved rural plan with the existing farm and street kit.

Housing reuses the kit's parametric wall/window/roof components: the bundled
whole compounds contain their own yards and cannot replace individual wings.
"""

import math
import random

import bpy
from mathutils import Matrix, Vector

from .assets import MeshBuilder, material
from .farm_assets import ensure_farm_assets, palette
from .lived_in import water_tank, aircon
from .rural_assets import front_wall, window, roof
from .sheds import metal_palette
from .street_assets import ensure_street_assets
from .surfaces import surface, palette as home_palette
from .rural_blender import build_rural_blockout
from .rural_layout import (
    load_layout, plan_building_lots, plan_housing, plan_field_parcels,
    _edges, _polyline_edges, _point_to_segment_distance, _point_to_polyline_distance,
    _polygon_inside, _polygons_intersect, point_in_polygon, distance,
)


def _house_mesh(width, depth, height, kind, door_x, seed):
    """Reuse kit components, keeping eaves and services inside the envelope.

    Local front is -Y; a clear door opening is aligned to the planned entrance.
    Dimensions include eaves. A shallow paved threshold bridges the wall inset.
    """
    b = MeshBuilder()
    rng = random.Random(seed)
    rp = home_palette()
    metals = metal_palette()
    p = {'steel': surface('Rural zinc frames', (.34, .37, .34), metallic=.55),
         'dark': material('Rural interior', (.023, .03, .027)),
         'concrete': surface('Rural yard concrete', (.29, .28, .25)),
         'pipe': material('Rural PVC', (.39, .40, .36))}
    brick = surface('Rural exposed red brick', (.30, .115, .066), tile='brick')
    wall = brick if kind == 'farmhouse' else surface('Rural cream mosaic', (.47, .435, .35), tile=True)
    if kind == 'shed_home':
        wall = metals[rng.randrange(len(metals))]
    x0, x1 = -width / 2 + .28, width / 2 - .28
    y0, y1 = -depth / 2 + .28, depth / 2 - .28
    pitched = kind != 'house'
    eave = min(height - .13, max(2.35, height - (.85 if pitched else 1.85)))
    door_x = max(x0 + .65, min(x1 - .65, door_x))
    b.box((0, 0, .065), (width - .04, depth - .04, .13), p['concrete'])
    for x in (x0, x1):
        b.box((x, (y0 + y1) / 2, eave / 2), (.16, y1 - y0, eave), wall)
    b.box((0, y1, eave / 2), (x1 - x0, .16, eave), wall)
    floors = max(1, round(eave / 3.))
    floor_height = eave / floors
    for floor in range(floors):
        z0, z1 = floor * floor_height, (floor + 1) * floor_height
        openings = [(door_x, 1.15, 1.15, 2.2)] if floor == 0 else []
        for x in (x0 + (x1 - x0) * .20, x0 + (x1 - x0) * .80):
            if floor == 0 and abs(x - door_x) < 1.35:
                continue
            openings.append((x, .95, z0 + floor_height * .57, .95))
            window(b, x, y0 - .02, z0 + floor_height * .57, .95, .95, p)
        front_wall(b, x0, x1, y0, z0, z1, openings, wall, p)
        if floor:
            b.box((0, 0, z0), (x1 - x0, y1 - y0, .13), p['concrete'])
    # A recessed door and a low threshold do not obstruct the pedestrian path.
    b.box((door_x, y0 + .035, 1.15), (1.1, .04, 2.2), metals[3])
    if pitched:
        roofing = surface('Village terracotta roof', (.46, .16, .095)) if kind == 'farmhouse' else metals[1]
        roof(b, x0 - .12, x1 + .12, y0 - .12, y1 + .12, eave, height - .12, roofing, p, drain_extension=.05)
        for y in (y0, y1):
            b.add([(x0, y, eave), (x1, y, eave), (0, y, height - .12)], [(0, 1, 2)], wall)
    else:
        b.box((0, 0, eave), (width - .12, depth - .12, .14), p['concrete'])
        for x in (x0, x1):
            b.box((x, 0, eave + .18), (.12, depth - .4, .36), wall)
        for y in (y0, y1):
            b.box((0, y, eave + .18), (width - .4, .12, .36), wall)
        water_tank(b, 0, max(0, y1 - 1.), eave + .12, .45, rp)
    if width > 4 and eave > 3:
        aircon(b, x0 + .85, y0 + .04, eave - .6, rp, seed)
    return b, (door_x, y0 - .10, 0)


def _assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for polygon in obj.data.polygons:
        polygon.material_index = 0


def _instances(name, points, source, collection):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(points, [], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    group = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = group.nodes, group.links
    source_input = nodes.new('NodeGroupInput')
    info = nodes.new('GeometryNodeObjectInfo')
    info.inputs['Object'].default_value = source
    info.inputs['As Instance'].default_value = True
    instance = nodes.new('GeometryNodeInstanceOnPoints')
    output = nodes.new('NodeGroupOutput')
    links.new(source_input.outputs['Geometry'], instance.inputs['Points'])
    links.new(info.outputs['Geometry'], instance.inputs['Instance'])
    links.new(instance.outputs['Instances'], output.inputs['Geometry'])
    obj.modifiers.new('Existing crop instances', 'NODES').node_group = group
    return obj


def _housing_instance_group(name, source_collection):
    """Create the Geometry Nodes placement layer for planned houses.

    The source meshes are assembled once by the Python asset builder so their
    openings and service details remain exact.  Placement is deliberately a
    node operation: the point mesh carries an asset index and a Z rotation,
    while Collection Info + Instance on Points handles the visible settlement.
    """

    group = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = group.nodes, group.links
    source_input = nodes.new('NodeGroupInput')
    source_input.label = 'Planned housing points'
    collection = nodes.new('GeometryNodeCollectionInfo')
    collection.label = 'Reusable rural housing assets'
    collection.inputs['Collection'].default_value = source_collection
    collection.inputs['Separate Children'].default_value = True
    collection.inputs['Reset Children'].default_value = False
    asset_index = nodes.new('GeometryNodeInputNamedAttribute')
    asset_index.data_type = 'INT'
    asset_index.inputs['Name'].default_value = 'rural_asset_index'
    rotation = nodes.new('GeometryNodeInputNamedAttribute')
    rotation.data_type = 'FLOAT_VECTOR'
    rotation.inputs['Name'].default_value = 'rural_rotation'
    instance = nodes.new('GeometryNodeInstanceOnPoints')
    instance.label = 'Instance planned house'
    instance.inputs['Pick Instance'].default_value = True
    output = nodes.new('NodeGroupOutput')
    links.new(source_input.outputs['Geometry'], instance.inputs['Points'])
    links.new(collection.outputs['Instances'], instance.inputs['Instance'])
    links.new(asset_index.outputs['Attribute'], instance.inputs['Instance Index'])
    links.new(rotation.outputs['Attribute'], instance.inputs['Rotation'])
    links.new(instance.outputs['Instances'], output.inputs['Geometry'])
    return group


def _housing_input(name, placements, source_collection, collection):
    """Build a point mesh and attach the housing instancing node group."""

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, y, z) for x, y, z, _, _ in placements], [], [])
    mesh.update()
    indices = mesh.attributes.new('rural_asset_index', 'INT', 'POINT')
    rotations = mesh.attributes.new('rural_rotation', 'FLOAT_VECTOR', 'POINT')
    for item, (_, _, _, _, asset_index) in zip(indices.data, placements):
        item.value = asset_index
    for item, (_, _, _, angle, _) in zip(rotations.data, placements):
        item.vector = (0., 0., angle)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj['rural_role'] = 'housing_gn'
    obj['asset_count'] = len(source_collection.objects)
    obj['instance_count'] = len(placements)
    obj['source_collection'] = source_collection.name
    modifier = obj.modifiers.new('Rural housing / Geometry Nodes', 'NODES')
    modifier.node_group = _housing_instance_group('Rural housing instancing', source_collection)
    return obj


def build_rural_scene(path, *, scene=None, crop_spacing=1.25, pole_spacing=32., cable_sag=.55, max_wire_span=40.):
    """Build a self-contained asset scene without changing the gray preview."""
    if crop_spacing < .8 or pole_spacing < 10:
        raise ValueError('crop_spacing must be >= 0.8 m and pole_spacing >= 10 m')
    layout = load_layout(path)
    lots = plan_building_lots(layout)
    homes = plan_housing(layout, lots)
    parcels = plan_field_parcels(layout)
    root = build_rural_blockout(path, scene=scene)
    root.name = 'TCity • Rural settlement'
    root['asset_scene'] = True
    root['crop_spacing'] = crop_spacing
    root['pole_spacing'] = pole_spacing
    farm = palette()
    kit = {obj['tc_farm_asset']: obj for obj in ensure_farm_assets().objects}
    objects = list(root.all_objects)
    building_objects = {(obj['source_id'], obj['building_part']): obj for obj in objects if obj.get('rural_role') == 'building'}
    housing_sources = bpy.data.collections.new('Rural GN housing assets')
    housing_sources.use_fake_user = True
    housing_sources['rural_role'] = 'housing_asset_sources'
    housing_sources['asset_scene'] = True
    housing_sources.hide_render = True
    housing_sources.hide_viewport = True
    housing_placements = []
    for lot, home in zip(lots, homes):
        angle = lot.heading + (math.pi if lot.side < 0 else 0)
        rotation = Matrix.Rotation(angle, 4, 'Z')
        for volume in home.buildings:
            center = Vector((sum(p[0] for p in volume.footprint) / 4, sum(p[1] for p in volume.footprint) / 4, .03))
            local = [rotation.inverted() @ (Vector((x, y, .03)) - center) for x, y in volume.footprint]
            width = max(p.x for p in local) - min(p.x for p in local)
            depth = max(p.y for p in local) - min(p.y for p in local)
            door = rotation.inverted() @ (Vector((*home.door, .03)) - center)
            kind = lot.kind if volume.role == 'main' else 'shed_home'
            builder, door_local = _house_mesh(width, depth, volume.height, kind,
                                             door.x if volume.role == 'main' else 0,
                                             f'{layout.seed}:{lot.id}:{volume.role}')
            source = builder.object('Rural housing source / ' + lot.id + ' / ' + volume.role,
                                    housing_sources)
            source['rural_role'] = 'rural_asset_source'
            source['source_id'] = lot.id
            source['building_part'] = volume.role
            source['asset_kind'] = kind
            source['source_index'] = len(housing_placements)
            transform = Matrix.Translation(center) @ rotation
            builder.transform(transform)
            obj = building_objects[lot.id, volume.role]
            temp = builder.object('Rural component assembly', root)
            old = obj.data
            obj.data = temp.data
            bpy.data.objects.remove(temp, do_unlink=True)
            if not old.users:
                bpy.data.meshes.remove(old)
            obj['asset_kind'] = kind
            obj['asset_door'] = tuple(transform @ Vector(door_local))
            obj['gn_asset_index'] = source['source_index']
            obj.hide_render = True
            obj.hide_set(True)
            housing_placements.append((center.x, center.y, center.z, angle, source['source_index']))
    root.children.link(housing_sources)
    _housing_input('Rural housing / GN points', housing_placements,
                   housing_sources, root)
    root['housing_gn'] = True
    root['housing_instance_count'] = len(housing_placements)
    parcel_map = {p.id: p for p in parcels}
    for obj in objects:
        role = obj.get('rural_role')
        if role == 'road':
            group = obj.modifiers[0].node_group
            for node in group.nodes:
                if node.bl_idname == 'GeometryNodeSetMaterial':
                    node.inputs['Material'].default_value = farm['road']
        elif role == 'field_parcel':
            tone = parcel_map[obj['source_id']].tone
            _assign_material(obj, farm['fields'][[0, 1, 2, 4, 5][tone]])
        elif role in ('yard', 'access', 'driveway'):
            _assign_material(obj, farm['concrete'] if role != 'yard' else farm['fields'][8])
        elif role == 'boundary':
            _assign_material(obj, farm['bund'])
        elif role == 'zone':
            _assign_material(obj, farm['water'] if obj['kind'] == 'reserved' else farm['bund'])
    crops = bpy.data.collections.new('Rural crops')
    root.children.link(crops)
    for parcel in parcels:
        if parcel.tone > 2:
            continue
        source = kit[parcel.tone]
        radius = max(math.hypot(v.co.x, v.co.y) for v in source.data.vertices)
        spacing = max(crop_spacing, radius * 2 + .15)
        points = []
        x = min(p[0] for p in parcel.polygon) + spacing / 2
        while x < max(p[0] for p in parcel.polygon):
            y = min(p[1] for p in parcel.polygon) + spacing / 2
            while y < max(p[1] for p in parcel.polygon):
                point = (x, y)
                if (point_in_polygon(point, parcel.polygon)
                    and all(_point_to_segment_distance(point, a, b) > radius + .12 for a, b in _edges(parcel.polygon))
                    and all(_point_to_polyline_distance(point, road.points) > road.width / 2 + radius + .35 for road in layout.roads)):
                    points.append((x, y, .055))
                y += spacing
            x += spacing
        obj = _instances('Crops / ' + parcel.id, points, source, crops)
        obj['rural_role'] = 'crops'
        obj['source_id'] = parcel.id
        obj['crop_radius'] = radius
        obj['crop_count'] = len(points)
    utilities = bpy.data.collections.new('Rural utility poles')
    root.children.link(utilities)
    pole = ensure_street_assets()['Pole']
    pole_radius = max(math.hypot(v.co.x, v.co.y) for v in pole.data.vertices)
    occupied = [v.footprint for home in homes for v in home.buildings]
    occupied += [polygon for home in homes for polygon in (home.access, home.driveway) if polygon]
    placed = []
    for road in layout.roads:
        for segment_index, (a, b) in enumerate(_polyline_edges(road.points)):
            length = distance(a, b)
            if length < 4:
                continue
            tangent = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
            for index in range(max(1, math.ceil(length / pole_spacing))):
                along = (index + .5) * length / max(1, math.ceil(length / pole_spacing))
                offset = road.width / 2 + pole_radius + .20
                point = (a[0] + tangent[0] * along + tangent[1] * offset,
                         a[1] + tangent[1] * along - tangent[0] * offset)
                guard = tuple((point[0] + dx * pole_radius, point[1] + dy * pole_radius)
                              for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)))
                if (not _polygon_inside(guard, layout.boundary)
                    or any(_polygons_intersect(guard, polygon) for polygon in occupied)
                    or any(_polygons_intersect(guard, z.polygon) for z in layout.zones if z.kind == 'reserved')
                    or any(_point_to_polyline_distance(point, other.points) < other.width / 2 + pole_radius + .1 for other in layout.roads)
                    or any(distance(point, other) < 8 for other in placed)):
                    continue
                obj = bpy.data.objects.new(f'Pole / {road.id}:{segment_index}:{index}', pole.data)
                utilities.objects.link(obj)
                obj.location = (*point, .03)
                obj.rotation_euler.z = math.atan2(tangent[1], tangent[0])
                obj['rural_role'] = 'pole'
                obj['road_id'] = road.id
                obj['road_station'] = sum(distance(x, y) for x, y in list(_polyline_edges(road.points))[:segment_index]) + along
                placed.append(point)
    for obj in crops.objects:
        radius = obj['crop_radius']
        points = [tuple(v.co) for v in obj.data.vertices
                  if all(distance((v.co.x, v.co.y), pole_point) > radius + pole_radius + .15 for pole_point in placed)]
        obj.data.clear_geometry()
        obj.data.from_pydata(points, [], [])
        obj.data.update()
        obj['crop_count'] = len(points)
    root['crop_count'] = sum(obj['crop_count'] for obj in crops.objects)
    root['pole_count'] = len(placed)
    from .rural_services import add_services
    add_services(root, layout, homes, farm, cable_sag=cable_sag, max_span=max_wire_span)
    return root
