"""Taipei walk-up apartments: recessed balconies, individual alterations, roof homes."""
import math
import random
from mathutils import Matrix
from .assets import MeshBuilder
from .surfaces import palette
from .lived_in import rod,cable,ring,plant,laundry,aircon,water_tank
from .sheds import sheet,sloped_roof


def grille(b,x,y,z,w,height,p,style):
    mat=p['frame'] if style%3 else p['steel']
    for dx in (-w/2,w/2):rod(b,(x+dx,y,z),(x+dx,y,z+height),.016,mat)
    # Some residents add horizontal cages; others retain vertical iron bars.
    for dz in (0,.40,height*.66,height):rod(b,(x-w/2,y,z+dz),(x+w/2,y,z+dz),.013,mat)
    count=max(3,int(w/.23))
    for j in range(count+1):
        xx=x-w/2+w*j/count
        rod(b,(xx,y,z),(xx,y,z+height),.009,mat,6)
        if style%3==0:
            points=[(xx+.085*math.cos(t*math.pi/8),y,z+height-.14+.085*math.sin(t*math.pi/8)) for t in range(9)]
            cable(b,points,.007,mat)
    for dx in (-w/2,w/2):
        for dz in (0,height*.5,height):rod(b,(x+dx,y,z+dz),(x+dx,y+.48,z+dz),.012,mat)


def window(b,x,y,z,w,h,p,rng):
    b.box((x,y+.09,z),(w+.13,.13,h+.13),p['frame'])
    b.box((x,y+.014,z),(w,.022,h),p['glassblue'] if rng.random()<.24 else p['glass'])
    b.box((x,y-.012,z),(.035,.028,h+.02),p['frame'])
    b.box((x,y-.012,z-h*.10),(w,.028,.025),p['frame'])
    if rng.random()<.48:
        # Opaque curtain behind part of the glazing, with actual folds.
        for j in range(10):
            xx=x-w*.40+j*w*.049
            b.box((xx,y+.022,z),(.065,.028,h*.93),p['curtain'])


