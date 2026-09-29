"""在相同依赖/字体下验证完整重建与已交付帧一致。"""
import hashlib,json
from pathlib import Path
from prepare import ROOT

def main():
    baseline=json.loads((ROOT/'tests/frame-baseline.json').read_text());variants={}
    for variant,expected in baseline.items():
        folder=ROOT/f'frames/full-composite-{variant}';actual={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.png')}
        missing=sorted(set(expected)-set(actual));extra=sorted(set(actual)-set(expected));changed=[n for n in expected if n in actual and expected[n]!=actual[n]]
        variants[variant]={'expected_frames':len(expected),'actual_frames':len(actual),'missing':missing,'extra':extra,'changed':changed}
    media={}
    for report in ['v3-verification.json','subtitle-verification.json']:
        data=json.loads((ROOT/'tests'/report).read_text());items=data['media']
        if 'file' in items:items={items['file']:items}
        for name,r in items.items():media[name]=hashlib.sha256((ROOT/'deliverables'/name).read_bytes()).hexdigest()==r['sha256']
    result={'variants':variants,'media_hashes_match_delivered':media};(ROOT/'review/migration-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    assert all(not x['missing'] and not x['extra'] and not x['changed'] for x in variants.values()),'Rebuilt frames differ; retain old caches and inspect'
    assert all(media.values()),'Encoded media differs; inspect before delivery'

if __name__=='__main__':main()
