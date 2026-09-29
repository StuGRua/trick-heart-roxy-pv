"""杂耍按源手形选十三张干净原画，球独立保留逐帧轨迹与前指遮挡。"""
from functools import lru_cache
import json

import composite as c
import full_composite as f
import revision3_composite as v3
import revision_composite as v2
from composite import np,cv2,Image
from prepare import ROOT
from revision4_layers import boundary_connected

POSE_REFS=(2472,2478,2484,2487,2490,2496,2502,2508,2514,2517,2520,2523,2600)
BOX=(1040,45,1880,1040)

def face_anchor(im,generated=False):
    r,g,b=im.astype(np.int16).transpose(2,0,1)
    skin=(r>240)&(g>170)&(g<(246 if generated else 240))&(b>(145 if generated else 175))&(b<245)
    skin&=c.rect((0,170,1920,620))>0
    count,labels,stats,centers=cv2.connectedComponentsWithStats(skin.astype(np.uint8),8)
    ids=[i for i in range(1,count) if stats[i,4]>1500 and 75<stats[i,2]<440 and 60<stats[i,3]<400]
    if not ids:raise ValueError('Juggling face anchor hidden or missing')
    i=max(ids,key=lambda j:stats[j,4]);return float(centers[i,0]),float(centers[i,1]),float(stats[i,2])

def gloves(im,anchor):
    r,g,b=im.astype(np.int16).transpose(2,0,1);x,y,w=anchor
    gray=(r>215)&(r<251)&(np.abs(r-g)<9)&(np.abs(g-b)<9)
    gray&=c.rect((int(x-460),int(y-90),int(x+460),1060))>0
    return f.component(gray.astype(np.uint8)*255,80)

@lru_cache(maxsize=340)
def source_info(n):
    # 闭幕遮住脸后沿用最近仍可见的锚点，不以旧人物作为失败回退画面。
    src=c.reference(n)
    try:a=face_anchor(src)
    except ValueError:
        if n<2769:raise
        a=source_info(2768)[0]
    scale=120/a[2];m=np.float32([[scale,0,180-a[0]*scale],[0,scale,100-a[1]*scale]])
    hands=cv2.warpAffine(gloves(src,a),m,(360,560),flags=cv2.INTER_AREA).astype(np.float32)/255
    face=cv2.warpAffine(src,m,(360,560),flags=cv2.INTER_AREA)[45:125,115:245]
    face=cv2.resize(face,(32,24)).astype(np.float32)/255
    return a,hands,face

def choose(n):
    if n<2478:return 2472,0.0
    if n<2484:return 2478,0.0
    _,hands,face=source_info(min(n,2768))
    scores=[]
    for ref in POSE_REFS[2:]:
        _,rh,rf=source_info(ref)
        # 只比较同一动作段的手形与表情，身体平移缩放已经被归一化。
        score=float(np.abs(hands-rh).mean()*8+np.abs(face-rf).mean()*.2)
        scores.append((score,ref))
    score,ref=min(scores);return ref,score

@lru_cache(maxsize=13)
def sprite(ref):
    x0,y0,x1,y1=BOX
    crop=np.asarray(Image.open(ROOT/f'assets/juggle-{ref}-v4-clean.png').convert('RGB').resize((x1-x0,y1-y0),Image.Resampling.LANCZOS))
    r,g,b=crop.astype(np.int16).transpose(2,0,1)
    red=(r>65)&(r>g*1.5)&(r>b*1.45)&(np.abs(g-b)<40)
    paper=(r>220)&(g>210)&(b>185)&(np.abs(r-g)<22)&(g>b)
    mask=(~boundary_connected(red|paper)).astype(np.uint8)*255
    # 排除裁切边缘的纸框线；原PV的边框最后从source恢复。
    mask[:8]=0;mask[-10:]=0;mask[:,:8]=0;mask[:,-12:]=0
    im=np.zeros((1080,1920,3),np.uint8);im[:]=[137,54,51]
    alpha=np.zeros((1080,1920),np.uint8);im[y0:y1,x0:x1]=crop;alpha[y0:y1,x0:x1]=mask
    # 原图下沿在镜框处裁断；整体缩放时延续裁断衣料，不能露出悬空横切边。
    bottom=990 if ref==2523 else 1020
    im[bottom:]=im[bottom-1];alpha[bottom:]=alpha[bottom-1]
    # 原画已按源裁切注册。新旧角色的可见肤色宽度不同，不能再以其比值
    # 缩放原画，否则手掌会被拉离源球；仅源片同角色之间计算相机变换。
    return im,alpha

