"""Showhome RGBA ground masks: exact height blend preview and portable export contract.

Use inside Blender after geometry/import:
    setup_preview()       # alias install_preview; standard materials kept intact
    prepare_export()      # canonical simple PBR + COLOR_0 data + contract extras
    restore_preview()     # render/save .blend with the full preview graph

This module does not change mesh colour attributes, UVs, geometry or game code.
The four mask channels are never a base-colour multiplier or an opacity source.
"""
from pathlib import Path
import json
import math

HERE = Path(__file__).resolve().parent
V2 = HERE / 'textures/v2'
MANIFEST = json.loads((V2 / 'manifest.json').read_text(encoding='utf-8'))['materials']

BASES = {
    'M_GND_Asphalt': ('asphalt',4.0,'hard'),
    'M_GND_AsphaltOld': ('asphalt_cracked',4.0,'hard'),
    'M_GND_Paving': ('paving_slabs',2.4,'hard'),
    'M_GND_PavingSage': ('paving_slabs',2.4,'hard'),
    'M_GND_PavingClay': ('paving_slabs',2.4,'hard'),
    'M_GND_Grass': ('grass_lawn',2.0,'lawn'),
    'M_GND_GrassFar': ('grass_lawn',5.0,'lawn'),
    'M_GND_Soil': ('garden_soil',1.0,'earth'),
    'M_GND_SoilFar': ('garden_soil',3.0,'earth'),
    'M_GND_Gravel': ('gravel',1.0,'earth'),
    'M_GND_Sand': ('construction_sand',6.0,'earth'),
    'M_GND_Concrete': ('concrete_smooth',2.0,'hard'),
    'M_GND_Kerb': ('kerb_concrete',2.0,'hard'),
    'M_GND_Edging': ('edging_strip',2.0,'hard'),
    'M_GND_SteelEdging': ('metal_scaffold_tube',1.0,'hard'),
    'M_GND_Mulch': ('bark_mulch',1.0,'earth'),
    'M_GND_PaintSage': ('fibercement_panel',2.4,'hard'),
    'M_GND_PaintClay': ('fibercement_panel',2.4,'hard'),
}
ORDER = ['R','G','B','A']
STANDARD = {}
PREVIEW = {}
CONTRACT_VERSION = 2

def layer_names(surface_class):
    return dict(R='worn_dirt',G='gravel',
                B='grass_verge_weeds' if surface_class in ('hard','lawn') else 'worksite_mud_tracks',
                A='construction_sand' if surface_class=='hard' else 'worksite_mud_tracks')

def material_contract(name,texture,repeat,surface_class,uv='UVMap',colour_layer='Col',tint=(1,1,1)):
    layers=layer_names(surface_class)
    return dict(version=CONTRACT_VERSION,base_material=name,base_texture=texture,
                base_repeat_m=repeat,base_height_range_m=MANIFEST[texture]['height_range_m'],
                base_uv=uv,base_uv_role='Provided UV0: metre UVs, paving origin and east mirror already applied',
                base_tint_linear=list(tint),surface_class=surface_class,colour_attribute=colour_layer,
                colour_attribute_glTF='COLOR_0',colour_attribute_encoding='linear RGBA independent blend masks',
                opacity=1,vertex_colour_is_albedo=False,
                channels={k:dict(texture=v,repeat_m=MANIFEST[v]['repeat_m'],
                                 height_range_m=MANIFEST[v]['height_range_m'],maps=MANIFEST[v]['maps']) for k,v in layers.items()},
                order=ORDER,uv_overlays='design_world.xy / repeat_m',
                normal_space='Base normal: UV0 tangent frame to world. Overlay normals: design world XYZ. Normalize after each mix.',
                contract='assets/maps/showhome/kit/ground_blend_contract.json')

