"""v2 正片与原片同步对比，音频直接复制。"""
import json,argparse
from prepare import ROOT,TASK,SOURCE,winpath,FFMPEG
from media_encode import run,OUT
from runtime import ffmpeg_font

def compare_versions():
    """对外v1在左、v2在右，使用已交付正片及一条原音轨。"""
    from media_verify import digest,audio_hash,PROBE,run as inspect
    before=OUT/'roxy-full-v3.mp4';after=OUT/'roxy-full-v4.mp4'
    contract=json.loads((ROOT/'tests/v4-revision-contract.json').read_text())
    baseline=json.loads((ROOT/'tests/v4-verification.json').read_text())
    expected={before.name:contract['preserved_media'][before.name],
              after.name:baseline['outputs'][after.name]['sha256']}
    for path in (before,after):
        if digest(path)!=expected[path.name]:raise ValueError('Version input differs from release baseline: '+path.name)
    font=ffmpeg_font(FFMPEG)
    chain='[0:v]settb=1/24,setpts=N[a];[1:v]settb=1/24,setpts=N[b];[a][b]hstack=inputs=2:shortest=1,trim=end_frame=3768,settb=1/24,setpts=N,pad=iw:ih+64:0:64:color=0x181a20'
    chain+=f",drawtext=fontfile='{font}':text='V1':x=960-text_w/2:y=10:fontsize=40:fontcolor=white"
    chain+=f",drawtext=fontfile='{font}':text='V2':x=2880-text_w/2:y=10:fontsize=40:fontcolor=white[v]"
    final=OUT/'roxy-v1-v2-comparison.mp4'
    run('v1-v2-comparison',['-i',winpath(before),'-i',winpath(after),'-filter_complex',chain,
        '-map','[v]','-map','1:a:0','-c:v','libx264','-crf','17','-preset','fast',
        '-pix_fmt','yuv420p','-r','24','-fps_mode','cfr','-c:a','copy'],final)
    meta=json.loads(inspect(PROBE,['-v','error','-count_frames','-show_streams','-of','json',winpath(final)]).stdout)
    video=next(s for s in meta['streams'] if s['codec_type']=='video')
    assert (video['width'],video['height'],video['avg_frame_rate'],int(video['nb_read_frames']))==(3840,1144,'24/1',3768)
    assert abs(float(video['duration'])-157)<.001
    assert len([s for s in meta['streams'] if s['codec_type']=='audio'])==1
    hashes={codec:audio_hash(final,codec) for codec in ('copy','pcm_s16le')}
    assert hashes=={codec:audio_hash(after,codec) for codec in hashes}
    decoded=inspect(FFMPEG,['-v','error','-xerror','-i',winpath(final),'-f','null','-'])
    assert not decoded.stderr.strip()
    for path in (before,after):assert digest(path)==expected[path.name]
    record={'file':final.name,'left':'v1','right':'v2','inputs_sha256':expected,
            'frames':3768,'fps':24,'duration':157,'size':[3840,1144],
            'audio_tracks':1,'audio_hashes':hashes,'strict_decode':True,
            'bytes':final.stat().st_size,'sha256':digest(final)}
    (ROOT/'review/v1-v2-comparison-verification.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2),flush=True)

def main(comparison_only=False,version='v2'):
    frames=ROOT/f'frames/full-composite-{version}'
    assert len(list(frames.glob('*.png')))==3768
    records=json.loads((ROOT/f'review/{version}-frame-verification.json').read_text())
    assert [r['frame'] for r in records]==list(range(3768))
    master=OUT/f'roxy-full-{version}.mp4'
    if not comparison_only:
        run(f'{version}-master',['-framerate','24','-start_number','0','-i',winpath(frames/'%05d.png'),
            '-i',winpath(TASK/'research/source-audio.m4s'),'-map','0:v:0','-map','1:a:0',
            '-c:v','libx264','-crf','15','-preset','slow','-pix_fmt','yuv420p','-c:a','copy'],master)
    font=ffmpeg_font(FFMPEG)
    chain='[0:v]settb=1/24,setpts=N[a];[1:v]settb=1/24,setpts=N[b];[a][b]hstack=inputs=2:shortest=1,trim=end_frame=3768,settb=1/24,setpts=N,pad=iw:ih+64:0:64:color=0x181a20'
    chain+=f",drawtext=fontfile='{font}':text='ORIGINAL PV':x=30:y=16:fontsize=30:fontcolor=white"
    chain+=f",drawtext=fontfile='{font}':text='ROXY {version.upper()} - StuG_III + GPT6Astra':x=1950:y=16:fontsize=30:fontcolor=white[v]"
    run(f'{version}-comparison',['-i',winpath(SOURCE),'-i',winpath(master),'-filter_complex',chain,
        '-map','[v]','-map','1:a:0','-c:v','libx264','-crf','17','-preset','fast',
        '-pix_fmt','yuv420p','-r','24','-fps_mode','cfr','-c:a','copy'],OUT/f'roxy-full-comparison-{version}.mp4')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--comparison-only',action='store_true');ap.add_argument('--compare-versions',action='store_true');ap.add_argument('--version',choices=['v2','v3','v4'],default='v2');args=ap.parse_args()
    if args.compare_versions:compare_versions()
    else:main(args.comparison_only,args.version)
