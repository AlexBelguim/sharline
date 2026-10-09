// Smoke clouds and molotov fires (val_etf/src/render/throw_fx.rs): the hedges' card approach (foliage.wgsl) for
// volumes. One mesh per cloud or fire, a StandardMaterial extension whose own vertex and fragment stages replace
// the PBR ones (alpha blended smoke, additive fire; neither is in a prepass or casts a shadow).
//
// Smoke: soft painted puff cards facing the camera fill the cloud. The vertex stage grows the cloud, drifts and
// rolls the puffs and lights each corner (light wrap, light through the smoke toward the sun, the ambient, and a
// sun visibility per puff baked on the CPU against the level), so the fragment stage only samples the atlas, cuts
// the bullet tunnels and softens where a puff meets the level. Puffs right at the camera vanish (no card in the
// face; GPU work bounded).
//
// Fire: flame cards stand up from the burning ground and turn to the camera, flickering; small ember sparks rise
// and fade. Unlit and additive, like the streak aura's embers.
//
// Vertex data: POSITION the card's centre (mesh space, the full-size cloud or fire), NORMAL its outward normal,
// UV_0 the atlas, UV_1 the corner's offset from the centre in metres (flames: from the foot), COLOR r = sun
// visibility (smoke) or heat (fire), g = shade, b = 0 puff / flame, 1 ember, a = a random phase.

#import bevy_pbr::{
    mesh_functions,
    mesh_view_bindings::view,
    view_transformations::{position_world_to_clip, depth_ndc_to_view_z},
    forward_io::{Vertex, VertexOutput, FragmentOutput},
    pbr_types,
    pbr_functions::main_pass_post_lighting_processing,
}
#ifdef DEPTH_PREPASS
#ifndef MULTISAMPLED
#import bevy_pbr::prepass_utils::prepass_depth
#endif
#endif

const TAU: f32 = 6.283185307179586;
const TUNNELS: u32 = 8u;

struct ThrowFx {
    // x: kind (0 smoke, 1 fire), y: growth (smoke size / fire spread, 0..1), z: alpha (smoke density, the fire's
    // burn-out), w: the area's age (s)
    state: vec4<f32>,
    // smoke: x young puff scale, y drift (m), z swirl (rad/s), w puff roll (rad/s)
    // fire: x flicker (share of the height), y flicker rate low (Hz), z high (Hz), w ember size (m)
    motion: vec4<f32>,
    // smoke: x wrap, y translucency, z translucency power, w spread while thinning
    // fire: x ember rise (m), y ember rise time (s), z flame glow, w ember glow
    shape: vec4<f32>,
    // rgb: the puffs' albedo / the flames' tint; a: the puffs' opacity
    tint: vec4<f32>,
    // rgb: the embers' tint
    tint2: vec4<f32>,
    // xyz: toward the sun; w: 1 with a sun
    sun_dir: vec4<f32>,
    // rgb: the sun's diffuse light (exposed, over PI)
    sun: vec4<f32>,
    // rgb: the ambient light (exposed)
    ambient: vec4<f32>,
    // x, y: puffs fade out from y to x metres from the camera (and vanish closer); z: soft depth (m);
    // w: live bullet tunnels
    fade: vec4<f32>,
    // x: tunnel radius (m), y: its soft edge (m)
    tunnel: vec4<f32>,
    // a bullet line through the cloud: xyz its ends, w (of a) how open it is
    tunnel_a: array<vec4<f32>, 8>,
    tunnel_b: array<vec4<f32>, 8>,
}

