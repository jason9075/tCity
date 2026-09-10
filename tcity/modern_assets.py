"""Modern Taiwanese residential modules; original geometry informed by photos.

A catalog entry is a nested collection of shared base/floor/roof meshes. Every
storey remains 3.1 m high; changing storeys selects a different composition,
never stretches the entire tower vertically. Source photographs are not bundled.
"""
import math
import random
import bpy
from mathutils import Vector, Matrix
from .assets import MeshBuilder, material
from .surfaces import surface, palette as residential_palette
from .lived_in import rod, cable, ring, plant, water_tank
from .farm_assets import palette as plant_palette
from .rural_assets import woodland

MIN_FLOORS=6
MAX_FLOORS=24
PODIUM_HEIGHT=4.5
FLOOR_HEIGHT=3.1
SITE_WIDTH=60.
SITE_DEPTH=48.
CATALOG='TCity • Modern communities v0.1'
TREE_POSITIONS=[(-26,-17),(-26,-7),(-26,16),(26,-17),(26,-7),(26,3),(-18,-13),(18,-13)]


def palette(style):
    colors=[(.49,.46,.39),(.46,.48,.465),(.61,.585,.52)]
    p={'wall':surface('Modern facade '+str(style),colors[style],tile=True),
       'frame':surface('Modern light stone '+str(style),tuple(v*1.15 for v in colors[style])),
       'dark':surface('Modern dark cladding',(.09,.105,.104)),
       'joint':material('Modern recessed joints',(.045,.05,.045)),
       'metal':material('Modern charcoal aluminium',(.095,.115,.118),.55,.36),
       'glass':material('Modern blue grey glazing',(.13,.23,.245),.3,.18),
       'railglass':material('Modern balcony laminated glass',(.16,.25,.24),.22,.20),
       'interior':material('Modern room shadow',(.035,.043,.040)),
       'curtain':material('Modern warm curtains',(.42,.40,.34)),
       'wood':surface('Modern timber soffit',(.25,.145,.075)),
       'paving':surface('Modern plaza stone',(.36,.355,.32)),
       'soil':surface('Modern planting soil',(.075,.065,.04)),
       'grass':surface('Modern lawn',(.10,.18,.038)),
       'white':material('Modern lane white',(.73,.73,.67)),
       'light':material('Modern warm fixtures',(.72,.59,.37))}
    p['glass'].node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=.20
    p['railglass'].node_tree.nodes.get('Principled BSDF').inputs['Transmission Weight'].default_value=.46
    return p


def transformed(dst,src,translation=(0,0,0),angle=0):
    rot=Matrix.Rotation(angle,3,'Z');offset=Vector(translation)
    for idx,mat in enumerate(src.materials):
        faces=[f for f,m in zip(src.faces,src.indices) if m==idx]
        smooth=[s for s,m in zip(src.smooth,src.indices) if m==idx]
        used=sorted({i for face in faces for i in face})
        remap={old:new for new,old in enumerate(used)}
        dst.add([tuple(rot@Vector(src.verts[i])+offset) for i in used],
                [tuple(remap[i] for i in face) for face in faces],mat,smooth)


def glazing(b,x,y,z,w,h,p,curtain=False):
    b.box((x,y+.055,z),(w,.07,h),p['glass'])
    for dx in (-w/2,0,w/2):b.box((x+dx,y-.015,z),(.045,.075,h+.06),p['metal'])
    for dz in (-h/2,h/2):b.box((x,y-.015,z+dz),(w+.06,.075,.045),p['metal'])
    if curtain:
        for j in range(6):b.box((x-w*.39+j*w*.045,y+.11,z),(.11,.04,h*.97),p['curtain'])


