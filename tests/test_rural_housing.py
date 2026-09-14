"""Pure Python checks for yard partitions and road-to-door access."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('rural_housing_test', ROOT / 'tcity/rural_layout.py')
RURAL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RURAL
SPEC.loader.exec_module(RURAL)


def run():
    layout = RURAL.reference_layout()
    lots = RURAL.plan_building_lots(layout)
    plans = RURAL.plan_housing(layout, lots)
    assert plans == RURAL.plan_housing(layout, lots)
    assert len(plans) == len(lots)
    wings = {p.lot_id for p in plans if len(p.buildings) == 2}
    assert 0 < len(wings) < len(plans)
    assert not any(len(p.buildings) > 1 for p in RURAL.plan_housing(layout, lots, wing_mix=0))
    assert wings <= {p.lot_id for p in RURAL.plan_housing(layout, lots, wing_mix=1) if len(p.buildings) == 2}
    roads = {road.id: road for road in layout.roads}
    for lot, plan in zip(lots, plans):
        pieces = [v.footprint for v in plan.buildings] + [plan.yard]
        assert abs(sum(RURAL.polygon_area(p) for p in pieces) - RURAL.polygon_area(lot.footprint)) < 1e-6
        assert all(RURAL._polygon_inside(p, lot.footprint) for p in pieces)
        assert all(RURAL._signed_polygon_area(p) > 0 for p in pieces)
        for index, first in enumerate(pieces):
            assert not any(RURAL.convex_polygons_overlap(first, second) for second in pieces[index + 1:])
        assert RURAL._polygon_inside(plan.access, plan.yard)
        assert RURAL.point_in_polygon(plan.gate, plan.access)
        assert RURAL.point_in_polygon(plan.door, plan.access)
        assert any(RURAL._point_on_segment(plan.door, a, b) for a, b in RURAL._edges(plan.buildings[0].footprint))
        assert abs(RURAL.polygon_area(plan.access) / RURAL.distance(plan.gate, plan.door) - 2) < 1e-6
        assert RURAL.point_in_polygon(plan.gate, plan.driveway)
        assert RURAL.point_in_polygon(plan.road_entry, plan.driveway)
        assert abs(RURAL._point_to_polyline_distance(plan.road_entry, roads[lot.road_id].points) - roads[lot.road_id].width / 2) < 1e-6
        if len(plan.buildings) == 2:
            main, wing = plan.buildings
            assert wing.height < main.height
            # A side wing must actually adjoin the main home's front wall.
            assert sum(RURAL.point_in_polygon(p, main.footprint) for p in wing.footprint) == 2
    assert {lot.side for lot in lots if lot.id in wings} == {-1, 1}
    assert RURAL.plan_housing(replace(layout, seed=99), lots) != plans

    # A narrow lot retains its front yard and corridor but cannot accept a wing.
    narrow = RURAL.plan_building_lots(layout, frontage=3.5, depth=6, variation=0, max_lots=1)
    assert narrow
    assert len(RURAL.plan_housing(layout, narrow, wing_mix=1)[0].buildings) == 1
    flush = RURAL.plan_building_lots(layout, setback=0, max_lots=1)
    assert not RURAL.plan_housing(layout, flush)[0].driveway
    try:
        RURAL.plan_housing(layout, narrow, access_width=4)
    except RURAL.LayoutError:
        pass
    else:
        raise AssertionError('An entrance wider than its lot must be rejected')

    blocked = RURAL.RuralLayout(
        name='field across entrance', boundary=((-50, -50), (50, -50), (50, 50), (-50, 50)),
        roads=(RURAL.Road('road', 'lane', 4, ((-30, 0), (30, 0))),),
        zones=(RURAL.Zone('home', 'residential', ((-20, 4), (20, 4), (20, 30), (-20, 30))),
               RURAL.Zone('field', 'field', ((-25, 2.5), (25, 2.5), (25, 3.5), (-25, 3.5)))),
    )
    assert RURAL.plan_building_lots(blocked)
    try:
        RURAL.plan_housing(blocked)
    except RURAL.LayoutError as error:
        assert 'unavailable land' in str(error)
    else:
        raise AssertionError('A house must not access the road through a field')
    print('RURAL_HOUSING_PASS', {'homes': len(plans), 'side_wings': len(wings), 'clear_entrances': len(plans)})


if __name__ == '__main__':
    run()
