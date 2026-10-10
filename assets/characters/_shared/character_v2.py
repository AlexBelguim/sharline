"""Shared authored character anatomy and deterministic skinning for the v2 agents.

Metres, Z up, front -Y, her left +X.  Clothing is the body: this module only
creates head/ears/neck, exposed forearms and articulated hands.  No imported
mesh, voxel remesh, image-to-3D, automatic heat weights, or hidden nude torso.

Public entry points: build_base, mesh, body_loft, tube, bind, rigid, socket,
export_character, reset_pose, aim, bend, twist, pose, report.
"""
from pathlib import Path
import math
import json
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
import blender_common as bc
import female_base as fb

FINGERS = ('thumb', 'index', 'middle', 'ring', 'pinky')
REF_HEIGHT = 1.70
# Crown of the authored smooth-union cranium recipe; mapping this exact source
# bound avoids a flat cap while preserving the requested skull height.
RAW_HEAD_TOP = 1.706401993
PARENTS = {'pelvis': 'root', 'spine_01': 'pelvis', 'spine_02': 'spine_01',
           'spine_03': 'spine_02', 'neck_01': 'spine_03', 'head': 'neck_01'}
for _s in ('l', 'r'):
    PARENTS.update({f'clavicle_{_s}': 'spine_03', f'upperarm_{_s}': f'clavicle_{_s}',
                   f'lowerarm_{_s}': f'upperarm_{_s}', f'hand_{_s}': f'lowerarm_{_s}',
                   f'thigh_{_s}': 'pelvis', f'calf_{_s}': f'thigh_{_s}',
                   f'foot_{_s}': f'calf_{_s}', f'ball_{_s}': f'foot_{_s}'})
    for _f in FINGERS:
        PARENTS[f'{_f}_01_{_s}'] = f'hand_{_s}'
        PARENTS[f'{_f}_02_{_s}'] = f'{_f}_01_{_s}'
        PARENTS[f'{_f}_03_{_s}'] = f'{_f}_02_{_s}'
    for _limb in ('upperarm', 'lowerarm', 'thigh', 'calf'):
        PARENTS[f'{_limb}_twist_01_{_s}'] = f'{_limb}_{_s}'


