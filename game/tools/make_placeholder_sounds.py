#!/usr/bin/env python3
"""Synthesise the game's placeholder sounds into game/assets/audio/<category>/<name>[_<n>].ogg.

Every file the game plays (game/assets/data/sounds.ron) is made here procedurally from noise bursts, filtered
clicks, tones and seamless loops: short, quiet-ish and clearly placeholders. Real sounds (MiniMax H3 picks)
replace them: copy the picks to game/assets/audio/<category>/<name>_<n>.ogg and list them in sounds.ron.

Only missing files are written, so a real sound already in place is never overwritten; --force rewrites every
placeholder this script makes (and would overwrite a real sound with the same name).

Format: OGG Vorbis, mono. Bevy's default `audio` feature decodes Vorbis (no extra engine feature). The script
encodes with `soundfile` when it can write OGG, else with `ffmpeg` (libvorbis) on PATH. It needs numpy.

    python game/tools/make_placeholder_sounds.py                    # every missing file
    python game/tools/make_placeholder_sounds.py --force ui/click   # rewrite names that start with this

The output is deterministic (fixed seeds, bit-exact encoding), so re-running it changes nothing in git.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

SR = 44100  # effects
SR_AMBIENT = 22050  # the long room-tone loops
OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "audio"))


# ------------------------------------------------------------------------------------------------ building blocks


def n_of(seconds, sr=SR):
    return max(1, int(round(seconds * sr)))


def rng(seed):
    return np.random.default_rng(seed)


def noise(seconds, seed, sr=SR):
    return rng(seed).standard_normal(n_of(seconds, sr))


def spectral(x, shape, sr=SR):
    """Filter in the frequency domain: `shape(freqs)` gives the gain per bin. On a whole loop this keeps the
    signal periodic, so loops made this way have no seam."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / sr)
    return np.fft.irfft(spec * shape(f), len(x))


def band(x, lo, hi, sr=SR, soft=1.6):
    """Band-pass with soft (roughly 12 dB/oct) edges."""

    def shape(f):
        f = np.maximum(f, 1e-3)
        g = 1.0 / (1.0 + (lo / f) ** (2 * soft)) if lo > 0 else np.ones_like(f)
        if hi:
            g = g / (1.0 + (f / hi) ** (2 * soft))
        return g

    return spectral(x, shape, sr)


def lowpass(x, hi, sr=SR):
    return band(x, 0, hi, sr)


def highpass(x, lo, sr=SR):
    return band(x, lo, None, sr)


def env(n, attack, decay, sr=SR, hold=0.0):
    """Linear attack, optional hold, exponential decay (time constant `decay` seconds)."""
    t = np.arange(n) / sr
    a = np.clip(t / max(attack, 1e-5), 0.0, 1.0)
    d = np.exp(-np.maximum(t - attack - hold, 0.0) / max(decay, 1e-5))
    return a * d


def at(total, offset, x, sr=SR):
    """Place `x` into a buffer of `total` seconds at `offset` seconds (clipped to the buffer)."""
    out = np.zeros(n_of(total, sr))
    i = n_of(offset, sr) if offset > 0 else 0
    j = min(len(out), i + len(x))
    out[i:j] += x[: j - i]
    return out


def sine(freq, seconds, sr=SR, phase=0.0):
    t = np.arange(n_of(seconds, sr)) / sr
    return np.sin(2 * np.pi * freq * t + phase)


def chirp(f0, f1, seconds, sr=SR):
    n = n_of(seconds, sr)
    f = np.linspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / sr)


def click(seconds, freq, seed, decay=0.004, noise_mix=0.6, sr=SR):
    """A small mechanical click: a decaying partial plus a filtered noise tick."""
    n = n_of(seconds, sr)
    e = env(n, 0.0004, decay, sr)
    tick = band(noise(seconds, seed, sr), freq * 0.6, freq * 2.2, sr)
    tick /= np.max(np.abs(tick)) + 1e-9
    return (sine(freq, seconds, sr) * (1 - noise_mix) + tick * noise_mix) * e


