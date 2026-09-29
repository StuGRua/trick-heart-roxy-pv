"""全片镜头表、原画差分与分层合成；试片缓存只读复用。"""
import argparse,json,hashlib
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
import composite as c
from composite import np,cv2,Image,ImageDraw,ImageFont
from prepare import ROOT,source_frame,WINDOWS
from runtime import FONT

W,H=1920,1080
FULL=(0,0,W,H)
SHOTS=[]
def shot(a,b,mode,**kw):SHOTS.append(dict(start=a,end=b,mode=mode,**kw))
def scene(a,b,ref,roi=FULL,**kw):shot(a,b,'scene',ref=ref,asset=f'full-{ref}',roi=roi,**kw)

# 左闭右开、逐帧穷尽；无人物镜头显式 passthrough。
shot(0,86,'hands');shot(86,163,'portrait',look='casual',search=(500,230,1420,810))
shot(163,240,'hands');scene(240,325,264,(240,70,1620,1080),letters=[(1660,0,1920,570)])
shot(325,362,'opening_panels');shot(362,393,'pass');shot(393,444,'hands')
scene(444,449,444,letters=[(0,0,220,H),(1720,0,W,H)])
scene(449,454,449);scene(454,459,456);shot(459,464,'clasp')
scene(464,472,464);shot(472,534,'pass');scene(534,546,540,letters=[(0,0,220,H),(1720,0,W,H)])
shot(546,621,'hands');shot(621,624,'early_mage')
shot(624,792,'approved');shot(792,849,'back');shot(849,862,'pass')
scene(862,901,888,letters=[(0,0,1700,190)],track=(550,180,1500,840),particles='white')
shot(901,912,'rabbit_mage');shot(912,1104,'approved')
shot(1104,1130,'casual_smile');scene(1130,1154,1140,border=True)
scene(1154,1174,1158,border=True);scene(1174,1208,1188,border=True)
shot(1208,1224,'thought');scene(1224,1244,1224,border=True)
scene(1244,1281,1260,border=True,keep=[(0,520,510,H),(1410,40,1890,540)])
shot(1281,1308,'pass');shot(1308,1328,'polygons');shot(1328,1401,'pass')
scene(1401,1467,1440,(1080,100,W,H),letters=[(0,430,1220,670)],track=(1350,220,1880,800),cup=True)
scene(1467,1543,1512,(0,0,1310,H),letters=[(1020,430,W,650)],track=(130,330,750,880),cup=True)
scene(1543,1585,1548,(400,0,W,H),letters=[(190,0,350,800)],cup=True)
scene(1585,1631,1608,letters=[(1550,0,1780,780)],cup=True)
shot(1631,1680,'standing');shot(1680,1776,'approved');shot(1776,1850,'pass')
shot(1850,1930,'hands');scene(1930,2007,1944,(850,90,1360,H),letters=[(0,250,850,480),(1380,250,W,480)])
shot(2007,2042,'portrait',look='mage_happy',search=(480,210,1420,820))
shot(2042,2081,'pass');scene(2081,2127,2090,(790,0,W,H),letters=[(0,440,850,650)],duck=True)
shot(2127,2139,'pass');shot(2139,2169,'sideface');shot(2169,2197,'pass')
scene(2197,2224,2200,(360,0,W,H),particles='gold',letters=[(0,0,190,H)])
scene(2224,2235,2225,(400,0,W,H),particles='gold',letters=[(0,0,190,H)],flowers=True)
shot(2235,2314,'pass');scene(2314,2367,2328,(0,0,1320,H),letters=[(1600,0,W,H)],flowers=True)
scene(2367,2401,2388,letters=[(0,350,500,800),(1360,350,W,800)],flowers=True)
scene(2401,2437,2410,(210,0,1630,H),letters=[(1700,0,W,H)],flowers=True,smoke=True)
scene(2437,2455,2448,(220,0,1620,H),letters=[(0,0,180,H),(1700,0,W,H)],smoke=True,card=True)
shot(2455,2472,'hands');shot(2472,2785,'juggle')
shot(2785,2832,'sofa_pair');shot(2832,2952,'approved')
shot(2952,2970,'closing_mage');shot(2970,3003,'portrait',look='casual_happy',search=(0,170,1919,860))
shot(3003,3038,'hands');shot(3038,3083,'hands')
shot(3083,3239,'sofa_single');shot(3239,3283,'pass');shot(3283,3305,'rabbit_lap')
shot(3305,3321,'portrait',look='casual_sleep',search=(500,240,1420,790))
scene(3321,3328,3321,(730,0,1760,H),particles='gold',letters=[(0,0,1600,210)],duck=True)
scene(3328,3335,3330,(730,0,1760,H),particles='gold',letters=[(0,0,1600,210)],duck=True)
scene(3335,3356,3338,(730,0,1760,H),particles='gold',letters=[(0,0,1600,210)],duck=True)
shot(3356,3397,'sofa_single');shot(3397,3478,'moving_portrait')
shot(3478,3509,'hands');scene(3509,3543,3516,(440,0,1390,H),particles='gold',letters=[(0,0,340,H),(1680,0,W,H)],duck=True,card=True)
shot(3543,3584,'detail_panel',ref=3550);shot(3584,3630,'detail_panel',ref=3588)
scene(3630,3666,3640,(680,10,1280,H),particles='gold',letters=[(0,410,W,650)])
scene(3666,3698,3675,particles='gold',letters=[(1670,0,W,H)],animals=True)
shot(3698,3768,'ending_tag')
assert SHOTS[0]['start']==0 and SHOTS[-1]['end']==3768
assert all(a['end']==b['start'] for a,b in zip(SHOTS,SHOTS[1:]))