def mesh(name, verts, faces, mat=None, smooth=True, col=None):
    """Create an authored mesh, correct outward winding, add portable UVs."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    (col or bpy.context.scene.collection).objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = smooth
    if mat is not None:
        me.materials.append(mat)
    uv = me.uv_layers.new(name='UVMap')
    if len(me.vertices):
        co = np.array(verts)
        lo, hi = co.min(0), co.max(0)
        for p in me.polygons:
            axes = (0, 2) if abs(p.normal.y) >= max(abs(p.normal.x), abs(p.normal.z)) else ((1, 2) if abs(p.normal.x) > abs(p.normal.z) else (0, 1))
            for li in p.loop_indices:
                v = co[me.loops[li].vertex_index]
                uv.data[li].uv = tuple((v[a] - lo[a]) / max(hi[a] - lo[a], 1e-6) for a in axes)
    return ob


def material(name, color, rough=.6, metal=0, emission=None, emission_strength=0):
    return bc.material(name, color, rough, metal, emission=emission, emission_strength=emission_strength)


def body_loft(name, rows, mat=None, sides=32, cap=False, col=None):
    """Torso/waist shell. rows=(z,half_width,half_depth,center_y,exponent)."""
    verts, faces = [], []
    for row in rows:
        z, rx, ry, cy, *rest = row
        exp = rest[0] if rest else 2
        for j in range(sides):
            a = 2 * math.pi * j / sides
            sn, cs = math.sin(a), math.cos(a)
            verts.append((rx * math.copysign(abs(sn) ** (2 / exp), sn),
                          cy - ry * math.copysign(abs(cs) ** (2 / exp), cs), z))
    for k in range(len(rows) - 1):
        for j in range(sides):
            a = k * sides + j
            b = k * sides + (j + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    if cap:
        faces.extend([tuple(reversed(range(sides))), tuple((len(rows) - 1) * sides + j for j in range(sides))])
    return mesh(name, verts, faces, mat, col=col)


def tube(name, points, radii, mat=None, sides=20, cap=True, col=None, hint=(0, -1, 0)):
    """Quad tube following explicit stations; scalar or elliptical station radii."""
    pts = [Vector(p) for p in points]
    if isinstance(radii, (int, float)):
        radii = [radii] * len(pts)
    verts, faces = [], []
    for k, (p, r) in enumerate(zip(pts, radii)):
        d = ((pts[min(k + 1, len(pts) - 1)] - pts[max(k - 1, 0)])).normalized()
        front = Vector(hint)
        front = front - d * front.dot(d)
        if front.length < .001:
            front = d.cross(Vector((1, 0, 0)))
        front.normalize()
        side = d.cross(front).normalized()
        rx, ry = (r, r) if isinstance(r, (int, float)) else r
        for j in range(sides):
            a = 2 * math.pi * j / sides
            verts.append(p + side * (math.sin(a) * rx) + front * (math.cos(a) * ry))
    for k in range(len(pts) - 1):
        for j in range(sides):
            a, b = k * sides + j, k * sides + (j + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    if cap:
        faces.extend([tuple(reversed(range(sides))), tuple((len(pts) - 1) * sides + j for j in range(sides))])
    ob = mesh(name, verts, faces, mat, col=col)
    # Logical station UVs follow the path instead of arbitrary world projections.
    uv = ob.data.uv_layers.active
    for p in ob.data.polygons:
        for li in p.loop_indices:
            vid = ob.data.loops[li].vertex_index
            uv.data[li].uv = ((vid % sides) / sides, (vid // sides) / max(1, len(pts) - 1))
    return ob


def _smooth(a, b, x):
    t = max(0., min(1., (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def _segment(p, a, b):
    d = b - a
    t = max(0., min(1., (p - a).dot(d) / max(d.length_squared, 1e-12)))
    return (p - (a + d * t)).length, t


def _write_weights(ob, base, weights):
    """Known mesh vertices -> normalized max-four weights, never heat/proxy weights."""
    bpy.context.view_layer.update()
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    groups = {}
    for i, w in enumerate(weights):
        w = sorted(((n, float(v)) for n, v in w.items() if v > 1e-6), key=lambda q: -q[1])[:4]
        total = sum(v for n, v in w)
        if total <= 0:
            w, total = [('pelvis', 1.)], 1.
        for n, v in w:
            if n not in groups:
                groups[n] = ob.vertex_groups.new(name=n)
            groups[n].add([i], v / total, 'REPLACE')
    for mod in list(ob.modifiers):
        if mod.type == 'ARMATURE':
            ob.modifiers.remove(mod)
    mod = ob.modifiers.new('Shared anatomy skin', 'ARMATURE')
    mod.object = base['armature']
    mod.use_deform_preserve_volume = False
    mw = ob.matrix_world.copy()
    ob.parent = base['armature']
    ob.matrix_world = mw
    ob['skin_method'] = 'authored region / analytic joint loops; normalized maximum four'
    return ob


def rigid(ob, base, bone='pelvis'):
    if bone not in base['armature'].data.bones:
        raise ValueError(f'Unknown bone {bone}')
    return _write_weights(ob, base, [{bone: 1.} for _ in ob.data.vertices])


def bind(ob, base, region='torso'):
    """Deterministic garment binding with explicit anatomical region.

    torso/coat distributes pelvis+spines by height; arm_l/r and leg_l/r only
    allow that limb's chain.  head and pelvis are rigid. auto chooses region
    from position.  Hand anatomy itself uses its logical digit chains.
    """
    if region in ('head', 'pelvis', 'neck_01', 'spine_03', 'spine_02'):
        return rigid(ob, base, region)
    bpy.context.view_layer.update()
    J, s = base['joints'], base['scale']
    weights = []
    for v in ob.data.vertices:
        p = ob.matrix_world @ v.co
        reg = region
        if reg == 'auto':
            if p.z > 1.475 * s:
                reg = 'head'
            elif p.z < .81 * s:
                reg = 'leg_l' if p.x > 0 else 'leg_r'
            elif abs(p.x) > .19 * s:
                reg = 'arm_l' if p.x > 0 else 'arm_r'
            else:
                reg = 'torso'
        if reg in ('head', 'pelvis'):
            w = {reg: 1.}
        elif reg.startswith('arm_'):
            sd = reg[-1]
            S, E, Wr = (J[f'{n}_{sd}'] for n in ('upperarm', 'lowerarm', 'hand'))
            if (p - E).dot((Wr - E).normalized()) < -.025 * s:
                du = (E - S).normalized()
                t = (p - S).dot(du)
                c = 1 - _smooth(-.008 * s, .065 * s, t)
                el = _smooth((E - S).length - .04 * s, (E - S).length + .04 * s, t)
                w = {f'clavicle_{sd}': c * .50, 'spine_03': c * .50,
                     f'upperarm_{sd}': (1 - c) * (1 - el), f'lowerarm_{sd}': (1 - c) * el}
            else:
                d = (Wr - E).normalized()
                t = (p - E).dot(d)
                elbow = _smooth(-.04 * s, .04 * s, t)
                wrist = _smooth((Wr - E).length - .022 * s, (Wr - E).length + .025 * s, t)
                w = {f'upperarm_{sd}': 1 - elbow,
                     f'lowerarm_{sd}': elbow * (1 - wrist), f'hand_{sd}': elbow * wrist}
        elif reg.startswith('leg_'):
            sd = reg[-1]
            H, K, A = (J[f'{n}_{sd}'] for n in ('thigh', 'calf', 'foot'))
            hip = 1 - _smooth(H.z - .07 * s, H.z + .025 * s, p.z)
            knee = 1 - _smooth(K.z - .042 * s, K.z + .042 * s, p.z)
            ankle = 1 - _smooth(A.z - .008 * s, A.z + .05 * s, p.z)
            w = {'pelvis': 1 - hip, f'thigh_{sd}': hip * (1 - knee),
                 f'calf_{sd}': hip * knee * (1 - ankle), f'foot_{sd}': hip * knee * ankle}
        else:
            names = ('pelvis', 'spine_01', 'spine_02', 'spine_03')
            stations = (.965 * s, 1.055 * s, 1.185 * s, 1.315 * s)
            if p.z <= stations[0]:
                w = {'pelvis': 1.}
            elif p.z >= stations[-1]:
                w = {'spine_03': 1.}
            else:
                for i in range(3):
                    if stations[i] <= p.z < stations[i + 1]:
                        t = _smooth(stations[i], stations[i + 1], p.z)
                        w = {names[i]: 1 - t, names[i + 1]: t}
                        break
            # Coat tails: pelvis follows sitting/sprinting; distal tail blends
            # toward its own thigh only, without cross-leg influence.
            if reg == 'coat' and p.z < .90 * s:
                sd = 'l' if p.x >= 0 else 'r'
                t = (1 - _smooth(.64 * s, .91 * s, p.z)) * .55
                w = {'pelvis': 1 - t, f'thigh_{sd}': t}
        weights.append(w)
    return _write_weights(ob, base, weights)


def _head_transform(p, s=1.):
    p = Vector(p)
    chin = 1.70 - 1.70 / 7.5
    back_shift=.016*_smooth(-.025,.020,p.y)
    return Vector((p.x,p.y-back_shift,1.475+(p.z-chin)*(.225/(RAW_HEAD_TOP-chin))))*s


def _eye_recess(p, info):
    """Smooth authored orbital transition, independent of sampling resolution."""
    p = np.array(p, dtype=float, copy=True)
    ec = info['eye_c']
    if p[1] < -.014:
        ry = .0077 if p[2] >= ec[2] else .0065
        r = math.sqrt(((abs(p[0]) - ec[0]) / .0165) ** 2 + ((p[2] - ec[2]) / ry) ** 2)
        p[1] += .0065 * (1 - _smooth(.67, 1.48, r))
    return p


def _head_mesh(prefix, field, info, mat, s):
    # Explicit horizontal loops concentrate vertices on lips, nose and eyelids.
    # Radial projection is solely onto our own authored sculpt recipe.
    zs = sorted(set(np.concatenate((np.linspace(info['z_chin'] + .003, RAW_HEAD_TOP - .001, 36),
                                   np.linspace(info['lip_c'][2] - .014, info['lip_c'][2] + .019, 10),
                                   np.linspace(info['eye_c'][2] - .015, info['eye_c'][2] + .015, 10)))))
    sides = 64
    verts, faces = [], []
    for z in zs:
        cy = float(np.interp(z, [info['z_chin'], info['z_chin'] + .025, info['z_chin'] + .075, RAW_HEAD_TOP], [-.055, -.036, .008, .020]))
        # Spend three quarters of the section on the visible face. This makes
        # clean eyelid/nose/cheek transitions with fewer hidden scalp vertices.
        theta = np.concatenate((np.linspace(-math.pi, -1.1, 8, endpoint=False),
                                np.linspace(-1.1, 1.1, 48, endpoint=False),
                                np.linspace(1.1, math.pi, 8, endpoint=False)))
        D = np.stack([np.sin(theta), -np.cos(theta), np.zeros(sides)], 1)
        C = np.tile([0, cy, z], (sides, 1))
        tt = np.linspace(0, .16, 180)
        fv = field((C[:, None, :] + D[:, None, :] * tt[None, :, None]).reshape(-1, 3)).reshape(sides, -1)
        # First exit includes the sculpted eyeball recess. Its back wall sits
        # behind the eye, giving a continuous skin surface with no jagged
        # approximated cutout along the visible canthus.
        idx = np.argmax((fv[:, :-1] < 0) & (fv[:, 1:] >= 0), axis=1)
        has = np.any((fv[:, :-1] < 0) & (fv[:, 1:] >= 0), axis=1)
        aa, bb = tt[idx], tt[idx + 1]
        for _ in range(14):
            mm = (aa + bb) * .5
            ff = field(C + D * mm[:, None])
            aa = np.where(ff < 0, mm, aa)
            bb = np.where(ff >= 0, mm, bb)
        rr = np.where(has, (aa + bb) * .5, .010)
        for p in C + D * rr[:, None]:
            p = _eye_recess(p, info)
            # Match the reference's compact bridge/tip rather than the SDF's
            # projecting midface. Preserve side-cheek and forehead contours.
            zz=float(_head_transform(p).z)
            if abs(p[0])<.024 and 1.522<zz<1.612 and p[1]<-.044:
                target=float(np.interp(zz,[1.522,1.540,1.553,1.580,1.612],[-.086,-.100,-.103,-.091,-.081]))
                excess=max(0.,target-p[1])
                blend=1-_smooth(.014,.024,abs(p[0]))
                p[1]+=excess*blend
            # Stronger cheek planes, a clean taper into the jaw.
            if p[1]<-.035 and 1.515<zz<1.578:
                cheek=_smooth(1.515,1.535,zz)*(1-_smooth(1.560,1.578,zz))
                p[0]*=1-.045*cheek
            verts.append(p)
    ec = info['eye_c']
    va = np.array(verts)
    for k in range(len(zs) - 1):
        for j in range(sides):
            a, b = k * sides + j, k * sides + (j + 1) % sides
            f = (a, b, b + sides, a + sides)
            c = np.mean(va[list(f)], axis=0)
            faces.append(f)
    lower = len(verts)
    verts.append(np.array((0, -.055, info['z_chin'])))
    upper = len(verts)
    verts.append(np.array((0, .020, RAW_HEAD_TOP)))
    for j in range(sides):
        faces.append((lower, (j + 1) % sides, j))
        a = (len(zs) - 1) * sides
        faces.append((upper, a + j, a + (j + 1) % sides))
    ob = mesh(f'{prefix}_Head', verts, faces, mat)
    fb._face_paint(ob, field, info, 1., lip_mult=(.80, .49, .48), blush_mult=(1.0, .83, .75))
    for v in ob.data.vertices:
        v.co = _head_transform(v.co, s)
    ob['topology'] = 'authored 64-sided horizontal facial loops; sculpted eyeball recesses; no voxel remesh'
    return ob


def _lids(prefix, info, field, mat, s):
    """Low, blended lids following the same almond as the eye surface."""
    verts, faces = [], []
    n = 64
    for sign in (1, -1):
        loops = []
        for ring, expand in enumerate((1., 1.11, 1.28, 1.55)):
            ids = []
            raw=[]
            for k in range(n):
                a=2*math.pi*k/n;cs,sn=math.cos(a),math.sin(a)
                dx=.0132*cs*expand
                dz=(.0055 if sn>=0 else .0043)*sn*expand+.09*dx
                raw.append((sign*(info['eye_c'][0]+dx),0.,info['eye_c'][2]+dz))
            projected=_face_front(raw,field)
            for p in projected:
                surface=_eye_recess(p,info)
                if ring==0:p[1]+=.00065
                elif ring==1:p[1]+=.0003 if p[2]>=info['eye_c'][2] else .0010
                elif ring==2:p[1]=surface[1]-.00035
                else:p[1]=surface[1]-.00012
                ids.append(len(verts))
                verts.append(_head_transform(p, s))
            loops.append(ids)
        for k in range(3):
            for j in range(n):
                faces.append((loops[k][j], loops[k][(j+1)%n],loops[k+1][(j+1)%n],loops[k+1][j]))
    return mesh(f'{prefix}_Eyelids', verts, faces, mat)


def _ears(prefix, mat, s):
    # Anatomical outer helix + recessed concha, explicitly ordered surface loops.
    verts, faces = [], []
    for sign in (1, -1):
        start = len(verts)
        for ring, (rx, depth) in enumerate(((1., .003), (.82, .009), (.55, .005), (.25, .002))):
            for j in range(24):
                a = 2 * math.pi * j / 24
                z = 1.578 + .028 * rx * math.cos(a)
                y = .005 + .0125 * rx * math.sin(a) + .005 * math.cos(a)
                x = sign * (.072 + depth + .001 * math.cos(a))
                verts.append(Vector((x, y, z)) * s)
        for k in range(3):
            for j in range(24):
                a, b = start + k * 24 + j, start + k * 24 + (j + 1) % 24
                faces.append((a, b, b + 24, a + 24))
        faces.append(tuple(start + 72 + j for j in range(24)))
        # back closes the ear into a clean shell attached at the skull.
        back = len(verts)
        verts.append(Vector((sign * .070, .006, 1.578)) * s)
        for j in range(24):
            faces.append((back, start + (j + 1) % 24, start + j))
    return mesh(f'{prefix}_Ears', verts, faces, mat)


def _eye_patch(prefix, sd, info, s, mats):
    """Only the visible spherical almond, with clean concentric iris loops.

    There is no full scleral sphere outside the modeled lid opening to leak
    through an adjacent skin loop.  Inner circular rings remain actual eye
    surface geometry, not a decal or a floating white plane.
    """
    sign = 1 if sd == 'L' else -1
    c = info['eye_c'] * np.array((sign, 1, 1))
    er = info['eye_r']
    verts = [c + np.array((0, 0, .0001))]
    seg = 64
    rings = []
    for ring in range(5):
        ids = []
        for j in range(seg):
            a = 2 * math.pi * j / seg
            sn, cs = math.sin(a), math.cos(a)
            # Mild upper/lower asymmetry and lifted outer canthus.
            ry = .0055 if sn >= 0 else .0043
            rho = 1 / math.sqrt((cs / .0132) ** 2 + (sn / ry) ** 2)
            iris_edge = min(.0067, rho * .982)
            r = (min(.0025,iris_edge*.45), iris_edge*.90, iris_edge, iris_edge + (rho - iris_edge) * .52, rho)[ring]
            x = r * cs
            z = r * sn + .0001 + .090 * x * sign
            ids.append(len(verts))
            verts.append(c + np.array((x, 0, z)))
        rings.append(ids)
    # A shallow corneal dome, seated within the skin plane. The former large
    # sphere exposure gave a protruding, staring eye and inverted iris rings.
    projected=_face_front(verts,info['_head_field'])
    centre_y=float(_face_front([c],info['_head_field'])[0][1])
    for i,p in enumerate(projected):
        dx=(p[0]-c[0])/.0132;dz=(p[2]-c[2]-.09*(p[0]-c[0])*sign)/.0055
        fullness=max(0.,1-dx*dx-dz*dz)
        p[1]+=.0014-.0023*fullness
        radius=math.hypot(p[0]-c[0],p[2]-c[2])
        straight_gaze=1-_smooth(.0055,.0100,radius)
        iris_y=centre_y-.0008+.0009*min(1,(radius/.0067)**2)
        p[1]=p[1]*(1-straight_gaze)+iris_y*straight_gaze
    verts=[_head_transform(p,s)for p in projected]
    faces, slot = [], []
    for j in range(seg):
        faces.append((0, rings[0][j], rings[0][(j + 1) % seg])); slot.append(2)
    for k in range(4):
        for j in range(seg):
            faces.append((rings[k][j], rings[k][(j + 1) % seg], rings[k + 1][(j + 1) % seg], rings[k + 1][j]))
            slot.append(1 if k == 0 else (3 if k == 1 else 0))
    ob = mesh(f'{prefix}_Eye_{sd}', verts, faces)
    for mat in mats:
        ob.data.materials.append(mat)
    for p, mi in zip(ob.data.polygons, slot):
        p.material_index = mi
    return ob


def _face_front(points, field):
    """Keep authored X/Z loops fixed, sample front Y only (no feature drift)."""
    points = np.array(points, dtype=float)
    n = len(points)
    ys = np.linspace(-.15, .04, 180)
    probes = np.repeat(points[:, None, :], len(ys), 1)
    probes[:, :, 1] = ys[None, :]
    ff = field(probes.reshape(-1, 3)).reshape(n, -1)
    inside = ff < 0
    idx = inside.argmax(1)
    lo = ys[np.maximum(0, idx - 1)]
    hi = ys[idx]
    for _ in range(15):
        mid = (lo + hi) * .5
        points[:, 1] = mid
        f = field(points)
        lo = np.where(f >= 0, mid, lo)
        hi = np.where(f < 0, mid, hi)
    points[:, 1] = (lo + hi) * .5
    return points


def _lip_surfaces(prefix, info, field, s, mat, dark_mat):
    """Authored cupid's bow, lower lip and mouth-corner line on the sculpt."""
    zc = info['lip_c'][2]
    verts, faces, offsets = [], [], []
    n = 28
    width = .0215
    for upper in (True, False):
        start = len(verts)
        for i in range(n + 1):
            x = -width + 2 * width * i / n
            t = x / width
            taper = max(0., 1 - t * t)
            seam = .0004 * taper - .0006 * t * t
            bow = .0024 * math.exp(-((abs(x) - .0065) / .0045) ** 2) + .0008 * taper
            border = bow * taper ** .35 if upper else -.0045 * taper ** .7
            for j in range(4):
                q = j / 3
                z = zc + seam * (1 - q) + border * q
                verts.append((x, -.12, z))
                offsets.append(.0005 + .00035 * math.sin(math.pi * q) * taper)
        for i in range(n):
            for j in range(3):
                a = start + i * 4 + j
                faces.append((a, a + 4, a + 5, a + 1))
    projected = _face_front(verts, field)
    projected[:, 1] -= np.array(offsets)
    lip = mesh(f'{prefix}_Lips', [_head_transform(p, s) for p in projected], faces, mat)
    lip.data.materials.append(dark_mat)
    for p in lip.data.polygons[:n * 3]:
        p.material_index = 1
    points, line_faces = [], []
    for i in range(n + 1):
        x = -width + 2 * width * i / n
        t = x / width
        z = zc + .0004 * (1 - t * t) - .0006 * t * t
        half = .00018 * (1-t*t)+.00010
        points.extend(((x, -.12, z - half), (x, -.12, z + half)))
        if i < n:
            a = 2 * i
            line_faces.append((a, a + 2, a + 3, a + 1))
    projected = _face_front(points, field)
    projected[:, 1] -= .0011
    points = [_head_transform(p, s) for p in projected]
    line_mat = bc.material(f'M_{prefix}_MouthLine', (.042, .012, .008), rough=.95)
    bc._set_input(bc._principled(line_mat), ['Specular IOR Level', 'Specular'], .08)
    line = mesh(f'{prefix}_MouthLine', points, line_faces, line_mat)
    return lip, line