def write_contract(path=None):
    default_path=path is None
    path=Path(path) if path else HERE / 'kit/ground_blend_contract.json'
    contract=dict(version=CONTRACT_VERSION,
        axes=dict(design='x=east,y=north,z=up',glTF_Bevy='(x,z,-y)',
                  Bevy_world_to_design_xy='(world_position.x,-world_position.z)',
                  design_normal_to_Bevy='(normal.x,normal.z,-normal.y)'),
        colour0=dict(R='worn dirt',G='gravel spill',B='moss on hard/lawn, wet mud on earth',A='sand on hard, mud on lawn/earth'),
        formula=dict(order=ORDER,height_unit='metres',height_scale=.18,height_reference_m=.020,
                     d='mask + 0.18 * (next_height_m - current_height_m) / 0.020',
                     t='clamp((d - 0.25) / 0.50, 0, 1)',
                     w='t * t * (3 - 2 * t)',
                     endpoint_guards='mask <= 0: w=0; mask >= 1: w=1',
                     state='colour=mix(colour,next_colour,w); height=mix(height,next_height,w); ORM=mix(ORM,next_ORM,w); normal=normalize(mix(normal,next_normal,w))',
                     roughness_contrast=1.0,transition_contrast=2.0),
        macro=dict(texture='macro_ground.png',repeat_m=32,colour_space='linear',formula='final_albedo *= 1 + 0.12 * (macro - 0.5)',affects=['albedo']),
        maps_root='assets/maps/showhome/textures/v2/',
        sampler=dict(wrap_u='REPEAT',wrap_v='REPEAT',albedo_sRGB=True,normal_sRGB=False,orm_sRGB=False,height_sRGB=False,height_bits=16),
        export=dict(custom_shader_required=True,portable_shader='Simple canonical PBR base texture; custom preview node graph is not a glTF shader',
                    COLOR_0='Export named Col with export_vertex_color=NAME, export_vertex_color_name=Col, export_all_vertex_colors=False. Set active_color_index and render_color_index after bmesh.to_mesh. This retains actual linear RGBA masks as COLOR_0 instead of a fake white COLOR_0 and real COLOR_1. A never connects to opacity.',
                    standard_viewer='glTF normally multiplies COLOR_0 into albedo. A viewer using standard vertex-colour semantics will tint/darken these meshes. The game custom ground shader must interpret all four channels as masks.',
                    extras='Canonical material extras showhome_ground_blend contain material contract JSON; showhome_ground_colour0=blend_masks'),
        materials={n:material_contract(n,*spec) for n,spec in BASES.items()},
        preview=dict(shader='Blender exact sequential height blend, no geometric displacement',alpha=1,
                     AO='Blended ORM.R is retained. Blender occlusion export socket has no direct light multiply; no baked directional light.',
                     surface='Top ground normal sampling; kerb geometry uses its own standard material.'))
    path.parent.mkdir(parents=True,exist_ok=True)
    serialized=json.dumps(contract,indent=2)+'\n'
    path.write_text(serialized,encoding='utf-8')
    if default_path:(HERE/'ground_blend_contract.json').write_text(serialized,encoding='utf-8')
    return contract

def _bpy():
    import bpy
    return bpy

def _node(nt,kind,label=None):
    n=nt.nodes.new(kind)
    if label:n.label=label;n.name=label
    return n

def _plug(nt,value,socket):
    if hasattr(value,'is_output'):nt.links.new(value,socket)
    else:socket.default_value=value

def _math(nt,op,a,b=None,label=None):
    n=_node(nt,'ShaderNodeMath',label);n.operation=op
    _plug(nt,a,n.inputs[0])
    if b is not None:_plug(nt,b,n.inputs[1])
    return n.outputs[0]

def _vscale(nt,v,s,label=None):
    n=_node(nt,'ShaderNodeVectorMath',label);n.operation='SCALE'
    _plug(nt,v,n.inputs[0]);_plug(nt,s,n.inputs['Scale'])
    return n.outputs['Vector']

def _vop(nt,op,a,b=None,label=None):
    n=_node(nt,'ShaderNodeVectorMath',label);n.operation=op
    _plug(nt,a,n.inputs[0])
    if b is not None:_plug(nt,b,n.inputs[1])
    return n.outputs['Vector']

def _mixcolour(nt,a,b,w,label=None):
    n=_node(nt,'ShaderNodeMixRGB',label);n.blend_type='MIX';n.use_clamp=False
    _plug(nt,w,n.inputs[0]);_plug(nt,a,n.inputs[1]);_plug(nt,b,n.inputs[2])
    return n.outputs['Color']

