"""Evaluate village land use, road-facing footprints and live controls."""
import json
import sys
from pathlib import Path
from collections import Counter
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import tcity
from tcity.farmland import make_farmland,farmland_modifier,PRESETS
from tcity.nodes import set_control,get_control
from test_farmland import evaluate,coverage


def run():
    tcity.register();obj=make_farmland(width=360,depth=260);mod=farmland_modifier(obj)
    for key,value in PRESETS['VILLAGE'].items():set_control(mod,key,value)
    set_control(mod,'Crops',False);set_control(mod,'Trees',False)
    verts,polys,layers,instances,digest=evaluate(obj)
    homes=[(o,m) for o,m in instances if o.get('tc_farm_asset') in (12,13,14)]
    assert len(homes)>=6,len(homes)
    assert not list(mod.node_warnings),list(mod.node_warnings)
    road=BVHTree.FromPolygons(verts,[ids for ids,n,c,a in polys if layers[ids[0]]==12 and n.z>.9],all_triangles=True)
    for source,matrix in homes:
        nearest=road.find_nearest(matrix.translation)[0]
        direction=nearest-matrix.translation;direction.z=0
        forward=matrix.to_3x3()@Vector((0,-1,0))
        assert direction.normalized().dot(forward.normalized())>.999
        assert all(Vector((v.co.x,v.co.y)).length<16. for v in source.data.vertices)
    for i,(_,a) in enumerate(homes):
        for _,b in homes[i+1:]:assert (a.translation-b.translation).length>24.96
    assert evaluate(obj)[-1]==digest
    set_control(mod,'Seed',32);assert evaluate(obj)[-1]!=digest
    set_control(mod,'Seed',31)
    set_control(mod,'Field Angle',17.)
    inside=lambda x,y:-180.002<=x<=180.002 and -130.002<=y<=130.002 and (x<=154.002 or y<=108.002 or (x-154)*22+(y-108)*26<=26*22+.03)
    coverage(obj,inside)
    set_control(mod,'Structures',False)
    assert not any(o.get('tc_farm_asset') in (4,5,6,8,9,12,13,14) for o,m in evaluate(obj)[3])
    set_control(mod,'Structures',True);set_control(mod,'Village Mix',0.)
    assert not any(o.get('tc_farm_asset') in (12,13,14) for o,m in evaluate(obj)[3])
    set_control(mod,'Village Mix',1.);set_control(mod,'Farm Roads',False)
    assert not any(o.get('tc_farm_asset') in (12,13,14) for o,m in evaluate(obj)[3])
    for name in ('PADDY','MIXED','FRINGE'):
        assert bpy.ops.tcity.farmland_preset(preset=name)=={'FINISHED'}
        assert get_control(mod,'Village Mix')==0.
    report={'blender':bpy.app.version_string,'result':'PASS','compounds':len(homes),
            'variants':dict(Counter(o.name for o,m in homes)),
            'checks':['road facing','radius','rotated boundary','deterministic seed','switches','preset reset']}
    (ROOT/'dist').mkdir(exist_ok=True)
    (ROOT/'dist/village_test_results.json').write_text(json.dumps(report,indent=2))
    print('VILLAGE_PASS',report,flush=True)


if __name__=='__main__':run()
