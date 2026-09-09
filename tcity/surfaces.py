"""Metre-scale weathering and small ceramic tiles for Taipei residential kit."""
import bpy
from .assets import material


def surface(name,color,tile=False,metallic=0):
    m=material('v03 '+name,color,metallic=metallic,roughness=.65)
    tree=m.node_tree;n=tree.nodes;l=tree.links
    if n.get('Residential weathering'):return m
    bs=n.get('Principled BSDF')
    def node(kind,**kwargs):
        x=n.new(kind)
        for k,v in kwargs.items():setattr(x,k,v)
        return x
    def noise(vector,scale):
        x=node('ShaderNodeTexNoise');x.inputs['Scale'].default_value=scale;x.inputs['Detail'].default_value=3
        l.new(vector,x.inputs['Vector']);return x
    def mix(a,b,factor,mode='MIX'):
        x=node('ShaderNodeMixRGB',blend_type=mode)
        if isinstance(factor,bpy.types.NodeSocket):l.new(factor,x.inputs[0])
        else:x.inputs[0].default_value=factor
        for val,s in ((a,x.inputs[1]),(b,x.inputs[2])):
            if isinstance(val,bpy.types.NodeSocket):l.new(val,s)
            else:s.default_value=val
        return x.outputs[0]
    coord=node('ShaderNodeTexCoord');coord.name='Residential weathering'
    local=coord.outputs['Object'];micro=noise(local,160)
    if tile:
        sep=node('ShaderNodeSeparateXYZ');l.new(local,sep.inputs[0])
        add=node('ShaderNodeMath',operation='ADD');l.new(sep.outputs[0],add.inputs[0]);l.new(sep.outputs[1],add.inputs[1])
        vec=node('ShaderNodeCombineXYZ');l.new(add.outputs[0],vec.inputs[0]);l.new(sep.outputs[2],vec.inputs[1])
        brick=node('ShaderNodeTexBrick');brick.offset=.5
        l.new(vec.outputs[0],brick.inputs['Vector']);brick.inputs['Scale'].default_value=1
        brick.inputs['Brick Width'].default_value=.105 if tile!='brick' else .205
        brick.inputs['Row Height'].default_value=.048 if tile!='brick' else .065
        brick.inputs['Mortar Size'].default_value=.002
        brick.inputs['Mortar Smooth'].default_value=.0008
        brick.inputs['Color1'].default_value=(*color,1)
        brick.inputs['Color2'].default_value=(*(v*.76 for v in color),1)
        brick.inputs['Mortar'].default_value=(.19,.185,.17,1)
        base=brick.outputs['Color']
        inv=node('ShaderNodeMath',operation='SUBTRACT');inv.inputs[0].default_value=1;l.new(brick.outputs['Fac'],inv.inputs[1])
        height=inv.outputs[0]
    else:
        base=(*color,1);height=micro.outputs['Fac']
    scale=node('ShaderNodeVectorMath',operation='MULTIPLY');l.new(local,scale.inputs[0]);scale.inputs[1].default_value=(2.8,2.8,.38) if not metallic else (1,1,1)
    streak=noise(scale.outputs[0],2)
    ramp=node('ShaderNodeValToRGB');l.new(streak.outputs['Fac'],ramp.inputs[0])
    ramp.color_ramp.elements[0].position=.20;ramp.color_ramp.elements[0].color=(.31,.275,.215,1)
    ramp.color_ramp.elements[1].position=.49;ramp.color_ramp.elements[1].color=(1,1,.98,1)
    # Sparse runoff on facades; metals and fabrics get gentler mottled wear.
    dirty=mix(base,ramp.outputs[0],.40 if not metallic else .15,'MULTIPLY')
    mottled=noise(local,2.3)
    final=mix(dirty,mottled.outputs['Fac'],.10,'MULTIPLY')
    l.new(final,bs.inputs['Base Color'])
    bump=node('ShaderNodeBump');bump.inputs['Strength'].default_value=.34;bump.inputs['Distance'].default_value=.0025 if tile else (.0008 if metallic else .002)
    l.new(height,bump.inputs['Height'])
    fine=node('ShaderNodeBump');fine.inputs['Strength'].default_value=.18;fine.inputs['Distance'].default_value=.00035
    l.new(micro.outputs['Fac'],fine.inputs['Height']);l.new(bump.outputs[0],fine.inputs['Normal']);l.new(fine.outputs[0],bs.inputs['Normal'])
    rough=node('ShaderNodeMapRange');l.new(mottled.outputs['Fac'],rough.inputs['Value'])
    rough.inputs['To Min'].default_value=.26 if metallic else .48
    rough.inputs['To Max'].default_value=.49 if metallic else .82
    l.new(rough.outputs[0],bs.inputs['Roughness'])
    return m


def palette():
    return {
        'walls':[surface('Ivory small tile',(.60,.565,.48),True),
                 surface('Grey mosaic',(.48,.50,.465),True),
                 surface('Aged plaster',(.53,.51,.46)),
                 surface('Oxide tile',(.31,.15,.105),'brick'),
                 surface('Off white mosaic',(.54,.535,.48),True),
                 surface('Ochre plaster',(.43,.38,.275))],
        'concrete':surface('Concrete',(.28,.275,.25)),
        'plaster':surface('Roof plaster',(.64,.63,.57)),
        'repair':surface('Repair plaster',(.33,.335,.30)),
        'steel':surface('Weathered steel',(.17,.19,.18),metallic=.65),
        'rust':surface('Rust seams',(.23,.10,.044),metallic=.22),
        'silver':material('v03 Brushed stainless',(.55,.57,.56),metallic=.92,roughness=.22),
        'frame':surface('Aluminium window frames',(.39,.40,.37),metallic=.75),
        'glass':material('v03 Dark reflective glazing',(.048,.07,.075),metallic=.48,roughness=.16),
        'glassblue':material('v03 Blue glass',(.075,.13,.15),metallic=.52,roughness=.12),
        'interior':material('v03 Interior shade',(.043,.038,.031)),
        'curtain':surface('Linen curtains',(.40,.36,.29)),
        'ac':surface('Old AC enamel',(.53,.51,.42)),
        'plastic':surface('Cream PVC',(.51,.50,.445)),
        'rubber':material('v03 Cable rubber',(.018,.020,.018)),
        'pot':surface('Old terracotta',(.29,.115,.065)),
        'leaves':[material('v03 Leaf '+str(i),c,roughness=.63) for i,c in enumerate([(.08,.15,.026),(.12,.22,.05),(.18,.24,.085)])],
        'cloth':[surface('Fabric '+str(i),c) for i,c in enumerate([(.49,.48,.43),(.045,.10,.17),(.29,.14,.12),(.12,.19,.17)])],
        'roof':[surface('Roof panel '+str(i),c,metallic=.46) for i,c in enumerate([(.07,.18,.23),(.20,.24,.19),(.34,.33,.29),(.30,.14,.09),(.20,.26,.27),(.31,.315,.29)])],
    }