def _nostril_surfaces(prefix, info, field, s, ztip):
    """Small recessed painted nostril rims define the underside of the nose."""
    vertices=[];faces=[]
    for sign in(-1,1):
        raw=[]
        for j in range(16):
            a=2*math.pi*j/16
            raw.append((sign*.0067+.0020*math.cos(a),0.,ztip-.0050+.0008*math.sin(a)))
        projected=_face_front(raw,field)
        for p in projected:
            q=_head_transform(p,s)
            zz=q.z/s
            target=float(np.interp(zz,[1.522,1.540,1.553,1.580,1.612],[-.086,-.100,-.103,-.091,-.081]))*s
            q.y=max(q.y,target)-.00025*s
            vertices.append(q)
        base=len(vertices)-16
        faces.append(tuple(base+j for j in range(16)))
    mat=bc.material(f'M_{prefix}_Nostril',(.065,.025,.013),rough=.95)
    return mesh(f'{prefix}_NostrilRims',vertices,faces,mat)


def _skeleton(prefix, J, s):
    B = {}
    chain = ('pelvis', 'spine_01', 'spine_02', 'spine_03', 'neck_01', 'head')
    for i, n in enumerate(chain):
        B[n] = (J[n], J[chain[i + 1]] if i + 1 < len(chain) else Vector((0, .020, 1.68)) * s)
    for sd in ('l', 'r'):
        for n, nn in (('clavicle', 'upperarm'), ('upperarm', 'lowerarm'), ('lowerarm', 'hand'),
                      ('thigh', 'calf'), ('calf', 'foot'), ('foot', 'ball')):
            B[f'{n}_{sd}'] = (J[f'{n}_{sd}'], J[f'{nn}_{sd}'])
        B[f'ball_{sd}'] = (J[f'ball_{sd}'], J[f'toe_end_{sd}'])
        B[f'hand_{sd}'] = (J[f'hand_{sd}'], J[f'middle_01_{sd}'])
        for f in FINGERS:
            for k in range(1, 4):
                B[f'{f}_{k:02d}_{sd}'] = (J[f'{f}_{k:02d}_{sd}'], J[f'{f}_{k + 1:02d}_{sd}'] if k < 3 else J[f'{f}_tip_{sd}'])
        for n in ('upperarm', 'lowerarm', 'thigh', 'calf'):
            a, b = B[f'{n}_{sd}']
            B[f'{n}_twist_01_{sd}'] = (a.lerp(b, .28), a.lerp(b, .65))
    arm_data = bpy.data.armatures.new(f'{prefix}_Armature')
    arm = bpy.data.objects.new(f'{prefix}_Armature', arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    root = arm_data.edit_bones.new('root')
    root.head, root.tail, root.use_deform = (0, 0, 0), (0, 0, .12 * s), False
    pending = dict(B)
    while pending:
        for n in list(pending):
            parent = PARENTS[n]
            if parent not in arm_data.edit_bones:
                continue
            b = arm_data.edit_bones.new(n)
            b.head, b.tail = pending.pop(n)
            b.parent = arm_data.edit_bones[parent]
            b.use_connect = (b.parent.tail - b.head).length < 1e-6
            hint = Vector((0, 0, 1)) if n.startswith(('clavicle', 'upperarm', 'lowerarm', 'hand', *FINGERS, 'foot', 'ball')) else Vector((0, -1, 0))
            b.align_roll(hint)
    bpy.ops.object.mode_set(mode='OBJECT')
    arm.show_in_front = True
    arm['convention'] = 'UE5 mannequin names, identical normalized rest matrices on both v2 agents'
    arm['front'] = '-Y'
    arm['reference_skull_height_m'] = 1.70
    arm['height_m'] = REF_HEIGHT * s
    return arm


def socket(name, base, bone, loc, yaxis=(0, 1, 0), zhint=(0, 0, 1)):
    Y, Z = Vector(yaxis).normalized(), Vector(zhint)
    Z = (Z - Y * Z.dot(Y)).normalized()
    X = Y.cross(Z).normalized()
    M = Matrix((X, Y, Z)).transposed().to_4x4()
    M.translation = Vector(loc)
    ob = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(ob)
    ob.empty_display_type, ob.empty_display_size = 'ARROWS', .025
    arm = base['armature']
    bpy.context.view_layer.update()
    ob.parent, ob.parent_type, ob.parent_bone = arm, 'BONE', bone
    bpy.context.view_layer.update()
    ob.matrix_world = M
    bpy.context.view_layer.update()
    ob['socket_bone'] = bone
    base.setdefault('sockets', []).append(ob)
    return ob


def _hand_skin(ob, base, sd):
    J, s = base['joints'], base['scale']
    weights = []
    Wr = J[f'hand_{sd}']
    ax = base['hand_axes'][sd][0]
    for v in ob.data.vertices:
        p = ob.matrix_world @ v.co
        u = (p - Wr).dot(ax)
        candidates = []
        for f in FINGERS:
            for k in range(1, 4):
                n = f'{f}_{k:02d}_{sd}'
                a = J[n]
                b = J[f'{f}_{k + 1:02d}_{sd}'] if k < 3 else J[f'{f}_tip_{sd}']
                dist, t = _segment(p, a, b)
                candidates.append((dist, n, t, f, k))
        candidates.sort()
        dist, n, t, f, k = candidates[0]
        digit = _smooth(.048 * s, .082 * s, u) if f != 'thumb' else _smooth(.014 * s, .052 * s, (p - Wr).length)
        root = J[f'{f}_01_{sd}']
        forward = (p - root).dot((J[f'{f}_02_{sd}'] - root).normalized())
        digit *= _smooth(-.008 * s, .012 * s, forward)
        w = {f'hand_{sd}': 1 - digit, n: digit}
        # Blend across each interphalangeal joint over three known loops.
        if t < .16 and k > 1:
            blend = .5 * (1 - _smooth(0, .16, t))
            w[n] = digit * (1 - blend)
            w[f'{f}_{k - 1:02d}_{sd}'] = digit * blend
        elif t > .84 and k < 3:
            blend = .5 * _smooth(.84, 1., t)
            w[n] = digit * (1 - blend)
            w[f'{f}_{k + 1:02d}_{sd}'] = digit * blend
        wrist = 1 - _smooth(-.02 * s, .02 * s, u)
        if wrist > 0:
            w = {key: val * (1 - wrist) for key, val in w.items()}
            w[f'lowerarm_{sd}'] = wrist
        weights.append(w)
    return _write_weights(ob, base, weights)


def build_base(prefix='KES', height=1.70, skin=(.62, .42, .33), eye_color=(.16, .30, .26), face=None):
    """Build only visible authored anatomy + compatible rig; return shared data."""
    s = height / REF_HEIGHT
    face_cfg = {'eye_z': .12115, 'jaw_w': .94, 'chin_w': 1.08, 'cheek': 1.10, 'lip_full': 1.12, 'nose_len': .80, 'nose_w': .80, 'eye_open': .94}
    if face:
        face_cfg.update(face)
    ops, old_J, info = fb.make_recipe(build=0., face=face_cfg)
    # Place the authored mouth/lip sculpt at the concept's lower-face landmark.
    lip_tags = {'philtrumfill', 'upperlip', 'tubercle', 'lowerlip', 'mouthline', 'mouthcorner', 'mentolabial'}
    for op in ops:
        if op.tag in lip_tags:
            op.prim.c[2] -= .009
            op.prim.lo[2] -= .009
            op.prim.hi[2] -= .009
            if op.tag in ('upperlip','tubercle','lowerlip'):
                op.prim.c[1]+=.0045
                op.prim.lo[1]+=.0045
                op.prim.hi[1]+=.0045
    info['lip_c'][2] -= .009
    info['brow_shape'] = {'w0': .0065, 'w1': .0023, 'arch': .0034, 'drop': .0030}
    head_tags = {'cranium', 'parietal', 'faceloft', 'chin', 'cheekfill', 'cheekbone', 'brow', 'nosebody',
                 'nosebridge', 'nosetip', 'ala', 'columella', 'nosebase', 'philtrumfill', 'upperlip',
                 'tubercle', 'lowerlip', 'mouthline', 'mouthcorner', 'mentolabial'}
    head_field = fb.Field([op for op in ops if op.tag in head_tags], 1.)
    info['_head_field']=head_field
    head_eye_field = fb.Field([op for op in ops if op.tag in head_tags | {'eyecarve', 'pocket'}], 1.)
    field = fb.Field(ops, 1.)
    # Reuse the existing procedural sculpt recipe, not its generated full body.
    Mskin = fb._skin_material(f'M_{prefix}_Skin', skin)
    bc._set_input(bc._principled(Mskin), ['Subsurface Weight', 'Subsurface'], .025)
    bc._set_input(bc._principled(Mskin), ['Specular IOR Level', 'Specular'], .25)
    bc._set_input(bc._principled(Mskin), ['Roughness'], .65)
    lip_color = (.19,.055,.032) if prefix=='KES' else (.14,.050,.030)
    Mlips = bc.material(f'M_{prefix}_Lips', lip_color, rough=.48)
    bc._set_input(bc._principled(Mlips), ['Specular IOR Level', 'Specular'], .20)
    Mupper = bc.material(f'M_{prefix}_UpperLip', tuple(c * .78 for c in lip_color), rough=.54)
    bc._set_input(bc._principled(Mupper), ['Specular IOR Level', 'Specular'], .15)
    J = {'root': Vector((0, 0, 0)), 'pelvis': Vector((0, .005, .91)) * s,
         'spine_01': Vector((0, .010, 1.035)) * s, 'spine_02': Vector((0, .015, 1.175)) * s,
         'spine_03': Vector((0, .010, 1.315)) * s, 'neck_01': Vector((0, .008, 1.405)) * s,
         'head': Vector((0, .010, 1.490)) * s}
    # Coherently rotate+translate the known hand template onto the brief A-pose.
    Xold, Told, Dold = info['hand_axes']
    X = np.array((.559 - .370, -.042, .997 - 1.155))
    X /= np.linalg.norm(X)
    T = np.array((0., -1., 0.)); T = T - (T @ X) * X; T /= np.linalg.norm(T)
    D = np.cross(T, X)
    Rhand = np.stack((X, T, D), 1) @ np.stack((Xold, Told, Dold), 1).T
    Wrnew = np.array((.559, -.042, .997))
    for sd, sign in (('l', 1), ('r', -1)):
        mir = Vector((sign, 1, 1))
        for n, p in {'clavicle': (.025, -.012, 1.398), 'upperarm': (.165, 0, 1.360),
                     'lowerarm': (.370, 0, 1.155), 'hand': (.559, -.042, .997),
                     'thigh': (.085, .005, .860), 'calf': (.110, -.008, .470),
                     'foot': (.118, .006, .085), 'ball': (.124, -.125, .035),
                     'toe_end': (.128, -.195, .027)}.items():
            J[f'{n}_{sd}'] = Vector(p) * s
            J[f'{n}_{sd}'].x *= sign
        for f in FINGERS:
            for n in [f'{f}_{i:02d}' for i in range(1, 4)] + [f'{f}_tip']:
                p = Wrnew + Rhand @ (old_J[f'{n}_L'] - info['Wr'])
                p[0] *= sign
                J[f'{n}_{sd}'] = Vector(p) * s
    aliases = {'upperarm': 'upperarm', 'forearm': 'lowerarm', 'hand': 'hand', 'thigh': 'thigh',
               'calf': 'calf', 'foot': 'foot', 'clavicle': 'clavicle'}
    for sd in ('l', 'r'):
        for old, new in aliases.items():
            J[f'{old}_{sd.upper()}'] = J[f'{new}_{sd}']
        for f in FINGERS:
            for k in range(1, 4):
                J[f'{f}_{k:02d}_{sd.upper()}'] = J[f'{f}_{k:02d}_{sd}']
            J[f'{f}_tip_{sd.upper()}'] = J[f'{f}_tip_{sd}']
    base = {'prefix': prefix, 'scale': s, 'joints': J, 'parts': [], 'sockets': [],
            'materials': {'skin': Mskin, 'lips': Mlips}, 'hand_axes': {}}
    base['armature'] = _skeleton(prefix, J, s)
    head = _head_mesh(prefix, head_field, info, Mskin, s)
    base['parts'].append(rigid(head, base, 'head'))
    for lip_ob in _lip_surfaces(prefix, info, head_field, s, Mlips, Mupper):
        base['parts'].append(rigid(lip_ob, base, 'head'))
    ears = _ears(prefix, Mskin, s)
    base['parts'].append(rigid(ears, base, 'head'))
    lids = _lids(prefix, info, head_field, Mskin, s)
    # Give non-painted skin objects white tint so the face attribute material
    # remains stable in both Blender and glTF.
    base['parts'].append(rigid(lids, base, 'head'))
    neck = tube(f'{prefix}_Neck', [Vector((0, .011, z)) * s for z in (1.405, 1.430, 1.455, 1.475, 1.495)],
                [(r * s, r * s) for r in (.043, .041, .040, .039, .036)], Mskin, sides=24, cap=False)
    _write_weights(neck, base, [{'neck_01': 1 - _smooth(1.45 * s, 1.49 * s, v.co.z), 'head': _smooth(1.45 * s, 1.49 * s, v.co.z)} for v in neck.data.vertices])
    base['parts'].append(neck)
    # Eyeballs have concentric authored material loops (sclera, iris, pupil).
    Mscl = bc.material(f'M_{prefix}_EyeSclera', (.42, .38, .31), rough=.35)
    Miris = bc.material(f'M_{prefix}_EyeIris', eye_color, rough=.24)
    Mlimbal = bc.material(f'M_{prefix}_EyeLimbal', tuple(c * .24 for c in eye_color), rough=.30)
    Mpup = bc.material(f'M_{prefix}_EyePupil', (.006, .008, .010), rough=.20)
    for sign, sd in ((1, 'L'), (-1, 'R')):
        eo = _eye_patch(prefix, sd, info, s, [Mscl, Miris, Mpup, Mlimbal])
        bc.smart_uv(eo)
        base['parts'].append(rigid(eo, base, 'head'))
    Mbrow = bc.material(f'M_{prefix}_Brow', (.027, .018, .014), rough=.75)
    brows = fb._brow_object(f'{prefix}_Brows', head_field, 1., info, Mbrow, None)
    for ob in (brows,):
        for v in ob.data.vertices:
            v.co = _head_transform(v.co, s)
            v.co.z -= .003 * s
        bc.smart_uv(ob)
        base['parts'].append(rigid(ob, base, 'head'))
    lash_parts = []
    for sign, side in ((1, 'L'), (-1, 'R')):
        raw,radii=[],[]
        for k in range(29):
            t = k / 28
            a=math.pi*(1-t);dx=.0132*math.cos(a)
            dz=.0055*math.sin(a)+.09*dx
            raw.append((sign*(info['eye_c'][0]+dx),0,info['eye_c'][2]+dz))
            radii.append((.00016+.00032*math.sin(math.pi*t))*s)
        projected=_face_front(raw,head_field);projected[:,1]+=.0001
        points=[_head_transform(p,s)for p in projected]
        lash_parts.append(tube(f'{prefix}_Lash_{side}', points, radii, Mbrow, sides=6, cap=True))
    lashes = bc.join(lash_parts, f'{prefix}_Lashes')
    base['parts'].append(rigid(lashes, base, 'head'))
    Vhand, Fhand, wrist_loop = fb.build_hand_template(field, old_J, info, 1.)
    Vhand = (Vhand - info['Wr']) @ Rhand.T + Wrnew
    for sd, sign in (('l', 1), ('r', -1)):
        base['hand_axes'][sd] = tuple(Vector(a * np.array((sign, 1, 1))) for a in (X, T, D))
        base['armature'][f'hand_axes_{sd}'] = {'long': tuple(base['hand_axes'][sd][0]),
                                              'thumb': tuple(base['hand_axes'][sd][1]),
                                              'dorsal': tuple(base['hand_axes'][sd][2])}
        E, W = J[f'lowerarm_{sd}'], J[f'hand_{sd}']
        ts = (.38, .46, .56, .66, .76, .86, .94, 1.03)
        armpts = [E.lerp(W, t) for t in ts]
        # Ordered muscle/ulna taper, avoiding a cylindrical mannequin forearm.
        armrad = [(r * s, r * sy * s) for r, sy in ((.038, 1.08), (.037, 1.07), (.0355, 1.02), (.033, .98), (.0295, .97), (.026, .94), (.024, .91), (.023, .88))]
        forearm = tube(f'{prefix}_Forearm_{sd.upper()}', armpts, armrad, Mskin, sides=24, cap=False)
        base['parts'].append(bind(forearm, base, f'arm_{sd}'))
        vh = Vhand * np.array((sign, 1, 1)) * s
        fh = Fhand if sign == 1 else [tuple(reversed(f)) for f in Fhand]
        hand = mesh(f'{prefix}_Hand_{sd.upper()}', vh, fh, Mskin)
        hand['topology'] = 'joined palm/5 digits; 8-sided joint-loop quad template; known phalange chains'
        base['parts'].append(_hand_skin(hand, base, sd))
    for ob in base['parts']:
        if Mskin in ob.data.materials.values():
            attr = ob.data.color_attributes.get('FacePaint')
            if attr is None:
                attr = ob.data.color_attributes.new('FacePaint', 'FLOAT_COLOR', 'POINT')
                attr.data.foreach_set('color', np.ones(len(ob.data.vertices) * 4, dtype=np.float32))
                ob.data.color_attributes.active_color = attr
            # Warm painted skin, retaining the style-guide material base value.
            # It survives export as COLOR_0 and does not rely on studio light.
            tint = (.78, .62, .52) if prefix == 'KES' else (.93, .85, .78)
            for c in attr.data:
                rgba = list(c.color)
                c.color = (*(rgba[i] * tint[i] for i in range(3)), rgba[3])
    ec = _head_transform(info['eye_c'], s)
    eye_plane=_face_front([info['eye_c']],head_field)[0]
    eye_plane[1]-=.0008
    base['dims'] = {'height': height, 'skull_height': height, 'chin_z': 1.475 * s,
                    'head_center': (0, .004 * s, 1.588 * s), 'head_height': .225 * s,
                    'head_width': .148 * s, 'head_depth': .188 * s,
                    'eye_center_L': tuple(ec), 'eye_center_R': (-ec.x, ec.y, ec.z),
                    'eye_height': ec.z, 'eye_radius': info['eye_r'] * s,
                    'eye_front_y': _head_transform(eye_plane,s).y, 'shoulder_width': .400 * s,
                    'sole_z': 0., 'arm_angle_deg': 45., 'crotch_z': .800 * s,
                    'wrist_width': .055 * s, 'hand_length': .182 * s,
                    'body_tris': sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in base['parts'])}
    base['materials'].update(sclera=Mscl, iris=Miris, pupil=Mpup, brow=Mbrow)
    halo = socket(f'{prefix}_SOCKET_Halo', base, 'head', (0, .004 * s, height + .22))
    halo['use_position_only'] = True
    halo['halo_anchor_bone'] = 'head'
    halo['halo_offset_up_m'] = height + .22 - J['head'].z
    halo['note'] = 'Keep level in world; head position plus world-up offset'
    for sd, label in (('r', 'R'), ('l', 'L')):
        Xh, Th, Dh = base['hand_axes'][sd]
        web = (J[f'index_01_{sd}'] + J[f'thumb_02_{sd}']) * .5 - Dh * (.012 * s)
        sock = socket(f'{prefix}_SOCKET_Weapon{label}', base, f'hand_{sd}', web, yaxis=-Xh, zhint=Th)
        sock['note'] = 'Web-of-hand grip; local -Y muzzle along fingers; local +Z thumb side'
    socket(f'{prefix}_SOCKET_BackAbility', base, 'spine_03', (0, .135 * s, 1.290 * s))
    print(f'[character_v2] {prefix}: visible anatomy {base["dims"]["body_tris"]} tris, {len(base["armature"].data.bones)} common bones')
    return base


