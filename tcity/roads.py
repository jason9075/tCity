"""Curved road pipeline (docs/PLAN.md §4-§5, milestone 0.5.0).

Independent from the orthogonal-grid pipeline in nodes.py/infrastructure.py — the
two branches are switched at the top of the district graph (decision 3: dual
branches stay separate through 0.5/0.6, converging only in 0.7). No Python runs
during evaluation; everything here only *builds* the Geometry Nodes graph once.
"""
import bpy
from .assets import material
from .infrastructure import paving_material
from .street_assets import ensure_street_assets


# ---------------------------------------------------------------- graph helpers
def _add(g,a,b):return g.math('ADD',a,b)
def _sub(g,a,b):return g.math('SUBTRACT',a,b)
def _mul(g,a,b):return g.math('MULTIPLY',a,b)


def _join(g,parts,label=''):
    n=g.node('GeometryNodeJoinGeometry',label)
    for x in parts:g.put(x,n.inputs[0])
    return n.outputs[0]


def _transform(g,geo,translation=(0,0,0),rotation=(0,0,0),scale=(1,1,1)):
    n=g.node('GeometryNodeTransform')
    g.put(geo,n.inputs['Geometry']);g.put(translation,n.inputs['Translation'])
    g.put(rotation,n.inputs['Rotation']);g.put(scale,n.inputs['Scale'])
    return n.outputs[0]


def _tag(g,geo,layer):
    n=g.node('GeometryNodeStoreNamedAttribute',data_type='INT',domain='POINT');n.inputs['Name'].default_value='tc_layer'
    g.put(geo,n.inputs['Geometry']);g.put(layer,n.inputs['Value']);return n.outputs[0]


def _mat(g,geo,value):
    n=g.node('GeometryNodeSetMaterial');g.put(geo,n.inputs['Geometry']);n.inputs['Material'].default_value=value
    return n.outputs[0]


def _gate(g,geo,toggle):
    n=g.node('GeometryNodeSwitch',input_type='GEOMETRY');g.put(toggle,n.inputs['Switch']);g.put(geo,n.inputs['True'])
    return n.outputs[0]


def _store(g,geo,name,value,dtype,domain='POINT',label=''):
    n=g.node('GeometryNodeStoreNamedAttribute',label,data_type=dtype,domain=domain);n.inputs['Name'].default_value=name
    g.put(geo,n.inputs['Geometry']);g.put(value,n.inputs['Value']);return n.outputs[0]


def _named(g,name,dtype='FLOAT'):
    n=g.node('GeometryNodeInputNamedAttribute',data_type=dtype);n.inputs['Name'].default_value=name
    return n.outputs['Attribute']


def _enabled(node,name):
    return next(s for s in node.inputs if s.name==name and s.enabled)


def _index_switch(g,index,dtype,values,label=''):
    n=g.node('GeometryNodeIndexSwitch',label,data_type=dtype)
    while len(n.index_switch_items)<len(values):n.index_switch_items.new()
    g.put(index,n.inputs[0])
    for i,v in enumerate(values):g.put(v,n.inputs[i+1])
    return n.outputs[0]


def _dot(g,a,b):
    n=g.node('ShaderNodeVectorMath',operation='DOT_PRODUCT')
    g.put(a,n.inputs[0]);g.put(b,n.inputs[1]);return n.outputs['Value']


def _scale(g,vec,scalar):
    """vec * scalar, where scalar may be a plain float or a math-node socket
    (ShaderNodeVectorMath's second input needs an actual vector, not a bare float)."""
    factor=(scalar,scalar,scalar) if isinstance(scalar,(int,float)) else g.vector(scalar,scalar,scalar)
    return g.vmath('MULTIPLY',vec,factor)


def _spline_count(g,geo):
    n=g.node('GeometryNodeAttributeDomainSize',component='CURVE');g.put(geo,n.inputs['Geometry'])
    return n.outputs['Spline Count']


def _boolean_op(g,a,b,op,label=''):
    n=g.node('GeometryNodeMeshBoolean',label or ('Curved street '+op.lower()),operation=op,solver='EXACT')
    if op=='INTERSECT':
        g.put(a,n.inputs['Mesh 2']);g.put(b,n.inputs['Mesh 2'])
    else:
        g.put(a,n.inputs['Mesh 1']);g.put(b,n.inputs['Mesh 2'])
    return n.outputs['Mesh']


def _region_prism(g,p,bottom,top,label=''):
    """A watertight solid over the region footprint, from z=bottom to z=top."""
    normal=g.node('GeometryNodeInputNormal');sep=g.node('ShaderNodeSeparateXYZ');g.put(normal.outputs[0],sep.inputs[0])
    flip=g.node('GeometryNodeFlipFaces')
    g.put(p['Geometry'],flip.inputs['Mesh']);g.put(g.math('LESS_THAN',sep.outputs['Z'],0),flip.inputs['Selection'])
    base=_transform(g,flip.outputs[0],translation=g.vector(0,0,bottom))
    e=g.node('GeometryNodeExtrudeMesh',label or 'Curved region volume',mode='FACES')
    g.put(base,e.inputs['Mesh']);e.inputs['Individual'].default_value=False
    g.put(g.vector(0,0,_sub(g,top,bottom)),e.inputs['Offset']);e.inputs['Offset Scale'].default_value=1
    bottom_face=g.node('GeometryNodeFlipFaces');g.put(base,bottom_face.inputs['Mesh'])
    merged=g.node('GeometryNodeMergeByDistance')
    g.put(_join(g,[e.outputs['Mesh'],bottom_face.outputs[0]]),merged.inputs['Geometry'])
    merged.inputs['Distance'].default_value=.00001
    return merged.outputs[0]


