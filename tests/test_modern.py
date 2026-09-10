"""Evaluated community layout, floor assembly and full-site boundary tests."""
import json
import sys
from collections import Counter
from pathlib import Path
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tcity
from tcity.modern import make_modern_region,modern_modifier,add_modern_modifier
from tcity.modern_assets import CATALOG,FLOOR_HEIGHT,PODIUM_HEIGHT
from tcity.nodes import set_control,get_control
results=[]
def record(name,detail):
    results.append({'test':name,'result':'PASS','detail':detail});print('PASS',name,detail,flush=True)
def evaluate(obj):
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    instances=[(i.object.original,i.matrix_world.copy()) for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj]
    mesh=obj.evaluated_get(dg).data
    layers={v.value for v in mesh.attributes['tc_layer'].data} if mesh.attributes.get('tc_layer') else set()
    return instances,layers

def bases(obj):return [(o,m) for o,m in evaluate(obj)[0] if o.get('tc_modern_role')=='Base']
def signature(obj):return [(o.name,tuple(round(c,4) for c in m.translation)) for o,m in evaluate(obj)[0]]
def controls(obj,**values):
    for k,v in values.items():set_control(modern_modifier(obj),k.replace('_',' '),v)
def region(verts,faces):
    mesh=bpy.data.meshes.new('Test region');mesh.from_pydata(verts,[],faces);mesh.update()
    obj=bpy.data.objects.new('Test modern boundary',mesh);bpy.context.collection.objects.link(obj);add_modern_modifier(obj);controls(obj,Density=1.)
    return obj

def coverage(obj,inside):
    inverse=obj.matrix_world.inverted();count=0
    for source,matrix in evaluate(obj)[0]:
        if not source.get('tc_modern_role'):continue
        transform=inverse@matrix
        # Every actual geometry vertex, including landscape canopy extents.
        for vertex in source.data.vertices:
            p=transform@vertex.co;assert inside(p.x,p.y),(source.name,tuple(p));count+=1
    assert count>1000,count
    return count

def run():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);tcity.register()
    obj=make_modern_region(width=228,depth=128);controls(obj,Density=1.,Seed=53,Min_Floors=10,Max_Floors=18,Green_Balcony_Mix=.35,Twin_Community_Mix=.5)
    assert len(bases(obj))==6,len(bases(obj))
    first=signature(obj);assert first==signature(obj)
    controls(obj,Seed=54);assert first!=signature(obj);controls(obj,Seed=53);assert first==signature(obj)
    record('seeded_live_communities',{'sites':6,'styles':sorted({o['tc_modern_style'] for o,_ in bases(obj)})})
    for style,green,twin in [(0,0.,0.),(1,0.,1.),(2,1.,0.)]:
        controls(obj,Green_Balcony_Mix=green,Twin_Community_Mix=twin,Min_Floors=12,Max_Floors=12)
        inst=evaluate(obj)[0];counts=Counter(o.get('tc_modern_role') for o,_ in inst)
        assert {o['tc_modern_style'] for o,_ in bases(obj)}=={style}
        assert counts['Roof']==6*(1 if style==0 else 2),counts
        assert counts['Floor']==6*(11 if style==0 else 20 if style==1 else 22),counts
        for source,matrix in inst:
            role=source.get('tc_modern_role')
            if role in ('Floor','Roof'):
                expected=.14+PODIUM_HEIGHT+(source['tc_level']-1)*FLOOR_HEIGHT
                assert abs(matrix.translation.z-expected)<.0001,(source.name,matrix.translation.z,expected)
                assert abs(matrix.to_scale().z-1)<1e-6
    record('three_types_and_fixed_floor_height','Single tower, stepped twin towers and bowed deep balconies; 3.1 m upper floors')
    for low,high in [(6,6),(24,24),(20,8)]:
        controls(obj,Min_Floors=low,Max_Floors=high)
        assert all(min(low,high)<=o['tc_modern_floors']<=max(low,high) for o,_ in bases(obj))
    meshes={o.data for c in bpy.data.collections[CATALOG].children for o in c.objects}
    assert len(meshes)==18,len(meshes)
    record('bounded_shared_asset_memory',{'variants':57,'architecture_meshes':len(meshes)})
    controls(obj,Min_Floors=8,Max_Floors=8,Landscape=False)
    assert not any(o.get('tc_modern_role')=='Landscape' for o,_ in evaluate(obj)[0]);assert len(bases(obj))==6
    controls(obj,Buildings=False);inst,layers=evaluate(obj)
    assert not any(o.get('tc_modern_role') for o,_ in inst);assert {1,2}<=layers
    controls(obj,Buildings=True,Density=0.);assert not bases(obj);assert {1,2}<=evaluate(obj)[1]
    controls(obj,Density=1.,Landscape=True)
    record('independent_switches','Architecture and trees hide independently; empty sites retain roads')
    for w,d in [(52.,42.),(90.,80.)]:
        controls(obj,Community_Width=w,Community_Depth=d)
        assert bases(obj)
        coverage(obj,lambda x,y:-114.002<=x<=114.002 and -64.002<=y<=64.002)
    controls(obj,Community_Width=60.,Community_Depth=48.)
    obj.location=(83,-127,4);obj.rotation_euler.z=.41;bpy.context.view_layer.update()
    record('transformed_and_scaled_footprints',coverage(obj,lambda x,y:-114.002<=x<=114.002 and -64.002<=y<=64.002))
    concave=region([(0,0,0),(228,0,0),(228,64,0),(152,64,0),(152,128,0),(0,128,0)],[(0,1,2,3,4,5)])
    assert len(bases(concave))==5,len(bases(concave))
    record('concave_region',coverage(concave,lambda x,y:-.002<=x<=228.002 and -.002<=y<=128.002 and (x<=152.002 or y<=64.002)))
    # A tiny internal hole lies well away from the corners AND tower footprints.
    # Complete site containment must reject that community, including its plaza.
    hole=region([(0,0,0),(152,0,0),(152,64,0),(0,64,0),(35,30,0),(36,30,0),(36,31,0),(35,31,0)],[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    assert len(bases(hole))==1,[(o.name,tuple(m.translation)) for o,m in bases(hole)]
    assert bases(hole)[0][1].translation.x>76
    record('one_square_metre_hole_rejects_whole_site',coverage(hole,lambda x,y:-.002<=x<=152.002 and -.002<=y<=64.002 and not(35.002<x<35.998 and 30.002<y<30.998)))
    tiny=make_modern_region(width=30,depth=30);controls(tiny,Density=1.);assert not bases(tiny)
    record('undersized_region','No partial towers')
    bpy.context.view_layer.objects.active=obj
    for o in bpy.context.selected_objects:o.select_set(False)
    obj.select_set(True)
    assert bpy.ops.tcity.modern_preset(preset='URBAN')=={'FINISHED'}
    assert get_control(modern_modifier(obj),'Min Floors')==15
    controls(obj,Min_Floors=6,Max_Floors=6,Landscape=False)
    assert bpy.ops.tcity.bake_copy()=={'FINISHED'}
    baked=bpy.data.objects[obj.name+' • Baked']
    assert baked!=obj and baked.type=='MESH' and len(baked.data.vertices)>10000
    assert not baked.modifiers and baked.hide_render and modern_modifier(obj)
    record('sidebar_presets_and_bake','Source stays procedural; hidden mesh copy includes complete buildings')
    report={'blender':bpy.app.version_string,'tests':results}
    (ROOT/'dist/modern_test_results.json').write_text(json.dumps(report,indent=2));print('MODERN_PASS',len(results),flush=True)
if __name__=='__main__':run()
