"""独立中文字幕层：冻结v3底片，用户译文是唯一文字来源。"""
import argparse,hashlib,json,multiprocessing,shutil,struct
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from prepare import ROOT,TASK,FFMPEG,winpath
from media_encode import run

DATA=ROOT/'subtitles';BASE=ROOT/'frames/full-composite-v3';DEST=ROOT/'frames/full-composite-v3-zh'
FONT=ROOT/'assets/fonts/ZCOOLKuaiLe-Regular.ttf'
SOURCE=(DATA/'translation.txt').read_text(encoding='utf-8-sig').splitlines()
CONFIG=json.loads((DATA/'cues.zh.json').read_text())
CUES=CONFIG['cues']

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def words(cue):return '\n'.join(SOURCE[i-1] for i in cue['source_lines']) if cue.get('line_break') else ' '.join(SOURCE[i-1] for i in cue['source_lines'])

@lru_cache(maxsize=1)
def covered_characters():
    # 固定TTF的Unicode BMP cmap，验证缺字而不是静默回退系统字体。
    data=FONT.read_bytes();u16=lambda p:struct.unpack_from('>H',data,p)[0];u32=lambda p:struct.unpack_from('>I',data,p)[0]
    tables={data[p:p+4]:u32(p+8) for p in range(12,12+16*u16(4),16)};base=tables[b'cmap'];chars=set()
    for p in range(base+4,base+4+8*u16(base+2),8):
        if u16(p) not in (0,3):continue
        t=base+u32(p+4)
        if u16(t)!=4:continue
        count=u16(t+6)//2;ends=t+14;starts=ends+count*2+2;deltas=starts+count*2;offsets=deltas+count*2
        for i in range(count):
            delta=u16(deltas+i*2);offset=u16(offsets+i*2)
            for ch in range(u16(starts+i*2),u16(ends+i*2)+1):
                glyph=u16(offsets+i*2+offset+2*(ch-u16(starts+i*2))) if offset else ch
                if glyph and ((glyph+delta)&65535):chars.add(ch)
    return chars

def validate_inputs():
    baseline=json.loads((DATA/'input-baseline.json').read_text())
    for name,sha in baseline.items():
        p=ROOT/name
        # 字幕附件只需底片帧；已有MP4时才校验旧版本文件。
        if name.startswith('deliverables/') and not p.exists():continue
        assert digest(p)==sha,name
    assert sorted(i for c in CUES for i in c['source_lines'])==list(range(1,53))
    assert all(0<=c['start']<c['end']<=3768 for c in CUES)
    assert all(a['end']<=b['start'] for a,b in zip(CUES,CUES[1:]))
    missing=sorted({ch for c in CUES for ch in words(c) if not ch.isspace() and ord(ch) not in covered_characters()})
    assert not missing,('Missing font glyphs',missing)
    assert not any(c['start']<2785 and c['end']>2702 or c['start']<3768 and c['end']>3698 for c in CUES),'No subtitles over English credits'
    return {'translation_lines':52,'cues':len(CUES),'font':ImageFont.truetype(str(FONT),48).getname(),'missing_glyphs':missing,'input_hashes':baseline}

def active(n):return next((c for c in CUES if c['start']<=n<c['end']),None)

@lru_cache(maxsize=64)
def lettering(cue_id):
    c=next(c for c in CUES if c['id']==cue_id);font=ImageFont.truetype(str(FONT),c.get('size',48));lines=words(c).splitlines();maxw=c.get('max_width',1400)
    assert max(font.getlength(line) for line in lines)<=maxw,(cue_id,'Text exceeds planned width')
    im=Image.new('RGBA',(1920,1080));d=ImageDraw.Draw(im);x,y=c.get('position',[960,1020]);step=58
    for j,line in enumerate(lines):
        top=round(y+(j-(len(lines)-1)/2)*step)
        d.text((x+1,top+2),line,font=font,anchor='mm',fill=(58,18,25,180),stroke_width=2,stroke_fill=(58,18,25,180))
        d.text((x,top),line,font=font,anchor='mm',fill=(255,242,210,255),stroke_width=1,stroke_fill=(71,25,31,230))
    box=im.getbbox();assert box and box[0]>=32 and box[1]>=32 and box[2]<=1888 and box[3]<=1060,(cue_id,box)
    return im,box