# --------------------------------------------------------------- 4.1 centerline
def build_centerline(g,p,region_geo,road_mesh_geo):
    """Combine mesh-drawn road edges with an optional external curve object.

    road_mesh_geo is already the region's free (Face Count == 0) edges, pre-filtered
    by nodes.py's ensure_group() — not a boolean selection field.

    Returns (curve geometry resampled by Road Resolution with tc_u/tc_curve_id/
    tc_junction_dist/tc_markings stored, has_curve boolean field).
    """
    mesh_curve=g.node('GeometryNodeMeshToCurve','Free edges to poly curve')
    g.put(road_mesh_geo,mesh_curve.inputs['Mesh'])
    length_node=g.node('GeometryNodeSplineLength')
    poly_with_len=_store(g,mesh_curve.outputs[0],'tc_orig_len',length_node.outputs['Length'],'FLOAT',domain='CURVE')
    smooth=g.node('GeometryNodeCurveSplineType','Smooth streets',spline_type='CATMULL_ROM')
    g.put(poly_with_len,smooth.inputs['Curve'])
    # Catmull-Rom overshoots past the drawn endpoints (docs/PLAN.md §3 spike #6);
    # clamp back to the original polyline length captured before the conversion.
    trim=g.node('GeometryNodeTrimCurve',mode='LENGTH')
    g.put(smooth.outputs[0],trim.inputs['Curve'])
    _enabled(trim,'Start').default_value=0
    g.put(_named(g,'tc_orig_len'),_enabled(trim,'End'))
    smoothed=trim.outputs['Curve']
    smooth_switch=g.node('GeometryNodeSwitch','Smooth or sharp streets',input_type='GEOMETRY')
    g.put(p['Smooth Streets'],smooth_switch.inputs['Switch'])
    g.put(poly_with_len,smooth_switch.inputs['False']);g.put(smoothed,smooth_switch.inputs['True'])
    mesh_result=smooth_switch.outputs[0]

    obj_info=g.node('GeometryNodeObjectInfo','External road curve object',transform_space='RELATIVE')
    g.put(p['Road Curves'],obj_info.inputs['Object'])
    has_external=g.math('GREATER_THAN',_spline_count(g,obj_info.outputs['Geometry']),0)
    curve_switch=g.node('GeometryNodeSwitch','Mesh edges or external curve object',input_type='GEOMETRY')
    g.put(has_external,curve_switch.inputs['Switch'])
    g.put(mesh_result,curve_switch.inputs['False']);g.put(obj_info.outputs['Geometry'],curve_switch.inputs['True'])
    combined=curve_switch.outputs[0]

    idx=g.node('GeometryNodeInputIndex').outputs[0]
    combined=_store(g,combined,'tc_curve_id',idx,'INT',domain='CURVE')
    has_curve=g.math('GREATER_THAN',_spline_count(g,combined),0)

    resample=g.node('GeometryNodeResampleCurve','Road resolution')
    g.put(combined,resample.inputs['Curve'])
    resample.inputs['Mode'].default_value='Length'
    g.put(p['Road Resolution'],resample.inputs['Length'])
    param=g.node('GeometryNodeSplineParameter')
    resampled=_store(g,resample.outputs[0],'tc_u',param.outputs['Length'],'FLOAT')
    total=g.node('GeometryNodeSplineLength')
    resampled=_store(g,resampled,'tc_total_len',total.outputs['Length'],'FLOAT',domain='CURVE')
    total_attr=_named(g,'tc_total_len')
    u_attr=_named(g,'tc_u')
    junction_dist=g.math('MINIMUM',u_attr,g.math('SUBTRACT',total_attr,u_attr))
    resampled=_store(g,resampled,'tc_junction_dist',junction_dist,'FLOAT')
    resampled=_store(g,resampled,'tc_markings',p['Road Markings'],'FLOAT')
    return resampled,has_curve


# ----------------------------------------------------------------- 4.2 profile
def build_profile(g,p):
    """Closed cross-section loop: bottom → curb → sidewalk → road top → mirror."""
    half=_mul(g,p['Road Width'],.5)
    outer=_add(g,half,p['Sidewalk Width'])
    neg_outer=g.math('MULTIPLY',outer,-1);neg_half=g.math('MULTIPLY',half,-1)
    T=g.math('MULTIPLY',p['Road Thickness'],-1)
    H=p['Curb Height']
    xs=[neg_outer,neg_outer,neg_half,neg_half,half,half,outer,outer]
    zs=[T,H,H,0,0,H,H,T]
    profs=[1,2,1,0,1,2,1,1]
    line=g.node('GeometryNodeMeshLine','Road profile points',mode='OFFSET');g.put(8,line.inputs['Count'])
    idx=g.node('GeometryNodeInputIndex').outputs[0]
    x=_index_switch(g,idx,'FLOAT',xs,'Profile lateral offset')
    z=_index_switch(g,idx,'FLOAT',zs,'Profile height')
    prof=_index_switch(g,idx,'INT',profs,'Profile material id')
    pos=g.vector(x,0,z)
    setpos=g.node('GeometryNodeSetPosition');g.put(line.outputs['Mesh'],setpos.inputs['Geometry']);g.put(pos,setpos.inputs['Position'])
    tagged=_store(g,setpos.outputs[0],'tc_v',x,'FLOAT')
    tagged=_store(g,tagged,'tc_profile',prof,'INT')
    to_curve=g.node('GeometryNodeMeshToCurve');g.put(tagged,to_curve.inputs['Mesh'])
    cyclic=g.node('GeometryNodeSetSplineCyclic','Close profile loop')
    g.put(to_curve.outputs[0],cyclic.inputs['Curve']);g.put(True,cyclic.inputs['Selection']);g.put(True,cyclic.inputs['Cyclic'])
    return cyclic.outputs[0],half,outer


