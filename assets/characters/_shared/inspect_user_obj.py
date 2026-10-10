"""Read-only OBJ structure audit and clay reference renders. Never modifies input."""
from pathlib import Path
import bpy,bmesh,sys,json,math
from collections import Counter
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
SOURCE=Path('D:/downloads/base.obj')
OUT=ROOT/'assets/characters/_shared/base_candidates/user_obj_2026_10_09'
OUT.mkdir(parents=True,exist_ok=True)
counts=Counter();arities=Counter();objects=[];comments=[];lo=[float('inf')]*3;hi=[-float('inf')]*3
corners=Counter();material_libs=[]
with SOURCE.open(encoding='utf-8',errors='replace')as f:
 for line in f:
  fields=line.split()
  if not fields:continue
  kind=fields[0];counts[kind]+=1
  if kind=='v':
   p=[float(v)for v in fields[1:4]]
   for i in range(3):lo[i]=min(lo[i],p[i]);hi[i]=max(hi[i],p[i])
  elif kind=='f':
   arities[len(fields)-1]+=1
   for token in fields[1:]:
    pieces=token.split('/');corners['uv']+=int(len(pieces)>1 and bool(pieces[1]));corners['normal']+=int(len(pieces)>2 and bool(pieces[2]));corners['total']+=1
  elif kind=='o':objects.append(' '.join(fields[1:]))
  elif kind=='mtllib':material_libs.append(' '.join(fields[1:]))
  elif kind=='#'and len(comments)<20:comments.append(line.rstrip())
report={'input':str(SOURCE),'input_bytes':SOURCE.stat().st_size,'obj_vertices':counts['v'],'obj_uvs':counts['vt'],'obj_normals':counts['vn'],
        'polygons':counts['f'],'face_arity':dict(arities),'triangles':sum((n-2)*c for n,c in arities.items()),
        'raw_bounds':[lo,hi],'raw_dimensions':[hi[i]-lo[i]for i in range(3)],'objects':objects,'comments':comments,
        'face_corners':dict(corners),'material_libraries':material_libs,'license':'not established from supplied OBJ',
        'rig':False,'pose_note':'OBJ has no skeletal rig or animation data'}
bc.reset_scene()
# Parsing found no MTL assets in the supplied package; import as plain geometry.
bpy.ops.wm.obj_import(filepath=str(SOURCE),forward_axis='NEGATIVE_Z',up_axis='Y')
parts=[o for o in bpy.context.scene.objects if o.type=='MESH']
detail=[]
for ob in parts:
 bm=bmesh.new();bm.from_mesh(ob.data)
 visited=set();components=[]
 for vertex in bm.verts:
  if vertex in visited:continue
  stack=[vertex];visited.add(vertex);size=0
  while stack:
   v=stack.pop();size+=1
   for e in v.link_edges:
    q=e.other_vert(v)
    if q not in visited:visited.add(q);stack.append(q)
  components.append(size)
 detail.append({'name':ob.name,'vertices':len(bm.verts),'edges':len(bm.edges),'polygons':len(bm.faces),
                'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges),
                'components':len(components),'largest_component_vertices':sorted(components,reverse=True)[:12],
                'uv_layers':list(ob.data.uv_layers.keys()),'bounds':[list(min(v.co[i]for v in ob.data.vertices)for i in range(3)),list(max(v.co[i]for v in ob.data.vertices)for i in range(3))]})
 bm.free()
report['imported_meshes']=detail
lo,hi=bc.world_bounds(parts)
# Inspection copy only: centre horizontally, place feet at zero, scale to Kestrel.
scale=1.70/max(hi.z-lo.z,1e-8)
center=(lo+hi)*.5
for ob in parts:
 for v in ob.data.vertices:
  p=ob.matrix_world@v.co;v.co=Vector(((p.x-center.x)*scale,(p.y-center.y)*scale,(p.z-lo.z)*scale))
 ob.matrix_world.identity()
 bc.assign(ob,bc.material('M_Inspection_Clay',(.40,.42,.44),rough=.62))
 for poly in ob.data.polygons:poly.use_smooth=True
report['inspection_scale_to_1_70']=scale
(OUT/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
print('OBJ_AUDIT',json.dumps(report),flush=True)
bc.setup_studio(bg=(.18,.185,.20),strength=.7,floor=True)
bpy.data.objects['_Floor'].scale=(4,4,4)
bc.render_views(str(OUT/'renders'),'base',parts,views=('front','three_quarter','right','back'),res=(900,1100),engine='EEVEE',samples=32,ortho=True,focus=((0,0,.86),.94),margin=1.1)
bc.VIEW_DIRS.update(three_quarter=(.60,-1,.035),front=(0,-1,.025),back=(0,1,.025))
bc.render_views(str(OUT/'renders'),'head',parts,views=('front','three_quarter','back'),res=(900,900),engine='CYCLES',samples=40,ortho=True,focus=((0,0,1.575),.17),margin=1.12)
bc.contact_sheet([str(OUT/'renders'/f'base_{v}.png')for v in('front','three_quarter','right','back')],str(OUT/'renders/contact_sheet.png'),cols=2)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'inspection.blend'),compress=True)
print('OBJ_INSPECTION_DONE',flush=True)
