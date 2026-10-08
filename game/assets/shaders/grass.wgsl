// Lawn grass for Showhome (val_etf/src/foliage/grass.rs): the mown lawn and the taller tufts at its edges.
//
// A StandardMaterial extension, main pass only: the grass stays out of the depth prepass (so screen-space contact
// shadows never see the strands; grass casts no shadow of any kind) and out of the shadow maps. Both kinds take their colour from the lawn's own ground texture (the base layer of the Showhome ground arrays,
// at the lawn's UV, with the ground's tint and macro variation) and light like the lawn, so they read as part of
// it rather than as objects on it. Neither casts shadows.
//
// Mown lawn (shells; mesh without UV_1): the kit's lawn triangles (ground.glb, M_GND_Grass) drawn once per layer
// (MeshTag = layer), each copy lifted by its layer's height. Layer 0 is a dark thatch just above the ground; on
// the others a fragment survives only inside a strand: one per cell of two overlapping jittered grids, each
// strand with its own height and lean, tapering to its tip. Strands thin out where the ground masks show worn
// dirt, gravel or mud, and with distance, where the colour also settles to the plain ground; past the fade
// distance only the ground is left. Wind bends the tips and runs a soft sheen over the lawn.
//   POSITION, NORMAL, TANGENT, UV_0 (the ground's UV), COLOR = ground blend masks (R dirt, G gravel, B moss,
//   A mud), as exported.
//
// Tufts (mesh with UV_1): blade strips around a root, shrinking into the lawn with distance.
//   POSITION = the tuft's root (chunk frame), COLOR xyz = this corner's offset from the root, w = height along
//   the blade (0 root .. 1 tip), NORMAL (mostly up), UV_0 = the lawn's UV at the root, UV_1 = (blade value, 0).

#import bevy_pbr::{
    mesh_functions,
    mesh_view_bindings::view,
    view_transformations::position_world_to_clip,
}

#import bevy_pbr::{
    forward_io::{Vertex, VertexOutput, FragmentOutput},
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing, calculate_tbn_mikktspace},
}