# ------------------------------------------------------- 4.2 surface + ground
def build_surface(g,p,centerline,road_material_fn):
    profile,half,outer=build_profile(g,p)
    swept=g.node('GeometryNodeCurveToMesh','Sweep road cross-section')
    g.put(centerline,swept.inputs['Curve']);g.put(profile,swept.inputs['Profile Curve'])
    swept.inputs['Fill Caps'].default_value=True
    clip_bottom=g.math('MULTIPLY',p['Road Thickness'],-1)
    clip_top=g.math('ADD',p['Curb Height'],1)
    clip_volume=_region_prism(g,p,clip_bottom,clip_top,'Road clip volume')
    clipped=_boolean_op(g,swept.outputs[0],clip_volume,'INTERSECT','Clip road to region')
    normal=g.node('GeometryNodeInputNormal',"Face normal");sep=g.node('ShaderNodeSeparateXYZ');g.put(normal.outputs[0],sep.inputs[0])
    flat=g.math('GREATER_THAN',sep.outputs['Z'],.9)
    # Classify by distance-to-centerline recomputed fresh from the face's own
    # position, not by averaging the stored tc_v point attribute to FACE domain:
    # the EXACT boolean retriangulates broadly (not just where it actually clips),
    # so a straddling triangle's interpolated tc_v can land on either side of the
    # asphalt/sidewalk boundary depending on triangulation happenstance — which
    # differed enough between a mesh-derived and an object-data curve of the exact
    # same shape to misclassify a large fraction of the road (found via docs/PLAN.md
    # §6 item 10's equivalence test). A geometric distance is well-defined for any
    # position regardless of how it was triangulated.
    centerline_pts=g.node('GeometryNodeCurveToPoints','Centerline points for classification',mode='EVALUATED')
    g.put(centerline,centerline_pts.inputs['Curve'])
    face_pos=g.node('GeometryNodeInputPosition').outputs[0]
    prox=g.node('GeometryNodeProximity','Distance to centerline',target_element='POINTS')
    g.put(centerline_pts.outputs['Points'],prox.inputs['Geometry']);g.put(face_pos,prox.inputs['Sample Position'])
    is_sidewalk=g.boolean('AND',flat,g.math('GREATER_THAN',prox.outputs['Distance'],g.math('ADD',half,.01)))
    is_asphalt=g.boolean('AND',flat,g.boolean('NOT',is_sidewalk))
    asphalt_sep=g.node('GeometryNodeSeparateGeometry','Asphalt faces',domain='FACE')
    g.put(clipped,asphalt_sep.inputs['Geometry']);g.put(is_asphalt,asphalt_sep.inputs['Selection'])
    paving_sep=g.node('GeometryNodeSeparateGeometry','Curb + sidewalk faces',domain='FACE')
    g.put(clipped,paving_sep.inputs['Geometry']);g.put(g.boolean('NOT',is_asphalt),paving_sep.inputs['Selection'])
    road=_mat(g,_tag(g,asphalt_sep.outputs['Selection'],1),road_material_fn())
    paving=_tag(g,paving_sep.outputs['Selection'],2)
    paving=_mat(g,paving,paving_material())
    curb_side=g.node('GeometryNodeSetMaterial','Curb concrete faces');g.put(paving,curb_side.inputs['Geometry'])
    curb_side.inputs['Material'].default_value=material('v04 Curb concrete',(.31,.315,.29),roughness=.84)
    g.put(g.math('LESS_THAN',g.math('ABSOLUTE',sep.outputs['Z']),.5),curb_side.inputs['Selection'])
    paving=curb_side.outputs[0]
    road_on=g.boolean('AND',p['Ground'],p['Road Surface'])
    sidewalk_on=g.boolean('AND',p['Ground'],p['Sidewalks'])
    ground=_region_prism(g,p,-.05,0,'Non-road ground slab')
    ground=_boolean_op(g,ground,clipped,'DIFFERENCE','Non-road ground minus street')
    ground=_mat(g,_tag(g,ground,4),material('v05 Bare ground',(.30,.27,.20),roughness=.92))
    results=[_gate(g,road,road_on),_gate(g,paving,sidewalk_on),_gate(g,ground,p['Ground'])]
    return results,half,outer


