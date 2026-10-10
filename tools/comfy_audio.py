"""Generate game sound effects with the local MiniMax H3 audio-video model via ComfyUI.

H3 makes a video with a stereo soundtrack (32 kHz). We ask for a tiny throwaway video, keep only the audio,
then cut / clean / normalise it with numpy + scipy and write .ogg (Vorbis, 48 kHz).

Usage:
  python tools/comfy_audio.py list                                   # the preset sound list
  python tools/comfy_audio.py gen  --preset weapons/mako_shot --seeds 3 --root assets/audio/h3_test
  python tools/comfy_audio.py gen  --name misc/door --scene "..." --sound "..." --kind oneshot --seeds 2
  python tools/comfy_audio.py cut  --preset weapons/mako_shot --root assets/audio/h3_test   # re-cut, no GPU
  python tools/comfy_audio.py report --root assets/audio/h3_test     # metrics table (markdown)

Outputs under --root:
  <name>_<i>.ogg            the cut sounds (mono one-shots, stereo ambience), i = 1..variations
  _spec/<name>_<i>.png      waveform of the raw clip with the cut marked + spectrogram of the result
  _raw/<name>/*.flac        the untouched H3 audio (plus .json with prompt/settings/timing) for re-cuts
  _metrics/<name>.json      per-output measurements (onset, attack, floor, clipping, tonal/speech flags)

Requires ComfyUI at http://127.0.0.1:8188 (COMFY_URL overrides), ffmpeg on PATH, and numpy, scipy and
matplotlib (system Python or ComfyUI's venv both have them). Only the speed LoRAs below may be loaded.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")

UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"      # t2va / fl2va checkpoint
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
AUDIO_VAE = "minimax_h3_audio_vae_fp32.safetensors"
# The ONLY LoRAs this tool will ever load (speed / turbo distillations).
LORAS = {
    "turbo4": "minimax_h3_turbo_4step_pruned_comfyui.safetensors",
    "turbo8": "minimax_h3_fl2v_lightx2v_turbo_8step_v1.0_resized_avg_rank_24_bf16.safetensors",
    "none": None,
}
SR_MODEL = 32000
SR_OUT = 48000
FPS = 24

# Chosen by the tuning pass (assets/audio/h3_test/REPORT.md).
DEFAULTS = dict(w=128, h=128, steps=6, lora="turbo4", shift_video=12.0, shift_audio=3.0,
                sampler="res_multistep", scheduler="simple", style="structured")

NO_EXTRA = "Nothing else is heard: no music, no speech, no voices."

# Processing kinds. preroll/hold/max_len in seconds, tail_db = how far below the peak the tail may run.
KINDS = {
    "oneshot": dict(preroll=0.010, tail_db=50, hold=0.06, max_len=1.2, min_gap=0.30, per_clip=1,
                    stereo=False, attack_max=0.15),
    "multi": dict(preroll=0.010, tail_db=40, hold=0.04, max_len=0.45, min_gap=0.22, per_clip=6,
                  stereo=False, attack_max=0.08),
    "loop": dict(stereo=True, loop_len=24.0, xfade=2.0, join=2),
    "loop_mono": dict(stereo=False, loop_len=1.5, xfade=0.25, join=1),
}

# name -> scene (what is seen), sound (exactly what is heard), kind, seconds of generated clip, overrides.
PRESETS = {
    # ---- weapons
    "weapons/mako_shot": dict(
        kind="oneshot", seconds=3.0, max_len=0.9, tail_db=45,
        scene="A static close-up of a black assault rifle resting on a sandbag at an empty outdoor shooting "
              "range on a calm afternoon. The rifle fires exactly one round: one small muzzle flash, then it "
              "is still.",
        sound="Foley recording, close microphone: one single punchy assault rifle gunshot, a hard sharp crack "
              "with a tight low thump, followed by a short dry outdoor echo that dies away within half a "
              "second, then silence."),
    "weapons/warden_shot": dict(
        kind="oneshot", seconds=4.0, max_len=2.6, tail_db=50,
        scene="A static side view of a long heavy bolt-action sniper rifle on a bipod on a concrete firing "
              "line at an outdoor range, wide open fields behind it. It fires exactly one round: a big muzzle "
              "flash and recoil, then it is still.",
        sound="Foley recording, close microphone: one single huge sniper rifle gunshot, a deep heavy boom with "
              "a hard supersonic crack, followed by a long rolling echo across the open fields that fades out "
              "over two seconds, then silence."),
    "weapons/skink_shot": dict(
        kind="oneshot", seconds=3.0, max_len=0.45, tail_db=40,
        scene="A static close-up of a compact black submachine gun on a bench at an indoor shooting range. "
              "It fires exactly one round: one small muzzle flash, then it is still.",
        sound="Foley recording, close microphone: one single light snappy submachine gun shot, a fast bright "
              "pop with a very short tail, then silence."),
    "weapons/shot_distant": dict(
        kind="oneshot", seconds=4.0, max_len=2.0, tail_db=40,
        scene="A wide static shot of empty suburban rooftops on a quiet afternoon. Far away, out of sight, "
              "someone fires one rifle shot.",
        sound="One single gunshot heard from very far away: a muffled distant crack with no close detail, "
              "followed by a long echo bouncing off the houses, then quiet."),
    "weapons/dry_fire": dict(
        kind="oneshot", seconds=3.0, max_len=0.3, tail_db=40,
        scene="Extreme close-up of a finger squeezing the trigger of an empty black rifle on a workbench. "
              "Nothing fires.",
        sound="Foley recording, close microphone, isolated sound: one single small dry metallic trigger "
              "click, then silence."),
    "weapons/mag_out": dict(
        kind="oneshot", seconds=3.0, max_len=0.8, tail_db=40,
        scene="Close-up of hands on a black rifle on a workbench: the thumb presses the release and the "
              "magazine is pulled out of the rifle in one motion.",
        sound="Foley recording, close microphone, isolated sound: a metallic release click and the scrape of "
              "a magazine sliding out of the rifle, then silence."),
    "weapons/mag_in": dict(
        kind="oneshot", seconds=3.0, max_len=0.6, tail_db=40,
        scene="Close-up of hands on a black rifle on a workbench: a magazine is pushed up into the rifle and "
              "locks in place with one firm push.",
        sound="Foley recording, close microphone, isolated sound: one firm metallic click-clack as the "
              "magazine seats and locks, then silence."),
    "weapons/bolt_cycle": dict(
        kind="oneshot", seconds=3.0, max_len=1.0, tail_db=40,
        scene="Close-up of a hand working the bolt of a bolt-action sniper rifle on a bench: lift, pull "
              "back, push forward, lock down, once.",
        sound="Foley recording, close microphone, isolated sound: the heavy metallic clack-clack of a rifle "
              "bolt pulled back and slammed forward, then silence."),
    "weapons/fire_mode": dict(
        kind="oneshot", seconds=3.0, max_len=0.25, tail_db=40,
        scene="Extreme close-up of a thumb flicking the selector switch on the side of a black rifle, once.",
        sound="Foley recording, close microphone, isolated sound: one small crisp mechanical switch click, "
              "then silence."),
    "weapons/mag_check": dict(
        kind="oneshot", seconds=3.0, max_len=1.2, tail_db=40,
        scene="Close-up of hands on a black rifle: the magazine is tilted out a little, glanced at, and "
              "pushed back in.",
        sound="Foley recording, close microphone, isolated sound: a soft metallic click, a short rattle of "
              "the magazine, and a firm click as it is pushed back in, then silence."),
    "weapons/equip": dict(
        kind="oneshot", seconds=3.0, max_len=0.9, tail_db=40,
        scene="A soldier in a quiet room quickly lifts a rifle from his side up to his shoulder.",
        sound="Foley recording, close microphone, isolated sound: a quick rustle of tactical clothing and a "
              "light rattle of the rifle's metal parts and sling, then silence."),
    # ---- movement
    "movement/step_concrete": dict(
        kind="multi", seconds=5.0,
        scene="Low static close-up of combat boots walking slowly across a concrete pavement on a quiet day.",
        sound="Foley recording, close microphone: slow separate footsteps of hard boots on concrete, each "
              "step a short gritty scuff and thud with a short gap of silence between steps."),
    "movement/step_grass": dict(
        kind="multi", seconds=5.0,
        scene="Low static close-up of combat boots walking slowly across a short-cut lawn on a quiet day.",
        sound="Foley recording, close microphone: slow separate footsteps on grass, each step a soft swishy "
              "crunch with a short gap of silence between steps."),
    "movement/step_gravel": dict(
        kind="multi", seconds=5.0,
        scene="Low static close-up of combat boots walking slowly along a gravel path on a quiet day.",
        sound="Foley recording, close microphone: slow separate footsteps on loose gravel, each step a "
              "crunchy grind of stones with a short gap of silence between steps."),
    "movement/step_wood": dict(
        kind="multi", seconds=5.0,
        scene="Low static close-up of combat boots walking slowly across a wooden floor in an empty house.",
        sound="Foley recording, close microphone: slow separate footsteps on hollow wooden floorboards, each "
              "step a knock with a faint creak, with a short gap of silence between steps."),
    "movement/jump": dict(
        kind="oneshot", seconds=3.0, max_len=0.6, tail_db=40,
        scene="A soldier in full gear jumps up from a concrete floor, once.",
        sound="Foley recording, close microphone, isolated sound: a boot push-off scuff and a short rattle of "
              "gear and buckles, then silence. No grunt."),
    "movement/land": dict(
        kind="oneshot", seconds=3.0, max_len=0.7, tail_db=40,
        scene="A soldier in full gear drops down and lands hard on a concrete floor, once.",
        sound="Foley recording, close microphone, isolated sound: a heavy boot landing thud with a short "
              "rattle of gear and buckles, then silence. No grunt."),
    "movement/slide": dict(
        kind="oneshot", seconds=3.0, max_len=1.1, tail_db=35, attack_max=0.25,
        scene="A soldier sprints and drops into a fast slide along a concrete floor, then stops.",
        sound="Foley recording, close microphone, isolated sound: a one-second rough scraping slide of "
              "fabric and boots over concrete that slows down and stops, then silence."),
    "movement/jetpack": dict(
        kind="loop_mono", seconds=4.0, loop_len=1.5,
        scene="Close-up of a small backpack thruster firing a steady blue flame jet, held in place on a "
              "test stand.",
        sound="A steady roaring rocket thruster hiss with a rumbling low end, constant and unchanging."),
    "movement/zipline": dict(
        kind="loop_mono", seconds=4.0, loop_len=2.0,
        scene="Close-up of a metal pulley trolley rolling fast along a steel zipline cable.",
        sound="A steady fast metallic whirr of a pulley running along a steel cable, with a constant "
              "buzzing hum of the wire."),
    # ---- combat
    "combat/hit_flesh": dict(
        kind="oneshot", seconds=3.0, max_len=0.4, tail_db=40,
        scene="Close-up of a bullet hitting a hanging leather punching bag filled with sand, once.",
        sound="Foley recording, close microphone, isolated sound: one single dull heavy thwack of a bullet "
              "hitting a dense body, then silence."),
    "combat/hit_head": dict(
        kind="oneshot", seconds=3.0, max_len=0.5, tail_db=40,
        scene="Close-up of a bullet striking a steel helmet on a stand, once.",
        sound="Foley recording, close microphone, isolated sound: one sharp hard metallic ping with a short "
              "bright ring, then silence."),
    "combat/shield_hit": dict(
        kind="oneshot", seconds=3.0, max_len=0.6, tail_db=45,
        scene="A glowing transparent blue energy shield hovers in a dark room. A bullet strikes it once and "
              "a ripple of light spreads across it.",
        sound="Foley recording, close microphone, isolated sound: one single glassy crystal tink with a "
              "short shimmering electric ring, then silence."),
    "combat/shield_break": dict(
        kind="oneshot", seconds=3.0, max_len=1.5, tail_db=45,
        scene="A glowing transparent blue energy shield hovers in a dark room. It cracks and shatters into "
              "falling sparks, once.",
        sound="Foley recording, close microphone, isolated sound: a bright glassy shattering crash with an "
              "electric crackle, the fragments tinkling away, then silence."),
    "combat/kill": dict(
        kind="oneshot", seconds=3.0, max_len=0.6, tail_db=40,
        scene="A futuristic heads-up display flashes a small red skull icon once on a dark screen.",
        sound="A single short clean electronic confirmation tone, a crisp two-note digital blip, then "
              "silence."),
    "combat/damage_taken": dict(
        kind="oneshot", seconds=3.0, max_len=0.5, tail_db=40,
        scene="Close-up of a heavy fist punching a padded tactical vest on a mannequin, once.",
        sound="Foley recording, close microphone, isolated sound: one heavy dull body-impact thump with a "
              "little fabric snap, then silence."),
    # ---- items / ui
    "items/heal": dict(
        kind="oneshot", seconds=4.0, max_len=2.0, tail_db=40, attack_max=0.3,
        scene="Close-up of hands opening a small medical pouch, pressing an auto-injector stim against an "
              "arm. It clicks and injects.",
        sound="Foley recording, close microphone, isolated sound: a quick rustle of fabric, a plastic click "
              "and a short pressurised hiss, then silence."),
    "ui/click": dict(
        kind="oneshot", seconds=3.0, max_len=0.15, tail_db=40,
        scene="A finger taps a button on a sleek futuristic touch screen, once.",
        sound="A single short crisp digital interface click, then silence."),
    "ui/hover": dict(
        kind="oneshot", seconds=3.0, max_len=0.1, tail_db=35,
        scene="A cursor glides over a button on a sleek futuristic menu screen, once.",
        sound="A single very short soft digital tick, then silence."),
    "ui/confirm": dict(
        kind="oneshot", seconds=3.0, max_len=0.5, tail_db=40,
        scene="A futuristic game menu shows a large READY button that lights up green, once.",
        sound="A single bright positive rising two-note electronic chime, then silence."),
    "ui/back": dict(
        kind="oneshot", seconds=3.0, max_len=0.4, tail_db=40,
        scene="A futuristic game menu panel slides closed, once.",
        sound="A single soft low falling electronic blip, then silence."),
    # ---- ambience
    "ambient/showhome_loop": dict(
        kind="loop", seconds=15.0, loop_len=24.0,
        scene="A wide static shot of an empty sunny suburban street with neat new show homes and trimmed "
              "lawns. Nobody is around; trees sway a little.",
        sound="A calm daytime outdoor ambience: distant birds chirping now and then, a light breeze in the "
              "trees, and far-off traffic hum, steady and even."),
    "ambient/range_loop": dict(
        kind="loop", seconds=15.0, loop_len=24.0,
        scene="A wide static shot of an empty indoor shooting range with concrete walls and fluorescent "
              "lights. Nobody is there.",
        sound="Steady indoor room tone: the constant low hum of ventilation fans and a faint air hiss, even "
              "and unchanging."),
}


# --------------------------------------------------------------------------------------------- ComfyUI
def align_frames(n):
    n = max(5, int(n))
    while n % 17 != 5:
        n += 1
    return n


def make_prompt(scene, sound, style="structured", no_extra=True):
    tail = (" " + NO_EXTRA) if no_extra else ""
    if style == "plain":
        return f"{scene}\n\nAudio: {sound}{tail}"
    summary = scene.split(". ")[0].rstrip(".") + "."
    return (f"summary: {summary}\n\n"
            f"detailed_description:\n[Shot 1] {scene} The camera is static and locked-off.\n\n"
            f"overall_soundscape: {sound}{tail}\n\n"
            f"non_diegetic_music: N/A")


def build_graph(prompt, seed, w, h, frames, steps, lora, shift_video, shift_audio, sampler, scheduler):
    if lora not in LORAS:
        raise ValueError(f"lora must be one of {list(LORAS)} (only the speed LoRAs are allowed)")
    g = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "4": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP, "type": "minimax", "device": "default"}},
        "6": {"class_type": "VAELoader", "inputs": {"vae_name": AUDIO_VAE}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["4", 0]}},
        "8": {"class_type": "EmptyMiniMaxH3LatentAV", "inputs": {"width": w, "height": h, "length": frames}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": sampler}},
        "13": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["12", 0], "vae": ["6", 0]}},
        "14": {"class_type": "PreviewAudio", "inputs": {"audio": ["13", 0]}},
    }
    model = ["1", 0]
    if LORAS[lora]:
        g["2"] = {"class_type": "LoraLoaderModelOnly",
                  "inputs": {"model": model, "lora_name": LORAS[lora], "strength_model": 1.0}}
        model = ["2", 0]
    g["3"] = {"class_type": "MiniMaxH3SigmaShift",
              "inputs": {"model": model, "shift_video": shift_video, "shift_audio": shift_audio}}
    g["5"] = {"class_type": "BasicGuider", "inputs": {"model": ["3", 0], "conditioning": ["7", 0]}}
    g["11"] = {"class_type": "BasicScheduler",
               "inputs": {"model": ["3", 0], "scheduler": scheduler, "steps": steps, "denoise": 1.0}}
    g["12"] = {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["9", 0], "guider": ["5", 0], "sampler": ["10", 0], "sigmas": ["11", 0],
                          "latent_image": ["8", 0]}}
    return g


def _post(path, payload):
    req = urllib.request.Request(COMFY + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _get(path):
    with urllib.request.urlopen(COMFY + path, timeout=120) as r:
        return r.read()


def _vram_used():
    try:
        d = json.loads(_get("/system_stats"))["devices"][0]
        return (d["vram_total"] - d["vram_free"]) / 2**30
    except Exception:
        return None


def run_graph(graph, timeout=1800):
    """Queue one graph, wait for it; returns (audio bytes, exec seconds, wall seconds, peak VRAM GiB)."""
    t0 = time.time()
    pid = _post("/prompt", {"prompt": graph, "client_id": str(uuid.uuid4())})["prompt_id"]
    peak = 0.0
    while True:
        v = _vram_used()
        if v is not None:
            peak = max(peak, v)
        hist = json.loads(_get(f"/history/{pid}"))
        if pid in hist:
            entry = hist[pid]
            status = entry.get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(json.dumps(status)[:3000])
            files = [a for node in entry.get("outputs", {}).values() for a in node.get("audio", [])]
            if files:
                ts = {m[0]: m[1].get("timestamp") for m in status.get("messages", []) if isinstance(m, list)}
                ex = None
                if ts.get("execution_start") and ts.get("execution_success"):
                    ex = (ts["execution_success"] - ts["execution_start"]) / 1000.0
                a = files[0]
                q = urllib.parse.urlencode({"filename": a["filename"], "subfolder": a.get("subfolder", ""),
                                            "type": a.get("type", "temp")})
                return _get("/view?" + q), ex, time.time() - t0, peak
        if time.time() - t0 > timeout:
            raise TimeoutError("ComfyUI generation timed out")
        time.sleep(0.5)


def free_comfy():
    try:
        _post("/free", {"unload_models": True, "free_memory": True})
    except Exception as e:
        print("free failed:", e, file=sys.stderr)


# --------------------------------------------------------------------------------------------- audio io
def load_audio(path, sr=SR_MODEL):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-acodec", "pcm_f32le",
                          "-ac", "2", "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()   # [2, n]


def write_ogg(path, x, sr=SR_OUT, quality=6):
    import numpy as np
    x = np.atleast_2d(x).astype(np.float32)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", str(x.shape[0]),
                    "-i", "-", "-c:a", "libvorbis", "-q:a", str(quality), path],
                   input=x.T.tobytes(), check=True)


# --------------------------------------------------------------------------------------------- analysis
def db(v):
    import numpy as np
    return 20.0 * np.log10(np.maximum(np.abs(v), 1e-9))


def envelope_db(x, sr, win=0.005, hop=0.001):
    """Sliding RMS (dBFS) of mono x; one value per hop."""
    import numpy as np
    n, h = max(1, int(win * sr)), max(1, int(hop * sr))
    c = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    starts = np.arange(0, max(1, len(x) - n + 1), h)
    rms = np.sqrt((c[starts + n] - c[starts]) / n)
    return 10.0 * np.log10(np.maximum(rms ** 2, 1e-18)), h


def highpass(x, sr, fc=25.0):
    from scipy.signal import butter, sosfiltfilt
    sos = butter(2, fc, btype="highpass", fs=sr, output="sos")
    return sosfiltfilt(sos, x, axis=-1)


def to_mono(x):
    import numpy as np
    l, r = x[0], x[1]
    corr = float(np.dot(l, r) / (np.linalg.norm(l) * np.linalg.norm(r) + 1e-12))
    if corr < 0.0:                                   # out of phase: take the louder side, do not cancel
        return (l if np.sum(l * l) >= np.sum(r * r) else r), corr
    return 0.5 * (l + r), corr


def clip_runs(x, run=3):
    """Samples sitting on a flat top (|x| at the clip's max for >= run samples): a clipping sign."""
    import numpy as np
    a = np.abs(x)
    m = a.max()
    if m <= 0:
        return 0
    hot = a >= m * 0.9995
    count, cur = 0, 0
    for v in hot:
        cur = cur + 1 if v else 0
        if cur == run:
            count += run
        elif cur > run:
            count += 1
    return int(count)


def tonal_metrics(x, sr, floor_db):
    """Heuristics for music / speech / hum contamination.
    tonal_run_s: longest time any narrow spectral line (100 Hz-5 kHz) persists (music notes, hum, voice).
    voiced: share of active 40 ms frames with strong pitch periodicity at 100-400 Hz (speech / sung notes).
    flatness: mean spectral flatness of active frames (1 = noise-like, 0 = pure tone)."""
    import numpy as np
    from scipy.ndimage import median_filter
    from scipy.signal import stft, butter, sosfiltfilt
    out = {}
    f, t, Z = stft(x, sr, nperseg=1024, noverlap=768)
    P = db(Z)
    act = P.max(axis=0) > floor_db + 25
    base = median_filter(P, size=(31, 1))
    peak = (P - base > 15) & (P >= np.roll(P, 1, 0)) & (P >= np.roll(P, -1, 0))
    band = (f >= 100) & (f <= 5000)
    peak &= band[:, None] & act[None, :]
    peak = peak | np.roll(peak, 1, 0) | np.roll(peak, -1, 0)    # tolerate +-1 bin drift
    best, best_f = 0, 0.0
    for i in np.nonzero(band)[0]:
        row, cur = peak[i], 0
        for v in row:
            cur = cur + 1 if v else 0
            if cur > best:
                best, best_f = cur, f[i]
    hop_s = (1024 - 768) / sr
    out["tonal_run_s"] = round(best * hop_s, 3)
    out["tonal_run_hz"] = round(float(best_f))
    S = np.abs(Z[:, act]) ** 2 + 1e-12
    out["flatness"] = round(float(np.mean(np.exp(np.mean(np.log(S), 0)) / np.mean(S, 0)))
                            if S.shape[1] else 1.0, 3)
    sos = butter(4, [80, 1000], btype="bandpass", fs=sr, output="sos")
    y = sosfiltfilt(sos, x)
    n, hop = int(0.04 * sr), int(0.02 * sr)
    lo, hi = sr // 400, sr // 100
    voiced = total = 0
    for s in range(0, len(y) - n, hop):
        fr = y[s:s + n]
        if 10 * np.log10(np.mean(fr * fr) + 1e-18) < floor_db + 20:
            continue
        total += 1
        fr = fr - fr.mean()
        ac = np.correlate(fr, fr, "full")[n - 1:]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        if ac[lo:hi].max() > 0.6:
            voiced += 1
    out["voiced"] = round(voiced / total, 3) if total else 0.0
    out["voiced_frames"] = total
    return out


def find_events(x, sr, p):
    """Detect sound events in mono x. Returns (events, env_db, hop, floor_db)."""
    import numpy as np
    from scipy.signal import find_peaks
    env, hop = envelope_db(x, sr, 0.005, 0.001)
    smooth, _ = envelope_db(x, sr, 0.03, 0.001)
    edge = int(0.05 / 0.001)
    core = env[edge:-edge] if len(env) > 3 * edge else env
    floor = float(np.percentile(core, 10))
    peaks, props = find_peaks(env, height=floor + 15, prominence=10, distance=int(p["min_gap"] / 0.001))
    events = []
    for k in peaks:
        pk = float(env[k])
        thr_on = max(floor + 0.3 * (pk - floor), pk - 25)
        lim = max(0, k - int(p["attack_max"] / 0.001))
        on = k
        while on > lim and env[on] > thr_on:
            on -= 1
        a10 = k                                       # attack time: -20 dB point to the peak
        while a10 > lim and env[a10] > pk - 20:
            a10 -= 1
        events.append(dict(peak_i=int(k), onset_i=int(on), peak_db=pk, attack_ms=float(k - a10)))
    return events, env, smooth, hop, floor


def cut_events(x, sr, p, src):
    """Cut every usable event of a raw clip; each gets an end, metrics and a score."""
    import numpy as np
    events, env, smooth, hop, floor = find_events(x, sr, p)
    tone = tonal_metrics(x, sr, floor)
    cands = []
    for j, e in enumerate(events):
        k, on, pk = e["peak_i"], e["onset_i"], e["peak_db"]
        thr_off = max(floor + 4, pk - p["tail_db"])
        hold = int(p["hold"] / 0.001)
        end_lim = min(len(smooth) - 1, on + int(p["max_len"] / 0.001))
        for n in events[j + 1:]:                      # stop before the next loud, separate event
            if n["peak_db"] > pk - 12:
                end_lim = min(end_lim, n["onset_i"] - 5)
                break
        end = k
        while end < end_lim:
            if smooth[end] < thr_off and np.all(smooth[end:end + hold] < thr_off):
                break
            end += 1
        start_s = max(0, (on * hop) - int(p["preroll"] * sr))
        end_s = min(len(x), end * hop + int(0.03 * sr))
        pre = env[max(0, on - 100):max(1, on - 10)]
        pre_db = float(np.mean(pre)) if len(pre) else floor
        seg = x[start_s:end_s]
        c = dict(src=src, start_s=start_s, end_s=end_s, onset_s=round(on * hop / sr, 4),
                 peak_db=round(pk, 1), floor_db=round(floor, 1), snr_db=round(pk - floor, 1),
                 pre_quiet_db=round(pk - pre_db, 1), attack_ms=e["attack_ms"],
                 dur_s=round((end_s - start_s) / sr, 3), hit_max_len=bool(end >= end_lim),
                 clip_samples=clip_runs(seg), n_events_in_clip=len(events), **tone)
        c["score"] = round(min(c["snr_db"], 60) + 0.5 * min(c["pre_quiet_db"], 30)
                           - (10 if c["clip_samples"] > 0 else 0)
                           - max(0.0, c["attack_ms"] - 15) * 0.3
                           - (8 if c["voiced"] > 0.4 else 0) - (8 if c["tonal_run_s"] > 0.8 else 0), 1)
        cands.append(c)
    return cands, floor


def shape_oneshot(x, sr, c, p):
    """Fade-in over the pre-roll, cosine fade-out over the last part of the tail."""
    import numpy as np
    y = x[..., c["start_s"]:c["end_s"]].astype(np.float64).copy()
    n = y.shape[-1]
    fi = max(16, min(int(p["preroll"] * sr), n // 4))
    fo = int(min(max(0.02 * sr, 0.35 * n), 0.25 * sr))
    y[..., :fi] *= 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fi))
    y[..., n - fo:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo))
    return y


