"""Showhome suburb backdrop: continue the existing ground skirt, using the existing house/prop kit helpers.

Run Blender 5.2 -b --factory-startup -P this_file. Geometry exports only; integrated lighting/sky/renders
are built separately. Every mesh has world-metre UVs, COLOR_0 and one of ten shared painted PBR materials.
Design frame: X east, Y north, Z up; exporter writes glTF Y-up (x,z,-y), loaded at identity.
"""
import json
import math
import os
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(r"F:/git/val etf")
SH = ROOT / "assets/maps/showhome"
OUT = SH / "backdrop"
V2 = SH / "textures/v2"
sys.path[:0] = [str(ROOT / "tools"), str(SH)]
import blender_common as bc
import props_lib as PL

# Reuse the actual kit's accumulator, UVs, bevels, exact 4 cm print beads and material exporter nodes.
# The architecture module's build/render main is deliberately excluded from this namespace.
HH = {}
source = (SH / "build_houses.py").read_text(encoding="utf-8").split("\ndef main():")[0]
exec(compile(source, str(SH / "build_houses.py"), "exec"), HH)
Acc, box, uv_box = HH["Acc"], HH["box"], HH["uv_box"]
bead_ribbon, make_object = HH["bead_ribbon"], HH["make_object"]
V = Vector
T0 = time.time()
RNG = random.Random(8112026)
MAN = json.loads((V2 / "manifest.json").read_text(encoding="utf-8"))["materials"]
PALETTE = HH["PALETTE"]
COL = {
    "sage": tuple(v / .70 for v in PALETTE["fibercement_sage"]["albedo_linear"]),
    "clay": tuple(v / .70 for v in PALETTE["fibercement_clay"]["albedo_linear"]),
    "yellow": tuple(v / .70 for v in PALETTE["crane_yellow"]["albedo_linear"]),
    "cream": (1.0, .94, .82), "white": (1.0, 1.0, 1.0),
    "dark": (.042, .044, .057), "glass": (.060, .080, .125), "tree": (.47, .38, .43),
}
TEXTURES = dict(printed="printed_concrete_layers", clad="fibercement_panel", roof="roof_shingle_dark",
                solar="solar_panel", timber="timber_pallets", earth="worksite_packed_dirt",
                foliage="grass_lawn", metal="metal_scaffold_tube", pave="paving_slabs", asphalt="asphalt")
REPEAT = {k: MAN.get(v, {}).get("repeat_m", 1.0) for k, v in TEXTURES.items()}
REPEAT["solar"] = 1.0
ALL = []
ROOTS = {}


def log(*a):
    print(f"[backdrop {time.time()-T0:5.1f}s]", *a, flush=True)


def materials():
    result = {}
    for key, family in TEXTURES.items():
        src = V2 if family != "solar_panel" else SH / "textures"
        base = src / (family + ".png")
        normal, orm = src / (family + "_normal.png"), src / (family + "_orm.png")
        m = HH["make_mat"]("M_SHB_" + key.title(), str(base),
                           rough=.78 if key not in ("metal", "solar") else .48,
                           metal=.72 if key == "metal" else 0.0,
                           normal=str(normal) if normal.exists() else None,
                           nstr=.16 if key in ("foliage", "printed") else .6,
                           orm=str(orm) if orm.exists() else None)
        m["metres_per_repeat"] = REPEAT[key]
        result[key] = m
    return result


def B(a, mn, mx, mat="clad", col=COL["white"], skip=()):
    box(a, mn, mx, mat, col, uv_box(REPEAT[mat]), skip=skip)


def primitive(a, label, callback, mat, col=COL["white"], face_jitter=0.0):
    """Use the existing props bmesh primitives, then preserve our explicit per-material mesh/UV convention."""
    prop = PL.Prop(label)
    callback(prop)
    prop.bm.normal_update()
    for i, face in enumerate(prop.bm.faces):
        value = 1.0 + face_jitter * math.sin(i * 2.31)
        tint = tuple(min(1.0, c * value) for c in col)
        a.poly([v.co.copy() for v in face.verts], mat, uv_box(REPEAT[mat]), tint, want=face.normal)
    prop.bm.free()


def cyl(a, p0, p1, radius, mat="metal", col=COL["white"], n=10):
    primitive(a, "Cylinder", lambda p: p.cyl(p0, p1, radius, mat, n=n), mat, col)