def reset_pose(arm):
    for b in arm.pose.bones:
        b.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def _world_rotate(arm, name, rotation):
    pb = arm.pose.bones[name]
    M = pb.matrix.copy()
    h = M.translation.copy()
    pb.matrix = Matrix.Translation(h) @ rotation @ Matrix.Translation(-h) @ M
    bpy.context.view_layer.update()


def aim(arm, name, toward, frac=1.):
    pb = arm.pose.bones[name]
    d, t = (pb.tail - pb.head).normalized(), Vector(toward).normalized()
    axis = d.cross(t)
    if axis.length > 1e-6:
        _world_rotate(arm, name, Matrix.Rotation(math.acos(max(-1., min(1., d.dot(t)))) * frac, 4, axis.normalized()))


def bend(arm, name, toward, degrees):
    pb = arm.pose.bones[name]
    axis = (pb.tail - pb.head).normalized().cross(Vector(toward))
    if axis.length > 1e-6:
        _world_rotate(arm, name, Matrix.Rotation(math.radians(degrees), 4, axis.normalized()))


def twist(arm, name, axis, degrees):
    _world_rotate(arm, name, Matrix.Rotation(math.radians(degrees), 4, Vector(axis).normalized()))


def pose(arm, name):
    """Static QA only; author no animations or actions."""
    reset_pose(arm)
    if name == 'idle':
        for sd in ('l', 'r'):
            bend(arm, f'upperarm_{sd}', (0, 0, -1), 33)
    elif name in ('rifle', 'aim'):
        aim(arm, 'upperarm_r', (-.25, -.65, -.40))
        aim(arm, 'lowerarm_r', (.35, -.65, .20))
        aim(arm, 'upperarm_l', (.25, -.65, -.35))
        aim(arm, 'lowerarm_l', (-.20, -.80, .20))
    elif name in ('zipline', 'hang'):
        aim(arm, 'upperarm_l', (.18, -.12, 1))
        aim(arm, 'lowerarm_l', (.12, -.15, 1))
        aim(arm, 'upperarm_r', (-.18, -.12, 1))
        aim(arm, 'lowerarm_r', (-.12, -.15, 1))
    elif name == 'crouch':
        bend(arm, 'spine_01', (0, -1, 0), 12)
        for sd in ('l', 'r'):
            bend(arm, f'thigh_{sd}', (0, -1, 0), 60)
            bend(arm, f'calf_{sd}', (0, 1, 0), 95)
    elif name == 'sprint':
        bend(arm, 'spine_01', (0, -1, 0), 14)
        bend(arm, 'thigh_l', (0, -1, 0), 48)
        bend(arm, 'calf_l', (0, 1, 0), 60)
        bend(arm, 'thigh_r', (0, 1, 0), 26)
        bend(arm, 'calf_r', (0, 1, 0), 55)
        aim(arm, 'upperarm_l', (.15, .4, -.7))
        aim(arm, 'upperarm_r', (-.15, -.4, -.7))
    elif name == 'fist':
        for sd in ('l', 'r'):
            hp = arm.pose.bones[f'hand_{sd}']
            hr = arm.data.bones[f'hand_{sd}']
            hand_rot = hp.matrix.to_3x3() @ hr.matrix_local.to_3x3().inverted()
            axes = arm.get(f'hand_axes_{sd}', {})
            palm = -(hand_rot @ Vector(axes.get('dorsal', (0, 0, 1))))
            for f in FINGERS:
                for k, deg in ((1, 50), (2, 70), (3, 40)):
                    b = arm.pose.bones[f'{f}_{k:02d}_{sd}']
                    axis = (b.tail - b.head).normalized().cross(palm)
                    if axis.length > 1e-6:
                        _world_rotate(arm, b.name, Matrix.Rotation(math.radians(deg), 4, axis.normalized()))
    bpy.context.view_layer.update()


