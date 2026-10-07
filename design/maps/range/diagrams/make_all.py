"""Re-render every range-map diagram from layout_data.py.  Run:  python make_all.py"""
import draw_site_layout
import draw_aimlab
import draw_range_lanes
import draw_course

for mod in (draw_site_layout, draw_aimlab, draw_range_lanes, draw_course):
    mod.main()