def thump(freq, seconds, decay, sr=SR):
    n = n_of(seconds, sr)
    # A slight downward pitch drop makes it read as an impact, not a tone.
    f = freq * (1.0 + 0.6 * np.exp(-np.arange(n) / sr / 0.015))
    return np.sin(2 * np.pi * np.cumsum(f) / sr) * env(n, 0.001, decay, sr)


def burst(seconds, seed, lo, hi, attack, decay, sr=SR):
    x = band(noise(seconds, seed, sr), lo, hi, sr)
    x /= np.max(np.abs(x)) + 1e-9
    return x * env(len(x), attack, decay, sr)


def rattle(seconds, seed, density, lo=2000, hi=6000, decay=0.06, sr=SR):
    """Gear rattle / gravel crunch: sparse tiny impulses, filtered, under a decaying envelope."""
    n = n_of(seconds, sr)
    r = rng(seed)
    x = np.zeros(n)
    hits = r.integers(0, n, size=max(1, int(density * seconds)))
    x[hits] = r.uniform(-1, 1, size=len(hits))
    x = band(x, lo, hi, sr)
    x /= np.max(np.abs(x)) + 1e-9
    return x * env(n, 0.002, decay, sr)


def fade(x, fade_in=0.002, fade_out=0.01, sr=SR):
    x = x.copy()
    a, b = n_of(fade_in, sr), n_of(fade_out, sr)
    x[:a] *= np.linspace(0, 1, a)
    x[-b:] *= np.linspace(1, 0, b)
    return x


def norm(x, peak_db):
    return x / (np.max(np.abs(x)) + 1e-9) * 10 ** (peak_db / 20)


def periodic_lfo(n, cycles, depth, phase=0.0):
    """A slow modulation with a whole number of cycles over the loop, so it wraps seamlessly."""
    t = np.arange(n) / n
    return 1.0 - depth * 0.5 * (1 + np.sin(2 * np.pi * cycles * t + phase))


# ------------------------------------------------------------------------------------------------ the sounds


def gun(seed, total, body, crack, boom, tail, sr=SR):
    """A shot: a hard crack, a noise body, a low boom and a filtered tail. Each argument is a tuple of the
    layer's numbers so the three guns differ in character, not just in level."""
    r = rng(seed)
    jitter = lambda v: v * r.uniform(0.93, 1.07)  # noqa: E731 (variation per file)
    x = np.zeros(n_of(total, sr))
    lo, hi, dec, g = crack
    x += g * burst(total, seed + 1, jitter(lo), jitter(hi), 0.0003, dec, sr)
    lo, hi, dec, g = body
    x += g * burst(total, seed + 2, jitter(lo), jitter(hi), 0.001, jitter(dec), sr)
    f, dec, g = boom
    x += g * thump(jitter(f), total, dec, sr)
    hi, dec, g = tail
    x += g * burst(total, seed + 3, 60, jitter(hi), 0.01, jitter(dec), sr)
    return fade(x, 0.0, 0.05, sr)


def shot_mako(i):
    # 5.56-style: punchy, short tail.
    return norm(gun(100 + i, 0.45, (250, 5000, 0.05, 1.0), (1800, 9000, 0.006, 0.8), (85, 0.06, 0.9), (2200, 0.12, 0.35)), -3)


def shot_warden(i):
    # Heavy bolt rifle: big boom, long rolling tail.
    return norm(gun(200 + i, 1.6, (120, 3500, 0.12, 1.0), (1200, 7000, 0.01, 0.9), (52, 0.22, 1.3), (1400, 0.55, 0.55)), -2)


def shot_skink(i):
    # SMG: fast, light, snappy.
    return norm(gun(300 + i, 0.25, (600, 7500, 0.025, 1.0), (2500, 11000, 0.004, 0.7), (130, 0.03, 0.5), (3000, 0.06, 0.25)), -5)


def shot_distant(i):
    # Muffled crack and two echoes off the houses.
    total = 1.4
    crack = lowpass(burst(total, 400 + i, 80, 1500, 0.002, 0.04), 1300)
    x = crack + 0.45 * np.roll(crack, n_of(0.17 + 0.03 * i)) + 0.22 * np.roll(crack, n_of(0.42 + 0.05 * i))
    x += 0.35 * burst(total, 410 + i, 50, 700, 0.03, 0.4)
    return norm(fade(x, 0.0, 0.1), -8)


