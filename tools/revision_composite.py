"""v2: 源动作驱动的差分、人物跟踪、裸手与二创署名。

v1 的图像/视频缓存不改写。姿势以源帧外观匹配决定，禁止跨切镜插值。
"""
import argparse,json,os,hashlib,multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import full_composite as f
import composite as c
from composite import np,cv2,Image,ImageDraw,ImageFont
from prepare import ROOT,WINDOWS
from runtime import FONT

DEST=ROOT/'frames/full-composite-v2'
TRACKS={
 444:(250,100,1600,1000),449:(700,90,1500,750),454:(550,100,1450,1000),
 464:(320,150,840,700),534:(650,150,1250,820),
 1130:(650,250,1660,950),1154:(700,180,1540,880),1174:(600,190,1350,870),
 1224:(650,150,1300,810),1244:(500,180,1250,810),
 1543:(1100,240,1550,730),1585:(370,150,1120,800),
 1930:(930,200,1210,520),2081:(1180,270,1660,850),
 2197:(1250,200,1830,830),2224:(1250,200,1830,830),
 2314:(200,100,1170,970),2367:(680,90,1320,800),2401:(600,180,1250,800),
 2437:(600,180,1250,800),3321:(900,350,1450,850),3328:(900,350,1450,850),3335:(900,350,1450,850),
 3509:(710,220,1280,840),3630:(820,200,1160,940),3666:(460,100,1100,710),
}

@lru_cache(maxsize=180)
def pose_signature(n,box):
    x0,y0,x1,y1=box
    return cv2.resize(c.reference(n)[y0:y1,x0:x1],(96,96),interpolation=cv2.INTER_AREA).astype(np.int16)

def pose(n,refs,box):
    """只在同一镜头候选中比较；源手绘持帧节奏自然保留。"""
    a=pose_signature(n,box)
    return min(refs,key=lambda r:float(np.abs(a-pose_signature(r,box)).mean()))

def draw_scene(src,n,asset,ref,roi=f.FULL,**kw):
    return f.apply_scene(src,n,dict(asset=asset,ref=ref,roi=roi,**kw))

def independent_people(src,n,name,ref,boxes,trackboxes):
    out=src.copy();area=np.zeros((1080,1920),np.uint8)
    for box,tb in zip(boxes,trackboxes):
        one,mask=draw_scene(src,n,name,ref,box,track=tb)
        out=c.paste(out,one,mask);area|=mask
    return out,area

def restore_cup_grip(out,src,n,ref):
    # 只替换杯沿外由原图恢复操作带回的无色手套像素；不按全片白色判断。
    boxes={1512:(550,380,1010,800),1608:(1100,530,1630,1000)}
    if ref not in boxes:return out
    r,g,b=out.astype(np.int16).transpose(2,0,1)
    zone=c.rect(boxes[ref])>0
    gray=(r>215)&(np.abs(r-g)<6)&(np.abs(g-b)<6)&zone
    # 细线、杯弦、衬衣不在孤立指尖的连通组件面积范围。
    count,lab,st,_=cv2.connectedComponentsWithStats(gray.astype(np.uint8),8)
    ids=[j for j in range(1,count) if 8<st[j,4]<1500 and st[j,2]>3 and st[j,3]>3]
    out=out.copy();out[np.isin(lab,ids)]=[255,226,208]
    return out

@lru_cache(maxsize=2)
def credit_layer(right):
    im=Image.new('RGBA',(1920,1080));d=ImageDraw.Draw(im)
    x=1080 if right else 180;y=824;gold=(255,215,157,255)
    d.rounded_rectangle((x,y+3,x+40,y+57),radius=4,outline=gold,width=2)
    d.rounded_rectangle((x+14,y-3,x+54,y+51),radius=4,fill=(137,54,51,255),outline=gold,width=2)
    d.ellipse((x+23,y+13,x+35,y+25),fill=gold);d.ellipse((x+33,y+13,x+45,y+25),fill=gold)
    d.polygon([(x+23,y+20),(x+45,y+20),(x+34,y+35)],fill=gold)
    font=ImageFont.truetype(FONT,34)
    small=ImageFont.truetype(FONT,19)
    d.text((x+78,y-4),'VISUAL ADAPTATION',font=small,fill=gold)
    d.text((x+78,y+23),'StuG_III + GPT6Astra',font=font,fill=(255,239,212,255))
    return np.asarray(im)

