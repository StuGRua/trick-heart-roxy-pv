"""按镜头合成洛克希试片，始终以原视频帧为画布。

所有空间规则按镜头配置；调色只用于已隔离的快速手部差分。
"""
from pathlib import Path
from functools import lru_cache
import argparse
import json
from concurrent.futures import ProcessPoolExecutor
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_fill_holes
from prepare import ROOT, WINDOWS, source_frame
from runtime import FONT

W,H=1920,1080
ASSETS=ROOT/'assets'
TRACK_LOG={}

def read(path):
    return np.asarray(Image.open(path).convert('RGB'))

@lru_cache(maxsize=40)
def asset(name):
    return np.asarray(Image.open(ASSETS/(name+'.png')).convert('RGB').resize((W,H),Image.Resampling.LANCZOS))

@lru_cache(maxsize=28)
def reference(n):
    return read(source_frame(n))

def rect(box):
    a=np.zeros((H,W),np.uint8)
    x0,y0,x1,y1=box;a[max(0,y0):min(H,y1),max(0,x0):min(W,x1)]=255
    return a

def polygon(points):
    a=np.zeros((H,W),np.uint8)
    cv2.fillPoly(a,[np.array(points,np.int32)],255)
    return a

def morph(mask,size=3,op=cv2.MORPH_CLOSE):
    return cv2.morphologyEx(mask.astype(np.uint8),op,np.ones((size,size),np.uint8))

def dilate(mask,size=5):
    return cv2.dilate(mask.astype(np.uint8),np.ones((size,size),np.uint8))

def fill_small_holes(mask,limit=15000):
    filled=binary_fill_holes(mask>0)
    holes=(filled&(mask==0)).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(holes,8)
    out=mask.copy()
    for i in range(1,count):
        if stats[i,cv2.CC_STAT_AREA]<limit:out[labels==i]=255
    return out

def bg_color(src):
    return np.median(src[:100,:100].reshape(-1,3),axis=0).astype(np.uint8)

def source_nonbg(src,bg):
    return np.max(np.abs(src.astype(np.int16)-np.asarray(bg,dtype=np.int16)),axis=2)>28

def generated_nonred(src):
    r,g,b=src.astype(np.float32).transpose(2,0,1)
    return ~((r>65)&(r>g*1.55)&(r>b*1.50)&(np.abs(g-b)<38))

def cream(src):
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    return (r>215)&(g>195)&(b>165)&(np.abs(r-g)<22)&(g>b)

def butterflies(src):
    # 本镜头已核验的前景蝴蝶色；不包含橙色袖口或白手套。
    dist=np.max(np.abs(src.astype(np.int16)-np.array([255,211,151])),axis=2)
    return (dist<23).astype(np.uint8)*255

def text_foreground(src,areas):
    region=np.zeros((H,W),np.uint8)
    for a in areas:region|=rect(a)
    # 歌词金色和白色帽饰/皮肤分开，禁止将白帽饰恢复到新帽子上。
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    return (((r>220)&(g>160)&(g<230)&(b>100)&(b<190)&(r-g>22)&(g-b>28))&(region>0)).astype(np.uint8)*255

def paste(base,img,mask):
    alpha=np.clip(mask.astype(np.float32)/255,0,1)[...,None]
    return np.clip(base.astype(np.float32)*(1-alpha)+img.astype(np.float32)*alpha,0,255).astype(np.uint8)

def warp(im,m,mask=False):
    return cv2.warpAffine(im,m,(W,H),flags=cv2.INTER_NEAREST if mask else cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,borderValue=0)

