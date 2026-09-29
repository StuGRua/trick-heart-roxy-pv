"""v3机器验证与返工区间的源片/新版连续联系表。"""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from prepare import ROOT,TASK,FFMPEG,winpath
from media_verify import digest,run,audio_hash,PROBE
from revision3_composite import render,HAND_RANGES,CREDIT_INTERVALS,CREDIT_LINES,FONT
from composite import read
from runtime import FONT as UI_FONT

def qa():
    picks=set()
    for a,b,_ in HAND_RANGES:
        picks.update(range(a,b,3 if b-a<90 else 6));picks.update([max(0,a-1),a,b-1,min(3767,b)])
    for a,b in CREDIT_INTERVALS:picks.update(range(a,b,12));picks.update([a-1,a,b-1,min(3767,b)])
    picks.update([1864,1867,1875,1877,1878,1880,2472,2500,2628]);picks=sorted(picks)
    folder=ROOT/'review/v3-qa';folder.mkdir(exist_ok=True);font=ImageFont.truetype(UI_FONT,18)
    for page in range((len(picks)+7)//8):
        sheet=Image.new('RGB',(1920,4*297),'#171923');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*8:page*8+8]):
            for side,name in enumerate(['source','full-composite-v3']):
                x=(j%2*2+side)*480;y=j//2*297
                im=Image.open(ROOT/f'frames/{name}/{n:05d}.png').resize((480,270));sheet.paste(im,(x,y+27));d.text((x+4,y+3),f'{n} {n/24:.3f}s {"SOURCE" if side==0 else "V3"}',font=font,fill='white')
        sheet.save(folder/f'qa-{page+1:02d}.jpg',quality=96)
    (folder/'index.json').write_text(json.dumps({'frames':picks,'count':len(picks),'pages':(len(picks)+7)//8},indent=2));print('v3 QA',len(picks),flush=True)

def verify():
    baseline=json.loads((TASK/'research/source-baseline.json').read_text());verified=[]
    for name,info in baseline['files'].items():
        p=TASK/'research'/name
        if name=='source-proxy-video.m4s' and not p.exists():continue
        assert digest(p)==info['sha256'],name;verified.append(name)
    rows=json.loads((ROOT/'review/v3-frame-verification.json').read_text());assert [r['frame'] for r in rows]==list(range(3768))
    expected=[n for a,b in CREDIT_INTERVALS for n in range(a,b)]
    assert [r['frame'] for r in rows if r.get('english_credit')]==expected
    assert len(CREDIT_INTERVALS)==2 and all(ord(x)<128 for line in CREDIT_LINES for x in line)
    unchanged=[]
    for r in rows:
        if r.get('reused_v2'):
            n=r['frame'];assert digest(ROOT/f'frames/full-composite-v3/{n:05d}.png')==digest(ROOT/f'frames/full-composite-v2/{n:05d}.png'),n;unchanged.append(n)
    deterministic=[576,2712,3003,1875,24,1075,3720,205,219,549,591,594,597,603,1064,1856,576]
    for n in deterministic:
        a,_=render(n);assert np.array_equal(a,read(ROOT/f'frames/full-composite-v3/{n:05d}.png')),n
    aac=audio_hash(TASK/'research/source-audio.m4s','copy');pcm=audio_hash(TASK/'research/source-audio.m4s','pcm_s16le');media={}
    for name,w,h in [('roxy-full-v3.mp4',1920,1080),('roxy-full-comparison-v3.mp4',3840,1144)]:
        p=ROOT/'deliverables'/name
        data=json.loads(run(PROBE,['-v','error','-count_frames','-show_streams','-show_format','-of','json',winpath(p)]).stdout)
        v=next(s for s in data['streams'] if s['codec_type']=='video');a=next(s for s in data['streams'] if s['codec_type']=='audio')
        assert (v['width'],v['height'])==(w,h) and v['avg_frame_rate']=='24/1' and int(v['nb_read_frames'])==3768
        assert abs(float(v['duration'])-157)<.001 and abs(float(a['duration'])-157.013333)<.002
        assert audio_hash(p,'copy')==aac and audio_hash(p,'pcm_s16le')==pcm
        dec=run(FFMPEG,['-v','error','-xerror','-i',winpath(p),'-f','null','-']);assert not dec.stderr.strip()
        media[name]={'width':w,'height':h,'frames':3768,'video_duration':v['duration'],'audio_duration':a['duration'],'bytes':p.stat().st_size,'sha256':digest(p),'strict_decode':True}
    report={'version':'v3','source_hashes_unchanged':True,'verified_inputs':verified,'frames':3768,'fps':24,'aac_and_pcm_identical':True,'aac_sha256':aac,'pcm_sha256':pcm,'deterministic_frames':deterministic,
        'unchanged_v2_frames_exact':len(unchanged),'bare_hand_redrawn_frames':sum(bool(r.get('hand')) for r in rows),'credit_intervals':CREDIT_INTERVALS,'credit_lines':CREDIT_LINES,'credit_font':{'name':Path(FONT).name,'sha256':digest(Path(FONT))},'media':media,'code_license':'MIT','creative_acceptance':'Pending user review; machine tests do not prove aesthetic acceptance.'}
    (ROOT/'deliverables/v3-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--sheets',action='store_true');args=ap.parse_args();qa() if args.sheets else verify()
