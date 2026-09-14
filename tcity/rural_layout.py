"""Pure-Python planning data for a road-driven rural settlement.

This module deliberately stops at 2D layout data.  It does not import
``bpy`` and it does not create Blender geometry.  The result is an explicit,
editable source plan that the Blender adapter can consume later:

    boundary + roads + land-use zones -> junctions + residential lots

The reference photograph is used for spatial relationships only.  Coordinates
are local metres chosen for composition, not a claim about the real site's
survey or cadastral dimensions.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence


Point = tuple[float, float]
Polygon = tuple[Point, ...]
EPSILON = 1.0e-7
ROAD_KINDS = frozenset({"main", "lane", "farm"})
ZONE_KINDS = frozenset({"residential", "field", "reserved"})


class LayoutError(ValueError):
    """Raised when a source layout cannot be planned safely."""


def _point(value: Sequence[float]) -> Point:
    if len(value) != 2:
        raise LayoutError(f"A point must have two coordinates: {value!r}")
    return (float(value[0]), float(value[1]))


def _polygon(values: Iterable[Sequence[float]]) -> Polygon:
    return tuple(_point(value) for value in values)


def _add(a: Point, b: Point) -> Point:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _scale(vector: Point, amount: float) -> Point:
    return (vector[0] * amount, vector[1] * amount)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _length(vector: Point) -> float:
    return math.hypot(vector[0], vector[1])


def distance(a: Point, b: Point) -> float:
    """Return the Euclidean distance between two 2D points."""

    return _length(_sub(a, b))


def polygon_area(polygon: Polygon) -> float:
    """Return the absolute area of a polygon."""

    return abs(sum(_cross(a, b) for a, b in _edges(polygon)) * 0.5)


def _signed_polygon_area(polygon: Polygon) -> float:
    return sum(_cross(a, b) for a, b in _edges(polygon)) * 0.5


def polygon_centroid(polygon: Polygon) -> Point:
    """Return the area centroid for a non-degenerate polygon."""

    signed_area = _signed_polygon_area(polygon)
    if abs(signed_area) <= EPSILON:
        raise LayoutError("A degenerate polygon has no centroid")
    factor = 1.0 / (6.0 * signed_area)
    x = sum((a[0] + b[0]) * _cross(a, b) for a, b in _edges(polygon))
    y = sum((a[1] + b[1]) * _cross(a, b) for a, b in _edges(polygon))
    return (x * factor, y * factor)


def _edges(points: Sequence[Point]) -> tuple[tuple[Point, Point], ...]:
    if not points:
        return ()
    return tuple(zip(points, points[1:] + points[:1]))


def _polyline_edges(points: Sequence[Point]) -> tuple[tuple[Point, Point], ...]:
    return tuple(zip(points, points[1:]))


def _orientation(a: Point, b: Point, c: Point) -> float:
    return _cross(_sub(b, a), _sub(c, a))


def _point_on_segment(point: Point, a: Point, b: Point, tolerance: float = 1.0e-6) -> bool:
    if abs(_orientation(a, b, point)) > tolerance:
        return False
    return (
        min(a[0], b[0]) - tolerance <= point[0] <= max(a[0], b[0]) + tolerance
        and min(a[1], b[1]) - tolerance <= point[1] <= max(a[1], b[1]) + tolerance
    )


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    ab = _orientation(a, b, c)
    ab2 = _orientation(a, b, d)
    cd = _orientation(c, d, a)
    cd2 = _orientation(c, d, b)
    if ((ab > EPSILON and ab2 < -EPSILON) or (ab < -EPSILON and ab2 > EPSILON)) and (
        (cd > EPSILON and cd2 < -EPSILON) or (cd < -EPSILON and cd2 > EPSILON)
    ):
        return True
    return (
        _point_on_segment(c, a, b)
        or _point_on_segment(d, a, b)
        or _point_on_segment(a, c, d)
        or _point_on_segment(b, c, d)
    )


def _segment_intersection_point(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    """Return one intersection point, including a shared endpoint."""

    if not _segments_intersect(a, b, c, d):
        return None
    denominator = _cross(_sub(b, a), _sub(d, c))
    if abs(denominator) <= EPSILON:
        for point in (a, b, c, d):
            if _point_on_segment(point, a, b) and _point_on_segment(point, c, d):
                return point
        return None
    t = _cross(_sub(c, a), _sub(d, c)) / denominator
    return _add(a, _scale(_sub(b, a), t))


def _point_to_segment_distance(point: Point, a: Point, b: Point) -> float:
    segment = _sub(b, a)
    length_squared = _dot(segment, segment)
    if length_squared <= EPSILON:
        return distance(point, a)
    t = max(0.0, min(1.0, _dot(_sub(point, a), segment) / length_squared))
    return distance(point, _add(a, _scale(segment, t)))


def point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Return true for points inside or on the boundary of ``polygon``."""

    for a, b in _edges(polygon):
        if _point_on_segment(point, a, b):
            return True
    inside = False
    for a, b in _edges(polygon):
        if (a[1] > point[1]) != (b[1] > point[1]):
            x_at_y = (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0]
            if point[0] < x_at_y:
                inside = not inside
    return inside


