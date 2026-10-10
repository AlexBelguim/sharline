"""Finish the supplied TRELLIS duffel as a painted, budgeted game prop.

Uses the existing cleaned/rebaked 4.5k-triangle test mesh of this source bag.
Geometry is preserved; shared Krea2 fabric/leather detail and game palette replace
the noisy generated material. Run Blender 5.2 -b --factory-startup -P this file.
"""
from pathlib import Path
import bpy,bmesh,sys,math,json,time
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
import blender_common as bc
SOURCE=Path('C:/Users/alexw/AppData/Roaming/StabilityMatrix/Packages/ComfyUI/output/valetf_a_duffel_full_00001_.glb')
CACHE=OUT/'input/duffel_clean_input.glb'
KTEX=ROOT/'assets/characters/kestrel/v2/textures'
TEX=ROOT/'art/textures'

def image_node(nt,path,linear=False):
 n=nt.nodes.new('ShaderNodeTexImage');n.image=bpy.data.images.load(str(path),check_existing=True)
 n.image.colorspace_settings.name='Non-Color'if linear else'sRGB'
 return n

def material(name,palette,detail,rough,normal=None,metal=0.):
 m=bc.material('M_Duffel_'+name,palette,rough,metal)
 p=bc._principled(m);bc._set_input(p,['Specular IOR Level','Specular'],.25 if not metal else .5)
 nt=m.node_tree
 if detail:
  texture=image_node(nt,OUT/'textures'/('duffel_'+name+'.png'))
  nt.links.new(texture.outputs['Color'],p.inputs['Base Color'])
 if normal:
  n=image_node(nt,KTEX/(normal+'_normal.png'),True)
  nm=nt.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.32
  nt.links.new(n.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],p.inputs['Normal'])
 m['source_detail']=str(TEX/(detail+'.png'))if detail else'flat standard PBR'
 return m

def color_sample(img,uv):
 w,h=img.size
 # Sampling is for semantic regions only; baked light/noise is not preserved.
 pixels=np.empty(w*h*4,dtype=np.float32);img.pixels.foreach_get(pixels)
 pixels=pixels.reshape(h,w,4)
 def sample(p):
  return pixels[min(h-1,max(0,int(p.y*h))),min(w-1,max(0,int(p.x*w))),:3]
 return sample

def classify(rgb,normal,z):
 r,g,b=map(float,rgb);v=max(r,g,b);lo=min(r,g,b);sat=(v-lo)/max(v,1e-5)
 if g>r*1.35 and g>b*.94 and g>.045:return 1 # teal end panel
 if b>r*1.35 and b>g*1.06 and sat>.20:return 0 # blue canvas
 if sat<.20 and v>.45:return 3 # bone trim
 if sat<.28 and v>.13 and z>.10:return 4 # brushed buckle/zipper
 return 2 # graphite webbing/lining

def smooth_fabric(ob):
 """Bilateral-style relaxation on broad coloured cloth, keeping seams/straps."""
 image=bpy.data.images.load(str(OUT/'textures/duffel_albedo.png'),check_existing=True)
 sample=color_sample(image,ob.data.uv_layers.active)
 sums=np.zeros((len(ob.data.vertices),3));hits=np.zeros(len(ob.data.vertices))
 for loop,uv in zip(ob.data.loops,ob.data.uv_layers.active.data):
  sums[loop.vertex_index]+=sample(uv.uv);hits[loop.vertex_index]+=1
 colors=sums/np.maximum(1,hits)[:,None]
 bm=bmesh.new();bm.from_mesh(ob.data);bm.verts.ensure_lookup_table();bm.normal_update()
 allowed=[]
 for v in bm.verts:
  rgb=colors[v.index];value=max(rgb);saturation=(value-min(rgb))/max(value,1e-5)
  fabric=saturation>.32 and value>.065
  feature=any(e.is_boundary or e.calc_face_angle(0.)>math.radians(43)for e in v.link_edges)
  if fabric and not feature and .025<v.co.z<.285:allowed.append(v)
 moved=0;maximum=0.
 for step in range(2):
  updates=[]
  for v in allowed:
   neighbors=[e.other_vert(v)for e in v.link_edges]
   if not neighbors:continue
   mean=sum((q.co for q in neighbors),Vector())/len(neighbors)
   delta=(mean-v.co)*.18
   if delta.length>.0016:delta=delta.normalized()*.0016
   updates.append((v,delta))
  for v,delta in updates:
   v.co+=delta;maximum=max(maximum,delta.length);moved+=int(delta.length>1e-5)
 bm.to_mesh(ob.data);bm.free();ob.data.update()
 return {'selected_vertices':len(allowed),'relaxation_steps':2,'max_step_m':maximum,'moved_vertex_steps':moved,
         'preserved':'high-angle seams/folds, neutral webbing/hardware, handle silhouette'}