def make_loop(x, sr, loop_len, xfade):
    """x: [ch, n] already trimmed. Returns [ch, L] whose end flows into its start (equal-power xfade)."""
    import numpy as np
    X = int(xfade * sr)
    L = min(int(loop_len * sr), x.shape[-1] - X)
    head, over = x[..., :L].copy(), x[..., L:L + X]
    t = np.linspace(0, np.pi / 2, X)
    head[..., :X] = head[..., :X] * np.sin(t) + over * np.cos(t)
    return head


def join_clips(clips, sr, xfade):
    import numpy as np
    out = clips[0]
    X = int(xfade * sr)
    t = np.linspace(0, np.pi / 2, X)
    for c in clips[1:]:
        mid = out[..., -X:] * np.cos(t) + c[..., :X] * np.sin(t)
        out = np.concatenate([out[..., :-X], mid, c[..., X:]], axis=-1)
    return out


def active_rms_db(y):
    import numpy as np
    m = y if y.ndim == 1 else y.mean(0)
    env, _ = envelope_db(m, SR_OUT, 0.05, 0.01)
    act = env[env > env.max() - 30]
    return float(10 * np.log10(np.mean(10 ** (act / 10)))) if len(act) else -120.0


def normalise_set(ys, peak_db=-1.0, spread_db=2.0):
    """Peak-normalise each to peak_db, then pull loud outliers down so active loudness is within spread_db."""
    import numpy as np
    out = []
    for y in ys:
        out.append(y * (10 ** (peak_db / 20) / (np.abs(y).max() + 1e-12)))
    louds = [active_rms_db(y) for y in out]
    ref = min(louds) + spread_db
    out = [y * 10 ** (min(0.0, ref - l) / 20) for y, l in zip(out, louds)]
    return out


