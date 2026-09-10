"""Verify the delivered .blend evaluates live without importing the addon."""
import json
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'dist/TCity_Modern_Communities.blend'))
obj=next(o for o in bpy.context.scene.objects if o.get('tc_modern'))
mod=next(m for m in obj.modifiers if m.type=='NODES')
assert mod.node_group.name=='TCity • Modern Taiwan Communities v0.1'
assert sum(o.type=='CAMERA' for o in bpy.context.scene.objects)==3
assert any(i.packed_file for i in bpy.data.images if i.source=='FILE')
assert not hasattr(bpy.types,'TCITY_PT_modern')
def snapshot():
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    sources=[i.object.original for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj]
    return sources,obj.evaluated_get(dg).data

def control(name,value):
    item=next(s for s in mod.node_group.interface.items_tree if s.item_type=='SOCKET' and s.name==name and s.in_out=='INPUT')
    getattr(mod.properties.inputs,item.identifier).value=value;obj.update_tag()
sources,_=snapshot();assert sum(o.get('tc_modern_role')=='Base' for o in sources)==6
assert {o['tc_modern_style'] for o in sources if o.get('tc_modern_role')=='Base'}=={0,1,2}
control('Min Floors',8);control('Max Floors',8)
sources,_=snapshot();assert {o['tc_modern_floors'] for o in sources if o.get('tc_modern_role')=='Base'}=={8}
control('Landscape',False);assert not any(o.get('tc_modern_role')=='Landscape' for o in snapshot()[0])
control('Buildings',False);sources,mesh=snapshot();assert not any(o.get('tc_modern_role') for o in sources)
assert {1,2}<={v.value for v in mesh.attributes['tc_layer'].data}
report={'blender':bpy.app.version_string,'result':'PASS','no_addon_import':True,'sites':6,'styles':3,'cameras':3,'packed_lighting':True,'live_controls':True}
(ROOT/'dist/modern_demo_test_results.json').write_text(json.dumps(report,indent=2));print('MODERN_DEMO_PASS',report,flush=True)
