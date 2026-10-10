//! Solo in-game editor for the exported kit's editable layer.
//! Fixed art and owned placements.ron remain untouched; explicit saves use placements.editor.ron.
use bevy::prelude::*;
use bevy::input::{keyboard::KeyboardInput,mouse::AccumulatedMouseMotion};
use bevy::tasks::{AsyncComputeTaskPool,Task,futures::check_ready};
use std::{collections::HashMap,path::PathBuf,sync::Arc};
use vetf_sim::build_mode::{self as bm,EditSession,EditCommand,EditableItem,Placements,PropCatalog,PropInstance,EditorOptions,FoliageVolume,FoliageKind,SpawnMarker,PlayerClip,ExtractMarker,ExtractParameters,LootSpot};
use vetf_sim::build_mode::collision::{ConvexVolume,instantiate_props};
use vetf_sim::maps::showhome_v3::{CorePreview,load_with_placements,promote_fixed_foliage,editor_path};
use crate::{AppState,config::{Cli,CurrentLevel},net::{Role,Session},render::{ViewCamera,Viewmodel},showhome_v3::CurrentV3Preview};
use vetf_net::{PlayerId,PlayerInfo,PlayerMove,PlayerLook,PlayerItems};

#[derive(Resource,Default)] pub struct EditorActive(pub bool);
#[derive(Resource,Default)] pub struct EditorLook(pub bool);
#[derive(Clone,Debug,PartialEq)] pub enum PlaceTool {Select,Prop(String),Hedge,Bush,SpawnA,SpawnB,SpawnFfa,Clip,Extract,Loot}
#[derive(Message,Clone,Debug)] pub enum EditorAction {Tool(PlaceTool),Save,Reload,Undo,Redo,Delete,Duplicate,Drop,ToggleLock,ToggleLoot,Move([f64;3]),Rotate(f64),Scale(f64),Resize(usize,f64),ToggleSnap,NextGrid,NextAngle,Search(String),SearchFocus(bool),Page(i32),Play}

#[derive(serde::Deserialize)]
#[serde(default)]
struct ViewOptions {camera_speed_mps:f32,camera_fast_mult:f32,mouse_radians_per_pixel:f32}
impl Default for ViewOptions {fn default()->Self {Self{camera_speed_mps:10.,camera_fast_mult:4.,mouse_radians_per_pixel:0.0025}}}

#[derive(Resource)]
pub struct EditorState {
 pub catalog:Option<PropCatalog>,pub selected:Option<String>,pub placement:Option<PlaceTool>,
 pub search:String,pub search_focus:bool,pub page:usize,pub status:String,
 pub options:EditorOptions,pub snap:bool,pub dirty:bool,pub ui_revision:u64,
 session:Option<EditSession>,map:String,path:PathBuf,saved_hash:Option<String>,just_entered:bool,failed_version:Option<u64>,
 fly:Transform,yaw:f32,pitch:f32,view:ViewOptions,auto:bool,version:u64,physics_version:u64,
 pending:Option<(u64,Task<Result<CorePreview,String>>)>,rendered:HashMap<String,PropInstance>,
 shapes:HashMap<(String,bool),Vec<ConvexVolume>>,last_save:f32,hidden_ui:HashMap<Entity,Display>,
}
impl Default for EditorState {fn default()->Self {Self{catalog:None,selected:None,placement:None,search:String::new(),search_focus:false,page:0,status:String::new(),options:EditorOptions::default(),snap:true,dirty:false,ui_revision:0,session:None,map:String::new(),path:PathBuf::new(),saved_hash:None,just_entered:false,failed_version:None,fly:Transform::default(),yaw:0.,pitch:0.,view:ViewOptions::default(),auto:false,version:0,physics_version:0,pending:None,rendered:HashMap::new(),shapes:HashMap::new(),last_save:0.,hidden_ui:HashMap::new()}}}
impl EditorState {
 pub fn document(&self)->Option<&Placements>{self.session.as_ref().map(EditSession::document)}
 fn command(&mut self,c:EditCommand){let Some(s)=self.session.as_mut() else{return};match s.apply(c){Ok(())=>self.changed(),Err(e)=>self.status=e.to_string()}}
 fn changed(&mut self){self.version+=1;self.failed_version=None;self.ui_revision+=1;self.dirty=true;self.status="Edited · collision preview updating".into()}
 fn next_id(&self,prefix:&str)->String{let mut n=1;loop{let id=format!("user_{prefix}_{n}");if self.document().is_none_or(|d|d.item(&id).is_none()){return id}n+=1}}
}