def balcony(b,x,y,width,p,style,seed):
    # Actual terrace floor and recessed glazing; every railing is detached from
    # the room facade by 1.5–2.3 metres, producing the shadow depth in the photos.
    rng=random.Random(seed);depth=2.25 if style==2 else 1.65
    outer=y-depth
    if style==2:
        # Gently bowed balcony edge, inspired by the observed rounded fronts.
        points=[(x-width/2+width*j/12,outer-.27*math.sin(j*math.pi/12),.12) for j in range(13)]
        outline=[(x-width/2,y),(x+width/2,y)]+[(xx,yy) for xx,yy,_ in reversed(points)]
        n=len(outline)
        verts=[(xx,yy,z) for z in (-.08,.18) for xx,yy in outline]
        faces=[tuple(range(n)),tuple(reversed(range(n,2*n)))]
        faces += [((j+1)%n,j,j+n,(j+1)%n+n) for j in range(n)]
        b.add(verts,faces,p['frame'])
        for a,c in zip(points,points[1:]):
            rod(b,(a[0],a[1],1.15),(c[0],c[1],1.15),.025,p['metal'],6)
            for t in (0,.5):
                xx=a[0]+(c[0]-a[0])*t;yy=a[1]+(c[1]-a[1])*t
                rod(b,(xx,yy,.18),(xx,yy,1.15),.011,p['metal'],6)
    else:
        b.box((x,(y+outer)/2,.04),(width,depth,.22),p['frame'])
        b.box((x,outer, .38),(width,.16,.50),p['wall'])
        b.box((x,outer-.015,.89),(width-.08,.035,.62),p['railglass'])
        rod(b,(x-width/2,outer,1.23),(x+width/2,outer,1.23),.025,p['metal'])
        for j in range(5):rod(b,(x-width/2+j*width/4,outer,.65),(x-width/2+j*width/4,outer,1.23),.018,p['metal'],6)
    for dx in (-width/2,width/2):
        b.box((x+dx,(y+outer)/2,.68),(.12,depth,1.2),p['wall'])
    glazing(b,x,y-.03,1.62,width-.55,2.55,p,rng.random()<.6)
    if style==2 or rng.random()<.28:
        rp=residential_palette()
        for j in range(2):plant(b,(x-width*.33+j*.45,outer+.40,.18),.52,rp,seed+j)
    # Soffit and a small ceiling fixture remain below the floor above.
    b.box((x,(y+outer)/2,3.02),(width,depth,.06),p['wood'] if style==2 else p['frame'])
    b.box((x,y-.8,2.97),(.16,.16,.035),p['light'])


def floor_mesh(style,variation):
    p=palette(style);b=MeshBuilder();rng=random.Random(100+style*13+variation)
    # Keep the room core behind the sliding doors, including their curtains.
    b.box((0,.675,1.55),(16.7,12.25,3.1),p['interior'])
    b.box((0,.3,.015),(18.0,16.0,.22),p['frame'])
    # Front: two deep balconies, a vertical service/window bay at each side.
    for x in (-4.15,4.15):balcony(b,x,-5.65,6.6,p,style,style*100+variation*7+int(x*3))
    for x in (-8.35,0,8.35):b.box((x,-5.63,1.55),(.42,.40,3.1),p['wall'])
    for x in (-8.85,8.85):b.box((x,-6.30,1.55),(.32,2.15,3.1),p['dark'])
    # The rear and both sides receive real windows and screened service areas.
    for angle,y,w in [(math.pi,-6.8,17.2),(math.pi/2,-8.4,12.3),(-math.pi/2,-8.4,12.3)]:
        face=MeshBuilder();face.box((0,y+.12,1.55),(w,.22,3.1),p['wall'])
        for x in (-w*.31,0,w*.31):
            glazing(face,x,y-.015,1.62,2.15,1.95,p,rng.random()<.45)
            face.box((x,y-.16,.48),(2.4,.32,.15),p['frame'])
        face.box((w*.30,y-.24,2.48),(2.25,.65,.14),p['frame'])
        # Condensers sit behind louvers instead of protruding randomly.
        face.box((w*.30,y-.33,1.70),(1.55,.4,.80),p['metal'])
        for j in range(10):face.box((w*.30,y-.61,1.2+j*.105),(2.1,.045,.035),p['metal'])
        transformed(b,face,angle=angle)
    # Continuous facade ribs, shadow joints and floor-level stone bands.
    for x in (-8.95,8.95):
        for y in (-6.8,6.8):b.box((x,y,1.55),(.30,.42,3.1),p['frame'])
    for y in (-5.8,7.0):b.box((0,y,.27),(17.5,.09,.055),p['joint'])
    return b


def tower_centers(style):return [(0,5)] if style==0 else [(-14,4),(14,4)]


