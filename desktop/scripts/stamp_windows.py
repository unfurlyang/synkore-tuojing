from pathlib import Path
import os,json
from PIL import Image
from PyInstaller.utils.win32.icon import CopyIcons
from PyInstaller.config import CONF
from PyInstaller.utils.win32.versioninfo import write_version_info_to_executable,VSVersionInfo,FixedFileInfo,StringFileInfo,StringTable,StringStruct,VarFileInfo,VarStruct
ROOT=Path(__file__).resolve().parents[1]
out=Path(os.environ.get('SYNKORE_OUTPUT_DIR',str(ROOT/'release')))/os.environ.get('SYNKORE_RELEASE_DIR','synkore-Windows')
icon=ROOT/'models/synkore.ico'
Image.open(ROOT/'frontend/public/assets/ghost-portrait.png').save(icon,sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
exe=out/'synkore.exe'
CONF['workpath']=str(ROOT/'models')
CopyIcons(str(exe),[str(icon)])
version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version'];version_tuple=tuple(map(int,version.split('.')))+(0,)
info=VSVersionInfo(ffi=FixedFileInfo(filevers=version_tuple,prodvers=version_tuple,mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','synkore'),StringStruct('FileDescription','synkore·拓境 · 课程工作室'),StringStruct('FileVersion',version),StringStruct('InternalName','synkore'),StringStruct('OriginalFilename','synkore.exe'),StringStruct('ProductName','synkore·拓境'),StringStruct('ProductVersion',version)])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])
write_version_info_to_executable(str(exe),info)
print('Windows icon and product metadata set.')