def _polygon_self_intersects(polygon: Polygon) -> bool:
    edges = _edges(polygon)
    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges):
            if j <= i or j == i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if _segments_intersect(a, b, c, d):
                return True
    return False


def _polygon_inside(inner: Polygon, outer: Polygon) -> bool:
    if not all(point_in_polygon(point, outer) for point in inner):
        return False
    # A concave outer polygon can contain all inner vertices while an inner edge
    # still crosses outside.  Reject proper boundary crossings; shared boundary
    # points are valid for a zone that touches the site edge.
    for a, b in _edges(inner):
        for c, d in _edges(outer):
            intersection = _segment_intersection_point(a, b, c, d)
            if intersection is None:
                continue
            if not (
                _point_on_segment(intersection, a, b)
                and _point_on_segment(intersection, c, d)
                and (
                    distance(intersection, a) <= 1.0e-6
                    or distance(intersection, b) <= 1.0e-6
                    or distance(intersection, c) <= 1.0e-6
                    or distance(intersection, d) <= 1.0e-6
                )
            ):
                return False
    return True


def _polygons_intersect(first: Polygon, second: Polygon) -> bool:
    if any(_segments_intersect(a, b, c, d) for a, b in _edges(first) for c, d in _edges(second)):
        return True
    return point_in_polygon(first[0], second) or point_in_polygon(second[0], first)


def _polyline_length(points: Sequence[Point]) -> float:
    return sum(distance(a, b) for a, b in _polyline_edges(points))


def _polyline_polygon_distance(points: Sequence[Point], polygon: Polygon) -> float:
    if any(point_in_polygon(point, polygon) for point in points):
        return 0.0
    for segment_a, segment_b in _polyline_edges(points):
        for edge_a, edge_b in _edges(polygon):
            if _segments_intersect(segment_a, segment_b, edge_a, edge_b):
                return 0.0
    return min(min(
        _point_to_segment_distance(point, edge_a, edge_b)
        for point in points
        for edge_a, edge_b in _edges(polygon)
    ), min(
        _point_to_segment_distance(point, a, b)
        for point in polygon
        for a, b in _polyline_edges(points)
    ))


@dataclass(frozen=True)
class Road:
    """An editable road centreline in local metres."""

    id: str
    kind: str
    width: float
    points: tuple[Point, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", _polygon(self.points))

    @property
    def length(self) -> float:
        return _polyline_length(self.points)


@dataclass(frozen=True)
class Zone:
    """An explicit land-use polygon."""

    id: str
    kind: str
    polygon: Polygon
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "polygon", _polygon(self.polygon))

    @property
    def area(self) -> float:
        return polygon_area(self.polygon)


