"""Pure-Python checks for the road-driven rural layout planner.

This test intentionally does not start Blender.  It covers the editable source
plan and the 2D planning contract that a later Blender adapter will consume.
"""

import importlib.util
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tcity_rural_layout_test", ROOT / "tcity" / "rural_layout.py")
RURAL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RURAL
SPEC.loader.exec_module(RURAL)


def run():
    layout = RURAL.reference_layout()
    source_layout = RURAL.load_layout(ROOT / "docs" / "rural_reference_layout.json")
    assert source_layout.to_dict() == layout.to_dict()
    metrics = RURAL.layout_metrics(layout)
    assert metrics.boundary_area == 93600.0
    assert {road.kind for road in layout.roads} == {"main", "lane", "farm"}
    assert {zone.kind for zone in layout.zones} == {"residential", "field", "reserved"}
    for index, first in enumerate(layout.zones):
        for second in layout.zones[index + 1 :]:
            assert not RURAL._polygons_intersect(first.polygon, second.polygon)

    junctions = RURAL.find_junctions(layout)
    assert len(junctions) >= 2
    assert all(junction.degree >= 3 for junction in junctions)
    assert "village_spine" in metrics.residential_road_ids
    assert "farm_south" not in metrics.residential_road_ids
    # Every source road must connect to the external road network, including
    # mid-segment crossings rather than only coincident endpoints.
    connected = {layout.roads[0].id}
    while True:
        expanded = connected | {
            road.id for road in layout.roads
            if any(other.id in connected and any(
                RURAL._segments_intersect(a, b, c, d)
                for a, b in RURAL._polyline_edges(road.points)
                for c, d in RURAL._polyline_edges(other.points)
            ) for other in layout.roads)
        }
        if expanded == connected:
            break
        connected = expanded
    assert connected == {road.id for road in layout.roads}

    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "reference.json"
        RURAL.save_layout(layout, path)
        restored = RURAL.load_layout(path)
    assert restored.to_dict() == layout.to_dict()

    invalid = RURAL.RuralLayout(
        name="invalid",
        boundary=((0, 0), (10, 0), (10, 10), (0, 10)),
        roads=(RURAL.Road("outside", "lane", 4, ((2, 2), (12, 2))),),
        zones=(RURAL.Zone("home", "residential", ((1, 1), (4, 1), (4, 4), (1, 4))),),
    )
    try:
        invalid.validate()
    except RURAL.LayoutError:
        pass
    else:
        raise AssertionError("an out-of-bound road must be rejected")

    lots = RURAL.plan_building_lots(layout)
    assert len(lots) >= 45, len(lots)
    assert {lot.side for lot in lots} == {-1, 1}
    assert len({lot.id for lot in lots}) == len(lots)
    assert {lot.road_id for lot in lots} >= {"village_spine", "lane_west", "lane_south", "lane_middle", "lane_east"}
    assert sum(lot.center[1] < 0 for lot in lots) >= 10
    assert len({round(lot.width, 1) for lot in lots}) > 10
    residential = next(zone for zone in layout.zones if zone.kind == "residential")
    roads = {road.id: road for road in layout.roads}
    for lot in lots:
        assert lot.zone_id == residential.id
        assert RURAL._polygon_inside(lot.footprint, residential.polygon)
        assert RURAL._point_to_polyline_distance(lot.entry, roads[lot.road_id].points) <= roads[lot.road_id].width / 2 + 2.001
        for road in layout.roads:
            assert RURAL._footprint_clear_of_road(lot.footprint, road, 2), (lot.id, road.id)

    for index, first in enumerate(lots):
        for second in lots[index + 1 :]:
            assert not RURAL._polygons_intersect(first.footprint, second.footprint)
    assert lots == RURAL.plan_building_lots(layout)
    assert RURAL.plan_building_lots(layout, max_lots=0) == ()
    assert RURAL.plan_building_lots(layout, max_lots=3) == lots[:3]
    # A crossing road must be rejected even when every corner is far away.
    square = ((-10, -10), (10, -10), (10, 10), (-10, 10))
    crossing = RURAL.Road('crossing', 'lane', 2, ((-20, 0), (20, 0)))
    assert not RURAL._footprint_clear_of_road(square, crossing, 0)
    # Closest approach can be inside a long segment, far from road endpoints.
    parallel = RURAL.Road('parallel', 'lane', 2, ((-100, 12), (100, 12)))
    assert abs(RURAL._polyline_polygon_distance(parallel.points, square) - 2) < 1e-6
    assert not RURAL._footprint_clear_of_road(square, parallel, 2)

    parcels = RURAL.plan_field_parcels(layout)
    assert len(parcels) >= 25
    assert parcels == RURAL.plan_field_parcels(layout)
    fields = {zone.id: zone for zone in layout.zones if zone.kind == 'field'}
    assert {parcel.zone_id for parcel in parcels} == set(fields)
    for parcel in parcels:
        assert RURAL._polygon_inside(parcel.polygon, fields[parcel.zone_id].polygon)
        assert RURAL.polygon_area(parcel.polygon) > 0
    for index, first in enumerate(parcels):
        for second in parcels[index + 1:]:
            assert not RURAL._polygons_intersect(first.polygon, second.polygon)
    # With bund gaps disabled, subdivision must conserve each source area's size.
    filled = RURAL.plan_field_parcels(layout, gap=0)
    for zone in fields.values():
        total = sum(RURAL.polygon_area(p.polygon) for p in filled if p.zone_id == zone.id)
        assert abs(total - zone.area) < 1e-6, (zone.id, total, zone.area)
    concave = RURAL.RuralLayout(
        name='concave field', boundary=((0, 0), (100, 0), (100, 100), (0, 100)),
        roads=(), zones=(
            RURAL.Zone('home', 'residential', ((70, 70), (90, 70), (90, 90), (70, 90))),
            RURAL.Zone('field', 'field', ((5, 5), (55, 5), (55, 20), (20, 20), (20, 55), (5, 55))),
        ))
    try:
        RURAL.plan_field_parcels(concave)
    except RURAL.LayoutError as error:
        assert 'convex' in str(error)
    else:
        raise AssertionError('Concave fields must not silently produce bridged polygons')
    changed = RURAL.RuralLayout(
        name=layout.name,
        source=layout.source,
        seed=99,
        boundary=layout.boundary,
        roads=layout.roads,
        zones=layout.zones,
    )
    assert [lot.kind for lot in lots] != [lot.kind for lot in RURAL.plan_building_lots(changed)]
    print("RURAL_LAYOUT_PASS", {"junctions": len(junctions), "lots": len(lots), "roads": len(layout.roads), "fields": len(parcels)})


if __name__ == "__main__":
    run()
