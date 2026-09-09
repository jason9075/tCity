"""Integration tests against evaluated Blender output, including boundary holes.

Run: blender -b --factory-startup --python-exit-code 1 --python tests/test_blender.py
"""
import json
import math
import sys
import time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tcity
from tcity.nodes import add_modifier,set_control,get_control

results=[]


def snapshot(obj,kind=None):
    bpy.context.view_layer.update()
    dg=bpy.context.evaluated_depsgraph_get()
    items=[]
    for i in dg.object_instances:
        if not i.is_instance or not i.parent or i.parent.original!=obj:continue
        source=i.object.original
        if not source.name.startswith('TC_') or source.name.startswith('TC_INF_'):continue
        if kind and '_'+kind+'_' not in source.name:continue
        items.append((source.name,tuple(round(v,5) for row in i.matrix_world for v in row)))
    return sorted(items)


def record(name,detail):
    results.append({'test':name,'result':'PASS','detail':detail})
    print('PASS',name,detail,flush=True)


def mesh_region(name,verts,faces):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj)
    add_modifier(obj)
    return obj


def footprint_check(obj,inside):
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    checked=0
    for i in dg.object_instances:
        if not i.is_instance or not i.parent or i.parent.original!=obj:continue
        # All actual asset vertices, not just parcel centers or corners.
        for v in i.object.data.vertices:
            world=i.matrix_world@v.co
            local=obj.matrix_world.inverted()@world
            assert inside(local.x,local.y),(i.object.name,tuple(local))
        checked+=1
    assert checked>0
    return checked