def render(n):
    base=Image.open(BASE/f'{n:05d}.png').convert('RGB');c=active(n)
    if c is None:return base,None,{'frame':n,'cue':None,'base_sha256':digest(BASE/f'{n:05d}.png')}
    layer,box=lettering(c['id']);layer=layer.copy();fade=min(1,(n-c['start']+1)/2,(c['end']-n)/2)
    if fade<1:layer.putalpha(layer.getchannel('A').point(lambda v:round(v*fade)))
    out=Image.alpha_composite(base.convert('RGBA'),layer).convert('RGB')
    # 全帧检查：字幕透明区域必须与底片逐像素相同。
    before=np.asarray(base);after=np.asarray(out);mask=np.asarray(layer.getchannel('A'))>0;changed=np.any(before!=after,axis=2)
    assert not np.any(changed&~mask),n
    return out,mask,{'frame':n,'cue':c['id'],'subtitle_box':box,'changed_pixels':int(changed.sum()),'outside_alpha_changed_pixels':0,'base_sha256':digest(BASE/f'{n:05d}.png')}

def one(n):
    if active(n) is None:
        p=BASE/f'{n:05d}.png';shutil.copyfile(p,DEST/p.name)
        return {'frame':n,'cue':None,'base_sha256':digest(p),'output_sha256':digest(DEST/p.name),'outside_alpha_changed_pixels':0}
    out,_,r=render(n);p=DEST/f'{n:05d}.png';out.save(p,compress_level=3);r['output_sha256']=digest(p);return r

def stamp(frame):
    ms=round(frame*1000/24);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def export_text():
    s='\n\n'.join(f'{i}\n{stamp(c["start"])} --> {stamp(c["end"])}\n{words(c)}' for i,c in enumerate(CUES,1))+'\n'
    (DATA/'roxy-zh.srt').write_text(s,encoding='utf-8-sig')
    lines=['# 中文字幕时间轴','', '| 序号 | 开始 | 结束 | 原文行 | 译文 |','| --- | --- | --- | --- | --- |']
    for c in CUES:lines.append(f'| {c["id"]} | {c["start"]/24:.3f} | {c["end"]/24:.3f} | {c["source_lines"]} | {words(c).replace(chr(10)," / ")} |')
    (DATA/'timing-review.md').write_text('\n'.join(lines)+'\n')

def preview():
    folder=ROOT/'review/chinese-subtitles';folder.mkdir(exist_ok=True);font=ImageFont.truetype(str(FONT),18)
    picks=sorted(set([(c['start']+c['end'])//2 for c in CUES]+[2702,3720,624,912,1018,1543,1585,2007,2139,2952,3397,3584,3666]))
    for page in range((len(picks)+11)//12):
        sheet=Image.new('RGB',(1920,900),'#171923');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*12:page*12+12]):
            out,_,r=render(n);out.save(folder/f'{n:05d}.png');x=j%4*480;y=j//4*300;sheet.paste(out.resize((480,270)),(x,y+30));d.text((x+4,y+4),f'{n} | {n/24:.3f}s | {r["cue"]}',font=font,fill='white')
        sheet.save(folder/f'preview-{page+1}.jpg',quality=96)
    (folder/'index.json').write_text(json.dumps(picks));print('Subtitle preview',len(picks),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--render',action='store_true');ap.add_argument('--encode',action='store_true');args=ap.parse_args()
    info=validate_inputs();export_text();print(json.dumps(info,ensure_ascii=False),flush=True)
    if args.render:
        DEST.mkdir(exist_ok=True);records=[]
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn')) as pool:
            for i,r in enumerate(pool.map(one,range(3768),chunksize=16)):
                records.append(r)
                if i%240==0:print('Subtitle frames',i,'/3768',flush=True)
        (ROOT/'review/subtitle-frame-verification.json').write_text(json.dumps(records,indent=2))
    elif not args.encode:preview()
    if args.encode:
        assert len(list(DEST.glob('*.png')))==3768
        run('v3-zh-master',['-framerate','24','-start_number','0','-i',winpath(DEST/'%05d.png'),'-i',winpath(TASK/'research/source-audio.m4s'),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-crf','15','-preset','slow','-pix_fmt','yuv420p','-c:a','copy'],ROOT/'deliverables/roxy-full-v3-zh.mp4')

if __name__=='__main__':main()
