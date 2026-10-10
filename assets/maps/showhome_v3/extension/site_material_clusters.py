"""Source-only staging of existing reusable worksite materials.

No catalog writes or new meshes. The missing loose pipes, boards and block
offcuts are explicit deferred asset requests in loose_material_requests.json.
"""
CLUSTERS=[
    dict(name='receiving_corner',items=[
        ('timber_pallet',(315.7,758.5,0),14,1.1),('printed_blocks_pallet',(317.4,758.1,0),-6,1),('toolbox',(316,759.6,0),32,1)]),
    dict(name='fabrication_sorting',items=[
        ('printed_blocks_pallet',(331,755.8,0),13,.95),('rebar_bundle',(332,755.4,0),88,1),('timber_pallet',(332.2,759.9,0),8,.9),('toolbox',(331.1,760.2,0),-21,1)]),
    dict(name='west_frame_drop',items=[
        ('printed_blocks_pallet',(334.1,786.6,0),31,1),('timber_pallet',(333.9,788.2,0),-9,.86),('gang_box',(335.5,786.5,0),5,1),('toolbox',(335.7,788.4,0),-17,1)]),
    dict(name='east_frame_drop',items=[
        ('printed_blocks_pallet',(427.5,782,0),11,1),('timber_pallet',(427.5,784.2,0),-18,.95),('rebar_bundle',(429,785,0),90,1),('toolbox',(429.3,781.2,0),23,1)]),
    dict(name='northwest_frame_drop',items=[
        ('printed_blocks_pallet',(334,885,0),-13,.94),('timber_pallet',(332.5,887,0),19,1.04),('rebar_bundle',(334,882,0),98,1),('gang_box',(331.1,884.3,0),8,1)]),
    dict(name='open_foundation_floor_supplies',items=[
        ('printed_blocks_pallet',(403,854,-3.2),-4,1),('timber_pallet',(400.9,854.3,-3.2),14,1),('rebar_bundle',(402,857,-3.2),8,.9),('toolbox',(403.5,856.1,-3.2),26,1)]),
]

def place_clusters(place):
    records=[]
    for cluster in CLUSTERS:
        ids=[]
        for pid,pos,yaw,scale in cluster['items']:ids.append(place(pid,pos,yaw,scale)['id'])
        records.append(dict(name=cluster['name'],instance_ids=ids,reusable_catalog_ids=sorted({p[0] for p in cluster['items']}),items=len(ids),source='construction concept: varied small material drop zones',new_meshes=False))
    return records

def place_ready_requests(place,catalog):
    # A later approved asset build can satisfy these IDs. Source assembly only
    # places already-catalogued props; it never generates or registers meshes.
    import json
    from pathlib import Path
    requests=json.loads((Path(__file__).resolve().parent/'loose_material_requests.json').read_text())['assets'];result=[]
    for request in requests:
        pid=request['requested_id'];ids=[]
        if pid in catalog:
            for placement in request['planned_positions']:ids.append(place(pid,placement['position'],placement['yaw_deg'])['id'])
        result.append(dict(id=pid,catalog_ready=pid in catalog,instance_ids=ids,status='placed_from_existing_catalog' if ids else 'explicit_mesh_request_pending'))
    return result