# ------------------------------------------------------------- 4.4 road paint
def curve_road_material():
    from .nodes import Graph
    from .assets import PREFIX
    name=PREFIX+'v05 Curved asphalt + procedural road paint'
    if name in bpy.data.materials: return bpy.data.materials[name]
    m=material('v05 Curved asphalt + procedural road paint',(.07,.075,.07),roughness=.86)
    g=Graph(m.node_tree); bs=m.node_tree.nodes.get('Principled BSDF')
    tex=g.node('ShaderNodeTexCoord')
    attrs={}
    for key in ('u','v','junction_dist','markings'):
        a=g.node('ShaderNodeAttribute'); a.attribute_name='tc_'+key
        attrs[key]=a.outputs['Fac']
    v=attrs['v'];jd=attrs['junction_dist']
    # Double yellow center line, both sides of the centerline.
    yellow=g.math('LESS_THAN',g.math('ABSOLUTE',g.math('SUBTRACT',g.math('ABSOLUTE',v),.15)),.05)
    # Stop bar and zebra crossing near either drawn endpoint. tc_junction_dist is a
    # proxy (distance to the nearest curve endpoint) until 0.6 adds real junctions
    # (docs/PLAN.md §4.4 / §7); only the value's source changes later, not the shader.
    lane=g.math('LESS_THAN',g.math('ABSOLUTE',v),2.4)
    stop=g.math('MULTIPLY',lane,g.math('MULTIPLY',g.math('LESS_THAN',jd,6.5),g.math('GREATER_THAN',jd,5.5)))
    stripes=g.math('LESS_THAN',g.math('PINGPONG',v,.65),.30)
    zebra=g.math('MULTIPLY',lane,g.math('MULTIPLY',g.math('LESS_THAN',jd,5.5),stripes))
    white=g.math('MAXIMUM',stop,zebra)
    wear=g.node('ShaderNodeTexNoise');wear.inputs['Scale'].default_value=24;g.put(tex.outputs['Object'],wear.inputs['Vector'])
    worn=g.math('MULTIPLY',g.math('GREATER_THAN',wear.outputs['Fac'],.31),attrs['markings'])
    yellow=g.math('MULTIPLY',yellow,worn);white=g.math('MULTIPLY',white,worn)
    noise=g.node('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value=95
    g.put(tex.outputs['Object'],noise.inputs['Vector'])
    base=g.node('ShaderNodeMixRGB')
    g.put(noise.outputs['Fac'],base.inputs[0])
    base.inputs[1].default_value=(.035,.043,.042,1); base.inputs[2].default_value=(.08,.09,.085,1)
    paint=g.node('ShaderNodeMixRGB'); g.put(yellow,paint.inputs[0]);g.put(base.outputs[0],paint.inputs[1])
    paint.inputs[2].default_value=(.9,.53,.055,1)
    final=g.node('ShaderNodeMixRGB');g.put(white,final.inputs[0]);g.put(paint.outputs[0],final.inputs[1])
    final.inputs[2].default_value=(.78,.77,.65,1)
    g.put(final.outputs[0],bs.inputs['Base Color'])
    bump=g.node('ShaderNodeBump');bump.inputs['Strength'].default_value=.20;bump.inputs['Distance'].default_value=.004
    g.put(noise.outputs['Fac'],bump.inputs['Height']);g.put(bump.outputs[0],bs.inputs['Normal'])
    return m


# ------------------------------------------------------------ 4.3 building line
def _inside(g,p,region_geo,boundary_sel,pos,radius):
    ray=g.node('GeometryNodeRaycast','Grounded parcel',data_type='FLOAT')
    g.put(region_geo,ray.inputs['Target Geometry']);g.put(g.vmath('ADD',pos,(0,0,100)),ray.inputs['Source Position'])
    ray.inputs['Ray Direction'].default_value=(0,0,-1);ray.inputs['Ray Length'].default_value=200
    prox=g.node('GeometryNodeProximity',target_element='EDGES')
    g.put(boundary_sel,prox.inputs['Geometry']);g.put(pos,prox.inputs['Sample Position'])
    return g.boolean('AND',ray.outputs['Is Hit'],g.math('GREATER_THAN',prox.outputs['Distance'],radius))


# ------------------------------------------------------------ 4.3 building line
def _inside(g,p,region_geo,boundary_sel,pos,radius):
    ray=g.node('GeometryNodeRaycast','Grounded parcel',data_type='FLOAT')
    g.put(region_geo,ray.inputs['Target Geometry']);g.put(g.vmath('ADD',pos,(0,0,100)),ray.inputs['Source Position'])
    ray.inputs['Ray Direction'].default_value=(0,0,-1);ray.inputs['Ray Length'].default_value=200
    prox=g.node('GeometryNodeProximity',target_element='EDGES')
    g.put(boundary_sel,prox.inputs['Geometry']);g.put(pos,prox.inputs['Sample Position'])
    return g.boolean('AND',ray.outputs['Is Hit'],g.math('GREATER_THAN',prox.outputs['Distance'],radius))


def _place_side(g,p,cols,region_geo,boundary_sel,centerline,dense,side):
    """One row of parcels on one side of the streets, resampled along the offset
    building line (docs/PLAN.md §4.3); optionally bent to follow the curve."""
    outer=g.math('ADD',g.math('MULTIPLY',p['Road Width'],.5),p['Sidewalk Width'])
    normal_attr=_named(g,'tc_normal','FLOAT_VECTOR')
    lateral=_scale(g,normal_attr,g.math('MULTIPLY',outer,float(side)))
    offset_curve=g.node('GeometryNodeSetPosition',f'Offset building line {side:+d}')
    g.put(dense,offset_curve.inputs['Geometry']);g.put(lateral,offset_curve.inputs['Offset'])
    dense_side=offset_curve.outputs[0]
    frontage=g.node('GeometryNodeResampleCurve',f'One point per lot {side:+d}')
    g.put(dense_side,frontage.inputs['Curve']);frontage.inputs['Mode'].default_value='Length'
    g.put(p['Frontage'],frontage.inputs['Length'])
    site_tangent=g.node('GeometryNodeInputTangent').outputs[0]
    stsep=g.node('ShaderNodeSeparateXYZ');g.put(site_tangent,stsep.inputs[0])
    site_normal=g.vector(g.math('MULTIPLY',stsep.outputs['Y'],-1),stsep.outputs['X'],0)
    facing=_scale(g,site_normal,float(side))
    align=g.node('FunctionNodeAlignRotationToVector','Face nearest street',axis='Y')
    g.put(facing,align.inputs['Vector'])
    param=g.node('GeometryNodeSplineParameter')
    tagged=_store(g,frontage.outputs[0],'tc_site_u',param.outputs['Length'],'FLOAT')
    site_pos=g.node('GeometryNodeInputPosition').outputs[0]
    tagged=_store(g,tagged,'tc_site_pos',site_pos,'FLOAT_VECTOR')
    tagged=_store(g,tagged,'tc_site_tangent',site_tangent,'FLOAT_VECTOR')
    tagged=_store(g,tagged,'tc_site_normal',site_normal,'FLOAT_VECTOR')
    curve_id=_named(g,'tc_curve_id','INT')
    tagged=_store(g,tagged,'tc_site_curve_id',curve_id,'INT')
    topoints=g.node('GeometryNodeCurveToPoints',f'Building line lots {side:+d}',mode='EVALUATED')
    g.put(tagged,topoints.inputs['Curve'])
    points=topoints.outputs['Points']
    idx=g.node('GeometryNodeInputIndex').outputs[0]
    site_offset=0 if side>0 else 500000
    site_id=g.math('ADD',idx,site_offset)

    pos=g.node('GeometryNodeInputPosition').outputs[0]
    radius=g.math('ADD',g.math('MULTIPLY',g.math('SQRT',g.math('ADD',g.math('MULTIPLY',p['Frontage'],p['Frontage']),
                    g.math('MULTIPLY',p['Depth'],p['Depth']))),.5),p['Boundary Setback'])
    inside=_inside(g,p,region_geo,boundary_sel,pos,radius)
    own_id=_named(g,'tc_site_curve_id','INT')
    prox_any=g.node('GeometryNodeProximity','Nearest street',target_element='POINTS')
    g.put(centerline,prox_any.inputs['Geometry']);g.put(pos,prox_any.inputs['Sample Position'])
    centerline_id=_named(g,'tc_curve_id','INT')
    prox_own=g.node('GeometryNodeProximity','Nearest point on own street',target_element='POINTS')
    g.put(centerline,prox_own.inputs['Geometry']);g.put(pos,prox_own.inputs['Sample Position'])
    g.put(centerline_id,prox_own.inputs['Group ID']);g.put(own_id,prox_own.inputs['Sample Group ID'])
    own_is_nearest=g.math('LESS_THAN',prox_own.outputs['Distance'],g.math('ADD',prox_any.outputs['Distance'],.05))
    occupied=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,43),p['Density'])
    choose=g.boolean('AND',g.boolean('AND',inside,own_is_nearest),occupied)

    floors=g.random('INT',g.math('MINIMUM',p['Min Floors'],p['Max Floors']),g.math('MAXIMUM',p['Min Floors'],p['Max Floors']),p['Seed'],site_id,101)
    typ=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,307),p['Townhouse Mix'])
    palette=g.random('INT',0,2,p['Seed'],site_id,701)
    asset=g.math('ADD',g.math('MULTIPLY',g.math('SUBTRACT',floors,2),6),g.math('ADD',g.math('MULTIPLY',typ,3),palette))
    is_shed=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,1103),p['Metal Shed Mix'])
    shed_asset=g.math('ADD',36,g.random('INT',0,5,p['Seed'],site_id,1201))
    select=g.node('GeometryNodeSwitch','Rowhouse or metal workshop',input_type='INT')
    g.put(is_shed,select.inputs['Switch']);g.put(asset,select.inputs['False']);g.put(shed_asset,select.inputs['True'])
    asset=select.outputs[0]
    storeys=g.node('GeometryNodeSwitch','One-storey sheds',input_type='INT')
    g.put(is_shed,storeys.inputs['Switch']);g.put(floors,storeys.inputs['False']);storeys.inputs['True'].default_value=1
    floors=storeys.outputs[0]
    geo=points
    for name,value,dtype in [('tc_parcel_id',site_id,'INT'),('tc_floors',floors,'INT'),('tc_asset',asset,'INT'),
                              ('tc_is_shed',is_shed,'BOOLEAN')]:
        geo=_store(g,geo,name,value,dtype)
    # geo is already a Points component (from CurveToPoints above); just filter it.
    meshpts=g.node('GeometryNodeSeparateGeometry','Chosen lots',domain='POINT')
    g.put(geo,meshpts.inputs['Geometry']);g.put(choose,meshpts.inputs['Selection'])

    named=g.node('GeometryNodeInputNamedAttribute',data_type='INT');named.inputs['Name'].default_value='tc_asset'
    shed_attr=g.node('GeometryNodeInputNamedAttribute',data_type='BOOLEAN');shed_attr.inputs['Name'].default_value='tc_is_shed'
    parcel_attr=g.node('GeometryNodeInputNamedAttribute',data_type='INT');parcel_attr.inputs['Name'].default_value='tc_parcel_id'
    addon_probability=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],parcel_attr.outputs['Attribute'],1601),p['Rooftop Addition Mix'])
    scale=g.vector(g.math('DIVIDE',p['Frontage'],6.4),g.math('DIVIDE',p['Depth'],12),1)
    rotation=align.outputs['Rotation']
    pieces=[]
    for key,toggle in [('Buildings','Buildings'),('Signs','Signs'),('Roofs','Rooftops'),('Street life','Street Life'),('Additions','Rooftops')]:
        collection=g.node('GeometryNodeCollectionInfo',key)
        collection.inputs['Collection'].default_value=cols[key]
        collection.inputs['Separate Children'].default_value=True
        collection.inputs['Reset Children'].default_value=True
        instance=g.node('GeometryNodeInstanceOnPoints',key+f' on curved lots {side:+d}')
        g.put(meshpts.outputs['Selection'],instance.inputs['Points'])
        g.put(collection.outputs['Instances'],instance.inputs['Instance'])
        instance.inputs['Pick Instance'].default_value=True
        g.put(named.outputs['Attribute'],instance.inputs['Instance Index'])
        g.put(rotation,instance.inputs['Rotation']);g.put(scale,instance.inputs['Scale'])
        selection=p[toggle] if key=='Buildings' else g.boolean('AND',p[toggle],p['Buildings'])
        if key=='Additions':selection=g.boolean('AND',selection,g.boolean('AND',addon_probability,g.boolean('NOT',shed_attr.outputs['Attribute'])))
        g.put(selection,instance.inputs['Selection'])
        pieces.append(instance.outputs['Instances'])
    return _bend(g,p,dense_side,pieces,side)


