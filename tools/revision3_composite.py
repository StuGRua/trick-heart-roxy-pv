"""v3：真正裸手原画和两处符合原PV风格的英文视觉二创署名。"""
import argparse,json,multiprocessing,shutil,os
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import revision_composite as v2
import full_composite as f
import composite as c
from composite import np,cv2,Image,ImageDraw,ImageFont
from prepare import ROOT

DEST=ROOT/'frames/full-composite-v3'
CROPS=json.loads((ROOT/'assets/v3-reference/crops.json').read_text())
MIRRORED_REFS={591:546,594:549,597:552}
for mirrored,original in MIRRORED_REFS.items():
    x0,y0,x1,y1=CROPS[str(original)];CROPS[str(mirrored)]=[1920-x1,y0,1920-x0,y1]
HAND_RANGES=[(0,86,[24]),(163,240,[24,205,216,220]),(393,444,[393]),(546,621,[546,549,552,555,576,591,594,597,600,603,612]),(1018,1036,[1018]),(1059,1063,[1059]),(1063,1065,[1064]),(1065,1073,[1071]),(1073,1082,[1075]),(1082,1091,[1084]),(1850,1851,[1850]),(1854,1857,[1856]),(1857,1864,[1858]),(1871,1875,[1872]),(1875,1878,[1875]),(3003,3038,[3003,3012,3024])]
CREDIT_INTERVALS=[(2702,2785),(3698,3768)]
CREDIT_LINES=['MUSHOKU TENSEI: ROXY','VISUAL FAN EDIT','StuG_III + GPT6Astra']
FONT=os.environ.get('ROXY_CREDIT_FONT') or next((str(p) for p in [Path('/mnt/c/Windows/Fonts/times.ttf'),Path('C:/Windows/Fonts/times.ttf')] if p.is_file()),v2.FONT)

@lru_cache(maxsize=24)
def base(n):
    p=ROOT/f'frames/full-composite-v2/{n:05d}.png'
    return c.read(p) if p.exists() else v2.render(n)[0]

@lru_cache(maxsize=120)
def glove(n):
    src=c.reference(n).astype(np.int16);r,g,b=src.transpose(2,0,1)
    gray=(r>210)&(r<250)&(np.abs(r-g)<9)&(np.abs(g-b)<9)
    peach=np.max(np.abs(base(n).astype(np.int16)-[255,226,208]),axis=2)<20
    # 球面小白点曾被旧改色规则染成肤色，不允许它们触发整只手的生成。
    return f.component((gray&peach).astype(np.uint8)*255,200)

@lru_cache(maxsize=120)
def signature(n):return cv2.resize(glove(n),(240,135),interpolation=cv2.INTER_AREA).astype(np.int16)

def choose(n,refs):
    # 原片每三帧换一次指势；明确记录动作差分边界，不能让形状相似度跳过中间画。
    if 163<=n<240:return 24 if n<205 else 205 if n<212 else 216 if n<219 else 220
    if 546<=n<621:
        return next(ref for end,ref in [(549,546),(552,549),(555,552),(558,555),(591,576),(594,591),(597,594),(600,597),(603,600),(606,603),(621,612)] if n<end)
    return min(refs,key=lambda ref:float(np.abs(signature(n)-signature(ref)).mean()))

@lru_cache(maxsize=40)
def sprite(ref):
    if ref in MIRRORED_REFS:
        original=MIRRORED_REFS[ref];rgb,alpha=sprite(original)
        # 原片左右手是镜像构图；仅镜像、整体注册已绘制原画，不进行手指局部形变。
        matrix=c.tracking(np.fliplr(c.reference(original)).copy(),c.reference(ref),tuple(CROPS[str(ref)]),ref)
        return cv2.warpAffine(np.fliplr(rgb).copy(),matrix,(1920,1080),borderMode=cv2.BORDER_REPLICATE),cv2.warpAffine(np.fliplr(alpha).copy(),matrix,(1920,1080),borderMode=cv2.BORDER_REPLICATE)
    x0,y0,x1,y1=CROPS[str(ref)];prefix='pair-bare' if ref in (3003,3012) else 'bare'
    im=Image.open(ROOT/f'assets/{prefix}-{ref}-v3.png').convert('RGBA').resize((x1-x0,y1-y0),Image.Resampling.LANCZOS)
    a=np.asarray(im).copy()
    if ref in (1018,1075):
        r,g,b=a[:,:,:3].astype(int).transpose(2,0,1)
        prop=(np.minimum(np.minimum(r,g),b)>230)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<16) if ref==1018 else ((r>225)&(g>65)&(g<180)&(b<110))
        # 模型仍画出的道具从原画alpha剔除，稍后只用源片道具轨迹。
        a[:,:,3][cv2.dilate(prop.astype(np.uint8),np.ones((7,7),np.uint8))>0]=0
    rgb=np.zeros((1080,1920,3),np.uint8);alpha=np.zeros((1080,1920),np.uint8)
    rgb[y0:y1,x0:x1]=a[:,:,:3];alpha[y0:y1,x0:x1]=a[:,:,3]
    return rgb,alpha

