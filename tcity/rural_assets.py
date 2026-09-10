"""Original rural homes and woodland kit, informed by real Taiwan photographs.
See docs/research/rural-landscape.md for observations and source attribution.
"""
import math
import random
from mathutils import Vector
from .assets import material
from .surfaces import surface, palette
from .sheds import sheet, sloped_roof, metal_palette
from .lived_in import rod, cable, water_tank, aircon, plant


def window(b,x,y,z,w,h,p):
    b.box((x,y+.035,z),(w,.075,h),p['dark'])
    for xx in (-w/2,0,w/2):b.box((x+xx,y-.025,z),(.034,.04,h+.06),p['steel'])
    for zz in (-h/2,h/2):b.box((x,y-.03,z+zz),(w+.05,.04,.035),p['steel'])
    for i in range(7):rod(b,(x-w*.43+i*w*.143,y-.12,z-h*.48),(x-w*.43+i*w*.143,y-.12,z+h*.48),.009,p['steel'],6)
    for zz in (-h*.33,h*.33):rod(b,(x-w*.5,y-.12,z+zz),(x+w*.5,y-.12,z+zz),.009,p['steel'],6)
    b.box((x,y-.08,z-h/2-.06),(w+.15,.28,.10),p['concrete'])


def front_wall(b,x0,x1,y,z0,z1,openings,wall,p):
    """Build actual door/window holes rather than laying dark cards on a box."""
    cursor=x0
    for x,w,z,h in sorted(openings):
        left,right=x-w/2,x+w/2
        if left>cursor:b.box(((cursor+left)/2,y,(z0+z1)/2),(left-cursor,.20,z1-z0),wall)
        if z-h/2>z0:b.box((x,y,(z0+z-h/2)/2),(w,.20,z-h/2-z0),wall)
        if z+h/2<z1:b.box((x,y,(z+h/2+z1)/2),(w,.20,z1-z-h/2),wall)
        cursor=right
    if cursor<x1:b.box(((cursor+x1)/2,y,(z0+z1)/2),(x1-cursor,.20,z1-z0),wall)


def roof(b,x0,x1,y0,y1,eave,ridge,metal,p):
    mid=(x0+x1)/2
    for a,c,l,r in [(x0,mid,eave,ridge),(mid,x1,ridge,eave)]:sloped_roof(b,a,c,y0,y1,l,r,metal,p['steel'])
    rod(b,(mid,y0,ridge+.04),(mid,y1,ridge+.04),.075,metal)
    for x in (x0,x1):
        b.box((x, (y0+y1)/2,eave-.04),(.15,y1-y0,.13),p['steel'])
        cable(b,[(x,y0+.25,eave),(x,y0+.25,.22),(x+.25,y0+.25,.08)],.038,p['pipe'])


