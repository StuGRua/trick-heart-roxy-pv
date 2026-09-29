"""只检查公开白名单，不读取凭证或仓库外文件。"""
import ast,json,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def public_files():
    names=json.loads((ROOT/'public-files.json').read_text())['files']
    if len(names)!=len(set(names)):raise ValueError('Duplicate public entry')
    paths=[]
    for name in names:
        p=ROOT/name
        if p.is_symlink() or not p.is_file() or p.resolve().relative_to(ROOT).as_posix()!=name:raise ValueError('Unsafe or missing public path: '+name)
        if name.startswith(('frames/','review/','deliverables/','.venv/')) or p.suffix.lower() in ('.mp4','.m4s','.wav','.png','.zip'):raise ValueError('Generated/raw media in public list: '+name)
        paths.append((name,p))
    return paths

def main():
    patterns=[re.compile(r'(?:[A-Za-z]:[/\\]|/mnt/[a-z]/)(?:Users|ai_workspace)[/\\]',re.I),re.compile('codex://'+r'threads/'),re.compile(r'sk-[A-Za-z0-9]{24,}')]
    paths=public_files();total=0
    for name,p in paths:
        b=p.read_bytes();total+=len(b)
        if p.suffix.lower() in ('.ttf','.otf'):
            if name!='assets/fonts/ZCOOLKuaiLe-Regular.ttf':raise ValueError('Unexpected font: '+name)
            continue
        s=b.decode('utf-8-sig')
        if any(x.search(s) for x in patterns):raise ValueError('Private path or secret-like text: '+name)
        if p.suffix=='.py':ast.parse(s,filename=name)
        if p.suffix=='.json':json.loads(s)
    # Git看到的候选与白名单相同，防止git add .夹带本地输入。
    git_match=None
    if (ROOT/'.git').is_dir():
        p=subprocess.run(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,capture_output=True,text=True,check=True)
        if set(p.stdout.splitlines())!={n for n,_ in paths}:raise ValueError('Git candidates differ from public-files.json')
        git_match=True
    print(json.dumps({'public_files':len(paths),'bytes':total,'syntax_and_json_valid':True,'private_path_scan_pass':True,'git_candidates_match':git_match}))

if __name__=='__main__':main()