def color(src):
    p=src[::12,::12].reshape(-1,3);r,g,b=p.T
    red=(r>60)&(r>g*1.5)&(r>b*1.45)&(np.abs(g.astype(int)-b)<35)
    if red.sum()<20:return np.array([140,55,53],np.uint8)
    vals,cnts=np.unique(p[red],axis=0,return_counts=True)
    return vals[cnts.argmax()]

def component(mask,minimum=150):
    num,labels,stats,_=cv2.connectedComponentsWithStats(mask.astype(np.uint8),8)
    ids=[i for i in range(1,num) if stats[i,4]>=minimum]
    return np.isin(labels,ids).astype(np.uint8)*255

def key(im,box=FULL,border=False):
    m=(c.generated_nonred(im)&(c.rect(box)>0)).astype(np.uint8)*255
    if border:m&=cv2.erode(c.frame_inner(im),np.ones((12,12),np.uint8))
    return c.fill_small_holes(component(c.morph(m),80),80000)

def decorations(src,maximum=12000):
    # 大面积原衣料与装饰同色，按已确认的连通实例面积排除衣料。
    raw=c.butterflies(src);num,labels,stats,_=cv2.connectedComponentsWithStats(raw,8)
    ids=[i for i in range(1,num) if 8<stats[i,4]<maximum]
    return np.isin(labels,ids).astype(np.uint8)*255

def letters_mask(src,areas,maximum=18000):
    raw=c.text_foreground(src,areas);num,labels,stats,_=cv2.connectedComponentsWithStats(raw,8)
    ids=[i for i in range(1,num) if stats[i,4]<maximum]
    return np.isin(labels,ids).astype(np.uint8)*255

def colored_overlay(src,kind,box=FULL):
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    if kind=='white':m=(r>248)&(g>248)&(b>248)
    elif kind=='gold':return decorations(src)&c.rect(box)
    elif kind=='flower':m=((g>r*1.1)&(g>b*1.1))|((r>230)&(g>185)&(b<120))|((r>230)&(b>160)&(g<170))
    elif kind=='cup':m=(r>230)&(g>180)&(b<100)
    else:raise ValueError(kind)
    return c.dilate(component((m&(c.rect(box)>0)).astype(np.uint8)*255,70),3)

@lru_cache(maxsize=60)
def layer(name,box,border=False):
    im=c.asset(name).copy();m=key(im,box,border)
    if name=='full-459':
        r,g,b=im.astype(int).transpose(2,0,1)
        paper=((r>237)&(g>232)&(b>216)).astype(np.uint8)
        count,lab,st,_=cv2.connectedComponentsWithStats(paper,8)
        ids=[j for j in range(1,count) if st[j,4]>22000]
        m[np.isin(lab,ids)]=0
    return im,m