def paper(src):
    r,g,b=src.astype(int).transpose(2,0,1)
    cream=(r>210)&(g>205)&(b>180)&(r-b>10)&(np.abs(r-g)<18)
    cc,lab,st,_=cv2.connectedComponentsWithStats(cream.astype(np.uint8),8)
    ids=[j for j in range(1,cc) if st[j,4]>20000]
    mask=np.zeros((1080,1920),np.uint8)
    if not ids:return mask,None
    j=max(ids,key=lambda j:st[j,4]);raw=np.isin(lab,ids).astype(np.uint8)
    contours,_=cv2.findContours(raw,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cv2.fillConvexPoly(mask,cv2.convexHull(np.concatenate(contours)),255)
    color=np.median(src[raw>0],axis=0).astype(np.uint8)
    return mask,color

def bare_hand(n,refs):
    src=c.reference(n);old=base(n);gm=glove(n)
    if np.count_nonzero(gm)<350:return old.copy(),None
    current_y,current_x=np.where(gm>0)
    if current_y.max()-current_y.min()<80:return old.copy(),None
    ref=choose(n,refs);rgb,alpha=sprite(ref);box=tuple(CROPS[str(ref)])
    # 仿射只跟踪原手，不拉伸脸或手指；不同指势用独立原画。
    refmask=glove(ref);ys,xs=np.where(refmask>0)
    track=(max(0,int(xs.min())-35),max(0,int(ys.min())-35),min(1920,int(xs.max())+35),min(1080,int(ys.max())+35))
    matrix=c.tracking(c.reference(ref),src,track,n)
    if 1871<=n<1875:
        # 手快速离开下边界，平移量超过通用跟踪保护阈值；以可见指尖定位。
        matrix=np.float32([[1,0,float(current_x.min()-xs.min())],[0,1,float(current_y.min()-ys.min())]])
    if 546<=n<621:
        # 镜像注册的整体上移会露出画布底边；延续被底边裁断的袖子，避免凭空悬浮。
        rgb=cv2.warpAffine(rgb,matrix,(1920,1080),borderMode=cv2.BORDER_REPLICATE)
        alpha=cv2.warpAffine(alpha,matrix,(1920,1080),borderMode=cv2.BORDER_REPLICATE)
    else:rgb=c.warp(rgb,matrix);alpha=c.warp(alpha,matrix,True)
    r,g,b=src.astype(np.int16).transpose(2,0,1);br,bg,bb=old.astype(np.int16).transpose(2,0,1)
    region=c.dilate(c.warp(c.rect(box),matrix,True),12)>0
    cuff=(r>225)&(g>100)&(g<215)&(b<125)
    coat=(br>125)&(br<210)&(bg>95)&(bg<185)&(bb<140)
    wrist=(r>245)&(g>185)&(g<240)&(b>175)&(b<245)&(c.dilate(gm,71)>0)
    if n>=3003:wrist&=c.rect((0,0,850,1080))>0
    material=(((gm>0)|cuff|coat|wrist)&region).astype(np.uint8)*255
    cc,lab,st,_=cv2.connectedComponentsWithStats(c.dilate(material,7),8)
    ids=np.unique(lab[gm>0]);ids=ids[ids>0]
    # 只选与原手连通的材质实例，排除同色歌词及其阴影。
    material&=np.isin(lab,ids).astype(np.uint8)*255
    # 旧色块的外轮廓和缝线也必须清走，不能留下悬浮黑线。
    dark=(np.max(old,axis=2)<110)&(c.dilate(material,25)>0)
    erase=c.dilate(c.morph(((material>0)|dark).astype(np.uint8)*255),9)&region.astype(np.uint8)*255
    erase=c.fill_small_holes(erase,5000)
    out=old.copy();out[erase>0]=f.color(src)
    if 546<=n<621:
        # 此镜头手臂与歌词分列两侧；完整清除旧袖口，避免姿势切换留下断开的衣袖碎片。
        isolated=(200,280,1150,1080) if n<591 else (950,150,1870,1080)
        out[c.rect(isolated)>0]=f.color(src)
    pm,pc=paper(src)
    if n>=3003:
        pm,_=f.panel_mask(src,(500,240,1440,880))
    if pc is not None:
        out[(erase>0)&(pm>0)]=pc
        if n<240:
            out[pm>0]=pc
            bottom=np.where(pm>0)[0].max();alpha[bottom+1:]=0
        elif n>=3003:alpha&=pm
    if ref in (3003,3012):
        # 接触双手联合重绘，避免按旧可见皮肤恢复时将旧手指边线叠回。
        out=old.copy();out[pm>0]=pc
        out=c.paste(out,rgb,alpha)
        return c.paste(old,out,pm),{'reference':ref,'joint_hands_redraw':True,'bare_hand_redraw':True}
    out=c.paste(out,rgb,alpha)
    if n>=3003:out=c.paste(old,out,pm)
    # 前景来自原片实例。未改变的灰白像素是烟/兔/牌，不是已改肤色的手套。
    unchanged=np.max(np.abs(src.astype(int)-old.astype(int)),axis=2)<5
    neutral=(np.minimum(np.minimum(r,g),b)>220)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<12)
    keep=(neutral&unchanged&region).astype(np.uint8)*255 if 1018<=n<1091 else np.zeros((1080,1920),np.uint8)
    if n<240:
        blue=(b>120)&(b>r*1.2)&(b>g*1.15)
        keep|=c.dilate(blue.astype(np.uint8)*255,3)
        keep|=(unchanged&neutral&(c.dilate(blue.astype(np.uint8)*255,17)>0)).astype(np.uint8)*255
    if 594<=n<621 or 1850<=n<1930:
        yellow=((r>230)&(g>125)&(g<220)&(b<100)).astype(np.uint8)
        cc,lab,st,_=cv2.connectedComponentsWithStats(yellow,8)
        ids=[j for j in range(1,cc) if 10<st[j,4]<6000]
        if n>=1850:
            gy=np.where(gm>0)[0].mean()
            ids=[j for j in range(1,cc) if st[j,4]>10 and st[j,1]+st[j,3]/2<gy]
        keep|=c.dilate(np.isin(lab,ids).astype(np.uint8)*255,2)
    if 1073<=n<1091:
        carrot=((r>225)&(g>75)&(g<155)&(b<80)).astype(np.uint8)*255;keep|=c.dilate(carrot,2)
    if 1082<=n<1091:
        keep|=c.rabbit_mask(src,(600,0,1920,880),(900,0,1920,650))
    out=c.paste(out,src,keep)
    if n>=3003:
        other=((r>245)&(g>185)&(g<240)&(b>190)&(b<250))|((r>130)&(r<200)&(b>r)&(np.abs(r-g)<18))
        other&=c.rect((850,300,1370,810))>0
        out=c.paste(out,old,c.dilate(other.astype(np.uint8)*255,5))
    return out,{'reference':ref,'tracking':c.TRACK_LOG.get(str(n)),'bare_hand_redraw':True}

