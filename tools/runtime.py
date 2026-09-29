"""本地工具路径配置，不附带二进制或字体。"""
import os,shutil
from pathlib import Path

def executable(name):
    configured=os.environ.get('ROXY_'+name.upper())
    if configured:return configured
    for p in [Path('/mnt/c/exec_bin')/(name+'.exe'),Path('C:/exec_bin')/(name+'.exe')]:
        if p.is_file():return str(p)
    found=shutil.which(name)
    if found:return found
    raise FileNotFoundError(f'Set ROXY_{name.upper()} to the {name} executable')

def font_file():
    configured=os.environ.get('ROXY_FONT')
    if configured:return configured
    for p in ['/mnt/c/Windows/Fonts/arial.ttf','C:/Windows/Fonts/arial.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(p).is_file():return p
    raise FileNotFoundError('Set ROXY_FONT to a local TrueType font')

FONT=font_file()

def ffmpeg_font(ffmpeg):
    s=str(Path(FONT).resolve()).replace('\\','/')
    if s.startswith('/mnt/') and ffmpeg.lower().endswith('.exe'):s=s[5].upper()+':'+s[6:]
    return s.replace(':',chr(92)+':')
