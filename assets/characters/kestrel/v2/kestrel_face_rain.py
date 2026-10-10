"""Kestrel's focused face, adapted from Rain's authored facial topology.

Rain Rig © Blender Foundation | cloud.blender.org — CC BY 4.0.
https://studio.blender.org/characters/rain/v2/
https://creativecommons.org/licenses/by/4.0/
Modifications: Kestrel proportions, weighted lid neutral, brow pose, intrinsic
PBR paint and rigid binding to the project's existing 61-bone skeleton.
The source control rig, drivers, node modifiers and embedded scripts are unused.
"""
from pathlib import Path
import math
import bpy
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
import character_v2 as cv
import blender_common as bc

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'assets/characters/_shared/_source/rain/bundle/rain_rig.blend'
TEXTURES = Path(__file__).parent / 'textures'
SOURCE_TOP = 1.623896122
SOURCE_CHIN = 1.323
SOURCE_EYE = Vector((.04733059, -.09109604, 1.4732605))
SX, SY, SZ = .64, .73, .225 / (SOURCE_TOP - SOURCE_CHIN)
YSHIFT = .017


def _position(p, scale=1.):
    return Vector((p.x * SX, p.y * SY + YSHIFT,
                   1.475 + (p.z - SOURCE_CHIN) * SZ)) * scale


def _orbital(p, weights):
    """Pose source eyelid stations around their native eyeball pivot.

    Only Rain's named eyelid/crease influences participate. Socket, cheek,
    nose and forehead proportions remain affine. Depth follows the sphere so
    the original lid thickness survives the neutral aperture adjustment.
    """
    if not weights:
        return p.copy()
    sign = 1 if p.x >= 0 else -1
    c = Vector((sign * SOURCE_EYE.x, SOURCE_EYE.y, SOURCE_EYE.z))
    q = p.copy();d=p-c
    for angle,weight in weights:
        cs,sn=math.cos(angle),math.sin(angle)
        rotated=Vector((d.x, d.y*cs-d.z*sn, d.y*sn+d.z*cs))+c
        q+=(rotated-p)*weight
    return q


def _lid_weights(ob):
    ids = {g.index: g.name for g in ob.vertex_groups}
    # The inner/outer corners move less than each lid's central stations;
    # source crease controls follow gently, leaving cheek topology intact.
    angles={**{f'DEF-Eyelid_Top_{k}':a for k,a in enumerate((.09,.22,.20,.03),1)},
            **{f'DEF-Eyelid_Bot_{k}':a for k,a in enumerate((-.11,-.23,-.23,-.08),1)},
            **{f'DEF-EyeLid_Crease_{k}':a for k,a in enumerate((.03,.07,.065,.01,-.025,-.065,-.06,-.02,0.,.015),1)}}
    result = []
    for v in ob.data.vertices:
        result.append([(angles[ids[g.group].rsplit('.',1)[0]],g.weight)
                       for g in v.groups if ids[g.group].rsplit('.',1)[0] in angles])
    return result


def _copy_mesh(source, name, scale, material, kind='head'):
    """Copy geometry only; deliberately do not append source objects/rigs."""
    me = source.data
    basis = [v.co.copy() for v in me.vertices]
    shapes = {}
    keys = me.shape_keys.key_blocks if me.shape_keys else []
    for key in keys:
        if key.name != 'Basis':
            shapes[key.name] = [d.co.copy() for d in key.data]
    neutral = [p.copy() for p in basis]
    defaults = {'LipsAdjust': 1.} if kind=='head' else ({'Flat': 1.} if kind=='eye' else {'fix': 1.})
    for key, value in defaults.items():
        if key in shapes:
            neutral = [p + (k-b)*value for p,k,b in zip(neutral, shapes[key], basis)]
    if kind=='lash':
        line=np.polyfit([p.x for p in neutral],[p.z for p in neutral],4)
        for p in neutral:
            z=np.polyval(line,p.x)
            p.z=z+(p.z-z)*.55
    weights = _lid_weights(source) if kind in ('head','lash') else [[] for p in basis]
    if kind=='lash' and not any(weights):
        weights = [[(.22,1.)] for p in basis]
    def fit(p,w):
        return _position(_orbital(p,w),scale)
    final = [fit(p,w) for p,w in zip(neutral,weights)]
    faces = [tuple(p.vertices) for p in me.polygons]
    mirror = any(m.type=='MIRROR' for m in source.modifiers)
    if mirror:
        offset = len(final)
        final += [Vector((-p.x,p.y,p.z)) for p in final]
        faces += [tuple(offset+i for i in reversed(f)) for f in faces]
    ob = cv.mesh(name, final, faces, material)
    ob['source_credit'] = 'Rain Rig © Blender Foundation | cloud.blender.org'
    ob['source_license'] = 'CC BY 4.0'
    ob['source_url'] = 'https://studio.blender.org/characters/rain/v2/'
    ob['source_license_url'] = 'https://creativecommons.org/licenses/by/4.0/'
    ob['source_modifications'] = 'Kestrel affine proportions, authored lid/brow neutral, PBR paint, shared rig binding'
    if kind=='head':
        ob.shape_key_add(name='Basis')
        useful = ('mouth_open','Smile.L','Smile.R','LipsWide.L','LipsWide.R',
                  'LipsPuff_Upper','LipsPuff_Lower','CheekPuff.L','CheekPuff.R')
        for key in useful:
            if key not in shapes: continue
            points = [fit(n+(k-b),w)
                      for n,k,b,w in zip(neutral,shapes[key],basis,weights)]
            if max((p-q).length for p,q in zip(points,final))<1e-6: continue
            block = ob.shape_key_add(name=key)
            for d,p in zip(block.data,points): d.co=p
            block.value=0.
        ob['neutral_expression'] = 'Focused almond aperture baked from Rain authored eyelid weights; source LipsAdjust baked'
    # UVs are projective from the original authored frame, and unaffected by
    # Kestrel proportions; back half occupies the right side of the atlas.
    uv=ob.data.uv_layers.active
    for poly in ob.data.polygons:
        orig=[neutral[i % len(neutral)] for i in poly.vertices]
        front=sum(p.y for p in orig)/len(orig)<-.03
        for li in poly.loop_indices:
            idx=ob.data.loops[li].vertex_index
            p=neutral[idx % len(neutral)].copy()
            if mirror and idx>=len(neutral):p.x=-p.x
            if kind=='head':
                uv.data[li].uv=((p.x/.30+.5)*.5+(0 if front else .5),(p.z-1.275)/(SOURCE_TOP-1.275))
            elif kind=='eye':
                uv.data[li].uv=(.5+(p.x-math.copysign(SOURCE_EYE.x,p.x))/.080,.5+(p.z-SOURCE_EYE.z)/.080)
    return ob