pub struct BuildEditorPlugin;
impl Plugin for BuildEditorPlugin {fn build(&self,app:&mut App){
 app.init_resource::<EditorActive>().init_resource::<EditorLook>().init_resource::<EditorState>().add_message::<EditorAction>();
 crate::build_editor_ui::plugin(app);
 app.add_systems(OnEnter(AppState::InGame),|cli:Res<Cli>,mut s:ResMut<EditorState>|s.auto=cli.build.is_some());
 app.add_systems(OnExit(AppState::InGame),|mut a:ResMut<EditorActive>,mut l:ResMut<EditorLook>,mut s:ResMut<EditorState>|{a.0=false;l.0=false;*s=EditorState::default();});
 app.add_systems(Update,(toggle_editor,editor_keys,apply_actions,fly_camera,reconcile_props,refresh_world,draw_editor,hide_game_ui).chain().after(crate::build_editor_ui::EditorUiSystems::Input).before(crate::build_editor_ui::EditorUiSystems::Refresh).run_if(in_state(AppState::InGame)));
}}

fn toggle_editor(keys:Res<ButtonInput<KeyCode>>,net:Res<Session>,preview:Option<Res<CurrentV3Preview>>,players:Query<&PlayerId,With<PlayerInfo>>,cams:Query<&Transform,With<ViewCamera>>,mut a:ResMut<EditorActive>,mut s:ResMut<EditorState>,mut control:ResMut<crate::client::LocalControl>,time:Res<Time>){
 if a.0&&players.iter().any(|p|p.0!=0){s.status="Editor requires a solo hosted session".into();return}
 if a.0||!(keys.just_pressed(KeyCode::F8)||s.auto){return}
 let Some(p)=preview else{return};let Some(cam)=cams.iter().next() else{return};
 if net.role!=Role::Host||players.iter().any(|p|p.0!=0){s.auto=false;s.status="Open a solo Showhome v3 session to edit".into();return}
 if s.session.is_none()||s.map!=p.0.level.name {
  s.map=p.0.level.name.clone();s.path=editor_path(crate::config::assets_root(),&s.map);
  let (mut doc,hash)=match load_editor_document(&s.path,&p.0.placements){Ok(v)=>v,Err(e)=>{s.status=e;return}};
  if doc.origin!=p.0.origin{s.status="Editor document has a different map origin".into();return}
  if let Err(e)=promote_fixed_foliage(&mut doc,&p.0.fixed_foliage){s.status=e.to_string();return}
  s.saved_hash=hash;s.catalog=Some(p.0.catalog.clone());
  s.options=EditorOptions::load(&crate::config::assets_root().join("data/build_mode.ron")).unwrap_or_default();
  s.view=std::fs::read_to_string(crate::config::assets_root().join("data/build_mode.ron")).ok().and_then(|t|ron::from_str(&t).ok()).unwrap_or_default();
  s.session=EditSession::new(doc).ok();s.rendered=p.0.placements.instances.iter().filter(|r|r.mode=="all"||r.mode==p.0.asset_mode).map(|r|(r.id.clone(),r.clone())).collect();
  s.version+=1;s.physics_version=0;
 }
 s.fly=*cam;let (yaw,pitch,_)=cam.rotation.to_euler(EulerRot::YXZ);s.yaw=yaw;s.pitch=pitch;s.auto=false;s.last_save=time.elapsed_secs();
 s.ui_revision+=1;s.status="RMB + WASD to fly · click to select · F8 to play".into();s.just_entered=true;a.0=true;control.mouse_block=true;
}

fn load_editor_document(path:&std::path::Path,fallback:&Placements)->Result<(Placements,Option<String>),String>{
 if !path.exists(){return Ok((fallback.clone(),None))}let bytes=std::fs::read(path).map_err(|e|e.to_string())?;
 let text=std::str::from_utf8(&bytes).map_err(|e|e.to_string())?;let doc=Placements::from_ron(text).map_err(|e|e.to_string())?;Ok((doc,Some(bm::sha256(&bytes))))
}