def farmhouse(b,variant):
    rp=palette();metals=metal_palette()
    p={'steel':surface('Rural zinc frames',(.34,.37,.34),metallic=.55),
       'dark':material('Rural interior',(.023,.03,.027)),
       'concrete':surface('Rural yard concrete',(.29,.28,.25)),
       'pipe':material('Rural PVC',(.39,.40,.36))}
    brick=surface('Rural exposed red brick',(.30,.115,.066),tile='brick')
    plaster=surface('Rural patched cement',(.40,.385,.32))
    if variant==0:
        # Compact postwar RC home: recessed front balcony, tiled walls, roof core
        # and utility tank; a modest working house rather than a villa.
        wall=surface('Rural cream mosaic',(.47,.435,.35),tile=True)
        b.box((0,0,.08),(8.6,12,.16),p['concrete'])
        for x in (-3.4,3.4):b.box((x,1,3.05),(.20,7,6.1),wall)
        b.box((0,4.4,3.05),(6.8,.2,6.1),wall)
        for z in (.20,3.12,6.15):b.box((0,1,z),(7,7,.18),p['concrete'])
        for z in (1.65,4.65):
            front_wall(b,-3.4,3.4,-2.45,z-1.5,z+1.5,[(-1.8,1.35,z,1.35),(1.25,1.5,z,1.35)],wall,p)
            for x,w in [(-1.8,1.35),(1.25,1.5)]:window(b,x,-2.55,z,w,1.35,p)
        b.box((0,-3.12,3.12),(7.3,1.6,.18),p['concrete'])
        for x in (-3.45,3.45):b.box((x,-3.12,4.64),(.16,1.6,3),wall)
        for x in (-3.3,0,3.3):rod(b,(x,-3.86,3.22),(x,-3.86,4.23),.025,p['steel'])
        for z in (3.5,3.84,4.21):rod(b,(-3.35,-3.86,z),(3.35,-3.86,z),.022,p['steel'])
        for i in range(27):rod(b,(-3.3+i*.25,-3.86,3.22),(-3.3+i*.25,-3.86,4.21),.008,p['steel'],6)
        for x in (-3.45,3.45):b.box((x,1,6.56),(.14,7.2,.68),wall)
        for y in (-2.5,4.5):b.box((0,y,6.56),(7,.14,.68),wall)
        b.box((-1.7,2.7,7.24),(2.4,2.7,2.15),plaster)
        sloped_roof(b,-3.05,-.35,1.15,4.2,8.4,8.22,metals[3],p['steel'])
        water_tank(b,1.55,2.8,6.25,.64,rp)
        aircon(b,2.2,-2.85,2.6,rp,51)
        sloped_roof(b,-3.7,3.7,-5.4,-3.1,2.8,3.2,metals[1],p['steel'])
        for x in (-3.6,3.6):rod(b,(x,-5.25,.1),(x,-5.25,2.8),.038,p['steel'])
        for j in range(4):plant(b,(-2.7+j*.65,-5.55,.16),.7,rp,90+j)
        return
    # The older type combines brickwork, partial cement repairs, mixed metal
    # roofs, small barred openings and a modest working yard.
    b.box((0,-.5,.07),(12.6,13,.14),p['concrete'])
    x0,x1,y0,y1=-5.6,5.6,-1.9,4.2
    wall_h=3.35
    for x in (x0,x1):b.box((x,(y0+y1)/2,wall_h/2),(.20,y1-y0,wall_h),brick)
    b.box((0,y1,wall_h/2),(x1-x0,.2,wall_h),brick)
    openings=[(-3.5,1.2,1.7,1.0),(0,1.35,1.18,2.20),(3.25,1.1,1.7,1.)]
    front_wall(b,x0,x1,y0,0,wall_h,openings,brick,p)
    # Irregular patches stop below the exposed brick, as in the reference photos.
    for x,w,h in [(-4.8,1.3,.95),(-1.9,1.6,1.1),(1.7,1.55,.87),(4.8,1.35,1.04)]:b.box((x,y0-.108,h/2),(w,.016,h),plaster)
    for x,w in [(-3.5,1.2),(3.25,1.1)]:window(b,x,y0-.03,1.7,w,1,p)
    b.box((0,y0+.08,1.1),(1.35,.08,2.2),p['dark'])
    for x in (-.67,.67):b.box((x,y0-.08,1.13),(.045,.1,2.3),p['steel'])
    b.box((-.49,y0-.15,1.12),(.34,.055,2.18),metals[3])
    for y in (y0,y1):b.add([(x0,y,wall_h),(x1,y,wall_h),(0,y,4.58)],[(0,1,2)],brick)
    roof(b,-5.87,5.87,y0-.32,y1+.28,3.52,4.65,metals[2 if variant==1 else 3],p)
    cable(b,[(-5.4,y0-.15,2.8),(0,y0-.16,2.6),(5.4,y0-.15,2.9)],.012,p['dark'])
    if variant==2:
        # Short wing creates an L-shaped house and an enclosed working corner.
        b.box((-4.1,-3.4,1.45),(3.,3.3,2.9),brick)
        roof(b,-5.8,-2.4,-5.3,-1.7,3.0,3.65,metals[1],p)
        b.box((-2.56,-3.55,1.2),(.08,1.4,2.4),p['dark'])
    else:
        sloped_roof(b,-5.7,5.7,-4.0,-2.1,2.7,3.18,metals[3],p['steel'])
        for x in (-5.4,5.4):rod(b,(x,-3.9,.12),(x,-3.9,2.72),.045,p['steel'])
    # Small cement service annex and an external stair with a tank platform.
    b.box((4.2,2.8,3.5),(2.25,2.7,.16),p['concrete']);water_tank(b,4.2,2.8,3.58,.51,rp)
    for j in range(11):b.box((5.95,3.7-j*.35,(j+1)*.145),(.55,.38,(j+1)*.29),plaster)
    for k in range(4):b.cylinder((1.8+k*.40,y0-.45,.25),.16,.50,metals[k%3],12)
    for j in range(5):plant(b,(-1.6+j*.53,-5.8,.15),.6,rp,510+j)
    b.box((1.4,-3.9,.25),(1.1,.75,.35),metals[3])
    for k in range(5):b.box((1.4,-3.9,.45+k*.055),(1.1,.08,.04),rp['wood'] if 'wood' in rp else p['concrete'])


def woodland(b,p,variant):
    rng=random.Random(902+variant)
    if variant==1:
        # A clump of culms with narrow leaves, rather than a sphere on a stick.
        for k in range(15):
            x,y=rng.uniform(-.75,.75),rng.uniform(-.75,.75);h=rng.uniform(4.2,6.7)
            tip=Vector((x*1.7,y*1.7,h));base=Vector((x,y,0))
            rod(b,base,tip,.038,p['stem'],6)
            for j in range(12):
                c=base.lerp(tip,j/12);rod(b,c,c+Vector((0,0,.024)),.045,p['leaves'][2],6)
            for j in range(70):
                t=rng.uniform(.5,1);c=base.lerp(tip,t)+Vector((rng.uniform(-.65,.65),rng.uniform(-.65,.65),0))
                a=rng.random()*math.tau;d=Vector((math.cos(a),math.sin(a),-.35))*.30;s=Vector((-math.sin(a),math.cos(a),0))*.023
                b.add([tuple(v) for v in (c-d,c+s,c+d,c-s)],[(0,1,2,3)],p['leaves'][rng.choice([0,1,2,5])])
        return
    rod(b,(0,0,0),(.12,0,3.5),.16,p['trunk'])
    for k in range(14):
        a=k*2.4;end=Vector((math.cos(a)*rng.uniform(.7,1.4),math.sin(a)*rng.uniform(.7,1.4),rng.uniform(3.1,5.3)))
        rod(b,(0,0,1.6),end,.055,p['trunk'],6)
        for j in range(135):
            theta=rng.random()*math.tau;zz=rng.uniform(-1,1);r=rng.random()**(1/3)*.85
            c=end+Vector((math.cos(theta)*math.sqrt(1-zz*zz)*r,math.sin(theta)*math.sqrt(1-zz*zz)*r,zz*r*.7))
            a=rng.random()*math.tau;d=Vector((math.cos(a),math.sin(a),rng.uniform(-.5,.5)))*rng.uniform(.13,.24);s=Vector((-math.sin(a),math.cos(a),0))*.085
            b.add([tuple(v) for v in (c-d,c+s,c+d,c-s,c+Vector((0,0,.055)))],[(0,1,4),(1,2,4),(2,3,4),(3,0,4)],p['leaves'][rng.choice([0,1,2,5,5])])
