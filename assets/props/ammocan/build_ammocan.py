"""Clean source-guided ammo-can reconstruction, Blender 5.2, standard glTF PBR.

Run from any working directory:
  blender --disable-autoexec -b --factory-startup -P build_ammocan.py

TRELLIS is a read-only silhouette/design reference, never a normal-bake source.
No packages beyond Blender's numpy are required. All generated files stay here.
"""
import bpy
import bmesh
import json
import hashlib
import math
import os
import struct
import shutil
import sys
import time
import zlib
from pathlib import Path

import numpy as np
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import blender_common as bc

SOURCE = Path("C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/output/valetf_c_ammocan_full_00001_.glb")
REFERENCE = ROOT / "assets/props/_tests/trellis2/inputs/PICK_c_ammocan.png"
TEX = HERE / "textures"
RENDERS = HERE / "renders"
START = time.time()
for p in (TEX, RENDERS):
    p.mkdir(parents=True, exist_ok=True)


def glb_document(path):
    raw=Path(path).read_bytes()
    assert raw[:4]==b"glTF"
    size,kind=struct.unpack("<II",raw[12:20])
    assert kind==0x4e4f534a
    return raw,json.loads(raw[20:20+size])


def document_summary(doc):
    primitives=[p for m in doc.get("meshes",[]) for p in m["primitives"]]
    return {"meshes":len(doc.get("meshes",[])),"primitives":len(primitives),
            "triangles":sum(doc["accessors"][p["indices"]]["count"]//3 for p in primitives if "indices" in p),
            "materials":len(doc.get("materials",[])),"images":len(doc.get("images",[])),
            "extensions_used":doc.get("extensionsUsed",[]),
            "all_primitives_uv0":all("TEXCOORD_0" in p["attributes"] for p in primitives),
            "node_transform_fields":{n.get("name",str(i)):{k:n[k] for k in ("matrix","translation","rotation","scale") if k in n}
                                      for i,n in enumerate(doc.get("nodes",[]))}}


def log(*args):
    print("[AMC]", *args, flush=True)


def read_png_rgb(path):
    """Read our library's 8-bit RGB PNGs with the standard library."""
    raw = Path(path).read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    pos, chunks = 8, []
    while pos < len(raw):
        size = struct.unpack(">I", raw[pos:pos+4])[0]
        typ = raw[pos+4:pos+8]
        data = raw[pos+8:pos+8+size]
        if typ == b"IHDR":
            w, h, bits, color, _, _, interlace = struct.unpack(">IIBBBBB", data)
        elif typ == b"IDAT":
            chunks.append(data)
        pos += size+12
    assert bits == 8 and color == 2 and interlace == 0
    scan = np.frombuffer(zlib.decompress(b"".join(chunks)), dtype=np.uint8).reshape(h, w*3+1)
    output = np.zeros((h, w*3), dtype=np.uint8)
    for y in range(h):
        row, f = scan[y, 1:].copy(), int(scan[y, 0])
        prev = output[y-1] if y else np.zeros(w*3, dtype=np.uint8)
        if f == 1:
            # Sub filter: one independent cumulative sum per colour channel.
            row = np.cumsum(row.reshape(w, 3), axis=0, dtype=np.uint32).astype(np.uint8).ravel()
        elif f == 2:
            row = (row.astype(np.uint16)+prev).astype(np.uint8)
        elif f in (3, 4):
            for x in range(w*3):
                a = int(row[x-3]) if x >= 3 else 0
                b = int(prev[x])
                c = int(prev[x-3]) if x >= 3 else 0
                if f == 3:
                    predictor = (a+b)//2
                else:
                    p = a+b-c
                    pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                    predictor = a if pa <= pb and pa <= pc else b if pb <= pc else c
                row[x] = (int(row[x])+predictor) & 255
        elif f != 0:
            raise ValueError("Unsupported PNG filter")
        output[y] = row
    return output.reshape(h, w, 3).astype(np.float32)/255


def write_png(path, data):
    data = np.clip(np.rint(data), 0, 255).astype(np.uint8)
    h, w, c = data.shape
    assert c == 3
    def chunk(typ, payload):
        return struct.pack(">I", len(payload))+typ+payload+struct.pack(">I", zlib.crc32(typ+payload)&0xffffffff)
    rows = b"".join(b"\x00"+row.tobytes() for row in data)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", struct.pack(">IIBBBBB", w,h,8,2,0,0,0))+
                           chunk(b"IDAT", zlib.compress(rows, 7))+chunk(b"IEND", b""))


