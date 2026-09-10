"""Original, texture-free Taiwanese streetscape kit. Dimensions are metres.

Each collection has identically sorted children: (floors - 2) * 6 + variant.
Indices 36–41 are independent, one-storey corrugated metal sheds.
The kit is built once; all district evaluation is done by Geometry Nodes.
"""
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector, Matrix

PREFIX = "TCity • "
KIT_VERSION = 4
# Indices 0-35 are the 6-floor-count x 6-variant rowhouses, 36-41 the metal sheds
# (both unchanged from KIT_VERSION 3); 42-53 are the 0.6.3 corner buildings —
# 6 floor counts x 2 mirror-image handedness, each combining two existing
# single-frontage facades around a rounded tile corner pier (docs/roadmap.md
# "轉角雙立面模組"). KIT_OBJECT_COUNT reflects the new total per collection.
KIT_OBJECT_COUNT = 54
COLLECTION_NAMES = {k: PREFIX + k + ' v0.3' for k in ("Buildings", "Signs", "Roofs", "Street life", "Additions")}


def material(name, color, metallic=0, roughness=.65, tile=False):
    name = PREFIX + name
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    n, links = m.node_tree.nodes, m.node_tree.links
    bs = n.get("Principled BSDF")
    bs.inputs['Base Color'].default_value = (*color, 1)
    bs.inputs['Metallic'].default_value = metallic
    bs.inputs['Roughness'].default_value = roughness
    if tile:
        coord = n.new('ShaderNodeTexCoord')
        sep = n.new('ShaderNodeSeparateXYZ')
        links.new(coord.outputs['Object'], sep.inputs[0])
        add = n.new('ShaderNodeMath'); add.operation = 'ADD'
        links.new(sep.outputs['X'], add.inputs[0]); links.new(sep.outputs['Y'], add.inputs[1])
        vec = n.new('ShaderNodeCombineXYZ')
        links.new(add.outputs[0], vec.inputs['X']); links.new(sep.outputs['Z'], vec.inputs['Y'])
        brick = n.new('ShaderNodeTexBrick'); brick.offset = 0
        links.new(vec.outputs[0], brick.inputs['Vector'])
        brick.inputs['Scale'].default_value = 1
        brick.inputs['Brick Width'].default_value = .24
        brick.inputs['Row Height'].default_value = .12
        brick.inputs['Mortar Size'].default_value = .008
        brick.inputs['Mortar Smooth'].default_value = .003
        brick.inputs['Color1'].default_value = (*color, 1)
        brick.inputs['Color2'].default_value = (*(v*.78 for v in color), 1)
        brick.inputs['Mortar'].default_value = (.15, .14, .12, 1)
        noise = n.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = 1.8
        noise.inputs['Detail'].default_value = 3
        links.new(coord.outputs['Object'], noise.inputs['Vector'])
        mix = n.new('ShaderNodeMixRGB'); mix.blend_type = 'MULTIPLY'
        mix.inputs[0].default_value = .28
        links.new(brick.outputs['Color'], mix.inputs[1]); links.new(noise.outputs['Fac'], mix.inputs[2])
        links.new(mix.outputs[0], bs.inputs['Base Color'])
        bump = n.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = .22
        bump.inputs['Distance'].default_value = .022
        links.new(brick.outputs['Fac'], bump.inputs['Height']); links.new(bump.outputs[0], bs.inputs['Normal'])
    return m


