"""Build the self-contained UI mockups and render them to PNG.

  python build.py            # build HTML only
  python build.py --render   # build HTML + render PNGs with headless Chrome/Edge (no Playwright needed)

Sources live next to this file: common.css, icons.svg, widgets.js, pages/*.html.
Outputs: ../<page>.html (self-contained: CSS, SVG icons, JS and images inlined as data URIs;
only Google Fonts is loaded from the web, with a system-font fallback) and ../png/<page>.png.
"""
import base64
import io
import os
import subprocess
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)
IMG_RAW = os.path.join(OUT, "img", "raw")
IMG = os.path.join(OUT, "img")
PNG = os.path.join(OUT, "png")

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&'
         'family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">')

FIT = """<script>
(function(){const s=document.querySelector('.screen');
function fit(){const k=Math.min(innerWidth/1920,innerHeight/1080);s.style.transform='scale('+k+')';}
addEventListener('resize',fit);fit();
const tok=(location.hash||'').replace('#','').split(',');
if(tok.includes('still')){const st=document.createElement('style');st.textContent='*{animation:none!important;transition:none!important}';document.head.appendChild(st);}
window.__tokens=tok;})();
</script>"""

# name -> (raw file, (w, h) output size or None, crop box in raw pixels or None)
IMAGES = {
    "hud_street": ("hud_street_s23.png", (1920, 1080), None),
    "kestrel_portrait": ("kestrel_portrait_s5.png", (640, 640), None),
    "solace_portrait": ("solace_portrait_s5.png", (640, 640), None),
    "mako_dark": ("mako_dark_s3_fixed.png", (1280, 720), None),
    "menu_kestrel": ("menu_kestrel_s17.png", (1920, 1080), None),
    "warden_dark": ("warden_dark_s4.png", (1280, 720), None),
}

# (output html, source page, variant, title, footer label)
PAGES = [
    ("hud.html", "hud.html", "default", "HUD in match", "Mockup 01 · HUD in match · press T: mag check · hold TAB: scoreboard"),
    ("hud_magcheck.html", "hud.html", "mag", "HUD mag check", "Mockup 02 · HUD with mag check open (T)"),
    ("health_panel.html", "health_panel.html", "default", "Health panel", "Mockup 03 · Health + halo close-up, all states"),
    ("main_menu.html", "main_menu.html", "default", "Main menu", "Mockup 04 · Main menu · Play > Join open"),
    ("loadout.html", "loadout.html", "default", "Loadout", "Mockup 05 · Loadout"),
    ("lobby.html", "lobby.html", "default", "Lobby", "Mockup 06 · Lobby (host view)"),
    ("scoreboard.html", "hud.html", "tab", "Scoreboard", "Mockup 07 · Scoreboard (hold TAB)"),
    ("settings.html", "settings.html", "default", "Settings", "Mockup 08 · Settings"),
    ("esc_menu.html", "esc_menu.html", "default", "Match menu", "Mockup 09 · In-match ESC menu (host)"),
    ("death.html", "death.html", "default", "Death recap", "Mockup 10 · Death recap / respawn + downed state"),
]

# (html, hash, png name)
RENDERS = [
    ("hud.html", "still", "01_hud.png"),
    ("hud_magcheck.html", "still", "02_hud_magcheck.png"),
    ("health_panel.html", "still", "03_health_panel.png"),
    ("main_menu.html", "still", "04_main_menu.png"),
    ("main_menu.html", "host,still", "04b_main_menu_host.png"),
    ("loadout.html", "still", "05_loadout.png"),
    ("loadout.html", "attach,still", "05b_loadout_attachment_list.png"),
    ("lobby.html", "still", "06_lobby.png"),
    ("scoreboard.html", "still", "07_scoreboard.png"),
    ("settings.html", "still", "08_settings_mouse.png"),
    ("settings.html", "keybinds,still", "08b_settings_keybinds.png"),
    ("settings.html", "video,still", "08c_settings_video.png"),
    ("settings.html", "audio,still", "08d_settings_audio.png"),
    ("settings.html", "hud,still", "08e_settings_hud.png"),
    ("esc_menu.html", "still", "09_esc_menu.png"),
    ("esc_menu.html", "confirm,still", "09b_esc_stop_hosting.png"),
    ("death.html", "still", "10_death_recap.png"),
    ("death.html", "downed,still", "10b_downed.png"),
]


