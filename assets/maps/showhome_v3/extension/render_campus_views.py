"""Render selected review views from the saved campus; does not alter assets."""
import sys
from pathlib import Path
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parent.parent)]
from build_extension import OUT,render_views
bpy.ops.wm.open_mainfile(filepath=str(OUT/'extension.blend'),load_ui=False,use_scripts=False)
selected=set(sys.argv[sys.argv.index('--views')+1].split(',')) if '--views' in sys.argv else None
render_views(selected)
