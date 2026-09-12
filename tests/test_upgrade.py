"""Migrate actual archived v0.1 and v0.2 scenes, preserving authored controls."""
import json,sys
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tcity
from tcity.nodes import get_control,set_control,GROUP_NAME
reports=[]
tcity.register()
for version in ('0.1','0.2','0.3'):
    bpy.ops.wm.open_mainfile(filepath=str(ROOT/f'dist/archive/v{version}/TCity_Taiwan_District.blend'))
    obj=bpy.context.object;mod=tcity.district_modifier(obj);old=mod.node_group
    assert old.name==f'TCity • Taiwan District v{version}'
    values={'Seed':402,'Road Width':10.,'Density':.73,'Min Floors':4,'Signs':False}
    if version in ('0.2','0.3'):values['Metal Shed Mix']=.41
    if version=='0.3':values['Rooftop Addition Mix']=.33
    for key,value in values.items():set_control(mod,key,value)
    boundary=[tuple(v.co) for v in obj.data.vertices]
    assert bpy.ops.tcity.upgrade()=={'FINISHED'}
    assert mod.node_group.name==GROUP_NAME
    assert bpy.data.node_groups.get(old.name)==old
    assert all(get_control(mod,k)==v or abs(get_control(mod,k)-v)<1e-5 for k,v in values.items())
    assert abs(get_control(mod,'Rooftop Addition Mix')-(.33 if version=='0.3' else .85))<1e-5
    assert get_control(mod,'Utility Poles') and get_control(mod,'Road Surface')
    assert boundary==[tuple(v.co) for v in obj.data.vertices]
    set_control(mod,'Corner Buildings',False)
    set_control(mod,'Metal Shed Mix',1)
    bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
    items=[i.object.original for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj]
    assert items and all(o.get('tc_kind')=='METAL_SHED' for o in items if o.name.startswith('TC_') and not o.name.startswith('TC_INF_'))
    assert not any('_Signs_' in o.name or '_Additions_' in o.name for o in items)
    # v0.3 scenes used to reuse their embedded kit outright (same name, same
    # kit_version) instead of regenerating a second collection; 0.6.3's corner
    # buildings bumped KIT_VERSION, so that embedded 42-object kit is now
    # stale too and every archived version regenerates a fresh 54-object one
    # alongside it.
    assert len([c for c in bpy.data.collections if c.name.startswith('TCity • Buildings')])==2
    reports.append({'result':'PASS','from':version,'to':'0.7','preserved_controls':list(values),
                    'boundary_unchanged':True,'old_kit_preserved':True,'roof_control':get_control(mod,'Rooftop Addition Mix'),'new_instances':len(items)})
(ROOT/'dist/upgrade_test_results.json').write_text(json.dumps(reports,indent=2))
tcity.unregister();print('TCITY_UPGRADE_PASS',json.dumps(reports))