@dataclass(frozen=True)
class RuralLayout:
    """Reference-scene source data before Blender geometry is built."""

    name: str
    boundary: Polygon
    roads: tuple[Road, ...]
    zones: tuple[Zone, ...]
    seed: int = 31
    source: str = "estimated reference composition"

    def __post_init__(self) -> None:
        object.__setattr__(self, "boundary", _polygon(self.boundary))
        object.__setattr__(self, "roads", tuple(self.roads))
        object.__setattr__(self, "zones", tuple(self.zones))

    def validate(self, *, require_roles: bool = True) -> None:
        validate_layout(self, require_roles=require_roles)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 1,
            "name": self.name,
            "source": self.source,
            "seed": self.seed,
            "boundary": [list(point) for point in self.boundary],
            "roads": [
                {"id": road.id, "kind": road.kind, "width": road.width, "points": [list(point) for point in road.points]}
                for road in self.roads
            ],
            "zones": [
                {"id": zone.id, "kind": zone.kind, "label": zone.label, "polygon": [list(point) for point in zone.polygon]}
                for zone in self.zones
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "RuralLayout":
        if data.get("schema", 1) != 1:
            raise LayoutError(f"Unsupported rural layout schema: {data.get('schema')!r}")
        roads = tuple(
            Road(
                id=str(item["id"]),
                kind=str(item["kind"]),
                width=float(item["width"]),
                points=_polygon(item["points"]),
            )
            for item in data.get("roads", [])
        )
        zones = tuple(
            Zone(
                id=str(item["id"]),
                kind=str(item["kind"]),
                label=str(item.get("label", "")),
                polygon=_polygon(item["polygon"]),
            )
            for item in data.get("zones", [])
        )
        layout = cls(
            name=str(data.get("name", "Rural reference layout")),
            source=str(data.get("source", "")),
            seed=int(data.get("seed", 31)),
            boundary=_polygon(data["boundary"]),
            roads=roads,
            zones=zones,
        )
        layout.validate()
        return layout


@dataclass(frozen=True)
class Junction:
    point: Point
    road_ids: tuple[str, ...]
    degree: int


@dataclass(frozen=True)
class BuildingLot:
    """A planned, road-connected building footprint.

    ``footprint`` and ``entry`` are local 2D values.  The Blender adapter can
    turn the footprint into a volume and orient an existing asset later.
    """

    id: str
    zone_id: str
    road_id: str
    side: int
    kind: str
    center: Point
    heading: float
    width: float
    depth: float
    footprint: Polygon
    entry: Point


@dataclass(frozen=True)
class LayoutMetrics:
    boundary_area: float
    zone_area: dict[str, float]
    road_length: dict[str, float]
    junction_count: int
    residential_road_ids: tuple[str, ...]


def validate_layout(layout: RuralLayout, *, require_roles: bool = True) -> None:
    """Validate source geometry before it reaches a Blender node graph."""

    errors: list[str] = []
    if len(layout.boundary) < 3:
        errors.append("boundary needs at least three points")
    elif polygon_area(layout.boundary) <= EPSILON:
        errors.append("boundary has zero area")
    elif _polygon_self_intersects(layout.boundary):
        errors.append("boundary self-intersects")

    road_ids: set[str] = set()
    for road in layout.roads:
        if not road.id:
            errors.append("road id is empty")
        if road.id in road_ids:
            errors.append(f"duplicate road id: {road.id}")
        road_ids.add(road.id)
        if road.kind not in ROAD_KINDS:
            errors.append(f"road {road.id!r} has unsupported kind {road.kind!r}")
        if road.width <= 0:
            errors.append(f"road {road.id!r} must have positive width")
        if len(road.points) < 2 or road.length <= EPSILON:
            errors.append(f"road {road.id!r} needs at least two distinct points")
        for index, point in enumerate(road.points):
            if layout.boundary and not point_in_polygon(point, layout.boundary):
                errors.append(f"road {road.id!r} point {index} is outside boundary")
        for a, b in _polyline_edges(road.points):
            midpoint = _scale(_add(a, b), 0.5)
            if layout.boundary and not point_in_polygon(midpoint, layout.boundary):
                errors.append(f"road {road.id!r} leaves boundary between source points")

    zone_ids: set[str] = set()
    for zone in layout.zones:
        if not zone.id:
            errors.append("zone id is empty")
        if zone.id in zone_ids:
            errors.append(f"duplicate zone id: {zone.id}")
        zone_ids.add(zone.id)
        if zone.kind not in ZONE_KINDS:
            errors.append(f"zone {zone.id!r} has unsupported kind {zone.kind!r}")
        if len(zone.polygon) < 3 or zone.area <= EPSILON:
            errors.append(f"zone {zone.id!r} has zero area or too few points")
        elif _polygon_self_intersects(zone.polygon):
            errors.append(f"zone {zone.id!r} self-intersects")
        elif layout.boundary and not _polygon_inside(zone.polygon, layout.boundary):
            errors.append(f"zone {zone.id!r} is outside boundary")

    for index, first in enumerate(layout.zones):
        for second in layout.zones[index + 1 :]:
            if _polygons_intersect(first.polygon, second.polygon):
                errors.append(f"zones {first.id!r} and {second.id!r} overlap")

    if require_roles:
        if not any(zone.kind == "residential" for zone in layout.zones):
            errors.append("layout needs at least one residential zone")
        if not any(zone.kind == "field" for zone in layout.zones):
            errors.append("layout needs at least one field zone")
    if errors:
        raise LayoutError("Invalid rural layout:\n- " + "\n- ".join(errors))


def _cluster_points(points: Iterable[Point], tolerance: float) -> list[list[Point]]:
    clusters: list[list[Point]] = []
    for point in points:
        cluster = next((items for items in clusters if any(distance(point, item) <= tolerance for item in items)), None)
        if cluster is None:
            clusters.append([point])
        else:
            cluster.append(point)
    return clusters


def _cluster_center(points: Sequence[Point]) -> Point:
    return (sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points))


