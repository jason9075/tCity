"""Open the distributed farm .blend without importing/registering the addon."""
import json
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'dist/TCity_Taiwan_Farmland.blend'))
obj=next(o for o in bpy.context.scene.objects if o.get('tc_farmland'))
mod=next(m for m in obj.modifiers if m.type=='NODES')
assert mod.node_group.name=='TCity • Taiwan Farmland v0.3'
assert sum(o.type=='CAMERA' for o in bpy.context.scene.objects)==4
assert any(i.packed_file for i in bpy.data.images if i.source=='FILE')
assert not hasattr(bpy.types,'TCITY_PT_farmland')
def snapshot():
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    result={}
    for i in dg.object_instances:
        if i.is_instance and i.parent and i.parent.original==obj:
            name=i.object.original.name;result[name]=result.get(name,0)+1
    mesh=obj.evaluated_get(dg).data
    layers={d.value for d in mesh.attributes['farm_layer'].data}
    return result,layers

def control(name,value):
    item=next(s for s in mod.node_group.interface.items_tree if s.item_type=='SOCKET' and s.name==name and s.in_out=='INPUT')
    getattr(mod.properties.inputs,item.identifier).value=value;obj.update_tag()
first,layers=snapshot()
assert 15 in layers and first.get('TC_INF_Pole',0)>0
assert any('Brick_farmhouse' in k for k in first)
assert any('Woodland_tree' in k for k in first)
control('Utility Poles',False);second,layers=snapshot();assert 15 not in layers and 'TC_INF_Pole' not in second
control('Crops',False);control('Trees',False)
third,_=snapshot();assert not any(any(s in k for s in ('Rice_','Vegetables','Orchard','Bund_grass','Woodland_tree','Bamboo_clump')) for k in third)
control('Structures',False);assert not snapshot()[0]
report={'blender':bpy.app.version_string,'result':'PASS','no_addon_import':True,'cameras':4,'packed_lighting':True,'initial_instances':sum(first.values()),'independent_controls':True}
(ROOT/'dist/farmland_demo_test_results.json').write_text(json.dumps(report,indent=2));print('FARMLAND_DEMO_PASS',report,flush=True)
