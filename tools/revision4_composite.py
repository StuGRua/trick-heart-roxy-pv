"""v4视觉返修：独立入口，保留v3算法与已发布媒体。

按源事件切换原画；纸框与前景物体分离，禁止全屏按相近颜色恢复旧人物。
"""
import argparse
import json
import multiprocessing
import shutil
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache

import composite as c
import full_composite as f
import revision_composite as v2
import revision3_composite as v3
from composite import np, cv2, Image, ImageDraw, ImageFont
from prepare import ROOT
from runtime import FONT
from revision4_layers import boundary_connected

DEST=ROOT/'frames/full-composite-v4'
REVIEW=ROOT/'review/v4-preview'
RANGES=[(0,240),(325,362),(1104,1130),(1244,1281),
        (1401,1543),(1930,2042),(2401,2455),(2472,2785),(3083,3239),
        (3284,3478),(3698,3768)]

def affected(n):
    return any(a<=n<b for a,b in RANGES)

def old_frame(n):
    p=ROOT/f'frames/full-composite-v3/{n:05d}.png'
    return c.read(p) if p.exists() else v3.render(n)[0]

@lru_cache(maxsize=20)
def paper_asset(name):
    im=c.asset(name).copy()
    im[boundary_connected(~c.generated_nonred(im))]=[240,233,212]
    return im

