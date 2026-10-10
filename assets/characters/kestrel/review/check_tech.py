"""Independent review: technical checks of KESTREL (read-only; writes nothing next to the asset).

blender -b --factory-startup -P check_tech.py
Loads kestrel.blend, then re-imports kestrel.glb and kestrel.fbx into fresh scenes, and prints facts.
"""
import math
import sys

sys.dont_write_bytecode = True
import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

A = r"F:/git/val etf/assets/characters/kestrel/"

UE5 = ["root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head"]
for s in ("l", "r"):
    UE5 += [f"clavicle_{s}", f"upperarm_{s}", f"lowerarm_{s}", f"hand_{s}", f"thigh_{s}", f"calf_{s}",
            f"foot_{s}", f"ball_{s}"]
    for f in ("thumb", "index", "middle", "ring", "pinky"):
        UE5 += [f"{f}_0{k}_{s}" for k in (1, 2, 3)]


def P(*a):
    print("[REV]", *a)


def tris(o):
    dg = bpy.context.evaluated_depsgraph_get()
    me = o.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    o.evaluated_get(dg).to_mesh_clear()
    return n


def world_co(o):
    co = np.zeros(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", co)
    mw = np.array(o.matrix_world)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def mesh_checks(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.transform(o.matrix_world)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    nonman = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    wire = sum(1 for e in bm.edges if e.is_wire)
    loose_v = sum(1 for v in bm.verts if not v.link_edges)
    degen = sum(1 for f in bm.faces if f.calc_area() < 1e-10)
    # islands
    seen = set()
    isl = []
    for v in bm.verts:
        if v.index in seen:
            continue
        st = [v]
        seen.add(v.index)
        cnt = 0
        while st:
            x = st.pop()
            cnt += 1
            for e in x.link_edges:
                y = e.other_vert(x)
                if y.index not in seen:
                    seen.add(y.index)
                    st.append(y)
        isl.append(cnt)
    isl.sort(reverse=True)
    P(f"{o.name}: verts {len(bm.verts)} faces {len(bm.faces)} boundary_edges {boundary} nonmanifold(>2 faces) {nonman}"
      f" wire {wire} loose_verts {loose_v} degenerate_faces {degen} islands {len(isl)} sizes(top10) {isl[:10]}"
      f" smallest {isl[-5:]}")
    # UVs
    uvl = bm.loops.layers.uv.active
    P(f"  uv layers: {[l.name for l in o.data.uv_layers]}")
    if uvl:
        zero_uv = 0
        out_uv = 0
        for f in bm.faces:
            uvs = [l[uvl].uv for l in f.loops]
            a = 0.0
            for i in range(1, len(uvs) - 1):
                a += abs((uvs[i] - uvs[0]).cross(uvs[i + 1] - uvs[0])) / 2
            if a < 1e-9:
                zero_uv += 1
            if any(u.x < -0.001 or u.x > 1.001 or u.y < -0.001 or u.y > 1.001 for u in uvs):
                out_uv += 1
        P(f"  faces with zero UV area {zero_uv}, faces with UVs outside 0-1 {out_uv}")
    # inside/outside heuristic for normals: ray parity from face centre along the normal
    bvh = BVHTree.FromBMesh(bm)
    rng = np.random.default_rng(1)
    faces = list(bm.faces)
    sel = rng.choice(len(faces), size=min(4000, len(faces)), replace=False)
    odd = 0
    for i in sel:
        f = faces[i]
        c = f.calc_center_median()
        n = f.normal
        if n.length < 0.5:
            continue
        origin = c + n * 1e-4
        hits = 0
        o2 = origin
        for _ in range(60):
            h = bvh.ray_cast(o2, n, 10.0)
            if h[0] is None:
                break
            hits += 1
            o2 = h[0] + n * 1e-4
        if hits % 2 == 1:
            odd += 1
    P(f"  normals: {odd}/{len(sel)} sampled faces have an odd number of surfaces in front of them "
      f"(points 'inward' if the shell were single and closed; TRELLIS double layers inflate this)")
    bm.free()


def weights_check(o, arm):
    bones = {b.name for b in arm.data.bones if b.use_deform}
    gnames = {g.index: g.name for g in o.vertex_groups}
    extra = [g.name for g in o.vertex_groups if g.name not in bones]
    infl = np.zeros(len(o.data.vertices), int)
    sums = np.zeros(len(o.data.vertices))
    for v in o.data.vertices:
        ws = [g.weight for g in v.groups if gnames[g.group] in bones and g.weight > 1e-6]
        infl[v.index] = len(ws)
        sums[v.index] = sum(ws)
    P(f"  {o.name}: vgroups {len(o.vertex_groups)} (non-bone groups {extra}), influences hist {np.bincount(infl)},"
      f" weight sum min {sums.min():.4f} max {sums.max():.4f}, unweighted {int((sums < 1e-6).sum())}")
    mods = [(m.type, getattr(m, 'object', None) and m.object.name) for m in o.modifiers]
    P(f"  modifiers: {mods}")


def rig_check(arm):
    names = [b.name for b in arm.data.bones]
    missing = [n for n in UE5 if n not in names]
    extra = [n for n in names if n not in UE5]
    P(f"armature {arm.name}: {len(names)} bones, missing UE5 {missing}, extra {extra}")
    P(f"  arm object loc {tuple(round(x, 4) for x in arm.location)} rot {tuple(round(x, 4) for x in arm.rotation_euler)} scale {tuple(round(x, 4) for x in arm.scale)}")
    nd = [b.name for b in arm.data.bones if not b.use_deform]
    P(f"  non-deform bones: {nd}")
    for b in arm.data.bones:
        P(f"  bone {b.name:12s} parent {b.parent.name if b.parent else None!s:12s} head {tuple(round(x, 3) for x in b.head_local)} tail {tuple(round(x, 3) for x in b.tail_local)} len {b.length:.3f} roll-z {tuple(round(x, 2) for x in b.z_axis)}")
    # mirror symmetry of the main chains
    for n in ["clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot", "ball"]:
        l, r = arm.data.bones[f"{n}_l"], arm.data.bones[f"{n}_r"]
        hl, hr = l.head_local, r.head_local
        tl, tr = l.tail_local, r.tail_local
        d = max((Vector((hl.x, hl.y, hl.z)) - Vector((-hr.x, hr.y, hr.z))).length,
                (Vector((tl.x, tl.y, tl.z)) - Vector((-tr.x, tr.y, tr.z))).length)
        # roll mirror: z axis of l should be mirror of r
        zl, zr = l.z_axis, r.z_axis
        dz = (Vector((zl.x, zl.y, zl.z)) - Vector((-zr.x, zr.y, zr.z))).length
        P(f"  mirror {n}: pos asym {d * 1000:.1f} mm, z-axis(roll) asym {dz:.3f}")


def socket_check(arm, body):
    co = world_co(body)
    top = co[:, 2].max()
    head_pts = co[co[:, 2] > 1.45]
    P(f"body world bbox min {co.min(0).round(4)} max {co.max(0).round(4)} height {co[:, 2].max() - co[:, 2].min():.4f}")
    P(f"head-region (z>1.45) x range {head_pts[:, 0].min():.3f}..{head_pts[:, 0].max():.3f} y range {head_pts[:, 1].min():.3f}..{head_pts[:, 1].max():.3f}")
    skull = co[co[:, 2] > 1.62]
    P(f"skull top (z>1.62) centre x {(skull[:, 0].min() + skull[:, 0].max()) / 2:.3f} y {(skull[:, 1].min() + skull[:, 1].max()) / 2:.3f}")
    for o in bpy.data.objects:
        if "SOCKET" in o.name:
            mw = o.matrix_world
            P(f"socket {o.name}: parent {o.parent and o.parent.name} type {o.parent_type} bone {o.parent_bone} world pos {tuple(round(x, 4) for x in mw.translation)}"
              f" X {tuple(round(x, 3) for x in mw.col[0][:3])} Y {tuple(round(x, 3) for x in mw.col[1][:3])} Z {tuple(round(x, 3) for x in mw.col[2][:3])}"
              f" keys {list(o.keys())}")
            if o.name.endswith("Halo"):
                P(f"  halo above top of hair: {mw.translation.z - top:.4f}")


def eyepiece_check(body, ep):
    dg = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(body, dg)
    me = ep.data
    co = world_co(ep)
    mats = [m.name for m in me.materials]
    for mi, mn in enumerate(mats):
        idx = set()
        for p in me.polygons:
            if p.material_index == mi:
                idx.update(p.vertices)
        idx = sorted(idx)
        if not idx:
            continue
        c = co[idx]
        d = []
        for p in c:
            h = bvh.find_nearest(Vector(p))
            d.append(h[3])
        d = np.array(d)
        P(f"eyepiece part {mn}: verts {len(idx)} bbox min {c.min(0).round(4)} max {c.max(0).round(4)} size {(c.max(0) - c.min(0)).round(4)}"
          f" dist to body: min {d.min() * 1000:.1f} mm median {np.median(d) * 1000:.1f} mm max {d.max() * 1000:.1f} mm")
    # inside test of strap verts: verts of graphite inside the body? (ray parity along +x)


def material_check():
    for m in bpy.data.materials:
        if m.users == 0:
            continue
        nt = m.node_tree
        info = []
        if nt:
            for n in nt.nodes:
                if n.type == "TEX_IMAGE" and n.image:
                    info.append(f"IMG {n.image.name} {n.image.size[:]} cs={n.image.colorspace_settings.name} packed={bool(n.image.packed_file)}")
                if n.type == "BSDF_PRINCIPLED":
                    vals = {}
                    for k in ("Roughness", "Metallic", "Alpha", "Emission Strength", "Specular IOR Level", "Coat Weight", "Transmission Weight"):
                        if k in n.inputs:
                            s = n.inputs[k]
                            vals[k] = "linked" if s.is_linked else round(float(s.default_value), 3)
                    info.append(f"BSDF {vals}")
        P(f"material {m.name}: blend {getattr(m, 'surface_render_method', None)} {info}")


def image_stats():
    for im in bpy.data.images:
        if not im.name.startswith("KES_"):
            continue
        w, h = im.size
        if w == 0:
            continue
        px = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, im.channels)
        st = [f"ch{c}: mean {px[..., c].mean():.3f} p1 {np.percentile(px[..., c], 1):.3f} p99 {np.percentile(px[..., c], 99):.3f}" for c in range(min(3, im.channels))]
        P(f"image {im.name} {w}x{h} ch {im.channels} {'; '.join(st)}")


# ------------------------------------------------------------------ 1. the .blend
bpy.ops.wm.open_mainfile(filepath=A + "kestrel.blend")
P("=== kestrel.blend")
for o in bpy.data.objects:
    P(f"object {o.name} type {o.type} parent {o.parent and o.parent.name} ptype {o.parent_type} pbone {o.parent_bone!r} "
      f"loc {tuple(round(x, 4) for x in o.location)} rot {tuple(round(x, 4) for x in o.rotation_euler)} scale {tuple(round(x, 4) for x in o.scale)}"
      f" data {o.data and o.data.name} mats {[s.material and s.material.name for s in o.material_slots]}")
arm = bpy.data.objects["KES_Armature"]
body = bpy.data.objects["KES_Body"]
ep = bpy.data.objects["KES_Eyepiece"]
P(f"tris body {tris(body)} eyepiece {tris(ep)} total {tris(body) + tris(ep)}")
mesh_checks(body)
mesh_checks(ep)
weights_check(body, arm)
weights_check(ep, arm)
rig_check(arm)
socket_check(arm, body)
eyepiece_check(body, ep)
material_check()
image_stats()
P(f"scene unit scale {bpy.context.scene.unit_settings.scale_length} system {bpy.context.scene.unit_settings.system}")
P(f"pose position {arm.data.pose_position}; any non-rest pose bones: {[pb.name for pb in arm.pose.bones if not pb.matrix_basis.is_identity] if hasattr(arm.pose.bones[0].matrix_basis, 'is_identity') else 'n/a'}")
P(f"actions {[a.name for a in bpy.data.actions]}; shape keys body {body.data.shape_keys}")

# ------------------------------------------------------------------ 2. the .glb re-import
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=A + "kestrel.glb")
P("=== kestrel.glb re-import")
for o in bpy.data.objects:
    P(f"glb object {o.name} type {o.type} parent {o.parent and o.parent.name} ptype {o.parent_type} pbone {o.parent_bone!r} dims {tuple(round(x, 3) for x in o.dimensions)}")
