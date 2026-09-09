"""Evaluated farmland integration tests, including holes and asset footprints."""
import hashlib
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tcity
from tcity.farmland import make_farmland,farmland_modifier,add_farmland_modifier,PRESETS
from tcity.nodes import set_control,get_control
results=[]


def record(name,detail):
    results.append({'test':name,'result':'PASS','detail':detail});print('PASS',name,detail,flush=True)


def evaluate(obj):
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();mesh=obj.evaluated_get(dg).data
    verts=[v.co.copy() for v in mesh.vertices]
    mesh.calc_loop_triangles()
    polygons=[(tuple(t.vertices),t.normal.copy(),sum((verts[i] for i in t.vertices),Vector())/3,t.area) for t in mesh.loop_triangles]
    layers=[a.value for a in mesh.attributes['farm_layer'].data]
    inst=[]
    for i in dg.object_instances:
        if i.is_instance and i.parent and i.parent.original==obj:
            inst.append((i.object.original,i.matrix_world.copy()))
    digest=hashlib.sha256(repr(([tuple(v) for v in verts],[(o.name,tuple(v for row in mat for v in row)) for o,mat in inst])).encode()).hexdigest()
    return verts,polygons,layers,inst,digest


def inside_polygon(x,y,poly):
    inside=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1]>y)!=(b[1]>y) and x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside


def coverage(obj,inside):
    verts,polys,layers,inst,_=evaluate(obj)
    assert verts and inst
    for v in verts:assert inside(v.x,v.y),(tuple(v),'mesh')
    for ids,normal,center,area in polys:assert inside(center.x,center.y),(tuple(center),'face')
    inv=obj.matrix_world.inverted()
    # Every source vertex in each instance, not only point centers.
    cache={o.name:[v.co.copy() for v in o.data.vertices] for o,_ in inst}
    for o,m in inst:
        local=inv@m
        for vertex in cache[o.name]:
            v=local@vertex;assert inside(v.x,v.y),(o.name,tuple(v))
    return len(verts),len(inst)