def bar(a, p0, p1, width, depth, mat="metal", col=COL["white"], bevel=0):
    primitive(a, "Bar", lambda p: p.bar(p0, p1, width, depth, mat, bev=bevel), mat, col)


def cable(a, p0, p1, sag=.65, radius=.020, mat="metal", col=(.21,.21,.22), samples=16):
    pts = PL.catenary(p0, p1, sag, samples)
    primitive(a, "Cable", lambda p: p.tube(pts, radius, mat, n=5), mat, col)


def part(ring, name, callback, note=""):
    acc = Acc()
    callback(acc)
    col = bc.collection("SHB_" + ring)
    for mat in sorted({p[1] for p in acc.P}):
        one = Acc(); one.P = [p for p in acc.P if p[1] == mat]
        obj = make_object("SHB_" + ring + "_" + name + "_" + mat, one, MATS, col)
        obj.parent = ROOTS[ring]
        obj["ring"] = ring
        obj["render_only"] = True
        obj["cast_shadows"] = ring != "Far"
        obj["part"] = name
        obj["note"] = note
        ALL.append(obj)


def printed_box(a, mn, mx):
    """Printed exterior ribbons retain the house kit's real, precisely aligned grooves."""
    x0,y0,z0 = mn; x1,y1,z1 = mx
    for pa, pb, n in (((x0,y0),(x1,y0),(0,-1)), ((x1,y0),(x1,y1),(1,0)),
                      ((x1,y1),(x0,y1),(0,1)), ((x0,y1),(x0,y0),(-1,0))):
        if (V(pb)-V(pa)).length < .5:
            # Thin wall returns/block ends use the exact bead normal/height sheet; keep full geometry on
            # the broad faces visible from the map instead of spending courses on 25 cm hidden ends.
            a.poly([(pa[0],pa[1],z0),(pb[0],pb[1],z0),(pb[0],pb[1],z1),(pa[0],pa[1],z1)],
                   "printed",uv_box(1.28),want=(n[0],n[1],0))
        else:
            bead_ribbon(a, [(pa,n,n),(pb,n,n)], z0,z1, mat="printed")
    B(a, mn, mx, "printed", skip=((0,-1),(0,1),(1,-1),(1,1)))


def pallet(a, x, y, z=0, blocks=True):
    for yy in (-.40, 0, .40):
        B(a,(x-.62,y+yy-.055,z+.04),(x+.62,y+yy+.055,z+.15),"timber")
    for i in range(5):
        xx=x-.58+i*.26
        B(a,(xx,y-.48,z+.15),(xx+.17,y+.48,z+.21),"timber")
    if blocks:
        for row in range(2):
            for xx in (-.32,.32):
                for yy in (-.23,.23):
                    # Layered printed blocks share the exact concrete helper used on the playable houses.
                    printed_box(a,(x+xx-.28,y+yy-.18,z+.21+row*.23),
                                   (x+xx+.28,y+yy+.18,z+.43+row*.23))
        for xx in (-.50,.50):
            B(a,(x+xx-.012,y-.51,z+.2),(x+xx+.012,y+.51,z+.69),"clad",(.31,.36,.39))


def stakes(a, x0,y0,x1,y1):
    for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):
        B(a,(x-.035,y-.035,.0),(x+.035,y+.035,.65),"timber")
        B(a,(x-.04,y-.04,.52),(x+.04,y+.04,.60),"clad",COL["yellow"])
    for pa,pb in (((x0,y0,.53),(x1,y0,.53)),((x1,y0,.53),(x1,y1,.53)),
                  ((x1,y1,.53),(x0,y1,.53)),((x0,y1,.53),(x0,y0,.53))):
        cable(a,pa,pb,.035,.006,"clad",(.92,.75,.39),samples=8)


def scaffold(a, x0,y0,x1,y1,height):
    zlevels=[.35]+[1.4*k for k in range(1,math.ceil(height/1.4))]+[height]
    for y in (y0-.65,y1+.65):
        xs=[x0-.6 + k*(x1-x0+1.2)/6 for k in range(7)]
        for x in xs:
            cyl(a,(x,y,.05),(x,y,height+.15),.032,n=8)
            B(a,(x-.12,y-.12,.0),(x+.12,y+.12,.055),"metal")
        for z in zlevels:
            cyl(a,(xs[0],y,z),(xs[-1],y,z),.030,n=6)
        for i in range(len(xs)-1):
            for lo,hi in zip(zlevels,zlevels[1:]):
                cyl(a,(xs[i],y,lo),(xs[i+1],y,hi),.024,n=6)
        for z in zlevels[1:-1]:
            for k in range(3):
                B(a,(xs[0],y-.33+k*.20,z-.055),(xs[-1],y-.17+k*.20,z),"timber")
    # Closed raking planks and outward facing ladder retain the site's believable construction silhouette.
    for x in (x0-.6,x1+.6):
        for z in zlevels:
            cyl(a,(x,y0-.65,z),(x,y1+.65,z),.029,n=8)


