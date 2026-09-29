"""显式预检和顺序构建；不联网、不下载原作、不发布。"""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from prepare import ROOT,TASK,FFMPEG,SOURCE,winpath
from runtime import FONT,executable

def preflight():
    baseline=json.loads((TASK/'research/source-baseline.json').read_text());verified={}
    for name in ['source-1080-video.m4s','source-audio.m4s']:
        p=TASK/'research'/name
        if not p.is_file():raise FileNotFoundError(f'Prepare the source input: {p}')
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=baseline['files'][name]['sha256']:raise ValueError(f'Input SHA256 mismatch: {name}')
        verified[name]=digest
    for manifest in ['manifest.json','full-manifest.json','revision-manifest.json','revision3-manifest.json']:
        if not (ROOT/'assets'/manifest).is_file():raise FileNotFoundError('Missing asset manifest: '+manifest)
    resources=json.loads((ROOT/'assets/resources.json').read_text())['files']
    for name,record in resources.items():
        p=ROOT/name
        if not p.is_file():raise FileNotFoundError('Extract the resource archive into the repository root: '+name)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Resource SHA256 mismatch: '+name)
    for folder in ['frames/source','frames/composite','frames/full-source','review','deliverables']:(ROOT/folder).mkdir(parents=True,exist_ok=True)
    tools={}
    for name in ['ffmpeg','ffprobe']:
        exe=executable(name);p=subprocess.run([exe,'-version'],capture_output=True,text=True,check=True);tools[name]=p.stdout.splitlines()[0]
    report={'python':sys.version,'tools':tools,'font':Path(FONT).name,'font_sha256':hashlib.sha256(Path(FONT).read_bytes()).hexdigest(),'source_sha256':verified}
    (ROOT/'review/build-environment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--without-subtitles',action='store_true');ap.add_argument('--version',choices=['v3','v4'],default='v3');args=ap.parse_args();preflight()
    if args.check:return
    if not SOURCE.exists():
        subprocess.run([FFMPEG,'-v','error','-i',winpath(TASK/'research/source-1080-video.m4s'),'-i',winpath(TASK/'research/source-audio.m4s'),'-map','0:v:0','-map','1:a:0','-c','copy',winpath(SOURCE)],check=True)
    steps=[['prepare.py'],['prepare_full.py'],['composite.py','--all'],['revision_composite.py','--all'],['revision3_composite.py','--all']]
    if args.version=='v4':
        steps.extend([['revision4_composite.py','--all'],['revision_encode.py','--version','v4'],['revision4_verify.py','--sheets']])
        if not args.without_subtitles:steps.extend([['chinese_subtitles.py','--version','v4','--render','--encode'],['revision4_verify.py']])
    else:
        steps.extend([['revision_encode.py','--version','v3'],['revision3_verify.py','--sheets'],['revision3_verify.py']])
        if not args.without_subtitles:steps.extend([['chinese_subtitles.py','--render','--encode'],['verify_chinese_subtitles.py']])
    for step in steps:
        print('STEP',' '.join(step),flush=True)
        subprocess.run([sys.executable,str(ROOT/'tools'/step[0]),*step[1:]],cwd=ROOT,check=True)

if __name__=='__main__':main()
