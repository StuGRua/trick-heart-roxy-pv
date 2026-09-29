"""提取全曲帧，保留试片源缓存并核验像素一致。"""
import hashlib,json,subprocess,shutil
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from prepare import ROOT,SOURCE,FFMPEG,winpath,source_frame
from runtime import FONT

def main():
    free=shutil.disk_usage(ROOT).free
    print('free_GiB',round(free/1024**3,1),flush=True)
    assert free>8*1024**3,'Need 8 GiB free for complete frame caches'
    folder=ROOT/'frames/full-source';folder.mkdir(exist_ok=True)
    if len(list(folder.glob('*.png')))!=3768:
        subprocess.run([FFMPEG,'-v','error','-y','-i',winpath(SOURCE),'-map','0:v:0','-an',
            '-fps_mode','passthrough','-start_number','0',winpath(folder/'%05d.png')],check=True)
    assert len(list(folder.glob('*.png')))==3768
    for n in (624,948,1099,1752,2880):
        assert np.array_equal(np.asarray(Image.open(source_frame(n))),np.asarray(Image.open(folder/f'{n:05d}.png'))),n
    for n in range(3768):
        dst=source_frame(n)
        if not dst.exists():dst.hardlink_to(folder/f'{n:05d}.png')
    print('full_frames',3768,flush=True)
    font=ImageFont.truetype(FONT,17)
    picks=list(range(0,3768,24))
    for page in range((len(picks)+35)//36):
        sheet=Image.new('RGB',(6*320,6*207),'#15171e');d=ImageDraw.Draw(sheet)
        for i,n in enumerate(picks[page*36:(page+1)*36]):
            x=i%6*320;y=i//6*207
            sheet.paste(Image.open(source_frame(n)).resize((320,180)),(x,y+27))
            d.text((x+4,y+3),f'{n:04d} | {n/24:.1f}s',fill='white',font=font)
        sheet.save(ROOT/f'review/full-source-{page+1:02d}.jpg',quality=93)
    (ROOT/'full-map.json').write_text(json.dumps({'fps':24,'frames':3768,'duration':157,'source_file':str(SOURCE)},indent=2))

if __name__=='__main__':main()