def linear(srgb):
    return np.where(srgb <= .04045, srgb/12.92, ((srgb+.055)/1.055)**2.4)


def srgb(lin):
    return np.where(lin <= .0031308, lin*12.92, 1.055*np.maximum(lin, 0)**(1/2.4)-.055)


def paint_stencil(img, bone):
    """Large fictional geometric ammunition marking; no generated/real text."""
    h, w = img.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = xx/w, 1-yy/h
    # A simple split hexagonal cartridge emblem and three broken inventory bars.
    cx, cy = .40, .57
    ax, ay = np.abs(u-cx)/.075, np.abs(v-cy)/.11
    outer = (ax <= 1) & (ay <= 1) & (ax+ay*.5 <= 1.25)
    ix, iy = np.abs(u-cx)/.052, np.abs(v-cy)/.083
    inner = (ix <= 1) & (iy <= 1) & (ix+iy*.5 <= 1.25)
    mask = outer & ~inner & (np.abs(v-cy) > .010)
    for y, right in ((.66,.72),(.585,.77),(.51,.68)):
        bar = (u>.51) & (u<right) & (np.abs(v-y)<.017)
        bar &= ~((u>.555)&(u<.569))
        mask |= bar
    # Restrained stencil abrasion from the existing painted surface; no deep dirt.
    wear = np.mean(img, axis=2)
    mask &= ~((wear < np.quantile(wear,.12)) & ((xx+2*yy)%29 < 3))
    img[mask] = srgb(np.asarray(bone))
    return img


def make_material(key, color, rough, metal=0, library="worn_paint.png", mix=.35, label=False):
    src = linear(read_png_rgb(ROOT / "art/textures" / library))
    # Preserve the palette mean, while keeping the library's broad painted variation.
    factor = (1-mix)+mix*src
    rgb = srgb(np.clip(np.asarray(color)*factor/np.mean(factor, axis=(0,1)), 0, 1))
    if label:
        rgb = paint_stencil(rgb, (.55,.52,.46))
    albedo = TEX / f"AMC_{key}_basecolor.png"
    orm = TEX / f"AMC_{key}_orm.png"
    normal = TEX / "AMC_flat_normal.png"
    write_png(albedo, rgb*255)
    orm_data = np.empty((256,256,3), dtype=np.float32)
    luminance = src[::4,::4].mean(axis=2)
    orm_data[:,:,0] = 255
    orm_data[:,:,1] = np.clip(rough+(luminance-luminance.mean())*.09,0,1)*255
    orm_data[:,:,2] = metal*255
    write_png(orm, orm_data)
    if not normal.exists():
        write_png(normal, np.tile(np.array([128,128,255]),(4,4,1)))
    m = bpy.data.materials.new(f"M_AMC_{key}")
    m.use_nodes = True
    m.use_backface_culling = True
    m.diffuse_color = (*color,1)
    nt = m.node_tree
    bs = nt.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (1,1,1,1)
    bs.inputs["Metallic"].default_value = 1
    bs.inputs["Roughness"].default_value = 1
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(str(albedo), check_existing=True)
    t.image.colorspace_settings.name = "sRGB"
    nt.links.new(t.outputs["Color"],bs.inputs["Base Color"])
    o = nt.nodes.new("ShaderNodeTexImage")
    o.image = bpy.data.images.load(str(orm),check_existing=True)
    o.image.colorspace_settings.name = "Non-Color"
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(o.outputs["Color"],sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"],bs.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"],bs.inputs["Metallic"])
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(str(normal),check_existing=True)
    n.image.colorspace_settings.name = "Non-Color"
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(n.outputs["Color"],nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"],bs.inputs["Normal"])
    return m


def select(*obs):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in obs:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]


def finish(ob):
    select(ob)
    for modifier in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-8)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-10)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()
    # Geometry intentionally carries the chamfer. Hard primary planes stay flat.
    for p in ob.data.polygons:
        p.use_smooth = False
    return ob


def box(name,size,loc,mat,bevel=.003,segments=1):
    bevel=min(bevel,min(size)*.42)
    return bc.box("AMC_"+name,size,loc=loc,mat=mat,bevel=bevel,segments=segments,smooth=None)


def cylinder(name,radius,depth,loc,mat,rot=(90,0,0),verts=12):
    return bc.cylinder("AMC_"+name,radius,depth,loc=loc,rot=rot,verts=verts,mat=mat,
                       bevel=.001,segments=1,smooth=None)