def main():
 start=time.time();OUT.mkdir(parents=True,exist_ok=True);(OUT/'renders').mkdir(exist_ok=True)
 bc.reset_scene();bpy.context.preferences.filepaths.save_version=0
 bpy.ops.import_scene.gltf(filepath=str(CACHE),merge_vertices=True)
 parts=[o for o in bpy.context.scene.objects if o.type=='MESH']
 for o in list(bpy.context.scene.objects):
  if o not in parts:bpy.data.objects.remove(o,do_unlink=True)
 bpy.ops.object.select_all(action='DESELECT')
 for o in parts:o.select_set(True)
 bpy.context.view_layer.objects.active=parts[0]
 if len(parts)>1:bpy.ops.object.join()
 ob=bpy.context.active_object;ob.name='DFL_Bag'
 ob.parent=None;bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
 # glTF vertex splits at UV/normal seams are rendering data, not real holes.
 # Weld positions on the authoring copy while preserving loop UV coordinates.
 bm=bmesh.new();bm.from_mesh(ob.data)
 bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
 bm.to_mesh(ob.data);bm.free();ob.data.update()
 lo,hi=bc.world_bounds([ob]);scale=.65/(hi.x-lo.x);center=(lo+hi)*.5
 for v in ob.data.vertices:v.co=Vector(((v.co.x-center.x)*scale,(v.co.y-center.y)*scale,(v.co.z-lo.z)*scale))
 ob.data.update()
 cleanup=smooth_fabric(ob)
 mat=bc.material('M_Duffel_Painted',(1,1,1),.76)
 nt=mat.node_tree;p=bc._principled(mat)
 albedo=image_node(nt,OUT/'textures/duffel_albedo.png')
 nt.links.new(albedo.outputs['Color'],p.inputs['Base Color'])
 normal=image_node(nt,OUT/'textures/duffel_normal.png',True)
 nm=nt.nodes.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.65
 nt.links.new(normal.outputs['Color'],nm.inputs['Color']);nt.links.new(nm.outputs['Normal'],p.inputs['Normal'])
 orm=image_node(nt,OUT/'textures/duffel_orm.png',True)
 channels=nt.nodes.new('ShaderNodeSeparateColor');channels.mode='RGB'
 nt.links.new(orm.outputs['Color'],channels.inputs['Color'])
 nt.links.new(channels.outputs['Green'],p.inputs['Roughness']);nt.links.new(channels.outputs['Blue'],p.inputs['Metallic'])
 mat['detail_source']='art/textures/fabric_ripstop.png and Kestrel jacket normal, combined with preserved source colour regions'
 mats=[mat]
 ob.data.materials.clear()
 for m in mats:ob.data.materials.append(m)
 for p in ob.data.polygons:p.material_index=0;p.use_smooth=True
 # The importer welded away one tiny degenerate triangle. Close that local
 # three-edge hole, preserving the rest of the cleaned bag geometry and UVs.
 bm=bmesh.new();bm.from_mesh(ob.data)
 bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
 edges=[e for e in bm.edges if e.is_boundary]
 if len(edges)==3:bmesh.ops.holes_fill(bm,edges=edges,sides=3)
 bm.to_mesh(ob.data);bm.free();ob.data.update()
 # Welded whole topology is measured before intentional material splits.
 bm=bmesh.new();bm.from_mesh(ob.data)
 geometry={'vertices':len(bm.verts),'triangles':sum(len(f.verts)-2 for f in bm.faces),
           'boundary_edges':sum(e.is_boundary for e in bm.edges),'nonmanifold_edges':sum(not e.is_manifold for e in bm.edges)}
 bm.free()
 ob['source']='Supplied TRELLIS duffel; cleaned/rebaked cache from the same source'
 ob['texture_source']='existing art/textures and Kestrel shared normal maps'
 bpy.context.view_layer.objects.active=ob;ob.select_set(True)
 bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.separate(type='MATERIAL');bpy.ops.object.mode_set(mode='OBJECT')
 finished=[o for o in bpy.context.scene.objects if o.type=='MESH']
 for o in finished:
  o.name='DFL_Duffel'
  o['prop']='duffel';o['frame']='metres, base centre Z=0, Blender Z up/front-Y'
  o['conversion']='Trellis source cleanup, 4.5k budget, shared painted materials'
  # Preserve broad cloth volume, keep high-angle folds and trim edges readable.
  bc.shade_smooth(o,75)
 bc.uv_all(finished)
 bpy.data.orphans_purge(do_recursive=True)
 bc.export_all(str(OUT/'duffel'),finished)
 lo,hi=bc.world_bounds(finished)
 result={'source':str(SOURCE),'clean_mesh_cache':str(CACHE),'status':'prop_style_test',
         'surface_cleanup':cleanup,
         'geometry':geometry,'source_triangles':698809,'reduction_percent':100*(1-geometry['triangles']/698809),
         'dimensions_m':list(hi-lo),'bounds':[list(lo),list(hi)],'materials':sorted(set(m.name for o in finished for m in o.data.materials)),
         'mesh_per_material':True,'UVs':all(o.data.uv_layers for o in finished),
         'outputs':['duffel.blend','duffel.glb','duffel.fbx'],'game_code_changed':False}
 (OUT/'duffel_qa.json').write_text(json.dumps(result,indent=2)+'\n')
 bc.setup_studio(bg=(.18,.185,.20),strength=.70,floor=True);bpy.data.objects['_Floor'].scale=(4,4,4)
 bc.render_views(str(OUT/'renders'),'duffel',finished,views=('front','three_quarter','right','back','three_quarter_back'),res=(1000,900),engine='CYCLES',samples=48,ortho=True,focus=((0,0,.19),.36),margin=1.14)
 bc.contact_sheet([str(OUT/'renders'/f'duffel_{v}.png')for v in('front','three_quarter','right','back')],str(OUT/'renders/contact_sheet.png'),cols=2)
 print('DUFFEL_DONE',json.dumps(result),round(time.time()-start,1),flush=True)

if __name__=='__main__':main()