def panel_geometry(src,search):
    """去除金色装饰后定位纸框；凸包补齐装饰遮掉的一小段边。"""
    bg=f.color(src);r,g,b=src.astype(np.int16).transpose(2,0,1)
    gold=(r>220)&(g>160)&(g<235)&(b<195)&(r-g>22)&(g-b>28)
    raw=(c.source_nonbg(src,bg)&~gold&(c.rect(search)>0)).astype(np.uint8)*255
    contours,_=cv2.findContours(raw,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contours=[p for p in contours if cv2.contourArea(p)>1500]
    if not contours:raise ValueError('No paper frame inside declared search region')
    contour=cv2.convexHull(max(contours,key=cv2.contourArea))
    mask=np.zeros((1080,1920),np.uint8);cv2.drawContours(mask,[contour],-1,255,-1)
    ring=mask&~cv2.erode(mask,np.ones((7,7),np.uint8))
    outline=(np.max(src,axis=2)<95)&(ring>0)
    interior=mask.copy();interior[outline]=0
    # 仅回贴从纸框外进入的金色实例，框内原衣服不具有该连接关系。
    count,labels,stats,_=cv2.connectedComponentsWithStats(gold.astype(np.uint8),8)
    outside=(c.dilate(mask,11)==0)&(c.rect(search)>0)
    ids=np.unique(labels[outside]);ids=[int(i) for i in ids if i and stats[i,4]>10]
    foreground=np.isin(labels,ids).astype(np.uint8)*255
    return interior,cv2.boundingRect(contour),foreground

def portrait(src,look,search,name=None,cropbox=None):
    mask,bounds,foreground=panel_geometry(src,search)
    oldname,box=f.PORTRAITS[look];box=cropbox or box;im=paper_asset(name or oldname)
    x0,y0,x1,y1=box;crop=im[y0:y1,x0:x1]
    ch,cw=crop.shape[:2];aspect=bounds[2]/bounds[3]
    if abs(cw/ch-aspect)>.25:
        if cw/ch>aspect:
            nw=int(ch*aspect);left=(cw-nw)//2;crop=crop[:,left:left+nw]
        else:
            nh=int(cw/aspect);top=(ch-nh)//2;crop=crop[top:top+nh]
    x,y,w,h=bounds;out=src.copy();out[y:y+h,x:x+w]=cv2.resize(crop,(w,h),interpolation=cv2.INTER_LANCZOS4)
    out=c.paste(src,out,mask)
    return c.paste(out,src,foreground),{'panel_bounds':list(map(int,bounds))}

def inset(src,name,cropbox,search):
    mask,bounds,foreground=panel_geometry(src,search)
    x0,y0,x1,y1=cropbox;im=c.asset(name)[y0:y1,x0:x1]
    x,y,w,h=bounds;out=src.copy();out[y:y+h,x:x+w]=cv2.resize(im,(w,h),interpolation=cv2.INTER_LANCZOS4)
    out=c.paste(src,out,mask)
    return c.paste(out,src,foreground)

def opening_hand(n):
    """原牌回贴后恢复新手的前景指；牌边不能截断手指。"""
    out=old_frame(n);src=c.reference(n)
    gm=v3.glove(n);gy,_=np.where(gm>0)
    # 入场白色魔法拖尾还没有手，不能仅凭蓝色像素把裸手贴进特效中。
    if len(gy)<350 or gy.max()-gy.min()<80:return out,{'hand_reference':None,'foreground_finger_pixels':0}
    ref=220 if n==218 else v3.choose(n,[24,205,216,220]);rgb,alpha=v3.sprite(ref)
    ys,xs=np.where(v3.glove(ref)>0)
    box=(max(0,int(xs.min())-35),max(0,int(ys.min())-35),min(1920,int(xs.max())+35),min(1080,int(ys.max())+35))
    matrix=c.tracking(c.reference(ref),src,box,n)
    rgb=c.warp(rgb,matrix);alpha=c.warp(alpha,matrix,True)
    r,g,b=rgb.astype(np.int16).transpose(2,0,1)
    skin=(r>185)&(g>140)&(b>120)&(r>g+8)&(alpha>0)
    sr,sg,sb=src.astype(np.int16).transpose(2,0,1)
    card=(sb>120)&(sb>sr*1.2)&(sb>sg*1.15)
    if n==218:
        pm,pc=v3.paper(src);out=src.copy();out[pm>0]=pc
        out=c.paste(out,rgb,alpha&pm)
        out=c.paste(out,src,c.dilate(card.astype(np.uint8)*255,3))
    front=c.dilate(skin.astype(np.uint8)*255,3)&alpha&c.dilate(card.astype(np.uint8)*255,19)
    return c.paste(out,rgb,front),{'hand_reference':ref,'foreground_finger_pixels':int(np.count_nonzero(front))}

def scene(src,n,s,**updates):
    s=dict(s);s.update(updates)
    if s['start'] in v2.TRACKS:s['track']=v2.TRACKS[s['start']]
    return f.apply_scene(src,n,s)[0]

@lru_cache(maxsize=1)
def sofa_hand_glyph():
    # 从原PV的干净字卡取同一个“手”字，避免把与金字同色的旧靴筒带回。
    patch=c.reference(744)[488:592,90:203]
    alpha=np.clip((215-np.max(patch.astype(np.float32),axis=2))/175*255,0,255).astype(np.uint8)
    yy,xx=np.where(alpha>0);alpha=alpha[yy.min():yy.max()+1,xx.min():xx.max()+1]
    return cv2.resize(alpha,(141,141),interpolation=cv2.INTER_CUBIC)

def restore_sofa_lyric(out,src):
    glyph=sofa_hand_glyph();r,g,b=src.astype(np.int16).transpose(2,0,1)
    gold=((r>225)&(g>175)&(g<230)&(b>115)&(b<190)&(r-g>22)&(g-b>28)).astype(np.uint8)*255
    matches=cv2.matchTemplate(gold[830:1080,1100:1380],glyph,cv2.TM_CCOEFF_NORMED)
    _,score,_,at=cv2.minMaxLoc(matches)
    if score<.45:raise ValueError('Missing sofa lyric glyph anchor')
    x,y=at[0]+1100,at[1]+830
    mask=np.zeros((1080,1920),np.uint8);mask[y:y+141,x:x+141]=glyph
    shadow=cv2.GaussianBlur(np.roll(np.roll(mask,4,axis=0),4,axis=1),(7,7),1.5)
    out=c.paste(out,np.full_like(out,(71,25,27)),(shadow*.7).astype(np.uint8))
    return c.paste(out,np.full_like(out,(255,211,151)),mask)

def sofa(src,n):
    awake=n>=3356;ref=None;name='full-3120'
    if awake:
        ref=v2.pose(n,(3356,3365,3376),(900,330,1190,610))
        name={3356:'sofa-front-v4',3365:'sofa-right-v4',3376:'sofa-awake-v4'}[ref]
    im=c.asset(name).copy()
    im[boundary_connected(~c.generated_nonred(im))]=f.color(c.reference(3120))
    # 同一固定镜头的家具底板覆盖原人物及旧鸭子全部范围，不把旧碎线当帘幕恢复。
    region=c.polygon([(770,330),(1170,330),(1180,625),(1330,775),(1330,1065),(975,1065),(975,900),(775,815)])
    out=c.paste(src,im,region)
    # 本固定镜头上半部的金色实例为背景蝴蝶；只在新人物/家具外恢复，
    # 避开下方与其同色的旧靴筒，保持蝴蝶在人物后方。
    background=boundary_connected(~c.generated_nonred(im)).astype(np.uint8)*255
    out=c.paste(out,src,c.butterflies(src)&c.rect((0,190,1920,830))&background)
    out=c.paste(out,src,f.decorations(src,4000)&~c.rect((780,345,1335,1080)))
    out=c.paste(out,src,f.letters_mask(src,[(0,0,1920,190),(1250,400,1920,1080)]))
    if awake:out=restore_sofa_lyric(out,src)
    if n<3092:
        r,g,b=src.astype(np.int16).transpose(2,0,1)
        dark=(r<110)&(r>g*1.5)&(r>b*1.5)
        curtain=boundary_connected(dark).astype(np.uint8)*255
        out=c.paste(out,src,curtain)
    return out,{'sofa_state':'awake' if awake else 'sleep','sofa_pose_reference':ref,'asset':name}

def render(n):
    record={'frame':n,'version':'v4','affected':affected(n)}
    if not affected(n):return old_frame(n),record
    src=c.reference(n);s=next(s for s in f.SHOTS if s['start']<=n<s['end']);extra={}
    if n<86 or 163<=n<240:out,extra=opening_hand(n)
    elif 86<=n<163:out,extra=portrait(src,'casual',(480,210,1440,830))
    elif 325<=n<362:
        out,extra=portrait(src,'mage_happy',(40,0,1025,590))
        if n>=343:
            part,_=portrait(src,'casual',(1020,520,1920,1080));mask,_,_=panel_geometry(src,(1020,520,1920,1080))
            out=c.paste(out,part,mask)
    elif 1104<=n<1130:
        name='casual-1103' if n<1113 else 'smile-closed-mouth-v4' if n<1118 else 'full-1140'
        ref=1140 if n>=1118 else 1103
        out=v2.draw_scene(src,n,name,ref,border=True,track=(820,450,1750,990))[0];extra['expression']=name
    elif 1244<=n<1281:out=scene(src,n,s,keep=[(1410,40,1890,540)])
    elif 1401<=n<1543:out=scene(src,n,s,cup=False)
    elif 1930<=n<2007:
        ref=v2.pose(n,(1930,1936),(900,180,1250,1040));name='full-1944' if ref==1930 else 'standing-alt-v4'
        out=scene(src,n,s,asset=name,ref=ref,roi=(850,90,1380,1080));extra.update(pose_reference=ref,asset=name)
    elif 2007<=n<2042:out,extra=portrait(src,'mage_happy',(460,190,1440,840),'mage-laugh-v4')
    elif 2401<=n<2437:out=scene(src,n,s,asset='spiral-v4')
    elif 2437<=n<2455:
        name='casual-card-closed-v2' if n<2440 else 'wink-v4' if n<2448 else 'full-2448'
        out=scene(src,n,s,asset=name,ref=2437 if n<2440 else 2448,card=False);extra['expression']=name
    elif 2472<=n<2785:
        from revision4_juggle import render as juggle
        out,extra=juggle(src,n)
    elif 3083<=n<3239 or 3356<=n<3397:out,extra=sofa(src,n)
    elif 3284<=n<3305:out=inset(src,'lap-clothing-v4',(580,310,1365,795),(555,285,1390,820))
    elif 3305<=n<3321:out,extra=portrait(src,'casual_sleep',(480,210,1440,825))
    elif 3321<=n<3356:
        name='blink-v4' if 3342<=n<3349 else s['asset']
        out=scene(src,n,s,asset=name,duck=False);extra.update(asset=name,duck_source='single generated cel')
    elif 3397<=n<3478:
        look='casual_open' if n<3417 or n>=3457 else 'casual_drowsy'
        # 竖框源构图裁掉头顶鸭子；不能把参考近景里的鸭子白边裁进头像。
        out,extra=portrait(src,look,f.moving_panel_bounds(src),cropbox=(790,390,1740,1075))
        extra['expression']=look
    elif n>=3698:
        out=inset(src,'ending-clothing-v4',(160,310,940,780),(120,270,985,820))
        out=v3.credits(out,n)
    else:raise AssertionError(('Unhandled v4 interval',n))
    record.update(extra)
    return out,record

def one(n):
    cv2.setNumThreads(1);p=DEST/f'{n:05d}.png'
    if not affected(n):
        prior=ROOT/f'frames/full-composite-v3/{n:05d}.png'
        if prior.exists():
            shutil.copyfile(prior,p);return {'frame':n,'version':'v4','affected':False,'reused_v3':True}
    try:out,r=render(n)
    except Exception as exc:raise RuntimeError(f'v4 frame {n}: {exc}') from exc
    Image.fromarray(out).save(p,compress_level=3);return r

def preview(picks):
    REVIEW.mkdir(parents=True,exist_ok=True);font=ImageFont.truetype(FONT,18)
    for page in range((len(picks)+7)//8):
        sheet=Image.new('RGB',(1280,4*392),'#171b24');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*8:page*8+8]):
            out,r=render(n);Image.fromarray(out).save(REVIEW/f'{n:05d}.png');(REVIEW/f'{n:05d}.json').write_text(json.dumps(r,indent=2))
            x=j%2*640;y=j//2*392;sheet.paste(Image.fromarray(out).resize((640,360)),(x,y+32));d.text((x+4,y+3),f'V4 | {n} | {n/24:.3f}s',font=font,fill='white')
        sheet.save(REVIEW/f'page-{page+1:02d}.jpg',quality=97)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--all',action='store_true');ap.add_argument('--frames',type=int,nargs='+');ap.add_argument('--update',nargs='+');args=ap.parse_args();cv2.setNumThreads(1)
    if args.all or args.update:
        DEST.mkdir(parents=True,exist_ok=True)
        indices=list(range(3768)) if args.all else sorted({n for v in args.update for n in range(*map(int,v.split(':')))})
        records=[None]*3768 if args.all else json.loads((ROOT/'review/v4-frame-verification.json').read_text())
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn')) as pool:
            for i,r in enumerate(pool.map(one,indices,chunksize=8)):
                records[r['frame']]=r
                if i%120==0:print(f'v4 rendered {i}/{len(indices)}',flush=True)
        (ROOT/'review/v4-frame-verification.json').write_text(json.dumps(records,indent=2))
    else:preview(args.frames or [48,205,220,350,1117,1260,1506,1930,1936,2024,2419,2446,3083,3294,3320,3345,3355,3376,3720])

if __name__=='__main__':main()