def _road_arms_at(point: Point, road: Road, tolerance: float) -> list[Point]:
    arms: list[Point] = []
    for a, b in _polyline_edges(road.points):
        if not _point_on_segment(point, a, b, tolerance):
            continue
        segment = _sub(b, a)
        length = _length(segment)
        if length <= EPSILON:
            continue
        direction = _scale(segment, 1.0 / length)
        t = _dot(_sub(point, a), segment) / (length * length)
        if t > tolerance:
            arms.append(_scale(direction, -1.0))
        if t < 1.0 - tolerance:
            arms.append(direction)
    return arms


def _unique_directions(directions: Iterable[Point]) -> list[Point]:
    unique: list[Point] = []
    for direction in directions:
        if not any(_dot(direction, existing) > 0.985 for existing in unique):
            unique.append(direction)
    return unique


def find_junctions(layout: RuralLayout, tolerance: float = 0.25) -> tuple[Junction, ...]:
    """Find T/cross junctions from shared endpoints and centreline crossings."""

    candidates: list[Point] = [point for road in layout.roads for point in (road.points[0], road.points[-1])]
    for road_index, first in enumerate(layout.roads):
        for second in layout.roads[road_index + 1 :]:
            for a, b in _polyline_edges(first.points):
                for c, d in _polyline_edges(second.points):
                    point = _segment_intersection_point(a, b, c, d)
                    if point is not None:
                        candidates.append(point)

    junctions: list[Junction] = []
    for cluster in _cluster_points(candidates, tolerance):
        point = _cluster_center(cluster)
        arms = _unique_directions(
            direction
            for road in layout.roads
            for direction in _road_arms_at(point, road, tolerance)
        )
        if len(arms) < 3:
            continue
        road_ids = tuple(sorted(road.id for road in layout.roads if _road_arms_at(point, road, tolerance)))
        junctions.append(Junction(point=point, road_ids=road_ids, degree=len(arms)))
    junctions.sort(key=lambda junction: (junction.point[0], junction.point[1]))
    return tuple(junctions)


def roads_near_zone(layout: RuralLayout, zone: Zone, clearance: float = 0.5) -> tuple[Road, ...]:
    """Return roads that touch or run within ``clearance`` of a zone."""

    return tuple(
        road for road in layout.roads if _polyline_polygon_distance(road.points, zone.polygon) <= clearance
    )


def layout_metrics(layout: RuralLayout) -> LayoutMetrics:
    layout.validate()
    residential_road_ids: list[str] = []
    for zone in layout.zones:
        if zone.kind != "residential":
            continue
        for road in roads_near_zone(layout, zone, clearance=0.5):
            if road.id not in residential_road_ids:
                residential_road_ids.append(road.id)
    return LayoutMetrics(
        boundary_area=polygon_area(layout.boundary),
        zone_area={zone.id: zone.area for zone in layout.zones},
        road_length={road.id: road.length for road in layout.roads},
        junction_count=len(find_junctions(layout)),
        residential_road_ids=tuple(residential_road_ids),
    )


def _oriented_rectangle(center: Point, tangent: Point, width: float, depth: float) -> Polygon:
    normal = (-tangent[1], tangent[0])
    half_width = width * 0.5
    half_depth = depth * 0.5
    along = _scale(tangent, half_width)
    across = _scale(normal, half_depth)
    return (
        _add(_sub(center, along), _scale(across, -1.0)),
        _add(_add(center, along), _scale(across, -1.0)),
        _add(_add(center, along), across),
        _add(_sub(center, along), across),
    )


def _normalised(vector: Point) -> Point:
    length = _length(vector)
    if length <= EPSILON:
        raise LayoutError("Cannot normalise a zero-length vector")
    return _scale(vector, 1.0 / length)


def _point_to_polyline_distance(point: Point, points: Sequence[Point]) -> float:
    return min(_point_to_segment_distance(point, a, b) for a, b in _polyline_edges(points))


def _footprint_clear_of_road(footprint: Polygon, road: Road, setback: float) -> bool:
    # Checking corners alone misses roads crossing through the footprint.
    minimum = road.width * 0.5 + setback
    return _polyline_polygon_distance(road.points, footprint) >= minimum - 1.0e-5


def _lot_kind(seed: int, zone_id: str, road_id: str, index: int) -> str:
    rng = random.Random(f"{seed}:{zone_id}:{road_id}:{index}")
    value = rng.random()
    if value < 0.20:
        return "farmhouse"
    if value < 0.36:
        return "shed_home"
    return "house"