def credits(out,n):
    if not 2472<=n<2757:return out
    r,g,b=out.astype(int).transpose(2,0,1)
    ys,xs=np.where((b>r*1.18)&(b>g*1.03)&(b>85)&(b<235))
    right=bool(len(xs) and xs.mean()<960)
    layer=credit_layer(right);alpha=layer[:,:,3].copy()
    # 署名在原作职员表留白中入场，闭幕前退出。
    opacity=min(1,(n-2471)/8,(2757-n)/8)
    alpha=(alpha*opacity).astype(np.uint8)
    return c.paste(out,layer[:,:,:3],alpha)

def render(n):
    src=c.reference(n);s=next(s for s in f.SHOTS if s['start']<=n<s['end']);mode=s['mode'];changed=True
    if n==3283:
        # 鸭子小框最后一帧仍是头顶，下一帧才切到兔子膝部。
        out,area,_=f.render(n);r,g,b=src.astype(int).transpose(2,0,1)
        hair=(r>175)&(g<90)&(b>45)&(b<130)&(c.rect((580,700,1365,790))>0)
        out[hair]=[100,117,188];area|=hair.astype(np.uint8)*255
    elif 240<=n<325:
        out,area=independent_people(src,n,'full-264',264,[(240,70,950,1080),(960,490,1620,1080)],[(350,180,830,1000),(1050,550,1450,1040)])
    elif 787<=n<849:
        ref=pose(n,(787,798,804,810),(650,300,1150,850))
        name={787:'back-0787',798:'back-calm-v2',804:'back-0787',810:'back-gust-v2'}[ref]
        out,area=draw_scene(src,n,name,ref,(300,170,1230,1080),track=(740,650,1100,1050))
    elif 1104<=n<1130:
        closed=pose(n,(1104,1119),(800,450,1720,1000))==1119
        ref=1140 if closed else 1103;name='full-1140' if closed else 'casual-1103'
        out,area=draw_scene(src,n,name,ref,border=True,track=(820,450,1750,990))
    elif 1631<=n<1708:
        out,area=independent_people(src,n,'pair-1680-v2',1680,[(70,100,620,1020),(1320,160,1885,1020)],[(210,210,440,620),(1450,245,1780,630)])
        for box in [(480,435,570,560),(1395,430,1510,600)]:
            r,g,b=src.astype(int).transpose(2,0,1);keep=((r>235)&(g>145)&(b<90)&(c.rect(box)>0)).astype(np.uint8)*255
            out=c.paste(out,src,c.dilate(keep,2))
    elif 2139<=n<2169:
        ref=pose(n,(2139,2166),(1550,250,1920,850))
        name='mage-profile-closed-v2' if ref==2166 else 'full-2145'
        out,area=draw_scene(src,n,name,ref,(1370,0,1920,1080),particles='gold',track=(1570,300,1910,840))
    elif 2785<=n<2939:
        out,area=c.sofa(src,n,trackbox=(775,340,1120,650))
    elif 3584<=n<3630:
        out,area,_=f.render(n)
        m=c.tracking(c.reference(3588),src,(680,425,1140,770),n)
        out=c.paste(out,c.warp(out,m),area)
    elif mode=='scene':
        s=dict(s)
        if s['start'] in TRACKS:s['track']=TRACKS[s['start']]
        if s['ref']==464:s['asset']='full-464-bare-v2'
        elif s['ref']==540:
            if pose(n,(534,540),(410,200,1510,1050))==534:s.update(asset='mage-fists-up-v2',ref=534)
        elif s['ref']==1224:
            if pose(n,(1224,1233),(520,330,1330,1070))==1233:s.update(asset='mage-hand-chest-v2-framed',ref=1233)
        elif s['ref']==1548:
            if pose(n,(1543,1549),(1000,180,1920,1000))==1543:s['asset']='cup-calm-v2'
            # 杯子和裸手使用同一个原画图层，避免杯沿带回白手套。
            s['cup']=False
        elif s['ref']==1608:
            if pose(n,(1585,1591),(370,150,1120,800))==1591:s.update(asset='mage-cup-subtle-v2',ref=1591)
            s['cup']=False
        elif s['ref']==2200:
            if pose(n,(2197,2221),(380,350,1720,1000))==2221:s.update(asset='mage-fingers-closed-v2',ref=2221)
        elif s['ref']==2448:
            if pose(n,(2437,2452),(620,300,1260,850))==2437:s.update(asset='casual-card-closed-v2',ref=2437,card=False)
        out,area=f.apply_scene(src,n,s)
        out=restore_cup_grip(out,src,n,s['ref'])
    else:
        # 已有的差分、动物、字卡和镜框路径继续使用。原样缓存是可选加速，非构建依赖。
        prior=ROOT/f'frames/full-composite/{n:05d}.png'
        out=c.read(prior) if prior.exists() else f.render(n)[0]
        area=np.full((1080,1920),255,np.uint8);changed=False
    out=credits(out,n)
    return out,{'frame':n,'mode':mode,'v2_recomputed':changed,'source_pose_driven':True if changed else None,'track':c.TRACK_LOG.get(str(n))}