def shell(a, x,y,w,d,height,stage):
    B(a,(x-.25,y-.25,-.015),(x+w+.25,y+d+.25,.20),"clad",(.88,.84,.75))
    # The openings face the outside streets; a solid rear wall faces Showhome.
    thick=.25
    printed_box(a,(x,y,.2),(x+thick,y+d,height))
    printed_box(a,(x+w-thick,y,.2),(x+w,y+d,height))
    printed_box(a,(x,y+d-thick,.2),(x+w,y+d,height))
    frontpieces=((x,x+2.1),(x+3.5,x+6.0),(x+7.6,x+w)) if w>=9 else ((x,x+2),(x+3.5,x+w))
    for xa,xb in frontpieces:
        printed_box(a,(xa,y,.2),(xb,y+thick,height))
    if height>2.6:
        printed_box(a,(x,y,2.5),(x+w,y+thick,min(height,2.9)))
    if stage>=2:
        B(a,(x+.25,y+.25,3.03),(x+w-.25,y+d-.25,3.18),"clad",(.9,.85,.78))
        # Shorter upper return is a visible partially printed layer, rather than a finished box.
        printed_box(a,(x+.25,y+d-.5,3.18),(x+w-.25,y+d-.25,height))
    for xa in (x+.4,x+w-.4):
        for ya in (y+.4,y+d-.4):
            cyl(a,(xa,ya,height-.12),(xa,ya,height+.65),.022,n=8)
    if stage>0:
        scaffold(a,x,y,x+w,y+d, min(6.5,height+.6))
    pallet(a,x+w+1.5,y+1.8)
    pallet(a,x+w+1.5,y+4.0,blocks=stage!=0)


def tree(a,x,y,height,seed,hero=False,cypress=False,lod=False):
    r=random.Random(seed)
    stem=height*.36
    cyl(a,(x,y,.03),(x,y,stem+.75),.16 if height>6 else .11,"timber",(.48,.40,.30),n=10)
    if cypress:
        count=4 if lod else 6
        for k in range(count):
            kk=k*7/(count-1)
            z=height*(.24+.083*kk)
            radius=height*(.145-.011*kk)
            primitive(a,"Cypress",lambda p,z=z,radius=radius,k=k:
                p.blob((x,y,z),radius,"foliage",scale=(.66,.62,1.32),sub=2,amp=.09,seed=seed+k),
                "foliage",(.43,.38,.40),.045)
    else:
        crown=height*.38
        centres=[(0,0,.14),(-.52,-.2,-.04),(.47,-.22,.08),(-.28,.48,.14),
                 (.26,.4,-.06),(-.24,-.52,.27),(.15,.08,.57),(.57,.24,.3),(-.6,.23,.32)]
        for k,(dx,dy,dz) in enumerate(centres[:4] if lod else centres):
            c=(x+dx*crown,y+dy*crown,stem+crown*(.85+dz))
            rad=crown*(.46+r.random()*.10)
            primitive(a,"Canopy",lambda p,c=c,rad=rad,k=k:
                p.blob(c,rad,"foliage",scale=(1.0,.9,1.05),sub=3 if hero else 2,amp=.08,seed=seed+k),
                "foliage",tuple(v*(.96+.08*r.random()) for v in COL["tree"]),.045)
            if k in (1,2,3,4):
                cyl(a,(x,y,stem*.85),(c[0],c[1],c[2]-.3),.075,"timber",(.42,.36,.29),n=6)


def hedge(a,p0,p1,height=1.7):
    p0,p1=V(p0),V(p1);d=p1-p0;length=d.length;u=d/length;side=V((-u.y,u.x,0))
    # Simple solid green shapes are intentional until the game's foliage-card technique is settled.
    for i in range(math.ceil(length/2)):
        c=p0+u*min(length-.9,1+i*2);c.z=height*.48
        primitive(a,"Hedge",lambda p,c=c:p.blob(c,1,"foliage",scale=(1.0,.52,height*.48),sub=2,amp=.06),
                  "foliage",(.45,.43,.42),.03)


