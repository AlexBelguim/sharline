"""Externalize embedded GLB images once, retaining geometry buffers and PBR semantics."""
import json,struct,hashlib,os
from pathlib import Path
def read(path):
    raw=Path(path).read_bytes();offset=12;chunks={}
    while offset<len(raw):
        n,t=struct.unpack_from('<II',raw,offset);chunks[t]=raw[offset+8:offset+8+n];offset+=8+n
    return json.loads(chunks[0x4e4f534a]),chunks.get(0x004e4942,b'')
def save(path,j,buf):
    js=json.dumps(j,separators=(',',':')).encode();js+=b' '*((-len(js))%4);buf+=b'\0'*((-len(buf))%4)
    body=struct.pack('<II',len(js),0x4e4f534a)+js
    if buf:body+=struct.pack('<II',len(buf),0x004e4942)+buf
    Path(path).write_bytes(struct.pack('<III',0x46546c67,2,len(body)+12)+body)
def externalize(path,texture_dir):
    path=Path(path);texture_dir=Path(texture_dir);texture_dir.mkdir(parents=True,exist_ok=True);j,buf=read(path);images=[];image_views=set()
    for im in j.get('images',[]):
        if 'bufferView' not in im:continue
        idx=im.pop('bufferView');image_views.add(idx);v=j['bufferViews'][idx];data=buf[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
        ext='.png' if im.get('mimeType')=='image/png' else '.jpg';name=hashlib.sha256(data).hexdigest()[:24]+ext;dest=texture_dir/name
        if not dest.exists():dest.write_bytes(data)
        im['uri']=os.path.relpath(dest,path.parent).replace('\\','/');images.append(name)
    if not image_views:return j,images
    # Preserve every non-image bufferView, with valid four-byte alignment.
    new=bytearray();views=[];remap={}
    for i,v in enumerate(j.get('bufferViews',[])):
        if i in image_views:continue
        new.extend(b'\0'*((-len(new))%4));off=len(new);new.extend(buf[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]);nv=dict(v,buffer=0,byteOffset=off);remap[i]=len(views);views.append(nv)
    for a in j.get('accessors',[]):
        if 'bufferView' in a:a['bufferView']=remap[a['bufferView']]
        for s in a.get('sparse',{}).values():
            if isinstance(s,dict) and 'bufferView' in s:s['bufferView']=remap[s['bufferView']]
    j['bufferViews']=views;j['buffers']=[{'byteLength':len(new)}];save(path,j,bytes(new));return j,images
if __name__=='__main__':
    import sys
    externalize(sys.argv[1],sys.argv[2])