fn editor_keys(a:Res<EditorActive>,keys:Res<ButtonInput<KeyCode>>,mouse:Res<ButtonInput<MouseButton>>,mut typed:MessageReader<KeyboardInput>,mut s:ResMut<EditorState>,mut out:MessageWriter<EditorAction>){
 if !a.0{return}
 if s.just_entered{s.just_entered=false;typed.clear();return}
 if s.search_focus {
  for e in typed.read(){if e.state==bevy::input::ButtonState::Pressed {if let Some(t)=&e.text{s.search.extend(t.chars().filter(|c|!c.is_control()));s.page=0;s.ui_revision+=1;}}}
  if keys.just_pressed(KeyCode::Backspace){s.search.pop();s.page=0;s.ui_revision+=1}
  if keys.any_just_pressed([KeyCode::Enter,KeyCode::Escape]){s.search_focus=false;s.ui_revision+=1}return
 }
 typed.clear();let ctrl=keys.any_pressed([KeyCode::ControlLeft,KeyCode::ControlRight]);
 if keys.just_pressed(KeyCode::F8){out.write(EditorAction::Play);return}
 if ctrl {for (k,c) in [(KeyCode::KeyS,EditorAction::Save),(KeyCode::KeyZ,EditorAction::Undo),(KeyCode::KeyY,EditorAction::Redo),(KeyCode::KeyD,EditorAction::Duplicate)]{if keys.just_pressed(k){out.write(c);}}return}
 if keys.just_pressed(KeyCode::Escape){s.placement=None;s.selected=None;s.ui_revision+=1}
 if mouse.pressed(MouseButton::Right){return}
 let step=s.options.position_snap_m;
 for (k,v) in [(KeyCode::ArrowLeft,[-step,0.,0.]),(KeyCode::ArrowRight,[step,0.,0.]),(KeyCode::ArrowUp,[0.,step,0.]),(KeyCode::ArrowDown,[0.,-step,0.]),(KeyCode::PageUp,[0.,0.,step]),(KeyCode::PageDown,[0.,0.,-step])]{if keys.just_pressed(k){out.write(EditorAction::Move(v));}}
 if keys.just_pressed(KeyCode::KeyR){out.write(EditorAction::Rotate(if keys.pressed(KeyCode::ShiftLeft){-s.options.yaw_snap_deg}else{s.options.yaw_snap_deg}));}
 let prop=s.selected.as_deref().and_then(|id|s.document().and_then(|d|d.item(id))).is_some_and(|i|matches!(i,EditableItem::Prop(_)));
 for (k,c) in [(KeyCode::Delete,EditorAction::Delete),(KeyCode::KeyG,EditorAction::Drop),(KeyCode::Equal,EditorAction::Scale(if prop{0.05}else{1.05})),(KeyCode::Minus,EditorAction::Scale(if prop{-0.05}else{0.95}))]{if keys.just_pressed(k){out.write(c);}}
}

fn save(s:&mut EditorState){let Some(doc)=s.document()else{return};if s.saved_hash.is_none()&&s.path.exists(){s.status="Editor file appeared on disk; reload before saving".into();return}
 match bm::save_atomic(&s.path,doc,&s.options,s.saved_hash.as_deref()){Ok(r)=>{s.saved_hash=Some(r.content_sha256);s.dirty=false;s.status=format!("Saved {} · owned placements.ron preserved",s.path.display());},Err(e)=>s.status=e.to_string()}}