class MeshBuilder:
    """Append primitives without creating thousands of scene objects."""
    def __init__(self):
        self.verts, self.faces, self.indices, self.materials = [], [], [], []
        self.smooth = []

    def add(self, verts, faces, mat, smooth=False):
        if mat not in self.materials:
            self.materials.append(mat)
        idx, offset = self.materials.index(mat), len(self.verts)
        self.verts.extend(verts)
        self.faces.extend(tuple(offset + i for i in f) for f in faces)
        self.indices.extend([idx] * len(faces))
        self.smooth.extend(smooth if isinstance(smooth,list) else [smooth]*len(faces))

    def transform(self, matrix):
        """Apply a rigid mathutils Matrix to every vertex in place. Only ever used
        with pure rotation/translation (no mirroring), so winding stays correct."""
        self.verts = [tuple(matrix @ Vector(v)) for v in self.verts]

    def extend(self, other):
        """Merge another builder's geometry into this one (0.6.3 corner buildings:
        combining two independently authored facades into one asset)."""
        offset = len(self.verts)
        remap = []
        for m in other.materials:
            if m not in self.materials:
                self.materials.append(m)
            remap.append(self.materials.index(m))
        self.verts.extend(other.verts)
        self.faces.extend(tuple(offset + i for i in f) for f in other.faces)
        self.indices.extend(remap[i] for i in other.indices)
        self.smooth.extend(other.smooth)

    def box(self, center, size, mat, rotation=None):
        verts = []
        for x, y, z in ((-1,-1,-1),(-1,-1,1),(-1,1,-1),(-1,1,1),
                        (1,-1,-1),(1,-1,1),(1,1,-1),(1,1,1)):
            v = Vector((x*size[0]/2, y*size[1]/2, z*size[2]/2))
            if rotation is not None: v = rotation @ v
            verts.append(tuple(v + Vector(center)))
        self.add(verts, [(0,4,6,2),(1,3,7,5),(0,1,5,4),
                         (2,6,7,3),(0,2,3,1),(4,5,7,6)], mat)

    def cylinder(self, center, radius, height, mat, segments=16, axis='Z'):
        rot = Matrix.Rotation(math.pi/2, 3, 'Y') if axis == 'X' else Matrix.Identity(3)
        verts = [tuple(Vector(center) + rot @ Vector((radius*math.cos(i*2*math.pi/segments),
                  radius*math.sin(i*2*math.pi/segments), z)))
                 for z in (-height/2, height/2) for i in range(segments)]
        faces = [tuple(reversed(range(segments))), tuple(range(segments, segments*2))]
        faces += [(i,(i+1)%segments,(i+1)%segments+segments,i+segments) for i in range(segments)]
        self.add(verts, faces, mat, [False,False]+[True]*segments)

    def beam(self, a, b, radius, mat):
        d = Vector(b)-Vector(a)
        self.box((Vector(a)+Vector(b))/2, (radius,radius,d.length), mat,
                 d.to_track_quat('Z', 'Y').to_matrix())

    def text(self, body, center, size, mat, font, rotation=(math.pi/2,0,0)):
        if font is None: return
        from mathutils import Euler
        c = bpy.data.curves.new('_tc_text', 'FONT')
        c.body = body; c.font = font; c.size = size
        c.align_x = 'CENTER'; c.align_y = 'CENTER'
        c.resolution_u = 3
        o = bpy.data.objects.new('_tc_text', c)
        bpy.context.scene.collection.objects.link(o)
        dg = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        rot = Euler(rotation).to_matrix()
        self.add([tuple(rot @ v.co + Vector(center)) for v in mesh.vertices],
                 [tuple(p.vertices) for p in mesh.polygons], mat)
        bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.curves.remove(c); bpy.data.meshes.remove(mesh)

    def object(self, name, collection):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.verts, [], self.faces); mesh.update()
        for m in self.materials: mesh.materials.append(m)
        for p, index, smooth in zip(mesh.polygons, self.indices, self.smooth):
            p.material_index = index; p.use_smooth = smooth
        o = bpy.data.objects.new(name, mesh); collection.objects.link(o)
        return o


def find_font():
    candidates = [Path(__file__).parent / 'fonts' / 'TCitySigns.otf',
                  Path('/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc'),
                  Path('/System/Library/Fonts/PingFang.ttc'),
                  Path('C:/Windows/Fonts/msjh.ttc')]
    for p in candidates:
        if p.exists():
            try: return bpy.data.fonts.load(str(p), check_existing=True)
            except RuntimeError: pass
    return None


def ensure_assets():
    existing = {k: bpy.data.collections.get(v) for k,v in COLLECTION_NAMES.items()}
    if all(c is not None and c.get('tc_kit_version') == KIT_VERSION and len(c.objects) == KIT_OBJECT_COUNT
           for c in existing.values()):
        return existing
    cols = {k: bpy.data.collections.new(v) for k,v in COLLECTION_NAMES.items()}
    for c in cols.values():
        c.use_fake_user = True
        c['tc_kit_version'] = KIT_VERSION
    # Collections are intentionally not linked to the scene. Collection Info still
    # evaluates them, but source buildings never appear beside the generated city.
    mats = {
        'concrete': material('Warm concrete', (.44,.42,.36)),
        'trim': material('Ivory stone', (.72,.70,.62)),
        'dark': material('Painted steel', (.065,.085,.083), .35),
        'glass': material('Blue grey windows', (.095,.20,.23), .38, .23),
        'warmglass': material('Curtained windows', (.34,.29,.20), .15, .36),
        'metal': material('Stainless steel', (.56,.61,.62), .82, .27),
        'rust': material('Oxidized metal', (.28,.105,.055), .45),
        'red': material('Oxblood signs', (.56,.045,.03)),
        'green': material('Jade signs', (.025,.29,.21)),
        'blue': material('Petrol blue metal', (.035,.19,.25), .3),
        'yellow': material('Golden shop signs', (.88,.53,.08)),
        'white': material('Warm white lettering', (.92,.87,.69)),
        'leaf': material('Foliage', (.095,.23,.075)),
        'pot': material('Terracotta pots', (.38,.14,.075)),
        'tire': material('Rubber', (.018,.022,.022)),
        'paving': material('Arcade paving', (.38,.37,.33)),
        'brick': material('Red tile', (.43,.19,.12), tile=True),
    }
    font = find_font()
    from .residential import build_residential, build_corner
    build_residential(cols,mats,font)
    from .sheds import build_sheds
    build_sheds(cols,mats,font)
    build_corner(cols,mats,font)
    return cols
