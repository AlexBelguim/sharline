"""Local Qwen2.1 image batch ONLY. Resume skips completed PNGs; never starts TRELLIS."""
import argparse,json,sys,time,urllib.parse
from pathlib import Path
from PIL import Image,ImageDraw
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'art/briefs/showhome_v3_handoff/ai_prop_workflow/scripts'))
import qwen_edit as q
import comfy_gen as cg
STYLE=('An original stylized extraction-shooter videogame prop, matching a calm sage, clay, ivory and graphite '
       'painted palette. Chunky clean readable shapes, soft bevels, broad hand-painted colour blocks and subtle '
       'brush shading, matte surfaces, restrained highlights. Complete single isolated object in a '
       'three-quarter view, centred with generous margin, pure white background and even soft lighting. '
       'No logos, lettering, numbers, watermark, scenery, floor plane, cast ground shadow, photographic grime '
       'or tiny decorative clutter. Every part of the requested object stays inside the frame.')
BASES=[
 ('city_hatchback_blue','A compact near-future five-door hatchback car, muted blue body, graphite lower trim, simple dark wheels, lightly blue clear windows, closed rear trunk.'),
 ('delivery_van_ivory','A compact boxy delivery van, warm ivory body, charcoal bumpers, simple dark wheels, cargo doors closed, grounded modern residential delivery vehicle.'),
 ('kitchen_base_cabinet','A freestanding compact kitchen base cabinet, two cream painted lower doors and one wide upper drawer, dark stained wood worktop, simple recessed pulls, all doors and drawer closed.'),
 ('small_drawer_cabinet','A small freestanding three-drawer household cabinet, clay painted rectangular drawer fronts, charcoal frame and short legs, dark wood top, all drawers closed.'),
 ('steel_pipe_bundle','A small tidy stack of eight thick steel construction pipes resting directly together, flat sawn circular ends clearly visible, graphite painted steel with subtle restrained wear.'),
 ('printed_blocks_stack','A small stable irregular stack of cream 3D-printed concrete building blocks, horizontal printed layer grooves, a few staggered rectangular blocks, no pallet or unrelated object.'),
 ('timber_board_stack','A short coherent stack of five thick dark stained timber construction boards, slightly offset flat ends, broad simple wood grain, all boards touching.'),
 ('compact_excavator_yellow','A complete compact tracked construction excavator, warm mustard yellow cab and folded articulated boom, graphite crawler tracks and bucket, parked pose with bucket resting close to machine.'),
 ('cement_mixer_truck','A complete concrete mixer truck, ivory cab, muted mustard yellow rotating mixer drum and chassis accents, graphite wheels, compact clean readable construction-site silhouette.'),
 ('pickup_truck_ivory','A complete modern crew-cab pickup truck, ivory body, charcoal trim, open empty cargo bed, four large simple dark wheels, grounded near-future work vehicle.'),
 ('panel_van_sage','A small complete short-wheelbase panel van, sage green painted body, graphite lower bumpers, two front doors and closed rear double cargo doors, simple black wheels.'),
 ('semi_truck_ivory','A complete cab-over semi-truck tractor unit without a trailer, ivory cab with muted clay accents, exposed rear coupling platform, chunky graphite chassis and six simple wheels.')]
EDITS=[
 ('city_hatchback_clay','city_hatchback_blue','Change only the blue painted body panels to muted terracotta clay. Preserve exact vehicle geometry, wheels, glass, camera and white background.'),
 ('city_hatchback_trunk_open','city_hatchback_blue','Open the rear hatch upward so the empty trunk compartment is visible, with a simple dark interior. Preserve the same car body, blue paint, wheels and white background. Shift the three-quarter view slightly toward the rear only enough to show the lifted hatch and compartment; keep the entire car inside the frame.'),
 ('kitchen_drawer_half_open','kitchen_base_cabinet','Slide the upper drawer halfway open, showing a clean empty drawer box. Keep both lower doors closed. Preserve the exact cabinet dimensions, cream paint, dark wood top, camera and white background.'),
 ('small_drawer_cabinet_sage','small_drawer_cabinet','Change only the clay drawer fronts to muted sage green. Preserve the exact cabinet shape, closed drawers, charcoal frame, dark wood top, camera and white background.'),
 ('pickup_truck_clay','pickup_truck_ivory','Change only the ivory body panels to muted terracotta clay. Preserve the exact pickup shape, open empty bed, wheels, glass, camera and white background.'),
 ('steel_pipe_bundle_static','steel_pipe_bundle','Remove the wheeled trolley and all wheels completely. Show only the coherent bundle of graphite steel pipes resting together directly on the white background, with flat hollow circular ends clearly visible. Preserve the painted style and three-quarter framing.'),
 ('kitchen_base_cabinet_static','kitchen_base_cabinet','Replace all caster wheels with one simple charcoal recessed rectangular plinth beneath the cabinet. This is a stationary kitchen cabinet. Preserve exact cabinet dimensions, closed drawer and doors, cream paint, dark wood top, camera and white background.'),
 ('kitchen_drawer_half_open_static','kitchen_base_cabinet_static','Slide only the wide upper drawer halfway open, showing the clean empty drawer box. Keep lower doors closed and the stationary rectangular plinth. Preserve exact cabinet size, cream paint, dark wood top, camera and white background.'),
 ('city_hatchback_trunk_open_rear','city_hatchback_trunk_open','Show this exact blue hatchback from a REAR three-quarter viewpoint, camera behind the vehicle so the lifted rear hatch and empty dark cargo compartment are clearly visible. Preserve car geometry, blue paint, wheels and white background. Keep the whole car in frame, including the raised hatch.')]