def tracking(ref,src,box,n):
    cv2.setRNGSeed(n)
    if np.array_equal(ref,src):return np.float32([[1,0,0],[0,1,0]])
    scale=.5
    a=cv2.cvtColor(cv2.resize(ref,None,fx=scale,fy=scale),cv2.COLOR_RGB2GRAY)
    b=cv2.cvtColor(cv2.resize(src,None,fx=scale,fy=scale),cv2.COLOR_RGB2GRAY)
    mask=cv2.resize(rect(box),None,fx=scale,fy=scale,interpolation=cv2.INTER_NEAREST)
    p=cv2.goodFeaturesToTrack(a,maxCorners=180,qualityLevel=.02,minDistance=8,mask=mask)
    identity=np.float32([[1,0,0],[0,1,0]])
    if p is None:return identity
    q,ok,_=cv2.calcOpticalFlowPyrLK(a,b,p,None,winSize=(31,31),maxLevel=3)
    good=ok[:,0]>0
    if good.sum()<8:return identity
    m,inliers=cv2.estimateAffinePartial2D(p[good]/scale,q[good]/scale,method=cv2.RANSAC,ransacReprojThreshold=3)
    accepted=m is not None and inliers.sum()>=8 and .85<np.linalg.norm(m[:,0])<1.18 and np.max(np.abs(m[:,2]))<160
    TRACK_LOG[str(n)]={'inliers':int(inliers.sum()) if inliers is not None else 0,'accepted':bool(accepted),'matrix':m.tolist() if accepted else identity.tolist()}
    return m.astype(np.float32) if accepted else identity

def remove_generated_letters(im,areas):
    mask=dilate(text_foreground(im,areas),9)
    return cv2.inpaint(im,mask,11,cv2.INPAINT_TELEA)

def face_fit(ref,src):
    def bounds(im):
        r,g,b=im.astype(np.int16).transpose(2,0,1)
        m=((r>235)&(r-g>18)&(g>160)&(b>160)&(rect((250,70,1780,1020))>0)).astype(np.uint8)
        count,labels,stats,centers=cv2.connectedComponentsWithStats(m,8)
        ids=[i for i in range(1,count) if stats[i,4]>1000]
        idx=max(ids,key=lambda i:stats[i,4])
        return stats[idx,:4],centers[idx]
    a,ac=bounds(ref);b,bc=bounds(src)
    scale=float(np.sqrt((b[2]*b[3])/(a[2]*a[3])))
    return np.float32([[scale,0,bc[0]-ac[0]*scale],[0,scale,bc[1]-ac[1]*scale]])

def frame_inner(src):
    paper=np.median(src[:20,:20].reshape(-1,3),axis=0)
    m=(np.max(np.abs(src.astype(np.int16)-paper),axis=2)>45).astype(np.uint8)*255
    cs,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    cs=[c for c in cs if cv2.contourArea(c)>W*H*.6]
    if len(cs)!=1:raise ValueError('Expected one full-frame bordered panel')
    a=np.zeros((H,W),np.uint8);cv2.drawContours(a,cs,-1,255,-1)
    return cv2.erode(a,np.ones((5,5),np.uint8))

def flat_scene(src,name,refnum,roi,trackbox=None,protect=None,letters=None,n=0,bg_override=None,fit_face=False):
    gen=asset(name).copy();ref=reference(refnum)
    if letters:gen=remove_generated_letters(gen,letters)
    region=rect(roi)
    gm=(generated_nonred(gen)&(region>0)).astype(np.uint8)*255
    gm=fill_small_holes(morph(gm,3))
    if name.startswith(('back-1092','casual-109','casual-110')):
        gm&=cv2.erode(frame_inner(gen),np.ones((13,13),np.uint8))
    matrix=tracking(ref,src,trackbox,n) if trackbox else np.float32([[1,0,0],[0,1,0]])
    if fit_face:
        matrix=face_fit(ref,src)
    gen=warp(gen,matrix);gm=warp(gm,matrix,True)
    bg=bg_color(src) if bg_override is None else np.asarray(bg_override,dtype=np.uint8)
    old=(source_nonbg(src,bg)&(region>0)).astype(np.uint8)*255
    affected=dilate(old|gm,5)
    out=src.copy();out[affected>0]=bg
    out=paste(out,gen,gm)
    if protect is not None:out=paste(out,src,protect)
    if letters:out=paste(out,src,dilate(text_foreground(src,letters),3))
    return out,affected

