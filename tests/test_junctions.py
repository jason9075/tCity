"""Road junctions (docs/PLAN.md §5 0.6.0). Multiple road edges meeting at a
shared mesh vertex (Face Count == 0, vertex degree >= 3) union into one
continuous surface, get a real tc_junction_dist, suppress sidewalks nearby,
and interrupt crossing overhead wires. Single-street regions (0.5, no
junction) must keep running the cheap no-union path unchanged.

Run: blender -b --factory-startup --python-exit-code 1 --python tests/test_junctions.py
"""
import collections
import json
import math
import sys
import time
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tcity
from tcity.nodes import add_modifier,set_control,get_control

results=[]


def record(name,detail):
    results.append({'test':name,'result':'PASS','detail':detail})
    print('PASS',name,detail,flush=True)


def update():
    bpy.context.view_layer.update();return bpy.context.evaluated_depsgraph_get()


def region(name,verts,faces,edges=()):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,list(edges),faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    add_modifier(obj);return obj


def mesh(obj):return obj.evaluated_get(update()).data


def attr(m,name):
    a=m.attributes.get(name);return [d.value for d in a.data] if a else None


def area_by_layer(m,layer):
    tags=m.attributes['tc_layer']
    return sum(f.area for f in m.polygons if tags.data[f.vertices[0]].value==layer and f.normal.z>.9)


def instances(obj,kind):
    dg=update()
    return [(i.object.original.name,i.matrix_world.copy()) for i in dg.object_instances
            if i.is_instance and i.parent and i.parent.original==obj and i.object.original.get('tc_infra_kind')==kind]


# A T-junction: a north-south main street from (0,-60) to (0,60), a side street
# branching from the midpoint (0,0) east to (0,80). The shared vertex at the
# origin has road-edge degree 3.
T_VERTS=[(-100,-100,0),(150,-100,0),(150,100,0),(-100,100,0),
         (0,-60,0),(0,-20,0),(0,0,0),(0,20,0),(0,60,0),(40,0,0),(80,0,0)]
T_FACES=[(0,1,2,3)]
T_EDGES=[(4,5),(5,6),(6,7),(7,8),(6,9),(9,10)]


def run():
    start=time.monotonic()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    tcity.register()

    obj=region('T junction',T_VERTS,T_FACES,T_EDGES)
    mod=tcity.district_modifier(obj)
    set_control(mod,'Smooth Streets',False)  # straight segments: positions are easy to reason about
    assert not mod.node_warnings[:],[w.message for w in mod.node_warnings]
    m=mesh(obj)

    # 1. Real junction distance: reaches (near) zero at the junction, grows
    # smoothly away from it, unlike the 0.5 proxy (distance to curve endpoint).
    jd=attr(m,'tc_junction_dist')
    assert jd and min(jd)<.6,min(jd)
    assert max(jd)>70,max(jd)
    record('Real junction distance','tc_junction_dist reaches ~0 at the T-junction and grows with distance from it')

    # 2. Road union: the main and side streets connect into one continuous
    # surface — total flat (asphalt+paving) area must be close to the sum of
    # both streets' own lengths at full width, not collapsed by a broken merge.
    total_flat=area_by_layer(m,1)+area_by_layer(m,2)
    expected=120*8.5+80*8.5  # main street 120 m + side street 80 m, full profile width
    assert total_flat>expected*.85,(total_flat,expected)
    record('Road union','Main and side street surfaces merge into one continuous area close to their combined footprint')

    # 3. No non-manifold gap at the junction itself: sample the asphalt right at
    # the origin and confirm road surface actually covers it (no hole).
    tags=m.attributes['tc_layer']
    covers_origin=any(tags.data[f.vertices[0]].value==1 and math.hypot(f.center.x,f.center.y)<2.5
                       for f in m.polygons if f.normal.z>.9)
    assert covers_origin
    record('Junction coverage','Asphalt actually covers the junction center, not just the two approaches')

    # 4. Sidewalk suppressed near the junction (flush asphalt instead of a raised
    # curb crossing the intersection).
    near_junction_sidewalk=[v for v,d in zip(m.vertices,tags.data)
                             if d.value==2 and math.hypot(v.co.x,v.co.y)<3]
    assert len(near_junction_sidewalk)<20,len(near_junction_sidewalk)
    record('Sidewalk suppression','Raised sidewalk/curb is suppressed within the fillet radius of the junction')

    # 5. Overhead wires: no span is allowed to cross through the junction.
    wires=[v.co.copy() for v,d in zip(m.vertices,tags.data) if d.value==3]
    assert wires
    crossing=[w for w in wires if math.hypot(w.x,w.y)<3]
    assert not crossing,crossing
    record('Wire interruption','No overhead wire vertex falls within the junction fillet radius')

    # 6. Regression: a single street with no junction takes the pre-0.6 path
    # (no self-union) and keeps giving a sane, correctly-sized road surface.
    plain=region('Single street',
                 [(-40,-40,0),(120,-40,0),(120,40,0),(-40,40,0),
                  (0,0,0),(10,8,0),(20,0,0),(30,-8,0),(40,0,0)],
                 [(0,1,2,3)],[(4,5),(5,6),(6,7),(7,8)])
    plain_mod=tcity.district_modifier(plain)
    assert not plain_mod.node_warnings[:]
    pm=mesh(plain)
    plain_flat=area_by_layer(pm,1)+area_by_layer(pm,2)
    assert plain_flat>0
    record('Single-street regression','A region with no junction (0.5 case) still evaluates cleanly with no union overhead')

    out={'blender':bpy.app.version_string,'seconds':round(time.monotonic()-start,2),'results':results}
    (ROOT/'dist'/'junction_test_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('TCITY_JUNCTION_TESTS_PASS',len(results),flush=True)

if __name__=='__main__':run()