def plan_building_lots(
    layout: RuralLayout,
    *,
    frontage: float = 10.0,
    depth: float = 13.0,
    setback: float = 2.0,
    spacing: float = 2.0,
    variation: float = 0.3,
    road_kinds: Iterable[str] = ("main", "lane"),
    max_lots: int | None = None,
) -> tuple[BuildingLot, ...]:
    """Place deterministic, road-connected building footprints in residential zones.

    This is intentionally a conservative planner.  A candidate is accepted only
    when the whole footprint fits inside a residential zone, stays clear of
    every road, and does not overlap a previously accepted footprint. Lanes
    receive lots first, so large main-road lots cannot block the village lanes.
    Seeded width, depth and spacing variation creates smaller groups. It gives
    the later Blender layer reliable inputs instead of asking Geometry Nodes to
    infer a house location from the nearest road through a field.
    """

    layout.validate()
    if frontage <= 0 or depth <= 0 or spacing < 0 or setback < 0:
        raise LayoutError("frontage and depth must be positive; spacing and setback cannot be negative")
    if not 0 <= variation <= 0.5:
        raise LayoutError("variation must be between zero and 0.5")
    if max_lots is not None and (not isinstance(max_lots, int) or max_lots < 0):
        raise LayoutError("max_lots must be a non-negative integer or None")
    if max_lots == 0:
        return ()
    allowed_kinds = frozenset(road_kinds)
    unknown_kinds = allowed_kinds - ROAD_KINDS
    if unknown_kinds:
        raise LayoutError(f"Unsupported road kinds for lot planning: {sorted(unknown_kinds)}")

    residential_zones = [zone for zone in layout.zones if zone.kind == "residential"]
    roads = [road for road in layout.roads if road.kind in allowed_kinds]
    lots: list[BuildingLot] = []
    frontage_clearance = depth * (1 + variation) + max((road.width for road in roads), default=0.0) + setback
    for zone in residential_zones:
        nearby = roads_near_zone(layout, zone, clearance=frontage_clearance)
        for road in sorted(nearby, key=lambda item: (item.kind != 'lane', item.id)):
            if road not in roads:
                continue
            for segment_index, (a, b) in enumerate(_polyline_edges(road.points)):
                segment = _sub(b, a)
                segment_length = _length(segment)
                if segment_length <= EPSILON:
                    continue
                tangent = _normalised(segment)
                left_normal = (-tangent[1], tangent[0])
                for side in (-1, 1):
                    rng = random.Random(f'{layout.seed}:{zone.id}:{road.id}:{segment_index}:{side}')
                    cursor = spacing * .5
                    candidate_index = 0
                    while cursor < segment_length:
                        width = frontage * rng.uniform(1 - variation, 1 + variation)
                        lot_depth = depth * rng.uniform(1 - variation, 1 + variation)
                        distance_along = cursor + width * .5
                        if cursor + width > segment_length:
                            break
                        cursor += width + spacing * rng.uniform(1, 1 + 4 * variation)
                        candidate_index += 1
                        road_point = _add(a, _scale(tangent, distance_along))
                        normal = _scale(left_normal, float(side))
                        center_offset = road.width * 0.5 + setback + lot_depth * 0.5
                        center = _add(road_point, _scale(normal, center_offset))
                        footprint = _oriented_rectangle(center, tangent, width, lot_depth)
                        if not _polygon_inside(footprint, zone.polygon):
                            continue
                        if any(not _footprint_clear_of_road(footprint, other, setback) for other in layout.roads):
                            continue
                        if any(_polygons_intersect(footprint, existing.footprint) for existing in lots):
                            continue
                        entry = _add(road_point, _scale(normal, road.width * 0.5 + setback))
                        lot_id = f"{zone.id}:{road.id}:{segment_index}:{side}:{candidate_index:04d}"
                        lots.append(
                            BuildingLot(
                                id=lot_id,
                                zone_id=zone.id,
                                road_id=road.id,
                                side=side,
                                kind=_lot_kind(layout.seed, zone.id, lot_id, candidate_index),
                                center=center,
                                heading=math.atan2(tangent[1], tangent[0]),
                                width=width,
                                depth=lot_depth,
                                footprint=footprint,
                                entry=entry,
                            )
                        )
                        if max_lots is not None and len(lots) >= max_lots:
                            return tuple(lots)
    return tuple(lots)


@dataclass(frozen=True)
class BuildingVolume:
    role: str
    footprint: Polygon
    height: float


@dataclass(frozen=True)
class HousingPlan:
    lot_id: str
    buildings: tuple[BuildingVolume, ...]
    yard: Polygon
    access: Polygon
    driveway: Polygon
    gate: Point
    door: Point
    road_entry: Point


