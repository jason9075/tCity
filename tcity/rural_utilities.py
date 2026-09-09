"""Road-edge poles and supported wires with conservative region/hole guards."""
import math
from .roads import _store, _named, _transform, _gate, _join
from .street_assets import ensure_street_assets


def rural_utilities(g,p,plan,road_selection,region,boundary):
    g.section('06 / RURAL UTILITIES · supported spans on farm access lanes',(9100,0))
    pos=g.node('GeometryNodeInputPosition').outputs[0]
    ev=g.node('GeometryNodeInputMeshEdgeVertices')
    a,b=ev.outputs['Position 1'],ev.outputs['Position 2']
    delta=g.vmath('SUBTRACT',b,a)
    direction=g.vmath('NORMALIZE',delta,(0,0,0))
    length=g.node('ShaderNodeVectorMath',operation='LENGTH');g.put(delta,length.inputs[0]);length=length.outputs['Value']
    sep=g.node('ShaderNodeSeparateXYZ');g.put(direction,sep.inputs[0])
    side=g.vector(sep.outputs['Y'],g.mul(sep.outputs['X'],-1),0)
    offset=g.vmath('MULTIPLY',side,g.vector(g.sub(g.mul(p['Road Width'],.5),.25),g.sub(g.mul(p['Road Width'],.5),.25),0))
    aa=g.vmath('ADD',a,offset);bb=g.vmath('ADD',b,offset)
    valid=g.boolean('AND',road_selection,p['Farm Roads'])
    for point in (aa,bb):
        valid=g.boolean('AND',valid,g.ray(region,point).outputs['Is Hit'])
        valid=g.boolean('AND',valid,g.math('GREATER_THAN',g.distance(boundary,point),1.05))
    # A tube around every boundary guards the complete span, including tiny
    # holes between valid endpoints and the lateral conductor offsets.
    bc=g.node('GeometryNodeMeshToCurve');g.put(boundary,bc.inputs['Mesh'])
    circle=g.node('GeometryNodeCurvePrimitiveCircle');circle.inputs['Radius'].default_value=1.05;circle.inputs['Resolution'].default_value=8
    guard=g.node('GeometryNodeCurveToMesh');g.put(bc.outputs[0],guard.inputs['Curve']);g.put(circle.outputs[0],guard.inputs['Profile Curve'])
    ray=g.node('GeometryNodeRaycast',data_type='FLOAT');g.put(guard.outputs[0],ray.inputs['Target Geometry'])
    g.put(aa,ray.inputs['Source Position']);g.put(direction,ray.inputs['Ray Direction']);g.put(length,ray.inputs['Ray Length'])
    valid=g.boolean('AND',valid,g.boolean('NOT',ray.outputs['Is Hit']))
    selected=g.node('GeometryNodeSeparateGeometry',domain='EDGE');g.put(plan,selected.inputs['Geometry']);g.put(valid,selected.inputs['Selection'])
    split=g.node('GeometryNodeSplitEdges');g.put(selected.outputs[0],split.inputs['Mesh'])
    curve=g.node('GeometryNodeMeshToCurve');g.put(split.outputs[0],curve.inputs['Mesh'])
    tangent=g.node('GeometryNodeInputTangent').outputs[0]
    tangent_sep=g.node('ShaderNodeSeparateXYZ');g.put(tangent,tangent_sep.inputs[0])
    lateral=g.vector(tangent_sep.outputs['Y'],g.mul(tangent_sep.outputs['X'],-1),0)
    shift=g.vmath('MULTIPLY',lateral,g.vector(g.sub(g.mul(p['Road Width'],.5),.25),g.sub(g.mul(p['Road Width'],.5),.25),0))
    moved=g.node('GeometryNodeSetPosition');g.put(curve.outputs[0],moved.inputs['Geometry']);g.put(g.vmath('ADD',shift,(0,0,.095)),moved.inputs['Offset'])
    theta=g.math('ARCTAN2',tangent_sep.outputs['Y'],tangent_sep.outputs['X'])
    spline_length=g.node('GeometryNodeSplineLength').outputs['Length']
    spans=g.math('MAXIMUM',g.math('CEIL',g.div(spline_length,p['Pole Spacing'])),1)
    resample=g.node('GeometryNodeResampleCurve');g.put(moved.outputs[0],resample.inputs['Curve']);g.put(g.add(spans,1),resample.inputs['Count'])
    tagged=_store(g,resample.outputs[0],'farm_pole_angle',theta,'FLOAT')
    pts=g.node('GeometryNodeCurveToPoints',mode='EVALUATED');g.put(tagged,pts.inputs['Curve'])
    info=g.node('GeometryNodeObjectInfo');info.inputs['Object'].default_value=ensure_street_assets()['Pole'];info.inputs['As Instance'].default_value=True
    pole=g.node('GeometryNodeInstanceOnPoints');g.put(pts.outputs['Points'],pole.inputs['Points']);g.put(info.outputs['Geometry'],pole.inputs['Instance'])
    g.put(g.vector(0,0,_named(g,'farm_pole_angle')),pole.inputs['Rotation']);g.put(p['Utility Poles'],pole.inputs['Selection'])
    # Sixteen substeps per supported span, with zero sag exactly at each pole.
    dense=g.node('GeometryNodeResampleCurve');g.put(moved.outputs[0],dense.inputs['Curve']);g.put(g.add(g.mul(spans,16),1),dense.inputs['Count'])
    parameter=g.node('GeometryNodeSplineParameter').outputs['Factor']
    t=g.math('FRACT',g.mul(parameter,spans));drop=g.mul(g.mul(g.mul(t,g.sub(1,t)),-4),p['Cable Sag'])
    wires=[]
    wire_material=ensure_street_assets()['Pole'].data.materials
    from .assets import material
    black=material('Rural cable insulation',(.012,.015,.014),roughness=.65)
    for across,height in [(-.38,8.66),(0,8.66),(.38,8.66),(-.27,6.18)]:
        # Local pole +Y is -lateral because the latter points to the right verge.
        off=g.vmath('ADD',g.vmath('MULTIPLY',lateral,(-across,-across,-across)),g.vector(0,0,g.add(height,drop)))
        sp=g.node('GeometryNodeSetPosition');g.put(dense.outputs[0],sp.inputs['Geometry']);g.put(off,sp.inputs['Offset'])
        profile=g.node('GeometryNodeCurvePrimitiveCircle');profile.inputs['Resolution'].default_value=6;profile.inputs['Radius'].default_value=.016
        tube=g.node('GeometryNodeCurveToMesh');g.put(sp.outputs[0],tube.inputs['Curve']);g.put(profile.outputs[0],tube.inputs['Profile Curve'])
        tube.inputs['Fill Caps'].default_value=True
        from .roads import _mat
        wires.append(_mat(g,tube.outputs[0],black))
    wire=_store(g,_join(g,wires),'farm_layer',15,'INT')
    wire=_gate(g,wire,g.boolean('AND',p['Utility Poles'],p['Overhead Wires']))
    return [pole.outputs[0],wire]