def _bend(g,p,frontage_curve,pieces,side):
    """Realize each rigid instance and resample its vertices along the offset
    building line, holding local footprint shape (docs/PLAN.md §4.3 last algorithm).

    The building's true local X/Y axes are (side*tangent, side*normal) — see the
    rotation built in _place_side/_furniture_side (axis='Y' aligned to
    side*normal) — so the along-curve coordinate needs the same side factor;
    it cancels out (side**2 == 1) for the lateral offset, which needs none.
    """
    bent=[]
    for instances in pieces:
        realized=g.node('GeometryNodeRealizeInstances','Realize for bending')
        g.put(instances,realized.inputs['Geometry'])
        vertex_pos=g.node('GeometryNodeInputPosition').outputs[0]
        site_pos=_named(g,'tc_site_pos','FLOAT_VECTOR')
        site_tangent=_named(g,'tc_site_tangent','FLOAT_VECTOR')
        site_normal=_named(g,'tc_site_normal','FLOAT_VECTOR')
        site_u=_named(g,'tc_site_u')
        offset=g.vmath('SUBTRACT',vertex_pos,site_pos)
        local_x=g.math('MULTIPLY',_dot(g,offset,site_tangent),float(side))
        local_y=_dot(g,offset,site_normal)
        new_u=g.math('ADD',site_u,local_x)
        sample=g.node('GeometryNodeSampleCurve','Bend along building line',mode='LENGTH')
        g.put(frontage_curve,sample.inputs['Curves']);g.put(new_u,_enabled(sample,'Length'))
        tsep=g.node('ShaderNodeSeparateXYZ');g.put(sample.outputs['Tangent'],tsep.inputs[0])
        curve_normal=g.vector(g.math('MULTIPLY',tsep.outputs['Y'],-1),tsep.outputs['X'],0)
        new_pos=g.vmath('ADD',sample.outputs['Position'],_scale(g,curve_normal,local_y))
        zsep=g.node('ShaderNodeSeparateXYZ');g.put(vertex_pos,zsep.inputs[0])
        final_pos=g.vmath('ADD',new_pos,g.vector(0,0,zsep.outputs['Z']))
        moved=g.node('GeometryNodeSetPosition','Bent world position')
        g.put(realized.outputs[0],moved.inputs['Geometry']);g.put(final_pos,moved.inputs['Position'])
        rigid_switch=g.node('GeometryNodeSwitch','Bend toggle',input_type='GEOMETRY')
        g.put(p['Bend Buildings to Curve'],rigid_switch.inputs['Switch'])
        g.put(instances,rigid_switch.inputs['False']);g.put(moved.outputs[0],rigid_switch.inputs['True'])
        bent.append(rigid_switch.outputs[0])
    return bent


