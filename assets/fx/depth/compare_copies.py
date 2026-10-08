"""Check that the game's texture copies (game/assets/textures/showhome) match the library's (read-only)."""
import hashlib
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.normpath(os.path.join(HERE, "..", "..", "..", "game", "assets", "textures", "showhome"))
LIB = r"F:\git\val etf\assets\maps\showhome\textures"


def md5(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:10]


for f in sorted(os.listdir(GAME)):
    if not f.endswith(".png"):
        continue
    lib = os.path.join(LIB, f)
    a = md5(os.path.join(GAME, f))
    b = md5(lib) if os.path.exists(lib) else "-"
    print(f"{f:44s} {'same' if a == b else 'DIFF'} {a} {b}")
print(sorted(os.listdir(os.path.join(LIB, "_src", "raw"))))
