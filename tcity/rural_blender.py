"""Editable Blender inputs and neutral volumes for rural composition review."""

import bpy

from .rural_layout import load_layout, plan_building_lots, plan_field_parcels, plan_housing


def _material(name, value):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (value, value, value, 1)
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = material.diffuse_color
    shader.inputs['Roughness'].default_value = .9
    return material


def _mesh(name, vertices, faces, collection, material):
    data = bpy.data.meshes.new(name)
    data.from_pydata(vertices, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    data.materials.append(material)
    return obj


def _road_surface(width, material):
    """A flat ribbon that follows edits to the original road Curve."""
    group = bpy.data.node_groups.new('Rural road preview', 'GeometryNodeTree')
    group.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = group.nodes, group.links
    source = nodes.new('NodeGroupInput')
    profile = nodes.new('GeometryNodeCurvePrimitiveLine')
    profile.inputs['Start'].default_value = (-width / 2, 0, 0)
    profile.inputs['End'].default_value = (width / 2, 0, 0)
    surface = nodes.new('GeometryNodeCurveToMesh')
    shade = nodes.new('GeometryNodeSetMaterial')
    shade.inputs['Material'].default_value = material
    output = nodes.new('NodeGroupOutput')
    links.new(source.outputs['Geometry'], surface.inputs['Curve'])
    links.new(profile.outputs['Curve'], surface.inputs['Profile Curve'])
    links.new(surface.outputs['Mesh'], shade.inputs['Geometry'])
    links.new(shade.outputs['Geometry'], output.inputs['Geometry'])
    return group


def build_rural_blockout(path, *, scene=None):
    """Append an isolated collection; leave existing scene objects untouched.

    JSON is authoritative. Reimport creates a separate snapshot for comparison.
    Curve edits update road ribbons; lots are a snapshot of the source plan.
    """
    layout = load_layout(path)
    lots = plan_building_lots(layout)
    parcels = plan_field_parcels(layout)
    housing = plan_housing(layout, lots)
    scene = scene or bpy.context.scene
    root = bpy.data.collections.new('TCity • Rural composition')
    scene.collection.children.link(root)
    root['source_json'] = str(path)
    root['seed'] = layout.seed
    children = {}
    for name in ('Road inputs', 'Zone inputs', 'Building placeholders', 'Field placeholders', 'Yards and access'):
        child = bpy.data.collections.new(name)
        root.children.link(child)
        children[name] = child
    materials = {name: _material('Rural preview / ' + name, value) for name, value in
                 [('ground', .30), ('road', .16), ('residential', .43),
                  ('field', .25), ('reserved', .11), ('building', .72),
                  ('side_wing', .50), ('yard', .28), ('access', .57)]}
    field_materials = [_material(f'Rural preview / field tone {i}', value)
                       for i, value in enumerate((.16, .22, .30, .38, .46))]
    boundary = _mesh('Rural boundary', [(x, y, 0) for x, y in layout.boundary],
                     [tuple(range(len(layout.boundary)))], root, materials['ground'])
    boundary['rural_role'] = 'boundary'
    for zone in layout.zones:
        obj = _mesh('Zone / ' + zone.id, [(x, y, .02) for x, y in zone.polygon],
                    [tuple(range(len(zone.polygon)))], children['Zone inputs'], materials[zone.kind])
        obj['rural_role'] = 'zone'
        obj['source_id'] = zone.id
        obj['kind'] = zone.kind
        obj['label'] = zone.label
    for parcel in parcels:
        obj = _mesh('Field / ' + parcel.id, [(x, y, .04) for x, y in parcel.polygon],
                    [tuple(range(len(parcel.polygon)))], children['Field placeholders'],
                    field_materials[parcel.tone])
        obj['rural_role'] = 'field_parcel'
        obj['source_id'] = parcel.id
        obj['zone_id'] = parcel.zone_id
    for index, road in enumerate(layout.roads):
        data = bpy.data.curves.new('Road / ' + road.id, 'CURVE')
        data.dimensions = '3D'
        data.twist_mode = 'Z_UP'
        spline = data.splines.new('POLY')
        spline.points.add(len(road.points) - 1)
        for point, (x, y) in zip(spline.points, road.points):
            point.co = (x, y, 0, 1)
        obj = bpy.data.objects.new(data.name, data)
        children['Road inputs'].objects.link(obj)
        # Separate overlapping ribbons slightly to avoid coplanar flicker.
        obj.location.z = .06 + index * .002
        obj['rural_role'] = 'road'
        obj['source_id'] = road.id
        obj['kind'] = road.kind
        obj['width'] = road.width
        modifier = obj.modifiers.new('Road surface preview', 'NODES')
        modifier.node_group = _road_surface(road.width, materials['road'])
    for lot, home in zip(lots, housing):
        objects = []
        for volume in home.buildings:
            vertices = [(x, y, z) for z in (.03, volume.height + .03) for x, y in volume.footprint]
            faces = [(3, 2, 1, 0), (4, 5, 6, 7)]
            faces.extend((i, (i + 1) % 4, (i + 1) % 4 + 4, i + 4) for i in range(4))
            obj = _mesh('Building / ' + lot.id + ' / ' + volume.role, vertices, faces,
                        children['Building placeholders'],
                        materials['building' if volume.role == 'main' else 'side_wing'])
            obj['rural_role'] = 'building'
            obj['building_part'] = volume.role
            objects.append(obj)
        for role, polygon, z in (('yard', home.yard, .035), ('access', home.access, .045),
                                 ('driveway', home.driveway, .05)):
            if not polygon:
                continue
            obj = _mesh(role.title() + ' / ' + lot.id, [(x, y, z) for x, y in polygon],
                        [tuple(range(len(polygon)))], children['Yards and access'],
                        materials['yard' if role == 'yard' else 'access'])
            obj['rural_role'] = role
            objects.append(obj)
        for obj in objects:
            obj['source_id'] = lot.id
            obj['zone_id'] = lot.zone_id
            obj['road_id'] = lot.road_id
            obj['kind'] = lot.kind
            obj['heading'] = lot.heading
            obj['entry'] = home.gate
            obj['door'] = home.door
            obj['road_entry'] = home.road_entry
    return root