@lru_cache(maxsize=4)
def lettering(phase,ending):
    im=Image.new('RGBA',(1920,1080));d=ImageDraw.Draw(im)
    x,y=(1120,674) if ending else (198,631)
    # 原片使用细衬线金字；第二张排字差分仅在源文字切换时改变字形基线。
    for row,(text,size) in enumerate(zip(CREDIT_LINES,(44,37,48))):
        font=ImageFont.truetype(FONT,size);cx=x
        for k,char in enumerate(text):
            dy=([-1,0,1,0][k%4] if phase else 0)
            if ending:d.text((round(cx)+2,y+row*59+dy+2),char,font=font,fill=(86,34,32,160))
            d.text((round(cx),y+row*59+dy),char,font=font,fill=(255,211,151,255),stroke_width=0)
            cx+=d.textlength(char,font=font)+2.0
    return np.asarray(im)

def credits(out,n):
    ending=n>=3698;start=3698 if ending else 2702
    if not (ending or 2702<=n<2785):return out
    box=(1120,310,1900,650) if ending else (150,380,1050,610)
    refs=(3700,3706) if ending else (2704,2710)
    phase=int(v2.pose(n,refs,box)==refs[1]);rgba=lettering(phase,ending)
    matrix=c.tracking(c.reference(start),c.reference(n),box,n)
    rgb=c.warp(rgba[:,:,:3],matrix);alpha=c.warp(rgba[:,:,3],matrix,True)
    out=c.paste(out,rgb,alpha)
    if ending:out=c.paste(out,c.reference(n),f.decorations(c.reference(n)))
    if not ending and n>=2769:
        src=c.reference(n);r,g,b=src.astype(int).transpose(2,0,1);dark=((r<110)&(g<70)&(b<70)).astype(np.uint8)
        cc,lab,st,_=cv2.connectedComponentsWithStats(dark,8);ids=[j for j in range(1,cc) if st[j,3]>900 and st[j,1]<100]
        out=c.paste(out,src,np.isin(lab,ids).astype(np.uint8)*255)
    return out

