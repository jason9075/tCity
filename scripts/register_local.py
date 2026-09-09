"""Enable the checkout's sidebar for this Blender session, without saving prefs."""
import sys
from pathlib import Path
import bpy

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tcity
if not hasattr(bpy.types,'TCITY_PT_panel'):
    tcity.register()
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':area.spaces.active.show_region_ui=True
print('TCity local sidebar enabled for this session')
