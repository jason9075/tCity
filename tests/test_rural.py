"""Rural second-round tests: source identity, actual wire anchors, woods and upgrade."""
import json
import sys
from pathlib import Path
from collections import Counter
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import tcity
from tcity.farmland import make_farmland,farmland_modifier,GROUP_NAME,SOCKETS
from tcity.nodes import set_control,get_control
from test_farmland import evaluate,coverage
results=[]
def record(name,detail):
    results.append({'test':name,'result':'PASS','detail':detail});print('PASS',name,detail,flush=True)

def anchors(obj):
    v,p,l,instances,_=evaluate(obj)
    points=[x for x,k in zip(v,l) if k==15];assert points
    kd=KDTree(len(points))
    for i,x in enumerate(points):kd.insert(x,i)
    kd.balance();count=0;maximum=0
    for source,m in instances:
        if source.get('tc_infra_kind')!='Pole':continue
        for y,z in [(-.38,8.66),(0,8.66),(.38,8.66),(-.27,6.18)]:
            a=m@Vector((0,y,z));_,_,distance=kd.find(a);maximum=max(maximum,distance)
            assert distance<.035,(tuple(a),distance)
            count+=1
    assert count>=8
    return count,round(maximum,5)

def run():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);tcity.register()
    obj=make_farmland(width=210,depth=160);mod=farmland_modifier(obj)
    for key,value in {'Plot Width':30.,'Plot Length':38.,'Structure Mix':.6,'Woodland Mix':.65,'Crops':False}.items():set_control(mod,key,value)
    v,p,l,inst,d=evaluate(obj)
    counts=Counter(o.get('tc_farm_asset',-1) for o,m in inst)
    assert 8 in counts and 9 in counts and 6 in counts,counts
    assert counts[10]+counts[11]>10,counts
    record('rural_homes_and_woodland',dict(counts))
    record('supported_wires',anchors(obj))
    set_control(mod,'Pole Spacing',15.);set_control(mod,'Cable Sag',.9)
    record('live_span_spacing_and_sag',anchors(obj))
    set_control(mod,'Utility Poles',False);v,p,l,inst,d=evaluate(obj)
    assert 15 not in l and not any(o.get('tc_infra_kind')=='Pole' for o,_ in inst)
    set_control(mod,'Utility Poles',True);set_control(mod,'Overhead Wires',False)
    v,p,l,inst,d=evaluate(obj);assert 15 not in l and any(o.get('tc_infra_kind')=='Pole' for o,_ in inst)
    set_control(mod,'Trees',False);assert not any(o.get('tc_farm_asset') in (10,11) for o,_ in evaluate(obj)[3])
    set_control(mod,'Trees',True);set_control(mod,'Structures',False)
    assert not any(o.get('tc_farm_asset') in (4,5,6,8,9) for o,_ in evaluate(obj)[3])
    set_control(mod,'Structures',True);set_control(mod,'Overhead Wires',True)
    record('independent_rural_switches','Woods, homes, poles and wires obey their own controls')
    # Check mesh and every transformed prototype vertex after rotating field axes.
    set_control(mod,'Field Angle',-19.)
    inside=lambda x,y:-105.002<=x<=105.002 and -80.002<=y<=80.002 and ((x<=79.002) or (y<=58.002) or ((x-79)*22+(y-58)*26<=26*22+.03))
    record('rural_footprint_clearance',coverage(obj,inside))
    # A v0.1-like interface in a separate tree exercises versioned value migration.
    legacy=mod.node_group.copy();legacy.name='TCity • Taiwan Farmland v0.1 upgrade test'
    for item in list(legacy.interface.items_tree):
        if item.item_type=='SOCKET' and item.name in ('Woodland Mix','Trees','Utility Poles','Pole Spacing','Overhead Wires','Cable Sag','Village Mix'):legacy.interface.remove(item)
    mod.node_group=legacy
    for name,_,default,*_ in SOCKETS:
        if name in {s.name for s in legacy.interface.items_tree}:set_control(mod,name,default)
    set_control(mod,'Seed',981);set_control(mod,'Plot Width',31.)
    assert bpy.ops.tcity.upgrade_farmland()=={'FINISHED'}
    assert mod.node_group.name==GROUP_NAME and get_control(mod,'Seed')==981 and abs(get_control(mod,'Plot Width')-31)<1e-5
    assert get_control(mod,'Utility Poles') and legacy.name in bpy.data.node_groups
    assert get_control(mod,'Village Mix')==0.
    record('farmland_upgrade','Prior controls and old graph retained; new rural controls initialized')
    (ROOT/'dist/rural_test_results.json').write_text(json.dumps({'blender':bpy.app.version_string,'tests':results},indent=2))
    print('RURAL_PASS',len(results),flush=True)
if __name__=='__main__':run()
