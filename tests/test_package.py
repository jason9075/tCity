"""Smoke-test the distributed ZIP in isolation from the source checkout."""
import json
import sys
import tempfile
import zipfile
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='tcity-package-') as directory:
    root=Path(directory)
    with zipfile.ZipFile(ROOT/'dist'/'tcity-0.6.2.zip') as archive:
        names=archive.namelist()
        assert 'blender_manifest.toml' in names
        assert 'fonts/TCitySigns.otf' in names
        assert not any('__pycache__' in name for name in names)
        archive.extractall(root/'tcity')
    sys.path.insert(0,str(root))
    import tcity
    assert str(root) in tcity.__file__
    tcity.register()
    assert bpy.ops.tcity.add_demo()=={'FINISHED'}
    obj=bpy.context.object
    dg=bpy.context.evaluated_depsgraph_get()
    count=sum(1 for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==obj)
    assert count>200,count
    from tcity.nodes import GROUP_NAME,get_control,set_control
    assert tcity.district_modifier(obj).node_group.name==GROUP_NAME
    assert abs(get_control(tcity.district_modifier(obj),'Rooftop Addition Mix')-.85)<1e-5
    assert (root/'tcity/environment/urban_street_03_2k.hdr').stat().st_size>6000000
    assert (root/'tcity/environment/CREDITS.txt').is_file()
    # Ensure Chinese text became mesh geometry even without external system fonts.
    from tcity.assets import find_font
    assert str(root) in find_font().filepath
    report={'blender':bpy.app.version_string,'package':'tcity-0.6.2.zip',
            'result':'PASS','instances':count,'bundled_font':True,'isolated_import':True}
    assert bpy.ops.tcity.add_farmland()=={'FINISHED'}
    farm=bpy.context.object
    from tcity.farmland import farmland_modifier
    assert farmland_modifier(farm)
    bpy.context.view_layer.update()
    dg=bpy.context.evaluated_depsgraph_get()
    sources={i.object.original.name for i in dg.object_instances if i.is_instance and i.parent and i.parent.original==farm}
    assert any('TC_FARM_' in name for name in sources)
    assert any('TC_INF_Pole' in name for name in sources)
    report['farmland']=True
    tcity.unregister()
    (ROOT/'dist'/'package_test_results.json').write_text(json.dumps(report,indent=2))
    print('TCITY_PACKAGE_PASS',json.dumps(report),flush=True)