def dry_fire():
    x = at(0.12, 0.0, click(0.03, 3200, 500, decay=0.003)) + 0.6 * at(0.12, 0.018, click(0.03, 2100, 501))
    return norm(fade(x), -12)


def mag_out():
    total = 0.5
    x = at(total, 0.0, click(0.04, 2600, 510, decay=0.005))
    scrape = burst(0.22, 511, 900, 4500, 0.12, 0.08) * 0.5
    x += at(total, 0.05, scrape)
    x += 0.7 * at(total, 0.28, click(0.06, 900, 512, decay=0.012, noise_mix=0.4))
    return norm(fade(x), -10)


def mag_in():
    total = 0.4
    x = 0.45 * at(total, 0.0, burst(0.12, 520, 900, 4000, 0.06, 0.04))
    x += at(total, 0.11, click(0.08, 1500, 521, decay=0.01, noise_mix=0.5))  # firm seat
    x += 0.5 * at(total, 0.115, thump(160, 0.1, 0.03))
    return norm(fade(x), -8)


def bolt_cycle():
    total = 0.85
    x = at(total, 0.0, click(0.05, 2200, 530, decay=0.006))  # handle up
    x += 0.5 * at(total, 0.04, burst(0.2, 531, 1200, 5000, 0.05, 0.06))  # back
    x += at(total, 0.26, click(0.07, 1300, 532, decay=0.012))  # clack
    x += 0.5 * at(total, 0.36, burst(0.2, 533, 1200, 5000, 0.05, 0.06))  # forward
    x += 1.1 * at(total, 0.58, click(0.08, 1100, 534, decay=0.014))  # locked
    return norm(fade(x), -8)


def fire_mode():
    return norm(fade(at(0.08, 0.0, click(0.05, 3000, 540, decay=0.004))), -12)


def mag_check():
    total = 0.95
    x = at(total, 0.0, click(0.04, 2400, 550))
    x += 0.4 * at(total, 0.04, burst(0.14, 551, 800, 3500, 0.05, 0.04))
    x += 0.4 * at(total, 0.62, burst(0.14, 552, 800, 3500, 0.05, 0.04))
    x += at(total, 0.75, click(0.06, 1600, 553, decay=0.008))
    return norm(fade(x), -12)


def equip():
    total = 0.6
    cloth = burst(0.35, 560, 300, 2500, 0.12, 0.1) * 0.6
    x = at(total, 0.0, cloth)
    x += 0.8 * at(total, 0.22, click(0.1, 1900, 561, decay=0.02, noise_mix=0.3))
    x += 0.4 * at(total, 0.3, rattle(0.2, 562, 220, 2500, 7000, 0.05))
    return norm(fade(x), -12)


def step(surface, i):
    seed = 600 + 10 * ["concrete", "grass", "gravel", "wood"].index(surface) + i
    r = rng(seed)
    total = 0.22
    if surface == "concrete":
        x = burst(total, seed, 80, 1400 * r.uniform(0.85, 1.15), 0.001, 0.035)
        x += 0.6 * burst(total, seed + 1, 2500, 9000, 0.0005, 0.008)
    elif surface == "grass":
        x = burst(total, seed, 1200, 6500, 0.012, 0.05) * 0.8
        x += 0.35 * burst(total, seed + 1, 60, 400, 0.004, 0.04)
    elif surface == "gravel":
        x = rattle(total, seed, 900, 1800, 7500, 0.05)
        x += 0.4 * burst(total, seed + 1, 80, 900, 0.002, 0.03)
    else:  # wood
        f = 170 * r.uniform(0.9, 1.1)
        x = 0.8 * thump(f, total, 0.05) + 0.4 * thump(f * 1.9, total, 0.03)
        x += 0.5 * burst(total, seed + 1, 2000, 8000, 0.0005, 0.006)
    return norm(fade(x, 0.0, 0.03), -10 + r.uniform(-1.5, 0))


