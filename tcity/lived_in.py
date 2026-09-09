"""Small life/utility details shared by residential facades and roof terraces."""
import math
import random
from mathutils import Vector,Matrix


def rod(b,a,end,r,mat,segments=8):
    d=Vector(end)-Vector(a);rot=d.to_track_quat('Z','Y').to_matrix()
    verts=[tuple(Vector(a)+rot@Vector((r*math.cos(i*math.tau/segments),r*math.sin(i*math.tau/segments),z)))
           for z in (0,d.length) for i in range(segments)]
    faces=[tuple(reversed(range(segments))),tuple(range(segments,2*segments))]
    faces += [(i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments)]
    b.add(verts,faces,mat,[False,False]+[True]*segments)


def cable(b,points,r,mat):
    for a,end in zip(points,points[1:]):rod(b,a,end,r,mat,6)


def ring(b,center,radius,wire,mat,axis='Y',segments=28):
    c=Vector(center)
    if axis=='Y':points=[c+Vector((radius*math.cos(t*math.tau/segments),0,radius*math.sin(t*math.tau/segments))) for t in range(segments)]
    else:points=[c+Vector((radius*math.cos(t*math.tau/segments),radius*math.sin(t*math.tau/segments),0)) for t in range(segments)]
    cable(b,points+[points[0]],wire,mat)


def plant(b,pos,size,p,seed):
    rng=random.Random(seed);x,y,z=pos
    b.cylinder((x,y,z+.16*size),.19*size,.32*size,p['pot'],12)
    b.cylinder((x,y,z+.32*size),.20*size,.05*size,p['pot'],12)
    for branch in range(6):
        angle=rng.random()*math.tau
        tip=Vector((x+math.cos(angle)*.29*size,y+math.sin(angle)*.29*size,z+rng.uniform(.65,1.25)*size))
        base=Vector((x,y,z+.2*size));rod(b,base,tip,.009*size,p['steel'],6)
        for j in range(6):
            t=.30+j*.12;origin=base.lerp(tip,t)
            a=angle+(j%2)*math.pi+rng.uniform(-.5,.5)
            direction=Vector((math.cos(a),math.sin(a),rng.uniform(-.12,.35)))*rng.uniform(.12,.26)*size
            cross=Vector((-math.sin(a),math.cos(a),0))*.050*size
            verts=[origin,origin+direction*.50+cross,origin+direction,origin+direction*.5-cross,origin+direction*.5+Vector((0,0,.025*size))]
            b.add([tuple(v) for v in verts],[(0,1,4),(1,2,4),(2,3,4),(3,0,4)],rng.choice(p['leaves']))


def laundry(b,x,y,z,width,p,seed):
    rng=random.Random(seed)
    for dx in (-width/2,width/2):rod(b,(x+dx,y,z-.45),(x+dx,y,z+.10),.018,p['steel'])
    cable(b,[(x-width/2,y,z),(x,y,z-.05),(x+width/2,y,z)],.007,p['rubber'])
    for i in range(4):
        xx=x-width*.36+i*width*.24;w=.26 if i%2 else .36;length=rng.uniform(.38,.67)
        verts=[]
        for row in range(5):
            for col in range(7):
                verts.append((xx-w/2+w*col/6,y+.035*math.sin(col*2.4+row*.25),z-.05-length*row/4))
        faces=[(r*7+c,r*7+c+1,(r+1)*7+c+1,(r+1)*7+c) for r in range(4) for c in range(6)]
        b.add(verts,faces,p['cloth'][i%4],True)


def aircon(b,x,y,z,p,seed):
    rng=random.Random(seed);width=rng.uniform(.70,.92);height=rng.uniform(.48,.65)
    b.box((x,y,z),(width,.38,height),p['ac'])
    center=(x-.12,y-.208,z)
    # Four fan blades behind a fine circular guard.
    b.box(center,(.40,.016,.40),p['interior'])
    for i in range(4):
        rot=Matrix.Rotation(i*math.pi/2+.3,3,'Y')
        v=rot@Vector((.09,0,0))
        b.box(Vector(center)+v,(.21,.02,.065),p['steel'],rot)
    for radius in (.08,.135,.19):ring(b,(center[0],y-.23,z),radius,.009,p['frame'])
    for i in range(4):
        a=i*math.pi/4
        rod(b,(center[0]-.20*math.cos(a),y-.245,z-.20*math.sin(a)),(center[0]+.20*math.cos(a),y-.245,z+.20*math.sin(a)),.005,p['steel'],6)
    for k in range(6):b.box((x+width*.32,y-.205,z-height*.33+k*height*.125),(.15,.018,.016),p['steel'])
    for dx in (-width*.30,width*.30):
        cable(b,[(x+dx,y+.17,z+.12),(x+dx,y+.17,z-height/2-.1),(x+dx,y-.22,z-height/2-.1)],.022,p['rust'])
    cable(b,[(x+width/2,y,z+.13),(x+width/2+.15,y,z+.13),(x+width/2+.15,y+.30,z-.65)],.027,p['plastic'])


def water_tank(b,x,y,z,radius,p):
    for dx in (-radius*.6,radius*.6):
        for dy in (-radius*.6,radius*.6):rod(b,(x+dx,y+dy,z),(x+dx,y+dy,z+.34),.035,p['steel'])
    h=radius*2.1
    b.cylinder((x,y,z+.34+h/2),radius,h,p['silver'],32)
    for dz in (.38,.34+h*.25,.34+h*.75,.34+h):ring(b,(x,y,z+dz),radius+.012,.018,p['silver'],axis='Z')
    b.cylinder((x,y,z+.37+h),radius*.82,.045,p['silver'],32)
    b.cylinder((x,y,z+.44+h),.13,.09,p['silver'],16)
    cable(b,[(x+radius,y,z+.55),(x+radius+.16,y,z+.55),(x+radius+.16,y,z+.07),(x+radius+.16,y-.8,z+.07)],.035,p['plastic'])