def report(base, objects=None):
    prefix = base['prefix']
    obs = objects or [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.startswith(prefix + '_')]
    out = {'prefix': prefix, 'height_m': base['dims']['height'], 'bones': len(base['armature'].data.bones),
           'tris': 0, 'meshes': [], 'errors': []}
    deps = bpy.context.evaluated_depsgraph_get()
    for o in obs:
        ev = o.evaluated_get(deps)
        me = ev.to_mesh()
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        ev.to_mesh_clear()
        sums = [sum(g.weight for g in v.groups) for v in o.data.vertices]
        counts = [len(v.groups) for v in o.data.vertices]
        stats = {'name': o.name, 'vertices': len(o.data.vertices), 'tris': tris,
                 'uv': bool(o.data.uv_layers), 'max_influences': max(counts, default=0),
                 'unweighted': sum(v < .999 for v in sums), 'bad_sum': sum(abs(v - 1) > 1e-4 for v in sums)}
        if not stats['uv'] or stats['max_influences'] > 4 or stats['unweighted'] or stats['bad_sum']:
            out['errors'].append(o.name + ': skin/UV validation failed')
        out['meshes'].append(stats)
        out['tris'] += tris
    if out['tris'] > 70000:
        out['errors'].append('Character exceeds 70k hard triangle budget')
    return out


