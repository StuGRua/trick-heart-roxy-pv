"""提取试片源帧与可追溯的镜头观察图。"""
from pathlib import Path
import json
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from runtime import executable,FONT

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT
FFMPEG = executable('ffmpeg')
SOURCE = TASK / 'research/source-1080.mp4'
WINDOWS = [(624, 792), (912, 1104), (1680, 1776), (2832, 2952)]

def winpath(path):
    s = str(path.resolve())
    if s.startswith('/mnt/') and FFMPEG.lower().endswith('.exe'):
        return s[5].upper() + ':' + s[6:]
    return s

def source_frame(n):
    return ROOT / f'frames/source/{n:05d}.png'

def export():
    for a, b in WINDOWS:
        if all(source_frame(n).exists() for n in range(a, b)):
            continue
        subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', str(a/24), '-i',
            winpath(SOURCE), '-t', str((b-a)/24), '-an', '-fps_mode', 'passthrough',
            '-start_number', str(a), winpath(source_frame(0)).replace('00000.png','%05d.png')], check=True)
    mapping = [{'sample_frame': i, 'source_frame': n, 'source_time': n/24}
        for i,n in enumerate(n for a,b in WINDOWS for n in range(a,b))]
    (ROOT/'sample-map.json').write_text(json.dumps(mapping, indent=2))
    print('source_frames',len(mapping),flush=True)

def overview():
    scores=[]
    for a,b in WINDOWS:
        last=None
        for n in range(a,b):
            im=np.asarray(Image.open(source_frame(n)).resize((240,135)),dtype=np.float32)
            value=float(np.abs(im-last).mean()) if last is not None else 0
            scores.append({'frame':n,'mean_abs_diff':round(value,3)})
            last=im
    (ROOT/'review/frame-differences.json').write_text(json.dumps(scores,indent=2))
    candidates=[x['frame'] for x in scores if x['mean_abs_diff']>8]
    print('candidate_transitions',candidates,flush=True)
    picks=sorted(set([n for a,b in WINDOWS for n in range(a,b,12)]+candidates))
    font=ImageFont.truetype(FONT,17)
    for page in range((len(picks)+19)//20):
        sheet=Image.new('RGB',(4*384,5*244),'#1d1e24');draw=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*20:(page+1)*20]):
            x=(j%4)*384;y=(j//4)*244
            sheet.paste(Image.open(source_frame(n)).resize((384,216)),(x,y+28))
            draw.text((x+5,y+5),f'{n:05d}   {n/24:.3f} s',font=font,fill='white')
        sheet.save(ROOT/f'review/source-detail-{page+1:02d}.jpg',quality=93)

if __name__=='__main__':
    export()
    overview()