def mesh(name, verts, faces, mats, indices=None):
    me=bpy.data.meshes.new("AMC_"+name)
    me.from_pydata(verts,[],faces)
    me.update()
    bm=bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob=bpy.data.objects.new("AMC_"+name,me)
    bpy.context.scene.collection.objects.link(ob)
    for m in mats:
        me.materials.append(m)
    if indices:
        for p,i in zip(me.polygons,indices):
            p.material_index=i
    return ob


def rounded_rect(w,d,c,z):
    return [(-w/2+c,-d/2,z),(w/2-c,-d/2,z),(w/2,-d/2+c,z),(w/2,d/2-c,z),
            (w/2-c,d/2,z),(-w/2+c,d/2,z),(-w/2,d/2-c,z),(-w/2,-d/2+c,z)]


def ring(name,w,d,thick,z0,z1,m,bevel=0):
    rings=[rounded_rect(w,d,.010,z0),rounded_rect(w,d,.010,z1),
           rounded_rect(w-2*thick,d-2*thick,.006,z1),rounded_rect(w-2*thick,d-2*thick,.006,z0)]
    verts=sum(rings,[])
    faces=[]
    for r in range(4):
        a,b=r*8,((r+1)%4)*8
        for i in range(8):
            j=(i+1)%8
            faces.append((a+i,a+j,b+j,b+i))
    ob=mesh(name,verts,faces,[m])
    if bevel:
        bc.add_bevel(ob,bevel,1)
    return ob


def shell():
    rings=[rounded_rect(.518,.220,.010,0), rounded_rect(.534,.236,.012,.009),
           rounded_rect(.534,.236,.012,.326), rounded_rect(.506,.208,.010,.326),
           rounded_rect(.506,.208,.010,.018)]
    verts=sum(rings,[])
    faces,indices=[],[]
    for r in range(4):
        for i in range(8):
            j=(i+1)%8
            faces.append((r*8+i,r*8+j,(r+1)*8+j,(r+1)*8+i))
            indices.append(1 if r>=2 else 2 if r==1 and i in (0,4) else 0)
    faces += [tuple(reversed(range(8))),tuple(range(32,40))]
    indices += [0,1]
    return mesh("Body_Shell",verts,faces,[OLIVE,INTERIOR,LABEL],indices)


ANGLE=math.radians(22)
LID_PIVOT=Vector((-.266,0,.335))
LID_MATRIX=Matrix.Rotation(-ANGLE,4,"Y")


def on_lid(ob):
    bpy.context.view_layer.update()
    ob.matrix_world=Matrix.Translation(LID_PIVOT) @ LID_MATRIX @ ob.matrix_world
    return ob


def bar_between(name,a,b,width,depth,mat):
    a,b=Vector(a),Vector(b)
    ob=box(name,(width,depth,(b-a).length),(a+b)/2,mat,.0015)
    ob.rotation_euler=(b-a).to_track_quat("Z","Y").to_euler()
    return ob


def end_loop():
    # A rigid stamped-steel rectangular bail, with cut corners and real thickness.
    outer=[(-.075,.106),(.075,.106),(.087,.117),(.087,.162),(.075,.175),
           (-.075,.175),(-.087,.162),(-.087,.117)]
    inner=[(-.070,.117),(.070,.117),(.075,.123),(.075,.156),(.069,.164),
           (-.069,.164),(-.075,.156),(-.075,.123)]
    verts=[]
    for x,points in ((.284,outer),(.293,outer),(.293,inner),(.284,inner)):
        verts += [(x,y,z) for y,z in points]
    faces=[]
    for r in range(4):
        for i in range(8):
            j=(i+1)%8
            faces.append((r*8+i,r*8+j,((r+1)%4)*8+j,((r+1)%4)*8+i))
    return mesh("End_Latch_Bail",verts,faces,[METAL])


def uv_all(obs):
    for ob in obs:
        select(ob)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66),island_margin=.025)
        bpy.ops.object.mode_set(mode="OBJECT")
        # The long body panels get one clean, intentional UV rectangle each.
        if ob.name=="AMC_Body_Shell":
            uv=ob.data.uv_layers.active.data
            for p in ob.data.polygons:
                if p.material_index==2:
                    for li in p.loop_indices:
                        v=ob.data.vertices[ob.data.loops[li].vertex_index].co
                        # Mirror the back so the fictional stencil faces outward correctly.
                        x=v.x if p.normal.y<0 else -v.x
                        uv[li].uv=(.045+.91*(x/.51+.5),.045+.91*((v.z-.009)/.317))


