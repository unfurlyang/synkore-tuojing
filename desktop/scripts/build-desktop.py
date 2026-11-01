"""Reproducible Windows build, run from desktop/ after installing build requirements."""
import os,subprocess,sys,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
os.chdir(root)
version='1.6.0'
env={**os.environ,'SYNKORE_RELEASE_DIR':f'Synkore-Tuojing-{version}-Windows-x64'}
commands=[['node','node_modules/vite/bin/vite.js','build'],
 [sys.executable,'-m','PyInstaller','--noconfirm','--distpath','runtime-build','--workpath','py-build/build','py-build/tingjian-backend.spec'],
 ['node','scripts/package.cjs'],[sys.executable,'scripts/stamp_windows.py']]
for cmd in commands:subprocess.run(cmd,cwd=root,env=env,check=True)
out=Path(env.get('SYNKORE_OUTPUT_DIR',str(root/'release')))/env['SYNKORE_RELEASE_DIR']
shutil.copy2(root.parent/'docs/WINDOWS.md',out/'使用说明.md')
shutil.copy2(root.parent/'THIRD_PARTY_NOTICES.md',out/'THIRD_PARTY_NOTICES.md')
print(out)