def _mixfloat(nt,a,b,w,label=None):
    inv=_math(nt,'SUBTRACT',1.0,w)
    return _math(nt,'ADD',_math(nt,'MULTIPLY',a,inv),_math(nt,'MULTIPLY',b,w),label)

def _mixnormal(nt,a,b,w,label=None):
    inv=_math(nt,'SUBTRACT',1.0,w)
    return _vop(nt,'NORMALIZE',_vop(nt,'ADD',_vscale(nt,a,inv),_vscale(nt,b,w)),label=label)

def _image(nt,name,map_kind,uv):
    bpy=_bpy();e=MANIFEST[name]
    im=bpy.data.images.load(str(V2 / e['maps'][map_kind]),check_existing=True)
    im.colorspace_settings.name='sRGB' if map_kind=='albedo' else 'Non-Color'
    n=_node(nt,'ShaderNodeTexImage',name+' '+map_kind);n.image=im;n.extension='REPEAT';n.interpolation='Linear'
    nt.links.new(uv,n.inputs['Vector'])
    return n.outputs['Color']

def _world_uv(nt,position,repeat,label=None):
    split=_node(nt,'ShaderNodeSeparateXYZ');nt.links.new(position,split.inputs[0])
    combine=_node(nt,'ShaderNodeCombineXYZ',label)
    nt.links.new(split.outputs['X'],combine.inputs['X']);nt.links.new(split.outputs['Y'],combine.inputs['Y'])
    return _vscale(nt,combine.outputs[0],1/repeat)

def _sample(nt,texture,uv,base=False,uv_name='UVMap',normal_strength=1.0):
    alb=_image(nt,texture,'albedo',uv);orm=_image(nt,texture,'orm',uv)
    hn=_image(nt,texture,'height',uv)
    h=_math(nt,'MULTIPLY',hn,MANIFEST[texture]['height_range_m'],texture+' physical height m')
    rgbn=_image(nt,texture,'normal',uv)
    if base:
        n=_node(nt,'ShaderNodeNormalMap',texture+' base UV0 tangent normal');n.uv_map=uv_name
        n.inputs['Strength'].default_value=normal_strength;nt.links.new(rgbn,n.inputs['Color'])
        normal=n.outputs['Normal']
    else:
        # Horizontal ground top: overlay UVs are design world X/Y, not the possibly mirrored paving UV0.
        normal=_vop(nt,'NORMALIZE',_vop(nt,'SUBTRACT',_vscale(nt,rgbn,2),(1,1,1)),label=texture+' design normal')
    return alb,orm,h,normal

def _height_weight(nt,mask,current_h,next_h,channel):
    delta=_math(nt,'SUBTRACT',next_h,current_h,channel+' height delta m')
    d=_math(nt,'ADD',mask,_math(nt,'MULTIPLY',delta,.18/.020),channel+' d mask plus physical height')
    t=_math(nt,'DIVIDE',_math(nt,'SUBTRACT',d,.25),.50)
    t=_math(nt,'MINIMUM',_math(nt,'MAXIMUM',t,0.0),1.0,channel+' clamped transition')
    smooth=_math(nt,'MULTIPLY',_math(nt,'MULTIPLY',t,t),_math(nt,'SUBTRACT',3.0,_math(nt,'MULTIPLY',t,2.0)))
    active=_math(nt,'GREATER_THAN',mask,0.0);partial=_math(nt,'LESS_THAN',mask,1.0)
    guarded=_math(nt,'MULTIPLY',_math(nt,'MULTIPLY',smooth,active),partial)
    return _math(nt,'ADD',guarded,_math(nt,'SUBTRACT',1.0,partial),channel+' endpoint guarded weight')

def _tint(nt,colour,tint,label):
    if all(abs(v-1)<1e-7 for v in tint):return colour
    n=_node(nt,'ShaderNodeMixRGB',label);n.blend_type='MULTIPLY';n.inputs[0].default_value=1
    nt.links.new(colour,n.inputs[1]);n.inputs[2].default_value=(*tint,1)
    return n.outputs[0]