def pickets(a,x0,x1,y,height=1.15):
    for i in range(math.ceil((x1-x0)/.30)+1):
        x=min(x1,x0+i*.30)
        primitive(a,"Picket",lambda p,x=x:p.prism([(x-.075,0),(x+.075,0),(x+.075,height-.12),(x,height),(x-.075,height-.12)],
                          y-.035,y+.035,"clad",axis="Y"),"clad",COL["cream"])
    for z in (.30,.80):
        B(a,(x0,y-.07,z),(x1,y+.02,z+.07),"clad",COL["cream"])


def pole(a,x,y,height=7.1):
    B(a,(x-.11,y-.11,0),(x+.11,y+.11,height),"clad",(.54,.52,.47))
    B(a,(x-.62,y-.08,height-.38),(x+.62,y+.08,height-.25),"metal")
    for dx in (-.47,0,.47):
        cyl(a,(x+dx,y,height-.25),(x+dx,y,height+.08),.06,"clad",(.76,.75,.73),n=8)


def near(a):
    for x,y,w,d,h,stage in ((18,66,10,10,1.1,0),(-28,20,10,12,3.15,1),(90,18,11,12,5.6,2)):
        shell(a,x,y,w,d,h,stage)
        stakes(a,x-.8,y-.8,x+w+.8,y+d+.8)
    for x0,y0,x1,y1 in ((-8,66,6,80),(43,66,56,79),(-28,65,-16,78),(88,62,101,74),(-27,-33,-12,-21),(91,-33,106,-21)):
        stakes(a,x0,y0,x1,y1)
        pallet(a,x0+1.4,y0+1.8)
        primitive(a,"DirtMound",lambda p,x0=x0,y0=y0:p.blob((x0+5,y0+5,.22),1.9,"earth",scale=(1.9,1.2,.30),sub=2,amp=.14),"earth")
    # Low fencing near the boundary never implies an opening through the existing hedge/clip.
    pickets(a,2,70,49.15,1.15)
    pickets(a,-35,22,-19,1.2);pickets(a,50,107,-19,1.2)
    hedge(a,(2,63,0),(12,63,0));hedge(a,(53,63,0),(72,63,0))
    # No new ground inside the existing skirt. These footprints sit on its actual dirt/grass/paving zones.
    for i,(x,y) in enumerate([(-18,8),(-20,18),(-17,41),(90,8),(92,40),(96,45),
                              (4,66),(39,68),(69,69),(-25,-29),(10,-28),(61,-29),
                              (84,-28),(-32,12),(-32,43),(106,12),(105,44),(21,82),
                              (55,83),(-10,78),(82,79),(-12,-40),(30,-37),(48,-38),(84,-39),(3,79)]):
        tree(a,x,y,6.7+(i%3)*.40,900+i)
    for i,(x,y) in enumerate([(-17,28),(-33,30),(91,31),(106,30),(9,70),(63,73),
                              (-12,-25),(24,-25),(48,-25),(83,-25),(-21,73),(94,72)]):
        tree(a,x,y,7.5+(i%2)*.45,1200+i,cypress=True)
    # Map pylon axes continue north; all new cable vertices begin outside the 1 m clearance.
    for x in (25,47):
        pole(a,x,67,7.0)
        cable(a,(x,54.1,6.3),(x,67,6.75),.50)
    cable(a,(25,67,6.75),(47,67,6.75),.85)
    for x in (-22,94):
        for y in (3,28,54,78):
            pole(a,x,y,7.0)
        for y0,y1 in ((3,28),(28,54),(54,78)):
            cable(a,(x,y0,6.75),(x,y1,6.75),.95)
    # Original abstract banner: printing-layer stair icon, ochre band and sage/clay blocks; no text/logo.
    for x in (80,96):
        cyl(a,(x,64,0),(x,64,2.25),.045,n=10)
    # Real corrugated backing panels share the galvanised material; no extra material or transparency.
    for k in range(128):
        xa,xb=80+k*.125,80+(k+1)*.125
        ya,yb=64.10+(.027 if k%2 else -.027),64.10+(-.027 if k%2 else .027)
        a.poly([(xa,ya,.06),(xb,yb,.06),(xb,yb,2.1),(xa,ya,2.1)],"metal",uv_box(REPEAT["metal"]),
               (.76,.77,.79),want=(0,-1,0))
    bar(a,(80,64.1,2.13),(96,64.1,2.13),.04,.05)
    B(a,(80,63.975,.55),(96,64.025,2.1),"clad",(.90,.86,.74))
    for i in range(6):
        B(a,(81+i*.25,63.962,.70+i*.15),(84.2,63.970,.83+i*.15),"clad",COL["yellow"])
    for x,c in ((87,COL["sage"]),(90,COL["clay"])):
        B(a,(x,63.958,.82),(x+1.2,63.970,1.79),"clad",c)
    # A small materials station continues the newly finished props kit's geometric vocabulary.
    for k in range(4):
        primitive(a,"CementBag",lambda p,k=k:p.box(30.2,68.2,.22+k*.17,30.85,68.62,.38+k*.17,
                       "clad",bev=.035,seg=1),"clad",(.89,.84,.71))
    for k in range(8):
        cyl(a,(30.3+k*.052,70.0,.13),(30.3+k*.052,72.0,.13),.024,n=6)
    primitive(a,"Cone",lambda p:p.lathe([(.26,0),(.26,.06),(.19,.07),(.045,.60),(.025,.64)],
                       "clad",n=10,c=(29.5,68.8,0)),"clad",(.91,.31,.072))
    B(a,(28.3,69.7,.0),(29.7,70.1,.80),"clad",COL["yellow"])


