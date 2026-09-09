"""Evaluate street layers, live updates, pole-wire anchoring and exact region clipping."""
import sys,json,math,collections,time
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tcity
from tcity.nodes import set_control,get_control
results=[]
def record(name,detail):
    results.append({'test':name,'result':'PASS','detail':detail});print('PASS',name,detail,flush=True)
def update():bpy.context.view_layer.update();return bpy.context.evaluated_depsgraph_get()
def instances(obj,kind):
    dg=update();return [(i.object.original.name,i.matrix_world.copy()) for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj and i.object.original.get('tc_infra_kind')==kind]
def mesh(obj):return obj.evaluated_get(update()).data
# Do not retain RNA data across changes to the dependency graph.
def coords(obj,layer):
    m=mesh(obj);a=m.attributes.get('tc_layer');return [v.co.copy() for v,d in zip(m.vertices,a.data) if d.value==layer] if a else []
def digest(obj,kind):return [(n,tuple(round(v,5) for row in matrix for v in row)) for n,matrix in instances(obj,kind)]
def region(name,verts,faces):
    data=bpy.data.meshes.new(name);data.from_pydata(verts,[],faces);data.update();o=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(o)
    from tcity.nodes import add_modifier
    add_modifier(o);return o

def coverage(obj,inside):
    m=mesh(obj);a=m.attributes['tc_layer']
    assert len(m.polygons)>0
    for v,d in zip(m.vertices,a.data):assert inside(v.co.x,v.co.y),(d.value,tuple(v.co))
    # Include face interiors: a polygon bridging a hole could have all vertices inside.
    for face in m.polygons:
        c=face.center;assert inside(c.x,c.y),('face',tuple(c))
    for i in update().object_instances:
        if not i.is_instance or not i.parent or i.parent.original!=obj:continue
        matrix=obj.matrix_world.inverted()@i.matrix_world
        for v in i.object.data.vertices:
            c=matrix@v.co;assert inside(c.x,c.y),(i.object.name,tuple(c))

def anchored(obj):
    poles=[mat.translation for _,mat in instances(obj,'Pole')]
    m=mesh(obj);tags=m.attributes['tc_layer'];span=m.attributes.get('tc_span_id');groups=collections.defaultdict(list)
    for v,a,s in zip(m.vertices,tags.data,span.data):
        if a.value==3:groups[s.value].append(v.co.copy())
    for key,verts in groups.items():
        left=min(v.x for v in verts);right=max(v.x for v in verts)
        for xx in (left,right):
            end=[v for v in verts if abs(v.x-xx)<.035]
            # Tube extrema are offset from the pole center by at most the crossarm half-width.
            assert end
            for v in end:
                assert any(abs(v.x-p.x)<.04 and abs(v.y-p.y)<.43 for p in poles),(key,tuple(v),[(tuple(p)) for p in poles])
    assert groups
    return len(groups)

start=time.monotonic();bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);tcity.register()
obj=tcity.make_region();mod=tcity.district_modifier(obj)
assert not mod.node_warnings[:]
assert instances(obj,'Pole') and instances(obj,'Telecom') and instances(obj,'Manhole') and instances(obj,'Drain')
assert all(coords(obj,k) for k in (1,2,3))
record('Street layers','Road volume, raised paving, poles, telecom cabinets, drains, covers and wire meshes all evaluate')
set_control(mod,'Buildings',False);a=digest(obj,'Pole');assert a and coords(obj,1)
set_control(mod,'Density',0);assert a==digest(obj,'Pole')
record('Independent infrastructure','Building density and visibility do not remove or move street layers')
for name,kind in [('Telecom Cabinets','Telecom'),('Utility Poles','Pole'),('Road Details','Manhole')]:
    set_control(mod,name,False);assert not instances(obj,kind)
    if name=='Utility Poles':assert not coords(obj,3)
    if name=='Road Details':assert not instances(obj,'Drain')
    set_control(mod,name,True)
set_control(mod,'Overhead Wires',False);assert not coords(obj,3) and instances(obj,'Pole');set_control(mod,'Overhead Wires',True)
set_control(mod,'Road Surface',False);assert not coords(obj,1) and not instances(obj,'Drain') and not instances(obj,'Manhole');set_control(mod,'Road Surface',True)
set_control(mod,'Ground',False);assert not coords(obj,1) and not coords(obj,2);set_control(mod,'Ground',True)
record('Layer toggles','Wires require poles; drains/covers require visible road; all detail switches work')
set_control(mod,'Cabinet Density',0);assert not instances(obj,'Telecom')
set_control(mod,'Cabinet Density',.3);a={m for n,m in digest(obj,'Telecom')};assert a
set_control(mod,'Cabinet Density',1);b={m for n,m in digest(obj,'Telecom')};assert a<b
assert digest(obj,'Telecom')==digest(obj,'Telecom')
record('Cabinet density','Seeded subset is reproducible and grows monotonically with probability')
set_control(mod,'Sidewalks',False);assert not coords(obj,2);assert all(abs(m.translation.z)<1e-5 for n,m in instances(obj,'Telecom'));set_control(mod,'Sidewalks',True)
set_control(mod,'Curb Height',.22);assert abs(max(v.z for v in coords(obj,2))-.22)<1e-4
assert all(abs(m.translation.z-.22)<1e-4 for n,m in instances(obj,'Pole'))
set_control(mod,'Road Thickness',.35);assert abs(min(v.z for v in coords(obj,1))+.35)<1e-4
record('Physical dimensions','Live road thickness, raised pavement and matching utility base elevations')
n=anchored(obj);assert n>5
pole_count=len(instances(obj,'Pole'));set_control(mod,'Pole Spacing',12);assert len(instances(obj,'Pole'))>pole_count;anchored(obj)
set_control(mod,'Cable Sag',0);zero=min(v.z for v in coords(obj,3));set_control(mod,'Cable Sag',1);assert min(v.z for v in coords(obj,3))<zero-.9
set_control(mod,'Pole Height',12);anchored(obj)
record('Supported wire spans',f'{n} initial spans attach at both ends; spacing, height and sag update live')
set_control(mod,'Road Width',11);set_control(mod,'Sidewalk Width',2.1);anchored(obj)
record('Road-dependent layout','Road and sidewalk width move pole anchors and their connected wires together')
# Surface is a watertight partition. Vertices/edges on volume caps must be stitched.
m=mesh(obj);tags=m.attributes['tc_layer'];counts=collections.Counter()
for f in m.polygons:
    kind=tags.data[f.vertices[0]].value
    if kind in (1,2):
        for e in f.edge_keys:counts[(kind,e)]+=1