def run():
    start=time.monotonic();bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);tcity.register()
    obj=make_farmland(width=120,depth=100);mod=farmland_modifier(obj)
    set_control(mod,'Woodland Mix',0.)
    verts,polys,layers,inst,first=evaluate(obj)
    assert set(layers)=={10,11,12,13,14,15},Counter(layers)
    assert len(inst)>3000,len(inst)
    assert not list(mod.node_warnings),list(mod.node_warnings)
    for layer,height in [(10,.02),(11,.13),(12,.095),(13,.12),(14,-.115)]:
        top=max(v.z for v,l in zip(verts,layers) if l==layer)
        assert abs(top-height)<.001,(layer,top)
    record('solid_layers_and_heights',{'vertices':len(verts),'instances':len(inst),'layers':sorted(set(layers))})
    assert evaluate(obj)[-1]==first
    set_control(mod,'Seed',32);assert evaluate(obj)[-1]!=first
    set_control(mod,'Seed',31);assert evaluate(obj)[-1]==first
    record('deterministic_live_seed','Same seed reproduces mesh and every instance transform')
    # Top-surface partition: channel floor counts once; its water surface does not.
    area=sum(area*normal.z for ids,normal,center,area in polys if normal.z>.99 and layers[ids[0]] not in {14,15})
    expected=120*100-26*22/2
    assert abs(area-expected)<expected*.002,(area,expected)
    record('surface_partition',{'projected_area':area,'region_area':expected})
    for control,absent in [('Farm Roads',{12,15}),('Irrigation',{13,14})]:
        set_control(mod,control,False);v,p,l,i,d=evaluate(obj);assert not(set(l)&absent)
        assert 10 in l and i
        set_control(mod,control,True)
    set_control(mod,'Crops',False);assert all(o.get('tc_infra_kind')=='Pole' or o.get('tc_farm_asset') in {4,5,6,8,9} for o,_ in evaluate(obj)[3])
    set_control(mod,'Crops',True)
    record('independent_switches','Roads, irrigation and crops update evaluated output')
    set_control(mod,'Plant Spacing',1.4);sparse=len(evaluate(obj)[3]);set_control(mod,'Plant Spacing',.72)
    assert len(evaluate(obj)[3])>sparse*2
    record('crop_spacing','Larger spacing reduces real crop instances')
    # Force individual crop families; implicit Index must never turn trees into houses.
    for control in ('Orchard Mix','Fallow Mix','Flooded Mix','Structure Mix'):set_control(mod,control,0.)
    set_control(mod,'Rice Mix',1.);set_control(mod,'Ripening',0.)
    assert {o['tc_farm_asset'] for o,_ in evaluate(obj)[3] if 'tc_farm_asset' in o}=={0,7}
    set_control(mod,'Ripening',1.);assert {o['tc_farm_asset'] for o,_ in evaluate(obj)[3] if 'tc_farm_asset' in o}=={1,7}
    set_control(mod,'Rice Mix',0.);assert {o['tc_farm_asset'] for o,_ in evaluate(obj)[3] if 'tc_farm_asset' in o}=={2,7}
    set_control(mod,'Orchard Mix',.8)
    kinds={o['tc_farm_asset'] for o,_ in evaluate(obj)[3] if 'tc_farm_asset' in o};assert 3 in kinds and kinds<={2,3,7},kinds
    record('crop_identity','All-green/all-golden rice, vegetables and orchard-only source indices verified')
    # Shrink to an L-shaped region with a separately triangulated hole ring.
    obj.hide_set(True);obj.hide_render=True
    mesh=bpy.data.meshes.new('L farmland');mesh.from_pydata([(0,0,0),(100,0,0),(100,45,0),(50,45,0),(50,90,0),(0,90,0)],[],[(5,4,3,2,1,0)]);mesh.update()
    region=bpy.data.objects.new('L farmland',mesh);bpy.context.collection.objects.link(region);add_farmland_modifier(region)
    set_control(farmland_modifier(region),'Plant Spacing',1.1)
    record('clockwise_concave_boundary',coverage(region,lambda x,y:-.001<=x<=100.001 and -.001<=y<=90.001 and not(x>50.001 and y>45.001)))
    region.hide_set(True);region.hide_render=True
    mesh=bpy.data.meshes.new('Farm with hole')
    outer=[(-60,-50,0),(60,-50,0),(60,50,0),(-60,50,0)];inner=[(-13,-11,0),(13,-11,0),(13,11,0),(-13,11,0)]
    mesh.from_pydata(outer+inner,[],[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);mesh.update()
    hole=bpy.data.objects.new('Farm with hole',mesh);bpy.context.collection.objects.link(hole);hm=add_farmland_modifier(hole)
    set_control(hm,'Plant Spacing',1.1);set_control(hm,'Field Angle',27.)
    inside=lambda x,y:-60.002<=x<=60.002 and -50.002<=y<=50.002 and not(-12.998<x<12.998 and -10.998<y<10.998)
    record('hole_and_rotated_field_layout',coverage(hole,inside))
    hole.location=(24,-15,3);hole.rotation_euler=(.1,-.15,.36);hole.data.vertices[0].co.x-=5
    # Instance positions must remain in the source's local coordinate system.
    vv,pp,ll,ii,_=evaluate(hole);assert ii
    inv=hole.matrix_world.inverted()
    assert all(abs((inv@m).translation.z-(.095 if o.get('tc_infra_kind')=='Pole' else .13 if o.get('tc_farm_asset')==7 else .02))<.001 for o,m in ii)
    record('object_transform_and_live_boundary','Object translation/rotation and Edit Mode vertex changes preserve grounding')
    for o in bpy.context.selected_objects:o.select_set(False)
    hole.select_set(True);bpy.context.view_layer.objects.active=hole
    for preset in PRESETS:
        assert bpy.ops.tcity.farmland_preset(preset=preset)=={'FINISHED'}
        assert abs(get_control(hm,'Rice Mix')-PRESETS[preset]['Rice Mix'])<1e-5
    record('sidebar_presets','All three presets execute against the active farm modifier')
    set_control(hm,'Crops',False);set_control(hm,'Structures',False)
    original=len(bpy.data.objects);assert bpy.ops.tcity.bake_copy()=={'FINISHED'}
    baked=next(o for o in bpy.data.objects if o.name.startswith(hole.name+' • Baked'))
    assert len(bpy.data.objects)==original+1 and len(baked.data.vertices)>0 and not baked.modifiers
    assert baked.hide_render and not baked['tc_farmland'] and farmland_modifier(hole)
    record('non_destructive_bake','Hidden mesh copy created; procedural source retained')
    report={'blender':bpy.app.version_string,'elapsed_seconds':round(time.monotonic()-start,2),'tests':results}
    (ROOT/'dist/farmland_test_results.json').write_text(json.dumps(report,indent=2));print('FARMLAND_PASS',len(results),flush=True)

if __name__=='__main__':run()
