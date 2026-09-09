"""Open the delivered .blend and evaluate controls without importing the addon."""
import bpy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'dist/TCity_Taiwan_District.blend'))
obj=next(o for o in bpy.context.scene.objects if o.name=='TCity • 台北住商混合街區')
mod=obj.modifiers[0]
assert mod.type=='NODES' and mod.node_group.name.endswith('v0.4')
assert len([o for o in bpy.context.scene.objects if o.type=='CAMERA'])==4
hdr=next(im for im in bpy.data.images if 'urban_street_03' in im.name)
assert hdr.packed_file and hdr.packed_file.size>6000000
assert bpy.context.scene.camera.name.startswith('01')
assert not mod.node_warnings[:]
def count_roof():
    bpy.context.view_layer.update()
    return sum(1 for i in bpy.context.evaluated_depsgraph_get().object_instances if i.is_instance and i.parent and i.parent.original==obj and '_Additions_' in i.object.name)
socket=next(s for s in mod.node_group.interface.items_tree if s.item_type=='SOCKET' and s.in_out=='INPUT' and s.name=='Rooftop Addition Mix')
initial=count_roof();assert initial>0
getattr(mod.properties.inputs,socket.identifier).value=0.;obj.update_tag();assert count_roof()==0
getattr(mod.properties.inputs,socket.identifier).value=1.;obj.update_tag();assert count_roof()>=initial
def control(name,value):
    sock=next(s for s in mod.node_group.interface.items_tree if s.item_type=='SOCKET' and s.in_out=='INPUT' and s.name==name)
    getattr(mod.properties.inputs,sock.identifier).value=value;obj.update_tag();bpy.context.view_layer.update()
def layers():
    data=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    return {v.value for v in data.attributes['tc_layer'].data}
assert {1,2,3}<=layers()
control('Road Surface',False);assert 1 not in layers() and 2 in layers()
control('Utility Poles',False);assert 3 not in layers()
report={'result':'PASS','blender':bpy.app.version_string,'addon_imported':False,'packed_hdri':True,'cameras':4,'initial_roof_homes':initial,'control_evaluates_without_addon':True,'street_layers_evaluate_without_addon':True}
(ROOT/'dist/demo_test_results.json').write_text(json.dumps(report,indent=2));print('TCITY_DEMO_PASS',json.dumps(report))