def build_sites(g,p,cols,region_geo,boundary_sel,centerline):
    dense=g.node('GeometryNodeResampleCurve','Dense centerline for offsets')
    g.put(centerline,dense.inputs['Curve']);dense.inputs['Mode'].default_value='Length';g.put(.25,dense.inputs['Length'])
    tangent=g.node('GeometryNodeInputTangent').outputs[0]
    tsep=g.node('ShaderNodeSeparateXYZ');g.put(tangent,tsep.inputs[0])
    normal_lateral=g.vector(g.math('MULTIPLY',tsep.outputs['Y'],-1),tsep.outputs['X'],0)
    dense_geo=_store(g,dense.outputs[0],'tc_tangent',tangent,'FLOAT_VECTOR')
    dense_geo=_store(g,dense_geo,'tc_normal',normal_lateral,'FLOAT_VECTOR')
    # Geometry Proximity's POINTS target only accepts mesh/point-cloud geometry, not
    # a raw curve, so realize the centerline's own points once for the group-id check.
    centerline_pts=g.node('GeometryNodeCurveToPoints','Centerline points for proximity',mode='EVALUATED')
    g.put(centerline,centerline_pts.inputs['Curve'])
    pieces=[]
    for side in (1,-1):
        pieces+=_place_side(g,p,cols,region_geo,boundary_sel,centerline_pts.outputs['Points'],dense_geo,side)
    return pieces


# ---------------------------------------------------------- 4.5 street furniture
def _instance(g,pts,geo,selection=True,rotation=(0,0,0),scale=(1,1,1),label='',realize=False):
    n=g.node('GeometryNodeInstanceOnPoints',label)
    for value,key in [(pts,'Points'),(geo,'Instance'),(selection,'Selection'),(rotation,'Rotation'),(scale,'Scale')]:g.put(value,n.inputs[key])
    if not realize:return n.outputs['Instances']
    r=g.node('GeometryNodeRealizeInstances');g.put(n.outputs['Instances'],r.inputs['Geometry']);return r.outputs[0]