def read(p):
    with open(os.path.join(HERE, p), encoding="utf-8") as f:
        return f.read()


_cache = {}


def data_uri(name):
    if name in _cache:
        return _cache[name]
    raw, size, crop = IMAGES[name]
    src = os.path.join(IMG_RAW, raw)
    if not os.path.exists(src):
        print("  ! missing image", raw, "(placeholder used)")
        _cache[name] = ""
        return ""
    im = Image.open(src).convert("RGB")
    if crop:
        im = im.crop(crop)
    if size:
        im = im.resize(size, Image.LANCZOS)
    os.makedirs(IMG, exist_ok=True)
    jpg = os.path.join(IMG, name + ".jpg")
    im.save(jpg, quality=84, optimize=True)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84, optimize=True)
    uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    _cache[name] = uri
    return uri


def build():
    css = read("common.css")
    icons = read("icons.svg")
    widgets = read("widgets.js")
    for out, src, variant, title, label in PAGES:
        p = os.path.join(HERE, "pages", src)
        if not os.path.exists(p):
            print("  - skip", out, "(no source yet)")
            continue
        html = read(os.path.join("pages", src))
        html = html.replace("<!--COMMON-->", FONTS + "<style>" + css + "</style>")
        html = html.replace("<!--ICONS-->", icons)
        html = html.replace("<!--WIDGETS-->", "<script>" + widgets + "</script>")
        html = html.replace("<!--FIT-->", FIT)
        html = html.replace("{{variant}}", variant).replace("{{title}}", title).replace("{{label}}", label)
        while "{{img:" in html:
            i = html.index("{{img:")
            j = html.index("}}", i)
            html = html[:i] + data_uri(html[i + 6:j]) + html[j + 2:]
        with open(os.path.join(OUT, out), "w", encoding="utf-8") as f:
            f.write(html)
        print("  built", out, f"{len(html) / 1024:.0f} KB")


INDEX_ITEMS = [
    ("hud.html", "01_hud.png", "HUD in match", "Busy moment: scan card, shield hit marker, damage arcs, bleeding, kill banner. Press T (mag check) or hold TAB (scoreboard)."),
    ("hud_magcheck.html", "02_hud_magcheck.png", "HUD · mag check open", "EFT-style estimate after pressing T. Six words, never a number."),
    ("health_panel.html", "03_health_panel.png", "Health + halo close-up", "Hold-H panel, every zone state (healthy / damaged / critical / destroyed / bleeding), halo widget states, weight classes."),
    ("main_menu.html", "04_main_menu.png", "Main menu · Join", "Play > Join with join code / direct IP / LAN. Open main_menu.html#host for the Host panel."),
    ("main_menu.html#host", "04b_main_menu_host.png", "Main menu · Host", "Create a lobby on your PC (listen server)."),
    ("loadout.html", "05_loadout.png", "Loadout", "Agent, weapon + per-slot attachments with 3D preview, halo core / tier / coverage, resulting stats."),
    ("loadout.html#attach", "05b_loadout_attachment_list.png", "Loadout · attachment list", "Slot list open with stat deltas."),
    ("lobby.html", "06_lobby.png", "Lobby (host view)", "Teams, ready, join code, host match settings, chat, connection health."),
    ("scoreboard.html", "07_scoreboard.png", "Scoreboard (TAB)", "Over the live HUD."),
    ("settings.html", "08_settings_mouse.png", "Settings · Mouse & aim", "cm/360 with Valorant / CS2 / OW2 conversion, ADS scaling, FOV, crosshair."),
    ("settings.html#keybinds", "08b_settings_keybinds.png", "Settings · Keybinds", "Full input map with gamepad column, listening and conflict states."),
    ("settings.html#video", "08c_settings_video.png", "Settings · Video", ""),
    ("settings.html#audio", "08d_settings_audio.png", "Settings · Audio", ""),
    ("settings.html#hud", "08e_settings_hud.png", "Settings · HUD & accessibility", "HUD scale, safe area, colour-blind team colours."),
    ("esc_menu.html", "09_esc_menu.png", "In-match ESC menu (host)", "The game keeps running."),
    ("esc_menu.html#confirm", "09b_esc_stop_hosting.png", "Stop hosting confirm", ""),
    ("death.html", "10_death_recap.png", "Death recap + respawn", "Who killed you, their halo, every hit by zone and shield vs flesh."),
    ("death.html#downed", "10b_downed.png", "Downed state (host option)", ""),
]