def band(src,name,side,yr=(300,805)):
    gen=asset(name).copy()
    x0,x1=(0,1380) if side=='left' else (755,1920)
    roi=rect((x0,yr[0],x1,yr[1]))
    bg=bg_color(src)
    inside=source_nonbg(src,bg)&(rect((0,yr[0],W,yr[1]))>0)
    # 沿每列围绕中央定位纸条；排除纸条外飞过的蝴蝶。
    clip=np.zeros((H,W),np.uint8)
    for x in range(W):
        ys=np.flatnonzero(inside[yr[0]:yr[1],x])+yr[0]
        if len(ys)>250:
            clip[ys.min()+3:ys.max()-2,x]=255
    nongeneratedbg=generated_nonred(gen)&~cream(gen)&(roi>0)
    # 将生成画面的纸色规范到原片纸色，只在该半幅框内贴入。
    paper=np.median(src[430:650,1650:1850].reshape(-1,3),axis=0) if side=='left' else np.median(src[400:700,100:300].reshape(-1,3),axis=0)
    candidates=cream(gen).astype(np.uint8)
    count,labels,_,_=cv2.connectedComponentsWithStats(candidates,8)
    sy,sx=(680,1820) if side=='left' else (430,200)
    label=labels[sy,sx]
    if label:gen[labels==label]=paper
    use=roi&clip
    out=paste(src,gen,use)
    out=paste(out,src,butterflies(src))
    return out,use

def rabbit_mask(src,box,red_limit=None):
    zone=rect(box)>0
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    white=(r>246)&(g>246)&(b>246)
    red=(r>160)&(g<125)&(b>45)&(r>1.6*g)
    if red_limit is None:
        red[:]=False
    else:
        count,labels,stats,centers=cv2.connectedComponentsWithStats(red.astype(np.uint8),8)
        x0,y0,x1,y1=red_limit
        ids=[i for i in range(1,count) if stats[i,cv2.CC_STAT_AREA]>100 and x0<=centers[i,0]<x1 and y0<=centers[i,1]<y1]
        red=np.isin(labels,ids)
    m=((white|red)&zone).astype(np.uint8)*255
    m=dilate(m,3)
    return m

def crown(src):
    # 从接触底边的人物头顶实例取遮罩，兔子红斑是另一连通实例。
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    red=((r>175)&(g<85)&(b>45)&(b<120)&(rect((620,650,W,H))>0)).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(red,8)
    ids=np.unique(labels[-2,:]);ids=ids[ids>0]
    mask=np.isin(labels,ids).astype(np.uint8)*255
    if not mask.any():return src.copy(),mask
    ys,xs=np.where(mask>0)
    gen=asset('crown-0984')
    # 源轮廓限定可见头顶，生成稿提供蓝发色与发丝。
    blue=(gen[:,:,2].astype(int)>gen[:,:,0].astype(int)+18)&(rect((700,730,W,H))>0)
    gy,gx=np.where(blue)
    crop=gen[gy.min():gy.max()+1,gx.min():gx.max()+1]
    target=cv2.resize(crop,(xs.max()-xs.min()+1,ys.max()-ys.min()+1))
    replacement=src.copy();replacement[ys.min():ys.max()+1,xs.min():xs.max()+1]=target
    mask=dilate(mask,2)
    out=paste(src,replacement,mask)
    return out,mask

def rapid_hand(src,n):
    # 手型沿用源差分线稿，替换为生成稿确立的肤色和法师黑袖口。
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    zone=rect((0,220,1600,H))>0
    cuff=(r>220)&(g>120)&(g<195)&(b<80)&zone
    gray=(np.abs(r-g)<8)&(np.abs(g-b)<8)&(r>216)&(r<247)
    glove=gray&zone
    if 1065<=n<1071:
        count,labels,stats,_=cv2.connectedComponentsWithStats(gray.astype(np.uint8),8)
        smoke_ids=[i for i in range(1,count) if stats[i,cv2.CC_STAT_AREA]>250000 and stats[i,1]<100]
        glove&=~np.isin(labels,smoke_ids)
    # 卡牌与烟雾为纯白，不在浅灰手套材质范围；轮廓线保持。
    out=src.copy();out[cuff]=[37,36,33];out[glove]=[255,226,208]
    return out,((cuff|glove).astype(np.uint8)*255)