def convex_polygons_overlap(first: Polygon, second: Polygon) -> bool:
    """Positive-area overlap using separating axes; shared edges are allowed."""
    for polygon in (first, second):
        for a, b in _edges(polygon):
            edge = _sub(b, a)
            if _length(edge) <= EPSILON:
                continue
            axis = _normalised((-edge[1], edge[0]))
            first_projection = [_dot(p, axis) for p in first]
            second_projection = [_dot(p, axis) for p in second]
            if min(max(first_projection), max(second_projection)) <= max(
                min(first_projection), min(second_projection)
            ) + EPSILON:
                return False
    return True


def plan_housing(layout: RuralLayout, lots: Sequence[BuildingLot] | None = None,
                 *, wing_mix: float = .65, access_width: float = 2.) -> tuple[HousingPlan, ...]:
    """Partition reserved lot envelopes into rear homes, side wings and yards.

    The wing shares the main home's front wall without overlapping its volume.
    A pedestrian corridor runs through the yard to that wall, with a separate
    driveway crossing the setback to the source road's edge. Geometry is a
    rebuild-time plan; all footprints are convex and counterclockwise.
    """
    layout.validate()
    if not 0 <= wing_mix <= 1 or not math.isfinite(access_width) or access_width <= 0:
        raise LayoutError('wing_mix must be between zero and one; access_width must be positive')
    lots = tuple(plan_building_lots(layout) if lots is None else lots)
    roads = {road.id: road for road in layout.roads}
    zones = {zone.id: zone for zone in layout.zones}
    plans = []
    for lot in lots:
        if lot.width <= access_width or lot.depth <= 0:
            raise LayoutError(f'Lot cannot fit the entrance corridor: {lot.id}')
        tangent = (math.cos(lot.heading), math.sin(lot.heading))
        inward = _scale((-tangent[1], tangent[0]), lot.side)

        def point(x, y):
            return _add(lot.entry, _add(_scale(tangent, x), _scale(inward, y)))

        def rectangle(left, right, front, back):
            polygon = (point(left, front), point(right, front), point(right, back), point(left, back))
            return polygon if _signed_polygon_area(polygon) > 0 else tuple(reversed(polygon))

        rng = random.Random(f'{layout.seed}:housing:{lot.id}')
        use_wing = rng.random() < wing_mix and lot.width >= access_width + 3.5 and lot.depth >= 9
        wing_left = rng.random() < .5
        yard_depth = lot.depth * rng.uniform(.30, .40)
        wing_width = max(2.6, lot.width * rng.uniform(.28, .36)) if use_wing else 0.
        half = lot.width * .5
        main = rectangle(-half, half, yard_depth, lot.depth)
        height = {'house': rng.choice((6.6, 9.9)), 'farmhouse': rng.choice((3.3, 6.6)),
                  'shed_home': 3.6}[lot.kind]
        volumes = [BuildingVolume('main', main, height)]
        yard_left, yard_right = -half, half
        if use_wing:
            if wing_left:
                wing = rectangle(-half, -half + wing_width, 0, yard_depth)
                yard_left += wing_width
            else:
                wing = rectangle(half - wing_width, half, 0, yard_depth)
                yard_right -= wing_width
            volumes.append(BuildingVolume('side_wing', wing, min(3.3, height * .75)))
        yard = rectangle(yard_left, yard_right, 0, yard_depth)
        entrance_x = (yard_left + yard_right) * .5
        gate, door = point(entrance_x, 0), point(entrance_x, yard_depth)
        access = rectangle(entrance_x - access_width / 2, entrance_x + access_width / 2, 0, yard_depth)
        road = roads[lot.road_id]
        projections = []
        for a, b in _polyline_edges(road.points):
            segment = _sub(b, a)
            squared = _dot(segment, segment)
            if squared > EPSILON:
                t = max(0., min(1., _dot(_sub(gate, a), segment) / squared))
                projections.append(_add(a, _scale(segment, t)))
        nearest = min(projections, key=lambda p: distance(p, gate))
        road_entry = _add(nearest, _scale(_normalised(_sub(gate, nearest)), road.width / 2))
        across = _scale(tangent, access_width / 2)
        driveway = (_sub(road_entry, across), _add(road_entry, across), _add(gate, across), _sub(gate, across))
        if _signed_polygon_area(driveway) < 0:
            driveway = tuple(reversed(driveway))
        if polygon_area(driveway) <= EPSILON:
            driveway = ()
        if not all(_polygon_inside(v.footprint, lot.footprint) for v in volumes):
            raise LayoutError(f'Housing leaves its lot envelope: {lot.id}')
        zone = zones[lot.zone_id]
        if zone.kind != 'residential' or not _polygon_inside(lot.footprint, zone.polygon):
            raise LayoutError(f'Housing needs a residential lot: {lot.id}')
        if any(not _footprint_clear_of_road(v.footprint, other, 0)
               for v in volumes for other in layout.roads):
            raise LayoutError(f'Housing crosses a road: {lot.id}')
        if not _polygon_inside(access, yard):
            raise LayoutError(f'Entrance corridor does not fit the yard: {lot.id}')
        # The connector may leave the residential zone to reach its bordering
        # road, but must not cross fields, reserved land or the site boundary.
        if driveway and (not _polygon_inside(driveway, layout.boundary) or any(
            _polygons_intersect(driveway, zone.polygon)
            for zone in zones.values() if zone.kind != 'residential'
        )):
            raise LayoutError(f'Entrance connector crosses unavailable land: {lot.id}')
        plans.append(HousingPlan(lot.id, tuple(volumes), yard, access, driveway, gate, door, road_entry))
    buildings = [volume.footprint for plan in plans for volume in plan.buildings]
    if any(convex_polygons_overlap(first, second)
           for index, first in enumerate(buildings) for second in buildings[index + 1:]):
        raise LayoutError('Housing volumes overlap')
    for plan in plans:
        if any(convex_polygons_overlap(corridor, footprint)
               for corridor in (plan.access, plan.driveway) if corridor for footprint in buildings):
            raise LayoutError(f'Entrance corridor is blocked: {plan.lot_id}')
    return tuple(plans)


