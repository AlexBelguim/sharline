"""Pack v2's exact maps into four PNG sources for Bevy D2 texture arrays.

Run from the repo: python assets/maps/showhome/_src/pack_ground_arrays.py
Height stays 16-bit unsigned grayscale; no 8-bit or half-float conversion occurs.
The PNG strips are reinterpreted by Bevy ImageLoaderSettings.array_layout before upload.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=HERE.parent/'textures/v2'
OUT=ROOT/'game/assets/maps/showhome/ground_arrays'

def validate_shader():
    """Validate the real WGSL body with cached Naga, independently of Cargo's lock.

    Bevy imports are represented by small type-correct boundary stubs. A game
    runtime smoke test still validates the complete Bevy imports/pipeline layout.
    """
    source=(ROOT/'game/assets/shaders/showhome_ground.wgsl').read_text(encoding='utf-8')
    kept=[];import_depth=0;in_import=False
    for line in source.splitlines():
        if line.lstrip().startswith('#import'):in_import=True;import_depth=0
        if in_import:
            import_depth+=line.count('{')-line.count('}')
            if import_depth==0:in_import=False
            continue
        kept.append(line)
    source='\n'.join(kept)
    defs={'VERTEX_COLORS','VERTEX_TANGENTS','VERTEX_UVS_A'};stack=[];active=True;lines=[]
    for line in source.splitlines():
        word=line.strip()
        if word.startswith('#ifdef '):
            flag=word.split()[1];stack.append((active,flag in defs));active=active and flag in defs;continue
        if word=='#else':
            parent,flag=stack[-1];active=parent and not flag;continue
        if word=='#endif':active=stack.pop()[0];continue
        if active:lines.append(line)
    body='\n'.join(lines).replace('#{MATERIAL_BIND_GROUP}','2').replace('pbr_types::','')
    stub='''
const STANDARD_MATERIAL_FLAGS_ALPHA_MODE_RESERVED_BITS:u32=7u<<29u;
struct TestMaterial {base_color:vec4<f32>,flags:u32,perceptual_roughness:f32,metallic:f32,}
struct TestPbr {material:TestMaterial,V:vec3<f32>,N:vec3<f32>,diffuse_occlusion:vec3<f32>,specular_occlusion:f32,}
struct VertexOutput {@builtin(position) position:vec4<f32>,@location(0) world_position:vec4<f32>,@location(1) world_normal:vec3<f32>,@location(2) uv:vec2<f32>,@location(4) world_tangent:vec4<f32>,@location(5) color:vec4<f32>,}
struct FragmentOutput {@location(0) color:vec4<f32>,}
fn pbr_input_from_standard_material(v:VertexOutput,front:bool)->TestPbr {
 var p:TestPbr;p.material.base_color=v.color;p.material.flags=0u;p.material.perceptual_roughness=0.8;p.material.metallic=0.0;
 p.V=vec3<f32>(0.0,1.0,0.0);p.N=v.world_normal;p.diffuse_occlusion=vec3<f32>(1.0);p.specular_occlusion=1.0;return p;
}
fn calculate_tbn_mikktspace(n:vec3<f32>,t:vec4<f32>)->mat3x3<f32>{return mat3x3<f32>(t.xyz,t.w*cross(n,t.xyz),n);}
fn apply_pbr_lighting(p:TestPbr)->vec4<f32>{return p.material.base_color;}
fn main_pass_post_lighting_processing(p:TestPbr,c:vec4<f32>)->vec4<f32>{return c;}
'''
    temp=HERE/'.shader_validation';temp.mkdir(exist_ok=True)
    wgsl=temp/'ground_body.wgsl';wgsl.write_text(stub+body,encoding='utf-8')
    rust=temp/'validate.rs';rust.write_text('''extern crate naga;
fn main(){let path=std::env::args().nth(1).unwrap();let source=std::fs::read_to_string(path).unwrap();
let module=naga::front::wgsl::parse_str(&source).unwrap_or_else(|e|panic!("{}",e.emit_to_string(&source)));
naga::valid::Validator::new(naga::valid::ValidationFlags::all(),naga::valid::Capabilities::all()).validate(&module)
.unwrap_or_else(|e|panic!("{}",e.emit_to_string(&source)));println!("Naga WGSL body validation passed");}
''',encoding='utf-8')
    deps=ROOT/'game/target/x86_64-pc-windows-msvc/debug/deps'
    libs=list(deps.glob('libnaga-*.rlib'));assert libs,'Need an existing cached game Naga build'
    executable=temp/'validate.exe'
    subprocess.run(['rustc','--edition','2024',str(rust),'--extern','naga='+str(libs[0]),'-L','dependency='+str(deps),
                    '-L','dependency='+str(ROOT/'game/target/debug/deps'),'-o',str(executable)],check=True)
    subprocess.run([str(executable),str(wgsl)],check=True)
    (OUT/'SHADER_VALIDATION.json').write_text(json.dumps(dict(naga_WGSL_body_pass=True,
        source='game/assets/shaders/showhome_ground.wgsl',bevy_boundary_stubs=True,
        full_Bevy_pipeline_runtime_smoke_required=True),indent=2)+'\n',encoding='utf-8')
    for file in temp.iterdir():
        if file.is_file():file.unlink()
    temp.rmdir()

def main():
    manifest=json.loads((SOURCE/'manifest.json').read_text(encoding='utf-8'))
    names=list(manifest['materials']);size=1024
    OUT.mkdir(parents=True,exist_ok=True)
    for kind in ['albedo','normal','orm']:
        out=Image.new('RGBA',(size,size*len(names)))
        for i,name in enumerate(names):
            image=Image.open(SOURCE/manifest['materials'][name]['maps'][kind]).convert('RGBA')
            assert image.size==(size,size)
            out.paste(image,(0,i*size))
        out.save(OUT/(kind+'_array.png'),compress_level=3)
    height=np.zeros((size*(len(names)+1),size),np.uint16)
    for i,name in enumerate(names):
        path=SOURCE/manifest['materials'][name]['maps']['height']
        assert path.read_bytes()[24]==16,(name,'source is not PNG16')
        height[i*size:(i+1)*size]=np.asarray(Image.open(path),np.uint16)
    height[-size:]=np.asarray(Image.open(SOURCE/'macro_ground.png'),np.uint16)
    Image.fromarray(height,mode='I;16').save(OUT/'height_array.png',compress_level=3)
    doc=dict(version=1,width=size,height=size,colour_rows=len(names),height_rows=len(names)+1,
             macro_layer=len(names),height_format='R16Uint, manual bilinear /65535, exact PNG16',
             materials={name:dict(index=i,repeat_m=manifest['materials'][name]['repeat_m'],
                                  height_range_m=manifest['materials'][name]['height_range_m']) for i,name in enumerate(names)})
    (OUT/'arrays.json').write_text(json.dumps(doc,indent=2)+'\n',encoding='utf-8')
    checks=[]
    stored=Image.open(OUT/'height_array.png')
    for i,name in enumerate(names):
        a=np.asarray(Image.open(SOURCE/manifest['materials'][name]['maps']['height']),np.uint16)
        b=np.asarray(stored.crop((0,i*size,size,(i+1)*size)),np.uint16)
        assert np.array_equal(a,b),name+' height changed while packing'
        checks.append(name)
    (OUT/'VALIDATION.json').write_text(json.dumps(dict(pass_all=True,layers=checks,height_bits=16,
                                                      native_height_values_preserved=True,
                                                      colour_spaces=dict(albedo='sRGB',normal='linear',orm='linear',height='linear')),
                                                 indent=2)+'\n',encoding='utf-8')
    print('Packed',len(names),'surfaces and macro; all PNG16 height values unchanged.',flush=True)

if __name__=='__main__':
    if '--validate-shader' in sys.argv:validate_shader()
    else:main()