def bounds(obs):
    pts=[ob.matrix_world@Vector(p) for ob in obs for p in ob.bound_box]
    mn=[min(p[i] for p in pts) for i in range(3)]
    mx=[max(p[i] for p in pts) for i in range(3)]
    return {"min":[round(v,6) for v in mn],"max":[round(v,6) for v in mx],
            "size":[round(mx[i]-mn[i],6) for i in range(3)]}


def qa(obs):
    rows=[]
    for ob in obs:
        me=ob.data
        me.calc_loop_triangles()
        bm=bmesh.new();bm.from_mesh(me)
        # glTF vertices split at hard normals and UV seams; inspect welded-position
        # topology on a disposable BMesh, retaining the imported render mesh unchanged.
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
        boundary=sum(e.is_boundary for e in bm.edges)
        nonmanifold=sum(not e.is_manifold for e in bm.edges)
        bm.free()
        rows.append({"name":ob.name,"triangles":len(me.loop_triangles),"vertices":len(me.vertices),
                     "uv_layers":len(me.uv_layers),"boundary_edges":boundary,"nonmanifold_edges":nonmanifold,
                     "identity_transform":all(abs(ob.matrix_world[i][j]-(1 if i==j else 0))<1e-6 for i in range(4) for j in range(4)),
                     "materials":[m.name for m in me.materials],
                     "degenerate_triangles":sum(t.area<1e-12 for t in me.loop_triangles)})
    return {"triangles":sum(r["triangles"] for r in rows),"vertices":sum(r["vertices"] for r in rows),
            "mesh_objects":len(rows),"boundary_edges":sum(r["boundary_edges"] for r in rows),
            "nonmanifold_edges":sum(r["nonmanifold_edges"] for r in rows),
            "all_uvs":all(r["uv_layers"]>0 for r in rows),"all_identity_transforms":all(r["identity_transform"] for r in rows),
            "degenerate_triangles":sum(r["degenerate_triangles"] for r in rows),
            "topology_measurement":"Welded coincident positions at 1e-7 m on disposable BMesh; UV/hard-normal splits remain in export",
            "bounds_blender_z_up_m":bounds(obs),"objects":rows}


bc.reset_scene()
OLIVE=make_material("Olive_Paint",(.10,.125,.067),.64)
LID=make_material("Lid_Paint",(.12,.145,.080),.61)
INTERIOR=make_material("Interior_Paint",(.068,.075,.048),.73,mix=.25)
LABEL=make_material("Olive_Stencil",(.10,.125,.067),.64,label=True)
METAL=make_material("Steel",(.11,.115,.12),.43,.72,"brushed_metal.png",.30)
POLYMER=make_material("Grip",(.030,.034,.031),.69,0,"polymer_stipple.png",.40)
ACCENT=make_material("Ochre_Mark",(.38,.275,.085),.67,mix=.25)
BODY=shell()
ring("Top_Rim",.548,.250,.017,.318,.338,LID,.002)
ring("Base_Rolled_Edge",.540,.242,.017,.006,.026,OLIVE,.002)
# Raised regular facets at the four corners; broad panels remain a single plane.
for x in (-1,1):
    for y in (-1,1):
        box(f"Corner_{x}_{y}",(.014,.015,.282),(x*.260,y*.113,.165),LID,.003)

on_lid(box("Lid_Panel",(.550,.255,.022),(.275,0,.009),LID,.007,2))
on_lid(box("Lid_Underside_Recess",(.503,.205,.008),(.276,0,-.005),INTERIOR,.005))
# Clean gasket seat creates a crisp lid edge without a baked wavy normal.
on_lid(box("Lid_Gasket",(.519,.222,.006),(.275,0,-.009),POLYMER,.004))
for x in (.095,.452):
    on_lid(box(f"Handle_Mount_{x}",(.054,.067,.009),(x,0,.024),METAL,.003))
    for y in (-.024,.024):
        a=(x,y,.028)
        b=(.152 if x<.2 else .395,y,.052)
        on_lid(bar_between(f"Handle_Arm_{x}_{y}",a,b,.010,.010,METAL))
for y in (-.024,.024):
    on_lid(box(f"Handle_Rail_{y}",(.243,.010,.010),(.2735,y,.052),METAL,.002))