def ground_floor(b,p):
    b.box((0,.3,.16),(18.6,16.8,.32),p['dark'])
    b.box((0,.5,2.25),(16.5,12.7,4.5),p['interior'])
    for x in (-8.5,-3.2,3.2,8.5):b.box((x,-6.0,2.25),(.65,.75,4.5),p['dark'])
    for x in (-5.75,0,5.75):glazing(b,x,-5.88,2.23,4.6,3.85,p)
    b.box((0,-7.5,3.65),(8.4,4.0,.24),p['dark'])
    for x in (-3.9,3.9):b.box((x,-9.15,1.88),(.12,.15,3.5),p['metal'])
    for angle in (math.pi/2,math.pi,-math.pi/2):
        wall=MeshBuilder();wall.box((0,-6.5,2.25),(16.7,.22,4.5),p['dark'])
        for x in (-5,0,5):glazing(wall,x,-6.63,2.2,3.8,3.4,p)
        transformed(b,wall,angle=angle)
    b.box((0,0,4.43),(18.4,16.7,.25),p['frame'])


def arc_path(b,cx,cy,r0,r1,start,end,p):
    segments=48;verts=[]
    for j in range(segments+1):
        t=start+(end-start)*j/segments
        verts.extend([(cx+r0*math.cos(t),cy+r0*math.sin(t),.045),(cx+r1*math.cos(t),cy+r1*math.sin(t),.045)])
    b.add(verts,[(2*j,2*j+2,2*j+3,2*j+1) for j in range(segments)],p['paving'])


def base_mesh(style):
    p=palette(style);b=MeshBuilder()
    # A connected plaza and garden fit wholly inside the standard 60 × 48 site.
    b.box((0,0,-.04),(59.4,47.4,.08),p['paving'])
    for cx,cy in tower_centers(style):
        tower=MeshBuilder();ground_floor(tower,p);transformed(b,tower,(cx,cy,0))
    for x in (-22,22):b.box((x,-14,.01),(12,11,.035),p['grass'])
    if style==0:b.box((-19,5,.01),(13,23,.035),p['grass'])
    # Concentric walking paths echo the shared public setback in the Qingpu photo.
    for r in (6.5,9.1):arc_path(b,0,-14,r,r+1.25,0,math.pi,p)
    b.box((0,-19,.028),(5.0,9.3,.05),p['paving'])
    for x,y in TREE_POSITIONS[:6]:
        b.box((x,y,.36),(2.3,2.3,.72),p['dark']);b.box((x,y,.73),(2.05,2.05,.04),p['soil'])
    # A ramp canopy and a dark below-grade opening communicate underground parking.
    b.box((24,16,.022),(5.2,10,.045),p['interior'])
    b.box((24,18,2.65),(5.8,5,.22),p['dark'])
    for x in (21.3,26.7):b.box((x,16,.58),(.25,10,1.15),p['wall'])
    for x in (21.5,26.5):b.box((x,19,1.4),(.18,.18,2.8),p['metal'])
    b.box((24,11,.5),(.18,.18,1),p['metal']);b.box((24,11,1.),(4.6,.08,.07),p['white'])
    for y in (14,17,20):
        b.add([(23.6,y,.052),(24.4,y,.052),(24,y-1,.052)],[(0,1,2)],p['white'])
    for x in (-10,10):
        for z in (.45,.54):b.box((x,-17,z),(3.8,.5,.08),p['wood'])
        for dx in (-1.6,1.6):b.box((x+dx,-17,.22),(.10,.42,.44),p['metal'])
    # Human-height gate piers, mailboxes and bollards; clear pedestrian opening.
    for x in (-4.2,4.2):b.box((x,-22,1.05),(.55,.65,2.1),p['dark'])
    for x in (-6.4,-5.6,5.6,6.4):b.cylinder((x,-22,.40),.075,.8,p['metal'],10)
    b.box((6,-20,1.1),(2.3,.4,1.4),p['metal'])
    for row in range(4):
        for col in range(7):b.box((5.03+col*.32,-20.212,.62+row*.30),(.27,.02,.24),p['frame'])
    return b