def finished_house(a,x,y,w=8,d=9,colour="sage",roof=True,half=False):
    B(a,(x,y,-.01),(x+w,y+d,.16),"clad",(.87,.85,.77))
    B(a,(x,y,.16),(x+w,y+d,2.85),"printed")
    tint=COL[colour]
    if half:
        for xa in (x,x+w-.25):
            B(a,(xa,y,2.85),(xa+.25,y+d,4.85),"printed")
        B(a,(x,y+d-.25,2.85),(x+w,y+d,4.35),"printed")
        for yy in (y+.8,y+d-.8):
            bar(a,(x,yy,5.5),(x+w*.5,yy,7.4),.13,.10,"timber")
            bar(a,(x+w*.5,yy,7.4),(x+w,yy,5.5),.13,.10,"timber")
        pallet(a,x+w+1,y+1)
        return
    B(a,(x,y,2.85),(x+w,y+d,5.45),"clad",tint)
    # Real panel recesses are cheap on the silhouettes; narrow backing lines remain recessed in the face.
    for yface,sgn in ((y,-1),(y+d,1)):
        for i in range(1,math.ceil(w/1.2)):
            xx=x+i*1.2
            B(a,(xx-.007,yface-.003,2.85),(xx+.007,yface+.003,5.45),"clad",tuple(v*.37 for v in tint))
        B(a,(x-.03,yface-.04,5.29),(x+w+.03,yface+.04,5.45),"clad",COL["cream"])
        for xx in (x+1.1,x+w-2.8):
            B(a,(xx,yface-.031,3.55),(xx+1.6,yface+.031,4.8),"clad",COL["cream"])
            B(a,(xx+.12,yface-.044,3.68),(xx+1.48,yface+.044,4.66),"clad",COL["glass"])
    ze=5.45;yr=y+d/2;zr=ze+d/2
    for xg,sgn in ((x,-1),(x+w,1)):
        a.poly([(xg,y,ze),(xg,y+d,ze),(xg,yr,zr)],"clad",uv_box(2.4),tint,want=(sgn,0,0))
        bar(a,(xg,y,ze),(xg,yr,zr),.16,.16,"clad",COL["cream"])
        bar(a,(xg,yr,zr),(xg,y+d,ze),.16,.16,"clad",COL["cream"])
    if roof:
        for ya,sgn in ((y,1),(y+d,-1)):
            n=V((0,-sgn,1)).normalized();length=d/2*math.sqrt(2)
            def P(xx,s,h=0):return V((xx,ya+sgn*s/math.sqrt(2),ze+s/math.sqrt(2)))+n*h
            def UV(pts,nrm):return [(p.x/2,(sgn*(p.y-ya)+(p.z-ze))/math.sqrt(2)/2)for p in pts]
            for k in range(math.ceil(length/.25)):
                sa,sb=k*.25,min(length,(k+1)*.25)
                a.poly([P(x,sa,.01),P(x+w,sa,.01),P(x+w,sb,.001),P(x,sb,.001)],"roof",UV,want=n)
            for row in range(2):
                for column in range(4):
                    xx=x+.55+column*1.68;sa=.65+row*1.45;sb=sa+1.35
                    q=[P(xx,sa,.10),P(xx+1.55,sa,.10),P(xx+1.55,sb,.10),P(xx,sb,.10)]
                    a.poly(q,"solar",[(0,0),(1,0),(1,1),(0,1)],want=n)
                    # Thin top-facing strips are enough for the mid ring, instead of four closed boxes
                    # for every frame. Keep their thickness silhouette on the module's edge.
                    centre=sum(q,V())/4
                    inner=[centre+(p-centre)*.968 for p in q]
                    for k in range(4):
                        j=(k+1)%4
                        a.poly([q[k],q[j],inner[j],inner[k]],"metal",uv_box(2),want=n)
        bar(a,(x-.05,yr,zr+.012),(x+w+.05,yr,zr+.012),.16,.19,"roof")
    B(a,(x+w-1.2,yr-.32,zr-.4),(x+w-.65,yr+.32,zr+.8),"clad",tint)
    B(a,(x+w-1.27,yr-.39,zr+.8),(x+w-.58,yr+.39,zr+.9),"clad",COL["cream"])