assert counts and set(counts.values())=={2},collections.Counter(counts.values())
record('Watertight street volumes','Every edge in the road and pavement volumes has exactly two incident faces')
# Sharp concavity, clockwise input, real courtyard hole, and a narrow slit crossing a span.
L=region('L roads',[(0,0,0),(90,0,0),(90,38,0),(43,38,0),(43,90,0),(0,90,0)],[(5,4,3,2,1,0)])
coverage(L,lambda x,y:-1e-4<=x<=90.0001 and -1e-4<=y<=90.0001 and (x<=43.0001 or y<=38.0001))
record('Concave clipped streets','Clockwise L shape: every road/pavement/wire face center and every asset vertex lies in the region')
ring=region('Hole roads',[(-70,-65,0),(70,-65,0),(70,65,0),(-70,65,0),(-15,-18,0),(15,-18,0),(15,18,0),(-15,18,0)],[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
coverage(ring,lambda x,y:abs(x)<=70.0001 and abs(y)<=65.0001 and (abs(x)>=14.9999 or abs(y)>=17.9999));anchored(ring)
record('Courtyard streets','Actual road/paving geometry preserves the hole; wire spans stay supported')
# A 10 cm-wide notch cuts through the first street frontage, between valid poles.
slit=region('Narrow slit',[(-50,-35,0),(-28,-35,0),(-28,-28,0),(-27.9,-28,0),(-27.9,-35,0),(50,-35,0),(50,35,0),(-50,35,0)],[(0,1,2,3,4,5,6,7)])
coverage(slit,lambda x,y:-50.0001<=x<=50.0001 and -35.0001<=y<=35.0001 and (x<=-27.9999 or x>=-27.9001 or y>=-28.0001))
anchored(slit)
record('Narrow boundary interruption','10 cm notch prevents a wire bridge even when both end poles are valid')
# A tiny interior hole intersects only the lower telecom conductor, not the pole axis.
tiny=region('Conductor hole',[(-50,-35,0),(50,-35,0),(50,35,0),(-50,35,0),
                            (-28,-31.51,0),(-27.9,-31.51,0),(-27.9,-31.48,0),(-28,-31.48,0)],
            [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
m=mesh(tiny);tags=m.attributes['tc_layer'];ids=m.attributes['tc_span_id'];groups=collections.defaultdict(list)
for v,a,k in zip(m.vertices,tags.data,ids.data):
    if a.value==3:groups[k.value].append(v.co.copy())
assert groups
for vs in groups.values():
    assert not (min(v.x for v in vs)<-28 and max(v.x for v in vs)>-27.9 and abs(sum(v.y for v in vs)/len(vs)+31.453)<.02)
record('Individual conductor clearance','A 3 cm hole touching only a telecom conductor rejects the entire span')
# Top surfaces form a partition of the exact input polygon, without overlaps or missing roads.
m=mesh(obj);area=collections.Counter();tags=m.attributes['tc_layer']
for face in m.polygons:
    if face.normal.z>.9:area[tags.data[face.vertices[0]].value]+=face.area
source_area=sum(f.area for f in obj.data.polygons)
assert abs(area[1]+area[2]-source_area)<.05,(area,source_area)
record('Ground partition',f'Road and paving top areas sum to input area {source_area:.1f} square metres')
bpy.context.view_layer.objects.active=obj
for preset in ('URBAN','ROAD_VIEW','RESIDENTIAL'):
    before=[tuple(v.co) for v in obj.data.vertices];seed=get_control(mod,'Seed');rooftop=get_control(mod,'Rooftop Addition Mix')
    assert bpy.ops.tcity.street_preset(preset=preset)=={'FINISHED'}
    assert before==[tuple(v.co) for v in obj.data.vertices] and seed==get_control(mod,'Seed') and rooftop==get_control(mod,'Rooftop Addition Mix')
    if preset=='URBAN':assert not instances(obj,'Pole') and not coords(obj,3)
    if preset=='ROAD_VIEW':assert not get_control(mod,'Buildings') and coords(obj,1)
record('Street presets','Residential, underground-utility and road-only views preserve boundary, seed and rooftop choices')
report={'blender':bpy.app.version_string,'seconds':round(time.monotonic()-start,2),'results':results}
(ROOT/'dist/infrastructure_test_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('TCITY_INFRA_PASS',len(results),flush=True)