on_lid(box("Handle_Grip",(.199,.057,.014),(.274,0,.057),POLYMER,.006,2))
for y in (-.070,.070):
    cylinder(f"Hinge_Barrel_{y}",.010,.054,(-.270,y,.330),METAL)
    box(f"Hinge_Body_Leaf_{y}",(.012,.046,.042),(-.268,y,.303),OLIVE,.002)
    on_lid(box(f"Hinge_Lid_Leaf_{y}",(.041,.047,.005),(.022,y,-.006),METAL,.002))
# End closure assembly: regular pressed plate, cap bar, bail and standoff pivots.
box("Latch_Plate",(.010,.161,.162),(.273,0,.222),OLIVE,.006)
box("Latch_Cap",(.021,.181,.023),(.276,0,.311),LID,.005)
box("Latch_Recess",(.004,.104,.028),(.280,0,.265),INTERIOR,.002)
box("Latch_Thumb_Tab",(.011,.089,.019),(.285,0,.269),METAL,.002)
for y in (-.070,.070):
    box(f"Latch_Link_{y}",(.010,.012,.147),(.284,y,.238),METAL,.002)
    cylinder(f"Latch_Pivot_{y}",.008,.009,(.287,y,.180),METAL,rot=(0,90,0),verts=10)
end_loop()
box("Latch_Safety_Mark",(.002,.049,.014),(.279,0,.204),ACCENT,.001)

ASSET=[o for o in bpy.context.scene.objects if o.type=="MESH"]
for ob in ASSET:
    finish(ob)
uv_all(ASSET)
source_bytes,source_doc=glb_document(SOURCE)
frozen_reference=HERE/"reference"/"PICK_c_ammocan.png"
frozen_reference.parent.mkdir(exist_ok=True)
if not frozen_reference.exists():
    shutil.copyfile(REFERENCE,frozen_reference)
QA={"asset":"ammocan","method":"Source-guided hard-surface reconstruction; no source triangles or baked source normals retained",
    "source_read_only":str(SOURCE),"source_sha256":hashlib.sha256(source_bytes).hexdigest(),
    "source_document":document_summary(source_doc),"reference":str(frozen_reference),
    "texture_sources":["art/textures/worn_paint.png","art/textures/brushed_metal.png","art/textures/polymer_stipple.png"],
    "pbr":{"basecolor":"sRGB","normal":"OpenGL tangent-space flat, no TRELLIS normal bake","orm":"linear: R=1 unoccluded, G=roughness, B=metallic"},
    "built":qa(ASSET)}
assert QA["built"]["triangles"]<=5000
assert QA["built"]["all_uvs"] and QA["built"]["all_identity_transforms"]
assert QA["built"]["nonmanifold_edges"]==0
assert QA["built"]["degenerate_triangles"]==0
log("built",QA["built"]["triangles"],"triangles")

# A small-prop studio rig: scale the standard human-scale light distances and energy.
scene=bpy.context.scene
bc.setup_studio(scene,floor=True)
for ob in bpy.data.objects:
    if ob.type=="LIGHT":
        ob.location*=.33
        ob.data.energy*=.109
        ob.data.size*=.33
        ob.rotation_euler=(Vector((0,0,.26))-ob.location).to_track_quat("-Z","Y").to_euler()
scene.view_settings.view_transform="AgX"
scene.view_settings.look="AgX - Medium High Contrast"
views=("front","right","back","three_quarter","three_quarter_back","top")
paths=bc.render_views(str(RENDERS),"ammocan",objs=ASSET,views=views,res=(1000,1000),samples=48,ortho=True,margin=1.10)
bc.contact_sheet(paths,str(RENDERS/"contact_sheet.png"),cols=3)

# Material-free check: deliberate chamfers rather than a normal-map illusion.
clay=bc.material("_QA_Clay",(.35,.37,.40),rough=.7)
scene.view_layers[0].material_override=clay
bc.render_views(str(RENDERS),"clay",objs=ASSET,views=("three_quarter",),res=(1000,1000),samples=32,ortho=True,margin=1.1)
scene.view_layers[0].material_override=None

base=str(HERE/"ammocan")
# Preserve individual editable parts in .blend, but reduce the engine asset to one
# mesh/seven material primitives. This avoids 35 tiny object submissions.
export_parts=[]
for ob in ASSET:
    clone=ob.copy();clone.data=ob.data.copy()
    bpy.context.scene.collection.objects.link(clone)
    export_parts.append(clone)