def build_furniture(g,p,region_geo,boundary_sel,centerline):
    height=g.math('MULTIPLY',p['Curb Height'],p['Sidewalks'])
    results=[]
    for side in (1,-1):
        results+=_furniture_side(g,p,region_geo,boundary_sel,centerline,height,side)
    return results


def _furniture_side(g,p,region_geo,boundary_sel,centerline,height,side):
    assets=ensure_street_assets()
    def source(key):
        n=g.node('GeometryNodeObjectInfo',key+f' source {side:+d}')
        n.inputs['Object'].default_value=assets[key];n.inputs['As Instance'].default_value=True
        return n.outputs['Geometry']
    half=g.math('MULTIPLY',p['Road Width'],.5)
    outer=g.math('ADD',half,p['Sidewalk Width'])
    pole_line=g.node('GeometryNodeResampleCurve',f'Pole spacing {side:+d}')
    g.put(centerline,pole_line.inputs['Curve']);pole_line.inputs['Mode'].default_value='Length'
    g.put(p['Pole Spacing'],pole_line.inputs['Length'])
    tangent=g.node('GeometryNodeInputTangent').outputs[0]
    tsep=g.node('ShaderNodeSeparateXYZ');g.put(tangent,tsep.inputs[0])
    normal=g.vector(g.math('MULTIPLY',tsep.outputs['Y'],-1),tsep.outputs['X'],0)
    facing=_scale(g,normal,float(side))
    align=g.node('FunctionNodeAlignRotationToVector',f'Furniture faces street {side:+d}',axis='Y')
    g.put(facing,align.inputs['Vector'])
    rotation=align.outputs['Rotation']

    def offset_points(curve,dist,label):
        lateral=_scale(g,normal,g.math('MULTIPLY',dist,float(side)))
        moved=g.node('GeometryNodeSetPosition',label);g.put(curve,moved.inputs['Geometry']);g.put(lateral,moved.inputs['Offset'])
        pts=g.node('GeometryNodeCurveToPoints',label+' points',mode='EVALUATED');g.put(moved.outputs[0],pts.inputs['Curve'])
        return pts.outputs['Points']

    pos=g.node('GeometryNodeInputPosition').outputs[0]
    valid=_inside(g,p,region_geo,boundary_sel,pos,.93)

    pole_offset=g.math('ADD',outer,.6)
    poles=offset_points(pole_line.outputs[0],pole_offset,f'Pole anchors {side:+d}')
    pole_geo=_transform(g,source('Pole'),translation=g.vector(0,0,height),scale=g.vector(1,1,g.math('DIVIDE',p['Pole Height'],9)))
    results=[_instance(g,poles,pole_geo,g.boolean('AND',p['Utility Poles'],valid),rotation,label=f'Utility poles {side:+d}')]

    cabinet_line=g.node('GeometryNodeResampleCurve',f'Cabinet candidate spacing {side:+d}')
    g.put(centerline,cabinet_line.inputs['Curve']);cabinet_line.inputs['Mode'].default_value='Length'
    g.put(g.math('MULTIPLY',p['Frontage'],p['Lots per Block']),cabinet_line.inputs['Length'])
    cabinet_offset=g.math('ADD',pole_offset,1.35)
    cabinets=offset_points(cabinet_line.outputs[0],cabinet_offset,f'Cabinet anchors {side:+d}')
    cidx=g.node('GeometryNodeInputIndex').outputs[0]
    cab_id=g.math('ADD',cidx,0 if side>0 else 300000)
    cab_valid=g.boolean('AND',valid,g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],cab_id,2601),p['Cabinet Density']))
    results.append(_instance(g,cabinets,_transform(g,source('Telecom'),translation=g.vector(0,0,height)),
                              g.boolean('AND',p['Telecom Cabinets'],cab_valid),rotation,label=f'Telecom cabinets {side:+d}'))

    detail_on=g.boolean('AND',p['Road Details'],g.boolean('AND',p['Ground'],p['Road Surface']))
    drain_offset=g.math('ADD',half,.25)
    drains=offset_points(pole_line.outputs[0],drain_offset,f'Drain anchors {side:+d}')
    results.append(_instance(g,drains,source('Drain'),g.boolean('AND',detail_on,valid),rotation,label=f'Storm drains {side:+d}'))
    manhole_offset=g.math('MULTIPLY',half,.6)
    manholes=offset_points(pole_line.outputs[0],manhole_offset,f'Manhole anchors {side:+d}')
    results.append(_instance(g,manholes,source('Manhole'),g.boolean('AND',detail_on,valid),label=f'Manholes {side:+d}'))
    return results


# ------------------------------------------------------------------ 4.6 wires
def build_wires(g,p,region_geo,boundary_sel,centerline):
    results=[]
    for side in (1,-1):
        results+=_wires_side(g,p,region_geo,boundary_sel,centerline,side)
    return results