@dataclass(frozen=True)
class FieldParcel:
    id: str
    zone_id: str
    polygon: Polygon
    tone: int


def _clip_half_plane(polygon: Polygon, axis: int, bound: float, keep_above: bool) -> Polygon:
    """Clip a convex polygon against one axis-aligned boundary."""
    result = []
    for a, b in _edges(polygon):
        a_inside = a[axis] >= bound if keep_above else a[axis] <= bound
        b_inside = b[axis] >= bound if keep_above else b[axis] <= bound
        if a_inside:
            result.append(a)
        if a_inside != b_inside:
            t = (bound - a[axis]) / (b[axis] - a[axis])
            result.append(_add(a, _scale(_sub(b, a), t)))
    clean = []
    for point in result:
        if not clean or distance(point, clean[-1]) > EPSILON:
            clean.append(point)
    if len(clean) > 1 and distance(clean[0], clean[-1]) <= EPSILON:
        clean.pop()
    return tuple(clean)


def plan_field_parcels(layout: RuralLayout, *, width: float = 28., length: float = 48.,
                       gap: float = 1.) -> tuple[FieldParcel, ...]:
    """Clip varied rectangular field strips to convex source zones.

    Gaps expose the zone plane as bunds. Roads are still preview overlays; this
    stage does not perform a road-buffer difference or generate crops.
    """
    layout.validate()
    if width <= 0 or length <= 0 or gap < 0 or gap >= min(width, length) * .75:
        raise LayoutError('Field dimensions must be positive and gap smaller than 75% of either dimension')
    parcels = []
    for zone in layout.zones:
        if zone.kind != 'field':
            continue
        signs = [_orientation(zone.polygon[i - 1], p, zone.polygon[(i + 1) % len(zone.polygon)])
                 for i, p in enumerate(zone.polygon)]
        if any(s > EPSILON for s in signs) and any(s < -EPSILON for s in signs):
            raise LayoutError(f'Field subdivision needs a convex zone: {zone.id}')
        rng = random.Random(f'{layout.seed}:field:{zone.id}')
        limits = []
        for axis, size in enumerate((width, length)):
            low = min(p[axis] for p in zone.polygon)
            high = max(p[axis] for p in zone.polygon)
            # Divide the full extent so the final row never becomes a sliver.
            count = max(1, round((high - low) / size))
            weights = [rng.uniform(.85, 1.15) for _ in range(count)]
            scale = (high - low) / sum(weights)
            cuts = [low]
            for weight in weights:
                cuts.append(cuts[-1] + weight * scale)
            cuts[-1] = high
            limits.append(cuts)
        for ix, (left, right) in enumerate(zip(limits[0], limits[0][1:])):
            for iy, (bottom, top) in enumerate(zip(limits[1], limits[1][1:])):
                polygon = zone.polygon
                for axis, bound, above in ((0, left + gap / 2, True), (0, right - gap / 2, False),
                                           (1, bottom + gap / 2, True), (1, top - gap / 2, False)):
                    polygon = _clip_half_plane(polygon, axis, bound, above)
                if len(polygon) >= 3 and polygon_area(polygon) > EPSILON:
                    parcels.append(FieldParcel(f'{zone.id}:{ix}:{iy}', zone.id, polygon, rng.randrange(5)))
    return tuple(parcels)