struct Grass {
    // xyz: the direction the wind blows toward (world, horizontal, unit)
    wind_dir: vec4<f32>,
    // x: tip sway (m), y: angular frequency (rad/s), z: wave number along the wind (rad/m), w: gust lean
    wind: vec4<f32>,
    // x: time (s), y: last frame's time, z: layer count, w: lawn height (m)
    time: vec4<f32>,
    // lawn strands: x cell size (m), y root radius (share of a cell), z shortest strand (share), w tip lean (share)
    shape: vec4<f32>,
    // x: fade start, y: fade end (m from the camera), z, w: ground mask range over which strands thin out
    fade: vec4<f32>,
    // x: root shade, y: tip lift, z: value jitter, w: patch strength
    shade: vec4<f32>,
    // rgb: tip tint, w: patch size (m)
    tip: vec4<f32>,
    // rgb: the ground material's tint, w: its macro strength
    ground_tint: vec4<f32>,
    // x: macro repeat (m), y: wind sheen, z: base normal scale, w: unused
    ground: vec4<f32>,
    // lawn patches: rgb the driest and the lushest tint
    dry: vec4<f32>,
    lush: vec4<f32>,
    // x: base albedo layer, y: macro height layer
    layers: vec4<u32>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var<uniform> grass: Grass;
@group(#{MATERIAL_BIND_GROUP}) @binding(101) var ground_albedo: texture_2d_array<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(102) var ground_sampler: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(103) var ground_normal: texture_2d_array<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(104) var ground_orm: texture_2d_array<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(105) var ground_height: texture_2d_array<u32>;

const TAU: f32 = 6.283185307179586;

struct Varying {
    @builtin(position) position: vec4<f32>,
    @location(0) world_position: vec4<f32>,
    @location(1) world_normal: vec3<f32>,
    // The lawn's UV (base ground texture).
    @location(2) uv: vec2<f32>,
    // Lawn: the ground blend masks. Tufts: unused.
    @location(3) masks: vec4<f32>,
    // Lawn: x layer height (0 thatch .. 1 top), y ground macro factor. Tufts: x height along the blade,
    // y macro factor, z blade value, w distance fade (0 near .. 1 gone).
    @location(4) data: vec4<f32>,
    @location(5) world_tangent: vec4<f32>,
    @location(6) @interpolate(flat) instance_index: u32,
}

// ------------------------------------------------------------------------------------------------- helpers

fn pcg(v: u32) -> u32 {
    let s = v * 747796405u + 2891336453u;
    let w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
    return (w >> 22u) ^ w;
}

// Four random numbers in 0..1 for an integer cell.
fn hash4(cell: vec2<i32>, salt: u32) -> vec4<f32> {
    var h = pcg(bitcast<u32>(cell.x) ^ pcg(bitcast<u32>(cell.y) ^ salt));
    let a = h;
    h = pcg(h);
    let b = h;
    h = pcg(h);
    let c = h;
    h = pcg(h);
    return vec4<f32>(vec4<u32>(a, b, c, h) >> vec4<u32>(8u)) / 16777216.0;
}

// Smooth value noise, 0..1.
fn value_noise(p: vec2<f32>) -> f32 {
    let i = vec2<i32>(floor(p));
    let f = fract(p);
    let u = f * f * (3.0 - 2.0 * f);
    let a = hash4(i, 91u).x;
    let b = hash4(i + vec2<i32>(1, 0), 91u).x;
    let c = hash4(i + vec2<i32>(0, 1), 91u).x;
    let d = hash4(i + vec2<i32>(1, 1), 91u).x;
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}

// The ground's macro variation (showhome_ground.wgsl): 1 + strength * (macro - 0.5), from the PNG16 macro layer.
fn ground_macro(world: vec3<f32>) -> f32 {
    let size = vec2<i32>(textureDimensions(ground_height, 0));
    let uv = vec2<f32>(world.x, world.z) / grass.ground.x;
    let texel = fract(uv) * vec2<f32>(size) - vec2<f32>(0.5);
    let p = vec2<i32>(floor(texel));
    let f = fract(texel);
    let layer = i32(grass.layers.y);
    let a = f32(textureLoad(ground_height, ((p % size) + size) % size, layer, 0).r);
    let b = f32(textureLoad(ground_height, ((p + vec2<i32>(1, 0)) % size + size) % size, layer, 0).r);
    let c = f32(textureLoad(ground_height, ((p + vec2<i32>(0, 1)) % size + size) % size, layer, 0).r);
    let d = f32(textureLoad(ground_height, ((p + vec2<i32>(1, 1)) % size + size) % size, layer, 0).r);
    let m = mix(mix(a, b, f.x), mix(c, d, f.x), f.y) / 65535.0;
    return 1.0 + grass.ground_tint.w * (m - 0.5);
}

// A wave travelling downwind (-1..1), broken up a little per place.
fn wind_wave(p: vec2<f32>, t: f32) -> f32 {
    let along = dot(p, grass.wind_dir.xz);
    let phase = along * grass.wind.z + sin(p.x * 0.73 + p.y * 1.13) * 0.8;
    let w = grass.wind.y;
    return sin(w * t - phase) * 0.7 + sin(w * 2.31 * t - phase * 1.7) * 0.3;
}

// Slow gusts (0.3..1).
fn gust(p: vec2<f32>, t: f32) -> f32 {
    let along = dot(p, grass.wind_dir.xz);
    return 0.65 + 0.35 * sin(t * 0.31 - along * 0.09);
}

// How far a tip at `p` is pushed downwind (metres, times the sway weight), at time t.
fn wind_push(p: vec2<f32>, t: f32) -> vec2<f32> {
    let g = gust(p, t);
    let side = vec2<f32>(-grass.wind_dir.z, grass.wind_dir.x);
    let flutter = sin(grass.wind.y * 1.41 * t + dot(p, vec2<f32>(2.1, 1.7)));
    return (grass.wind_dir.xz * (wind_wave(p, t) * g + grass.wind.w * g) + side * flutter * 0.3) * grass.wind.x;
}

// Distance fade: 0 near, 1 at (and past) the fade end.
fn distance_fade(world: vec3<f32>) -> f32 {
    return smoothstep(grass.fade.x, grass.fade.y, distance(view.world_position.xyz, world));
}

// ------------------------------------------------------------------------------------------------- lawn strands

struct Strand {
    // 1 inside a strand (or on the thatch), 0 not
    hit: f32,
    // the strand's own random number (0..1)
    value: f32,
}

// One grid of strands: cells `spacing` apart in `q` (metres), with this salt. `h` = layer height (0..1),
// `keep` = share of strands that grow here, `bend` = wind push at the tip (metres).
fn strand_grid(q: vec2<f32>, spacing: f32, salt: u32, h: f32, keep: f32, bend: vec2<f32>) -> Strand {
    var s: Strand;
    let g = q / spacing;
    let cell = floor(g);
    let f = g - cell;
    let r = hash4(vec2<i32>(cell), salt);
    s.value = r.z;
    s.hit = 0.0;
    let tall = mix(grass.shape.z, 1.0, r.z);
    if r.w >= keep || h > tall {
        return s;
    }
    let a = h / tall;
    let angle = fract((r.x + r.y) * 7.31) * TAU;
    let lean = vec2<f32>(cos(angle), sin(angle)) * grass.shape.w + bend / spacing;
    let centre = vec2<f32>(0.3) + 0.4 * r.xy + lean * a * a;
    let radius = grass.shape.y * sqrt(max(1.0 - a, 0.0)) * (0.8 + 0.4 * r.x);
    s.hit = select(0.0, 1.0, length(f - centre) < radius);
    return s;
}

// Is there lawn at this shell fragment? `h` = layer height (0..1), `masks` = ground blend masks.
fn lawn_strand(world: vec3<f32>, h: f32, masks: vec4<f32>, t: f32) -> Strand {
    let fade = distance_fade(world);
    let dirt = max(max(masks.r, masks.g), masks.a);
    let ground_keep = 1.0 - smoothstep(grass.fade.z, grass.fade.w, dirt);
    let keep = ground_keep * (1.0 - fade);
    var s: Strand;
    if h <= 0.0 {
        // Thatch: everywhere the lawn is green, dissolving over the dirt and with distance.
        let r = hash4(vec2<i32>(floor(world.xz / grass.shape.x)), 7u);
        s.value = r.z;
        s.hit = select(0.0, 1.0, r.w < keep);
        return s;
    }
    let bend = wind_push(world.xz, t);
    s = strand_grid(world.xz, grass.shape.x, 1u, h, keep, bend);
    if s.hit < 0.5 {
        // The second grid, larger and turned, breaks up the first one's rows.
        let q = vec2<f32>(0.8 * world.x - 0.6 * world.z, 0.6 * world.x + 0.8 * world.z);
        s = strand_grid(q, grass.shape.x * 1.31, 2u, h, keep, bend);
    }
    return s;
}

// The layer height (0..1) of shell layer `layer`.
fn layer_height(layer: u32) -> f32 {
    let n = max(grass.time.z, 2.0);
    return f32(layer) / (n - 1.0);
}

// ------------------------------------------------------------------------------------------------- vertex

@vertex
fn vertex(v: Vertex) -> Varying {
    var out: Varying;
    let world_from_local = mesh_functions::get_world_from_local(v.instance_index);
    let base = mesh_functions::mesh_position_local_to_world(world_from_local, vec4<f32>(v.position, 1.0)).xyz;
    var color = vec4<f32>(0.0);
#ifdef VERTEX_COLORS
    color = v.color;
#endif
    var uv = vec2<f32>(0.0);
#ifdef VERTEX_UVS_A
    uv = v.uv;
#endif
    var world = base;
#ifdef VERTEX_UVS_B
    // Tuft blade corner: shrink toward the root with distance, sway by the height along the blade.
    let fade = distance_fade(base);
    let s = 1.0 - fade;
    let sway = color.w * color.w * s;
    let offset = color.xyz * s;
    let push = wind_push(base.xz, grass.time.x) * sway;
    // Bend: the tip moves sideways and drops a little (keeps the blade's length).
    world = base + offset + vec3<f32>(push.x, -0.3 * length(push), push.y);
    out.data = vec4<f32>(color.w, ground_macro(base), v.uv_b.x, fade);
    out.masks = vec4<f32>(0.0);
#else
    // Lawn shell: the lawn lifted by this layer's height (the thatch sits 1.5 mm up).
    let h = layer_height(mesh_functions::get_tag(v.instance_index));
    world = base + vec3<f32>(0.0, max(h * grass.time.w, 0.0015), 0.0);
    out.data = vec4<f32>(h, ground_macro(base), 0.0, 0.0);
    out.masks = color;
#endif
    out.world_position = vec4<f32>(world, 1.0);
    out.position = position_world_to_clip(world);
    out.uv = uv;
    out.instance_index = v.instance_index;
    out.world_normal = vec3<f32>(0.0, 1.0, 0.0);
    out.world_tangent = vec4<f32>(1.0, 0.0, 0.0, 1.0);
#ifdef VERTEX_NORMALS
    out.world_normal = mesh_functions::mesh_normal_local_to_world(v.normal, v.instance_index);
#endif
#ifdef VERTEX_TANGENTS
    out.world_tangent = mesh_functions::mesh_tangent_local_to_world(world_from_local, v.tangent, v.instance_index);
#endif
    return out;
}

// ------------------------------------------------------------------------------------------------- fragment


@fragment
fn fragment(in: Varying, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    let world = in.world_position.xyz;
    let duv_dx = dpdx(in.uv);
    let duv_dy = dpdy(in.uv);
    let base_layer = i32(grass.layers.x);
    let macro_factor = in.data.y;

    var vo: VertexOutput;
    vo.position = in.position;
    vo.world_position = in.world_position;
    vo.world_normal = in.world_normal;
#ifdef VERTEX_UVS_A
    vo.uv = in.uv;
#endif
#ifdef VERTEX_UVS_B
    vo.uv_b = vec2<f32>(0.0);
#endif
#ifdef VERTEX_TANGENTS
    vo.world_tangent = in.world_tangent;
#endif
#ifdef VERTEX_COLORS
    vo.color = vec4<f32>(1.0);
#endif
#ifdef VERTEX_OUTPUT_INSTANCE_INDEX
    vo.instance_index = in.instance_index;
#endif
#ifdef VISIBILITY_RANGE_DITHER
    vo.visibility_range_dither = 0;
#endif

#ifdef VERTEX_UVS_B
    // ---- Tuft blade.
    let along = in.data.x;
    let fade = in.data.w;
    // One lawn colour per tuft (its UV is the root's): a soft mip, so it is the lawn's local average.
    let lawn = textureSampleLevel(ground_albedo, ground_sampler, in.uv, base_layer, 3.0).rgb;
    let orm = textureSampleLevel(ground_orm, ground_sampler, in.uv, base_layer, 3.0).rgb;
    var shade = mix(grass.shade.x, grass.shade.y, smoothstep(0.0, 1.0, along)) * in.data.z;
    shade = mix(shade, 1.0, fade);
    let tint = mix(vec3<f32>(1.0), grass.tip.rgb, along * (1.0 - fade));
    let colour = lawn * grass.ground_tint.rgb * macro_factor * tint * shade;
    let N = normalize(in.world_normal);
    vo.world_normal = N;
    var pbr = pbr_input_from_standard_material(vo, is_front);
    pbr.world_normal = N;
    pbr.N = N;
    pbr.material.perceptual_roughness = orm.g;
    pbr.diffuse_occlusion *= vec3<f32>(mix(orm.r, 1.0, along));
#else
    // ---- Lawn shell.
    let h = in.data.x;
    let strand = lawn_strand(world, h, in.masks, grass.time.x);
    let lawn = textureSampleGrad(ground_albedo, ground_sampler, in.uv, base_layer, duv_dx, duv_dy).rgb;
    let orm = textureSampleGrad(ground_orm, ground_sampler, in.uv, base_layer, duv_dx, duv_dy).rgb;
    let nmap = textureSampleGrad(ground_normal, ground_sampler, in.uv, base_layer, duv_dx, duv_dy).rgb * 2.0 - 1.0;
    if strand.hit < 0.5 {
        discard;
    }
    // The colour settles to the plain ground before the strands thin out, so the far lawn is the ground's
    // colour with a little texture, and nothing changes where the shells end.
    let d = distance(view.world_position.xyz, world);
    let fade = smoothstep(grass.fade.x * 0.5, mix(grass.fade.x, grass.fade.y, 0.6), d);
    // Darker toward the roots, lighter and a little warmer at the tips; each strand a little different.
    var shade = mix(grass.shade.x, grass.shade.y, pow(h, 0.85));
    shade *= 1.0 + grass.shade.z * (strand.value * 2.0 - 1.0) * h;
    // Slow, irregular patches (mown stripes, drier spots), and the sheen of a gust running over the lawn.
    let patch_noise = value_noise(world.xz / grass.tip.w) * 0.65 + value_noise(world.xz / grass.tip.w * 2.7 + 17.0) * 0.35;
    shade *= 1.0 + grass.shade.w * (patch_noise * 2.0 - 1.0);
    let patch_tint = mix(grass.lush.rgb, grass.dry.rgb, smoothstep(0.2, 0.8, patch_noise));
    shade *= 1.0 + grass.ground.y * h * h * wind_wave(world.xz * 0.6, grass.time.x * 0.8) * gust(world.xz, grass.time.x);
    shade = mix(shade, 1.0, fade);
    let tint = mix(vec3<f32>(1.0), grass.tip.rgb, h * (1.0 - fade)) * mix(patch_tint, vec3<f32>(1.0), fade);
    let colour = lawn * grass.ground_tint.rgb * macro_factor * tint * shade;
    // The lawn's own normal (normal map in its UV frame), so the far end matches the ground exactly.
    var N = normalize(in.world_normal);
#ifdef VERTEX_TANGENTS
    let tbn = calculate_tbn_mikktspace(in.world_normal, in.world_tangent);
    N = normalize(tbn * vec3<f32>(nmap.xy * grass.ground.z, nmap.z));
#endif
    var pbr = pbr_input_from_standard_material(vo, is_front);
    pbr.N = N;
    pbr.material.perceptual_roughness = orm.g;
    pbr.material.metallic = orm.b;
    pbr.diffuse_occlusion *= vec3<f32>(orm.r);
    pbr.specular_occlusion *= orm.r;
#endif
    pbr.material.base_color = vec4<f32>(colour, 1.0);
    var out: FragmentOutput;
    out.color = apply_pbr_lighting(pbr);
    out.color = main_pass_post_lighting_processing(pbr, out.color);
    return out;
}

