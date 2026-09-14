"""Road-gap box conduits with open end chambers; visual geometry, not flow simulation."""

import math

import bpy
from mathutils import Matrix, Vector

from .assets import MeshBuilder
from .rural_layout import (
    _edges, _oriented_rectangle, _polygon_inside, _polygons_intersect,
    _footprint_clear_of_road, _polyline_polygon_distance, distance,
    _signed_polygon_area, polygon_area,
)


def trough(builder, length, farm):
    builder.box((0, 0, .10), (length, .8, .12), farm['concrete'])
    for side in (-1, 1):
        builder.box((0, side * .34, .30), (length, .12, .40), farm['concrete'])
    builder.add([(-length / 2, -.28, .28), (length / 2, -.28, .28),
                 (length / 2, .28, .28), (-length / 2, .28, .28)], [(0, 1, 2, 3)], farm['water'])


def _clip(polygon, a, b, inside):
    result = []
    def signed(p):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
    for p, q in _edges(polygon):
        dp, dq = signed(p), signed(q)
        pin, qin = (dp >= 0, dq >= 0) if inside else (dp <= 0, dq <= 0)
        if pin:
            result.append(p)
        if pin != qin and abs(dp - dq) > 1e-12:
            t = dp / (dp - dq)
            result.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    clean = []
    for point in result:
        if not clean or distance(point, clean[-1]) > 1e-7:
            clean.append(point)
    if len(clean) > 1 and distance(clean[0], clean[-1]) < 1e-7:
        clean.pop()
    return tuple(clean)


def _cut_ground_openings(root, openings):
    """Subtract convex chamber footprints from planar ground faces.

    Triangulate source faces first so concave region outlines remain supported.
    Source layout polygons remain in JSON; the asset scene contains the cuts.
    """
    from mathutils.geometry import tessellate_polygon
    for obj in list(root.all_objects):
        if obj.get('rural_role') not in ('boundary', 'zone', 'field_parcel'):
            continue
        builder = MeshBuilder()
        changed = False
        for face in obj.data.polygons:
            vertices = [obj.data.vertices[i].co for i in face.vertices]
            polygon = tuple((v.x, v.y) for v in vertices)
            relevant = [p for p in openings if _polygons_intersect(polygon, p)]
            if not relevant:
                builder.add([tuple(v) for v in vertices], [tuple(range(len(vertices)))], obj.data.materials[face.material_index])
                continue
            changed = True
            pieces = [tuple((vertices[i].x, vertices[i].y) for i in triangle)
                      for triangle in tessellate_polygon([vertices])]
            for opening in relevant:
                if _signed_polygon_area(opening) < 0:
                    opening = tuple(reversed(opening))
                result = []
                for piece in pieces:
                    remainder = piece
                    for a, b in _edges(opening):
                        outside = _clip(remainder, a, b, False)
                        if len(outside) >= 3 and polygon_area(outside) > 1e-8:
                            result.append(outside)
                        remainder = _clip(remainder, a, b, True)
                        if len(remainder) < 3:
                            break
                pieces = result
            for piece in pieces:
                if _signed_polygon_area(piece) < 0:
                    piece = tuple(reversed(piece))
                builder.add([(x, y, vertices[0].z) for x, y in piece], [tuple(range(len(piece)))], obj.data.materials[face.material_index])
        if changed:
            temp = builder.object('Culvert ground opening', root)
            old = obj.data
            obj.data = temp.data
            bpy.data.objects.remove(temp, do_unlink=True)
            if not old.users:
                bpy.data.meshes.remove(old)