def build_index():
    cards = []
    for href, png, title, desc in INDEX_ITEMS:
        cards.append(f'<a class="c" href="{href}"><img src="png/{png}" loading="lazy" alt=""><div class="t">{title}</div>'
                     f'<div class="d">{desc}</div></a>')
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UI Mockups</title>{FONTS}<style>
:root{{--bg:#07090D;--panel:#10151C;--text:#D7D4CD;--hi:#F3F0E9;--mid:#9CA2AB;--teal:#00DACE}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{background:var(--bg);color:var(--text);font-family:'Barlow',sans-serif;padding:40px 16px}}
.w{{max-width:1500px;margin:0 auto}}h1{{font-family:'Barlow Condensed',sans-serif;font-size:44px;letter-spacing:.12em;color:var(--hi)}}
p.s{{color:var(--mid);margin:6px 0 26px;max-width:900px;line-height:1.5}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}}
.c{{display:block;background:var(--panel);border:1px solid rgba(255,255,255,.08);text-decoration:none;color:inherit;padding-bottom:12px}}
.c:hover{{border-color:var(--teal)}}.c img{{width:100%;aspect-ratio:16/9;object-fit:cover;display:block;background:#000}}
.t{{font-family:'Barlow Condensed',sans-serif;font-weight:700;font-size:20px;letter-spacing:.08em;color:var(--hi);padding:10px 12px 0;text-transform:uppercase}}
.d{{font-size:13.5px;color:var(--mid);padding:4px 12px 0;line-height:1.4}}
code{{color:var(--hi)}}</style></head><body><div class="w">
<h1>UI MOCKUPS · HUD + MENUS</h1>
<p class="s">Self-contained HTML at a 1920×1080 canvas (scales to your window). PNG renders in <code>png/</code>. Spec: <code>../UI_DESIGN.md</code>.
Sources and the build script are in <code>_src/</code> (<code>python _src/build.py --render</code>). All art is placeholder: generated backdrops, concept portraits, a painted-over Mako concept.</p>
<div class="g">{''.join(cards)}</div></div></body></html>"""
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("  built index.html")


def find_browser():
    for c in [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]:
        if os.path.exists(c):
            return c
    return None


def render(only=None):
    exe = find_browser()
    if not exe:
        print("no Chrome/Edge found: PNG render skipped")
        return
    os.makedirs(PNG, exist_ok=True)
    for html, h, png in RENDERS:
        if only and not any(o in png for o in only):
            continue
        src = os.path.join(OUT, html)
        if not os.path.exists(src):
            continue
        url = "file:///" + src.replace("\\", "/").replace(" ", "%20") + ("#" + h if h else "")
        out = os.path.join(PNG, png)
        cmd = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
               "--window-size=1920,1080", "--virtual-time-budget=6000", "--run-all-compositor-stages-before-draw",
               f"--screenshot={out}", url]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        print("  rendered", png, "ok" if os.path.exists(out) else "FAILED")


if __name__ == "__main__":
    build()
    build_index()
    if "--render" in sys.argv:
        only = [a for a in sys.argv[1:] if not a.startswith("--")]
        render(only or None)