def sheet():
 files=sorted((HERE/'images').glob('*.png'));w,h=320,350
 canvas=Image.new('RGB',(w*4,h*((len(files)+3)//4)),'#e8e6df');draw=ImageDraw.Draw(canvas)
 for i,p in enumerate(files):
  im=Image.open(p).convert('RGB');im.thumbnail((310,310));x,y=(i%4)*w,(i//4)*h
  canvas.paste(im,(x+(w-im.width)//2,y+(310-im.height)//2));draw.text((x+8,y+320),p.stem,fill='#333333')
 if files:canvas.save(HERE/'contact_sheet.png')

def main():
 global HERE
 ap=argparse.ArgumentParser();ap.add_argument('--spec',type=Path);args=ap.parse_args()
 spec=json.loads(args.spec.read_text(encoding='utf8')) if args.spec else None
 if args.spec:HERE=args.spec.resolve().parent
 for sub in ('images','prompts','workflows'): (HERE/sub).mkdir(parents=True,exist_ok=True)
 previous={}
 if (HERE/'manifest.json').exists():previous={r['name']:r for r in json.loads((HERE/'manifest.json').read_text(encoding='utf8'))['jobs']}
 jobs=[(r['name'],r['prompt'],r.get('base')) for r in spec['jobs']] if spec else [(name,desc,None) for name,desc in BASES]+[(name,desc,base) for name,base,desc in EDITS]
 manifest={'model':'Qwen Image2.1 int8','endpoint':'http://127.0.0.1:8188','image_size':[1024,1024],
           'steps':25,'cfg':1,'no_loras':True,'trellis_started':False,'jobs':[]}
 failures=0
 for index,(name,description,base) in enumerate(jobs):
  path=HERE/'images'/(name+'.png');prompt=description+' '+(spec.get('style',STYLE) if spec else STYLE);seed=(spec.get('seed_start',110) if spec else 110)+index
  row={'name':name,'seed':seed,'prompt':prompt,'input_image':base,'output':str(path.relative_to(HERE))}
  if path.exists():
   row=previous.get(name,row);row['reused']=True;manifest['jobs'].append(row);continue
  manifest['jobs'].append(row)
  try:
   names=[]
   if base:
    source=HERE/'images'/(base+'.png')
    if not source.exists():raise RuntimeError('Base image unavailable: '+base)
    names=[cg.upload_image(str(source))];prompt='Edit <image1>. '+prompt;row['prompt']=prompt
   graph=q.graph(names,prompt,seed,25,0 if base else 1024,'showhome_prop_'+name,
                 None if base else 1024,None if base else 1024)
   assert all('trellis' not in n['class_type'].lower() and '3d' not in n['class_type'].lower() for n in graph.values())
   (HERE/'prompts'/(name+'.txt')).write_text(prompt+'\n',encoding='utf8')
   (HERE/'workflows'/(name+'.api.json')).write_text(json.dumps(graph,indent=2)+'\n',encoding='utf8')
   pid=cg._post('/prompt',{'prompt':graph,'client_id':'showhome-prop-images-20261010'})['prompt_id']
   row['prompt_id']=pid;row['status']='queued';start=time.time()
   print('QUEUED',index+1,'/',len(jobs),name,pid,flush=True)
   while True:
    history=json.loads(cg._get('/history/'+pid)).get(pid)
    if history:
     if history.get('status',{}).get('status_str')=='error':raise RuntimeError(json.dumps(history['status'])[:2000])
     output=[im for node in history.get('outputs',{}).values() for im in node.get('images',[])]
     if output:
      image=output[0];path.write_bytes(cg._get('/view?'+urllib.parse.urlencode(image)))
      row.update(status='complete',seconds=round(time.time()-start,1),comfy_output=image)
      print('DONE',name,row['seconds'],'seconds',flush=True);failures=0;break
    if time.time()-start>1800:raise TimeoutError('Image timed out; queued job left untouched')
    time.sleep(2)
  except Exception as exc:
   row.update(status='failed',error=str(exc));failures+=1;print('FAILED',name,str(exc)[:400],flush=True)
  finally:
   (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8');sheet()
  if failures>=2:print('STOPPED after two consecutive errors; queue not cleared',flush=True);break
 print('IMAGES_ONLY_BATCH_FINISHED',sum(j.get('status','').startswith('complete') for j in manifest['jobs']),flush=True)
if __name__=='__main__':main()