def export_character(base, path, objects=None):
    """Export selected meshes, common skeleton, bone-parented sockets, no clips."""
    reset_pose(base['armature'])
    path = str(Path(path).resolve())
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    prefix = base['prefix']
    obs = objects or [o for o in bpy.context.scene.objects if o.name.startswith(prefix + '_') and o.type in ('MESH', 'EMPTY', 'ARMATURE')]
    obs = list(obs)
    for sock in base.get('sockets', []):
        if sock not in obs:
            obs.append(sock)
    if base['armature'] not in obs:
        obs.append(base['armature'])
    qa = report(base, [o for o in obs if o.type == 'MESH'])
    Path(path + '_qa.json').write_text(json.dumps(qa, indent=2))
    if qa['errors']:
        raise RuntimeError('Character QA failed: ' + '; '.join(qa['errors']))
    bpy.ops.object.select_all(action='DESELECT')
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = base['armature']
    bpy.ops.export_scene.gltf(filepath=path + '.glb', export_format='GLB', use_selection=True,
                             export_apply=False, export_yup=True, export_animations=False,
                             export_skins=True, export_extras=True, export_all_influences=False)
    bpy.ops.export_scene.fbx(filepath=path + '.fbx', use_selection=True, axis_forward='-Z', axis_up='Y',
                            apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                            use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False,
                            path_mode='COPY', embed_textures=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=path + '.blend', compress=True)
    return qa