fn apply_actions(mut actions:MessageReader<EditorAction>,mut s:ResMut<EditorState>,mut active:ResMut<EditorActive>,level:Option<Res<CurrentLevel>>,preview:Option<Res<CurrentV3Preview>>,mut control:ResMut<crate::client::LocalControl>,mut people:Query<(&PlayerId,&mut PlayerMove,&mut PlayerLook,&mut PlayerItems,Option<&mut crate::client::Smoothed>)>,time:Res<Time>){
 if !active.0{actions.clear();return}
 for action in actions.read(){
  match action {
   EditorAction::Tool(t)=>{s.placement=if *t==PlaceTool::Select{None}else{Some(t.clone())};s.search_focus=false;s.status="Click a surface to place · Esc returns to selection".into();},
   EditorAction::Save=>{save(&mut s);s.last_save=time.elapsed_secs()},
   EditorAction::Reload=>match Placements::load(&s.path){Ok(d)=>{s.session=EditSession::new(d).ok();s.saved_hash=std::fs::read(&s.path).ok().map(|b|bm::sha256(&b));s.selected=None;s.changed();s.dirty=false;s.status="Reloaded saved working copy".into()},Err(e)=>s.status=e.to_string()},
   EditorAction::Undo=>{if s.session.as_mut().is_some_and(EditSession::undo){s.changed()}},
   EditorAction::Redo=>{if s.session.as_mut().is_some_and(EditSession::redo){s.changed()}},
   EditorAction::Search(t)=>{s.search=t.clone();s.page=0},EditorAction::SearchFocus(b)=>s.search_focus=*b,
   EditorAction::Page(delta)=>s.page=(s.page as i32+delta).max(0) as usize,
   EditorAction::ToggleSnap=>s.snap=!s.snap,
   EditorAction::NextGrid=>s.options.position_snap_m=if s.options.position_snap_m<0.5{0.5}else if s.options.position_snap_m<1.{1.}else{0.25},
   EditorAction::NextAngle=>s.options.yaw_snap_deg=if s.options.yaw_snap_deg<45.{45.}else if s.options.yaw_snap_deg<90.{90.}else{15.},
   EditorAction::Play=>{
    if s.pending.is_some()||s.version!=s.physics_version{s.status="Collision preview updating; wait before playing".into();continue}
    let Some(world)=level.as_ref()else{continue};let feet=s.fly.translation-Vec3::Y*1.6;
    if let Some(p)=preview.as_ref(){let x=feet.x as f64+p.0.origin[0];let y=-feet.z as f64+p.0.origin[1];let b=p.0.play_bounds_design;if x<=b[0]||x>=b[2]||y<=b[1]||y>=b[3]{s.status="Fly inside the play bounds before playing".into();continue}}
    let hit=world.world.trace_solid(feet+Vec3::Y*0.9,feet+Vec3::Y*0.9,Vec3::new(0.32,0.9,0.32));
    if hit.start_solid{s.status="Camera is inside collision; fly into free space before playing".into();continue}
    for (id,mut mv,mut look,mut items,smoothed) in &mut people {if id.0==0 {mv.0=vetf_sim::movement::MoveState::spawn(feet,mv.0.fuel);look.yaw=s.yaw;look.pitch=s.pitch;items.0.throw.selected=None;items.0.throw.windup=None;items.0.throw.charge_ticks=0;if let Some(mut smooth)=smoothed{smooth.prev=feet;smooth.curr=feet;}}}
    control.yaw=s.yaw;control.pitch=s.pitch;control.mouse_block=true;control.held=0;control.latched=vetf_sim::input::Buttons::THROW_CANCEL;active.0=false;
   },
   _=>{
    let Some(id)=s.selected.clone()else{continue};let Some(item)=s.document().and_then(|d|d.item(&id))else{continue};
    let command=match action {
     EditorAction::Delete=>Some(EditCommand::Delete{id:id.clone()}),
     EditorAction::Duplicate=>Some(EditCommand::Duplicate{id:id.clone(),new_id:s.next_id("copy"),offset:[s.options.position_snap_m,0.,0.]}),
     EditorAction::ToggleLock=>Some(EditCommand::SetLocked{id:id.clone(),locked:!item.locked()}),
     EditorAction::ToggleLoot=>if let EditableItem::Prop(p)=&item{Some(EditCommand::SetLootable{id:id.clone(),lootable:!p.lootable})}else{None},
     EditorAction::Move(delta)=>{let p=item.position();Some(EditCommand::Move{id:id.clone(),position:std::array::from_fn(|i|p[i]+delta[i])})},
     EditorAction::Rotate(delta)=>{let yaw=match &item{EditableItem::Prop(p)=>p.yaw_deg,EditableItem::Foliage(p)=>p.yaw_deg,EditableItem::Spawn(p)=>p.yaw_deg,EditableItem::Extract(p)=>p.yaw_deg,_=>{s.status="This marker has no rotation".into();continue}};Some(EditCommand::Rotate{id:id.clone(),yaw_deg:yaw+delta,tilt_deg:if let EditableItem::Prop(p)=&item{p.tilt_deg}else{None}})},
     EditorAction::Scale(delta)=>{let scale=if let EditableItem::Prop(p)=&item{(p.scale+delta).clamp(0.8,1.25)}else{*delta};Some(EditCommand::Scale{id:id.clone(),scale})},
     EditorAction::Resize(axis,delta)=>if let EditableItem::Foliage(p)=&item{let mut dims=p.dimensions_m;if *axis<3{dims[*axis]=(dims[*axis]+delta).max(0.1)}Some(EditCommand::Resize{id:id.clone(),dimensions_m:dims})}else{None},
     EditorAction::Drop=>{let p=item.position();let origin=s.document().unwrap().origin;let mut start=p;if let EditableItem::Clip(c)=&item{start[2]=c.min[2]}
      let top=Vec3::from_array(bm::collision::design_to_bevy(start,origin).map(|x|x as f32))+Vec3::Y*0.1;
      let mut support=vetf_sim::movement::collision::CollisionWorld::default();if let Some(preview)=preview.as_ref(){for v in &preview.0.volumes{if v.extras.get("instance_id").and_then(|x|x.as_str())!=Some(&id)&&v.walkable{support.push(vetf_sim::maps::showhome_v3::brush(v));}}}
      support.raycast(top,Vec3::NEG_Y,200.).map(|(d,_)|{let mut pos=p;pos[2]=(top.y-d) as f64+origin[2];if let EditableItem::Clip(c)=&item{pos[2]+=(c.max[2]-c.min[2])/2.}EditCommand::Move{id:id.clone(),position:pos}})},
     _=>None,
    };if let Some(c)=command{s.command(c)}
   }
  };s.ui_revision+=1;
 }
 if s.dirty&&time.elapsed_secs()-s.last_save>=s.options.autosave_seconds as f32{save(&mut s);s.last_save=time.elapsed_secs();s.ui_revision+=1}
}