def roof_home(b,h,variant,p):
    rng=random.Random(3100+variant);wall=p['plaster'];metal=p['roof'][variant]
    # Main room covers the front roof, leaving a rear service terrace and headhouse.
    x0=-2.73; x1=2.70
    front=-3.25 if variant%3==0 else -4.02
    rear=2.38 if variant%3!=2 else 1.55
    base=h+.20;top=h+2.55+rng.uniform(-.12,.20)
    room_mat=metal if variant%3==1 else wall
    for x in (x0,x1):
        if variant%3==1:sheet(b,(x,front,base),(0,rear-front,0),(0,0,top-base),metal,pitch=.18,amplitude=.019)
        else:b.box((x,(front+rear)/2,(base+top)/2),(.14,rear-front,top-base),wall)
    b.box(((x0+x1)/2,rear,(base+top)/2),(x1-x0,.14,top-base),room_mat)
    # Front wall has true window/door cutouts, with a dark interior behind them.
    b.box((0,front+.75,base+1.1),(5.35,.06,2.05),p['interior'])
    b.box((0,front,base+.31),(5.50,.13,.62),room_mat)
    b.box((0,front,top-.22),(5.50,.13,.45),room_mat)
    for x in (-2.64,-.85,.85,2.64):b.box((x,front,base+1.39),(.19,.13,1.57),room_mat)
    for x in (-1.73,1.72):window(b,x,front-.081,base+1.38,1.55,1.30,p,rng)
    b.box((0,front-.02,base+1.0),(1.44,.10,1.90),p['steel'])
    b.box((0,front-.09,base+1.42),(1.22,.04,.74),p['glass'])
    rod(b,(.51,front-.15,base+.83),(.51,front-.15,base+1.02),.025,p['silver'])
    # Three roof constructions: mono pitch, gable, and a repaired mono pitch.
    if variant%3==0:
        # Roof drains to the front, supported by a steel perimeter.
        sheet(b,(x0-.13,front-.27,top+.08),(x1-x0+.26,0,0),(0,rear-front+.47,.48),metal)
        for x in (x0,x1):
            b.add([(x,front,top),(x,rear,top),(x,rear,top+.53),(x,front,top+.10)],[(0,1,2,3)],room_mat)
        b.box((0,rear,top+.27),(5.54,.10,.54),room_mat)
    elif variant%3==1:
        ridge=top+.70
        sloped_roof(b,x0-.13,0,front-.27,rear+.2,top+.08,ridge,metal,p['steel'])
        sloped_roof(b,0,x1+.13,front-.27,rear+.2,ridge,top+.08,metal,p['steel'])
        for y in (front,rear):b.add([(x0,y,top),(x1,y,top),(0,y,ridge)],[(0,1,2)],room_mat)
        rod(b,(0,front-.29,ridge+.015),(0,rear+.22,ridge+.015),.04,p['silver'])
    else:
        split=1.68
        sloped_roof(b,x0-.13,split,front-.27,rear+.2,top+.10,top+.43,metal,p['steel'])
        sloped_roof(b,split,x1+.13,front-.27,rear+.2,top+.43,top+.52,p['roof'][(variant+2)%6],p['steel'])
        for y in (front,rear):b.add([(x0,y,top),(x1,y,top),(x1,y,top+.51),(x0,y,top+.11)],[(0,1,2,3)],room_mat)
        b.box((x1,(front+rear)/2,top+.25),(.13,rear-front,.5),room_mat)
    for y in (front,rear):rod(b,(x0,y,top),(x1,y,top),.035,p['steel'])
    # Open front terrace with a secondary rain canopy and exposed rafters.
    canopy_front=-5.62;canopy_z=top-.23
    sheet(b,(x0-.09,canopy_front,canopy_z),(5.62,0,0),(0,front-canopy_front+.10,.22),p['roof'][(variant+1)%6] if variant%2 else metal,pitch=.19,amplitude=.019)
    for x in (x0,.1,x1):
        rod(b,(x,canopy_front,base),(x,canopy_front,canopy_z),.034,p['rust'])
        rod(b,(x,canopy_front,canopy_z-.06),(x,front,canopy_z+.16),.030,p['steel'])
    for y in (canopy_front+.1,(canopy_front+front)/2,front):rod(b,(x0,y,canopy_z+.08),(x1,y,canopy_z+.08),.025,p['steel'])
    rod(b,(x0-.14,canopy_front-.04,canopy_z),(x1+.14,canopy_front-.04,canopy_z),.045,p['silver'])
    cable(b,[(2.80,canopy_front,canopy_z),(2.80,canopy_front,h+.24),(2.8,-4.8,h+.24)],.035,p['plastic'])
    # Roof residents: washing machine, AC, laundry and plants on their terrace.
    aircon(b,1.6,front-.30,base+.40,p,variant+30)
    b.box((-2.17,front-.52,base+.46),(.53,.54,.91),p['ac'])
    b.box((-2.17,front-.52,base+.93),(.48,.48,.055),p['steel'])
    laundry(b,-.72,front-.80,base+1.68,1.8,p,variant)
    for j,x in enumerate((1.04,2.20)):
        plant(b,(x,-5.24,base),.65,p,variant*10+j)
    # A low utility shelter attached to the rear, distinct from the main room.
    if variant%2:
        b.box((1.65,3.22,h+.76),(1.35,1.1,1.14),p['plaster'])
        sloped_roof(b,.88,2.43,2.55,3.88,h+1.40,h+1.63,p['roof'][(variant+3)%6],p['steel'])


