"""分别打包白名单代码与非MIT资源；不包含原曲、原PV或成片。"""
import hashlib,json,zipfile
from pathlib import Path
from check_public import ROOT,public_files,main as check_public

def sha(b):return hashlib.sha256(b).hexdigest()

def write_zip(name,entries):
    out=ROOT/'deliverables';out.mkdir(exist_ok=True)
    index={n:{'bytes':len(b),'sha256':sha(b)} for n,b in entries.items()}
    entries['release-manifest.json']=(json.dumps(index,ensure_ascii=False,indent=2)+'\n').encode()
    p=out/name
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,b in sorted(entries.items()):z.writestr('trick-heart-roxy-pv/'+n,b)
    with zipfile.ZipFile(p) as z:
        assert z.testzip() is None
        for n,r in index.items():assert sha(z.read('trick-heart-roxy-pv/'+n))==r['sha256']
    return {'file':name,'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),'files':len(entries)}

def main():
    check_public()
    code={n:p.read_bytes() for n,p in public_files()}
    resources=json.loads((ROOT/'assets/resources.json').read_text())['files'];art={}
    for name,r in resources.items():
        p=(ROOT/name).resolve();p.relative_to(ROOT);b=p.read_bytes()
        assert sha(b)==r['sha256'],name;art[name]=b
    art['ASSET-NOTICE.md']=(ROOT/'ASSET-NOTICE.md').read_bytes()
    records=[write_zip('trick-heart-roxy-pv-source.zip',code),write_zip('trick-heart-roxy-pv-resources.zip',art)]
    (ROOT/'deliverables/release-packages.json').write_text(json.dumps({'packages':records,'published':False,'original_media_included':False},indent=2));print(json.dumps(records,indent=2))

if __name__=='__main__':main()
