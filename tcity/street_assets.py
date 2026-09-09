"""Original Taiwanese street infrastructure. Fixed metre dimensions, +Z up, front -Y."""
import math
import bpy
from mathutils import Vector
from .assets import MeshBuilder,material
from .surfaces import surface
from .lived_in import rod,cable,ring


def ensure_street_assets():
    name='TCity • Street infrastructure v0.4'
    if name in bpy.data.collections:return {o['tc_infra_kind']:o for o in bpy.data.collections[name].objects}
    coll=bpy.data.collections.new(name);coll.use_fake_user=True
    concrete=surface('Pole concrete',(.40,.405,.375));steel=surface('Pole galvanized fittings',(.34,.36,.34),metallic=.7)
    black=material('v04 Cable rubber',(.015,.018,.019),roughness=.57)
    yellow=material('v04 Pole warning yellow',(.72,.47,.035),roughness=.72)
    porcelain=material('v04 Brown porcelain',(.16,.075,.043),roughness=.24)
    green=surface('Telecom cabinet paint',(.40,.47,.39),metallic=.28)
    dark=material('v04 Vents and keyholes',(.025,.033,.027))
    blue=material('v04 Pole ID blue',(.035,.12,.22))
    silver=material('v04 Equipment labels',(.63,.65,.61),metallic=.4)
    out={}
    def finish(b,kind):
        o=b.object('TC_INF_'+kind,coll);o['tc_infra_kind']=kind;out[kind]=o
        return o
    b=MeshBuilder()
    # Tapered reinforced-concrete pole, with diagonal black/yellow wrapping at the base.
    segments=32
    verts=[(r*math.cos(i*math.tau/segments),r*math.sin(i*math.tau/segments),z)
           for z,r in [(0,.19),(9,.11)] for i in range(segments)]
    b.add(verts,[tuple(reversed(range(segments))),tuple(range(segments,segments*2))]+
          [(i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments)],concrete,[False,False]+[True]*segments)
    for band in range(9):
        v=[]
        for j in range(segments+1):
            a=j*math.tau/segments
            for z in (.12+band*.19+a*.12,.12+(band+1)*.19+a*.12):
                r=.19-z*(.08/9)+.002
                v.append((r*math.cos(a),r*math.sin(a),z))
        b.add(v,[(2*j,2*j+2,2*j+3,2*j+1) for j in range(segments)],yellow if band%2 else black,True)
    b.box((0,-.189,2.8),(.18,.016,.26),blue)
    for j in range(3):b.box((0,-.200,2.87-j*.07),(.125,.004,.008),silver)
    # Pole straps, climbing pegs, crossarm and three high-level insulators.
    for z in (4.2,5.6,6.4,8.05):ring(b,(0,0,z),.19-z*.008,.018,steel,axis='Z')
    for j in range(11):
        z=3+j*.43;x=(-1)**j*.28
        rod(b,(0,.025,z),(x,.025,z),.018,steel)
    b.box((0,0,8.22),(.12,.93,.12),steel)
    for y in (-.38,0,.38):
        rod(b,(0,y,8.23),(0,y,8.66),.026,steel)
        for j in range(4):b.cylinder((0,y,8.31+j*.075),.069-.007*j,.035,porcelain,16)
    # Cylindrical transformer, bracket and guarded high-voltage lead on the street side.
    b.box((0,-.25,6.96),(.46,.48,.11),steel)
    b.cylinder((0,-.41,7.36),.22,.70,green,24)
    for z in (7.03,7.66):b.cylinder((0,-.41,z),.235,.045,steel,24)
    for x in (-.11,.11):
        rod(b,(x,-.41,7.70),(x,-.41,7.92),.023,porcelain)
    cable(b,[(.11,-.41,7.92),(.26,-.25,8.10),(.12,0,8.64),(0,0,8.66)],.016,black)
    # Telecom slack loop and splice housing below the power conductors.
    ring(b,(.12,-.24,6.10),.25,.020,black)
    b.box((-.16,-.17,5.79),(.16,.17,.34),dark)
    cable(b,[(0,-.18,.05),(0,-.18,5.3),(-.17,-.18,5.65)],.032,black)
    for y in (-.27,-.12):rod(b,(0,0,6.18),(0,y,6.18),.025,steel)
    finish(b,'Pole')
    b=MeshBuilder()
    b.box((0,0,.065),(1.08,.63,.13),concrete)
    b.box((0,0,.76),(.98,.48,1.27),green)
    b.box((0,0,1.42),(1.045,.55,.085),green)
    # Two service doors, fine panel seams, hinges, vents, lock, inventory label.
    for x in (-.246,.246):
        b.box((x,-.251,.78),(.466,.019,1.18),green)
        b.box((x,-.266,.20),(.405,.009,.016),dark)
        for j in range(9):b.box((x,-.266,1.22-j*.035),(.36,.018,.012),dark)
        for z in (.35,1.12):b.box((x+(-.215 if x<0 else .215),-.28,z),(.028,.03,.11),steel)
        b.box((x+(.16 if x<0 else -.16),-.276,.72),(.035,.025,.11),steel)
    b.box((0,-.266,.8),(.011,.015,1.18),dark)
    b.box((-.21,-.27,.89),(.19,.007,.10),silver)
    for j in range(3):b.box((-.21,-.275,.919-j*.023),(.14,.004,.006),dark)
    for x in (-.28,.28):rod(b,(x,.13,.04),(x,.13,.20),.026,steel)
    reflective=material('v04 Reflective orange',(.85,.17,.026),roughness=.28)
    white=material('v04 Reflective white',(.74,.75,.68),roughness=.32)
    for x in (-.472,.472):
        b.box((x,-.278,.80),(.047,.008,1.14),white)
        for j in range(6):
            z=.24+j*.185
            b.add([(x-.022,-.284,z),(x+.022,-.284,z+.045),(x+.022,-.284,z+.12),(x-.022,-.284,z+.075)],[(0,1,2,3)],reflective)
    for j in range(8):
        x=-.53+j*.132
        b.add([(x,-.318,.012),(x+.065,-.318,.012),(x+.131,-.318,.125),(x+.066,-.318,.125)],[(0,1,2,3)],yellow if j%2 else black)
    font_curve=bpy.data.curves.new('_tc_label_font','FONT');label_font=font_curve.font
    b.text('TC-041',(.255,-.284,1.30),.10,material('v04 Cabinet ID red',(.34,.043,.025)),label_font)
    bpy.data.curves.remove(font_curve)
    finish(b,'Telecom')
    b=MeshBuilder();iron=surface('Cast iron covers',(.065,.077,.075),metallic=.67)
    b.cylinder((0,0,-.015),.43,.04,iron,48)
    ring(b,(0,0,.008),.38,.016,steel,axis='Z',segments=48)
    for j in range(-6,7):
        yy=j*.05;span=math.sqrt(max(0,.35**2-yy**2))
        rod(b,(-span,yy,.008),(span,yy,.008),.008,iron,6)
    for x in (-.20,.20):b.box((x,0,.017),(.09,.035,.008),black)
    finish(b,'Manhole')
    b=MeshBuilder()
    b.box((0,0,-.018),(.74,.39,.06),concrete)
    b.box((0,0,.008),(.65,.30,.025),black)
    for y in (-.16,.16):b.box((0,y,.021),(.71,.025,.028),iron)
    for x in (-.345,.345):b.box((x,0,.021),(.022,.32,.028),iron)
    for j in range(15):b.box((-.32+j*.046,0,.023),(.022,.30,.025),iron)
    finish(b,'Drain')
    # Very small real bevels give cabinet edges a readable highlight in close views.
    for kind in ('Telecom',):
        o=out[kind];mod=o.modifiers.new('Fabricated edges','BEVEL');mod.width=.006;mod.segments=2
        active=bpy.context.view_layer.objects.active
        # Source collections are unlinked, so evaluate with a temporary scene link.
        bpy.context.collection.objects.link(o)
        bpy.context.view_layer.objects.active=o
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.context.collection.objects.unlink(o)
        bpy.context.view_layer.objects.active=active
    return out