def street(a,x0,x1,y):
    B(a,(x0,y,-.018),(x1,y+8,.0),"asphalt")
    for yy in (y-.22,y+8):
        B(a,(x0,yy,0),(x1,yy+.22,.12),"pave",(.82,.84,.85))
        for k in range(math.ceil((x1-x0)/1)):
            xx=x0+k
            a.poly([(xx-.009,yy,.121),(xx+.009,yy,.121),(xx+.009,yy+.22,.121),(xx-.009,yy+.22,.121)],
                   "clad",uv_box(2.4),(.19,.20,.20),want=(0,0,1))
    for yy in (y-2.2,y+8.22):
        B(a,(x0,yy,-.007),(x1,yy+1.98,.09),"pave")
    for xx in range(math.ceil(x0/5)*5,int(x1),5):
        B(a,(xx,y+3.93,.002),(xx+1.8,y+4.07,.004),"clad",(.74,.69,.57))


def crane(a,x=117,y=104,height=42):
    yellow=COL["yellow"]
    B(a,(x-2.4,y-2.4,0),(x+2.4,y+2.4,.6),"clad",(.74,.73,.68))
    radius=1.25
    for dx in (-radius,radius):
        for dy in (-radius,radius):bar(a,(x+dx,y+dy,.6),(x+dx,y+dy,height),.32,.32,"clad",yellow)
    for k in range(1,math.ceil(height/2.4)):
        z=min(height,k*2.4)
        for dy in (-radius,radius):
            bar(a,(x-radius,y+dy,z),(x+radius,y+dy,z),.19,.19,"clad",yellow)
            bar(a,(x-radius,y+dy,z-2.4),(x+radius,y+dy,z),.17,.17,"clad",yellow)
        for dx in (-radius,radius):
            bar(a,(x+dx,y-radius,z),(x+dx,y+radius,z),.19,.19,"clad",yellow)
            bar(a,(x+dx,y-radius,z-2.4),(x+dx,y+radius,z),.17,.17,"clad",yellow)
    x0,x1=x-43,x+15
    for yy,zz in ((y-.75,height),(y+.75,height),(y,height+1.7)):
        bar(a,(x0,yy,zz),(x1,yy,zz),.26,.26,"clad",yellow)
    for k in range(math.ceil((x1-x0)/2.6)):
        xa=x0+k*2.6;xb=min(x1,xa+2.6)
        for yy in (y-.75,y+.75):
            bar(a,(xa,yy,height),(xb,y,height+1.7),.17,.17,"clad",yellow)
            bar(a,(xa,yy,height),(xb,yy,height),.17,.17,"clad",yellow)
        bar(a,(xa,y-.75,height),(xa,y+.75,height),.17,.17,"clad",yellow)
    B(a,(x+9,y-1.5,height-1.1),(x+15,y+1.5,height+.3),"clad",(.67,.64,.57))
    B(a,(x-2.2,y-.8,height-2.4),(x-.4,y+1.2,height-.3),"clad",(.87,.81,.67))
    B(a,(x-2.23,y-.83,height-2.2),(x-.43,y-.86,height-.55),"clad",COL["glass"])
    for xa in (x0+4,x1-2):cable(a,(x,y,height+7),(xa,y,height+1.7),.10,.036)
    bar(a,(x,y,height),(x,y,height+7),.26,.26,"clad",yellow)
    cyl(a,(x0+9,y,height),(x0+9,y,15),.035,n=6)
    cyl(a,(x0+9,y+.10,height),(x0+9,y+.10,15),.035,n=6)
    B(a,(x0+8.72,y-.22,14.1),(x0+9.28,y+.22,15.1),"clad",COL["dark"])