select(*export_parts)
bpy.ops.object.join()
EXPORT=bpy.context.view_layer.objects.active
EXPORT.name="AMC_AmmoCan"
EXPORT.data.name="AMC_AmmoCan"
select(EXPORT)
bpy.ops.export_scene.gltf(filepath=base+".glb",export_format="GLB",use_selection=True,
                          export_apply=True,export_yup=True,export_normals=True,export_tangents=True)
bpy.ops.export_scene.fbx(filepath=base+".fbx",use_selection=True,axis_forward="-Z",axis_up="Y",
                         apply_unit_scale=True,apply_scale_options="FBX_SCALE_ALL",use_mesh_modifiers=True,
                         mesh_smooth_type="FACE",path_mode="COPY",embed_textures=True,object_types={"MESH"},
                         bake_anim=False)
bpy.data.objects.remove(EXPORT,do_unlink=True)
QA["export_document"]=document_summary(glb_document(base+".glb")[1])
export_doc=glb_document(base+".glb")[1]
QA["export_materials"]=[{"name":m["name"],"basecolor_texture":"baseColorTexture" in m.get("pbrMetallicRoughness",{}),
                         "metallic_roughness_texture":"metallicRoughnessTexture" in m.get("pbrMetallicRoughness",{}),
                         "normal_texture":"normalTexture" in m,"double_sided":m.get("doubleSided",False)}
                        for m in export_doc.get("materials",[])]
b=QA["built"]["bounds_blender_z_up_m"]
QA["bounds_gltf_y_up_m"]={"min":[b["min"][0],b["min"][2],-b["max"][1]],
                          "max":[b["max"][0],b["max"][2],-b["min"][1]],
                          "size":[b["size"][0],b["size"][2],b["size"][1]]}
QA["pivot"]="Identity mesh node at body-centre ground level; Blender Z=0 / glTF Y=0"
assert all(not v for v in QA["export_document"]["node_transform_fields"].values())
assert QA["export_document"]["all_primitives_uv0"]
assert all(m["basecolor_texture"] and m["metallic_roughness_texture"] and m["normal_texture"] for m in QA["export_materials"])
for im in bpy.data.images:
    if im.filepath and Path(bpy.path.abspath(im.filepath)).is_relative_to(TEX):
        im.filepath=bpy.path.relpath(im.filepath,start=str(HERE))
bpy.ops.wm.save_as_mainfile(filepath=base+".blend")

# Fresh scene/import checks: inspect actual exports, not the authoring meshes.
bc.reset_scene()
bpy.ops.import_scene.gltf(filepath=base+".glb",merge_vertices=True)
IMPORTED=[o for o in bpy.context.scene.objects if o.type=="MESH"]
QA["fresh_glb_import"]=qa(IMPORTED)
QA["fresh_glb_import"]["material_names"]=sorted({s.material.name for o in IMPORTED for s in o.material_slots if s.material})
log("fresh GLB", QA["fresh_glb_import"]["triangles"], "built", QA["built"]["triangles"])
(HERE/"QA.json").write_text(json.dumps(QA,indent=2))
assert QA["fresh_glb_import"]["triangles"]==QA["built"]["triangles"]
assert QA["fresh_glb_import"]["all_uvs"] and QA["fresh_glb_import"]["all_identity_transforms"]
assert QA["fresh_glb_import"]["nonmanifold_edges"]==0
bc.setup_studio(floor=True)
for ob in bpy.data.objects:
    if ob.type=="LIGHT":
        ob.location*=.33;ob.data.energy*=.109;ob.data.size*=.33
        ob.rotation_euler=(Vector((0,0,.26))-ob.location).to_track_quat("-Z","Y").to_euler()
bc.render_views(str(RENDERS),"imported_glb",objs=IMPORTED,views=("three_quarter",),res=(1000,1000),samples=48,ortho=True,margin=1.1)
bc.reset_scene()
bpy.ops.import_scene.fbx(filepath=base+".fbx")
QA["fresh_fbx_import"]=qa([o for o in bpy.context.scene.objects if o.type=="MESH"])
assert QA["fresh_fbx_import"]["triangles"]==QA["built"]["triangles"]
assert QA["fresh_fbx_import"]["all_uvs"]
QA["wall_seconds"]=round(time.time()-START,2)
(HERE/"QA.json").write_text(json.dumps(QA,indent=2))
log("Done",QA["wall_seconds"],"seconds")