def _paint_material(name, path, roughness):
    mat=bc.material(name,(1,1,1),rough=roughness)
    p=bc._principled(mat)
    bc._set_input(p,['Specular IOR Level','Specular'],.28 if roughness>.4 else .4)
    bc._set_input(p,['Subsurface Weight','Subsurface'],.035 if roughness>.4 else 0.)
    im=mat.node_tree.nodes.new('ShaderNodeTexImage')
    im.image=bpy.data.images.load(str(path),check_existing=True)
    mat.node_tree.links.new(im.outputs['Color'],p.inputs['Base Color'])
    return mat


def make(base):
    """Replace temporary facial anatomy, keep neck/hands and the shared rig."""
    prefix=base['prefix'];scale=base['scale']
    stems=('Head','Lips','MouthLine','Eyelids','Eye_L','Eye_R','Eyes','Brows','Lashes','Ears',
           'Eyelid_L','Eyelid_R','LashLine_L','LashLine_R','Brow_L','Brow_R')
    for ob in list(base['parts']):
        if ob.name.removeprefix(prefix+'_') in stems:
            base['parts'].remove(ob);bpy.data.objects.remove(ob,do_unlink=True)
    initial_objects=set(bpy.data.objects)
    names=['GEO-rain_head','GEO-rain_eyes_viewport','GEO-rain_eyebrows','GEO-rain_eyelashes']
    with bpy.data.libraries.load(str(SOURCE),link=False)as(src,dst): dst.objects=names
    source=dict(zip(names,dst.objects))
    face=_paint_material(f'M_{prefix}_RainFace',TEXTURES/'rain_face_basecolor.png',.58)
    eye=_paint_material(f'M_{prefix}_RainEye',TEXTURES/'rain_face_eye.png',.23)
    brow=bc.material(f'M_{prefix}_RainBrow',(.018,.012,.015),rough=.72)
    head=_copy_mesh(source[names[0]],prefix+'_Head',scale,face,'head')
    eyes=_copy_mesh(source[names[1]],prefix+'_Eyes',scale,eye,'eye')
    brows=_copy_mesh(source[names[2]],prefix+'_Brows',scale,brow,'brow')
    lashes=_copy_mesh(source[names[3]],prefix+'_Lashes',scale,brow,'lash')
    parts=[head,eyes,brows,lashes]
    # Shape the authored brow strip into a calm straight inner brow with a
    # restrained outer arch; project onto the face to prevent detached strips.
    bpy.context.view_layer.update()
    face_bvh=BVHTree.FromObject(head,bpy.context.evaluated_depsgraph_get())
    raw=source[names[2]].data.vertices
    xs=np.array([abs(v.co.x)*SX for v in raw])
    zs=np.array([1.475+(v.co.z-SOURCE_CHIN)*SZ for v in raw])
    ys=np.array([v.co.y*SY+YSHIFT for v in raw])
    zcurve=np.polyfit(xs,zs,3);ycurve=np.polyfit(xs,ys,3)
    for v in brows.data.vertices:
        x=v.co.x/scale
        t=max(0.,min(1.,(abs(x)-.012)/.047))
        center=1.609+.005*math.sin(math.pi*t)-.003*(1-t)
        v.co.z=(center+(v.co.z/scale-np.polyval(zcurve,abs(x)))*.62)*scale
        hit,normal,_,_=face_bvh.ray_cast(Vector((v.co.x,-.25*scale,center*scale)),Vector((0,1,0)),.4*scale)
        if hit:v.co.y=hit.y-.0010*scale+(v.co.y/scale-np.polyval(ycurve,abs(x)))*scale
    for ob in parts:
        for p in ob.data.polygons:p.use_smooth=True
        cv.rigid(ob,base,'head');base['parts'].append(ob)
    # Source objects never enter the scene; remove any appended dependencies.
    for ob in list(bpy.data.objects):
        if ob not in initial_objects and ob not in parts:
            bpy.data.objects.remove(ob,do_unlink=True)
    ec=_position(SOURCE_EYE,scale)
    front=_position(Vector((SOURCE_EYE.x,-.13030785,SOURCE_EYE.z)),scale).y
    base['dims'].update(eye_center_L=tuple(ec),eye_center_R=(-ec.x,ec.y,ec.z),
                        eye_front_y=front,eye_height=ec.z)
    base['materials'].update(brow=brow)
    bpy.context.view_layer.update()
    return head