fn fly_camera(a:Res<EditorActive>,mut look:ResMut<EditorLook>,mut s:ResMut<EditorState>,keys:Res<ButtonInput<KeyCode>>,mouse:Res<ButtonInput<MouseButton>>,motion:Res<AccumulatedMouseMotion>,time:Res<Time>,mut cam:Query<&mut Transform,With<ViewCamera>>,mut gun:Query<&mut Visibility,With<Viewmodel>>){
 look.0=a.0&&mouse.pressed(MouseButton::Right);if !a.0{return}
 for mut v in &mut gun{*v=Visibility::Hidden}
 if look.0 {let sensitivity=s.view.mouse_radians_per_pixel;s.yaw-=motion.delta.x*sensitivity;s.pitch=(s.pitch-motion.delta.y*sensitivity).clamp(-1.55,1.55);s.fly.rotation=Quat::from_euler(EulerRot::YXZ,s.yaw,s.pitch,0.);
  let horizontal=Vec3::new((keys.pressed(KeyCode::KeyD) as i32-keys.pressed(KeyCode::KeyA) as i32) as f32,0.,(keys.pressed(KeyCode::KeyS) as i32-keys.pressed(KeyCode::KeyW) as i32) as f32);
  let mut direction=s.fly.rotation*horizontal;direction.y+=(keys.pressed(KeyCode::Space) as i32-keys.pressed(KeyCode::KeyC) as i32) as f32;
  let speed=s.view.camera_speed_mps*if keys.pressed(KeyCode::ShiftLeft){s.view.camera_fast_mult}else{1.};s.fly.translation+=direction.normalize_or_zero()*speed*time.delta_secs();
 }for mut t in &mut cam{*t=s.fly}
}