def build_residential(cols,mats,font):
    p=palette()
    for floors in range(2,8):
        for variant in range(6):
            rng=random.Random(5400+floors*61+variant)
            body,signs,roof,props,addition=(MeshBuilder() for _ in range(5))
            wall=p['walls'][variant];h=3.25+(floors-1)*2.95
            # Deep dark rooms behind a genuine recessed balcony zone.
            body.box((0,0,.09),(6.36,12,.18),p['concrete'])
            body.box((0,1.90,h/2),(6.12,7.9,h),wall)
            for x in (-3.01,3.01):body.box((x,-.23,h/2),(.16,11.80,h),wall)
            body.box((0,-.30,3.20),(6.20,11.3,.18),p['concrete'])
            # Ground-floor apartment entrance and adjacent recessed shop/garage.
            for x in (-2.92,2.92):body.box((x,-5.28,1.62),(.29,.31,3.07),wall)
            body.box((2.10,-3.52,1.29),(1.35,.16,2.37),p['steel'])
            window(body,2.10,-3.63,1.73,1.09,.70,p,rng)
            for j in range(5):
                body.box((1.20,-3.62,.72+j*.28),(.26,.055,.21),p['frame'])
                body.box((1.20,-3.654,.76+j*.28),(.19,.012,.016),p['interior'])
            body.box((2.88,-3.70,1.50),(.14,.07,.28),p['frame'])
            shop_y=-3.70
            if variant in (0,3,5):
                # Some shutters half-open, revealing a dark shop with a simple counter.
                body.box((-.80,-3.14,1.35),(3.85,.08,2.7),p['interior'])
                shutter_low=1.15 if variant==0 else .23
                for j in range(int((2.85-shutter_low)/.075)):
                    body.box((-.80,shop_y,shutter_low+j*.075),(3.88,.08,.059),p['steel'])
                if variant==0:body.box((-.80,-3.20,.48),(2.1,.55,.8),p['repair'])
                signs.box((-.67,-5.36,2.88),(4.22,.16,.56),mats['white'])
                signs.text(['永和豆漿','金興五金','日日茶行'][variant//2 if variant<5 else 2],(-.67,-5.46,2.89),.38,mats['blue'],font)
                # Faded sagging canvas strips on a lean metal frame.
                sheet(signs,(-2.8,-5.89,2.34),(4.27,0,0),(0,.69,.27),p['roof'][variant],pitch=.27,amplitude=.015)
                if variant==3:
                    signs.box((2.76,-5.50,5.04),(.47,.24,2.08),mats['white'])
                    for j,ch in enumerate('五金'):signs.text(ch,(2.76,-5.635,5.55-j*.64),.40,mats['red'],font)
            else:
                for x in (-1.72,.05):window(body,x,-3.69,1.45,1.58,2.52,p,rng)
            # Per-household alterations, rather than one repeated window module.
            for floor in range(1,floors):
                z=3.25+(floor-1)*2.95
                body.box((0,-.1,z),(6.25,11.25,.16),p['concrete'])
                body.box((0,-5.57,z+.04),(5.96,.57,.16),p['concrete'])
                body.box((0,-4.07,z+.37),(5.85,.17,.70),wall)
                body.box((0,-4.07,z+2.72),(5.85,.17,.38),wall)
                for x in (-2.92,0,2.92):body.box((x,-4.07,z+1.52),(.20,.17,1.66),wall)
                for bay,x in enumerate((-1.43,1.43)):
                    window(body,x,-4.18,z+1.54,2.58,1.77,p,rng)
                    enclosure=rng.random()
                    front=-5.48-rng.uniform(0,.14)
                    if enclosure<.72:
                        # Low tiled balcony wall topped with varied iron cages.
                        body.box((x,front+.04,z+.43),(2.72,.15,.66),wall if enclosure<.43 else p['repair'])
                        grille(body,x,front-.065,z+.81,2.62,1.84,p,variant+floor+bay)
                        if enclosure<.2:window(body,x,front+.02,z+1.63,2.40,1.53,p,rng)
                    else:
                        grille(body,x,front,z+.23,2.62,1.00,p,variant+bay)
                    # A few replaced awnings and side windbreak panels.
                    if rng.random()<.65:
                        sheet(body,(x-1.34,front-.16,z+2.58),(2.68,0,0),(0,.82,.14),p['roof'][(variant+floor+bay)%6],pitch=.20,amplitude=.012)
                        rod(body,(x-1.27,front,z+2.50),(x-1.27,-4.4,z+2.66),.012,p['steel'])
                    if rng.random()<.74:
                        aircon(body,x+rng.uniform(-.7,.6),front-.03,z+.34 if enclosure>.4 else z+2.60,p,floor*6+variant+bay)
                    if rng.random()<.65:plant(body,(x+.65,front+.37,z+.2),.55,p,100*floor+variant+bay)
                    if rng.random()<.40:laundry(body,x,front+.42,z+2.05,1.72,p,floor*37+bay+variant)
                # Stairwell/rear windows, drain stacks and poorly matched repairs.
                for x in (-1.55,1.65):
                    window(body,x,5.86,z+1.41,1.0,1.2,p,rng)
                for side in (-1,1):
                    for yy in (0.0,3.9):
                        body.box((side*3.10,yy,z+1.5),(.03,.94,1.15),p['glass'])
                        for j in range(4):body.box((side*3.13,yy-.35+j*.23,z+1.5),(.02,.025,1.12),p['frame'])
                if floor%2==variant%2:
                    body.box((2.82,-4.12,z+1.3),(.15,.022,1.73),p['repair'])
            for x,y in ((2.82,-5.25),(-2.85,5.72)):
                cable(body,[(x,y,.3),(x,y,h-.4),(x-.25,y,h-.2)],.041,p['plastic'])
                for z in range(1,int(h),2):ring(body,(x,y,z),.059,.010,p['steel'],axis='Z',segments=12)
            # Loose electric loops and telecom junction boxes under the arcade.
            for j in range(3):
                points=[(-2.9+5.8*t/12,-5.34,3.04-.23*math.sin(t*math.pi/12)-j*.075) for t in range(13)]
                cable(body,points,.010,p['rubber'])
            body.box((-2.58,-5.4,2.47),(.32,.18,.40),p['plastic'])
            # Roof slab, parapets, permanently present stair access and service tanks.
            body.box((0,.1,h+.08),(6.25,11.6,.20),p['concrete'])
            for x in (-3.02,3.02):body.box((x,.1,h+.56),(.16,11.56,.95),wall)
            for y in (-5.6,5.8):body.box((0,y,h+.56),(6.06,.16,.95),wall)
            roof.box((-1.55,4.58,h+1.27),(2.35,2.24,2.34),p['plaster'])
            roof.box((-1.55,4.58,h+2.50),(2.51,2.4,.16),p['concrete'])
            roof.box((-1.62,3.42,h+1.2),(.91,.10,2.10),p['steel'])
            for j,(xx,r) in enumerate(((-2.06,.46),(-.92,.51))):water_tank(roof,xx,4.7,h+2.60,r,p)
            if variant%2:water_tank(roof,1.72,4.67,h+.22,.57,p)
            # Accessible terrace rails, ladder and scattered roof plants.
            for x in (2.3,2.67):rod(roof,(x,5.41,h+.2),(x,5.41,h+1.9),.018,p['silver'])
            for j in range(6):rod(roof,(2.3,5.41,h+.3+j*.28),(2.67,5.41,h+.3+j*.28),.014,p['silver'])
            plant(roof,(1.0,4.7,h+.19),.85,p,variant+500)
            roof_home(addition,h,variant,p)
            # Scatter individually shaped plants and a narrow utility cart at ground level.
            for j,(x,y) in enumerate(((-2.42,-4.35),(2.52,-4.33))):plant(props,(x,y,.18),.72,p,variant*32+j)
            props.box((.7,-4.2,.57),(.37,.43,.76),p['plastic'])
            for j in range(3):props.box((.7,-4.44,.38+j*.23),(.31,.03,.16),p['frame'])
            index=(floors-2)*6+variant
            for key,builder in zip(cols,(body,signs,roof,props,addition)):
                obj=builder.object(f'TC_{index:02d}_{key}_{floors}F_{variant}',cols[key])
                obj['tc_floors']=floors;obj['tc_variant']=variant;obj['tc_kind']='ROWHOUSE'
                obj['tc_roof_home']=key=='Additions'
