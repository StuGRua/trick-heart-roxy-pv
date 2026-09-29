"""提取局部原画参考；框、歌词、道具之后按源帧恢复。"""
import json
from PIL import Image,ImageDraw,ImageFont
from prepare import ROOT
from runtime import FONT
REFS={24: (620, 160, 1150, 925), 216: (680, 410, 1270, 940), 393: (430, 0, 1090, 720), 546: (225, 350, 820, 1080), 576: (200, 300, 1110, 1080), 600: (1090, 180, 1820, 1080), 612: (960, 200, 1830, 1080), 1018: (130, 600, 790, 1080), 1059: (350, 100, 1150, 1080), 1071: (340, 240, 1350, 1080), 1075: (390, 260, 1450, 1080), 1084: (260, 220, 1540, 1080), 1850: (880, 250, 1500, 1080), 1858: (600, 180, 1230, 1080), 1872: (620, 490, 1250, 1080), 3003: (570, 300, 1370, 810), 3012: (570, 300, 1370, 810), 3024: (570, 300, 1370, 810), 205: (680, 350, 1270, 940), 220: (530, 350, 1270, 940), 549: (225, 300, 1050, 1080), 552: (225, 300, 1050, 1080), 555: (225, 300, 1050, 1080), 603: (960, 200, 1830, 1080), 1064: (280, 250, 1130, 1080), 1856: (450, 250, 1140, 1080), 1875: (650, 680, 1330, 1080)}
def main():
    dest=ROOT/'assets/v3-reference';dest.mkdir(exist_ok=True)
    for n,box in REFS.items():Image.open(ROOT/f'frames/full-composite-v2/{n:05d}.png').crop(box).save(dest/f'hand-{n}.png')
    (dest/'crops.json').write_text(json.dumps(REFS,indent=2))
    items=list(REFS);font=ImageFont.truetype(FONT,18)
    for page in range((len(items)+5)//6):
        sheet=Image.new('RGB',(1500,1000),'#15171e');d=ImageDraw.Draw(sheet)
        for j,n in enumerate(items[page*6:page*6+6]):
            a=Image.open(dest/f'hand-{n}.png');a.thumbnail((480,450));x=j%3*500;y=j//3*500
            sheet.paste(a,(x+(500-a.width)//2,y+40));d.text((x+5,y+5),str(n),font=font,fill='white')
        sheet.save(ROOT/f'review/v3-hand-targets-{page+1}.jpg',quality=96)
if __name__=='__main__':main()
