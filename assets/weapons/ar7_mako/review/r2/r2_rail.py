import bpy, bmesh, sys
bpy.ops.wm.open_mainfile(filepath=sys.argv[sys.argv.index("--")+1])
dg = bpy.context.evaluated_depsgraph_get()
for rn in ("MAKO_Rail","MAKO_RailBottom","MAKO_RailSide_R"):
    o = bpy.data.objects[rn]; oe = o.evaluated_get(dg); me = oe.to_mesh()
    bm = bmesh.new(); bm.from_mesh(me); bm.transform(o.matrix_world)
    # slot floor faces: faces whose normal points outward along the rail's up axis but are recessed
    ax = {"MAKO_Rail":(2,1),"MAKO_RailBottom":(2,-1),"MAKO_RailSide_R":(0,-1)}[rn]
    i, s = ax
    top = max(v.co[i]*s for v in bm.verts)
    fl = [f for f in bm.faces if f.normal[i]*s > 0.99 and top-0.006 < f.calc_center_median()[i]*s < top-0.001]
    ys = sorted(round(f.calc_center_median().y,5) for f in fl)
    import itertools
    d = [round(b-a,4) for a,b in zip(ys,ys[1:])]
    print(rn, "n", len(ys), "first", ys[:3], "last", ys[-3:], "odd pitches", [(ys[k],ys[k+1]) for k,x in enumerate(d) if abs(x-0.010)>0.0003])
    print("   floor depth", round(top - max(f.calc_center_median()[i]*s for f in fl),4))
    oe.to_mesh_clear()