def apply_scene(src,n,s):
    box=tuple(s.get('roi',FULL));im,m=layer(s['asset'],box,s.get('border',False));im=im.copy();m=m.copy()
    matrix=c.tracking(c.reference(s['ref']),src,s['track'],n) if s.get('track') else np.float32([[1,0,0],[0,1,0]])
    im=c.warp(im,matrix);m=c.warp(m,matrix,True)
    region=c.rect(box);bg=color(src)
    old=(c.source_nonbg(src,bg)&(region>0)).astype(np.uint8)*255
    area=c.dilate(old|m,5);out=src.copy();out[area>0]=bg;out=c.paste(out,im,m)
    if s.get('border'):
        inner=c.frame_inner(src);out=c.paste(src,out,inner);area&=inner
    for keep in s.get('keep',[]):
        keepmask=c.rect(keep)
        if s['ref']==1260 and keep[0]==0:keepmask&=c.polygon([(0,620),(430,755),(330,1080),(0,1080)])
        out=c.paste(out,src,keepmask)
    if s.get('cup'):out=c.paste(out,src,colored_overlay(src,'cup'))
    if s.get('flowers'):out=c.paste(out,src,colored_overlay(src,'flower',box))
    if s.get('card') and s['ref'] not in (2448,3516):
        r,g,b=src.astype(np.int16).transpose(2,0,1)
        cm=(b>120)&(b>r*1.4)&(b>g*1.3)&(c.rect(box)>0)
        out=c.paste(out,src,c.dilate(cm.astype(np.uint8)*255,8))
    if s.get('particles'):
        dm=colored_overlay(src,s['particles'])
        exclude=None
        if 3321<=n<3356:exclude=(850,820,1780,H)
        elif 3509<=n<3543:exclude=(500,610,1420,H)
        elif 3630<=n<3666:exclude=(760,255,1280,H)
        elif 3666<=n<3698:exclude=(420,250,1560,H)
        if exclude:dm&=~c.rect(exclude)
        out=c.paste(out,src,dm)
    if s.get('smoke') and 2428<=n<2437:
        r,g,b=src.astype(int).transpose(2,0,1)
        smoke=(np.minimum(np.minimum(r,g),b)>220)&(np.maximum(np.maximum(r,g),b)-np.minimum(np.minimum(r,g),b)<13)
        out=c.paste(out,src,smoke.astype(np.uint8)*255)
    if s.get('duck'):
        zone=c.rect((650,0,1700,400));r,g,b=src.astype(np.int16).transpose(2,0,1)
        duck=((r>245)&(g>245)&(b>245))|((r>230)&(g>120)&(g<190)&(b<70))
        dm=c.dilate(component((duck&(zone>0)).astype(np.uint8)*255,100),4)
        out=c.paste(out,src,dm)
    if s.get('animals'):
        r,g,b=src.astype(int).transpose(2,0,1)
        rabbit=c.rabbit_mask(src,(0,170,530,700),(50,170,380,390))
        dog=((np.max(np.abs(src.astype(int)-[255,236,209]),axis=2)<18)|((r<60)&(g<60)&(b<60)))&(c.rect((950,580,W,H))>0)
        duck=(((r>246)&(g>246)&(b>246))|((r>230)&(g>125)&(g<185)&(b<80)))&(c.rect((1400,320,1850,720))>0)
        out=c.paste(out,src,rabbit|c.dilate(dog.astype(np.uint8)*255,3)|c.dilate(duck.astype(np.uint8)*255,3))
    if s.get('letters'):
        lm=letters_mask(src,s['letters'])
        if 3630<=n<3666:lm&=~c.rect((720,260,1270,H))
        out=c.paste(out,src,c.dilate(lm,2))
        if 3630<=n<3666:
            # 从100秒段原歌词取同一字形，避免将同色旧衣料带回。
            glyph_source=c.reference(2410);gbg=color(glyph_source)
            for cropbox,at in [((1718,367,1918,557),(723,421)),((1735,555,1918,721),(1034,438))]:
                x0,y0,x1,y1=cropbox;gx,gy=at;patch=glyph_source[y0:y1,x0:x1]
                gm=(c.source_nonbg(patch,gbg)).astype(np.uint8)*255
                ph,pw=patch.shape[:2];temp=out.copy();temp[gy:gy+ph,gx:gx+pw]=patch
                mask=np.zeros((H,W),np.uint8);mask[gy:gy+ph,gx:gx+pw]=gm
                out=c.paste(out,temp,mask);area|=mask
    return out,area