def truck(a,x,y):
    B(a,(x-1.5,y-5,.35),(x+1.5,y+2.5,3.9),"clad",(.97,.97,.96))
    B(a,(x-1.45,y+2.5,.35),(x+1.45,y+4.7,2.8),"clad",(.96,.94,.87))
    B(a,(x-1.33,y+4.70,1.65),(x+1.33,y+4.73,2.50),"clad",COL["glass"])
    B(a,(x-1.46,y+4.66,.35),(x+1.46,y+4.85,.66),"clad",COL["dark"])
    for yy in (y-3.7,y+3.3):
        for xx,sgn in ((x-1.51,-1),(x+1.51,1)):
            cyl(a,(xx,yy,.66),(xx+sgn*.12,yy,.66),.66,"clad",COL["dark"],n=12)
            cyl(a,(xx+sgn*.125,yy,.66),(xx+sgn*.13,yy,.66),.30,"metal",n=10)


def mid(a):
    # Beyond the existing skirt: avoid painting a second road over the ground kit's surfaces.
    street(a,-78,151,115);street(a,-78,151,-74)
    for i,(x,y) in enumerate([(-58,64),(-62,88),(-35,94),(3,97),(22,98),(46,97),(70,96),(91,88),
                              (120,63),(133,88),(-58,-47),(-35,-48),(0,-48),(26,-48),(51,-48),(83,-48),(109,-46),(129,-47)]):
        finished_house(a,x,y,8,9,colour="sage" if i%2==0 else "clay",half=i in (1,7,11,16))
    crane(a)
    truck(a,90,118)
    for x in (-58,-28,6,38,72,113,143):
        pole(a,x,112,8.2)
        cyl(a,(x,112,7.8),(x,114.3,7.8),.065,n=8)
        B(a,(x-.25,114.10,7.65),(x+.25,114.7,7.8),"clad",COL["cream"])
    for x0,x1 in zip((-58,-28,6,38,72,113),(-28,6,38,72,113,143)):
        cable(a,(x0,112,7.95),(x1,112,7.95),1.2)
    for i,(x,y) in enumerate([(-55,5),(-55,31),(-51,111),(-15,104),(40,107),(99,100),(137,42),
                              (136,4),(-39,-58),(13,-59),(77,-57),(119,-58)]):
        tree(a,x,y,8.5+(i%3)*.5,1800+i,cypress=i%3==0,lod=True)


def far(a):
    # Very low-poly solid silhouettes, deliberately avoiding foliage/alpha cards while that technique is held.
    for i in range(180):
        angle=2*math.pi*i/180
        radius=240+(i%7)*9
        x=36+radius*math.cos(angle);y=24+radius*.80*math.sin(angle)
        h=7.5+(i%5)*1.4
        cyl(a,(x,y,-.02),(x,y,h*.36),.20,"timber",(.42,.35,.29),n=5)
        primitive(a,"DistantTree",lambda p,x=x,y=y,h=h,i=i:
            p.blob((x,y,h*.64),h*.37,"foliage",scale=(.9,.82,1.13),sub=1,amp=.07,seed=4000+i),
            "foliage",(.54,.50,.51),.025)
    for i in range(14):
        angle=2*math.pi*i/14
        x=36+340*math.cos(angle);y=24+290*math.sin(angle)
        primitive(a,"RollingHill",lambda p,x=x,y=y,i=i:
            p.blob((x,y,-9),70,"earth",scale=(1.4,1,.28+(i%3)*.05),sub=3,amp=.06,seed=8000+i),
            "earth",(.78,.86,.84),.02)
    for i in range(80):
        x=-190+i*6.5;y=280+math.sin(i*.48)*15;h=4+(i%6)*1.1
        B(a,(x,y,0),(x+4.4,y+5.2,h),"clad",(.56,.61,.67))
        a.poly([(x,y,h),(x+4.4,y,h),(x+4.4,y+2.6,h+2),(x,y+2.6,h+2)],"roof",uv_box(2),(.79,.84,.94),want=(0,-1,1))
        a.poly([(x,y+2.6,h+2),(x+4.4,y+2.6,h+2),(x+4.4,y+5.2,h),(x,y+5.2,h)],"roof",uv_box(2),(.79,.84,.94),want=(0,1,1))