def connect_road_gaps(root, layout, homes, poles, farm):
    """Connect consecutive channels only across verified road-only gaps.

    A buried box conduit sits below all preview road surfaces. Each end has
    an open drop chamber occupying the last 0.8 m of the adjoining channel.
    Unrelated obstacles and short channels remain disconnected.
    """
    collection = bpy.data.collections.new('Rural road culverts')
    root.children.link(collection)
    channels = [o for o in root.all_objects if o.get('rural_role') == 'canal']
    blocked = [v.footprint for h in homes for v in h.buildings]
    blocked += [p for h in homes for p in (h.access, h.driveway) if p]
    groups = {}
    for obj in channels:
        groups.setdefault((obj['zone_id'], obj['edge_index']), []).append(obj)
    zones = {z.id: z for z in layout.zones}
    links = []
    exclusions = []
    openings = []
    for (zone_id, edge_index), group in groups.items():
        a, b = _edges(zones[zone_id].polygon)[edge_index]
        length = distance(a, b)
        tangent = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        rotation = Matrix.Rotation(math.atan2(tangent[1], tangent[0]), 4, 'Z')

        def guard(start, end):
            mid = (start + end) / 2
            return _oriented_rectangle((a[0] + tangent[0] * mid, a[1] + tangent[1] * mid), tangent, end - start, .8)

        def transform(start, end):
            mid = (start + end) / 2
            return Matrix.Translation(Vector((a[0] + tangent[0] * mid, a[1] + tangent[1] * mid, 0))) @ rotation

        ordered = sorted(group, key=lambda o: o['station_start'])
        for first, second in zip(ordered, ordered[1:]):
            start, end = first['station_end'], second['station_start']
            if not 1 < end - start < 35 or min(first['length'], second['length']) < 3:
                continue
            footprint = guard(start - .8, end + .8)
            roads = [r for r in layout.roads if not _footprint_clear_of_road(guard(start, end), r, 0)]
            if not roads or not _polygon_inside(footprint, layout.boundary):
                continue
            if (any(_polygons_intersect(footprint, polygon) for polygon in blocked)
                or any(_polygons_intersect(footprint, z.polygon) for z in layout.zones if z.kind == 'reserved')
                or any(_polyline_polygon_distance((tuple(p.location[:2]), tuple(p.location[:2])), footprint) < .9 for p in poles)
                or any(_polygons_intersect(footprint, other) for other in exclusions)):
                continue
            # Both chamber rims must be fully outside every road buffer.
            if any(not _footprint_clear_of_road(g, road, .49)
                   for g in (guard(start - .8, start), guard(end, end + .8)) for road in layout.roads):
                continue
            first['station_end'] = start - .8
            second['station_start'] = end + .8
            for channel in (first, second):
                lo, hi = channel['station_start'], channel['station_end']
                builder = MeshBuilder()
                trough(builder, hi - lo, farm)
                builder.transform(transform(lo, hi))
                temp = builder.object('Culvert channel trim', collection)
                old = channel.data
                channel.data = temp.data
                bpy.data.objects.remove(temp, do_unlink=True)
                if not old.users:
                    bpy.data.meshes.remove(old)
                channel['length'] = hi - lo
                channel['footprint'] = [v for p in guard(lo, hi) for v in p]
            name = f'Culvert / {zone_id}:{edge_index}:{len(links)}'
            builder = MeshBuilder()
            span = end - start
            # Box opening: clear width .56, floor -.60, ceiling -.18.
            builder.box((0, 0, -.66), (span, .8, .12), farm['concrete'])
            builder.box((0, 0, -.12), (span, .8, .12), farm['concrete'])
            for side in (-1, 1):
                builder.box((0, side * .34, -.39), (span, .12, .42), farm['concrete'])
            builder.transform(transform(start, end))
            obj = builder.object(name, collection)
            obj['rural_role'] = 'culvert'
            obj['channel_start'] = first.name
            obj['channel_end'] = second.name
            obj['road_ids'] = ','.join(r.id for r in roads)
            obj['length'] = span
            obj['footprint'] = [v for p in guard(start, end) for v in p]
            for side, lo, hi in ((-1, start - .8, start), (1, end, end + .8)):
                chamber = MeshBuilder()
                chamber.box((0, 0, -.66), (.8, .8, .12), farm['concrete'])
                for lateral in (-1, 1):
                    chamber.box((0, lateral * .34, -.05), (.8, .12, 1.10), farm['concrete'])
                # At the channel end, only close below the open channel floor.
                chamber.box((side * .34, 0, -.22), (.12, .56, .76), farm['concrete'])
                chamber.add([(-.4, -.28, .28), (.4, -.28, .28), (.4, .28, .28), (-.4, .28, .28)],
                            [(0, 1, 2, 3)], farm['water'])
                chamber.transform(transform(lo, hi))
                inlet = chamber.object(name + (' / inlet' if side < 0 else ' / outlet'), collection)
                inlet['rural_role'] = 'culvert_chamber'
                inlet['culvert'] = obj.name
                inlet['footprint'] = [v for p in guard(lo, hi) for v in p]
                openings.append(guard(lo, hi))
            exclusions.append(footprint)
            links.append(obj)
    root['culvert_count'] = len(links)
    root['culvert_length'] = sum(o['length'] for o in links)
    _cut_ground_openings(root, openings)
    return exclusions
