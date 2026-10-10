"""Validate the actual exported GLB rather than only the Blender source scene."""
import json
import math
import struct
from pathlib import Path

HERE=Path(__file__).resolve().parent


def distance(x,y):
    return math.hypot(max(0,-x,x-72),max(0,-y,y-48))


def main():
    raw=(HERE/"backdrop.glb").read_bytes()
    magic,version,total=struct.unpack_from("<4sII",raw)
    assert magic==b"glTF" and version==2 and total==len(raw)
    n,kind=struct.unpack_from("<II",raw,12);assert kind==0x4E4F534A
    data=json.loads(raw[20:20+n]);binstart=20+n+8
    roots=[data["nodes"][i]["name"]for i in data["scenes"][0]["nodes"]]
    assert sorted(roots)==["SHB_Far","SHB_Mid","SHB_Near"]
    assert len(data["materials"])<=10
    assert all(not any(k in node for k in ("matrix","translation","rotation","scale"))for node in data["nodes"])
    counts={"Near":0,"Mid":0,"Far":0};positions=0;violations=[]
    for mesh in data["meshes"]:
        assert mesh["name"].startswith("SHB_")and len(mesh["primitives"])==1
        ring=mesh["name"].split("_")[1]
        p=mesh["primitives"][0];attrs=p["attributes"]
        assert all(k in attrs for k in ("POSITION","NORMAL","TEXCOORD_0","COLOR_0"))
        counts[ring]+=data["accessors"][p["indices"]]["count"]//3
        accessor=data["accessors"][attrs["POSITION"]]
        view=data["bufferViews"][accessor["bufferView"]]
        start=binstart+view.get("byteOffset",0)+accessor.get("byteOffset",0)
        stride=view.get("byteStride",12)
        assert accessor["componentType"]==5126 and accessor["type"]=="VEC3"
        for i in range(accessor["count"]):
            gx,gy,gz=struct.unpack_from("<fff",raw,start+i*stride)
            x,y,z=gx,-gz,gy
            assert all(math.isfinite(v)for v in (x,y,z))
            d=distance(x,y);positions+=1
            if d<.998 or(d<5.998 and z>2.502)or(d<19.998 and z>10.002):
                violations.append(dict(mesh=mesh["name"],design_position=[x,y,z],distance_m=d))
                break
    source=json.loads((HERE/"backdrop_stats.json").read_text())
    assert counts=={k:v["triangles"]for k,v in source["rings"].items()}
    assert sum(counts.values())<=120000 and counts["Mid"]<=35000 and counts["Far"]<=15000
    assert not violations,violations
    assert all(m.get("alphaMode","OPAQUE")!="BLEND"for m in data["materials"])
    result=dict(export="backdrop.glb",bytes=len(raw),triangles=counts,total_triangles=sum(counts.values()),
                material_count=len(data["materials"]),meshes=len(data["meshes"]),root_nodes=roots,
                all_nodes_identity=True,glTF_Y_up_design_frame=True,all_meshes_uv_color_0_single_material=True,
                position_samples_checked=positions,clearance_violations=violations,alpha_blended_materials=0)
    (HERE/"backdrop_validation.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