fn reconcile_props(mut commands:Commands,server:Res<AssetServer>,a:Res<EditorActive>,mut s:ResMut<EditorState>,preview:Option<Res<CurrentV3Preview>>,mut roots:Query<(Entity,&crate::showhome_kit::PreviewInstanceId,&mut Transform)>){
 if !a.0{return}let Some(p)=preview else{return};let Some(doc)=s.document().cloned()else{return};let Some(cat)=s.catalog.clone()else{return};
 let rows:HashMap<_,_>=doc.instances.iter().filter(|r|r.mode=="all"||r.mode==p.0.asset_mode).map(|r|(r.id.clone(),r.clone())).collect();let mut found=std::collections::HashSet::new();
 for (e,id,mut t) in &mut roots {if let Some(row)=rows.get(&id.0){let respawn=s.rendered.get(&id.0).is_some_and(|old|old.prop_id!=row.prop_id||old.lootable!=row.lootable||old.color_variant!=row.color_variant);if respawn{commands.entity(e).despawn();}else{*t=crate::showhome_kit::preview_prop_transform(row,doc.origin);found.insert(id.0.clone());}}else{commands.entity(e).despawn();}}
 for row in rows.values(){if !found.contains(&row.id){if let Ok(d)=cat.get(&row.prop_id){crate::showhome_kit::spawn_preview_prop(&mut commands,&server,row,d,doc.origin);}}}
 s.rendered=rows;
}

fn refresh_world(mut commands:Commands,mut s:ResMut<EditorState>,a:Res<EditorActive>){
 if !a.0{return}
 let ready=s.pending.as_mut().and_then(|(_,task)|check_ready(task));
 if let Some(result)=ready {let revision=s.pending.take().unwrap().0;if revision==s.version {let result=result.and_then(CurrentV3Preview::from_snapshot);match result{Ok(preview)=>{commands.insert_resource(CurrentLevel(Arc::new(preview.0.level.clone())));commands.insert_resource(preview);s.physics_version=revision;s.status="Preview collision and foliage ready".into();},Err(e)=>{s.failed_version=Some(revision);s.status=e;}}s.ui_revision+=1;}}
 if s.pending.is_none()&&s.version!=s.physics_version&&s.failed_version!=Some(s.version) {let Some(doc)=s.document().cloned()else{return};let map=s.map.clone();let root=crate::config::assets_root().to_path_buf();let revision=s.version;s.pending=Some((revision,AsyncComputeTaskPool::get().spawn(async move{load_with_placements(&root,&map,Some(&doc)).map_err(|e|e.to_string())})));}
}

fn in_ui(w:&Window,pos:Vec2)->bool{pos.x<310.||pos.x>w.width()-340.||pos.y<52.||pos.y>w.height()-90.}
fn ray_box(origin:Vec3,dir:Vec3,min:Vec3,max:Vec3)->Option<f32>{let mut near=0f32;let mut far=f32::INFINITY;for i in 0..3 {if dir[i].abs()<1e-7{if origin[i]<min[i]||origin[i]>max[i]{return None}}else{let a=(min[i]-origin[i])/dir[i];let b=(max[i]-origin[i])/dir[i];near=near.max(a.min(b));far=far.min(a.max(b));if far<near{return None}}}Some(near)}
fn mode(item:&EditableItem)->&str{match item{EditableItem::Prop(p)=>&p.mode,EditableItem::Foliage(p)=>&p.mode,EditableItem::Clip(p)=>&p.mode,EditableItem::Spawn(p)=>&p.mode,EditableItem::Extract(p)=>&p.mode,EditableItem::Loot(p)=>&p.mode}}
fn bounds(item:&EditableItem,origin:[f64;3],cat:&PropCatalog)->(Vec3,Vec3,Transform){let p=Vec3::from_array(bm::collision::design_to_bevy(item.position(),origin).map(|v|v as f32));match item{
 EditableItem::Prop(row)=>{let d=cat.get(&row.prop_id).map(|p|p.size_m).unwrap_or([1.;3]);let size=Vec3::new(d[0] as f32,d[2] as f32,d[1] as f32);(-size*Vec3::new(0.5,0.,0.5),size*Vec3::new(0.5,1.,0.5),crate::showhome_kit::preview_prop_transform(row,origin))},
 EditableItem::Foliage(f)=>{let size=Vec3::new(f.dimensions_m[0] as f32,f.dimensions_m[2] as f32,f.dimensions_m[1] as f32);(-size*Vec3::new(0.5,0.,0.5),size*Vec3::new(0.5,1.,0.5),Transform::from_translation(p).with_rotation(Quat::from_rotation_y(f.yaw_deg.to_radians() as f32)))},
 EditableItem::Clip(c)=>{let d=Vec3::new((c.max[0]-c.min[0]) as f32,(c.max[2]-c.min[2]) as f32,(c.max[1]-c.min[1]) as f32);(-d/2.,d/2.,Transform::from_translation(p))},
 _=>(Vec3::splat(-0.35),Vec3::splat(0.35),Transform::from_translation(p)),}}