def reference_layout() -> RuralLayout:
    """Return an editable composition based on the supplied aerial reference."""

    layout = RuralLayout(
        name="Taiwan rural settlement reference",
        source="Screenshot from 2026-09-13 20-26-34.png; estimated local composition",
        seed=31,
        boundary=(
            (-180.0, -130.0),
            (180.0, -130.0),
            (180.0, 130.0),
            (-180.0, 130.0),
        ),
        roads=(
            Road(
                "main_outer_southwest",
                "main",
                8.0,
                (
                    (-168.0, 103.0),
                    (-166.0, 65.0),
                    (-139.0, 22.0),
                    (-137.0, -25.0),
                    (-106.0, -55.0),
                    (-61.0, -69.0),
                    (-8.0, -81.0),
                    (48.0, -97.0),
                    (94.0, -124.0),
                ),
            ),
            Road(
                "main_outer_north",
                "main",
                8.0,
                ((-168.0, 103.0), (-100.0, 105.0), (-22.0, 108.0), (60.0, 107.0), (170.0, 104.0)),
            ),
            Road(
                "village_spine",
                "main",
                6.0,
                ((-139.0, 22.0), (-132.0, 8.0), (-94.0, 17.0), (-54.0, 29.0), (-15.0, 43.0), (25.0, 54.0), (65.0, 66.0), (98.0, 77.0), (130.0, 90.0), (170.0, 104.0)),
            ),
            Road("lane_west", "lane", 4.5, ((-104.0, -25.0), (-108.0, 11.0), (-111.0, 43.0), (-77.0, 76.0))),
            Road("lane_middle", "lane", 4.5, ((-57.0, -30.0), (-44.0, 0.0), (-47.0, 27.0), (-42.0, 58.0), (-12.0, 84.0))),
            Road("lane_east", "lane", 4.5, ((25.0, 54.0), (34.0, 29.0), (67.0, 12.0), (84.0, -33.0), (94.0, -70.0), (94.0, -124.0))),
            Road("lane_northwest", "lane", 4.5, ((-132.0, 8.0), (-122.0, 29.0), (-126.0, 64.0), (-96.0, 88.0))),
            Road("lane_south", "lane", 4.5, ((-137.0, -25.0), (-104.0, -25.0), (-57.0, -30.0), (-10.0, -22.0), (28.0, -9.0), (34.0, 29.0))),
            Road("farm_south", "farm", 3.5, ((-158.0, -111.0), (-77.0, -113.0), (8.0, -109.0), (91.0, -95.0), (169.0, -65.0))),
            Road("farm_east", "farm", 3.5, ((127.0, -47.0), (127.0, 2.0), (130.0, 54.0), (130.0, 90.0))),
        ),
        zones=(
            Zone(
                "village_core",
                "residential",
                (
                    (-137.0, -20.0),
                    (-104.0, -43.0),
                    (-37.0, -52.0),
                    (37.0, -43.0),
                    (101.0, -4.0),
                    (96.0, 58.0),
                    (43.0, 94.0),
                    (-40.0, 91.0),
                    (-111.0, 61.0),
                    (-137.0, 25.0),
                ),
                "dense but irregular roadside village cluster",
            ),
            Zone("field_southwest", "field", ((-176.0, -124.0), (-83.0, -124.0), (-97.0, -53.0), (-164.0, -39.0)), "large outer field"),
            Zone("field_south", "field", ((-72.0, -124.0), (87.0, -124.0), (72.0, -67.0), (-37.0, -55.0)), "long rectangular fields"),
            Zone("field_east", "field", ((105.0, -33.0), (176.0, -48.0), (176.0, 83.0), (111.0, 72.0), (106.0, 24.0)), "east fields"),
            Zone("field_north", "field", ((-174.0, 112.0), (174.0, 112.0), (174.0, 124.0), (-174.0, 124.0)), "far northern fields"),
            Zone("reserved_west_water", "reserved", ((-176.0, -30.0), (-150.0, -33.0), (-141.0, 10.0), (-174.0, 14.0)), "canal or unclear reserve"),
        ),
    )
    layout.validate()
    return layout


def save_layout(layout: RuralLayout, path: str | Path) -> None:
    layout.validate()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(layout.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_layout(path: str | Path) -> RuralLayout:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise LayoutError("Rural layout JSON must contain an object")
    return RuralLayout.from_dict(data)
