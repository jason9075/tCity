"""Road-driven district pipeline for TCity 0.7.

Hand-drawn or external curves override an internal orthogonal road mesh. No Python
runs during evaluation; this module only constructs Geometry Nodes.
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


def _sample_region_float(g,region_geo,position,name,fallback,label=''):
    """Sample an optional float attribute from the source region surface."""
    attribute=g.node('GeometryNodeInputNamedAttribute',data_type='FLOAT')
    attribute.inputs['Name'].default_value=name
    sample=g.node('GeometryNodeSampleNearestSurface',label or f'Sample {name}',data_type='FLOAT')
    g.put(region_geo,sample.inputs['Mesh']);g.put(attribute.outputs['Attribute'],_enabled(sample,'Value'))
    g.put(position,sample.inputs['Sample Position'])
    exists=g.node('GeometryNodeSampleNearestSurface',f'{name} exists on region',data_type='BOOLEAN')
    g.put(region_geo,exists.inputs['Mesh']);g.put(attribute.outputs['Exists'],_enabled(exists,'Value'))
    g.put(position,exists.inputs['Sample Position'])
    chosen=g.node('GeometryNodeSwitch',f'{name} or global control',input_type='FLOAT')
    g.put(exists.outputs['Value'],chosen.inputs['Switch']);g.put(fallback,chosen.inputs['False'])
    g.put(sample.outputs['Value'],chosen.inputs['True'])
    return chosen.outputs[0],exists.outputs['Value']


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


def _point_count(g,geo):
    n=g.node('GeometryNodeAttributeDomainSize',component='POINTCLOUD');g.put(geo,n.inputs['Geometry'])
    return n.outputs['Point Count']


def _mesh_point_count(g,geo):
    n=g.node('GeometryNodeAttributeDomainSize',component='MESH');g.put(geo,n.inputs['Geometry'])
    return n.outputs['Point Count']


def _self_union(g,geo,label=''):
    """Mesh Boolean UNION on a single (possibly multi-island, overlapping) input —
    merges overlapping solids in place, e.g. streets meeting at a junction
    (docs/PLAN.md 0.6.0).

    Uses the FLOAT solver, not EXACT: the road cross-section's Fill Caps are a
    non-convex N-gon (the curb step), and EXACT + Fill Caps + self-union
    specifically collapsed the result to a small fraction of its real area
    (down from ~1700 m² to ~200 m² in testing) even for a single straight,
    non-branching street with no other geometry to merge with — EXACT alone
    (via the region-clip INTERSECT) and FLOAT alone were each individually
    fine, only this combination broke. FLOAT is measurably correct here
    (verified against the expected swept area) and only used for this one
    self-merge step; INTERSECT/DIFFERENCE elsewhere stay on EXACT.
    """
    n=g.node('GeometryNodeMeshBoolean',label or 'Self union',operation='UNION',solver='FLOAT')
    g.put(geo,n.inputs['Mesh 2'])
    return n.outputs['Mesh']


def _boolean_op(g,a,b,op,label=''):
    n=g.node('GeometryNodeMeshBoolean',label or ('Curved street '+op.lower()),operation=op,solver='EXACT')
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


# ----------------------------------------------------------------- 0.6 junctions
def find_junctions(g,road_mesh_geo):
    """Points where 3+ road edges meet (docs/PLAN.md 0.6.0).

    Mesh-edge input only: validate_region forbids road edges from touching the
    region boundary, so every vertex among road_mesh_geo touches only other road
    edges — its total edge-neighbor count is exactly its junction degree. External
    Road Curves objects don't get junction detection (a single Curve datablock has
    no natural vertex-degree/branching concept); tc_junction_dist just falls back
    to "no junction nearby" for that path.
    """
    vn=g.node('GeometryNodeInputMeshVertexNeighbors')
    is_junction=g.math('GREATER_THAN',vn.outputs['Vertex Count'],2.5)
    sep=g.node('GeometryNodeSeparateGeometry','Junction vertices',domain='POINT')
    g.put(road_mesh_geo,sep.inputs['Geometry']);g.put(is_junction,sep.inputs['Selection'])
    pts=g.node('GeometryNodeMeshToPoints','Junction points',mode='VERTICES')
    g.put(sep.outputs['Selection'],pts.inputs['Mesh'])
    has_junctions=g.math('GREATER_THAN',_point_count(g,pts.outputs['Points']),0)
    return pts.outputs['Points'],has_junctions


def build_grid_network(g,p,origin,span_x,span_y,px,py):
    """Build centered roads with shared junctions and boundary-reaching ends."""
    outer=_add(g,_mul(g,p['Road Width'],.5),p['Sidewalk Width'])
    reach_x=_add(g,_mul(g,span_x,.5),_add(g,outer,.5))
    reach_y=_add(g,_mul(g,span_y,.5),_add(g,outer,.5))
    usable_x=g.math('MAXIMUM',_sub(g,span_x,_mul(g,outer,2)),0)
    usable_y=g.math('MAXIMUM',_sub(g,span_y,_mul(g,outer,2)),0)
    steps_x=g.math('MAXIMUM',g.math('FLOOR',g.math('DIVIDE',usable_x,px)),1)
    steps_y=g.math('MAXIMUM',g.math('FLOOR',g.math('DIVIDE',usable_y,py)),1)
    extent_x=_mul(g,steps_x,px);extent_y=_mul(g,steps_y,py)
    count_x=_add(g,steps_x,3);count_y=_add(g,steps_y,3)
    grid=g.node('GeometryNodeMeshGrid','Internal orthogonal road network')
    g.put(span_x,grid.inputs['Size X']);g.put(span_y,grid.inputs['Size Y'])
    g.put(count_x,grid.inputs['Vertices X']);g.put(count_y,grid.inputs['Vertices Y'])
    idx=g.node('GeometryNodeInputIndex').outputs[0]
    col=g.math('MODULO',idx,count_x);row=g.math('FLOOR',g.math('DIVIDE',idx,count_x))
    def coordinate(slot,count,period,extent,reach,label):
        interior=_sub(g,_mul(g,_sub(g,slot,1),period),_mul(g,extent,.5))
        first=g.node('GeometryNodeSwitch',label+' first boundary',input_type='FLOAT')
        g.put(g.equal(slot,0,.01),first.inputs['Switch']);g.put(interior,first.inputs['False']);g.put(_mul(g,reach,-1),first.inputs['True'])
        last=g.node('GeometryNodeSwitch',label+' last boundary',input_type='FLOAT')
        g.put(g.equal(slot,_sub(g,count,1),.01),last.inputs['Switch']);g.put(first.outputs[0],last.inputs['False']);g.put(reach,last.inputs['True'])
        return last.outputs[0]
    local_x=coordinate(col,count_x,px,extent_x,reach_x,'Grid X')
    local_y=coordinate(row,count_y,py,extent_y,reach_y,'Grid Y')
    center=g.vmath('ADD',origin,g.vector(_mul(g,span_x,.5),_mul(g,span_y,.5),0))
    positioned=g.node('GeometryNodeSetPosition','Centered irregular road grid')
    g.put(grid.outputs['Mesh'],positioned.inputs['Geometry']);g.put(g.vmath('ADD',center,g.vector(local_x,local_y,0)),positioned.inputs['Position'])
    edges=g.node('GeometryNodeDeleteGeometry','Keep road grid edges',domain='FACE',mode='ONLY_FACE')
    g.put(positioned.outputs['Geometry'],edges.inputs['Geometry']);g.put(True,edges.inputs['Selection'])
    pos=g.node('GeometryNodeInputPosition').outputs[0];pos_sep=g.node('ShaderNodeSeparateXYZ');g.put(pos,pos_sep.inputs[0])
    center_sep=g.node('ShaderNodeSeparateXYZ');g.put(center,center_sep.inputs[0])
    min_x=_sub(g,center_sep.outputs['X'],reach_x);max_x=_add(g,center_sep.outputs['X'],reach_x)
    min_y=_sub(g,center_sep.outputs['Y'],reach_y);max_y=_add(g,center_sep.outputs['Y'],reach_y)
    perimeter_x=g.boolean('OR',g.equal(pos_sep.outputs['X'],min_x,.01),g.equal(pos_sep.outputs['X'],max_x,.01))
    perimeter_y=g.boolean('OR',g.equal(pos_sep.outputs['Y'],min_y,.01),g.equal(pos_sep.outputs['Y'],max_y,.01))
    without_perimeter=g.node('GeometryNodeDeleteGeometry','Remove boundary perimeter roads',domain='EDGE',mode='ALL')
    g.put(edges.outputs['Geometry'],without_perimeter.inputs['Geometry'])
    g.put(g.boolean('OR',perimeter_x,perimeter_y),without_perimeter.inputs['Selection'])
    return without_perimeter.outputs['Geometry']


# --------------------------------------------------------------- 4.1 centerline
def build_centerline(g,p,region_geo,road_mesh_geo,grid_road_mesh_geo,boundary_sel):
    """Choose drawn/external roads or the internal orthogonal fallback.

    road_mesh_geo is already the region's free (Face Count == 0) edges, pre-filtered
    by nodes.py's ensure_group() — not a boolean selection field.

    Returns the resampled centerline with inspection attributes, junction points,
    a junction-presence field, and whether the source came from the user.
    """
    has_drawn=g.math('GREATER_THAN',_mesh_point_count(g,road_mesh_geo),0)
    mesh_source=g.node('GeometryNodeSwitch','Internal grid or drawn road edges',input_type='GEOMETRY')
    g.put(has_drawn,mesh_source.inputs['Switch'])
    g.put(grid_road_mesh_geo,mesh_source.inputs['False']);g.put(road_mesh_geo,mesh_source.inputs['True'])
    selected_mesh=mesh_source.outputs[0]
    junction_points,has_mesh_junctions=find_junctions(g,selected_mesh)
    junction_pos=g.node('GeometryNodeInputPosition').outputs[0]
    interior_junctions=g.node('GeometryNodeSeparateGeometry','Junctions inside region',domain='POINT')
    g.put(junction_points,interior_junctions.inputs['Geometry'])
    junction_clearance=_add(g,_add(g,_mul(g,p['Road Width'],.5),p['Sidewalk Width']),.55)
    g.put(_inside(g,p,region_geo,boundary_sel,junction_pos,junction_clearance),interior_junctions.inputs['Selection'])
    junction_points=interior_junctions.outputs['Selection']
    has_mesh_junctions=g.math('GREATER_THAN',_point_count(g,junction_points),0)
    mesh_curve=g.node('GeometryNodeMeshToCurve','Free edges to poly curve')
    g.put(selected_mesh,mesh_curve.inputs['Mesh'])
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
    g.put(g.boolean('AND',p['Smooth Streets'],has_drawn),smooth_switch.inputs['Switch'])
    g.put(poly_with_len,smooth_switch.inputs['False']);g.put(smoothed,smooth_switch.inputs['True'])
    mesh_result=smooth_switch.outputs[0]

    obj_info=g.node('GeometryNodeObjectInfo','External road curve object',transform_space='RELATIVE')
    g.put(p['Road Curves'],obj_info.inputs['Object'])
    has_external=g.math('GREATER_THAN',_spline_count(g,obj_info.outputs['Geometry']),0)
    curve_switch=g.node('GeometryNodeSwitch','Mesh edges or external curve object',input_type='GEOMETRY')
    g.put(has_external,curve_switch.inputs['Switch'])
    g.put(mesh_result,curve_switch.inputs['False']);g.put(obj_info.outputs['Geometry'],curve_switch.inputs['True'])
    combined=curve_switch.outputs[0]

    empty=g.node('GeometryNodeJoinGeometry','No external-curve junction points').outputs[0]
    junction_switch=g.node('GeometryNodeSwitch','External curves have no mesh junctions',input_type='GEOMETRY')
    g.put(has_external,junction_switch.inputs['Switch'])
    g.put(junction_points,junction_switch.inputs['False']);g.put(empty,junction_switch.inputs['True'])
    junction_points=junction_switch.outputs[0]
    has_junctions=g.boolean('AND',has_mesh_junctions,g.boolean('NOT',has_external))
    has_user_roads=g.boolean('OR',has_drawn,has_external)

    idx=g.node('GeometryNodeInputIndex').outputs[0]
    combined=_store(g,combined,'tc_curve_id',idx,'INT',domain='CURVE')

    resample=g.node('GeometryNodeResampleCurve','Road resolution')
    g.put(combined,resample.inputs['Curve'])
    resample.inputs['Mode'].default_value='Length'
    g.put(p['Road Resolution'],resample.inputs['Length'])
    param=g.node('GeometryNodeSplineParameter')
    resampled=_store(g,resample.outputs[0],'tc_u',param.outputs['Length'],'FLOAT')
    # Real junction distance (docs/PLAN.md 0.6.0): distance to the nearest point
    # where 3+ road edges meet, not merely to the drawn curve's own endpoint — the
    # 0.5 proxy used tc_u distance-to-endpoint; same attribute, new algorithm, per
    # the plan's own note that only the source should change, not the interface.
    pos=g.node('GeometryNodeInputPosition').outputs[0]
    prox=g.node('GeometryNodeProximity','Distance to nearest junction',target_element='POINTS')
    g.put(junction_points,prox.inputs['Geometry']);g.put(pos,prox.inputs['Sample Position'])
    junction_dist=g.node('GeometryNodeSwitch','No junction nearby fallback',input_type='FLOAT')
    g.put(prox.outputs['Is Valid'],junction_dist.inputs['Switch'])
    g.put(99999.,junction_dist.inputs['False']);g.put(prox.outputs['Distance'],junction_dist.inputs['True'])
    resampled=_store(g,resampled,'tc_junction_dist',junction_dist.outputs[0],'FLOAT')
    resampled=_store(g,resampled,'tc_markings',p['Road Markings'],'FLOAT')
    return resampled,junction_points,has_junctions,has_user_roads


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
    pos=g.vector(x,g.math('MULTIPLY',z,-1),0)
    setpos=g.node('GeometryNodeSetPosition');g.put(line.outputs['Mesh'],setpos.inputs['Geometry']);g.put(pos,setpos.inputs['Position'])
    tagged=_store(g,setpos.outputs[0],'tc_v',x,'FLOAT')
    tagged=_store(g,tagged,'tc_profile',prof,'INT')
    to_curve=g.node('GeometryNodeMeshToCurve');g.put(tagged,to_curve.inputs['Mesh'])
    cyclic=g.node('GeometryNodeSetSplineCyclic','Close profile loop')
    g.put(to_curve.outputs[0],cyclic.inputs['Curve']);g.put(True,cyclic.inputs['Selection']);g.put(True,cyclic.inputs['Cyclic'])
    return cyclic.outputs[0],half,outer


def build_block_cutter(g,centerline,outer):
    """Convex street volume used only to split residual ground into islands."""
    line=g.node('GeometryNodeMeshLine','Block cutter profile points',mode='OFFSET');g.put(4,line.inputs['Count'])
    idx=g.node('GeometryNodeInputIndex').outputs[0]
    x=_index_switch(g,idx,'FLOAT',[g.math('MULTIPLY',outer,-1),g.math('MULTIPLY',outer,-1),outer,outer],
                    'Block cutter lateral offset')
    z=_index_switch(g,idx,'FLOAT',[-.5,.5,.5,-.5],'Block cutter height')
    positioned=g.node('GeometryNodeSetPosition','Block cutter rectangle')
    g.put(line.outputs['Mesh'],positioned.inputs['Geometry']);g.put(g.vector(x,g.math('MULTIPLY',z,-1),0),positioned.inputs['Position'])
    curve=g.node('GeometryNodeMeshToCurve');g.put(positioned.outputs['Geometry'],curve.inputs['Mesh'])
    cyclic=g.node('GeometryNodeSetSplineCyclic','Close block cutter profile')
    g.put(curve.outputs['Curve'],cyclic.inputs['Curve']);g.put(True,cyclic.inputs['Selection']);g.put(True,cyclic.inputs['Cyclic'])
    swept=g.node('GeometryNodeCurveToMesh','Sweep block cutter')
    g.put(centerline,swept.inputs['Curve']);g.put(cyclic.outputs['Curve'],swept.inputs['Profile Curve'])
    swept.inputs['Fill Caps'].default_value=True
    union=g.node('GeometryNodeMeshBoolean','Union convex block cutter',operation='UNION',solver='EXACT')
    g.put(swept.outputs['Mesh'],union.inputs['Mesh 2'])
    return union.outputs['Mesh']


# ------------------------------------------------------- 4.2 surface + ground
def build_surface(g,p,centerline,junction_points,has_junctions,road_material_fn):
    profile,half,outer=build_profile(g,p)
    swept=g.node('GeometryNodeCurveToMesh','Sweep road cross-section')
    g.put(centerline,swept.inputs['Curve']);g.put(profile,swept.inputs['Profile Curve'])
    swept.inputs['Fill Caps'].default_value=True

    # 0.6: fill each junction with a flat asphalt-height disc, then self-union the
    # whole thing so multiple streets (and their disjoint per-spline sweeps, see
    # find_junctions) join into one continuous surface instead of raw overlapping
    # tube solids (docs/PLAN.md 0.6.0: "路面聯集讓多條街自然接合").
    fillet_radius=g.math('ADD',outer,.5)
    cylinder=g.node('GeometryNodeMeshCylinder','Junction fillet disc')
    g.put(fillet_radius,cylinder.inputs['Radius']);g.put(p['Road Thickness'],cylinder.inputs['Depth'])
    cylinder_geo=_transform(g,cylinder.outputs['Mesh'],translation=g.vector(0,0,g.math('MULTIPLY',p['Road Thickness'],-.5)))
    fillets=g.node('GeometryNodeInstanceOnPoints','Fillets at junctions')
    g.put(junction_points,fillets.inputs['Points']);g.put(cylinder_geo,fillets.inputs['Instance'])
    fillets_realized=g.node('GeometryNodeRealizeInstances');g.put(fillets.outputs['Instances'],fillets_realized.inputs['Geometry'])
    merged_candidate=_self_union(g,_join(g,[swept.outputs[0],fillets_realized.outputs[0]]),'Union streets + junction fillets')
    # No junctions (the common single-street case): skip the extra self-union
    # entirely rather than merge a single already-clean solid with itself —
    # keeps 0.5's behavior and performance unchanged when there's nothing to merge.
    merge_switch=g.node('GeometryNodeSwitch','Skip union when there are no junctions',input_type='GEOMETRY')
    g.put(has_junctions,merge_switch.inputs['Switch'])
    g.put(swept.outputs[0],merge_switch.inputs['False']);g.put(merged_candidate,merge_switch.inputs['True'])
    clipped=merge_switch.outputs[0]
    clip_pos=g.node('GeometryNodeInputPosition').outputs[0]
    clip_ray=g.node('GeometryNodeRaycast','Remove road vertices outside region',data_type='FLOAT')
    g.put(p['Geometry'],clip_ray.inputs['Target Geometry'])
    g.put(g.vmath('ADD',clip_pos,(0,0,100)),clip_ray.inputs['Source Position'])
    clip_ray.inputs['Ray Direction'].default_value=(0,0,-1);clip_ray.inputs['Ray Length'].default_value=200
    clean=g.node('GeometryNodeDeleteGeometry','Strict region mask for road network',domain='POINT',mode='ALL')
    g.put(clipped,clean.inputs['Geometry']);g.put(g.boolean('NOT',clip_ray.outputs['Is Hit']),clean.inputs['Selection'])
    face_pos=g.node('GeometryNodeInputPosition').outputs[0]
    face_ray=g.node('GeometryNodeRaycast','Remove road faces crossing region gaps',data_type='FLOAT')
    g.put(p['Geometry'],face_ray.inputs['Target Geometry'])
    g.put(g.vmath('ADD',face_pos,(0,0,100)),face_ray.inputs['Source Position'])
    face_ray.inputs['Ray Direction'].default_value=(0,0,-1);face_ray.inputs['Ray Length'].default_value=200
    clean_faces=g.node('GeometryNodeDeleteGeometry','Strict face mask for road network',domain='FACE',mode='ALL')
    g.put(clean.outputs['Geometry'],clean_faces.inputs['Geometry'])
    g.put(g.boolean('NOT',face_ray.outputs['Is Hit']),clean_faces.inputs['Selection'])
    clipped=clean_faces.outputs['Geometry']
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
    # 0.6: suppress the sidewalk/curb classification within the fillet radius of a
    # junction ("路口附近抑制人行道") — that area becomes flush asphalt instead.
    prox_junction=g.node('GeometryNodeProximity','Distance to nearest junction (face)',target_element='POINTS')
    g.put(junction_points,prox_junction.inputs['Geometry']);g.put(face_pos,prox_junction.inputs['Sample Position'])
    near_junction=g.boolean('AND',prox_junction.outputs['Is Valid'],g.math('LESS_THAN',prox_junction.outputs['Distance'],fillet_radius))
    is_sidewalk=g.boolean('AND',g.boolean('AND',flat,g.math('GREATER_THAN',prox.outputs['Distance'],g.math('ADD',half,.01))),g.boolean('NOT',near_junction))
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
    block_cutter=build_block_cutter(g,centerline,outer)
    ground=_boolean_op(g,ground,block_cutter,'DIFFERENCE','Non-road ground minus street')
    clean_ground=g.node('GeometryNodeDeleteGeometry','Strict point mask for residual ground',domain='POINT',mode='ALL')
    g.put(ground,clean_ground.inputs['Geometry']);g.put(g.boolean('NOT',clip_ray.outputs['Is Hit']),clean_ground.inputs['Selection'])
    clean_ground_faces=g.node('GeometryNodeDeleteGeometry','Strict face mask for residual ground',domain='FACE',mode='ALL')
    g.put(clean_ground.outputs['Geometry'],clean_ground_faces.inputs['Geometry'])
    g.put(g.boolean('NOT',face_ray.outputs['Is Hit']),clean_ground_faces.inputs['Selection'])
    ground=clean_ground_faces.outputs['Geometry']
    island=g.node('GeometryNodeInputMeshIsland','Residual block islands')
    ground=_store(g,ground,'tc_block_id',island.outputs['Island Index'],'INT',label='Store residual block ID')
    ground=_mat(g,_tag(g,ground,4),material('v05 Bare ground',(.30,.27,.20),roughness=.92))
    results=[_gate(g,road,road_on),_gate(g,paving,sidewalk_on),_gate(g,ground,p['Ground'])]
    return results,half,outer,ground


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


def _open_space_assets(g,p):
    """Small realized lot surfaces for deterministic vacant-site reuse."""
    pad_size=g.vector(g.math('MULTIPLY',p['Frontage'],.9),g.math('MULTIPLY',p['Depth'],.9),.06)
    pad=g.node('GeometryNodeMeshCube','Vacant lot pad');g.put(pad_size,pad.inputs['Size'])
    pad_geo=_transform(g,pad.outputs['Mesh'],translation=(0,0,.03))
    parking=_mat(g,_tag(g,pad_geo,5),material('v07 Parking asphalt',(.055,.06,.058),roughness=.9))

    stripe=g.node('GeometryNodeMeshCube','Parking bay stripe')
    g.put(g.vector(.08,g.math('MULTIPLY',p['Depth'],.72),.025),stripe.inputs['Size'])
    stripe_parts=[]
    for factor in (-.28,0,.28):
        stripe_parts.append(_transform(g,stripe.outputs['Mesh'],translation=g.vector(g.math('MULTIPLY',p['Frontage'],factor),0,.073)))
    markings=_mat(g,_tag(g,_join(g,stripe_parts,'Parking bay markings'),5),
                  material('v07 Parking markings',(.78,.77,.66),roughness=.72))
    parking=_join(g,[parking,markings],'Parking lot asset')

    green=_mat(g,_tag(g,pad_geo,6),material('v07 Pocket green',(.12,.28,.075),roughness=.96))
    border=g.node('GeometryNodeMeshCube','Pocket green planter')
    g.put(g.vector(g.math('MULTIPLY',p['Frontage'],.72),g.math('MULTIPLY',p['Depth'],.72),.16),border.inputs['Size'])
    border_geo=_transform(g,border.outputs['Mesh'],translation=(0,0,.08))
    border_geo=_mat(g,_tag(g,border_geo,6),material('v07 Pocket green soil',(.16,.10,.055),roughness=1.0))
    green=_join(g,[green,border_geo],'Pocket green asset')
    return parking,green


def _place_side(g,p,cols,region_geo,boundary_sel,centerline,dense,junction_points,block_ground,side,bend_buildings,
                block_frontage=False,normal_sites=True,corner_sites=True):
    """Place parcels on either a legacy centerline side or block frontage curves."""
    outer=g.math('ADD',g.math('MULTIPLY',p['Road Width'],.5),p['Sidewalk Width'])
    if block_frontage:
        dense_side=dense
    else:
        normal_attr=_named(g,'tc_normal','FLOAT_VECTOR')
        lateral=_scale(g,normal_attr,g.math('MULTIPLY',outer,float(side)))
        offset_curve=g.node('GeometryNodeSetPosition',f'Offset building line {side:+d}')
        g.put(dense,offset_curve.inputs['Geometry']);g.put(lateral,offset_curve.inputs['Offset'])
        dense_side=offset_curve.outputs[0]
    spline_index=g.node('GeometryNodeInputIndex').outputs[0]
    dense_side=_store(g,dense_side,'tc_site_spline_id',spline_index,'INT',domain='CURVE')
    label='block frontage' if block_frontage else f'side {side:+d}'
    frontage=g.node('GeometryNodeResampleCurve',f'One point per lot on {label}')
    g.put(dense_side,frontage.inputs['Curve']);frontage.inputs['Mode'].default_value='Length'
    g.put(p['Frontage'],frontage.inputs['Length'])
    site_tangent=g.node('GeometryNodeInputTangent').outputs[0]
    stsep=g.node('ShaderNodeSeparateXYZ');g.put(site_tangent,stsep.inputs[0])
    site_normal=_named(g,'tc_normal','FLOAT_VECTOR') if block_frontage else g.vector(g.math('MULTIPLY',stsep.outputs['Y'],-1),stsep.outputs['X'],0)
    param=g.node('GeometryNodeSplineParameter')
    tagged=_store(g,frontage.outputs[0],'tc_site_u',param.outputs['Length'],'FLOAT')
    site_pos=g.node('GeometryNodeInputPosition').outputs[0]
    tagged=_store(g,tagged,'tc_site_pos',site_pos,'FLOAT_VECTOR')
    tagged=_store(g,tagged,'tc_site_tangent',site_tangent,'FLOAT_VECTOR')
    tagged=_store(g,tagged,'tc_site_normal',site_normal,'FLOAT_VECTOR')
    curve_id=_named(g,'tc_curve_id','INT')
    tagged=_store(g,tagged,'tc_site_curve_id',curve_id,'INT')
    # 0.6.3 corner buildings: which end of this row's own spline the site is
    # closer to, 0=start/1=end, needed once past CurveToPoints below (see the
    # handedness comment further down).
    tagged=_store(g,tagged,'tc_site_factor',param.outputs['Factor'],'FLOAT')
    site_index=g.node('GeometryNodeInputIndex').outputs[0]
    previous=g.node('GeometryNodeOffsetPointInCurve','Previous lot tangent')
    g.put(site_index,previous.inputs['Point Index']);previous.inputs['Offset'].default_value=-1
    following=g.node('GeometryNodeOffsetPointInCurve','Next lot tangent')
    g.put(site_index,following.inputs['Point Index']);following.inputs['Offset'].default_value=1
    previous_position=g.node('GeometryNodeSampleIndex','Sample previous lot position',data_type='FLOAT_VECTOR',domain='POINT')
    g.put(tagged,previous_position.inputs['Geometry']);g.put(site_pos,_enabled(previous_position,'Value'))
    g.put(previous.outputs['Point Index'],previous_position.inputs['Index'])
    following_position=g.node('GeometryNodeSampleIndex','Sample next lot position',data_type='FLOAT_VECTOR',domain='POINT')
    g.put(tagged,following_position.inputs['Geometry']);g.put(site_pos,_enabled(following_position,'Value'))
    g.put(following.outputs['Point Index'],following_position.inputs['Index'])
    incoming=g.node('ShaderNodeVectorMath',operation='NORMALIZE')
    g.put(g.vmath('SUBTRACT',site_pos,previous_position.outputs['Value']),incoming.inputs[0])
    outgoing=g.node('ShaderNodeVectorMath',operation='NORMALIZE')
    g.put(g.vmath('SUBTRACT',following_position.outputs['Value'],site_pos),outgoing.inputs[0])
    tangent_dot=_dot(g,incoming.outputs['Vector'],outgoing.outputs['Vector'])
    bent_angle=g.math('MINIMUM',g.math('DIVIDE',g.math('MULTIPLY',p['Frontage'],2),p['Depth']),1.570796)
    # Across the previous/current/next sites the measured turn is about twice
    # the per-lot angle. For rigid assets, Depth * angle/2 <= 0.3 m keeps the
    # estimated rear-edge mismatch within the roadmap's tolerance. Bent assets
    # stay valid until the curve radius approaches one lot depth.
    rigid_angle=g.math('DIVIDE',.6,p['Depth'])
    allowed_angle=g.node('GeometryNodeSwitch','Bent or rigid curvature allowance',input_type='FLOAT')
    g.put(bend_buildings,allowed_angle.inputs['Switch'])
    g.put(rigid_angle,allowed_angle.inputs['False']);g.put(bent_angle,allowed_angle.inputs['True'])
    tight_curve=g.boolean('AND',g.boolean('AND',previous.outputs['Is Valid Offset'],following.outputs['Is Valid Offset']),
                          g.math('LESS_THAN',tangent_dot,g.math('COSINE',allowed_angle.outputs[0])))
    tagged=_store(g,tagged,'tc_site_tight_curve',tight_curve,'BOOLEAN')
    topoints=g.node('GeometryNodeCurveToPoints',f'Building line lots {side:+d}',mode='EVALUATED')
    g.put(tagged,topoints.inputs['Curve'])
    points=topoints.outputs['Points']
    # Read tc_site_tangent/tc_site_normal back as stored named attributes, not the
    # live Input Tangent/Vector Math field, for the alignment below: Curve To
    # Points + the SeparateGeometry filters further down move everything off the
    # curve domain, and a curve-only field like Input Tangent silently evaluates
    # to a degenerate (zero) vector once it's read back past that point — which
    # made every instance's Rotation input collapse to identity (verified via a
    # standalone AlignRotationToVector probe) unless Bend Buildings to Curve was
    # on to paper over it by rebuilding orientation from these same *stored*
    # attributes. Corner buildings (0.6.3) never go through that bend step, so
    # they need this fixed here rather than relying on it being masked.
    stored_normal=_named(g,'tc_site_normal','FLOAT_VECTOR')
    stored_tangent=_named(g,'tc_site_tangent','FLOAT_VECTOR')
    facing=stored_normal if block_frontage else _scale(g,stored_normal,float(side))
    align=g.node('FunctionNodeAlignRotationToVector','Face nearest street',axis='Y')
    g.put(facing,align.inputs['Vector'])
    idx=g.node('GeometryNodeInputIndex').outputs[0]
    site_offset=1000000 if block_frontage else (0 if side>0 else 500000)
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
    own_is_nearest=True if block_frontage else g.math('LESS_THAN',prox_own.outputs['Distance'],g.math('ADD',prox_any.outputs['Distance'],.05))
    zone_position=g.vmath('ADD',pos,_scale(g,facing,g.math('MULTIPLY',p['Depth'],.5)))
    vacancy,_=_sample_region_float(g,region_geo,zone_position,'tc_zone_vacancy',0,'Sample local vacancy')
    vacancy=g.math('MINIMUM',g.math('MAXIMUM',vacancy,0),1)
    local_density=g.math('MULTIPLY',p['Density'],g.math('SUBTRACT',1,vacancy))
    occupied=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,43),local_density)

    # 0.6.3 corner buildings (docs/roadmap.md "轉角雙立面模組"): a site excluded by
    # own_is_nearest (i.e. genuinely closer to a *different* road than its own) is
    # exactly the gap a real junction leaves next to its outer corner. Simplified
    # scope: only fill it in when that other road is close by, roughly
    # perpendicular to this one, and there is an actual detected junction nearby —
    # anything sharper/shallower or without a real junction stays an empty lot,
    # same as before.
    #
    # A resampled row's site right next to a junction sits at (or extremely close
    # to) the crossing road's own centerline — Resample Curve always forces both
    # of a spline's endpoints in, and the exclusion zone this leaves is at most
    # ~outer wide (own_dist stays ~outer while any_dist shrinks to ~arc-length
    # from the junction). That makes the *position* delta to the nearest other
    # point (prox_any) too close to zero to read a reliable direction from, so
    # both "is this really a near-right-angle crossing" and "which side does the
    # crossing road lie on" are answered from *directions* instead of positions:
    # the other road's own tangent, sampled at whichever of its points is
    # nearest, via Sample Nearest + Sample Index rather than Geometry Proximity
    # (which only returns a position/distance, not an attribute at that point).
    fillet_radius=g.math('ADD',outer,.5)
    prox_junction=g.node('GeometryNodeProximity',f'Distance to nearest junction (site {side:+d})',target_element='POINTS')
    g.put(junction_points,prox_junction.inputs['Geometry']);g.put(pos,prox_junction.inputs['Sample Position'])
    near_junction=g.boolean('AND',prox_junction.outputs['Is Valid'],
                             g.math('LESS_THAN',prox_junction.outputs['Distance'],g.math('ADD',fillet_radius,p['Frontage'])))
    close_enough=g.math('LESS_THAN',prox_any.outputs['Distance'],g.math('ADD',outer,p['Frontage']))
    dense_tangent_pts=g.node('GeometryNodeCurveToPoints',f'Tangent-tagged centerline points {side:+d}',mode='EVALUATED')
    g.put(dense,dense_tangent_pts.inputs['Curve'])
    nearest=g.node('GeometryNodeSampleNearest',f'Nearest point on any street {side:+d}',domain='POINT')
    g.put(dense_tangent_pts.outputs['Points'],nearest.inputs['Geometry']);g.put(pos,nearest.inputs['Sample Position'])
    sample_tangent=g.node('GeometryNodeSampleIndex',f'Tangent of nearest street {side:+d}',data_type='FLOAT_VECTOR',domain='POINT')
    g.put(dense_tangent_pts.outputs['Points'],sample_tangent.inputs['Geometry'])
    g.put(_named(g,'tc_tangent','FLOAT_VECTOR'),_enabled(sample_tangent,'Value'))
    g.put(nearest.outputs['Index'],sample_tangent.inputs['Index'])
    other_tangent=next(s for s in sample_tangent.outputs if s.name=='Value' and s.enabled)
    # A curve's tangent direction is whichever way it happens to have been drawn,
    # so only its *line*, not its sign, is meaningful here — abs() keeps the
    # perpendicularity test the same regardless of draw direction.
    near_right_angle=g.math('LESS_THAN',g.math('ABSOLUTE',_dot(g,stored_tangent,other_tangent)),.5)
    corner_candidate=g.boolean('AND',g.boolean('AND',g.boolean('NOT',own_is_nearest),near_junction),
                                g.boolean('AND',near_right_angle,close_enough))
    corner_ok=g.boolean('AND',g.boolean('AND',corner_candidate,inside),g.boolean('AND',occupied,p['Corner Buildings'])) if corner_sites else False
    # Which of the two mirror-image corner assets to use. The asset's own local
    # +X axis, once rotated to align local Y with `facing`, always ends up
    # pointing at rotate(facing, -90 deg) = (facing.y, -facing.x) in the world
    # (checked directly against Align Rotation To Vector's actual output, not
    # assumed) — so wing B (which extends toward local +X on the "R" asset)
    # should be used exactly when the safe-to-extend direction below has a
    # positive dot product with that axis. The safe direction is simply this
    # row's own tangent, forward if this site is nearer the end of its spline
    # (nothing of this row continues past it), backward if nearer the start —
    # either way, away from where this row's own ordinary buildings continue,
    # never into them. tc_site_factor (0=start, 1=end) is read back as a stored
    # attribute for the same domain-conversion reason as tc_site_normal above.
    site_factor=_named(g,'tc_site_factor')
    extend_sign=g.node('GeometryNodeSwitch','Extend toward spline end?',input_type='FLOAT')
    g.put(g.math('GREATER_THAN',site_factor,.5),extend_sign.inputs['Switch'])
    extend_sign.inputs['False'].default_value=-1.;extend_sign.inputs['True'].default_value=1.
    extend_direction=_scale(g,stored_tangent,extend_sign.outputs[0])
    facingsep=g.node('ShaderNodeSeparateXYZ');g.put(facing,facingsep.inputs[0])
    local_x_axis=g.vector(facingsep.outputs['Y'],g.math('MULTIPLY',facingsep.outputs['X'],-1),0)
    wrap_positive=g.math('GREATER_THAN',_dot(g,extend_direction,local_x_axis),0)
    # The excluded slot this corner building is replacing sits right where it
    # was excluded from — inside the crossing road's own paved width, not
    # beside it (own_dist stays ~outer while the crossing road can be
    # arbitrarily close along this row's tangent). extend_direction already
    # points along this row away from where its ordinary buildings continue —
    # the same direction wing B extends into — so sliding the whole L-shaped
    # asset that same way by (crossing road's half-width + this asset's own
    # half-width) clears the crossing pavement instead of straddling it, for
    # both the near-right-angle scope and the default Frontage/Depth ratio the
    # asset's footprint was authored at (see residential.py _CORNER_HALF).
    half_asset_width=g.math('MULTIPLY',p['Frontage'],3.18/6.4)
    corner_push=_scale(g,extend_direction,g.math('ADD',outer,half_asset_width))
    pushed_corner_pos=g.vmath('ADD',pos,corner_push)
    corner_radius=g.math('ADD',p['Depth'],p['Frontage'])
    corner_fits=_inside(g,p,region_geo,boundary_sel,pushed_corner_pos,corner_radius)
    corner_ok=g.boolean('AND',corner_ok,corner_fits)

    tight_curve=_named(g,'tc_site_tight_curve','BOOLEAN')
    curvature_skip=g.boolean('AND',g.boolean('AND',g.boolean('AND',tight_curve,inside),own_is_nearest),
                             g.boolean('NOT',near_junction)) if normal_sites is not False else False
    safe_curve=g.boolean('NOT',tight_curve)
    candidate_normal=g.boolean('AND',g.boolean('AND',own_is_nearest,g.boolean('NOT',near_junction)),safe_curve) if normal_sites is not False else False
    valid_normal=g.boolean('AND',candidate_normal,inside) if normal_sites is not False else False
    if normal_sites is not True and normal_sites is not False:
        curvature_skip=g.boolean('AND',curvature_skip,normal_sites)
        candidate_normal=g.boolean('AND',candidate_normal,normal_sites)
        valid_normal=g.boolean('AND',valid_normal,normal_sites)
    if not block_frontage:candidate_normal=valid_normal

    zone_min,_=_sample_region_float(g,region_geo,zone_position,'tc_zone_min_floors',p['Min Floors'],'Sample local minimum floors')
    zone_max,_=_sample_region_float(g,region_geo,zone_position,'tc_zone_max_floors',p['Max Floors'],'Sample local maximum floors')
    zone_min=g.math('ROUND',g.math('MINIMUM',g.math('MAXIMUM',zone_min,2),7))
    zone_max=g.math('ROUND',g.math('MINIMUM',g.math('MAXIMUM',zone_max,2),7))
    floors=g.random('INT',g.math('MINIMUM',zone_min,zone_max),g.math('MAXIMUM',zone_min,zone_max),p['Seed'],site_id,101)
    facade_mix,_=_sample_region_float(g,region_geo,zone_position,'tc_zone_facade_mix',p['Townhouse Mix'],'Sample local facade mix')
    facade_mix=g.math('MINIMUM',g.math('MAXIMUM',facade_mix,0),1)
    typ=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,307),facade_mix)
    palette=g.random('INT',0,2,p['Seed'],site_id,701)
    variant=g.math('ADD',g.math('MULTIPLY',typ,3),palette)
    # The authored variants have real semantic differences: 0/3/5 contain a
    # recessed ground-floor shop and signage; 0/1/4 use tile/mosaic finishes,
    # while 2/3/5 use aged plaster, oxide tile or ochre plaster. Optional zoning
    # fields select within those sets; with neither field present the original
    # variant remains byte-for-byte equivalent to the pre-zoning choice.
    base_commercial=g.boolean('OR',g.boolean('OR',g.equal(variant,0,.01),g.equal(variant,3,.01)),g.equal(variant,5,.01))
    base_newer=g.boolean('OR',g.boolean('OR',g.equal(variant,0,.01),g.equal(variant,1,.01)),g.equal(variant,4,.01))
    commercial,commercial_exists=_sample_region_float(g,region_geo,zone_position,'tc_zone_commercial',base_commercial,'Sample local commercial mix')
    era,era_exists=_sample_region_float(g,region_geo,zone_position,'tc_zone_era',base_newer,'Sample local facade era')
    commercial=g.math('MINIMUM',g.math('MAXIMUM',commercial,0),1)
    era=g.math('MINIMUM',g.math('MAXIMUM',era,0),1)
    commercial_pick=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,733),commercial)
    newer_pick=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,739),era)
    alternate=g.random('INT',0,1,p['Seed'],site_id,743)
    old_shop=_index_switch(g,alternate,'INT',[3,5],'Old shop variants')
    new_home=_index_switch(g,alternate,'INT',[1,4],'Newer residential variants')
    shop_variant=g.node('GeometryNodeSwitch','Old or newer shopfront',input_type='INT')
    g.put(newer_pick,shop_variant.inputs['Switch']);g.put(old_shop,shop_variant.inputs['False']);shop_variant.inputs['True'].default_value=0
    home_variant=g.node('GeometryNodeSwitch','Old or newer residential facade',input_type='INT')
    g.put(newer_pick,home_variant.inputs['Switch']);home_variant.inputs['False'].default_value=2;g.put(new_home,home_variant.inputs['True'])
    semantic_variant=g.node('GeometryNodeSwitch','Commercial or residential facade',input_type='INT')
    g.put(commercial_pick,semantic_variant.inputs['Switch']);g.put(home_variant.outputs[0],semantic_variant.inputs['False']);g.put(shop_variant.outputs[0],semantic_variant.inputs['True'])
    zoning_active=g.boolean('OR',commercial_exists,era_exists)
    zoned_variant=g.node('GeometryNodeSwitch','Use semantic zoning',input_type='INT')
    g.put(zoning_active,zoned_variant.inputs['Switch']);g.put(variant,zoned_variant.inputs['False']);g.put(semantic_variant.outputs[0],zoned_variant.inputs['True'])
    variant=zoned_variant.outputs[0]
    asset=g.math('ADD',g.math('MULTIPLY',g.math('SUBTRACT',floors,2),6),variant)
    is_shed=g.boolean('OR',g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],site_id,1103),p['Metal Shed Mix']),
                       g.math('GREATER_THAN',p['Metal Shed Mix'],.999999))
    is_shed=g.boolean('AND',is_shed,g.boolean('NOT',corner_ok))
    shed_asset=g.math('ADD',36,g.random('INT',0,5,p['Seed'],site_id,1201))
    select=g.node('GeometryNodeSwitch','Rowhouse or metal workshop',input_type='INT')
    g.put(is_shed,select.inputs['Switch']);g.put(asset,select.inputs['False']);g.put(shed_asset,select.inputs['True'])
    asset=select.outputs[0]
    corner_wrap=g.node('GeometryNodeSwitch','Corner handedness',input_type='INT')
    g.put(wrap_positive,corner_wrap.inputs['Switch']);corner_wrap.inputs['False'].default_value=0;corner_wrap.inputs['True'].default_value=1
    corner_asset=g.math('ADD',42,g.math('ADD',g.math('MULTIPLY',g.math('SUBTRACT',floors,2),2),corner_wrap.outputs[0]))
    corner_select=g.node('GeometryNodeSwitch','Corner or normal asset',input_type='INT')
    g.put(corner_ok,corner_select.inputs['Switch']);g.put(asset,corner_select.inputs['False']);g.put(corner_asset,corner_select.inputs['True'])
    asset=corner_select.outputs[0]
    storeys=g.node('GeometryNodeSwitch','One-storey sheds',input_type='INT')
    g.put(is_shed,storeys.inputs['Switch']);g.put(floors,storeys.inputs['False']);storeys.inputs['True'].default_value=1
    floors=storeys.outputs[0]
    geo=points
    for name,value,dtype in [('tc_parcel_id',site_id,'INT'),('tc_floors',floors,'INT'),('tc_asset',asset,'INT'),
                              ('tc_is_shed',is_shed,'BOOLEAN'),('tc_occupied',occupied,'BOOLEAN'),
                              ('tc_zone_vacancy',vacancy,'FLOAT'),('tc_zone_min_floors',zone_min,'FLOAT'),
                              ('tc_zone_max_floors',zone_max,'FLOAT'),('tc_zone_facade_mix',facade_mix,'FLOAT'),
                              ('tc_zone_commercial',commercial,'FLOAT'),('tc_zone_era',era,'FLOAT')]:
        geo=_store(g,geo,name,value,dtype)
    centered=g.node('GeometryNodeSetPosition',f'Parcel centers behind frontage {side:+d}')
    g.put(geo,centered.inputs['Geometry']);g.put(_scale(g,facing,g.math('MULTIPLY',p['Depth'],.5)),centered.inputs['Offset'])
    centered_geo=centered.outputs['Geometry']
    if not block_frontage:
        center_pos=g.node('GeometryNodeInputPosition').outputs[0]
        nearest_block=g.node('GeometryNodeSampleNearest',f'Nearest residual block {side:+d}',domain='POINT')
        g.put(block_ground,nearest_block.inputs['Geometry']);g.put(center_pos,nearest_block.inputs['Sample Position'])
        sample_block=g.node('GeometryNodeSampleIndex',f'Sample parcel block ID {side:+d}',data_type='INT',domain='POINT')
        g.put(block_ground,sample_block.inputs['Geometry']);g.put(_named(g,'tc_block_id','INT'),_enabled(sample_block,'Value'))
        g.put(nearest_block.outputs['Index'],sample_block.inputs['Index'])
        centered_geo=_store(g,centered_geo,'tc_block_id',sample_block.outputs['Value'],'INT')
    centered_geo=_store(g,centered_geo,'tc_site_valid',valid_normal,'BOOLEAN')
    centered_geo=_store(g,centered_geo,'tc_site_candidate',candidate_normal,'BOOLEAN')
    centered_geo=_store(g,centered_geo,'tc_layer',0,'INT')

    parcel=g.node('GeometryNodeMeshGrid','Parcel face template')
    parcel.inputs['Vertices X'].default_value=2;parcel.inputs['Vertices Y'].default_value=2
    g.put(p['Frontage'],parcel.inputs['Size X']);g.put(p['Depth'],parcel.inputs['Size Y'])
    candidate_sites=g.node('GeometryNodeSeparateGeometry',f'Candidate parcel sites {side:+d}',domain='POINT')
    g.put(centered_geo,candidate_sites.inputs['Geometry']);g.put(_named(g,'tc_site_candidate','BOOLEAN'),candidate_sites.inputs['Selection'])
    parcel_instances=g.node('GeometryNodeInstanceOnPoints',f'Parcel faces {side:+d}')
    g.put(candidate_sites.outputs['Selection'],parcel_instances.inputs['Points']);g.put(parcel.outputs['Mesh'],parcel_instances.inputs['Instance'])
    g.put(align.outputs['Rotation'],parcel_instances.inputs['Rotation'])
    parcels=g.node('GeometryNodeRealizeInstances',f'Realize parcel faces {side:+d}')
    g.put(parcel_instances.outputs['Instances'],parcels.inputs['Geometry'])
    parcel_points=g.node('GeometryNodeMeshToPoints',f'Parcel face centers {side:+d}',mode='FACES')
    g.put(parcels.outputs['Geometry'],parcel_points.inputs['Mesh'])
    g.put(_named(g,'tc_site_valid','BOOLEAN'),parcel_points.inputs['Selection'])
    occupied_points=g.node('GeometryNodeSeparateGeometry',f'Occupied parcel faces {side:+d}',domain='POINT')
    g.put(parcel_points.outputs['Points'],occupied_points.inputs['Geometry'])
    g.put(_named(g,'tc_occupied','BOOLEAN'),occupied_points.inputs['Selection'])
    normal_pts=occupied_points.outputs['Selection']
    vacant_pts=occupied_points.outputs['Inverted']

    guide_faces=parcels.outputs['Geometry']
    if block_frontage:
        guide_template=g.node('GeometryNodeMeshGrid','Subdivided parcel guide template')
        guide_template.inputs['Vertices X'].default_value=9;guide_template.inputs['Vertices Y'].default_value=9
        g.put(p['Frontage'],guide_template.inputs['Size X']);g.put(p['Depth'],guide_template.inputs['Size Y'])
        guide_instances=g.node('GeometryNodeInstanceOnPoints','Parcel guide grids on block frontages')
        g.put(candidate_sites.outputs['Selection'],guide_instances.inputs['Points'])
        g.put(guide_template.outputs['Mesh'],guide_instances.inputs['Instance']);g.put(align.outputs['Rotation'],guide_instances.inputs['Rotation'])
        guide_realized=g.node('GeometryNodeRealizeInstances','Realize subdivided parcel guides')
        g.put(guide_instances.outputs['Instances'],guide_realized.inputs['Geometry'])
        guide_position=g.node('GeometryNodeInputPosition').outputs[0]
        block_distance=g.node('GeometryNodeProximity','Clip parcel guide cells to block surface',target_element='FACES')
        g.put(block_ground,block_distance.inputs['Geometry']);g.put(guide_position,block_distance.inputs['Sample Position'])
        nearest_parcel=g.node('GeometryNodeSampleNearest','Nearest parcel owner for guide cells',domain='POINT')
        g.put(candidate_sites.outputs['Selection'],nearest_parcel.inputs['Geometry'])
        g.put(guide_position,nearest_parcel.inputs['Sample Position'])
        parcel_owner=g.node('GeometryNodeSampleIndex','Assign guide cells to nearest parcel',data_type='INT',domain='POINT')
        g.put(candidate_sites.outputs['Selection'],parcel_owner.inputs['Geometry'])
        g.put(_named(g,'tc_parcel_id','INT'),_enabled(parcel_owner,'Value'))
        g.put(nearest_parcel.outputs['Index'],parcel_owner.inputs['Index'])
        wrong_owner=g.boolean('NOT',g.equal(_named(g,'tc_parcel_id','INT'),parcel_owner.outputs['Value'],.01))
        clipped_cells=g.node('GeometryNodeDeleteGeometry','Remove parcel guide cells outside block',domain='FACE',mode='ALL')
        g.put(guide_realized.outputs['Geometry'],clipped_cells.inputs['Geometry'])
        outside_block=g.math('GREATER_THAN',block_distance.outputs['Distance'],.02)
        g.put(g.boolean('OR',outside_block,wrong_owner),clipped_cells.inputs['Selection'])
        guide_faces=clipped_cells.outputs['Geometry']
    guide=g.node('GeometryNodeSetPosition',f'Raise parcel guides {side:+d}')
    g.put(guide_faces,guide.inputs['Geometry'])
    guide.inputs['Offset'].default_value=(0,0,.025)
    guide_geo=_mat(g,_tag(g,guide.outputs['Geometry'],7),material('v07 Parcel guides',(.08,.32,.48),roughness=.7))
    guide_geo=_gate(g,guide_geo,p['Parcel Guides'])

    # Corner sites keep their dedicated rigid path; ordinary buildings and open
    # spaces now originate from explicit parcel face centers.
    # Corner sites get their own unbent selection — own_is_nearest is false for
    # every corner_ok point, so the two selections can never overlap.
    meshpts_corner=g.node('GeometryNodeSeparateGeometry','Chosen corner lots',domain='POINT')
    g.put(geo,meshpts_corner.inputs['Geometry']);g.put(corner_ok,meshpts_corner.inputs['Selection'])
    # A junction vertex splits the road into separate splines, and Resample Curve
    # always forces both of a spline's endpoints in regardless of remainder — so
    # two different splines that both end exactly at the same junction each force
    # a resampled point there too, landing this row's offset at the exact same
    # world position twice. Collapse those coincident corner candidates into one
    # before instancing so the same corner building doesn't get stacked on itself.
    corner_vertices=g.node('GeometryNodePointsToVertices','Corner sites to mergeable vertices')
    g.put(meshpts_corner.outputs['Selection'],corner_vertices.inputs['Points'])
    corner_pts=g.node('GeometryNodeMergeByDistance','Deduplicate coincident corner sites')
    g.put(corner_vertices.outputs['Mesh'],corner_pts.inputs['Geometry']);corner_pts.inputs['Distance'].default_value=1.0
    pushed=g.node('GeometryNodeSetPosition','Slide corner site clear of the crossing road')
    g.put(corner_pts.outputs[0],pushed.inputs['Geometry']);g.put(corner_push,pushed.inputs['Offset'])
    corner_pts=pushed

    named=g.node('GeometryNodeInputNamedAttribute',data_type='INT');named.inputs['Name'].default_value='tc_asset'
    shed_attr=g.node('GeometryNodeInputNamedAttribute',data_type='BOOLEAN');shed_attr.inputs['Name'].default_value='tc_is_shed'
    parcel_attr=g.node('GeometryNodeInputNamedAttribute',data_type='INT');parcel_attr.inputs['Name'].default_value='tc_parcel_id'
    addon_probability=g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],parcel_attr.outputs['Attribute'],1601),p['Rooftop Addition Mix'])
    scale=g.vector(g.math('DIVIDE',p['Frontage'],6.4),g.math('DIVIDE',p['Depth'],12),1)
    rotation=align.outputs['Rotation']

    def instance_kit(points_selection,label):
        pieces=[]
        for key,toggle in [('Buildings','Buildings'),('Signs','Signs'),('Roofs','Rooftops'),('Street life','Street Life'),('Additions','Rooftops')]:
            collection=g.node('GeometryNodeCollectionInfo',key+label)
            collection.inputs['Collection'].default_value=cols[key]
            collection.inputs['Separate Children'].default_value=True
            collection.inputs['Reset Children'].default_value=True
            instance=g.node('GeometryNodeInstanceOnPoints',key+label)
            g.put(points_selection,instance.inputs['Points'])
            g.put(collection.outputs['Instances'],instance.inputs['Instance'])
            instance.inputs['Pick Instance'].default_value=True
            g.put(named.outputs['Attribute'],instance.inputs['Instance Index'])
            g.put(rotation,instance.inputs['Rotation']);g.put(scale,instance.inputs['Scale'])
            selection=p[toggle] if key=='Buildings' else g.boolean('AND',p[toggle],p['Buildings'])
            if key=='Additions':selection=g.boolean('AND',selection,g.boolean('AND',addon_probability,g.boolean('NOT',shed_attr.outputs['Attribute'])))
            g.put(selection,instance.inputs['Selection'])
            pieces.append(instance.outputs['Instances'])
        return pieces

    normal_pieces=instance_kit(normal_pts,f' on parcel faces {side:+d}')
    # Corner buildings are a fixed L-shape baked around the junction's outer
    # corner; bending them along the row (which only makes sense for a single
    # frontage-wide instance) would tear the sideways wing away from its anchor,
    # so they stay rigid regardless of the Bend Buildings to Curve toggle.
    corner_pieces=instance_kit(corner_pts.outputs[0],f' corner {side:+d}')
    parking_asset,green_asset=_open_space_assets(g,p)
    parking_pick=g.boolean('OR',g.math('LESS_THAN',g.random('FLOAT',0,1,p['Seed'],parcel_attr.outputs['Attribute'],3201),p['Parking Mix']),
                           g.math('GREATER_THAN',p['Parking Mix'],.999999))
    open_on=g.boolean('AND',p['Ground'],p['Open Spaces'])
    parking_selection=g.boolean('AND',parking_pick,open_on)
    green_selection=g.boolean('AND',g.boolean('NOT',parking_pick),open_on)
    open_spaces=[_instance(g,vacant_pts,parking_asset,parking_selection,align.outputs['Rotation'],label=f'Parking lots {side:+d}',realize=True),
                 _instance(g,vacant_pts,green_asset,green_selection,align.outputs['Rotation'],label=f'Pocket greens {side:+d}',realize=True)]
    skipped=g.node('GeometryNodeSeparateGeometry',f'Unsafe curvature sites {side:+d}',domain='POINT')
    g.put(geo,skipped.inputs['Geometry']);g.put(curvature_skip,skipped.inputs['Selection'])
    has_skipped=g.math('GREATER_THAN',_point_count(g,skipped.outputs['Selection']),0)
    return _bend(g,dense_side,normal_pieces,side,bend_buildings,block_frontage)+corner_pieces+open_spaces+[guide_geo],has_skipped


def _bend(g,frontage_curve,pieces,side,bend_buildings,block_frontage=False):
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
        site_spline_id=_named(g,'tc_site_spline_id','INT')
        offset=g.vmath('SUBTRACT',vertex_pos,site_pos)
        if block_frontage:
            tangent_parts=g.node('ShaderNodeSeparateXYZ');g.put(site_tangent,tangent_parts.inputs[0])
            curve_left=g.vector(g.math('MULTIPLY',tangent_parts.outputs['Y'],-1),tangent_parts.outputs['X'],0)
            local_x=_dot(g,offset,site_tangent)
            local_y=_dot(g,offset,curve_left)
        else:
            local_x=g.math('MULTIPLY',_dot(g,offset,site_tangent),float(side))
            local_y=_dot(g,offset,site_normal)
        new_u=g.math('ADD',site_u,local_x)
        sample=g.node('GeometryNodeSampleCurve','Bend along building line',mode='LENGTH')
        g.put(frontage_curve,sample.inputs['Curves']);g.put(new_u,_enabled(sample,'Length'))
        g.put(site_spline_id,sample.inputs['Curve Index'])
        tsep=g.node('ShaderNodeSeparateXYZ');g.put(sample.outputs['Tangent'],tsep.inputs[0])
        curve_normal=g.vector(g.math('MULTIPLY',tsep.outputs['Y'],-1),tsep.outputs['X'],0)
        new_pos=g.vmath('ADD',sample.outputs['Position'],_scale(g,curve_normal,local_y))
        zsep=g.node('ShaderNodeSeparateXYZ');g.put(vertex_pos,zsep.inputs[0])
        final_pos=g.vmath('ADD',new_pos,g.vector(0,0,zsep.outputs['Z']))
        moved=g.node('GeometryNodeSetPosition','Bent world position')
        g.put(realized.outputs[0],moved.inputs['Geometry']);g.put(final_pos,moved.inputs['Position'])
        rigid_switch=g.node('GeometryNodeSwitch','Bend toggle',input_type='GEOMETRY')
        g.put(bend_buildings,rigid_switch.inputs['Switch'])
        g.put(instances,rigid_switch.inputs['False']);g.put(moved.outputs[0],rigid_switch.inputs['True'])
        bent.append(rigid_switch.outputs[0])
    return bent


def build_block_frontages(g,p,block_ground,centerline_points):
    """Extract the street-facing top boundary of residual block meshes as curves."""
    normal=g.node('GeometryNodeInputNormal','Residual block top face normal')
    normal_z=g.node('ShaderNodeSeparateXYZ');g.put(normal.outputs[0],normal_z.inputs[0])
    top_faces=g.node('GeometryNodeSeparateGeometry','Residual block top faces',domain='FACE')
    g.put(block_ground,top_faces.inputs['Geometry']);g.put(g.math('GREATER_THAN',normal_z.outputs['Z'],.9),top_faces.inputs['Selection'])
    edge_neighbors=g.node('GeometryNodeInputMeshEdgeNeighbors','Residual block boundary neighbors')
    position=g.node('GeometryNodeInputPosition').outputs[0]
    nearest_street=g.node('GeometryNodeProximity','Block edge distance to street',target_element='POINTS')
    g.put(centerline_points,nearest_street.inputs['Geometry']);g.put(position,nearest_street.inputs['Sample Position'])
    outer=g.math('ADD',g.math('MULTIPLY',p['Road Width'],.5),p['Sidewalk Width'])
    is_boundary=g.equal(edge_neighbors.outputs['Face Count'],1)
    beside_street=g.boolean(
        'AND',g.math('GREATER_THAN',nearest_street.outputs['Distance'],g.math('SUBTRACT',outer,.5)),
        g.math('LESS_THAN',nearest_street.outputs['Distance'],g.math('ADD',outer,.5)))
    street_edge=g.boolean('AND',is_boundary,beside_street)
    curves=g.node('GeometryNodeMeshToCurve','Block boundaries to frontage curves')
    g.put(top_faces.outputs['Selection'],curves.inputs['Mesh']);g.put(street_edge,curves.inputs['Selection'])
    dense=g.node('GeometryNodeResampleCurve','Dense block frontage curves')
    g.put(curves.outputs['Curve'],dense.inputs['Curve']);dense.inputs['Mode'].default_value='Length';g.put(.25,dense.inputs['Length'])
    curve_position=g.node('GeometryNodeInputPosition').outputs[0]
    nearest=g.node('GeometryNodeProximity','Nearest street from block frontage',target_element='POINTS')
    g.put(centerline_points,nearest.inputs['Geometry']);g.put(curve_position,nearest.inputs['Sample Position'])
    tangent=g.node('GeometryNodeInputTangent').outputs[0]
    tangent_parts=g.node('ShaderNodeSeparateXYZ');g.put(tangent,tangent_parts.inputs[0])
    left=g.vector(g.math('MULTIPLY',tangent_parts.outputs['Y'],-1),tangent_parts.outputs['X'],0)
    away=g.vmath('SUBTRACT',curve_position,nearest.outputs['Position'])
    inward=g.node('GeometryNodeSwitch','Choose block-facing frontage normal',input_type='VECTOR')
    g.put(g.math('GREATER_THAN',_dot(g,left,away),0),inward.inputs['Switch'])
    g.put(_scale(g,left,-1),inward.inputs['False']);g.put(left,inward.inputs['True'])
    frontage=_store(g,dense.outputs['Curve'],'tc_normal',inward.outputs[0],'FLOAT_VECTOR')
    top_size=g.node('GeometryNodeAttributeDomainSize','Residual block top face count',component='MESH')
    g.put(top_faces.outputs['Selection'],top_size.inputs['Geometry'])
    return frontage,g.math('GREATER_THAN',top_size.outputs['Face Count'],0)


def build_sites(g,p,cols,region_geo,boundary_sel,centerline,junction_points,block_ground,bend_buildings):
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
    g.put(dense_geo,centerline_pts.inputs['Curve'])
    block_frontages,has_block_tops=build_block_frontages(g,p,block_ground,centerline_pts.outputs['Points'])
    pieces,curvature_warning=_place_side(
        g,p,cols,region_geo,boundary_sel,centerline_pts.outputs['Points'],block_frontages,junction_points,
        block_ground,1,bend_buildings,block_frontage=True,normal_sites=has_block_tops,corner_sites=False)
    use_legacy_rows=g.boolean('NOT',has_block_tops)
    for side in (1,-1):
        corner_pieces,side_warning=_place_side(
            g,p,cols,region_geo,boundary_sel,centerline_pts.outputs['Points'],dense_geo,junction_points,
            block_ground,side,bend_buildings,normal_sites=use_legacy_rows)
        pieces+=corner_pieces
        curvature_warning=g.boolean('OR',curvature_warning,side_warning)
    return pieces,curvature_warning


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
def build_wires(g,p,region_geo,boundary_sel,centerline,junction_points):
    results=[]
    for side in (1,-1):
        results+=_wires_side(g,p,region_geo,boundary_sel,centerline,side,junction_points)
    return results


def _wires_side(g,p,region_geo,boundary_sel,centerline,side,junction_points):
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
    boundary_curve=g.node('GeometryNodeMeshToCurve',f'Wire boundary guards {side:+d}')
    g.put(boundary_sel,boundary_curve.inputs['Mesh'])
    guard_profile=g.node('GeometryNodeCurvePrimitiveCircle',mode='RADIUS')
    guard_profile.inputs['Resolution'].default_value=8;guard_profile.inputs['Radius'].default_value=.45
    guard=g.node('GeometryNodeCurveToMesh',f'Inflated wire boundary guards {side:+d}')
    g.put(boundary_curve.outputs[0],guard.inputs['Curve']);g.put(guard_profile.outputs[0],guard.inputs['Profile Curve'])
    chord_direction=g.node('ShaderNodeVectorMath',operation='NORMALIZE');g.put(chord,chord_direction.inputs[0])
    boundary_ray=g.node('GeometryNodeRaycast',f'Reject span crossing boundary {side:+d}',data_type='FLOAT')
    g.put(guard.outputs['Mesh'],boundary_ray.inputs['Target Geometry']);g.put(pos_field,boundary_ray.inputs['Source Position'])
    g.put(chord_direction.outputs['Vector'],boundary_ray.inputs['Ray Direction']);g.put(chord_length.outputs['Value'],boundary_ray.inputs['Ray Length'])
    connected=g.boolean('AND',connected,g.boolean('NOT',boundary_ray.outputs['Is Hit']))
    # 0.6: interrupt any span whose midpoint falls within a junction's fillet
    # radius (docs/PLAN.md 0.6.0 "架空線在路口中斷"), reusing build_surface's
    # own fillet_radius formula (outer + .5).
    midpoint=_scale(g,g.vmath('ADD',pos_field,sample_pos.outputs['Value']),.5)
    prox_junction=g.node('GeometryNodeProximity',f'Span clear of junction {side:+d}',target_element='POINTS')
    g.put(junction_points,prox_junction.inputs['Geometry']);g.put(midpoint,prox_junction.inputs['Sample Position'])
    fillet_radius=g.math('ADD',outer,.5)
    crosses_junction=g.boolean('AND',prox_junction.outputs['Is Valid'],g.math('LESS_THAN',prox_junction.outputs['Distance'],fillet_radius))
    connected=g.boolean('AND',connected,g.boolean('NOT',crosses_junction))
    spanpts=g.node('GeometryNodeCurveToPoints',f'Wire span anchors {side:+d}',mode='EVALUATED')
    tagged=_store(g,moved.outputs[0],'tc_chord',chord,'FLOAT_VECTOR')
    tagged=_store(g,tagged,'tc_chord_len',chord_length.outputs['Value'],'FLOAT')
    tagged=_store(g,tagged,'tc_connected',connected,'BOOLEAN')
    g.put(tagged,spanpts.inputs['Curve'])
    chord_attr=_named(g,'tc_chord','FLOAT_VECTOR');chord_len_attr=_named(g,'tc_chord_len')
    connected_attr=_named(g,'tc_connected','BOOLEAN')
    align=g.node('FunctionNodeAlignRotationToVector',f'Span follows chord {side:+d}',axis='X')
    g.put(chord_attr,align.inputs['Vector'])

    line=g.node('GeometryNodeCurvePrimitiveLine',mode='POINTS');g.put((1.0,0,0),line.inputs['End'])
    resample=g.node('GeometryNodeResampleCurve','Wire sag profile');g.put(line.outputs[0],resample.inputs['Curve']);resample.inputs['Count'].default_value=33
    factor=g.node('GeometryNodeSplineParameter').outputs['Factor']
    sag=g.math('MINIMUM',p['Cable Sag'],g.math('MULTIPLY',p['Pole Height'],.12))
    one_minus=g.math('SUBTRACT',1,factor)
    shape=g.math('MULTIPLY',g.math('MULTIPLY',factor,factor),g.math('MULTIPLY',one_minus,one_minus))
    drop=g.math('MULTIPLY',g.math('MULTIPLY',shape,sag),-16)
    bend=g.node('GeometryNodeSetPosition','Smooth cable sag (curved)')
    g.put(resample.outputs[0],bend.inputs['Geometry']);g.put(g.vector(0,0,drop),bend.inputs['Offset'])
    circle=g.node('GeometryNodeCurvePrimitiveCircle',mode='RADIUS');circle.inputs['Resolution'].default_value=8;circle.inputs['Radius'].default_value=.019
    tube=g.node('GeometryNodeCurveToMesh');g.put(bend.outputs[0],tube.inputs['Curve']);g.put(circle.outputs[0],tube.inputs['Profile Curve']);tube.inputs['Fill Caps'].default_value=True
    wires=[]
    for y,z in [(-.38,8.66),(0,8.66),(.38,8.66),(-.27,6.18),(-.12,6.18)]:
        wires.append(_transform(g,tube.outputs[0],translation=g.vector(0,y,g.math('ADD',height,g.math('MULTIPLY',p['Pole Height'],z/9)))))
    wire_geo=_mat(g,_tag(g,_join(g,wires),3),material('v04 Cable rubber',(.015,.018,.019),roughness=.57))
    wire_on=g.boolean('AND',p['Utility Poles'],p['Overhead Wires'])
    scale=g.vector(chord_len_attr,1,1)
    span_id=g.math('ADD',idxnode,0 if side>0 else 1000000)
    span_points=_store(g,spanpts.outputs['Points'],'tc_span_id',span_id,'INT')
    return [_instance(g,span_points,wire_geo,g.boolean('AND',wire_on,connected_attr),
                       align.outputs['Rotation'],scale,label=f'Continuous overhead spans {side:+d}',realize=True)]


# ------------------------------------------------------------------ orchestrator
def curve_district(g,p,cols,region_geo,road_mesh_geo,grid_road_mesh_geo,boundary_sel):
    """Build every district from one selected road-centerline source."""
    centerline,junction_points,has_junctions,has_user_roads=build_centerline(
        g,p,region_geo,road_mesh_geo,grid_road_mesh_geo,boundary_sel)
    bend_buildings=g.boolean('AND',p['Bend Buildings to Curve'],has_user_roads)
    empty=g.node('GeometryNodeJoinGeometry','No internal-grid surface fillets').outputs[0]
    surface_junctions=g.node('GeometryNodeSwitch','User-road surface junctions',input_type='GEOMETRY')
    g.put(has_user_roads,surface_junctions.inputs['Switch'])
    g.put(empty,surface_junctions.inputs['False']);g.put(junction_points,surface_junctions.inputs['True'])
    surface_has_junctions=g.boolean('AND',has_junctions,has_user_roads)
    surface,half,outer,block_ground=build_surface(g,p,centerline,surface_junctions.outputs[0],surface_has_junctions,curve_road_material)
    sites,curvature_warning=build_sites(g,p,cols,region_geo,boundary_sel,centerline,junction_points,block_ground,bend_buildings)
    furniture=build_furniture(g,p,region_geo,boundary_sel,centerline)
    wires=build_wires(g,p,region_geo,boundary_sel,centerline,junction_points)
    warned_surface=[_store(g,geometry,'tc_curvature_warning',curvature_warning,'BOOLEAN',label='Store curvature warning')
                    for geometry in surface]
    return _join(g,warned_surface+sites+furniture+wires,'Unified district layers')
