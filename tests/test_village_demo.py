"""The village demo must evaluate and react to controls without addon imports."""
from pathlib import Path
import json
import bpy
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'dist/TCity_Taiwan_Village.blend'))
obj=next(o for o in bpy.context.scene.objects if o.get('tc_farmland'))
mod=next(m for m in obj.modifiers if m.type=='NODES')
assert mod.node_group.name=='TCity • Taiwan Farmland v0.3'
assert not hasattr(bpy.types,'TCITY_PT_farmland')
assert sum(o.type=='CAMERA' for o in bpy.context.scene.objects)==4
assert any(i.packed_file for i in bpy.data.images if i.source=='FILE')


def homes():
    bpy.context.view_layer.update()
    return [i.matrix_world.copy() for i in bpy.context.evaluated_depsgraph_get().object_instances
            if i.is_instance and i.parent and i.parent.original==obj and i.object.original.get('tc_farm_asset') in (12,13,14)]


initial=homes();assert len(initial)>=6
socket=next(s for s in mod.node_group.interface.items_tree if s.item_type=='SOCKET' and s.in_out=='INPUT' and s.name=='Village Mix')
control=getattr(mod.properties.inputs,socket.identifier)
value=control.value;control.value=0.;obj.update_tag();assert not homes()
control.value=value;obj.update_tag();assert homes()==initial
report={'result':'PASS','blender':bpy.app.version_string,'compounds':len(initial),'standalone':True,'live_controls':True}
(ROOT/'dist/village_demo_test_results.json').write_text(json.dumps(report,indent=2))
print('VILLAGE_DEMO_PASS',report,flush=True)
