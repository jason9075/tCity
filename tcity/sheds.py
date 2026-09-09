"""Taiwanese small metal workshops and rooftop additions, original mesh kit."""
import math
from mathutils import Vector
from .assets import MeshBuilder, material


def metal_palette():
    colors=[('Ocean blue',(.045,.25,.40)),('Faded jade',(.13,.32,.24)),
            ('Red oxide',(.40,.13,.07)),('Galvanized grey',(.42,.47,.45)),
            ('Weathered turquoise',(.08,.34,.36)),('Olive steel',(.28,.32,.15))]
    result=[]
    for name,color in colors:
        m=material('Sheet metal • '+name,color,metallic=.55,roughness=.48)
        if not m.node_tree.nodes.get('TC sheet weathering'):
            n=m.node_tree.nodes;links=m.node_tree.links
            tex=n.new('ShaderNodeTexCoord')
            noise=n.new('ShaderNodeTexNoise');noise.name='TC sheet weathering'
            noise.inputs['Scale'].default_value=3.0;noise.inputs['Detail'].default_value=3
            links.new(tex.outputs['Object'],noise.inputs['Vector'])
            ramp=n.new('ShaderNodeValToRGB')
            ramp.color_ramp.elements[0].position=.25
            ramp.color_ramp.elements[0].color=(*(c*.60 for c in color),1)
            ramp.color_ramp.elements[1].position=.72
            ramp.color_ramp.elements[1].color=(*color,1)
            links.new(noise.outputs['Fac'],ramp.inputs[0])
            links.new(ramp.outputs[0],n.get('Principled BSDF').inputs['Base Color'])
        result.append(m)
    return result


def sheet(builder, origin, across, along, mat, pitch=.22, amplitude=.04):
    """Folded trapezoid sheet. Ribs follow along, across may slope in Z."""
    o,u,v=Vector(origin),Vector(across),Vector(along)
    normal=u.cross(v).normalized()
    # Use a consistent upward/outward-facing corrugation direction for roofs.
    if normal.z < -.1:normal=-normal
    repeats=max(1,math.ceil(u.length/pitch))
    profile=(0,0,1,1)
    verts=[]
    for j in range(repeats*4+1):
        base=o+u*(j/(repeats*4))+normal*(amplitude*profile[j%4])
        verts.extend([tuple(base),tuple(base+v)])
    builder.add(verts,[(2*j,2*j+2,2*j+3,2*j+1) for j in range(repeats*4)],mat)


def sloped_roof(builder, x0,x1,y0,y1,left,right,mat,trim):
    # Corrugations run down the roof slope, so the metal reads correctly close up.
    sheet(builder,(x0,y0,left),(0,y1-y0,0),(x1-x0,0,right-left),mat)
    for y in (y0,y1):builder.beam((x0,y,left),(x1,y,right),.065,trim)
    for x,z in ((x0,left),(x1,right)):
        builder.beam((x,y0,z),(x,y1,z),.065,trim)


def rooftop_addition(builder, h,variant,mats):
    metal=metal_palette()[variant]
    x0,x1,y0,y1=-1.075,2.275,-3.0,2.4
    bottom=h+.2; low=h+2.05; high=low+.42
    # Three sheet walls; front opening has a small louver window over solid skin.
    for x,top in ((x0,low),(x1,high)):
        sheet(builder,(x,y0,bottom),(0,y1-y0,0),(0,0,top-bottom),metal)
    for y in (y0,y1):
        builder.add([(x0,y,bottom),(x1,y,bottom),(x1,y,high),(x0,y,low)],[(0,1,2,3)],metal)
        for j in range(19):
            x=x0+(x1-x0)*j/18;top=low+(high-low)*j/18
            builder.beam((x,y,bottom),(x,y,top),.025,mats['metal'])
    sloped_roof(builder,x0-.13,x1+.13,y0-.16,y1+.16,low-.016,high+.016,metal,mats['metal'])
    builder.box((.6,y0-.04,h+1.15),(1.35,.08,.78),mats['dark'])
    for i in range(6):builder.box((.6,y0-.09,h+.87+i*.105),(1.24,.045,.035),mats['metal'])