def rect_distance(x,y):
    return math.hypot(max(0,-x,x-72),max(0,-y,y-48))


def audit():
    rings={k:{"triangles":0,"meshes":0,"bounds":None}for k in ROOTS}
    violations=[];meshes=[]
    for ob in ALL:
        ring=ob["ring"];me=ob.data;tri=sum(len(p.vertices)-2 for p in me.polygons)
        coords=[v.co for v in me.vertices]
        mn=[min(p[k]for p in coords)for k in range(3)];mx=[max(p[k]for p in coords)for k in range(3)]
        distances=[rect_distance(p.x,p.y)for p in coords]
        for p,d in zip(coords,distances):
            if d < .999 or (d<6 and p.z>2.501)or(d<20 and p.z>10.001):
                violations.append(dict(mesh=ob.name,vertex=list(p),distance_m=d))
                break
        assert len(me.materials)==1 and len(me.uv_layers)>0 and len(me.color_attributes)>0
        rr=rings[ring];rr["triangles"]+=tri;rr["meshes"]+=1
        if rr["bounds"] is None:rr["bounds"]=[mn,mx]
        else:
            rr["bounds"][0]=[min(a,b)for a,b in zip(rr["bounds"][0],mn)]
            rr["bounds"][1]=[max(a,b)for a,b in zip(rr["bounds"][1],mx)]
        meshes.append(dict(name=ob.name,ring=ring,triangles=tri,material=me.materials[0].name,
                           bounds=[mn,mx],min_rect_distance_m=min(distances),uv=True,color_0=True))
    total=sum(r["triangles"]for r in rings.values())
    result=dict(triangles=total,rings=rings,materials=[m.name for m in MATS.values()],material_count=len(MATS),
                frame="design metres X east Y north Z up; glTF=(x,z,-y); roots identity",violations=violations,
                all_meshes_uv_and_color_0=True,all_meshes_single_material=True,meshes=meshes,
                utility_endpoints=[[25,54.1,6.3],[47,54.1,6.3]],
                existing_skirt_bounds=[[-80,-60],[152,110]],
                no_collision=True)
    (OUT/"backdrop_stats.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    assert total<=120000,f"Backdrop budget exceeded: {total}"
    assert rings["Mid"]["triangles"]<=35000 and rings["Far"]["triangles"]<=15000
    assert not violations,f"Clearance violations: {violations[:3]}"
    return result


def main():
    global MATS
    OUT.mkdir(parents=True,exist_ok=True)
    bc.reset_scene()
    MATS=materials()
    for ring in ("Near","Mid","Far"):
        root=bpy.data.objects.new("SHB_"+ring,None)
        bpy.context.scene.collection.objects.link(root)
        root["render_only"]=True;root["ring"]=ring;root["cast_shadows"]=ring!="Far";ROOTS[ring]=root
    part("Near","PlotsShellsTreesUtilities",near,"Existing skirt reused; exact house print grooves; original banner")
    part("Mid","SuburbCraneRoad",mid,"NE tower crane; finished and partial house silhouettes")
    part("Far","TreelineHillsTown",far,"Solid low-poly silhouettes; disable shadows and apply distance fog")
    facts=audit();log("budget",facts["triangles"],facts["rings"])
    bpy.ops.object.select_all(action="DESELECT")
    for ob in ALL+list(ROOTS.values()):ob.select_set(True)
    bpy.context.view_layer.objects.active=ALL[0]
    bpy.ops.export_scene.gltf(filepath=str(OUT/"backdrop.glb"),export_format="GLB",use_selection=True,
        export_apply=True,export_yup=True,export_tangents=True,export_normals=True,export_vertex_color="ACTIVE",export_extras=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"backdrop.blend"),compress=True,relative_remap=False)
    log("exported",OUT/"backdrop.glb")


if __name__=="__main__":main()
