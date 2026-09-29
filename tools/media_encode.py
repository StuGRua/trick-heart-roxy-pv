"""共享FFmpeg原子编码辅助函数。"""
import subprocess
from prepare import ROOT,FFMPEG,winpath
OUT=ROOT/"deliverables"
def run(name,args,final):
    temp=final.with_name(final.stem+'.rendering.mp4')
    p=subprocess.run([FFMPEG,'-hide_banner','-v','error','-y']+args+['-movflags','+faststart',winpath(temp)],capture_output=True,text=True)
    (ROOT/f'review/{name}.log').write_text(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError(p.stderr[-3000:])
    temp.replace(final);print(name,'OK',final.stat().st_size,flush=True)