def jump():
    total = 0.4
    x = 0.6 * burst(total, 700, 250, 1800, 0.03, 0.06)
    x += 0.5 * at(total, 0.02, rattle(0.3, 701, 260, 2200, 6500, 0.07))
    return norm(fade(x), -10)


def land():
    total = 0.5
    x = burst(total, 710, 40, 350, 0.002, 0.07) + 0.8 * thump(62, total, 0.09)
    x += 0.45 * at(total, 0.01, rattle(0.35, 711, 320, 2200, 6500, 0.08))
    return norm(fade(x), -7)


def slide():
    total = 1.0
    n = n_of(total)
    x = band(noise(total, 720), 350, 3200)
    x *= periodic_lfo(n, 9, 0.35) * env(n, 0.04, 10.0)
    x = x / (np.max(np.abs(x)) + 1e-9)
    x *= np.linspace(1.0, 0.25, n)
    return norm(fade(x, 0.01, 0.2), -11)


def jetpack():
    # Loop: rumble + hiss + a low hum, all periodic over 1.5 s.
    total = 1.5
    n = n_of(total)
    rumble = lowpass(noise(total, 730), 260)
    hiss = band(noise(total, 731), 1500, 7000)
    rumble /= np.max(np.abs(rumble))
    hiss /= np.max(np.abs(hiss))
    hum = sine(90, total) * 0.25 + sine(180, total) * 0.1  # 135 and 270 whole cycles
    x = rumble * 0.9 + hiss * 0.45 * periodic_lfo(n, 6, 0.3) + hum
    return norm(x, -9)


def zipline():
    # Loop: trolley wheels whirring on the cable (a buzzy tone, rattle-modulated) over hiss, 2 s.
    total = 2.0
    n = n_of(total)
    tone = sum(sine(260 * k, total) / k for k in range(1, 6))  # 520 whole cycles
    tone *= periodic_lfo(n, 60, 0.6)
    hiss = band(noise(total, 740), 1800, 6000)
    hiss /= np.max(np.abs(hiss))
    x = tone * 0.5 + hiss * 0.3
    return norm(x, -11)


def hit_flesh():
    total = 0.18
    x = burst(total, 750, 90, 900, 0.001, 0.04) + 0.7 * thump(140, total, 0.05)
    return norm(fade(x), -6)


def hit_head():
    total = 0.32
    ding = (sine(2350, total) + 0.5 * sine(3720, total) + 0.25 * sine(5900, total)) * env(n_of(total), 0.001, 0.08)
    x = ding + 0.6 * burst(total, 760, 120, 1100, 0.001, 0.03)
    return norm(fade(x), -6)


def shield_hit():
    # Glassy tink: inharmonic partials, the game pitches it up per tier.
    total = 0.4
    n = n_of(total)
    x = sum(a * sine(f, total) * env(n, 0.0005, d) for f, a, d in [(2210, 1.0, 0.09), (3340, 0.6, 0.06), (5170, 0.4, 0.04)])
    x += 0.3 * burst(total, 770, 4000, 12000, 0.0003, 0.004)
    return norm(fade(x), -9)


def shield_break():
    total = 0.9
    r = rng(780)
    x = np.zeros(n_of(total))
    for k in range(26):
        t = r.uniform(0, 0.45) * r.uniform(0.2, 1.0)
        f = r.uniform(1800, 6500)
        x += at(total, t, sine(f, 0.2) * env(n_of(0.2), 0.0005, r.uniform(0.02, 0.06))) * r.uniform(0.2, 0.8)
    x += 0.8 * burst(total, 781, 3000, 12000, 0.001, 0.08)
    x += 0.6 * thump(90, total, 0.12)
    return norm(fade(x), -6)


def kill():
    total = 0.3
    a = sine(880, 0.09) * env(n_of(0.09), 0.003, 0.05)
    b = sine(1320, 0.14) * env(n_of(0.14), 0.003, 0.07)
    x = at(total, 0.0, a) + at(total, 0.07, b)
    return norm(fade(x), -8)