def run():
    start=time.monotonic()
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    tcity.register()
    obj=tcity.make_region();mod=tcity.district_modifier(obj)
    first=snapshot(obj,'Buildings');assert len(first)>30,len(first)
    assert len(mod.node_group.nodes)>80
    assert not mod.node_warnings[:],[(w.message) for w in mod.node_warnings]
    record('Initial generation',f'{len(first)} buildings, {len(mod.node_group.nodes)} nodes')
    # Existing apartment floor rules are tested without the one-storey shed class.
    set_control(mod,'Metal Shed Mix',0)
    set_control(mod,'Density',0);assert not snapshot(obj)
    record('Density zero','No building, sign, roof or prop instances')
    set_control(mod,'Density',1);a=snapshot(obj);a_buildings=snapshot(obj,'Buildings')
    assert a==snapshot(obj)
    set_control(mod,'Seed',18);b=snapshot(obj);assert a!=b
    assert sorted(x[1] for x in a_buildings)==sorted(x[1] for x in snapshot(obj,'Buildings'))
    set_control(mod,'Seed',17);assert snapshot(obj)==a
    record('Determinism','Same seed reproduces output; new seed changes kit, preserves occupied parcel positions')
    for lo,hi in [(2,2),(7,7),(6,3)]:
        set_control(mod,'Min Floors',lo);set_control(mod,'Max Floors',hi)
        rows=snapshot(obj,'Buildings');assert rows
        floors=[int(name.split('_')[3][:-1]) for name,_ in rows]
        assert min(floors)>=min(lo,hi) and max(floors)<=max(lo,hi),floors
    record('Floor controls','2 and 7 storeys plus reversed min/max evaluate correctly')
    for toggle,kind in [('Signs','Signs'),('Rooftops','Roofs'),('Street Life','Street life')]:
        set_control(mod,toggle,False);assert not snapshot(obj,kind)
        assert snapshot(obj,'Buildings');set_control(mod,toggle,True)
    set_control(mod,'Buildings',False);assert not snapshot(obj);set_control(mod,'Buildings',True)
    set_control(mod,'Rooftops',False);assert not snapshot(obj,'Additions');set_control(mod,'Rooftops',True)
    record('Detail controls','Independent detail toggles; rooftop switch also hides residential additions')
    def additions():return {matrix for name,matrix in snapshot(obj,'Additions')}
    set_control(mod,'Rooftop Addition Mix',0);assert not additions()
    core=snapshot(obj,'Roofs');assert core
    set_control(mod,'Rooftop Addition Mix',.3);low=additions();assert low
    set_control(mod,'Rooftop Addition Mix',.7);high=additions();assert low<high
    set_control(mod,'Rooftop Addition Mix',1)
    assert additions()=={matrix for name,matrix in snapshot(obj,'Buildings')}
    assert snapshot(obj,'Roofs')==core
    record('Roof home proportion','0/30/70/100 percent is monotonic, all residential parcels at 100%; permanent roof services unchanged')
    from tcity.assets import ensure_assets
    cols=ensure_assets()
    assert len(cols)==5 and all(len(c.objects)==42 for c in cols.values())
    for key,c in cols.items():
        assert [int(o.name.split('_')[1]) for o in sorted(c.objects,key=lambda o:o.name)]==list(range(42))
    for o in cols['Additions'].objects:
        if o.get('tc_kind')=='ROWHOUSE':
            coords=[v.co for v in o.data.vertices]
            assert max(v.x for v in coords)-min(v.x for v in coords)>5.4
            assert max(v.y for v in coords)-min(v.y for v in coords)>6
    record('Residential kit','Five aligned collections; residential roof homes have full-size rooms and terraces')
    for mix,allowed in [(0,{0,1,2}),(1,{3,4,5})]:
        set_control(mod,'Townhouse Mix',mix)
        assert {int(n.split('_')[4]) for n,_ in snapshot(obj,'Buildings')}<=allowed
    record('Facade mix','Facade group 0–2 and facade group 3–5 selections')
    def sheds():
        return {matrix for name,matrix in snapshot(obj,'Buildings') if int(name.split('_')[1])>=36}
    assert not sheds()
    set_control(mod,'Metal Shed Mix',.3);low=sheds();assert low
    set_control(mod,'Metal Shed Mix',.7);high=sheds();assert low<high
    set_control(mod,'Metal Shed Mix',1)
    all_sheds=snapshot(obj,'Buildings')
    assert not snapshot(obj,'Additions')
    assert len(sheds())==len(all_sheds)
    assert all('_1F_' in name for name,_ in all_sheds)
    assert {int(name.split('_')[1]) for name,_ in all_sheds}==set(range(36,42))
    assert all(bpy.data.objects[name].get('tc_kind')=='METAL_SHED' for name,_ in all_sheds)
    set_control(mod,'Rooftops',False)
    assert snapshot(obj,'Buildings')==all_sheds
    assert all(max(v.co.z for v in bpy.data.objects[name].data.vertices)>4 for name,_ in all_sheds)
    set_control(mod,'Rooftops',True)
    record('Metal shed proportion','0%, 30%, 70%, 100% select a monotonic set; all six one-storey variants; essential roofs remain with rooftop extras disabled')
    set_control(mod,'Metal Shed Mix',0)
    before=snapshot(obj,'Buildings')
    set_control(mod,'Road Width',13);after=snapshot(obj,'Buildings');assert before!=after
    set_control(mod,'Frontage',8);set_control(mod,'Depth',15)
    assert snapshot(obj,'Buildings')
    record('Layout controls','Road width, frontage and depth change evaluated layout')
    before=snapshot(obj,'Buildings')
    old=[v.co.copy() for v in obj.data.vertices]
    for v in obj.data.vertices:v.co.x*=.65
    obj.data.update();obj.update_tag()
    assert snapshot(obj,'Buildings')!=before
    for v,co in zip(obj.data.vertices,old):v.co=co
    obj.data.update();obj.update_tag()
    assert snapshot(obj,'Buildings')==before
    record('Live boundary edit','Mesh edit changes generation; restoring boundary reproduces previous output')
    # L shape and a tessellated annulus: holes must be respected, including overhangs.
    l=mesh_region('Concave test',[(0,0,0),(110,0,0),(110,42,0),(48,42,0),(48,105,0),(0,105,0)],[(0,1,2,3,4,5)])
    n=footprint_check(l,lambda x,y:-1e-4<=x<=110.0001 and -1e-4<=y<=105.0001 and (x<=48.0001 or y<=42.0001))
    l.location=(200,70,4);l.rotation_euler.z=.63
    assert footprint_check(l,lambda x,y:-1e-4<=x<=110.0001 and -1e-4<=y<=105.0001 and (x<=48.0001 or y<=42.0001))==n
    record('Concave + transforms',f'All vertices of {n} instances stay in L-shaped region, including rotated/translated object')
    ring=mesh_region('Hole test',[(-70,-65,0),(70,-65,0),(70,65,0),(-70,65,0),
                     (-15,-18,0),(15,-18,0),(15,18,0),(-15,18,0)],
                     [(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    n=footprint_check(ring,lambda x,y:abs(x)<=70.0001 and abs(y)<=65.0001 and (abs(x)>=14.9999 or abs(y)>=17.9999))
    record('Courtyard hole',f'All vertices of {n} instances stay outside central hole and inside outer boundary')
    # Residential overhangs including roof canopies must also fit at both extremes.
    ringmod=tcity.district_modifier(ring);set_control(ringmod,'Rooftop Addition Mix',1)
    for w,d in [(5.2,9),(10,18)]:
        set_control(ringmod,'Frontage',w);set_control(ringmod,'Depth',d)
        footprint_check(ring,lambda x,y:abs(x)<=70.0001 and abs(y)<=65.0001 and (abs(x)>=14.9999 or abs(y)>=17.9999))
    record('Residential footprint','Every balcony, AC, tank and addition vertex stays within the region at extreme dimensions')
    # Verify all overhangs on sheds at both extreme asset scale settings.
    ringmod=tcity.district_modifier(ring);set_control(ringmod,'Metal Shed Mix',1)
    for w,d in [(5.2,9),(10,18)]:
        set_control(ringmod,'Frontage',w);set_control(ringmod,'Depth',d)
        footprint_check(ring,lambda x,y:abs(x)<=70.0001 and abs(y)<=65.0001 and (abs(x)>=14.9999 or abs(y)>=17.9999))
    record('Shed footprint','All actual shed vertices fit around a courtyard at minimum and maximum lot dimensions')
    # A filled small region is valid but should contain zero buildings.
    small=mesh_region('Small',[(0,0,0),(4,0,0),(4,4,0),(0,4,0)],[(0,1,2,3)])
    assert not snapshot(small)
    record('Small region','No overflowing buildings for an undersized region')
    assert tcity.validate_region(small) is None
    small.scale.x=2;assert tcity.validate_region(small);small.scale.x=1
    small.data.vertices[0].co.z=1;assert tcity.validate_region(small)
    record('Input validation','Unapplied scale and non-planar input rejected')
    # Bake actual geometry of the original, leave source and settings untouched.
    set_control(mod,'Min Floors',4);set_control(mod,'Max Floors',5);set_control(mod,'Density',.15)
    bpy.context.view_layer.objects.active=obj
    before=snapshot(obj)
    result=bpy.ops.tcity.bake_copy();assert result=={'FINISHED'}
    baked=bpy.data.objects[obj.name+' • Baked']
    assert len(baked.data.polygons)>10000 and not baked.modifiers
    assert baked.hide_render and baked.hide_get() and snapshot(obj)==before
    record('Non-destructive bake',f'{len(baked.data.polygons)} faces, source unchanged')
    out={'blender':bpy.app.version_string,'seconds':round(time.monotonic()-start,2),'results':results}
    (ROOT/'dist'/'test_results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('TCITY_TESTS_PASS',len(results),flush=True)

if __name__=='__main__':run()
