"""Original farm kit: rice tufts, vegetables, orchard trees and rural facilities.

Meshes are built once. Placement, crop choice and clipping stay in Geometry Nodes.
"""
import math
import random
import bpy
from mathutils import Vector
from .assets import MeshBuilder, material
from .surfaces import surface
from .sheds import sheet, sloped_roof, metal_palette
from .lived_in import rod, cable, water_tank, aircon


def field_material(name, color, rows=False, wet=False):
    m=material('Farm / '+name,color,roughness=.9 if not wet else .19)
    if m.node_tree.nodes.get('Farm coordinates'):return m
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
    tex=n.new('ShaderNodeTexCoord');tex.name='Farm coordinates'
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=2.8
    noise.inputs['Detail'].default_value=4;l.new(tex.outputs['Object'],noise.inputs['Vector'])
    mix=n.new('ShaderNodeMixRGB');l.new(noise.outputs['Fac'],mix.inputs[0])
    mix.inputs[1].default_value=(*(c*.70 for c in color),1)
    mix.inputs[2].default_value=(*(c*1.12 for c in color),1)
    l.new(mix.outputs[0],bs.inputs['Base Color'])
    macro=n.new('ShaderNodeTexNoise');macro.inputs['Scale'].default_value=.085;macro.inputs['Detail'].default_value=2
    l.new(tex.outputs['Object'],macro.inputs['Vector'])
    mottled=n.new('ShaderNodeMixRGB');mottled.blend_type='MULTIPLY';mottled.inputs[0].default_value=.55
    l.new(mix.outputs[0],mottled.inputs[1]);l.new(macro.outputs['Fac'],mottled.inputs[2]);l.new(mottled.outputs[0],bs.inputs['Base Color'])
    height=noise.outputs['Fac']
    if rows:
        wave=n.new('ShaderNodeTexWave');wave.bands_direction='X';wave.wave_profile='SIN'
        wave.inputs['Scale'].default_value=1.3;wave.inputs['Distortion'].default_value=.08
        l.new(tex.outputs['Object'],wave.inputs['Vector']);height=wave.outputs['Fac']
        furrow=n.new('ShaderNodeMixRGB');furrow.blend_type='MULTIPLY';furrow.inputs[0].default_value=.42
        l.new(mottled.outputs[0],furrow.inputs[1]);l.new(height,furrow.inputs[2]);l.new(furrow.outputs[0],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.28
    bump.inputs['Distance'].default_value=.004 if wet else (.065 if rows else .025)
    l.new(height,bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return m


def palette():
    return {
        'fields':[field_material('Young paddy',(.068,.105,.032)),
                  field_material('Ripening paddy',(.18,.18,.055)),
                  field_material('Vegetable beds',(.095,.073,.040),True),
                  field_material('Orchard floor',(.075,.105,.042)),
                  field_material('Fallow furrows',(.20,.155,.092),True),
                  field_material('Flooded mud',(.073,.10,.079),wet=True),
                  field_material('Farmyard earth',(.14,.15,.08)),
                  field_material('Woodland leaf litter',(.065,.084,.029))],
        'bund':field_material('Grass and earth bund',(.15,.18,.072)),
        'road':field_material('Faded rural asphalt',(.12,.125,.116)),
        'concrete':field_material('Irrigation concrete',(.31,.32,.275)),
        'water':field_material('Canal water',(.045,.095,.075),wet=True),
        'leaves':[material('Farm / Leaf '+str(i),c,roughness=.72) for i,c in enumerate(
            [(.07,.19,.018),(.14,.255,.032),(.22,.29,.047),(.32,.32,.066),(.42,.36,.10),(.038,.115,.02)])],
        'stem':material('Farm / Stems',(.22,.25,.07)),
        'trunk':surface('Farm bark',(.15,.11,.064)),
    }


def rice(b,p,ripe=False):
    rng=random.Random(108+int(ripe));leaves=p['leaves'][2:5] if ripe else p['leaves'][:3]
    # Arched tapered blades with a raised midrib. No alpha cards or billboards.
    for j in range(24):
        angle=rng.random()*math.tau;h=rng.uniform(.48,.88)*(1.1 if ripe else 1)
        reach=rng.uniform(.17,.37);dx,dy=math.cos(angle),math.sin(angle)
        base=Vector((rng.uniform(-.09,.09),rng.uniform(-.09,.09),0))
        verts=[]
        for k in range(4):
            t=k/3;center=base+Vector((dx*reach*t*t,dy*reach*t*t,h*(1.4*t-.52*t*t)))
            width=.019*math.sin((.10+t*.90)*math.pi)
            verts.extend([tuple(center+Vector((-dy*width,dx*width,0))),tuple(center+Vector((dy*width,-dx*width,0)))])
        b.add(verts,[(2*k,2*k+1,2*k+3,2*k+2) for k in range(3)],rng.choice(leaves))
        if ripe and j%4==0:
            tip=base+Vector((dx*reach,dy*reach,h*.88))
            for k in range(4):
                c=tip+Vector((dx*k*.018,dy*k*.018,-k*.026))
                b.add([tuple(c+Vector(v)) for v in [(-.018,0,0),(0,.018,0),(.018,0,0),(0,-.018,0),(0,0,.043)]],
                      [(0,1,4),(1,2,4),(2,3,4),(3,0,4)],p['leaves'][4])


def vegetable(b,p):
    rng=random.Random(61)
    for i in range(11):
        a=i*2.4;reach=rng.uniform(.18,.34);h=rng.uniform(.12,.27)
        d=Vector((math.cos(a),math.sin(a),0));side=Vector((-math.sin(a),math.cos(a),0))*.09
        base=Vector((0,0,.03));mid=d*reach*.6+Vector((0,0,h));tip=d*reach+Vector((0,0,h*.58))
        b.add([tuple(v) for v in [base,mid+side,tip,mid-side,mid+Vector((0,0,.045))]],
              [(0,1,4),(1,2,4),(2,3,4),(3,0,4)],p['leaves'][i%3])


def orchard(b,p):
    rng=random.Random(881);rod(b,(0,0,0),(.08,0,1.9),.105,p['trunk'])
    for k in range(9):
        a=k*2.4;end=Vector((math.cos(a)*rng.uniform(.6,1.0),math.sin(a)*rng.uniform(.6,1),rng.uniform(1.7,2.65)))
        rod(b,(0,0,.9),end,.039,p['trunk'],6)
        # Small intersecting folded leaves form an irregular, porous crown.
        for j in range(100):
            theta=rng.random()*math.tau;zz=rng.uniform(-1,1);r=rng.random()**(1/3)*.67
            c=end+Vector((math.cos(theta)*math.sqrt(1-zz*zz)*r,math.sin(theta)*math.sqrt(1-zz*zz)*r,zz*r*.8))
            a=rng.random()*math.tau;d=Vector((math.cos(a),math.sin(a),rng.uniform(-.5,.5)))*rng.uniform(.10,.19)
            s=Vector((-math.sin(a),math.cos(a),0))*.058
            b.add([tuple(v) for v in [c-d,c+s,c+d,c-s,c+Vector((0,0,.035))]],
                  [(0,1,4),(1,2,4),(2,3,4),(3,0,4)],p['leaves'][rng.choice([0,1,2,5,5])])


def facility(b,p,variant):
    concrete=p['concrete'];steel=material('Farm / Galvanized frame',(.36,.40,.38),.7,.39)
    dark=material('Farm / Recess',(.023,.029,.027));metals=metal_palette()
    if variant==1:
        # Agricultural tunnel: translucent film, visible hoops and an open door.
        film=material('Farm / Translucent PE film',(.57,.63,.54),roughness=.38)
        bs=film.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=.36
        for lane in (-2.7,2.7):
            verts=[]
            for y in (-7,7):
                for j in range(17):
                    a=j*math.pi/16;verts.append((lane+2.45*math.cos(a),y,1.+2.05*math.sin(a)))
            b.add(verts,[(j,j+1,18+j,17+j) for j in range(16)],film,True)
            for y in range(-7,8,2):
                pts=[(lane+2.45*math.cos(j*math.pi/16),y,1+2.05*math.sin(j*math.pi/16)) for j in range(17)]
                cable(b,[(lane-2.45,y,0)]+list(reversed(pts))+[(lane+2.45,y,0)],.027,steel)
            for x in (-2.45,2.45):
                b.box((lane+x,0,.5),(.035,14,1),film)
            b.box((lane,0,.035),(4.7,13.8,.07),p['fields'][2])
            for x in (-1.6,-.8,0,.8,1.6):b.box((lane+x,0,.09),(.53,13,.11),dark)
        return
    if variant==0:
        b.box((0,0,.12),(9.5,13,.24),concrete)
        for x in (-4.1,4.1):
            sheet(b,(x,-5.5,.25),(0,11,0),(0,0,3.5),metals[3])
            for y in (-5.5,0,5.5):rod(b,(x,y,.1),(x,y,3.8),.065,steel)
        sheet(b,(-4.1,5.5,.25),(8.2,0,0),(0,0,3.5),metals[3])
        b.box((0,-5.49,1.9),(5.8,.06,3.2),dark)
        for x in (-3.55,3.55):sheet(b,(x-.55,-5.53,.25),(1.1,0,0),(0,0,3.5),metals[3])
        for x0,x1,l,r in [(-4.35,0,3.82,4.8),(0,4.35,4.8,3.82)]:
            sloped_roof(b,x0,x1,-5.8,5.8,l,r,metals[1],steel)
        for k in range(6):b.box((-2.0+k*.7,-5.56,3.55),( .67,.06,.31),metals[3])
        for k in range(4):b.box((2.4,3.6+k*.4,.6),(.8,.35,1.0),concrete)
    else:
        wall=surface('Farmhouse plaster',(.48,.46,.38))
        b.box((0,0,2.7),(7,9,5.4),wall)
        b.box((0,0,5.43),(7.3,9.3,.18),concrete)
        for x in (-3.45,3.45):b.box((x,0,5.8),(.13,9.2,.65),wall)
        for y in (-4.45,4.45):b.box((0,y,5.8),(7,.13,.65),wall)
        for z in (1.5,4.):
            for x in (-2.1,1.8):
                b.box((x,-4.515,z),(1.3,.06,1.15),dark)
                for dx in (-.65,0,.65):b.box((x+dx,-4.57,z),(.035,.045,1.18),steel)
                for dz in (-.56,0,.56):b.box((x,-4.58,z+dz),(1.34,.04,.025),steel)
        b.box((0,-4.56,1.03),(1.2,.07,2.05),metals[3])
        sloped_roof(b,-3.7,3.7,-6.0,-4.4,2.4,2.7,metals[0],steel)
        from .surfaces import palette as residential_palette
        rp=residential_palette();water_tank(b,1.6,2.2,5.53,.65,rp)
        aircon(b,2,-4.75,3.15,rp,1)
    b.cylinder((4.5,4,.64),.42,1.25,metals[0],16)
    rod(b,(4.5,4,.05),(4.5,2,.05),.035,steel)


def ensure_farm_assets():
    name='TCity • Farm kit v0.2'
    if name in bpy.data.collections:return bpy.data.collections[name]
    col=bpy.data.collections.new(name);col.use_fake_user=True;p=palette()
    for m in p['leaves']:
        n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
        geo=n.new('ShaderNodeNewGeometry');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=.11
        l.new(geo.outputs['Position'],noise.inputs['Vector'])
        mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=.44
        mix.inputs[1].default_value=m.diffuse_color;l.new(noise.outputs['Fac'],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs['Base Color'])
        bs.inputs['Subsurface Weight'].default_value=.035
    builders=[lambda b:rice(b,p),lambda b:rice(b,p,True),lambda b:vegetable(b,p),lambda b:orchard(b,p)]
    builders += [lambda b,v=v:facility(b,p,v) for v in range(3)]
    def grass(b):
        rice(b,p)
        b.verts=[(x*.32,y*.32,z*.24) for x,y,z in b.verts]
    builders.append(grass)
    from .rural_assets import farmhouse,woodland
    builders[6]=lambda b:farmhouse(b,0)
    builders.extend([lambda b:farmhouse(b,1),lambda b:farmhouse(b,2),lambda b:woodland(b,p,0),lambda b:woodland(b,p,1)])
    for i,build in enumerate(builders):
        b=MeshBuilder();build(b);obj=b.object('TC_FARM_%02d_'%i+['Rice_green','Rice_gold','Vegetables','Orchard','Metal_shed','Growing_tunnels','Farmhouse','Bund_grass','Brick_farmhouse','Courtyard_home','Woodland_tree','Bamboo_clump'][i],col)
        obj['tc_farm_asset']=i;obj.use_fake_user=True
    return col
