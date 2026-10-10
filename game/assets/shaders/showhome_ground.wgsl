// Four exact material arrays; COLOR_0 is independent RGBA masks, never opacity.
//
// Cost (the ground fills most of the view): a layer is sampled only where it shows. A mask of 0 blends with
// weight 0, so that layer is skipped; a mask of 1 replaces everything under it, so the layers below the last
// full mask (the base and its relief included) are never sampled; the height maps only steer partial masks.
// The base layer's relief marches as many steps as its shift covers pixels on screen (at most the preset's
// count) and is off where the whole shift is under `relief.y` pixels (far away, or seen from above, it would
// move nothing). Every pixel gets the texels the full march would give it, to within a pixel of relief.
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
    // x: relief on (0 = off: LOW), y: most relief steps (the preset's), z: base normal repeat correction.
    parallax: vec4<f32>,
    // x: relief steps per pixel of the relief's whole shift on screen, y: no relief below this many pixels.
    relief: vec4<f32>,
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

// Colour, ORM and normal, and the height when a partial blend reads it (`with_height`).
fn sample_surface(
    layer: u32,
    uv: vec2<f32>,
    height_range: f32,
    dx: vec2<f32>,
    dy: vec2<f32>,
    with_height: bool,
) -> Surface {
    var s: Surface;
    s.colour = textureSampleGrad(ground_albedo, ground_sampler, uv, i32(layer), dx, dy).rgb;
    s.orm = textureSampleGrad(ground_orm, ground_sampler, uv, i32(layer), dx, dy).rgb;
    s.normal = normalize(textureSampleGrad(ground_normal, ground_sampler, uv, i32(layer), dx, dy).rgb * 2.0 - 1.0);
    s.height_m = 0.0;
    if with_height {
        s.height_m = height16(uv, layer) * height_range;
    }
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

// How many pixels a UV shift `d` spans on screen, through the UV's derivatives (`dx` per pixel across, `dy` per
// pixel down). A degenerate footprint counts as very long (the full march).
fn screen_pixels(d: vec2<f32>, dx: vec2<f32>, dy: vec2<f32>) -> f32 {
    let det = dx.x * dy.y - dx.y * dy.x;
    if abs(det) < 1e-24 { return 1e6; }
    return length(vec2<f32>(d.x * dy.y - d.y * dy.x, dx.x * d.y - dx.y * d.x) / det);
}

// Restrained base relief; depth is physical height / metre repeat. This keeps the
// existing kit UVs and does not replace the game's other depth/foliage materials.
fn base_relief(uv: vec2<f32>, tangent_view: vec3<f32>, dx: vec2<f32>, dy: vec2<f32>) -> vec2<f32> {
    if ground.parallax.x <= 0.0 { return uv; }
    // The whole shift (the relief at its deepest) for this view, in UV and in pixels. Into the surface is
    // -V; glTF's bitangent (cross(N, T) * w) points toward decreasing v, so V's B part moves v the other way
    // (as Bevy's own parallax does: Vt.xy * vec2(1, -1)). With -V.xy the relief went the wrong way along v
    // (map-kit review K5).
    let shift = vec2<f32>(-tangent_view.x, tangent_view.y) / max(abs(tangent_view.z), 0.15)
        * (ground.heights.x / ground.repeats.x);
    let pixels = screen_pixels(shift, dx, dy);
    if pixels < ground.relief.y { return uv; }
    let steps = clamp(ceil(pixels * ground.relief.x), 1.0, max(ground.parallax.y, 1.0));
    let delta = shift / steps;
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
    // Every derivative up front, in uniform control flow: the layers sample with explicit gradients.
    var base_uv = vec2<f32>(0.0);
#ifdef VERTEX_UVS_A
    base_uv = in.uv;
#endif
    let uv_dx = dpdx(base_uv);
    let uv_dy = dpdy(base_uv);
    // Design x/y = Bevy x/-z; PNG/glTF V is flipped relative to Blender V,
    // so repeating overlay UVs are (Bevy x,z) / repeat.
    let world_uv_metres = vec2<f32>(in.world_position.x, in.world_position.z) + vec2<f32>(ground.parallax.w, ground.relief.w);
    let world_dx = dpdx(world_uv_metres);
    let world_dy = dpdy(world_uv_metres);

    // The last full mask replaces every layer under it (-1: none, the base shows).
    var first = -1;
    for (var channel = 0; channel < 4; channel += 1) {
        if masks[channel] >= 1.0 { first = channel; }
    }
    // The heights only steer a partial mask above that.
    var partial = false;
    for (var channel = first + 1; channel < 4; channel += 1) {
        partial = partial || (masks[channel] > 0.0 && masks[channel] < 1.0);
    }

#ifdef VERTEX_TANGENTS
    let tbn = calculate_tbn_mikktspace(in.world_normal, in.world_tangent);
    if first < 0 {
        let tangent_view = vec3<f32>(dot(pbr.V, tbn[0]), dot(pbr.V, tbn[1]), dot(pbr.V, tbn[2]));
        base_uv = base_relief(base_uv, tangent_view, uv_dx, uv_dy);
    }
#endif
    // The base samples with the relief UV's own derivatives (as before the march was made adaptive): across a
    // joint they jump, which picks a softer mip there and gives the joints their weight. Uniform control flow.
    let relief_dx = dpdx(base_uv);
    let relief_dy = dpdy(base_uv);
    var state: Surface;
    if first < 0 {
        state = sample_surface(ground.indices.x, base_uv, ground.heights.x, relief_dx, relief_dy, partial);
        state.colour *= ground.tint.rgb;
#ifdef VERTEX_TANGENTS
        state.normal = normalize(tbn * vec3<f32>(state.normal.xy * ground.parallax.z, state.normal.z));
#else
        state.normal = normalize(in.world_normal);
#endif
    }
    for (var channel = max(first, 0); channel < 4; channel += 1) {
        let mask = masks[channel];
        if mask <= 0.0 { continue; }
        let i = u32(channel) + 1u;
        let repeat = layer_repeat(i);
        var next = sample_surface(
            layer_index(i),
            world_uv_metres / repeat,
            layer_height(i),
            world_dx / repeat,
            world_dy / repeat,
            partial,
        );
        // Design normal (x,y,z) -> Bevy (x,z,-y), matching the Blender preview.
        next.normal = vec3<f32>(next.normal.x, next.normal.z, -next.normal.y);
        if channel == first {
            state = next;
        } else {
            state = blend_surface(state, next, mask);
        }
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