@group(#{MATERIAL_BIND_GROUP}) @binding(100) var<uniform> fx: ThrowFx;
@group(#{MATERIAL_BIND_GROUP}) @binding(101) var atlas_texture: texture_2d<f32>;
@group(#{MATERIAL_BIND_GROUP}) @binding(102) var atlas_sampler: sampler;

fn rotate_y(p: vec3<f32>, a: f32) -> vec3<f32> {
    let s = sin(a);
    let c = cos(a);
    return vec3<f32>(p.x * c + p.z * s, p.y, -p.x * s + p.z * c);
}

@vertex
fn vertex(vertex: Vertex) -> VertexOutput {
    var out: VertexOutput;
    let world_from_local = mesh_functions::get_world_from_local(vertex.instance_index);
    let data = vertex.color;
    let phase = data.a;
    let corner = vertex.uv_b;
    let t = fx.state.w;
    let growth = fx.state.y;
    let alpha = fx.state.z;
    let cam = view.world_position.xyz;
    let cam_right = view.world_from_view[0].xyz;
    let cam_up = view.world_from_view[1].xyz;

    var world: vec3<f32>;
    var color: vec4<f32>;
    if fx.state.x < 0.5 {
        // ------------------------------------------------------------------ smoke
        // The cloud grows, turns slowly and spreads a little as it thins; each puff wanders around its place.
        let spread = 1.0 + fx.shape.w * (1.0 - alpha);
        var local = rotate_y(vertex.position * growth * spread, t * fx.motion.z * (0.6 + phase * 0.8));
        let wander = vec3<f32>(
            sin(t * 0.37 + phase * 6.1),
            sin(t * 0.23 + phase * 4.3) * 0.5,
            cos(t * 0.31 + phase * 5.2),
        );
        local += wander * fx.motion.y * growth;
        let centre = (world_from_local * vec4<f32>(local, 1.0)).xyz;
        let origin = (world_from_local * vec4<f32>(0.0, 0.0, 0.0, 1.0)).xyz;
        let dist = distance(cam, centre);
        // Close to the camera a puff fades out, then vanishes (a degenerate card draws nothing).
        let near = smoothstep(fx.fade.x, fx.fade.y, dist);
        let keep = select(0.0, 1.0, dist > fx.fade.x);
        let size = mix(fx.motion.x, 1.0, growth) * spread * keep;
        let roll = phase * TAU + t * fx.motion.w * (phase * 2.0 - 1.0);
        let s = sin(roll);
        let c = cos(roll);
        let o = vec2<f32>(corner.x * c - corner.y * s, corner.x * s + corner.y * c) * size;
        world = centre + cam_right * o.x + cam_up * o.y;

        // Lit per corner: the puff's outward normal, rounded toward its corner, with light wrap and light
        // through the smoke toward the sun; the puff's sun visibility and shade come from the CPU.
        let n_card = normalize((world_from_local * vec4<f32>(vertex.normal, 0.0)).xyz);
        let n = normalize(n_card + normalize(world - centre + (centre - origin) * 0.05) * 0.45);
        let wrap = fx.shape.x;
        let L = fx.sun_dir.xyz;
        let ndl = dot(n, L);
        let diffuse = max((ndl + wrap) / (1.0 + wrap), 0.0);
        let v = normalize(cam - world);
        let back = pow(saturate(dot(-v, L)), fx.shape.z) * fx.shape.y;
        let sun = fx.sun.rgb * (diffuse + back) * data.r * fx.sun_dir.w;
        let albedo = fx.tint.rgb * data.g;
        color = vec4<f32>(albedo * (fx.ambient.rgb + sun), fx.tint.a * alpha * near);
    } else {
        // ------------------------------------------------------------------ fire
        var local = vertex.position;
        local = vec3<f32>(local.x * growth, local.y, local.z * growth);
        if data.b < 0.5 {
            // A flame: stands up from the ground and turns to the camera about the vertical, flickering.
            let hz = mix(fx.motion.y, fx.motion.z, phase);
            let flicker = 1.0 + fx.motion.x * sin(t * hz * TAU + phase * 13.0);
            let height = alpha * flicker * mix(0.35, 1.0, growth);
            let foot = (world_from_local * vec4<f32>(local, 1.0)).xyz;
            let to_cam = cam - foot;
            let right = normalize(vec3<f32>(to_cam.z, 0.0, -to_cam.x) + vec3<f32>(1e-4, 0.0, 0.0));
            let rise = corner.y * height;
            let sway = sin(t * 2.3 + phase * 7.0) * 0.12 * rise;
            world = foot + right * (corner.x * mix(0.6, 1.0, alpha) + sway) + vec3<f32>(0.0, rise, 0.0);
            let heat = data.r;
            color = vec4<f32>(fx.tint.rgb * fx.shape.z * (0.65 + 0.35 * heat), alpha);
        } else {
            // An ember: rises from the flames and burns out.
            let up = fract(t / max(fx.shape.y, 0.05) + phase);
            local += vec3<f32>(sin(up * 5.0 + phase * 9.0) * 0.15, up * fx.shape.x, cos(up * 4.0 + phase * 7.0) * 0.15);
            let centre = (world_from_local * vec4<f32>(local, 1.0)).xyz;
            let size = fx.motion.w * (1.0 - up) * alpha;
            world = centre + (cam_right * corner.x + cam_up * corner.y) * size;
            color = vec4<f32>(fx.tint2.rgb * fx.shape.w, alpha * (1.0 - up));
        }
    }

    out.world_position = vec4<f32>(world, 1.0);
    out.position = position_world_to_clip(world);
    out.world_normal = normalize(cam - world);
#ifdef VERTEX_UVS_A
    out.uv = vertex.uv;
#endif
#ifdef VERTEX_UVS_B
    out.uv_b = vertex.uv_b;
#endif
#ifdef VERTEX_COLORS
    out.color = color;
#endif
#ifdef VERTEX_OUTPUT_INSTANCE_INDEX
    out.instance_index = vertex.instance_index;
#endif
    return out;
}

// Distance from `p` to the segment `a..b`.
fn segment_distance(p: vec3<f32>, a: vec3<f32>, b: vec3<f32>) -> f32 {
    let ab = b - a;
    let s = saturate(dot(p - a, ab) / max(dot(ab, ab), 1e-6));
    return distance(p, a + ab * s);
}

@fragment
fn fragment(in: VertexOutput) -> FragmentOutput {
    var out: FragmentOutput;
    let tex = textureSample(atlas_texture, atlas_sampler, in.uv);
    let smoke = fx.state.x < 0.5;
    var rgb: vec3<f32>;
    var a = tex.a * in.color.a;
    if smoke {
        rgb = in.color.rgb * tex.rgb;
        // Bullet tunnels: puffs near a recent bullet line fade away, a clear tube along it.
        let n = min(u32(fx.fade.w), TUNNELS);
        let p = in.world_position.xyz;
        for (var i = 0u; i < n; i = i + 1u) {
            let ta = fx.tunnel_a[i];
            let d = segment_distance(p, ta.xyz, fx.tunnel_b[i].xyz);
            let clear = 1.0 - smoothstep(fx.tunnel.x - fx.tunnel.y, fx.tunnel.x + fx.tunnel.y, d);
            a *= 1.0 - clear * ta.w;
        }
    } else {
        // Hot cores go yellow-white.
        let heat = tex.r;
        rgb = in.color.rgb * mix(vec3<f32>(1.0), vec3<f32>(1.6, 1.5, 1.2), heat * heat) * heat;
    }
#ifdef DEPTH_PREPASS
#ifndef MULTISAMPLED
    // Soft where a card meets the level.
    if fx.fade.z > 0.0 {
        let scene_z = depth_ndc_to_view_z(prepass_depth(in.position, 0u));
        let card_z = depth_ndc_to_view_z(in.position.z);
        a *= saturate((card_z - scene_z) / fx.fade.z);
    }
#endif
#endif
    if a < 0.003 {
        discard;
    }
    var pbr_input = pbr_types::pbr_input_new();
    pbr_input.world_position = in.world_position;
    pbr_input.frag_coord = in.position;
    if smoke {
        pbr_input.material.flags = pbr_types::STANDARD_MATERIAL_FLAGS_FOG_ENABLED_BIT;
    } else {
        pbr_input.material.flags = pbr_types::STANDARD_MATERIAL_FLAGS_ALPHA_MODE_ADD;
    }
    out.color = main_pass_post_lighting_processing(pbr_input, vec4<f32>(rgb, a));
    return out;
}