def ball_layer(src):
    r,g,b=src.astype(np.int16).transpose(2,0,1)
    yellow=((r>230)&(g>180)&(b<100)).astype(np.uint8)*255
    contours,_=cv2.findContours(yellow,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    rgb=src.copy();alpha=np.zeros((1080,1920),np.uint8);centers=[]
    white=(np.minimum(np.minimum(r,g),b)>238).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(white,8)
    dots=np.isin(labels,[i for i in range(1,count) if stats[i,4]<90])
    for p in contours:
        if cv2.contourArea(p)<300:continue
        (x,y),radius=cv2.minEnclosingCircle(p)
        if not 12<radius<100:continue
        point=(round(x),round(y));rad=round(radius)
        m=np.zeros((1080,1920),np.uint8);cv2.circle(m,point,rad,255,-1,cv2.LINE_AA)
        cv2.circle(rgb,point,rad,(28,26,22),-1,cv2.LINE_AA)
        cv2.circle(rgb,point,max(1,rad-2),(255,202,20),-1,cv2.LINE_AA)
        rgb[dots&(m>0)]=src[dots&(m>0)];alpha|=m
        centers.append([float(x),float(y),float(radius)])
    return rgb,alpha,centers

def render(src,n):
    if n>=2778:
        # 此事件起源片已全闭幕；整层恢复包括从画布上沿进入的黑缝，
        # 不再让颜色分割漏掉的开放缝隙显示被遮挡的人物。
        return src.copy(),{'curtain_state':'closed','pose_reference':choose(n)[0]}
    ref,score=choose(n);a=source_info(n)[0];ra=source_info(ref)[0]
    scale=a[2]/ra[2];matrix=np.float32([[scale,0,a[0]-ra[0]*scale],[0,scale,a[1]-ra[1]*scale]])
    if n<2769 and n!=ref:
        # 球遮到脸边会改变可见肤色宽度；粗对齐后用原角色的头发/衣服
        # 特征细化整个人物变换，避免将遮挡误判为镜头缩放。
        aligned=c.warp(c.reference(ref),matrix)
        box=(max(0,int(a[0]-400)),160,min(1920,int(a[0]+400)),1040)
        delta=c.tracking(aligned,src,box,n)
        matrix=(np.vstack((delta,[0,0,1]))@np.vstack((matrix,[0,0,1])))[:2].astype(np.float32)
    gen,alpha=sprite(ref)
    gen=cv2.warpAffine(gen,matrix,(1920,1080),borderMode=cv2.BORDER_REPLICATE)
    alpha=cv2.warpAffine(alpha,matrix,(1920,1080),flags=cv2.INTER_NEAREST,borderMode=cv2.BORDER_REPLICATE)
    region=c.rect((max(45,int(a[0]-530*scale)),40,min(1875,int(a[0]+530*scale)),1040))
    old=(c.source_nonbg(src,f.color(src))&(region>0)).astype(np.uint8)*255
    erase=c.dilate(old|alpha,5);out=src.copy();out[erase>0]=f.color(c.reference(2500));out=c.paste(out,gen,alpha)
    balls,bm,centers=ball_layer(src);out=c.paste(out,balls,bm)
    r,g,b=gen.astype(np.int16).transpose(2,0,1)
    skin=(r>205)&(g>150)&(b>130)&(r>g+7)&(alpha>0)
    # 前指仅限源握球处；整张手掌不能盖住球心，漂浮球也不会受肤色误遮。
    front=c.dilate(skin.astype(np.uint8)*255,2)&c.dilate(gloves(src,a),7)&bm
    out=c.paste(out,gen,front)
    inner=c.frame_inner(src) if n<2769 else c.rect((45,35,1880,1040))
    out=c.paste(src,out,inner)
    out=c.paste(out,src,c.dilate(f.letters_mask(src,[(0,380,1920,670)]),2))
    if n>=2702:
        box=(150,380,1050,610)
        phase=int(v2.pose(n,(2704,2710),box)==2710);rgba=v3.lettering(phase,False)
        cm=c.tracking(c.reference(2702),src,box,n)
        out=c.paste(out,c.warp(rgba[:,:,:3],cm),c.warp(rgba[:,:,3],cm,True))
    if n>=2769:
        sr,sg,sb=src.astype(np.int16).transpose(2,0,1)
        darkred=(sr>25)&(sr<110)&(sr>sg*1.5)&(sr>sb*1.5)
        curtain=c.morph(boundary_connected(darkred).astype(np.uint8)*255,7)
        contours,_=cv2.findContours(curtain,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(curtain,contours,-1,255,-1)
        out=c.paste(out,src,curtain)
    return out,{'pose_reference':ref,'pose_match_score':score,'ball_centers':centers,
                'finger_occlusion_pixels':int(np.count_nonzero(front)),'source_driven_phase':True}

def event_manifest():
    rows=[]
    for n in range(2472,2785):
        ref,score=choose(n);rows.append({'frame':n,'pose_reference':ref,'score':score})
    (ROOT/'review/v4-juggle-events.json').write_text(json.dumps(rows,indent=2))
    return rows

if __name__=='__main__':
    cv2.setNumThreads(1);event_manifest()
