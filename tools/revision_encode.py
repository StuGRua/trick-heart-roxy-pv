"""v2 正片与原片同步对比，音频直接复制。"""
import json,argparse
from prepare import ROOT,TASK,SOURCE,winpath,FFMPEG
from media_encode import run,OUT
from runtime import ffmpeg_font

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
    ap=argparse.ArgumentParser();ap.add_argument('--comparison-only',action='store_true');ap.add_argument('--version',choices=['v2','v3','v4'],default='v2');args=ap.parse_args();main(args.comparison_only,args.version)