fn box_lines(g:&mut Gizmos,min:Vec3,max:Vec3,t:Transform,color:Color){let v=[Vec3::new(min.x,min.y,min.z),Vec3::new(max.x,min.y,min.z),Vec3::new(max.x,min.y,max.z),Vec3::new(min.x,min.y,max.z),Vec3::new(min.x,max.y,min.z),Vec3::new(max.x,max.y,min.z),Vec3::new(max.x,max.y,max.z),Vec3::new(min.x,max.y,max.z)].map(|p|t.transform_point(p));for [i,j] in [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]{g.line(v[i],v[j],color)}}

fn draw_editor(mut s:ResMut<EditorState>,a:Res<EditorActive>,mouse:Res<ButtonInput<MouseButton>>,windows:Query<&Window,With<bevy::window::PrimaryWindow>>,camera:Query<(&Camera,&GlobalTransform),With<ViewCamera>>,level:Option<Res<CurrentLevel>>,preview:Option<Res<CurrentV3Preview>>,panels:Query<&Interaction,With<crate::build_editor_ui::EditorPanel>>,mut gizmos:Gizmos){
 if !a.0{return}let (Some(doc),Some(cat),Some(world),Some(preview))=(s.document().cloned(),s.catalog.clone(),level,preview)else{return};let teal=Color::srgb(0.1,0.9,0.75);
 for item in doc.items(){if mode(&item)!="all"&&mode(&item)!=preview.0.asset_mode{continue}if s.selected.as_deref()==Some(item.id())||!matches!(item,EditableItem::Prop(_)){let (lo,hi,t)=bounds(&item,doc.origin,&cat);box_lines(&mut gizmos,lo,hi,t,if s.selected.as_deref()==Some(item.id()){teal}else{Color::srgba(0.3,0.6,0.9,0.65)})}}
 let (Ok(w),Some((cam,transform)))=(windows.single(),camera.iter().next())else{return};let Some(pos)=w.cursor_position()else{return};if in_ui(w,pos)||panels.iter().any(|i|*i!=Interaction::None)||mouse.pressed(MouseButton::Right){return}
 let Ok(ray)=cam.viewport_to_world(transform,pos)else{return};let dir=*ray.direction;
 if let Some((d,_))=world.world.raycast(ray.origin,dir,500.) {let hit=ray.origin+dir*d;let mut point=[hit.x as f64+doc.origin[0],-hit.z as f64+doc.origin[1],hit.y as f64+doc.origin[2]];if s.snap{point=s.options.snap_position(point)}
  let centre=Vec3::from_array(bm::collision::design_to_bevy(point,doc.origin).map(|v|v as f32));for k in -8..=8{let off=k as f32*s.options.position_snap_m as f32;gizmos.line(centre+Vec3::new(off,0.012,-2.),centre+Vec3::new(off,0.012,2.),Color::srgba(0.1,0.8,0.65,0.25));gizmos.line(centre+Vec3::new(-2.,0.012,off),centre+Vec3::new(2.,0.012,off),Color::srgba(0.1,0.8,0.65,0.25));}
  if let Some(tool)=s.placement.clone(){if mouse.just_pressed(MouseButton::Left){let id=s.next_id("item");let item=match tool {
   PlaceTool::Prop(prop_id)=>EditableItem::Prop(PropInstance{id:id.clone(),prop_id,position:point,yaw_deg:0.,tilt_deg:None,scale:1.,color_variant:None,lootable:false,locked:false,mode:"all".into()}),
   PlaceTool::Hedge|PlaceTool::Bush=>EditableItem::Foliage(FoliageVolume{id:id.clone(),kind:if tool==PlaceTool::Bush{FoliageKind::Bush}else{FoliageKind::Hedge},position:point,yaw_deg:0.,dimensions_m:if tool==PlaceTool::Bush{[1.2,1.2,0.8]}else{[6.,1.2,3.]},density:1.,tint:"sage_hedge".into(),mode:"all".into(),locked:false}),
   PlaceTool::SpawnA|PlaceTool::SpawnB|PlaceTool::SpawnFfa=>EditableItem::Spawn(SpawnMarker{id:id.clone(),position:point,yaw_deg:0.,mode:if tool==PlaceTool::SpawnFfa{"ffa".into()}else{"tdm".into()},team:if tool==PlaceTool::SpawnFfa{None}else{Some(if tool==PlaceTool::SpawnB{"B"}else{"A"}.into())},group:None,locked:false}),
   PlaceTool::Clip=>EditableItem::Clip(PlayerClip{id:id.clone(),kind:"player_clip".into(),phys:"concrete".into(),min:[point[0]-2.,point[1]-0.15,point[2]],max:[point[0]+2.,point[1]+0.15,point[2]+3.],mode:"all".into(),locked:false}),
   PlaceTool::Extract=>EditableItem::Extract(ExtractMarker{id:id.clone(),name:"New extract".into(),position:point,yaw_deg:0.,shape:"sphere".into(),radius_m:2.,size_m:None,kind:"always".into(),parameters:ExtractParameters::default(),mode:"extraction".into(),locked:false}),
   PlaceTool::Loot=>EditableItem::Loot(LootSpot{id:id.clone(),position:point,loot_table:"residential_common".into(),tier:None,spawn_chance:1.,max_count:1,container_id:None,mode:"all".into(),locked:false}),PlaceTool::Select=>return};s.command(EditCommand::Add(item));s.selected=Some(id);}}
 }
 if s.placement.is_none()&&mouse.just_pressed(MouseButton::Left){let wall=world.world.raycast(ray.origin,dir,500.).map_or(500.,|(d,_)|d+0.08);let mut nearest=None;for item in doc.items(){if mode(&item)!="all"&&mode(&item)!=preview.0.asset_mode{continue}let (lo,hi,t)=bounds(&item,doc.origin,&cat);let inverse=t.to_matrix().inverse();let from=inverse.transform_point3(ray.origin);let direction=inverse.transform_vector3(dir);
  let distance=if let EditableItem::Prop(row)=&item{let key=(row.prop_id.clone(),row.lootable);if !s.shapes.contains_key(&key){let mut one=doc.clone();one.origin=[0.;3];let mut r=row.clone();r.id="probe".into();r.position=[0.;3];r.yaw_deg=0.;r.tilt_deg=None;r.scale=1.;r.mode="all".into();one.instances=vec![r];if let Ok(shapes)=instantiate_props(crate::config::assets_root(),&cat,&one,None){s.shapes.insert(key.clone(),shapes);}}
   s.shapes.get(&key).and_then(|shapes|shapes.iter().filter_map(|v|ray_hull(from,direction,v)).min_by(f32::total_cmp))
  }else{ray_box(from,direction,lo,hi)};
  if let Some(d)=distance{if d<=wall&&nearest.as_ref().is_none_or(|(old,_):&(f32,String)|d<*old){nearest=Some((d,item.id().to_string()))}}}s.selected=nearest.map(|(_,id)|id);s.ui_revision+=1;}
}

fn ray_hull(from:Vec3,dir:Vec3,hull:&ConvexVolume)->Option<f32>{let mut near=0f32;let mut far=f32::INFINITY;for p in &hull.planes{let n=Vec3::new(p[0] as f32,p[1] as f32,p[2] as f32);let distance=p[3] as f32-n.dot(from);let denominator=n.dot(dir);if denominator.abs()<1e-7{if distance<0.{return None}}else{let t=distance/denominator;if denominator<0.{near=near.max(t)}else{far=far.min(t)}if near>far{return None}}}Some(near)}

fn hide_game_ui(a:Res<EditorActive>,mut s:ResMut<EditorState>,mut nodes:Query<(Entity,&mut Node),(Without<ChildOf>,Without<crate::build_editor_ui::EditorUiRoot>)>){
 for (e,mut n) in &mut nodes{if a.0{if !s.hidden_ui.contains_key(&e){s.hidden_ui.insert(e,n.display);}n.display=Display::None;}else if let Some(display)=s.hidden_ui.remove(&e){n.display=display;}}
}