def assist():
    # A lighter cousin of the kill confirm: one soft, rising two-note blip.
    total = 0.22
    a = sine(990, 0.07) * env(n_of(0.07), 0.003, 0.035)
    b = sine(1180, 0.1) * env(n_of(0.1), 0.003, 0.05)
    x = at(total, 0.0, a) + at(total, 0.05, b)
    return norm(fade(x), -12)


def announcer_assist():
    # The announcer hook's placeholder: a short airy stinger (a sweep and a chord) until a voice line drops in.
    total = 0.45
    n = n_of(total)
    sweep = chirp(420, 1250, total) * env(n, 0.01, 0.12)
    chord = (sine(660, total) + 0.7 * sine(830, total) + 0.5 * sine(990, total)) * env(n, 0.02, 0.15)
    x = 0.5 * sweep + at(total, 0.06, chord[: n - n_of(0.06)]) + 0.15 * burst(total, 795, 2000, 7000, 0.005, 0.05)
    return norm(fade(x), -12)


def damage_taken():
    total = 0.35
    x = thump(70, total, 0.12) + 0.6 * burst(total, 790, 40, 450, 0.002, 0.06)
    return norm(fade(x), -6)


def heal():
    total = 1.3
    x = 0.5 * at(total, 0.0, burst(0.35, 800, 300, 2500, 0.1, 0.12))  # cloth
    x += at(total, 0.36, click(0.05, 2000, 801, decay=0.006))  # click
    hiss = band(noise(0.8, 802), 3000, 11000)
    hiss = hiss / (np.max(np.abs(hiss)) + 1e-9) * env(len(hiss), 0.02, 0.25)
    x += 0.45 * at(total, 0.4, hiss)
    return norm(fade(x, 0.002, 0.08), -11)


def ui_click():
    return norm(fade(at(0.06, 0.0, click(0.05, 1800, 810, decay=0.006, noise_mix=0.35)), 0.0, 0.01), -12)


def ui_hover():
    x = sine(2600, 0.025) * env(n_of(0.025), 0.001, 0.005)
    return norm(fade(x, 0.0, 0.005), -22)


def ui_confirm():
    total = 0.2
    a = sine(660, 0.07) * env(n_of(0.07), 0.002, 0.03)
    b = sine(990, 0.12) * env(n_of(0.12), 0.002, 0.05)
    return norm(fade(at(total, 0.0, a) + at(total, 0.06, b)), -12)


def ui_back():
    x = chirp(700, 520, 0.12) * env(n_of(0.12), 0.003, 0.04)
    return norm(fade(x), -15)


def showhome_loop():
    # Suburban day: wind, far traffic swells and the odd bird; every layer wraps, so the 20 s loop is seamless.
    sr, total = SR_AMBIENT, 20.0
    n = n_of(total, sr)
    wind = lowpass(noise(total, 900, sr), 700, sr)
    wind /= np.max(np.abs(wind))
    wind *= periodic_lfo(n, 3, 0.6) * periodic_lfo(n, 7, 0.3, 1.0)
    traffic = lowpass(noise(total, 901, sr), 160, sr)
    traffic /= np.max(np.abs(traffic))
    traffic *= periodic_lfo(n, 2, 0.8, 2.0)
    x = 0.55 * wind + 0.45 * traffic
    r = rng(902)
    for _ in range(9):
        t0 = r.uniform(0, total)
        for k in range(r.integers(2, 5)):
            f0 = r.uniform(3000, 4800)
            ch = chirp(f0, f0 * r.uniform(1.1, 1.4), 0.07, sr) * env(n_of(0.07, sr), 0.005, 0.02, sr)
            i = n_of(t0 + 0.11 * k, sr) % n
            idx = (np.arange(len(ch)) + i) % n  # wrap around the loop end
            x[idx] += ch * r.uniform(0.04, 0.09)
    return norm(x, -16)


def range_loop():
    # Indoor range room tone: ventilation airflow and mains hum (whole cycles over 20 s).
    sr, total = SR_AMBIENT, 20.0
    n = n_of(total, sr)
    air = band(noise(total, 910, sr), 180, 1400, sr)
    air /= np.max(np.abs(air))
    air *= periodic_lfo(n, 4, 0.15)
    hum = sine(60, total, sr) * 0.3 + sine(120, total, sr) * 0.18 + sine(180, total, sr) * 0.07
    return norm(0.6 * air + hum, -18)