def build_sheds(cols,mats,font):
    colors=metal_palette()
    for variant in range(6):
        body,signs,extras,props=(MeshBuilder() for _ in range(4))
        metal=colors[variant]
        eave=3.65+(variant%3)*.32
        gable=variant%3!=1
        ridge=eave+1.12
        body.box((0,0,.10),(6.36,12,.20),mats['paving'])
        body.box((0,.68,.42),(5.8,9.98,.44),mats['concrete'])
        # Long walls, with a concrete plinth below the thin corrugated skin.
        for side in (-1,1):
            walltop=eave if gable or side==-1 else ridge
            sheet(body,(side*2.9,-4.30,.62),(0,9.98,0),(0,0,walltop-.62),metal)
            for y in (-4.30,-1.0,2.3,5.68):
                body.box((side*2.87,y,(walltop+.3)/2),(.12,.12,walltop-.3),mats['dark'])
        # Back wall and front strips around a real recessed opening.
        sheet(body,(-2.90,5.68,.62),(5.8,0,0),(0,0,eave-.62),metal)
        for x0,width in ((-2.90,.65),(1.45,1.45)):
            sheet(body,(x0,-4.30,.62),(width,0,0),(0,0,eave-.62),metal)
        sheet(body,(-2.25,-4.30,2.88),(3.70,0,0),(0,0,eave-2.88),metal)
        for y in (-4.30,5.68):
            polygon=[(-2.9,y,eave),(2.9,y,eave)]
            polygon+=([(0,y,ridge)] if gable else [(2.9,y,ridge)])
            body.add(polygon,[tuple(range(len(polygon)))],metal)
            # Slim mullions above the main walls emphasize the gable frame.
            for x in (-1.9,-.95,0,.95,1.9):
                top=eave+(ridge-eave)*(1-abs(x)/2.9 if gable else (x+2.9)/5.8)
                body.beam((x,y,eave),(x,y,top),.045,mats['metal'])
        # The essential pitched roof is part of Buildings, not the optional Roofs kit.
        if gable:
            sloped_roof(body,-3.04,0,-4.5,5.87,eave-.054,ridge,metal,mats['metal'])
            sloped_roof(body,0,3.04,-4.5,5.87,ridge,eave-.054,metal,mats['metal'])
            body.beam((0,-4.52,ridge+.045),(0,5.88,ridge+.045),.12,mats['metal'])
        else:
            sloped_roof(body,-3.04,3.04,-4.5,5.87,eave-.027,ridge+.027,metal,mats['metal'])
        # Blue roller shutter, side service door, grilled side windows.
        body.box((-.4,-4.21,1.56),(3.70,.12,2.64),mats['blue' if variant%2 else 'metal'])
        for j in range(22):body.box((-.4,-4.285,.3+j*.118),(3.65,.035,.028),mats['dark'])
        body.box((2.19,-4.37,1.31),(.70,.11,1.99),mats['trim'])
        body.box((2.40,-4.44,1.28),(.07,.045,.16),mats['dark'])
        for side in (-1,1):
            for y in (-.8,2.6):
                body.box((side*2.96,y,2.1),(.12,1.18,1.0),mats['dark'])
                body.box((side*3.027,y,2.1),(.025,1.04,.86),mats['glass'])
                for j in range(5):body.box((side*3.05,y-.45+j*.225,2.1),(.025,.025,.89),mats['metal'])
        # Sloping front canopy with open steel posts, braces and rainwater gutter.
        sheet(body,(-3.02,-5.87,2.87),(6.04,0,0),(0,1.52,.32),metal)
        for x in (-2.82,2.82):
            body.beam((x,-5.7,.22),(x,-5.7,2.96),.095,mats['dark'])
            body.beam((x,-5.7,2.15),(x,-4.85,3.09),.065,mats['dark'])
        body.beam((-3.04,-5.91,2.85),(3.04,-5.91,2.85),.12,mats['metal'])
        body.beam((2.97,-5.88,.23),(2.97,-5.88,2.90),.075,mats['metal'])
        # Sign names reuse bundled glyphs; no network/font dependency at runtime.
        words=['金興五金','阿春機車行','日日茶行','金興五金','幸福便當','永和豆漿']
        signs.box((-.35,-4.41,3.34),(3.85,.15,.61),mats['white'])
        signs.text(words[variant],(-.35,-4.50,3.34),.43,mats['red' if variant%2 else 'blue'],font)
        # Ventilator stands on the roof at its actual slope height.
        roof_z=ridge if gable else (eave+ridge)/2
        extras.cylinder((0,3.3,roof_z+.26),.16,.52,mats['metal'])
        extras.cylinder((0,3.3,roof_z+.57),.33,.23,mats['metal'])
        extras.cylinder((0,3.3,roof_z+.72),.20,.08,mats['metal'])
        # A metal workshop's everyday frontage: pallet, crates, bucket, potted tree.
        for x in (-1.5,-.9,-.3):props.box((x,-5.02,.31),(.13,.65,.18),mats['pot'])
        for y in (-5.26,-5.02,-4.78):props.box((-.9,y,.43),(1.38,.17,.07),mats['pot'])
        props.box((-.9,-5.02,.71),(.92,.49,.45),mats['green'])
        props.cylinder((1.24,-5.1,.50),.23,.57,mats['blue'])
        props.cylinder((-2.32,-5.1,.46),.23,.49,mats['pot'])
        props.cylinder((-2.32,-5.1,.99),.30,.56,mats['leaf'],10)
        for key,builder in zip(cols,(body,signs,extras,props,MeshBuilder())):
            obj=builder.object(f'TC_{36+variant:02d}_{key}_1F_{variant}',cols[key])
            obj['tc_floors']=1;obj['tc_variant']=variant;obj['tc_kind']='METAL_SHED'