def render(n):
    record={'frame':n,'version':'v3'}
    if 2472<=n<2785:out=f.render(n)[0];record['credit_replaced']=True
    else:out=base(n).copy()
    for a,b,refs in HAND_RANGES:
        if a<=n<b:out,hand=bare_hand(n,refs);record['hand']=hand;break
    if any(a<=n<b for a,b in CREDIT_INTERVALS):out=credits(out,n);record['english_credit']=True
    return out,record

def one(n):
    cv2.setNumThreads(1)
    affected=any(a<=n<b for a,b,_ in HAND_RANGES) or 2472<=n<2785 or n>=3698
    prior=ROOT/f'frames/full-composite-v2/{n:05d}.png'
    if not affected and prior.exists():
        shutil.copyfile(prior,DEST/f'{n:05d}.png');return {'frame':n,'version':'v3','reused_v2':True}
    out,record=render(n);Image.fromarray(out).save(DEST/f'{n:05d}.png',compress_level=3);return record

def preview(picks):
    folder=ROOT/'review/v3-preview';folder.mkdir(exist_ok=True)
    font=ImageFont.truetype(v2.FONT,18)
    for page in range((len(picks)+11)//12):
        sheet=Image.new('RGB',(1920,3*300),'#16191f');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*12:page*12+12]):
            out,_=render(n);Image.fromarray(out).save(folder/f'{n:05d}.png');x=j%4*480;y=j//4*300
            sheet.paste(Image.fromarray(out).resize((480,270)),(x,y+30));d.text((x+4,y+4),f'{n} | {n/24:.3f}s',font=font,fill='white')
        sheet.save(folder/f'page-{page+1:02d}.jpg',quality=96)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--all',action='store_true');ap.add_argument('--frames',type=int,nargs='*');ap.add_argument('--update',nargs='+',help='更新半开区间，如 546:621');args=ap.parse_args();cv2.setNumThreads(1)
    if args.all or args.update:
        DEST.mkdir(exist_ok=True)
        indices=range(3768) if args.all else sorted({n for value in args.update for n in range(*map(int,value.split(':')))})
        records=[None]*3768 if args.all else json.loads((ROOT/'review/v3-frame-verification.json').read_text())
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn')) as pool:
            for i,r in enumerate(pool.map(one,indices,chunksize=8)):
                records[r['frame']]=r
                if i%120==0:print(f'v3 rendered {i}/{len(indices)}',flush=True)
        (ROOT/'review/v3-frame-verification.json').write_text(json.dumps(records,indent=2))
    else:preview(args.frames or [24,216,393,546,576,600,612,1059,1071,1858,2712,3720])

if __name__=='__main__':main()