def setup():
    # 图像模型差分不重画纸框；纸框从已通过的同镜头稿恢复到派生文件。
    base=c.asset('full-1224');new=c.asset('mage-hand-chest-v2')
    framed=c.paste(base,new,c.frame_inner(base))
    Image.fromarray(framed).save(ROOT/'assets/mage-hand-chest-v2-framed.png')
    # 采用清单随源码固定；不再读取逐批清单或在构建时改写输入元数据。

def render_one(n):
    cv2.setNumThreads(1);out,record=render(n)
    Image.fromarray(out).save(DEST/f'{n:05d}.png',compress_level=3)
    return record

def preview(picks):
    folder=ROOT/'review/v2-preview';folder.mkdir(exist_ok=True)
    font=ImageFont.truetype(FONT,17)
    for page in range((len(picks)+15)//16):
        sheet=Image.new('RGB',(1920,4*297),'#171923');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*16:page*16+16]):
            out,_=render(n);Image.fromarray(out).save(folder/f'{n:05d}.png')
            x=j%4*480;y=j//4*297;sheet.paste(Image.fromarray(out).resize((480,270)),(x,y+27));d.text((x+5,y+3),f'{n} {n/24:.3f}s',font=font,fill='white')
        sheet.save(folder/f'page-{page+1:02d}.jpg',quality=95)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--all',action='store_true');ap.add_argument('--frames',nargs='*',type=int);args=ap.parse_args();cv2.setNumThreads(1);setup()
    if args.all:
        DEST.mkdir(exist_ok=True);records=[]
        # OpenCV 预处理后不 fork 线程池，否则 Linux 子进程可能停在首帧。
        with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('spawn')) as pool:
            for i,r in enumerate(pool.map(render_one,range(3768),chunksize=8)):
                records.append(r)
                if i%120==0:print(f'v2 rendered {i}/3768',flush=True)
        (ROOT/'review/v2-frame-verification.json').write_text(json.dumps(records,indent=2))
    else:preview(args.frames or [464,534,540,787,792,798,804,810,1119,1233,1543,1549,1585,1591,2166,2221,2437,2452,2500,2628,2710])

if __name__=='__main__':main()