def portraits(src,n):
    closed=1718<=n<1732
    gen=asset('profile-1728' if closed else 'profiles-1752').copy()
    bg=bg_color(src);out=src.copy();affected=np.zeros((H,W),np.uint8)
    regions=[(160,45,775,935)]
    if n>=1749:regions.append((1140,45,1770,935))
    for box in regions:
        zone=rect(box)
        nonbg=(source_nonbg(src,bg)&(zone>0)).astype(np.uint8)*255
        cs,_=cv2.findContours(nonbg,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cs=[c for c in cs if cv2.contourArea(c)>100000]
        if len(cs)!=1:raise ValueError(f'Expected one annotated portrait panel: {n}, {box}, {len(cs)}')
        panel=np.zeros((H,W),np.uint8);cv2.drawContours(panel,cs,-1,255,-1)
        inner=cv2.erode(panel,np.ones((7,7),np.uint8))
        x,y,w,h=cv2.boundingRect(cs[0])
        left=box[0]<500
        gr=(214,76,714,891) if left else (1200,80,1710,900)
        crop=gen[gr[1]:gr[3],gr[0]:gr[2]]
        patch=cv2.resize(crop,(w,h),interpolation=cv2.INTER_LANCZOS4)
        copy=out.copy();copy[y:y+h,x:x+w]=patch
        out=paste(out,copy,inner);affected|=inner
    return out,affected

def standing(src,n):
    # 两个人物各有独立 ROI；狗和牵引绳由源帧置于前景。
    gen=asset('pair-1680-v2');out=src.copy();affected=np.zeros((H,W),np.uint8)
    for box in [(70,100,620,1020),(1320,160,1885,1020)]:
        patch,mask=flat_scene(src,'pair-1680-v2',1680,box,n=n)
        out=paste(out,patch,mask);affected|=mask
    # 牵引把手和线的空间范围不与服装混用。
    for box in [(480,435,570,560),(1395,430,1510,600)]:
        zone=rect(box)>0;r,g,b=src.transpose(2,0,1)
        keep=((r>235)&(g>145)&(b<90)&zone).astype(np.uint8)*255
        out=paste(out,src,dilate(keep,2))
    dog=polygon([(650,630),(750,610),(900,700),(1050,685),(1070,480),(1210,470),(1245,720),(1270,840),(1260,1010),(640,1030)])
    out=paste(out,src,dog)
    return out,affected

def sofa(src,n,trackbox=(490,550,1630,1050)):
    gen=asset('sofa-2880').copy()
    # 先用沙发固定特征估计原镜头的微小抖动。
    m=tracking(reference(2880),src,trackbox,n)
    gen=warp(gen,m)
    # 人物、必要补底区域；原字幕/柜子/绝大部分沙发与狗保持原帧。
    zone=polygon([(750,280),(1110,280),(1220,570),(1300,765),(1310,1078),(585,1078),(610,835),(655,725),(730,560)])
    zone=warp(zone,m,True)
    out=paste(src,gen,zone)
    # 背景归一为源色，去掉生成稿酒红渐变。
    bg=bg_color(src)
    red=(~generated_nonred(gen))&(zone>0)
    out[red]=bg
    # 狗和鸭子使用原片动态层，避免它们的形状被重绘改变。
    dog=polygon([(0,850),(450,820),(585,822),(640,845),(665,890),(655,962),(705,1003),(720,1047),(400,1075),(0,1080)])
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    animal=((r-g>7)&(g-b>7)&(r>170)&(g>160))|((r<80)&(g<80)&(b<80))
    dog=dog*animal.astype(np.uint8)
    out=paste(out,src,dog)
    keep=rabbit_mask(src,(1010,660,1175,755),(1010,660,1110,713))
    out=paste(out,src,keep)
    return out,zone

def render(n):
    src=read(source_frame(n))
    if 624<=n<704:
        name,ref=('mage-0624',624) if n<632 else (('mage-0632',632) if n<639 else ('mage-0648',648))
        out,mask=flat_scene(src,name,ref,(790,0,W,H),(1320,210,1900,540),butterflies(src),n=n)
    elif n<744:out,mask=band(src,'face-0720','left')
    elif n<787:out,mask=band(src,'face-0768','right')
    elif n<792:out,mask=flat_scene(src,'back-0787',787,(550,190,1210,H),n=n)
    elif 912<=n<930:
        keep=rabbit_mask(src,(1300,240,1790,780),(1380,280,1720,620))
        out,mask=flat_scene(src,'mage-0912',912,(0,0,W,H),(260,200,1030,820),keep,[(0,0,1200,180),(1150,870,W,H)],n)
    elif 930<=n<982:
        if n<939:name,ref,box,redbox='casual-0930-v2',930,(925,705,1390,H),(930,835,1145,950)
        elif n<948:name,ref,box,redbox='casual-0939',939,(1080,690,1370,940),None
        elif n<958:name,ref,box,redbox='casual-0948',948,(1390,240,1850,590),(1560,342,1760,555)
        else:name,ref,box,redbox='casual-0960',960,(1010,0,1600,430),(1220,0,1530,320)
        keep=rabbit_mask(src,box,redbox)
        out,mask=flat_scene(src,name,ref,(820,230,W,H),(1090,330,1670,820),keep,n=n)
    elif 982<=n<1036:
        out,mask=crown(src)
        if n>=1018:
            other,handmask=rapid_hand(src,n);out=paste(out,other,handmask);mask|=handmask
    elif 1036<=n<1059:
        out,mask=flat_scene(src,'hand-1036',1036,(300,170,1490,H),(810,230,1420,755),n=n)
    elif 1059<=n<1091:out,mask=rapid_hand(src,n)
    elif 1091<=n<1095:
        keep=((np.min(src,axis=2)>250)&(rect((0,500,W,H))>0)).astype(np.uint8)*255 if n==1091 else None
        out,mask=flat_scene(src,'back-1092',1092,(650,75,1230,1045),protect=keep,n=n,bg_override=src[250,1700])
        if n>=1092:
            inner=frame_inner(src);out=paste(src,out,inner);mask&=inner
    elif 1095<=n<1104:
        name,ref=('casual-1095',1095) if n<1099 else (('casual-1099',1099) if n<1103 else ('casual-1103',1103))
        out,mask=flat_scene(src,name,ref,(70,50,1870,1045),n=n,bg_override=src[250,150])
        inner=frame_inner(src);out=paste(src,out,inner);mask&=inner
    elif 1680<=n<1708:out,mask=standing(src,n)
    elif 1708<=n<1776:out,mask=portraits(src,n)
    elif 2832<=n<2939:out,mask=sofa(src,n)
    elif 2939<=n<2952:out,mask=band(src,'closing-2939' if n<2951 else 'closing-2951','right',(125,895))
    else:raise ValueError(f'Uncovered source frame {n}')
    # 写入范围同时包含保护层恢复；范围以外必须逐像素不变。
    changed=np.any(out!=src,axis=2)
    if np.any(changed&(dilate(mask,9)==0)):
        raise AssertionError(f'Changed outside declared region at {n}')
    return out,mask

def preview():
    picks=[624,632,648,695,704,720,744,780,787,912,924,930,939,948,960,984,1018,1036,1058,1064,1075,1085,1092,1095,1099,1103,1680,1708,1728,1752,2832,2880,2938,2951]
    font=ImageFont.truetype(FONT,18)
    outdir=ROOT/'review/composite';outdir.mkdir(exist_ok=True)
    for page in range((len(picks)+11)//12):
        sheet=Image.new('RGB',(4*480,3*300),'#1b1d22');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*12:(page+1)*12]):
            out,mask=render(n);Image.fromarray(out).save(outdir/f'{n:05d}.png')
            x=j%4*480;y=j//4*300
            sheet.paste(Image.fromarray(out).resize((480,270)),(x,y+30))
            d.text((x+5,y+5),f'{n} / {n/24:.3f}s',fill='white',font=font)
        sheet.save(ROOT/f'review/composite-preview-{page+1:02d}.jpg',quality=94)
    (ROOT/'review/track-log.json').write_text(json.dumps(TRACK_LOG,indent=2))

def render_one(pair):
    cv2.setNumThreads(1)
    i,n=pair;out,mask=render(n)
    Image.fromarray(out).save(ROOT/f'frames/composite/{i:05d}.png',compress_level=3)
    return {'sample_frame':i,'source_frame':n,'changed_pixels':int(np.any(out!=reference(n),axis=2).sum()),'roi_pixels':int((mask>0).sum()),'track':TRACK_LOG.get(str(n))}

def all_frames():
    dest=ROOT/'frames/composite';dest.mkdir(exist_ok=True)
    records=[]
    frames=list(enumerate(n for a,b in WINDOWS for n in range(a,b)))
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,item in enumerate(pool.map(render_one,frames,chunksize=12)):
            records.append(item)
            if i%48==0:print(f'rendered {i}/576',flush=True)
    (ROOT/'review/frame-verification.json').write_text(json.dumps(records,indent=2))
    (ROOT/'review/track-log.json').write_text(json.dumps(TRACK_LOG,indent=2))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--all',action='store_true');args=ap.parse_args()
    all_frames() if args.all else preview()
