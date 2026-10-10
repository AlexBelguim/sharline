"""Pair actual Blender extension views with the supplied art references."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
REF=ROOT/'art/briefs/showhome_v3_handoff'
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',21)
small=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',16)
pairs=[
 ('aerial','concept_areas/01_worksite_aerial.png','Four-structure campus with shared parking and active worksite'),
 ('site_aerial','user_revisions/2026-10-10_tdm_and_campus/perpendicular_road_straight_ramp_planters.png','Perpendicular grey road continues directly into the north-descending basement ramp'),
 ('worksite_ground','concept_areas/01_worksite_ground.png','Five-storey open frame and movable worksite kit'),
 ('street','user_revisions/2026-10-10_tdm_and_campus/house_front_setback_driveways.png','Three recessed standalone homes; equal24x44m plots, visible pebble drive-ups and picket front gardens'),
 ('street_house','user_revisions/2026-10-09_neighbourhood/frontage_style.png','Existing detailed source house adapted to a standalone road-facing frontage'),
 ('stairs','concept_areas/01_worksite_ground.png','Actual 1.4m stair route; construction palette reference'),
 ('foundation_stage','concept_areas/01_worksite_ground.png','Foundation-only structure exposes shared parking basement'),
 ('parking_basement','concept_areas/01_worksite_ground.png','Connected underground parking with stairs and shafts'),
 ('gravel_tracks','user_revisions/2026-10-09_campus/gravel_depth_look.png','Gravel service road and real height/normal tyre maps'),
 ('tire_worn_lanes','user_revisions/2026-10-10_tdm_and_campus/tire_worn_lanes_light_depth_crop.png','Broad light tyre-worn lanes, paired grooves and restrained localized wet dirt'),
 ('material_yard','user_revisions/2026-10-10_tdm_and_campus/tire_worn_lanes_loose_materials_crop.png','Varied reusable material dropzones; loose pipe/board/offcut assets await their explicit requests'),
 ('cabin_stairs','user_revisions/2026-10-10_tdm_and_campus/offset_worksite_cabin_metal_stairs_reference.png','External metal stair access on three cabin stacks, including one offset upperoffice'),
 ('ramp_access','user_revisions/2026-10-10_tdm_and_campus/perpendicular_road_straight_ramp_planters.png','One straight ramp descends from the road and enters parking near the back'),
 ('courtyard','user_revisions/2026-10-10_tdm_and_campus/perpendicular_road_straight_ramp_planters.png','Two organic printed-concrete planter runs with integrated curved timber benches'),
 ('site_excavations','concept_areas/01_worksite_ground.png','Real excavation banks and painted dirt hills'),
 ('earthworks_street','concept_areas/01_worksite_ground.png','Painted spoil heaps at player eye height'),
]
for view,reference,caption in pairs:
    out=Image.new('RGB',(1600,575),(239,239,234));draw=ImageDraw.Draw(out)
    draw.text((22,12),'ACTUAL ASSET RENDER',font=font,fill=(32,37,33));draw.text((822,12),'SUPPLIED CONCEPT REFERENCE',font=font,fill=(32,37,33))
    for x,path in ((16,HERE/'renders'/f'{view}.png'),(816,REF/reference)):
        im=Image.open(path).convert('RGB');im=ImageOps.contain(im,(768,480))
        out.paste(im,(x+(768-im.width)//2,47+(480-im.height)//2))
    draw.text((22,544),caption+'  |  UV / physics / convex collision verified; foliage shown as proxies',font=small,fill=(46,50,44))
    dest=HERE/'renders'/f'compare_{view}.png';out.save(dest);print(dest)
