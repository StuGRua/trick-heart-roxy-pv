"""共享媒体哈希、命令与原音轨验证。"""
import hashlib,subprocess
from prepare import FFMPEG,winpath
from runtime import executable
PROBE=executable("ffprobe")
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def run(exe,args):
    p=subprocess.run([exe]+args,capture_output=True)
    if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace')[-2000:])
    return p

def audio_hash(path,codec):
    args=['-v','error','-i',winpath(path),'-map','0:a:0','-vn','-c:a',codec,'-f','hash','-hash','sha256','pipe:1']
    return run(FFMPEG,args).stdout.decode().strip()