def sounds():
    """Every file: name (under game/assets/audio, no extension) -> (samples, sample rate, vorbis quality)."""
    s = {}
    for i in range(1, 4):
        s[f"weapons/mako_shot_{i}"] = shot_mako(i)
        s[f"weapons/warden_shot_{i}"] = shot_warden(i)
        s[f"weapons/skink_shot_{i}"] = shot_skink(i)
    for i in range(1, 3):
        s[f"weapons/shot_distant_{i}"] = shot_distant(i)
    s["weapons/dry_fire"] = dry_fire()
    s["weapons/mag_out"] = mag_out()
    s["weapons/mag_in"] = mag_in()
    s["weapons/bolt_cycle"] = bolt_cycle()
    s["weapons/fire_mode"] = fire_mode()
    s["weapons/mag_check"] = mag_check()
    s["weapons/equip"] = equip()
    for surface in ["concrete", "grass", "gravel", "wood"]:
        for i in range(1, 4):
            s[f"movement/step_{surface}_{i}"] = step(surface, i)
    s["movement/jump"] = jump()
    s["movement/land"] = land()
    s["movement/slide"] = slide()
    s["movement/jetpack"] = jetpack()
    s["movement/zipline"] = zipline()
    s["combat/hit_flesh"] = hit_flesh()
    s["combat/hit_head"] = hit_head()
    s["combat/shield_hit"] = shield_hit()
    s["combat/shield_break"] = shield_break()
    s["combat/kill"] = kill()
    s["combat/damage_taken"] = damage_taken()
    s["combat/assist"] = assist()
    s["announcer/assist"] = announcer_assist()
    s["items/heal"] = heal()
    s["ui/click"] = ui_click()
    s["ui/hover"] = ui_hover()
    s["ui/confirm"] = ui_confirm()
    s["ui/back"] = ui_back()
    out = {k: (v, SR, 3) for k, v in s.items()}
    out["ambient/showhome_loop"] = (showhome_loop(), SR_AMBIENT, 0)
    out["ambient/range_loop"] = (range_loop(), SR_AMBIENT, 0)
    return out


# ------------------------------------------------------------------------------------------------ writing


def write_wav(path, x, sr):
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def encoder():
    try:
        import soundfile  # noqa: F401

        if "OGG" in soundfile.available_formats():
            return "soundfile"
    except ImportError:
        pass
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    sys.exit("needs soundfile (with OGG support) or ffmpeg with libvorbis on PATH to write .ogg")


def write_ogg(path, x, sr, quality, how, tmp):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if how == "soundfile":
        import soundfile

        soundfile.write(path, np.clip(x, -1.0, 1.0), sr, format="OGG", subtype="VORBIS")
        return
    wav = os.path.join(tmp, "in.wav")
    write_wav(wav, x, sr)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-map_metadata", "-1", "-fflags", "+bitexact",
           "-flags:a", "+bitexact", "-c:a", "libvorbis", "-q:a", str(quality), path]
    subprocess.run(cmd, check=True)


def main():
    args = sys.argv[1:]
    force = "--force" in args
    names = [a for a in args if a != "--force"]
    only = names[0] if names else ""
    how = encoder()
    total, kept = 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, (x, sr, quality) in sorted(sounds().items()):
            if not name.startswith(only):
                continue
            path = os.path.join(OUT, *name.split("/")) + ".ogg"
            if os.path.exists(path) and not force:
                kept += 1
                continue
            write_ogg(path, x.astype(np.float64), sr, quality, how, tmp)
            size = os.path.getsize(path)
            total += size
            print(f"{name}.ogg  {len(x) / sr:5.2f} s  {size / 1024:6.1f} KiB")
    print(f"wrote {total / 1024:.0f} KiB in {OUT} ({how}); kept {kept} existing files (--force rewrites them)")


if __name__ == "__main__":
    main()