def panel_mask(src,search):
    bg=color(src);zone=c.rect(search)
    raw=(c.source_nonbg(src,bg)&(zone>0)).astype(np.uint8)*255
    contours,_=cv2.findContours(raw,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contours=[p for p in contours if cv2.contourArea(p)>1500]
    if not contours:return np.zeros((H,W),np.uint8),None
    chosen=max(contours,key=cv2.contourArea)
    m=np.zeros((H,W),np.uint8);cv2.drawContours(m,[chosen],-1,255,-1)
    return cv2.erode(m,np.ones((5,5),np.uint8)),cv2.boundingRect(chosen)

def moving_panel_bounds(src):
    # 此段只有一个人物竖框；红发实例给出框的左右和上边，
    # 排除文字与蝴蝶，允许它移动到任一画面边缘。
    r,g,b=src.astype(int).transpose(2,0,1)
    hair=((r>175)&(g<90)&(b>45)&(b<135)).astype(np.uint8)
    count,lab,st,_=cv2.connectedComponentsWithStats(hair,8)
    j=max(range(1,count),key=lambda j:st[j,4]);x,y,w,h=st[j,:4]
    return (max(0,x-15),max(0,y-15),min(W,x+w+15),min(H,y+660))

# 只取已绘制原画的脸部；小画框使用原片轮廓裁切。
PORTRAITS={
 'casual':('full-86',(585,315,1360,790)),
 'mage_happy':('full-325',(108,60,1040,505)),
 'casual_happy':('full-2090',(940,90,1820,1030)),
 'casual_sleep':('full-3321',(790,290,1740,1075)),
 'casual_open':('full-3338',(790,290,1740,1075)),
 'casual_drowsy':('full-3330',(790,290,1740,1075)),
}
def portrait(src,look,search):
    pm,bounds=panel_mask(src,search)
    if bounds is None:return src.copy(),pm
    name,box=PORTRAITS[look];im=c.asset(name).copy()
    # 小框原片纸色；只规范外部背景，衣服和脸不改色。
    red=~c.generated_nonred(im);im[red]=[240,233,212]
    x0,y0,x1,y1=box;crop=im[y0:y1,x0:x1]
    # 窄竖框从原画居中裁切，不能压扁脸部。
    ch,cw=crop.shape[:2];aspect=bounds[2]/bounds[3]
    if abs(cw/ch-aspect)>.25:
        if cw/ch>aspect:
            nw=int(ch*aspect);left=(cw-nw)//2;crop=crop[:,left:left+nw]
        else:
            nh=int(cw/aspect);top=(ch-nh)//2;crop=crop[top:top+nh]
    x,y,w,h=bounds;patch=cv2.resize(crop,(w,h),interpolation=cv2.INTER_LANCZOS4)
    out=src.copy();out[y:y+h,x:x+w]=patch
    return c.paste(src,out,pm),pm

def hands(src,n):
    r,g,b=src.astype(np.int16).transpose(2,0,1);out=src.copy()
    gray=(r>190)&(r<246)&(np.abs(r-g)<10)&(np.abs(g-b)<10)
    orange=(r>225)&(g>115)&(g<190)&(b<95)
    sleeve=(r>130)&(r<200)&(b>r)&(np.abs(r-g)<18)
    zone=c.rect((150,0,1810,H))>0
    if 546<=n<621:zone=c.rect((0,300,W,H))>0
    if 1850<=n<1930:
        zone=c.rect((0,0,W,H))>0
        # 只有此镜头的红色外套可改棕；不会作用于花/兔。
        suit=(r>170)&(g<90)&(b>45)&(b<130)&zone;out[suit]=[167,130,83]
    if 393<=n<444 or 546<=n<621 or 3003<=n<3038:
        suit=(r>170)&(g<90)&(b>45)&(b<130);out[suit]=[167,130,83];zone|=suit
    if n>=3003 or n<240:zone&=c.rect((500,50,1420,920))>0
    out[gray&zone]=[255,226,208];out[orange&zone]=[36,35,32];out[sleeve&zone]=[239,230,210]
    if n>=3478:out[orange&zone]=[239,230,210]
    return out,zone.astype(np.uint8)*255

def single_sofa(src,n):
    gen=c.asset('full-3120').copy();bg=color(src)
    zone=c.polygon([(780,350),(1120,350),(1150,650),(1320,775),(1310,1055),(980,1055),(1000,900),(785,800)])
    red=~c.generated_nonred(gen);gen[red]=bg
    out=c.paste(src,gen,zone)
    dm=decorations(src,4000)&~c.rect((800,400,1310,H));out=c.paste(out,src,dm)
    out=c.paste(out,src,c.rabbit_mask(src,(1000,650,1190,765),(1000,650,1150,750)))
    # 开场帘幕在人物前面。
    if n<3092:
        r,g,b=src.astype(int).transpose(2,0,1)
        curtain=(r<100)&(r>g*1.5)&(r>b*1.5)
        out=c.paste(out,src,curtain.astype(np.uint8)*255)
    return out,zone

def juggle(src,n):
    # 原片24帧循环：按手形匹配选三幅原画，球独立保留源运动。
    refs=[2500,2508,2512];refbase=c.reference(2500)
    srcsmall=cv2.resize(src,(192,108))
    # 分段位置变化是同一角色的平移/放大。
    r,g,b=src.astype(int).transpose(2,0,1)
    hair=((r>175)&(g<90)&(b>50)&(b<135)).astype(np.uint8)*255
    hair&=c.rect((40,45,1880,1040))
    count,labels,stats,centers=cv2.connectedComponentsWithStats(hair,8)
    ids=[i for i in range(1,count) if stats[i,4]>1000]
    if not ids:return src.copy(),np.zeros((H,W),np.uint8)
    ids.sort(key=lambda i:stats[i,4],reverse=True);i=ids[0]
    x,y,w,h=stats[i,:4]
    # 人物头发连通块定位，服装同红时使用脸部肤色轮廓定位。
    skin=((r>240)&(g>175)&(g<235)&(b>170)&(b<240)).astype(np.uint8)
    skin&=(c.rect((0,140,W,650))>0).astype(np.uint8)
    cnt,lab,st,cent=cv2.connectedComponentsWithStats(skin,8)
    inds=[j for j in range(1,cnt) if st[j,4]>1200]
    if inds:
        j=max(inds,key=lambda j:st[j,4]);cx,cy=cent[j];fw=st[j,2]
    else:cx,cy=1550,360;fw=260
    # 基准2500的脸中心 / 宽，生成原画与源布局保持一致。
    rr,gg,bb=refbase.astype(int).transpose(2,0,1)
    sm=((rr>240)&(gg>175)&(gg<235)&(bb>170)&(bb<240)&(c.rect((1100,150,1870,650))>0)).astype(np.uint8)
    cc,ll,ss,ct=cv2.connectedComponentsWithStats(sm,8);jj=max(range(1,cc),key=lambda j:ss[j,4]);rcx,rcy=ct[jj];rfw=ss[jj,2]
    scale=np.clip(fw/rfw,.65,1.6);matrix=np.float32([[scale,0,cx-rcx*scale],[0,scale,cy-rcy*scale]])
    phase=(n-2472)%24
    nr=2520 if phase<4 or phase>=20 else (2500 if phase<12 else (2508 if phase<16 else 2512))
    gen,gm=layer(f'full-{nr}',(1060,35,1880,1045),True);gen=c.warp(gen,matrix);gm=c.warp(gm,matrix,True)
    region=c.rect((max(45,int(cx-490*scale)),45,min(1875,int(cx+490*scale)),1040))
    bg=color(src);old=(c.source_nonbg(src,bg)&(region>0)).astype(np.uint8)*255
    area=c.dilate(old|gm,4);out=src.copy();out[area>0]=bg;out=c.paste(out,gen,gm)
    # 补齐被旧手指遮掉的球体；保留源轨迹与白色点纹。
    yellow=((r>230)&(g>180)&(b<100)).astype(np.uint8)*255
    contours,_=cv2.findContours(yellow,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    balls=np.zeros((H,W),np.uint8);ball_layer=src.copy()
    white=((r>235)&(g>235)&(b>235)).astype(np.uint8)
    cc,ll,ss,_=cv2.connectedComponentsWithStats(white,8)
    dots=np.isin(ll,[j for j in range(1,cc) if ss[j,4]<90])
    for contour in contours:
        if cv2.contourArea(contour)<300:continue
        (bx,by),rad=cv2.minEnclosingCircle(contour)
        if not 12<rad<100:continue
        circle=np.zeros((H,W),np.uint8);center=(round(bx),round(by));radius=round(rad)
        cv2.circle(circle,center,radius,255,-1,cv2.LINE_AA)
        cv2.circle(ball_layer,center,radius,(28,26,22),-1,cv2.LINE_AA)
        cv2.circle(ball_layer,center,max(1,radius-2),(255,202,20),-1,cv2.LINE_AA)
        ball_layer[dots&(circle>0)]=src[dots&(circle>0)];balls|=circle
    out=c.paste(out,ball_layer,balls);area|=balls
    inner=c.frame_inner(src) if n<2769 else c.rect((45,35,1880,1040))
    out=c.paste(src,out,inner);area&=inner
    out=c.paste(out,src,c.dilate(c.text_foreground(src,[(0,380,W,670)]),2))
    if n>=2769:
        dark=((r<110)&(g<70)&(b<70)).astype(np.uint8)
        count,lab,st,_=cv2.connectedComponentsWithStats(dark,8)
        ids=[j for j in range(1,count) if st[j,3]>900 and st[j,1]<100]
        curtain=np.isin(lab,ids).astype(np.uint8)*255
        out=c.paste(out,src,curtain)
    return out,area

def render(n):
    src=c.reference(n);s=next(s for s in SHOTS if s['start']<=n<s['end']);mode=s['mode']
    if mode=='approved':
        idx=next(sum(b-a for a,b in WINDOWS[:j])+n-a for j,(a,b) in enumerate(WINDOWS) if a<=n<b)
        cached=ROOT/f'frames/composite/{idx:05d}.png'
        if cached.exists():return c.read(cached),np.full((H,W),255,np.uint8),mode
        out,area=c.render(n)
        return out,area,mode
    if mode=='pass':
        out,area=src.copy(),np.zeros((H,W),np.uint8)
        if 3239<=n<3283:
            # 鸭子头像下沿仍能看见人物头顶，此处不是纯动物镜头。
            r,g,b=src.astype(int).transpose(2,0,1)
            hm=(r>175)&(g<90)&(b>45)&(b<130)&(c.rect((580,700,1365,790))>0)
            out[hm]=[100,117,188];area=hm.astype(np.uint8)*255
    elif mode=='scene':out,area=apply_scene(src,n,s)
    elif mode=='hands':out,area=hands(src,n)
    elif mode=='portrait':
        if n>=2970 and n<3003:out,area=c.band(src,'full-2976','left',(125,895))
        else:out,area=portrait(src,s['look'],s['search'])
    elif mode=='opening_panels':
        out,area=portrait(src,'mage_happy',(60,0,1010,600))
        if n>=343:
            out2,area2=portrait(src,'casual',(1030,590,W,H));out=c.paste(out,out2,area2);area|=area2
    elif mode=='early_mage':out,area=c.flat_scene(src,'mage-0624',624,(790,0,W,H),protect=c.butterflies(src),n=n)
    elif mode=='back':out,area=c.flat_scene(src,'back-0787',787,(550,190,1210,H),n=n)
    elif mode=='rabbit_mage':
        keep=c.rabbit_mask(src,(1300,240,1790,780),(1380,280,1720,620))
        out,area=c.flat_scene(src,'mage-0912',912,FULL,protect=keep,letters=[(0,0,1200,180),(1150,870,W,H)],n=n)
    elif mode=='casual_smile':out,area=apply_scene(src,n,dict(asset='casual-1103',ref=1103,roi=FULL,border=True))
    elif mode=='clasp':out,area=apply_scene(src,n,dict(asset='full-459-v2',ref=459))
    elif mode=='thought':
        pm,bd=panel_mask(src,(650,100,1730,950));out=src.copy();area=pm
        if bd:
            x,y,w,h=bd;im=c.asset('full-1209');out[y:y+h,x:x+w]=cv2.resize(im[148:879,760:1660],(w,h));out=c.paste(src,out,pm)
    elif mode=='polygons':
        out=src.copy();area=np.zeros((H,W),np.uint8);gen=c.asset('full-1319')
        for search,gb in [((990,130,1875,1025),(1015,240,1860,1010)),((60,50,945,1020),(65,55,860,890))]:
            if search[0]<100 and n<1318:continue
            pm,bd=panel_mask(src,search)
            if bd is None:continue
            x,y,w,h=bd;a,b,d,e=gb;patch=cv2.resize(gen[b:e,a:d],(w,h));temp=out.copy();temp[y:y+h,x:x+w]=patch;out=c.paste(out,temp,pm);area|=pm
    elif mode=='standing':out,area=c.standing(src,n)
    elif mode=='sideface':out,area=apply_scene(src,n,dict(asset='full-2145',ref=2145,roi=(1370,0,W,H),particles='gold'))
    elif mode=='juggle':out,area=juggle(src,n)
    elif mode=='sofa_pair':out,area=c.sofa(src,n)
    elif mode=='closing_mage':out,area=c.band(src,'closing-2951','right',(125,895))
    elif mode=='sofa_single':out,area=single_sofa(src,n)
    elif mode=='rabbit_lap':
        out=src.copy();r,g,b=src.astype(int).transpose(2,0,1);m=(r>130)&(r<200)&(b>r)&(np.abs(r-g)<18)&(c.rect((550,250,1380,800))>0);out[m]=[43,51,76];area=m.astype(np.uint8)*255
    elif mode=='moving_portrait':
        look='casual_open' if n<3417 or n>=3457 else ('casual_drowsy' if n<3438 else 'casual_sleep')
        out,area=portrait(src,look,moving_panel_bounds(src))
    elif mode=='detail_panel':
        pm,bd=panel_mask(src,(579,316,1370,798));out=src.copy();area=pm
        if bd:
            im=c.asset(f'full-{s["ref"]}');x,y,w,h=bd;out[y:y+h,x:x+w]=cv2.resize(im[325:790,580:1370],(w,h));out=c.paste(src,out,pm)
    elif mode=='ending_tag':
        out=src.copy();r,g,b=src.astype(int).transpose(2,0,1);zone=c.rect((140,290,960,800))>0
        cloth=(r>220)&(g>180)&(b>120)&(b<190)&zone;out[cloth]=[239,230,210];area=zone.astype(np.uint8)*255
    else:raise ValueError(mode)
    changed=np.any(out!=src,axis=2)
    if np.any(changed&(c.dilate(area,9)==0)):raise AssertionError(f'out-of-region {n} {mode}')
    return out,area,mode

def render_one(n):
    cv2.setNumThreads(1);out,area,mode=render(n)
    Image.fromarray(out).save(ROOT/f'frames/full-composite/{n:05d}.png',compress_level=3)
    return dict(frame=n,mode=mode,changed=int(np.any(out!=c.reference(n),axis=2).sum()),roi=int((area>0).sum()))

def resume_one(n):
    path=ROOT/f'frames/full-composite/{n:05d}.png'
    if path.exists() and not 2769<=n<2785:
        out=c.read(path);src=c.reference(n);s=next(s for s in SHOTS if s['start']<=n<s['end'])
        return dict(frame=n,mode=s['mode'],changed=int(np.any(out!=src,axis=2).sum()),roi=None,cached_from_checked_render=True)
    return render_one(n)

def preview(picks=None):
    if picks is None:picks=sorted(set([int((s['start']+s['end'])/2) for s in SHOTS if s['mode']!='approved']))
    dest=ROOT/'review/full-composite';dest.mkdir(exist_ok=True)
    font=ImageFont.truetype(FONT,17)
    for page in range((len(picks)+15)//16):
        sheet=Image.new('RGB',(1920,4*297),'#171922');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(picks[page*16:page*16+16]):
            out,_,mode=render(n);Image.fromarray(out).save(dest/f'{n:05d}.png');x=j%4*480;y=j//4*297
            sheet.paste(Image.fromarray(out).resize((480,270)),(x,y+27));d.text((x+4,y+4),f'{n} | {n/24:.2f}s | {mode}',font=font,fill='white')
        sheet.save(ROOT/f'review/full-preview-{page+1:02d}.jpg',quality=94)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--all',action='store_true');ap.add_argument('--resume',action='store_true');ap.add_argument('--frames',nargs='*',type=int);args=ap.parse_args()
    (ROOT/'full-shot-map.json').write_text(json.dumps(SHOTS,ensure_ascii=False,indent=2))
    if args.all:
        (ROOT/'frames/full-composite').mkdir(exist_ok=True);records=[]
        with ProcessPoolExecutor(max_workers=4) as pool:
            for i,r in enumerate(pool.map(resume_one if args.resume else render_one,range(3768),chunksize=8)):
                records.append(r)
                if i%96==0:print(f'rendered {i}/3768',flush=True)
        (ROOT/'review/full-frame-verification.json').write_text(json.dumps(records,indent=2))
    else:preview(args.frames)

if __name__=='__main__':main()