def roof_mesh(style):
    p=palette(style);b=MeshBuilder();rp=residential_palette()
    b.box((0,.3,.04),(18.2,16.1,.25),p['frame'])
    for x in (-8.95,8.95):b.box((x,.3,.64),(.17,16,.95),p['wall'])
    for y in (-7.65,8.25):b.box((0,y,.64),(18,.17,.95),p['wall'])
    b.box((-.8,1.7,1.65),(6.5,7.0,3.2),p['dark'])
    b.box((-.8,1.7,3.35),(7.,7.5,.22),p['frame'])
    for x in (-4.0,2.4):b.box((x,1.7,2.4),(.22,7,4.5),p['frame'])
    for j in range(15):b.box((-.8,-1.86,.3+j*.21),(6.5,.045,.06),p['metal'])
    water_tank(b,5.0,4.5,.20,.78,rp);water_tank(b,5.0,1.6,.20,.78,rp)
    # Plant/screen equipment enclosure; tank bodies stay below the screening fins.
    for j in range(20):b.box((3.3+j*.22,6.0,1.45),(.09,.09,2.8),p['frame'])
    for y in (0,3):b.box((-5.9,y,.6),(2.0,2.0,1.1),p['metal'])
    return b


def ensure_modern_assets():
    if CATALOG in bpy.data.collections:return bpy.data.collections[CATALOG]
    catalog=bpy.data.collections.new(CATALOG);catalog.use_fake_user=True
    gardens=bpy.data.collections.new(CATALOG+' • Landscape');gardens.use_fake_user=True
    sources=bpy.data.collections.new('TCity • Modern shared mesh sources v0.1');sources.use_fake_user=True
    floors={};bases={};roofs={}
    for style in range(3):
        bases[style]=base_mesh(style).object('TC_MOD_SOURCE_Base_%d'%style,sources).data
        roofs[style]=roof_mesh(style).object('TC_MOD_SOURCE_Roof_%d'%style,sources).data
        for variation in range(4):floors[style,variation]=floor_mesh(style,variation).object('TC_MOD_SOURCE_Floor_%d_%d'%(style,variation),sources).data
    # Trees are shared objects inside each community collection, never realized
    # into all 57 height/style variants.
    pb=MeshBuilder();woodland(pb,plant_palette(),0)
    tree_mesh=pb.object('TC_MOD_SOURCE_PlazaTree',sources).data
    for style in range(3):
        garden=bpy.data.collections.new('TC_MOD_GARDEN_%d'%style);gardens.children.link(garden)
        for j,(x,y) in enumerate(TREE_POSITIONS):
            o=bpy.data.objects.new('TC_MOD_Landscape_%d_%d'%(style,j),tree_mesh);garden.objects.link(o)
            o.location=(x,y,.75 if abs(x)==26 else .04);o.scale=(.60,.60,.70)
            o['tc_modern_role']='Landscape';o['tc_modern_style']=style
    for storeys in range(MIN_FLOORS,MAX_FLOORS+1):
        for style in range(3):
            index=(storeys-MIN_FLOORS)*3+style
            site=bpy.data.collections.new('TC_MOD_SITE_%03d_%02dF_style%d'%(index,storeys,style));catalog.children.link(site)
            def obj(role,mesh,loc=(0,0,0),tower=-1,level=0,scale=(1,1,1)):
                o=bpy.data.objects.new('TC_MOD_%03d_%s_%d_%02d'%(index,role,tower,level),mesh);site.objects.link(o);o.location=loc;o.scale=scale
                for k,v in {'tc_modern_role':role,'tc_modern_style':style,'tc_modern_floors':storeys,'tc_tower':tower,'tc_level':level,'tc_modern_site':index}.items():o[k]=v
                return o
            obj('Base',bases[style])
            for ti,(x,y) in enumerate(tower_centers(style)):
                actual=storeys-2 if style==1 and ti==1 and storeys>=8 else storeys
                for level in range(1,actual):obj('Floor',floors[style,level%4],(x,y,PODIUM_HEIGHT+(level-1)*FLOOR_HEIGHT),ti,level)
                obj('Roof',roofs[style],(x,y,PODIUM_HEIGHT+(actual-1)*FLOOR_HEIGHT),ti,actual)
    return catalog
