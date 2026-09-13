"""Live street layers sharing the district grid. No Python runs during evaluation."""
import math
import bpy
from .assets import material
from .street_assets import ensure_street_assets


def paving_material():
    m=material('v04 Sidewalk pavers',(.32,.32,.30),roughness=.85)
    if m.node_tree.nodes.get('Paving joints'):return m
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n.get('Principled BSDF')
    coord=n.new('ShaderNodeTexCoord');brick=n.new('ShaderNodeTexBrick');brick.name='Paving joints'
    l.new(coord.outputs['Object'],brick.inputs['Vector'])
    brick.inputs['Scale'].default_value=1;brick.inputs['Brick Width'].default_value=.40;brick.inputs['Row Height'].default_value=.20
    brick.inputs['Mortar Size'].default_value=.004;brick.inputs['Mortar Smooth'].default_value=.001
    brick.inputs['Color1'].default_value=(.28,.285,.265,1);brick.inputs['Color2'].default_value=(.38,.365,.32,1)
    brick.inputs['Mortar'].default_value=(.12,.13,.115,1)
    l.new(brick.outputs['Color'],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.004;bump.inputs['Strength'].default_value=.3
    l.new(brick.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return m


def infrastructure(g,p,origin,px,py,nx,ny,boundary,road_material):
    """Return separate road/paving meshes, utility instances and realized wire tubes."""
    g.section('05 / STREETS · clipped carriageway and raised pavement',(5100,0))
    S=p['Sidewalk Width'];D=p['Depth'];R=p['Road Width'];A=p['Alley Width']
    B=g.math('MULTIPLY',p['Frontage'],p['Lots per Block'])
    W=g.math('ADD',B,g.math('MULTIPLY',S,2));T=p['Road Thickness'];H=p['Curb Height']
    # Hiding sidewalks lowers freestanding street assets back to road level.
    height=g.math('MULTIPLY',H,p['Sidewalks'])
    blocks=g.math('MINIMUM',g.math('MULTIPLY',nx,ny),g.math('FLOOR',g.math('DIVIDE',20000,g.math('MULTIPLY',p['Lots per Block'],2))))
    rows=g.math('MULTIPLY',blocks,2)
    def add(a,b):return g.math('ADD',a,b)
    def mul(a,b):return g.math('MULTIPLY',a,b)
    def sub(a,b):return g.math('SUBTRACT',a,b)
    def join(parts,label=''):
        n=g.node('GeometryNodeJoinGeometry',label)
        for x in parts:g.put(x,n.inputs[0])
        return n.outputs[0]
    def transform(geo,translation=(0,0,0),scale=(1,1,1)):
        n=g.node('GeometryNodeTransform');g.put(geo,n.inputs['Geometry']);g.put(translation,n.inputs['Translation']);g.put(scale,n.inputs['Scale']);return n.outputs[0]
    def tag(geo,value):
        n=g.node('GeometryNodeStoreNamedAttribute',data_type='INT',domain='POINT');n.inputs['Name'].default_value='tc_layer'
        g.put(geo,n.inputs['Geometry']);g.put(value,n.inputs['Value']);return n.outputs[0]
    def mat(geo,value):
        n=g.node('GeometryNodeSetMaterial');g.put(geo,n.inputs['Geometry']);n.inputs['Material'].default_value=value;return n.outputs[0]
    def gate(geo,toggle):
        n=g.node('GeometryNodeSwitch',input_type='GEOMETRY');g.put(toggle,n.inputs['Switch']);g.put(geo,n.inputs['True']);return n.outputs[0]
    def points(count,position,label,selection=True,facing=0):
        line=g.node('GeometryNodeMeshLine',label,mode='OFFSET');g.put(count,line.inputs['Count'])
        loc=g.node('GeometryNodeSetPosition');g.put(line.outputs['Mesh'],loc.inputs['Geometry']);g.put(position,loc.inputs['Position'])
        capture=g.node('GeometryNodeStoreNamedAttribute',domain='POINT',data_type='FLOAT');capture.inputs['Name'].default_value='tc_street_rotation'
        g.put(loc.outputs[0],capture.inputs['Geometry']);g.put(mul(facing,math.pi),capture.inputs['Value'])
        node=g.node('GeometryNodeMeshToPoints',mode='VERTICES');g.put(capture.outputs[0],node.inputs['Mesh']);g.put(selection,node.inputs['Selection'])
        return node.outputs['Points']
    def instance(pts,geo,selection=True,rotation=(0,0,0),scale=(1,1,1),label='',realize=False):
        n=g.node('GeometryNodeInstanceOnPoints',label)
        for value,key in [(pts,'Points'),(geo,'Instance'),(selection,'Selection'),(rotation,'Rotation'),(scale,'Scale')]:g.put(value,n.inputs[key])
        if not realize:return n.outputs['Instances']
        r=g.node('GeometryNodeRealizeInstances');g.put(n.outputs['Instances'],r.inputs['Geometry']);return r.outputs[0]
    def boolean(a,b,op):
        n=g.node('GeometryNodeMeshBoolean','Street volume '+op.lower(),operation=op,solver='EXACT')
        # Index, don't subscript by name: Blender 5.2 renames the 2nd input from
        # 'Mesh 2' to the multi-input 'Mesh' for UNION/INTERSECT, and separately
        # `n.inputs['Mesh 1']` raises a spurious KeyError for those operations
        # even though 'Mesh 1' is genuinely that socket's name/identifier.
        mesh2=n.inputs[1]
        if op=='INTERSECT':
            g.put(a,mesh2);g.put(b,mesh2)
        else:g.put(a,n.inputs[0]);g.put(b,mesh2)
        return n.outputs['Mesh']
    # Correct input winding, then close both caps after Extrude Mesh (which omits its base).
    normal=g.node('GeometryNodeInputNormal');sep=g.node('ShaderNodeSeparateXYZ');g.put(normal.outputs[0],sep.inputs[0])
    flip=g.node('GeometryNodeFlipFaces');g.put(p['Geometry'],flip.inputs['Mesh']);g.put(g.math('LESS_THAN',sep.outputs['Z'],0),flip.inputs['Selection'])
    def prism(top):
        base=transform(flip.outputs[0],g.vector(0,0,mul(T,-1)))
        e=g.node('GeometryNodeExtrudeMesh','Watertight region sidewalls',mode='FACES')
        g.put(base,e.inputs['Mesh']);e.inputs['Individual'].default_value=False
        g.put(g.vector(0,0,add(top,T)),e.inputs['Offset']);e.inputs['Offset Scale'].default_value=1
        bottom=g.node('GeometryNodeFlipFaces');g.put(base,bottom.inputs['Mesh'])
        merged=g.node('GeometryNodeMergeByDistance');g.put(join([e.outputs['Mesh'],bottom.outputs[0]]),merged.inputs['Geometry']);merged.inputs['Distance'].default_value=.00001
        return merged.outputs[0]
    road_prism=prism(0);clip_prism=prism(H)
    idx=g.node('GeometryNodeInputIndex').outputs[0]
    row=g.math('MODULO',idx,2);block=g.math('FLOOR',g.math('DIVIDE',idx,2))
    bx=g.math('MODULO',block,nx);by=g.math('FLOOR',g.math('DIVIDE',block,nx))
    rowdepth=add(D,S)
    x=add(mul(bx,px),add(mul(R,.5),mul(W,.5)))
    y=add(mul(by,py),add(add(mul(R,.5),mul(rowdepth,.5)),mul(row,add(rowdepth,A))))
    centers=points(rows,g.vmath('ADD',origin,g.vector(x,y,0)),'Pavement islands')
    cube=g.node('GeometryNodeMeshCube');cube.inputs['Size'].default_value=(1,1,1)
    elevated=transform(cube.outputs['Mesh'],g.vector(0,0,mul(sub(H,T),.5)),g.vector(W,rowdepth,add(H,T)))
    islands=instance(centers,elevated,realize=True,label='Front/back sidewalk islands')
    road=boolean(road_prism,islands,'DIFFERENCE')
    paving=boolean(clip_prism,islands,'INTERSECT')
    paving=mat(paving,paving_material())
    side=g.node('GeometryNodeSetMaterial','Concrete curb faces');g.put(paving,side.inputs['Geometry'])
    side.inputs['Material'].default_value=material('v04 Curb concrete',(.31,.315,.29),roughness=.84)
    g.put(g.math('LESS_THAN',g.math('ABSOLUTE',sep.outputs['Z']),.5),side.inputs['Selection']);paving=side.outputs[0]
    for key,value,dtype in [('origin',origin,'FLOAT_VECTOR'),('period_x',px,'FLOAT'),('period_y',py,'FLOAT'),('road_width',R,'FLOAT'),('markings',p['Road Markings'],'FLOAT')]:
        store=g.node('GeometryNodeStoreNamedAttribute',data_type=dtype,domain='POINT');store.inputs['Name'].default_value='tc_'+key
        g.put(road,store.inputs['Geometry']);g.put(value,store.inputs['Value']);road=store.outputs[0]
    road=mat(road,road_material())
    road_on=g.boolean('AND',p['Ground'],p['Road Surface'])
    sidewalk_on=g.boolean('AND',p['Ground'],p['Sidewalks'])
    results=[gate(tag(road,1),road_on),gate(tag(paving,2),sidewalk_on)]
    g.section('06 / UTILITIES · curb anchors, cabinets and drainage',(6600,0))
    assets=ensure_street_assets()
    facing_attr=g.node('GeometryNodeInputNamedAttribute',data_type='FLOAT');facing_attr.inputs['Name'].default_value='tc_street_rotation'
    rotation=g.vector(0,0,facing_attr.outputs['Attribute'])
    def source(key):
        n=g.node('GeometryNodeObjectInfo',key+' source');n.inputs['Object'].default_value=assets[key];n.inputs['As Instance'].default_value=True
        return n.outputs['Geometry']
    def row_fields(row_id):
        direction=g.math('MODULO',row_id,2);block=g.math('FLOOR',g.math('DIVIDE',row_id,2))
        xx=mul(g.math('MODULO',block,nx),px);yy=mul(g.math('FLOOR',g.math('DIVIDE',block,nx)),py)
        # Front and rear rows face opposite streets. y is in the sidewalk furniture strip.
        y=add(yy,add(add(mul(R,.5),mul(S,.5)),mul(direction,sub(py,add(R,S)))))
        return xx,y,direction
    pos=g.node('GeometryNodeInputPosition').outputs[0]
    def inside(position,radius):
        ray=g.node('GeometryNodeRaycast','Grounded anchor',data_type='FLOAT')
        g.put(p['Geometry'],ray.inputs['Target Geometry']);g.put(g.vmath('ADD',position,(0,0,100)),ray.inputs['Source Position'])
        ray.inputs['Ray Direction'].default_value=(0,0,-1);ray.inputs['Ray Length'].default_value=200
        proximity=g.node('GeometryNodeProximity',target_element='EDGES')
        g.put(boundary,proximity.inputs['Geometry']);g.put(position,proximity.inputs['Sample Position'])
        return g.boolean('AND',ray.outputs['Is Hit'],g.math('GREATER_THAN',proximity.outputs['Distance'],radius))
    valid=inside(pos,.93)
    spanlength_total=sub(B,1.2)
    divisions=g.math('MAXIMUM',g.math('CEIL',g.math('DIVIDE',spanlength_total,p['Pole Spacing'])),1)
    spanlength=g.math('DIVIDE',spanlength_total,divisions)
    pole_count=add(divisions,1)
    pole_row=g.math('FLOOR',g.math('DIVIDE',idx,pole_count));k=g.math('MODULO',idx,pole_count)
    xx,yy,side_row=row_fields(pole_row)
    anchor=add(add(mul(R,.5),S),.60)
    polepos=g.vmath('ADD',origin,g.vector(add(xx,add(anchor,mul(k,spanlength))),yy,0))
    poles=points(mul(rows,pole_count),polepos,'Pole anchors',valid,side_row)
    rot=rotation
    pole_geo=transform(source('Pole'),g.vector(0,0,height),g.vector(1,1,g.math('DIVIDE',p['Pole Height'],9)))
    results.append(instance(poles,pole_geo,p['Utility Poles'],rot,label='Utility poles'))
    xx,yy,side_row=row_fields(idx);rot=rotation
    cabpos=g.vmath('ADD',origin,g.vector(add(xx,add(anchor,1.35)),yy,0))
    cabselect=g.boolean('AND',valid,g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],idx,2601),p['Cabinet Density']))
    cabinets=points(rows,cabpos,'Cabinets away from pole bases',cabselect,side_row)
    results.append(instance(cabinets,transform(source('Telecom'),g.vector(0,0,height)),p['Telecom Cabinets'],rot,label='Telecom cabinets'))
    # Drains sit immediately outside the curb; access covers sit in the carriageway.
    sign=sub(1,mul(side_row,2))
    front_edge=add(yy,mul(sign,mul(S,-.5)))
    drainpos=g.vmath('ADD',origin,g.vector(add(xx,add(mul(R,.5),mul(W,.68))),sub(front_edge,mul(sign,.23)),0))
    drainpts=points(rows,drainpos,'Curb inlets',valid,side_row)
    detail_on=g.boolean('AND',p['Road Details'],road_on)
    results.append(instance(drainpts,source('Drain'),detail_on,rot,label='Storm drains'))
    coverpos=g.vmath('ADD',origin,g.vector(add(xx,add(mul(R,.5),mul(W,.37))),sub(front_edge,mul(sign,mul(R,.28))),0))
    coverpts=points(rows,coverpos,'Road access covers',valid)
    results.append(instance(coverpts,source('Manhole'),detail_on,label='Manholes'))
    g.section('07 / WIRES · paired anchors, boundary visibility and sag',(8100,0))
    spanrow=g.math('FLOOR',g.math('DIVIDE',idx,divisions));k=g.math('MODULO',idx,divisions)
    xx,yy,side_row=row_fields(spanrow);sign=sub(1,mul(side_row,2));rot=rotation
    start=g.vmath('ADD',origin,g.vector(add(xx,add(anchor,mul(add(k,side_row),spanlength))),yy,0))
    end=g.vmath('ADD',pos,g.vector(mul(sign,spanlength),0,0))
    connected=g.boolean('AND',valid,inside(end,.93))
    # Inflate every boundary edge into a thin guard tube. This catches not only
    # centerline exits but small holes touching the physical cable's side wall.
    edges=g.node('GeometryNodeMeshToCurve','Region boundary guards');g.put(boundary,edges.inputs['Mesh'])
    guard_profile=g.node('GeometryNodeCurvePrimitiveCircle',mode='RADIUS');guard_profile.inputs['Resolution'].default_value=8;guard_profile.inputs['Radius'].default_value=.04
    guard=g.node('GeometryNodeCurveToMesh');g.put(edges.outputs[0],guard.inputs['Curve']);g.put(guard_profile.outputs[0],guard.inputs['Profile Curve']);guard.inputs['Fill Caps'].default_value=True
    for yoffset in (-.38,0,.38,-.27,-.12):
        ray=g.node('GeometryNodeRaycast','Reject conductor crossing boundary guard',data_type='FLOAT')
        g.put(guard.outputs[0],ray.inputs['Target Geometry']);g.put(g.vmath('ADD',pos,g.vector(0,mul(sign,yoffset),0)),ray.inputs['Source Position'])
        g.put(g.vector(sign,0,0),ray.inputs['Ray Direction']);g.put(spanlength,ray.inputs['Ray Length'])
        connected=g.boolean('AND',connected,g.boolean('NOT',ray.outputs['Is Hit']))
    spans=points(mul(rows,divisions),start,'Only paired poles inside region',connected,side_row)
    idstore=g.node('GeometryNodeStoreNamedAttribute',domain='POINT',data_type='INT');idstore.inputs['Name'].default_value='tc_span_id'
    g.put(spans,idstore.inputs['Geometry']);g.put(idx,idstore.inputs['Value']);spans=idstore.outputs[0]
    line=g.node('GeometryNodeCurvePrimitiveLine',mode='POINTS');g.put(g.vector(spanlength,0,0),line.inputs['End'])
    line.inputs['Start'].default_value=(0,0,0)
    resample=g.node('GeometryNodeResampleCurve');g.put(line.outputs[0],resample.inputs['Curve']);resample.inputs['Count'].default_value=33
    factor=g.node('GeometryNodeSplineParameter').outputs['Factor']
    sag=g.math('MINIMUM',p['Cable Sag'],mul(p['Pole Height'],.12))
    drop=mul(mul(mul(factor,sub(1,factor)),sag),-4)
    bend=g.node('GeometryNodeSetPosition','Parabolic cable sag');g.put(resample.outputs[0],bend.inputs['Geometry']);g.put(g.vector(0,0,drop),bend.inputs['Offset'])
    circle=g.node('GeometryNodeCurvePrimitiveCircle',mode='RADIUS');circle.inputs['Resolution'].default_value=8;circle.inputs['Radius'].default_value=.019
    tube=g.node('GeometryNodeCurveToMesh');g.put(bend.outputs[0],tube.inputs['Curve']);g.put(circle.outputs[0],tube.inputs['Profile Curve']);tube.inputs['Fill Caps'].default_value=True
    wires=[]
    for y,z in [(-.38,8.66),(0,8.66),(.38,8.66),(-.27,6.18),(-.12,6.18)]:
        wires.append(transform(tube.outputs[0],g.vector(0,y,add(height,mul(p['Pole Height'],z/9)))))
    wire_geo=mat(tag(join(wires),3),material('v04 Cable rubber',(.015,.018,.019),roughness=.57))
    wire_on=g.boolean('AND',p['Utility Poles'],p['Overhead Wires'])
    results.append(instance(spans,wire_geo,wire_on,rot,label='Continuous overhead spans',realize=True))
    return results
