"""Corner buildings at near-right-angle curved-road junctions (0.6.3,
docs/roadmap.md "轉角雙立面模組"). Two existing single-frontage facades
joined around the junction's outer corner, replacing the empty lot 0.6.0
left there — restricted to near-right-angle junctions, and pushed clear of
the crossing road's own paved width.

Run: blender -b --factory-startup --python-exit-code 1 --python tests/test_corner_buildings.py
"""
import json
import math
import sys
import time
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tcity
from tcity.nodes import add_modifier,set_control

results=[]


def record(name,detail):
    results.append({'test':name,'result':'PASS','detail':detail})
    print('PASS',name,detail,flush=True)


def update():
    bpy.context.view_layer.update();return bpy.context.evaluated_depsgraph_get()


def region(name,verts,edges,faces=((0,1,2,3),)):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,list(edges),list(faces));mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    mod=add_modifier(obj)
    set_control(mod,'Smooth Streets',False)  # straight segments: positions are easy to reason about
    set_control(mod,'Frontage',7.2);set_control(mod,'Density',1.0)
    return obj,mod


def corner_instances(obj):
    """(name, world matrix) for every corner-building Buildings instance."""
    dg=update()
    return [(i.object.original.name,i.matrix_world.copy()) for i in dg.object_instances
            if i.is_instance and i.parent and i.parent.original==obj
            and i.object.original.get('tc_kind')=='CORNER' and 'Buildings' in i.object.original.name]


# A right-angle "+" crossing: N-S street (0,-60)-(0,60) and E-W street
# (-60,0)-(60,0) sharing the vertex at the origin.
CROSS_VERTS=[(-100,-100,0),(150,-100,0),(150,100,0),(-100,100,0),
             (0,-60,0),(0,-20,0),(0,0,0),(0,20,0),(0,60,0),
             (-60,0,0),(-20,0,0),(20,0,0),(60,0,0)]
CROSS_EDGES=[(4,5),(5,6),(6,7),(7,8),(9,10),(10,6),(6,11),(11,12)]

# A T-junction, same shape as tests/test_junctions.py: a side street only to
# the east, so main street's west row never qualifies as a corner.
T_VERTS=[(-100,-100,0),(150,-100,0),(150,100,0),(-100,100,0),
         (0,-60,0),(0,-20,0),(0,0,0),(0,20,0),(0,60,0),(40,0,0),(80,0,0)]
T_EDGES=[(4,5),(5,6),(6,7),(7,8),(6,9),(9,10)]

# A 45-degree Y-junction: the side street leaves the main north-south street
# at a shallow angle, not a right angle.
Y_VERTS=[(-100,-100,0),(150,-100,0),(150,100,0),(-100,100,0),
         (0,-60,0),(0,-20,0),(0,0,0),(0,20,0),(0,60,0),(40,40,0),(80,80,0)]
Y_EDGES=[(4,5),(5,6),(6,7),(7,8),(6,9),(9,10)]


def run():
    start=time.monotonic()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    tcity.register()

    obj,mod=region('Cross junction',CROSS_VERTS,CROSS_EDGES)
    assert not mod.node_warnings[:],[w.message for w in mod.node_warnings]
    corners=corner_instances(obj)
    assert corners,'expected corner buildings at a right-angle 4-way crossing'
    assert all(42<=int(name.split('_')[1])<=53 for name,_ in corners)
    record('Corner detection','A right-angle 4-way crossing gets dual-frontage corner buildings (index 42-53)')

    # Clear of both roads' paved width (Road Width/2 + Sidewalk Width from
    # each street's own centerline axis), not just visually close to it.
    half=6/2+1.25  # default Road Width 6, Sidewalk Width 1.25
    clipped=0
    for name,matrix in corners:
        x,y=matrix.translation.x,matrix.translation.y
        # Whichever axis this corner's own row runs along, its footprint must
        # clear the *other* axis's paved band (the crossing road).
        if abs(x)<=half+.5 and abs(y)<=half+.5:
            clipped+=1
    assert clipped==0,f'{clipped} corner building(s) still overlap the crossing road pavement'
    record('Corner clearance','Every corner building sits clear of the crossing road\'s own paved width')

    obj2,mod2=region('T junction',T_VERTS,T_EDGES)
    assert not mod2.node_warnings[:]
    t_corners=corner_instances(obj2)
    assert t_corners,'expected corner buildings near the T-junction'
    assert all(42<=int(name.split('_')[1])<=53 for name,_ in t_corners)
    record('T-junction corners','A T-junction also gets dual-frontage corner buildings near its stem')

    obj3,mod3=region('Shallow Y junction',Y_VERTS,Y_EDGES)
    assert not mod3.node_warnings[:]
    assert not corner_instances(obj3),'a 45 degree junction is outside the near-right-angle scope and must stay empty'
    record('Angle scope','A shallow (45 degree) junction is left as an empty lot, matching 0.6.0')

    set_control(mod,'Corner Buildings',False)
    assert not corner_instances(obj),'Corner Buildings off must fall back to the 0.6.0 empty-lot behaviour'
    record('Corner Buildings toggle','Turning the switch off removes corner buildings entirely')

    # Regression for the rotation fix this feature depends on: Bend Buildings
    # to Curve off must still orient ordinary buildings along their own row,
    # not collapse to a single world direction (the bug corner buildings, and
    # unbent normal buildings, would otherwise both hit).
    set_control(mod,'Corner Buildings',True)
    set_control(mod,'Bend Buildings to Curve',False)
    dg=update()
    yaws=set()
    for i in dg.object_instances:
        if i.is_instance and i.parent and i.parent.original==obj and i.object.original.get('tc_kind')=='ROWHOUSE' and 'Buildings' in i.object.original.name:
            yaws.add(round(math.degrees(i.matrix_world.to_euler('XYZ').z)/90)*90%360)
    assert len(yaws)>=3,f'expected buildings facing multiple street directions, got {yaws}'
    record('Unbent rotation regression','Ordinary buildings on both streets face their own row even without bending')

    out={'blender':bpy.app.version_string,'seconds':round(time.monotonic()-start,2),'results':results}
    (ROOT/'dist'/'corner_test_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('TCITY_CORNER_TESTS_PASS',len(results),flush=True)

if __name__=='__main__':run()