garm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
gbody = next(o for o in bpy.data.objects if o.type == "MESH" and "Body" in o.name)
P(f"glb armature bones {len(garm.data.bones)}; body verts {len(gbody.data.vertices)} tris {tris(gbody)}")
co = world_co(gbody)
P(f"glb body bbox min {co.min(0).round(4)} max {co.max(0).round(4)}")
for o in bpy.data.objects:
    if "SOCKET" in o.name:
        P(f"glb socket {o.name} world {tuple(round(x, 4) for x in o.matrix_world.translation)} Y {tuple(round(x, 3) for x in o.matrix_world.col[1][:3])} Z {tuple(round(x, 3) for x in o.matrix_world.col[2][:3])}")
P(f"glb images {[(i.name, i.size[:]) for i in bpy.data.images]}")
P(f"glb materials {[m.name for m in bpy.data.materials]}")

# ------------------------------------------------------------------ 3. the .fbx re-import
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=A + "kestrel.fbx")
P("=== kestrel.fbx re-import")
for o in bpy.data.objects:
    P(f"fbx object {o.name} type {o.type} parent {o.parent and o.parent.name} ptype {o.parent_type} pbone {o.parent_bone!r} scale {tuple(round(x, 4) for x in o.scale)} dims {tuple(round(x, 3) for x in o.dimensions)}")
farm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
fbody = next(o for o in bpy.data.objects if o.type == "MESH" and "Body" in o.name)
co = world_co(fbody)
P(f"fbx armature bones {len(farm.data.bones)} names-ok {sorted(b.name for b in farm.data.bones) == sorted(UE5)}; body bbox min {co.min(0).round(4)} max {co.max(0).round(4)}")
for o in bpy.data.objects:
    if "SOCKET" in o.name:
        P(f"fbx socket {o.name} world {tuple(round(x, 4) for x in o.matrix_world.translation)}")
P(f"fbx images {[(i.name, i.size[:], bool(i.packed_file)) for i in bpy.data.images]}")
P("done")
