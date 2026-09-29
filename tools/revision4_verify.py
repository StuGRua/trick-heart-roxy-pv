"""v4完整帧、字幕边界、原音轨、旧交付保护及媒体解码验证。"""
import argparse
import json
import random
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont

import revision4_composite as v4
import chinese_subtitles as zh
from prepare import ROOT,FFMPEG,winpath
from runtime import FONT
from media_verify import digest,run,PROBE,audio_hash

CONTRACT=json.loads((ROOT/'tests/v4-revision-contract.json').read_text())

def sheets():
    folder=ROOT/'review/v4-verification';folder.mkdir(exist_ok=True)
    picks=CONTRACT['witness_frames'];font=ImageFont.truetype(FONT,18)
    for page in range((len(picks)+3)//4):
        sheet=Image.new('RGB',(1440,4*302),'#161922');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*4:page*4+4]):
            for k,(label,dirname) in enumerate([('SOURCE','source'),('V3','full-composite-v3'),('V4','full-composite-v4')]):
                x=k*480;y=j*302;im=Image.open(ROOT/f'frames/{dirname}/{n:05d}.png')
                sheet.paste(im.resize((480,270)),(x,y+30));d.text((x+4,y+3),f'{label} | {n} | {n/24:.3f}s',font=font,fill='white')
        sheet.save(folder/f'page-{page+1:02d}.jpg',quality=97)

def verify_frames():
    zh.configure('v4');info=zh.validate_inputs()
    records=json.loads((ROOT/'review/v4-frame-verification.json').read_text())
    subtitles=json.loads((ROOT/'review/v4-subtitle-frame-verification.json').read_text())
    assert [r['frame'] for r in records]==list(range(3768))
    assert [r['frame'] for r in subtitles]==list(range(3768))
    baseline=json.loads((ROOT/'tests/frame-baseline.json').read_text())['v3']
    changed=[];unchanged=0;no_subtitles=0;hashes={}
    for n in range(3768):
        filename=f'{n:05d}.png';p=v4.DEST/filename
        with Image.open(p) as im:assert im.size==(1920,1080) and im.mode=='RGB'
        sha=digest(p);hashes[filename]=sha
        if not v4.affected(n):assert sha==baseline[filename],('Unexpected change',n)
        if sha==baseline[filename]:unchanged+=1
        else:changed.append(n)
        r=subtitles[n]
        assert r['base_sha256']==sha and r['output_sha256']==digest(zh.DEST/filename)
        assert r['outside_alpha_changed_pixels']==0
        if r['cue'] is None:
            assert r['base_sha256']==r['output_sha256'];no_subtitles+=1
    picks=set(CONTRACT['witness_frames'])
    picks.update(n for a,b in v4.RANGES for n in (a-1,a,a+1,b-1,b) if 0<=n<3768)
    picks=list(picks);random.Random(4).shuffle(picks)
    for n in picks:
        out,_=v4.render(n)
        assert np.array_equal(out,np.asarray(Image.open(v4.DEST/f'{n:05d}.png'))),('Render nondeterminism',n)
    subtitle_picks=sorted({n for cue in zh.CUES for n in [cue['start']-1,cue['start'],cue['end']-1,cue['end']] if 0<=n<3768})
    for n in subtitle_picks:
        out,_,_=zh.render(n)
        assert np.array_equal(np.asarray(out),np.asarray(Image.open(zh.DEST/f'{n:05d}.png'))),('Subtitle boundary',n)
    from revision4_juggle import event_manifest,POSE_REFS
    events=event_manifest()
    assert len(events)==313 and {r['pose_reference'] for r in events}==set(POSE_REFS)
    assert {records[n].get('sofa_pose_reference') for n in range(3356,3397)}=={3356,3365,3376}
    for e in CONTRACT['expression_events']:
        for n in range(e['start'],e['end']):
            r=records[n]
            assert e['asset'] in (r.get('expression'),r.get('asset'),'sofa-awake-v4' if r.get('sofa_state')=='awake' else None),(n,e)
    (ROOT/'review/v4-frame-hashes.json').write_text(json.dumps(hashes,indent=2))
    return {'frames':3768,'changed_frames':len(changed),'unchanged_v3_frames_exact':unchanged,
            'changes_confined_to_declared_intervals':True,'deterministic_checks':len(picks),
            'subtitle_boundary_checks':len(subtitle_picks),'subtitle_alpha_outside_changes':0,
            'no_subtitle_frames_identical':no_subtitles,'juggle_pose_count':len({r['pose_reference'] for r in events}),
            'subtitle_font':info['font'],'input_validation':True}

def verify_media():
    source=ROOT/'research/source-audio.m4s';original={codec:audio_hash(source,codec) for codec in ('copy','pcm_s16le')}
    outputs={}
    for name,width,height in [('roxy-full-v4.mp4',1920,1080),('roxy-full-v4-zh.mp4',1920,1080),('roxy-full-comparison-v4.mp4',3840,1144)]:
        p=ROOT/'deliverables'/name
        probe=json.loads(run(PROBE,['-v','error','-count_frames','-show_streams','-of','json',winpath(p)]).stdout)
        v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
        assert (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_read_frames']))==(width,height,'24/1',3768),name
        assert abs(float(v['duration'])-157)<.001 and abs(float(a['duration'])-157.013333)<.002,name
        audio={codec:audio_hash(p,codec) for codec in original};assert audio==original,name
        result=run(FFMPEG,['-v','error','-xerror','-i',winpath(p),'-f','null','-']);assert not result.stderr.strip(),name
        outputs[name]={'sha256':digest(p),'bytes':p.stat().st_size,'strict_decode':True,'audio_unchanged':True,'frames':3768}
    preserved={}
    for name,sha in CONTRACT['preserved_media'].items():
        p=ROOT/'deliverables'/name
        if p.exists():assert digest(p)==sha,name;preserved[name]=True
        else:preserved[name]='not present in this checkout'
    return {'outputs':outputs,'preserved_v3':preserved,'audio_hashes':original}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--sheets',action='store_true');ap.add_argument('--media-only',action='store_true');args=ap.parse_args()
    if args.sheets:sheets();return
    path=ROOT/'review/v4-verification.json'
    report=json.loads(path.read_text()) if args.media_only and path.exists() else verify_frames()
    report.update(verify_media());path.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