def resample_out(y):
    from scipy.signal import resample_poly
    return resample_poly(y, SR_OUT // 8000, SR_MODEL // 8000, axis=-1)


def plot(png, raw_mono, sr_raw, spans, y, sr, title, info):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import spectrogram
    os.makedirs(os.path.dirname(os.path.abspath(png)), exist_ok=True)
    fig, ax = plt.subplots(3, 1, figsize=(9, 7.5), gridspec_kw=dict(height_ratios=[1, 1, 2]))
    t = np.arange(len(raw_mono)) / sr_raw
    ax[0].plot(t, raw_mono, lw=0.4, color="#456")
    for a, b, col in spans:
        ax[0].axvspan(a / sr_raw, b / sr_raw, color=col, alpha=0.3)
    ax[0].set_xlim(0, t[-1] if len(t) else 1)
    ax[0].set_title("raw H3 audio (shaded = cut)", fontsize=8)
    m = y if y.ndim == 1 else y.mean(0)
    ax[1].plot(np.arange(len(m)) / sr, m, lw=0.5, color="#a33")
    ax[1].set_xlim(0, len(m) / sr)
    ax[1].set_ylim(-1, 1)
    ax[1].set_title("output waveform", fontsize=8)
    nper = 512 if len(m) / sr < 2 else 1024
    f, tt, S = spectrogram(m, sr, nperseg=nper, noverlap=nper * 3 // 4)
    ax[2].pcolormesh(tt, f / 1000, 10 * np.log10(S + 1e-14), shading="auto", cmap="magma",
                     vmin=-130, vmax=-20)
    ax[2].set_ylabel("kHz")
    ax[2].set_xlabel("s")
    ax[2].set_title("output spectrogram", fontsize=8)
    fig.suptitle(title + "\n" + info, fontsize=8)
    for a in ax:
        a.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(png, dpi=90)
    plt.close(fig)


# --------------------------------------------------------------------------------------------- commands
def preset_params(name, args):
    pr = dict(PRESETS.get(name, {}))
    kind = args.kind or pr.get("kind", "oneshot")
    p = dict(KINDS[kind])
    for k in ("max_len", "tail_db", "preroll", "min_gap", "per_clip", "loop_len", "xfade", "join", "attack_max"):
        if k in pr:
            p[k] = pr[k]
        if getattr(args, k, None) is not None:
            p[k] = getattr(args, k)
    p["kind"] = kind
    return pr, p


def generate(args):
    name = args.preset or args.name
    pr, p = preset_params(name, args)
    scene = args.scene or pr.get("scene")
    sound = args.sound or pr.get("sound")
    if args.sound_prefix:
        sound = args.sound_prefix.strip() + " " + sound
    if not scene or not sound:
        raise SystemExit("need --preset, or --name with --scene and --sound")
    prompt = args.prompt or make_prompt(scene, sound, args.style, not args.no_extra)
    seconds = args.seconds or pr.get("seconds", 3.0)
    frames = align_frames(round(seconds * FPS)) if args.frames is None else align_frames(args.frames)
    settings = dict(w=args.w, h=args.h, frames=frames, steps=args.steps, lora=args.lora,
                    shift_video=args.shift_video, shift_audio=args.shift_audio, sampler=args.sampler,
                    scheduler=args.scheduler, style=args.style)
    tag = hashlib.sha1(json.dumps([prompt, settings], sort_keys=True).encode()).hexdigest()[:8]
    raw_dir = os.path.join(args.root, "_raw", name)
    os.makedirs(raw_dir, exist_ok=True)
    seeds = list(range(args.seed, args.seed + args.seeds))
    files = []
    for s in seeds:
        flac = os.path.join(raw_dir, f"{tag}_s{s}.flac")
        if os.path.exists(flac) and not args.force:
            print(f"cached {flac}")
            files.append(os.path.basename(flac))
            continue
        graph = build_graph(prompt, s, frames=frames, **{k: settings[k] for k in
                            ("w", "h", "steps", "lora", "shift_video", "shift_audio", "sampler", "scheduler")})
        data, ex, wall, vram = run_graph(graph)
        with open(flac, "wb") as f:
            f.write(data)
        meta = dict(name=name, seed=s, prompt=prompt, settings=settings, exec_s=ex, wall_s=round(wall, 1),
                    peak_vram_gib=round(vram, 2), audio_s=round(frames / FPS, 2))
        with open(flac[:-5] + ".json", "w") as f:
            json.dump(meta, f, indent=1)
        files.append(os.path.basename(flac))
        print(f"{name} seed {s}: exec {ex if ex is None else round(ex, 1)}s wall {wall:.1f}s "
              f"vram {vram:.1f} GiB -> {flac}")
    with open(os.path.join(raw_dir, "manifest.json"), "w") as f:
        json.dump(dict(files=files, tag=tag, prompt=prompt, settings=settings, params=p), f, indent=1)
    if not args.no_cut:
        cut(args, name)


def cut(args, name=None):
    import numpy as np
    name = name or args.preset or args.name
    raw_dir = os.path.join(args.root, "_raw", name)
    man = json.load(open(os.path.join(raw_dir, "manifest.json")))
    _, p = preset_params(name, args)
    if name not in PRESETS and args.kind is None and "params" in man:      # custom sound: keep gen-time params
        p = {**man["params"], **{k: v for k, v in p.items() if getattr(args, k, None) is not None}}
    raws = {f: highpass(load_audio(os.path.join(raw_dir, f)), SR_MODEL) for f in man["files"]}
    V = args.variations
    results, pngs = [], []
    if p["kind"] in ("oneshot", "multi"):
        cands = []
        for f, x in raws.items():
            mono, corr = to_mono(x)
            cs, _ = cut_events(mono, SR_MODEL, p, f)
            for c in cs:
                c["stereo_corr"] = round(corr, 3)
            cs.sort(key=lambda c: -c["score"])
            cands += cs[:p["per_clip"]]
        cands.sort(key=lambda c: -c["score"])
        if p["kind"] == "oneshot":                     # spread over seeds first: one per raw clip
            seen, first, rest = set(), [], []
            for c in cands:
                (first if c["src"] not in seen else rest).append(c)
                seen.add(c["src"])
            cands = first + rest
        picked = cands[:V]
        ys = []
        for c in picked:
            mono, _ = to_mono(raws[c["src"]])
            ys.append(resample_out(shape_oneshot(mono, SR_MODEL, c, p)))
    else:
        clips = []
        for f, x in raws.items():
            sk = int(0.3 * SR_MODEL)
            y = x[:, sk:-sk] if p["stereo"] else to_mono(x)[0][sk:-sk]
            clips.append((f, y))
        picked, ys = [], []
        J = p.get("join", 1)
        for i in range(V):
            group = clips[i * J:(i + 1) * J]
            if not group:
                break
            parts = [g[1] for g in group]
            rms = [np.sqrt(np.mean(q ** 2)) for q in parts]
            parts = [q * (np.mean(rms) / (r + 1e-12)) for q, r in zip(parts, rms)]
            body = join_clips(parts, SR_MODEL, p["xfade"]) if len(parts) > 1 else parts[0]
            y = make_loop(body, SR_MODEL, p["loop_len"], p["xfade"])
            mono = y if y.ndim == 1 else y.mean(0)
            env, _ = envelope_db(mono, SR_MODEL)
            floor = float(np.percentile(env, 10))
            c = dict(src=",".join(g[0] for g in group), dur_s=round(y.shape[-1] / SR_MODEL, 2),
                     floor_db=round(floor, 1), peak_db=round(float(env.max()), 1),
                     level_p90_p10_db=round(float(np.percentile(env, 90) - floor), 1),
                     clip_samples=clip_runs(mono), **tonal_metrics(mono, SR_MODEL, floor))
            seam = np.abs(np.diff(np.concatenate([y[..., -64:], y[..., :64]], -1), axis=-1)).max()
            c["seam_jump"] = round(float(seam), 4)
            picked.append(c)
            ys.append(resample_out(y))
    ys = normalise_set(ys, args.peak_db)
    for i, (c, y) in enumerate(zip(picked, ys), 1):
        out = os.path.join(args.root, f"{name}_{i}.ogg")
        write_ogg(out, y.astype(np.float32))
        c["out"] = os.path.relpath(out, args.root).replace("\\", "/")
        c["out_peak_dbfs"] = round(float(db(np.abs(y).max())), 2)
        c["out_loudness_db"] = round(active_rms_db(y), 1)
        c["out_dur_s"] = round(y.shape[-1] / SR_OUT, 3)
        raw_x = raws[c["src"].split(",")[0]]
        rm = to_mono(raw_x)[0]
        spans = [(c["start_s"], c["end_s"], "#e33")] if "start_s" in c else [(int(0.3 * SR_MODEL),
                                                                                 len(rm), "#3a3")]
        info = " ".join(f"{k}={c[k]}" for k in ("out_dur_s", "snr_db", "attack_ms", "floor_db", "pre_quiet_db",
                                                 "tonal_run_s", "voiced", "clip_samples", "score")
                        if k in c)
        png = os.path.join(args.root, "_spec", f"{name}_{i}.png")
        plot(png, rm, SR_MODEL, spans, y, SR_OUT, f"{name}_{i}  <- {c['src']}", info)
        results.append(c)
        print(f"wrote {out}  ({c['out_dur_s']}s, peak {c['out_peak_dbfs']} dBFS)")
    mdir = os.path.join(args.root, "_metrics")
    os.makedirs(os.path.dirname(os.path.join(mdir, name + ".json")), exist_ok=True)
    gen = []
    for f in man["files"]:
        j = os.path.join(raw_dir, f[:-5] + ".json")
        if os.path.exists(j):
            gen.append(json.load(open(j)))
    with open(os.path.join(mdir, name + ".json"), "w") as f:
        json.dump(dict(name=name, params=p, prompt=man["prompt"], settings=man["settings"],
                       gen=[{k: g.get(k) for k in ("seed", "exec_s", "wall_s", "peak_vram_gib")} for g in gen],
                       outputs=results), f, indent=1)


def report(args):
    rows = []
    mdir = os.path.join(args.root, "_metrics")
    for dp, _, fs in os.walk(mdir):
        for f in sorted(fs):
            if f.endswith(".json"):
                m = json.load(open(os.path.join(dp, f)))
                for o in m["outputs"]:
                    rows.append(o)
    keys = ["out", "out_dur_s", "snr_db", "attack_ms", "pre_quiet_db", "floor_db", "tonal_run_s", "voiced",
            "flatness", "clip_samples", "n_events_in_clip", "out_loudness_db", "score"]
    print("| " + " | ".join(keys) + " |")
    print("|" + "---|" * len(keys))
    for r in rows:
        print("| " + " | ".join(str(r.get(k, "")) for k in keys) + " |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for c in ("gen", "cut"):
        s = sub.add_parser(c)
        s.add_argument("--preset", help="name from the preset list (e.g. weapons/mako_shot)")
        s.add_argument("--name", help="output name for a custom sound (with --scene/--sound)")
        s.add_argument("--root", default="assets/audio/h3_test")
        s.add_argument("--kind", choices=list(KINDS), default=None)
        s.add_argument("--variations", type=int, default=3)
        s.add_argument("--peak-db", type=float, default=-1.0)
        for k in ("max_len", "tail_db", "preroll", "min_gap", "loop_len", "xfade", "attack_max"):
            s.add_argument("--" + k.replace("_", "-"), dest=k, type=float, default=None)
        s.add_argument("--per-clip", dest="per_clip", type=int, default=None)
        s.add_argument("--join", type=int, default=None)
        if c == "gen":
            s.add_argument("--scene")
            s.add_argument("--sound")
            s.add_argument("--sound-prefix", default="")
            s.add_argument("--prompt", help="raw prompt (overrides scene/sound)")
            s.add_argument("--no-extra", action="store_true", help="omit the 'no music, no speech' sentence")
            s.add_argument("--seeds", type=int, default=3)
            s.add_argument("--seed", type=int, default=1)
            s.add_argument("--seconds", type=float, default=None)
            s.add_argument("--frames", type=int, default=None)
            for k, v in DEFAULTS.items():
                s.add_argument("--" + k.replace("_", "-"), dest=k, type=type(v), default=v)
            s.add_argument("--force", action="store_true")
            s.add_argument("--no-cut", action="store_true")
            s.add_argument("--free", action="store_true", help="unload models from ComfyUI afterwards")
    r = sub.add_parser("report")
    r.add_argument("--root", default="assets/audio/h3_test")
    args = ap.parse_args()
    if args.cmd == "list":
        for k, v in PRESETS.items():
            print(f"{k:28s} {v['kind']:9s} {v['seconds']:>4}s  {v['sound'][:80]}")
    elif args.cmd == "gen":
        generate(args)
        if args.free:
            free_comfy()
    elif args.cmd == "cut":
        cut(args)
    else:
        report(args)


if __name__ == "__main__":
    main()
