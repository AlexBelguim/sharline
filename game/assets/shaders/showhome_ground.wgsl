// Four exact material arrays; COLOR_0 is independent RGBA masks, never opacity.
#import bevy_pbr::{
    pbr_types,
    pbr_fragment::pbr_input_from_standard_material,
    pbr_functions::calculate_tbn_mikktspace,
}

#ifdef PREPASS_PIPELINE
#import bevy_pbr::{
    prepass_io::{VertexOutput, FragmentOutput},
    pbr_deferred_functions::deferred_output,
}
#else
#import bevy_pbr::{
    forward_io::{VertexOutput, FragmentOutput},
    pbr_functions::{apply_pbr_lighting, main_pass_post_lighting_processing},
}
#endif

struct GroundParams {
    indices: vec4<u32>,
    extra_indices: vec4<u32>,
    repeats: vec4<f32>,
    heights: vec4<f32>,
    extra: vec4<f32>,
    tint: vec4<f32>,
    parallax: vec4<f32>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var<uniform> ground: GroundParams;
@group(#{MATERIAL_BIND_GROUP}) @binding(101) var ground_albedo: texture_2d_array<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(102) var ground_sampler: sampler;
@group(#{MATERIAL_BIND_GROUP}) @binding(103) var ground_normal: texture_2d_array<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(104) var ground_orm: texture_2d_array<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(105) var ground_height: texture_2d_array<u32>;

struct Surface {
    colour: vec3<f32>,
    orm: vec3<f32>,
    height_m: f32,
    normal: vec3<f32>,
}

fn wrap_pixel(pixel: vec2<i32>, size: vec2<i32>) -> vec2<i32> {
    return ((pixel % size) + size) % size;
}

// Integer textureLoad preserves the sixteen source bits. Manual bilinear matches
// the repeating Blender image sampler without optional float filtering features.
fn height16(uv: vec2<f32>, layer: u32) -> f32 {
    let size = vec2<i32>(textureDimensions(ground_height, 0));
    let texel = fract(uv) * vec2<f32>(size) - vec2<f32>(0.5);
    let p = vec2<i32>(floor(texel));
    let f = fract(texel);
    let a = f32(textureLoad(ground_height, wrap_pixel(p, size), i32(layer), 0).r);
    let b = f32(textureLoad(ground_height, wrap_pixel(p + vec2<i32>(1, 0), size), i32(layer), 0).r);
    let c = f32(textureLoad(ground_height, wrap_pixel(p + vec2<i32>(0, 1), size), i32(layer), 0).r);
    let d = f32(textureLoad(ground_height, wrap_pixel(p + vec2<i32>(1, 1), size), i32(layer), 0).r);
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y) / 65535.0;
}

fn sample_surface(layer: u32, uv: vec2<f32>, height_range: f32, dx: vec2<f32>, dy: vec2<f32>) -> Surface {
    var s: Surface;
    s.colour = textureSampleGrad(ground_albedo, ground_sampler, uv, i32(layer), dx, dy).rgb;
    s.orm = textureSampleGrad(ground_orm, ground_sampler, uv, i32(layer), dx, dy).rgb;
    s.normal = normalize(textureSampleGrad(ground_normal, ground_sampler, uv, i32(layer), dx, dy).rgb * 2.0 - 1.0);
    s.height_m = height16(uv, layer) * height_range;
    return s;
}

// Exactly ground_blend.py and ground_blend_contract.json, in metres.
fn height_weight(mask: f32, current_height_m: f32, next_height_m: f32) -> f32 {
    if mask <= 0.0 { return 0.0; }
    if mask >= 1.0 { return 1.0; }
    let d = mask + 0.18 * (next_height_m - current_height_m) / 0.020;
    let t = clamp((d - 0.25) / 0.50, 0.0, 1.0);
    return t * t * (3.0 - 2.0 * t);
}

fn blend_surface(current: Surface, next: Surface, mask: f32) -> Surface {
    let w = height_weight(mask, current.height_m, next.height_m);
    var s: Surface;
    s.colour = mix(current.colour, next.colour, w);
    s.orm = mix(current.orm, next.orm, w);
    s.height_m = mix(current.height_m, next.height_m, w);
    s.normal = normalize(mix(current.normal, next.normal, w));
    return s;
}

fn layer_index(i: u32) -> u32 {
    if i < 4u { return ground.indices[i]; }
    return ground.extra_indices.x;
}

fn layer_repeat(i: u32) -> f32 {
    if i < 4u { return ground.repeats[i]; }
    return ground.extra.x;
}

fn layer_height(i: u32) -> f32 {
    if i < 4u { return ground.heights[i]; }
    return ground.extra.y;
}

// Restrained base relief; depth is physical height / metre repeat. This keeps the
// existing kit UVs and does not replace the game's other depth/foliage materials.
fn base_relief(uv: vec2<f32>, tangent_view: vec3<f32>) -> vec2<f32> {
    if ground.parallax.x <= 0.0 { return uv; }
    let steps = max(ground.parallax.y, 1.0);
    let delta = -tangent_view.xy / max(abs(tangent_view.z), 0.15)
        * (ground.heights.x / ground.repeats.x) / steps;
    let depth_step = 1.0 / steps;
    var depth = 0.0;
    var out_uv = uv;
    var surface_depth = 1.0 - height16(out_uv, ground.indices.x);
    for (var step = 0u; step < 24u; step += 1u) {
        if depth >= surface_depth || f32(step) >= steps { break; }
        out_uv += delta;
        depth += depth_step;
        surface_depth = 1.0 - height16(out_uv, ground.indices.x);
    }
    return out_uv;
}

@fragment
fn fragment(vertex_output: VertexOutput, @builtin(front_facing) is_front: bool) -> FragmentOutput {
    var in = vertex_output;
    var masks = vec4<f32>(0.0);
#ifdef VERTEX_COLORS
    masks = clamp(in.color, vec4<f32>(0.0), vec4<f32>(1.0));
    // Standard PBR must never tint by mask RGB or become transparent from mask A.
    in.color = vec4<f32>(1.0);
#endif
    var pbr = pbr_input_from_standard_material(in, is_front);
    var base_uv = vec2<f32>(0.0);
#ifdef VERTEX_UVS_A
    base_uv = in.uv;
#endif
#ifdef VERTEX_TANGENTS
    let tbn = calculate_tbn_mikktspace(in.world_normal, in.world_tangent);
    let tangent_view = vec3<f32>(dot(pbr.V, tbn[0]), dot(pbr.V, tbn[1]), dot(pbr.V, tbn[2]));
    base_uv = base_relief(base_uv, tangent_view);
#endif
    var state = sample_surface(ground.indices.x, base_uv, ground.heights.x, dpdx(base_uv), dpdy(base_uv));
    state.colour *= ground.tint.rgb;
#ifdef VERTEX_TANGENTS
    state.normal = normalize(tbn * vec3<f32>(state.normal.xy * ground.parallax.z, state.normal.z));
#else
    state.normal = normalize(in.world_normal);
#endif
    // Design x/y = Bevy x/-z; PNG/glTF V is flipped relative to Blender V,
    // so repeating overlay UVs are (Bevy x,z) / repeat.
    let world_uv_metres = vec2<f32>(in.world_position.x, in.world_position.z);
    let world_dx = dpdx(world_uv_metres);
    let world_dy = dpdy(world_uv_metres);
    for (var channel = 0u; channel < 4u; channel += 1u) {
        let i = channel + 1u;
        let repeat = layer_repeat(i);
        var next = sample_surface(layer_index(i), world_uv_metres / repeat, layer_height(i), world_dx / repeat, world_dy / repeat);
        // Design normal (x,y,z) -> Bevy (x,z,-y), matching the Blender preview.
        next.normal = vec3<f32>(next.normal.x, next.normal.z, -next.normal.y);
        state = blend_surface(state, next, masks[channel]);
    }
    let macro_mask = height16(world_uv_metres / ground.extra.z, ground.extra_indices.y);
    state.colour *= 1.0 + ground.extra.w * (macro_mask - 0.5);
    pbr.material.base_color = vec4<f32>(state.colour, 1.0);
    pbr.material.flags &= ~pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_RESERVED_BITS;
    pbr.material.perceptual_roughness = state.orm.g;
    pbr.material.metallic = state.orm.b;
    pbr.diffuse_occlusion *= vec3<f32>(state.orm.r);
    pbr.specular_occlusion *= state.orm.r;
    pbr.N = state.normal;
#ifdef PREPASS_PIPELINE
    return deferred_output(in, pbr);
#else
    var out: FragmentOutput;
    out.color = apply_pbr_lighting(pbr);
    out.color = main_pass_post_lighting_processing(pbr, out.color);
    return out;
#endif
}