def _wires_side(g,p,region_geo,boundary_sel,centerline,side):
    half=g.math('MULTIPLY',p['Road Width'],.5)
    outer=g.math('ADD',half,p['Sidewalk Width'])
    pole_offset=g.math('ADD',outer,.6)
    pole_line=g.node('GeometryNodeResampleCurve',f'Wire pole spacing {side:+d}')
    g.put(centerline,pole_line.inputs['Curve']);pole_line.inputs['Mode'].default_value='Length'
    g.put(p['Pole Spacing'],pole_line.inputs['Length'])
    tangent=g.node('GeometryNodeInputTangent').outputs[0]
    tsep=g.node('ShaderNodeSeparateXYZ');g.put(tangent,tsep.inputs[0])
    normal=g.vector(g.math('MULTIPLY',tsep.outputs['Y'],-1),tsep.outputs['X'],0)
    lateral=_scale(g,normal,g.math('MULTIPLY',pole_offset,float(side)))
    moved=g.node('GeometryNodeSetPosition',f'Offset pole line {side:+d}')
    g.put(pole_line.outputs[0],moved.inputs['Geometry']);g.put(lateral,moved.inputs['Offset'])
    height=g.math('MULTIPLY',p['Curb Height'],p['Sidewalks'])

    idxnode=g.node('GeometryNodeInputIndex').outputs[0]
    next_offset=g.node('GeometryNodeOffsetPointInCurve',f'Next pole {side:+d}')
    g.put(idxnode,next_offset.inputs['Point Index']);next_offset.inputs['Offset'].default_value=1
    sample_pos=g.node('GeometryNodeSampleIndex',f'Next pole position {side:+d}',data_type='FLOAT_VECTOR')
    g.put(moved.outputs[0],sample_pos.inputs['Geometry'])
    pos_field=g.node('GeometryNodeInputPosition').outputs[0]
    g.put(pos_field,sample_pos.inputs['Value']);g.put(next_offset.outputs['Point Index'],sample_pos.inputs['Index'])
    chord=g.vmath('SUBTRACT',sample_pos.outputs['Value'],pos_field)
    chord_length=g.node('ShaderNodeVectorMath',operation='LENGTH');g.put(chord,chord_length.inputs[0])

    valid=_inside(g,p,region_geo,boundary_sel,pos_field,.93)
    next_valid=_inside(g,p,region_geo,boundary_sel,sample_pos.outputs['Value'],.93)
    connected=g.boolean('AND',valid,g.boolean('AND',next_offset.outputs['Is Valid Offset'],next_valid))
    spanpts=g.node('GeometryNodeCurveToPoints',f'Wire span anchors {side:+d}',mode='EVALUATED')
    tagged=_store(g,moved.outputs[0],'tc_chord',chord,'FLOAT_VECTOR')
    tagged=_store(g,tagged,'tc_chord_len',chord_length.outputs['Value'],'FLOAT')
    tagged=_store(g,tagged,'tc_connected',connected,'BOOLEAN')
    g.put(tagged,spanpts.inputs['Curve'])
    span_pos=g.node('GeometryNodeInputPosition').outputs[0]
    chord_attr=_named(g,'tc_chord','FLOAT_VECTOR');chord_len_attr=_named(g,'tc_chord_len')
    connected_attr=_named(g,'tc_connected','BOOLEAN')
    align=g.node('FunctionNodeAlignRotationToVector',f'Span follows chord {side:+d}',axis='X')
    g.put(chord_attr,align.inputs['Vector'])

    line=g.node('GeometryNodeCurvePrimitiveLine',mode='POINTS');g.put((1.0,0,0),line.inputs['End'])
    resample=g.node('GeometryNodeResampleCurve','Wire sag profile');g.put(line.outputs[0],resample.inputs['Curve']);resample.inputs['Count'].default_value=33
    factor=g.node('GeometryNodeSplineParameter').outputs['Factor']
    sag=g.math('MINIMUM',p['Cable Sag'],g.math('MULTIPLY',p['Pole Height'],.12))
    drop=g.math('MULTIPLY',g.math('MULTIPLY',g.math('MULTIPLY',factor,g.math('SUBTRACT',1,factor)),sag),-4)
    bend=g.node('GeometryNodeSetPosition','Parabolic cable sag (curved)')
    g.put(resample.outputs[0],bend.inputs['Geometry']);g.put(g.vector(0,0,drop),bend.inputs['Offset'])
    circle=g.node('GeometryNodeCurvePrimitiveCircle',mode='RADIUS');circle.inputs['Resolution'].default_value=8;circle.inputs['Radius'].default_value=.019
    tube=g.node('GeometryNodeCurveToMesh');g.put(bend.outputs[0],tube.inputs['Curve']);g.put(circle.outputs[0],tube.inputs['Profile Curve']);tube.inputs['Fill Caps'].default_value=True
    wires=[]
    for y,z in [(-.38,8.66),(0,8.66),(.38,8.66),(-.27,6.18),(-.12,6.18)]:
        wires.append(_transform(g,tube.outputs[0],translation=g.vector(0,y,g.math('ADD',height,g.math('MULTIPLY',p['Pole Height'],z/9)))))
    wire_geo=_mat(g,_tag(g,_join(g,wires),3),material('v04 Cable rubber',(.015,.018,.019),roughness=.57))
    wire_on=g.boolean('AND',p['Utility Poles'],p['Overhead Wires'])
    scale=g.vector(chord_len_attr,1,1)
    return [_instance(g,spanpts.outputs['Points'],wire_geo,g.boolean('AND',wire_on,connected_attr),
                       align.outputs['Rotation'],scale,label=f'Continuous overhead spans {side:+d}',realize=True)]


# ------------------------------------------------------------------ orchestrator
def curve_district(g,p,cols,region_geo,road_mesh_geo,boundary_sel,road_material_fn):
    """Entry point for the whole curved-road branch. Returns (geometry, has_curve)."""
    centerline,has_curve=build_centerline(g,p,region_geo,road_mesh_geo)
    surface,half,outer=build_surface(g,p,centerline,road_material_fn)
    sites=build_sites(g,p,cols,region_geo,boundary_sel,centerline)
    furniture=build_furniture(g,p,region_geo,boundary_sel,centerline)
    wires=build_wires(g,p,region_geo,boundary_sel,centerline)
    return _join(g,surface+sites+furniture+wires,'Curved district layers'),has_curve