def create_preview_material(name,base_texture=None,repeat=None,surface_class=None,uv_name='UVMap',colour_layer='Col',tint=None):
    bpy=_bpy();standard=bpy.data.materials.get(name)
    key=_canonical_name(name)
    texture,nominal_repeat,cls=BASES[key]
    texture=base_texture or texture;repeat=repeat or nominal_repeat;surface_class=surface_class or cls
    if tint is None:tint=tuple(standard.get('showhome_ground_tint',[1,1,1])) if standard else (1,1,1)
    preview=bpy.data.materials.get(name+'__HeightPreview') or bpy.data.materials.new(name+'__HeightPreview')
    preview.use_nodes=True;nt=preview.node_tree;nt.nodes.clear()
    geometry=_node(nt,'ShaderNodeNewGeometry','Design world position')
    uv=_node(nt,'ShaderNodeUVMap','Original UV0 metre coordinates');uv.uv_map=uv_name
    col,orm,h,normal=_sample(nt,texture,uv.outputs['UV'],base=True,uv_name=uv_name,
                              normal_strength=MANIFEST[texture]['repeat_m']/repeat)
    col=_tint(nt,col,tint,'Original kit base tint')
    vc=_node(nt,'ShaderNodeVertexColor','RGBA blend data; never albedo or opacity');vc.layer_name=colour_layer
    split=_node(nt,'ShaderNodeSeparateColor','Independent R G B masks');split.mode='RGB'
    nt.links.new(vc.outputs['Color'],split.inputs['Color'])
    masks=dict(R=split.outputs['Red'],G=split.outputs['Green'],B=split.outputs['Blue'],A=vc.outputs['Alpha'])
    layers=layer_names(surface_class)
    for channel in ORDER:
        next_name=layers[channel]
        coord=_world_uv(nt,geometry.outputs['Position'],MANIFEST[next_name]['repeat_m'],channel+' metre projection')
        next_col,next_orm,next_h,next_normal=_sample(nt,next_name,coord)
        w=_height_weight(nt,masks[channel],h,next_h,channel)
        col=_mixcolour(nt,col,next_col,w,channel+' blended linear albedo')
        orm=_mixcolour(nt,orm,next_orm,w,channel+' blended linear ORM')
        h=_mixfloat(nt,h,next_h,w,channel+' resulting physical height')
        normal=_mixnormal(nt,normal,next_normal,w,channel+' normalized world normal')
    # Repeat 32m macro breakup affects albedo only; never the data masks or parallax height.
    macro_uv=_world_uv(nt,geometry.outputs['Position'],32,'32 metre macro projection')
    im=bpy.data.images.load(str(V2 / 'macro_ground.png'),check_existing=True);im.colorspace_settings.name='Non-Color'
    macro=_node(nt,'ShaderNodeTexImage','32m macro colour only');macro.image=im;macro.extension='REPEAT'
    nt.links.new(macro_uv,macro.inputs['Vector'])
    mult=_math(nt,'ADD',1.0,_math(nt,'MULTIPLY',.12,_math(nt,'SUBTRACT',macro.outputs['Color'],.5)))
    col=_vscale(nt,col,mult,'Final albedo with soft macro breakup')
    bs=_node(nt,'ShaderNodeBsdfPrincipled','Opaque painted ground');bs.inputs['Alpha'].default_value=1
    nt.links.new(col,bs.inputs['Base Color']);nt.links.new(normal,bs.inputs['Normal'])
    pack=_node(nt,'ShaderNodeSeparateColor','Blended AO roughness metalness');pack.mode='RGB'
    nt.links.new(orm,pack.inputs['Color']);nt.links.new(pack.outputs['Green'],bs.inputs['Roughness']);nt.links.new(pack.outputs['Blue'],bs.inputs['Metallic'])
    out=_node(nt,'ShaderNodeOutputMaterial');nt.links.new(bs.outputs['BSDF'],out.inputs['Surface'])
    contract=material_contract(key,texture,repeat,surface_class,uv_name,colour_layer,tint)
    preview['showhome_ground_blend']=json.dumps(contract,separators=(',',':'))
    preview['showhome_ground_colour0']='blend_masks';preview['showhome_ground_preview_only']=True
    preview.diffuse_color=(.6,.6,.5,1);preview.use_backface_culling=False
    # Deterministic readable node arrangement; graphs remain editable in .blend.
    for i,n in enumerate(nt.nodes):n.location=((i%12)*220,(i//12)*-190)
    if standard:
        standard['showhome_ground_blend']=json.dumps(contract,separators=(',',':'))
        standard['showhome_ground_colour0']='blend_masks';standard['showhome_ground_opacity']=1.0
        STANDARD[name]=standard;PREVIEW[name]=preview
    return preview

def _canonical_name(name):
    if name in BASES:return name
    for key in sorted(BASES,key=len,reverse=True):
        if name.startswith(key+'.') and name[len(key)+1:].isdigit():return key
    return None

def _sanitize_standard(material):
    """Remove established kit AO-colour multiply when Col has become RGBA mask data."""
    if not material.use_nodes:return
    nt=material.node_tree
    for n in list(nt.nodes):
        if n.type not in ('MIX','MIX_RGB'):continue
        inputs=[(sock,ln) for sock in n.inputs for ln in list(sock.links)]
        vc=[ln for _,ln in inputs if ln.from_node.type=='VERTEX_COLOR']
        if not vc:continue
        other=[ln.from_socket for sock,ln in inputs if ln.from_node.type!='VERTEX_COLOR']
        if not other:continue
        for out in n.outputs:
            for ln in list(out.links):nt.links.new(other[-1],ln.to_socket)
        nt.nodes.remove(n)
    for n in nt.nodes:
        if n.type=='BSDF_PRINCIPLED':
            for ln in list(n.inputs['Alpha'].links):nt.links.remove(ln)
            n.inputs['Alpha'].default_value=1
    material['showhome_ground_colour0']='blend_masks';material['showhome_ground_opacity']=1.0

def _find_mesh_mapping(material):
    bpy=_bpy()
    for ob in bpy.data.objects:
        if ob.type!='MESH' or not any(m==material for m in ob.data.materials):continue
        uv=ob.data.uv_layers[0].name if ob.data.uv_layers else 'UVMap'
        attr=ob.data.color_attributes.get('Col') or ob.data.color_attributes.active_color
        return uv,attr.name if attr else 'Col'
    return 'UVMap','Col'

def _existing_tint(material):
    bpy=_bpy()
    try:
        import props_lib as PL
        spec=PL._SPECS.get(material.name,{})
        if spec.get('tint') is not None:return tuple(spec['tint'])
    except ImportError:pass
    if material.get('showhome_ground_tint') is not None:return tuple(material['showhome_ground_tint'])
    if material.use_nodes:
        # Imported glTF baseColorFactor is usually a MULTIPLY mix with an unlinked colour input.
        for n in material.node_tree.nodes:
            if n.type=='MIX_RGB' and n.blend_type=='MULTIPLY':
                for s in n.inputs[1:3]:
                    if not s.is_linked:return tuple(s.default_value[:3])
            if n.type=='MIX' and getattr(n,'blend_type','')=='MULTIPLY':
                for i in [6,7]:
                    if not n.inputs[i].is_linked:return tuple(n.inputs[i].default_value[:3])
    return (1,1,1)

def setup_preview(material_base_names=None):
    bpy=_bpy();names=list(material_base_names) if material_base_names is not None else [m.name for m in bpy.data.materials if _canonical_name(m.name)]
    for name in names:
        m=bpy.data.materials.get(name);key=_canonical_name(name)
        if not m or not key:continue
        uv,col=_find_mesh_mapping(m);texture,repeat,cls=BASES[key]
        if m.get('repeat') is not None:repeat=float(m['repeat'][0])
        tint=_existing_tint(m);m['showhome_ground_tint']=list(tint)
        _sanitize_standard(m)
        create_preview_material(name,texture,repeat,cls,uv,col,tint)
    restore_preview();write_contract()
    return {k:v.name for k,v in PREVIEW.items()}

install_preview=setup_preview

def _swap(mapping):
    bpy=_bpy();count=0
    for ob in bpy.data.objects:
        if ob.type!='MESH':continue
        for i,mat in enumerate(ob.data.materials):
            if mat in mapping:ob.data.materials[i]=mapping[mat];count+=1
    return count

def prepare_export():
    """Use canonical glTF PBR nodes; caller exports ACTIVE COLOR_0 RGBA plus extras."""
    for m in STANDARD.values():_sanitize_standard(m)
    return _swap({PREVIEW[n]:m for n,m in STANDARD.items() if n in PREVIEW})

def prepare_mesh_attributes(objects):
    """Call after every bmesh split/triangulate and before export; retain linear mask data.

    Blender ACTIVE export reads the render colour index, not active_color alone.
    For production also pass export_vertex_color='NAME', export_vertex_color_name='Col',
    export_all_vertex_colors=False to avoid the exporter's fake white COLOR_0 fallback.
    """
    fixed=[]
    for ob in objects:
        if ob.type!='MESH':continue
        mesh=ob.data
        mask_mesh=any(_canonical_name(m.name) or m.get('showhome_ground_colour0')=='blend_masks'
                      for m in mesh.materials if m)
        ca=mesh.color_attributes.get('Col')
        if ca is None:
            if mask_mesh:raise ValueError(ob.name+' ground mask mesh has no Col attribute')
            continue
        if mask_mesh and ca.data_type!='FLOAT_COLOR':
            raise ValueError(ob.name+' mask must retain FLOAT_COLOR linear RGBA, got '+ca.data_type)
        index=mesh.color_attributes.find(ca.name)
        mesh.color_attributes.active_color=ca
        mesh.color_attributes.active_color_index=index
        mesh.color_attributes.render_color_index=index
        fixed.append(dict(object=ob.name,attribute=ca.name,domain=ca.domain,type=ca.data_type,
                          active_color_index=mesh.color_attributes.active_color_index,
                          render_color_index=mesh.color_attributes.render_color_index))
    return fixed

def restore_preview():
    return _swap({m:PREVIEW[n] for n,m in STANDARD.items() if n in PREVIEW})

def blend_reference(mask,current_h,next_h):
    """CPU scalar reference for external validation and the game implementation."""
    if mask<=0:return 0.0
    if mask>=1:return 1.0
    d=mask+.18*(next_h-current_h)/.020
    t=max(0,min(1,(d-.25)/.50))
    return t*t*(3-2*t)

def validate_blender():
    """Headless graph/export and rendered-weight validation; no production meshes touched."""
    import bpy
    import struct
    import sys
    from mathutils import Vector
    sys.path.insert(0,str(HERE));import props_lib as PL
    bpy.ops.wm.read_factory_settings(use_empty=True)
    STANDARD.clear();PREVIEW.clear()
    # Create real meshes with 0-alpha mask data, a common source of incorrect opacity.
    objects=[]
    for i,(name,(texture,repeat,cls)) in enumerate(BASES.items()):
        e=MANIFEST[texture]
        PL.spec(name,tex=str(V2/e['maps']['albedo']),normal=str(V2/e['maps']['normal']),
                orm=str(V2/e['maps']['orm']),repeat=repeat,rough=e['roughness'],vc=True)
        mesh=bpy.data.meshes.new('GBValidationMesh_'+str(i))
        mesh.from_pydata([(i,0,0),(i+1,0,0),(i+1,1,0),(i,1,0)],[],[(0,1,2,3)])
        uv=mesh.uv_layers.new(name='UVMap')
        for j,loop in enumerate(mesh.loops):uv.data[j].uv=(mesh.vertices[loop.vertex_index].co.x/repeat,mesh.vertices[loop.vertex_index].co.y/repeat)
        ca=mesh.color_attributes.new(name='Col',type='FLOAT_COLOR',domain='CORNER')
        for j in range(len(mesh.loops)):ca.data[j].color=(0,.35,.5,0)
        mesh.color_attributes.active_color=ca
        ob=bpy.data.objects.new('GBValidation_'+str(i),mesh);bpy.context.collection.objects.link(ob)
        ob.data.materials.append(PL.M(name));objects.append(ob)
    installed=setup_preview()
    assert len(installed)==len(BASES),(installed,len(BASES))
    for m in PREVIEW.values():
        bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
        assert bs.inputs['Alpha'].default_value==1 and not bs.inputs['Alpha'].is_linked,m.name
        assert any(n.type=='VERTEX_COLOR' for n in m.node_tree.nodes),m.name
    swapped=prepare_export();assert swapped==len(BASES),swapped
    for m in STANDARD.values():
        for n in m.node_tree.nodes:
            if n.type=='VERTEX_COLOR':assert all(not o.is_linked for o in n.outputs),m.name+' mask still feeds base'
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objects:ob.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    kit=HERE/'kit';kit.mkdir(exist_ok=True)
    path=kit/'_ground_blend_validation.glb'
    bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,
                              export_yup=True,export_vertex_color='ACTIVE',export_extras=True)
    data=path.read_bytes();length=struct.unpack_from('<I',data,12)[0]
    gltf=json.loads(data[20:20+length].decode('utf-8'))
    attrs=[p['attributes'] for m in gltf['meshes'] for p in m['primitives']]
    assert all('COLOR_0' in a for a in attrs),attrs
    for a in attrs:assert gltf['accessors'][a['COLOR_0']]['type']=='VEC4',a
    assert all('showhome_ground_blend' in m.get('extras',{}) for m in gltf['materials']),gltf['materials']
    restored=restore_preview();assert restored==len(BASES),restored
    # Numerically test the actual Blender Math node graph by rendering emissive swatches to float EXR.
    for ob in objects:ob.hide_render=True
    cases=[(0,.005,.023),(.15,.005,.023),(.25,.020,.008),(.5,.005,.023),(.5,.025,.002),(.75,.005,.023),(1,.025,.002)]
    for i,(mask,current,nxt) in enumerate(cases):
        bpy.ops.mesh.primitive_plane_add(size=1,location=(i+.5,.5,0))
        ob=bpy.context.object;mat=bpy.data.materials.new('Weight_'+str(i));mat.use_nodes=True;nt=mat.node_tree;nt.nodes.clear()
        weight=_height_weight(nt,mask,current,nxt,'test')
        em=_node(nt,'ShaderNodeEmission');nt.links.new(weight,em.inputs['Color']);em.inputs['Strength'].default_value=1
        out=_node(nt,'ShaderNodeOutputMaterial');nt.links.new(em.outputs[0],out.inputs['Surface']);ob.data.materials.append(mat)
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=1
    scene.render.resolution_x=700;scene.render.resolution_y=100;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='OPEN_EXR';scene.render.image_settings.color_mode='RGBA';scene.render.image_settings.color_depth='32'
    scene.render.film_transparent=True;scene.view_settings.view_transform='Standard'
    camdata=bpy.data.cameras.new('WeightCamera');cam=bpy.data.objects.new('WeightCamera',camdata);bpy.context.collection.objects.link(cam)
    cam.location=(3.5,.5,10);cam.rotation_euler=(0,0,0);camdata.type='ORTHO';camdata.ortho_scale=7;scene.camera=cam
    scene.render.filepath=str(kit/'_ground_blend_weight_validation.exr')
    bpy.ops.render.render(write_still=True)
    im=bpy.data.images.load(scene.render.filepath,check_existing=False);pixels=list(im.pixels)
    results=[]
    for i,case in enumerate(cases):
        idx=(50*700+100*i+50)*4;actual=pixels[idx];expected=blend_reference(*case)
        assert abs(actual-expected)<.003,(case,actual,expected)
        results.append(dict(mask=case[0],current_height_m=case[1],next_height_m=case[2],expected=expected,blender_rendered=actual))
    report=dict(pass_all=True,preview_material_count=len(PREVIEW),opaque_with_alpha_mask_zero=True,
                mask_albedo_multiply_removed=True,canonical_export_swap_count=swapped,
                restore_preview_swap_count=restored,exported_RGBA_COLOR_0=True,
                exported_material_contract_extras=True,weight_graph_actual_render_tests=results,
                max_render_weight_error=max(abs(r['expected']-r['blender_rendered']) for r in results))
    (kit/'ground_blend_validation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('GROUND BLEND VALIDATED',json.dumps(report),flush=True)
    return report

if __name__=='__main__':
    import sys
    if '--self-test' in sys.argv:validate_blender()
    else:
        write_contract()
        print('Wrote',HERE/'kit/ground_blend_contract.json')
