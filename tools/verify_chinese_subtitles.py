"""中文字幕版：逐帧范围、底片、音频与输出媒体验证。"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from chinese_subtitles import ROOT,TASK,BASE,DEST,CUES,DATA,render,validate_inputs,digest,words
from media_verify import run,PROBE,audio_hash
from prepare import FFMPEG,winpath

def main():
    info=validate_inputs();records=json.loads((ROOT/'review/subtitle-frame-verification.json').read_text())
    assert [r['frame'] for r in records]==list(range(3768));changed=0;unchanged=0
    for r in records:
        n=r['frame'];assert digest(BASE/f'{n:05d}.png')==r['base_sha256'],('Base changed',n)
        assert digest(DEST/f'{n:05d}.png')==r['output_sha256'],('Output changed',n)
        assert r['outside_alpha_changed_pixels']==0
        if r['cue'] is None:assert r['base_sha256']==r['output_sha256'];unchanged+=1
        else:changed+=1
    # 切入/切出边界和乱序重渲，覆盖无字幕间奏及两处英文署名。
    picks=sorted({n for c in CUES for n in [c['start']-1,c['start'],c['start']+1,c['end']-1,c['end']] if 0<=n<3768})
    for n in [3720,576,2702,11,3440,1018,576]+picks:
        a,_,_=render(n);assert np.array_equal(np.asarray(a),np.asarray(Image.open(DEST/f'{n:05d}.png').convert('RGB'))),n
    p=ROOT/'deliverables/roxy-full-v3-zh.mp4';probe=json.loads(run(PROBE,['-v','error','-count_frames','-show_streams','-of','json',winpath(p)]).stdout)
    v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_read_frames']))==(1920,1080,'24/1',3768)
    assert abs(float(v['duration'])-157)<.001 and abs(float(a['duration'])-157.013333)<.002
    audio={}
    for codec in ['copy','pcm_s16le']:
        audio[codec]=audio_hash(p,codec);assert audio[codec]==audio_hash(TASK/'research/source-audio.m4s',codec)
    decoded=run(FFMPEG,['-v','error','-xerror','-i',winpath(p),'-f','null','-']);assert not decoded.stderr.strip()
    report={**info,'frames':3768,'fps':24,'captioned_frames':changed,'no_caption_frames_exact':unchanged,'all_base_frame_hashes_unchanged':True,'all_output_frame_hashes_verified':True,'outside_subtitle_alpha_changed_pixels':0,'deterministic_boundary_frames':len(picks),'existing_english_credits_preserved':True,'audio_hashes':audio,'strict_decode':True,'media':{'file':p.name,'sha256':digest(p),'bytes':p.stat().st_size,'video_duration':v['duration'],'audio_duration':a['duration']},'timing_basis':'Source PV Japanese visual lyric events, not speech recognition or original subtitle timestamps','visual_review':'See docs/pipeline.md and docs/validation.md; prior visual review is retained in the external migration archive'}
    (ROOT/'deliverables/subtitle-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
