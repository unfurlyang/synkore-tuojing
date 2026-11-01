const {app,BrowserWindow,ipcMain,dialog,shell,session,safeStorage,Menu}=require('electron');
const {spawn,execFile}=require('node:child_process');
const fs=require('node:fs');const path=require('node:path');const net=require('node:net');const crypto=require('node:crypto');
app.setName('synkore');
app.setPath('userData',process.env.SYNKORE_USER_DATA||path.join(app.getPath('appData'),'Synkore'));
const single=app.requestSingleInstanceLock();if(!single){app.quit();}
const root=path.resolve(__dirname,'..');let win,child,origin,port,settings={},quitting=false;
const token=crypto.randomBytes(32).toString('hex');
const allowed=new Set(['ASR_PROVIDER','REWRITE_PROVIDER','TTS_PROVIDER','MIMO_BASE_URL','MIMO_API_KEY','MIMO_ASR_MODEL','MIMO_LLM_MODEL','MIMO_TTS_MODEL','MIMO_TTS_VOICE','ASR_BASE_URL','ASR_API_KEY','ASR_MODEL','LLM_BASE_URL','LLM_API_KEY','LLM_MODEL','TTS_BASE_URL','TTS_API_KEY','TTS_MODEL','TTS_VOICE','MAX_UPLOAD_MB']);
const secrets=['MIMO_API_KEY','ASR_API_KEY','LLM_API_KEY','TTS_API_KEY'];
const defaults={ASR_PROVIDER:'mimo',REWRITE_PROVIDER:'mimo',TTS_PROVIDER:'mimo',MIMO_BASE_URL:'https://api.xiaomimimo.com/v1',MIMO_ASR_MODEL:'mimo-v2.5-asr',MIMO_LLM_MODEL:'mimo-v2.6-flash',MIMO_TTS_MODEL:'mimo-v2.5-tts',MIMO_TTS_VOICE:'mimo_default',MAX_UPLOAD_MB:'64'};
const cfg=()=>path.join(app.getPath('userData'),'settings.enc');
async function readSettings(){
  if(fs.existsSync(cfg())){
    try{
      const decrypted=await safeStorage.decryptStringAsync(fs.readFileSync(cfg()));
      const text=typeof decrypted==='string'?decrypted:decrypted.result;
      const saved=JSON.parse(text);
      if(!saved||typeof saved!=='object'||Array.isArray(saved))throw Error('Invalid settings');
      return {...defaults,...Object.fromEntries(Object.entries(saved).filter(([key])=>allowed.has(key)))};
    }catch{throw Error('本机加密配置暂时无法读取。配置文件仍保留，请勿删除；请确认正在使用原 Windows 账户，或联系维护者恢复。');}
  }
  let values={...defaults};
  if(process.env.COURSE_IMPORT_ENV && fs.existsSync(process.env.COURSE_IMPORT_ENV)){
    const content=fs.readFileSync(process.env.COURSE_IMPORT_ENV,'utf8');
    for(const line of content.split(/\r?\n/)){const match=line.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/);if(match&&allowed.has(match[1]))values[match[1]]=match[2].trim().replace(/^(['"])(.*)\1$/,'$2');}
  }
  return values;
}
async function persist(values){
  if(!await safeStorage.isAsyncEncryptionAvailable())throw Error('Windows 配置加密暂不可用，请稍后重试。');
  fs.mkdirSync(app.getPath('userData'),{recursive:true});
  const dest=cfg(),temp=dest+'.tmp';fs.writeFileSync(temp,await safeStorage.encryptStringAsync(JSON.stringify(values)));fs.renameSync(temp,dest);
}
function publicSettings(){const result={...settings};for(const key of secrets){result[key]='';result[key+'_SAVED']=Boolean(settings[key]);}return result;}
function validate(input){
  if(!input||typeof input!=='object'||Array.isArray(input))throw Error('配置格式无效');
  const next={...settings};
  for(const [k,v] of Object.entries(input)){
    if(!allowed.has(k))continue;if(typeof v!=='string'||v.length>3000||/[\r\n\0]/.test(v))throw Error('配置中存在无效内容');
    if(secrets.includes(k)&&!v.trim())continue;
    if(k.endsWith('BASE_URL')&&v){let u;try{u=new URL(v)}catch{throw Error('服务地址格式不正确')};if(!['https:','http:'].includes(u.protocol)||u.username||u.password||u.search||u.hash)throw Error('请填写不含账户信息或查询参数的 HTTP(S) 服务地址');}
    if(k.endsWith('PROVIDER')&&!['mimo','openai','rules','none'].includes(v))throw Error('模型类型无效');
    if(k==='MAX_UPLOAD_MB'&&(!/^\d+$/.test(v)||+v<1||+v>512))throw Error('上传上限需为 1–512 MB');
    next[k]=v.trim();
  }return next;
}
async function freePort(){return new Promise((resolve,reject)=>{const server=net.createServer();server.on('error',reject);server.listen(0,'127.0.0.1',()=>{const n=server.address().port;server.close(()=>resolve(n));});});}
async function stopBackend(){if(!child)return;const target=child;child=null;if(target.exitCode!==null)return;
  await new Promise(resolve=>{if(process.platform==='win32')execFile('taskkill',['/PID',String(target.pid),'/T','/F'],{windowsHide:true},()=>resolve());else{target.kill('SIGTERM');resolve();}});
}
async function startBackend(){
  const bundled=path.join(root,'runtime','tingjian-backend.exe');
  const py=process.env.COURSE_PYTHON;
  if(!fs.existsSync(bundled)&&!py)throw Error('未找到内置服务。开发模式请设置 COURSE_PYTHON。');
  const cmd=fs.existsSync(bundled)?bundled:py,args=fs.existsSync(bundled)?[]:[path.join(root,'backend','run_backend.py')];
  const env={...process.env,...settings,COURSE_PORT:String(port),LOCAL_APP_TOKEN:token,COURSE_WEB_DIR:path.join(root,'web'),DATA_DIR:path.join(app.getPath('userData'),'data'),PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'};
  delete env.COURSE_IMPORT_ENV;delete env.COURSE_ENV_FILE;
  child=spawn(cmd,args,{env,cwd:path.join(root,'backend'),windowsHide:true,stdio:['ignore','ignore','pipe']});
  let launchError;child.on('error',e=>{launchError=e.message});child.stderr.on('data',()=>{});
  for(let i=0;i<180;i++){
    if(launchError||(child&&child.exitCode!==null))throw Error('课程服务未能启动，请检查内置运行文件是否完整。');
    try{const r=await fetch(origin+'/v1/health',{signal:AbortSignal.timeout(700)});if(r.ok)return;}catch{}
    await new Promise(r=>setTimeout(r,250));
  }throw Error('课程服务启动超时，请重新打开软件。');
}
function senderAllowed(event){try{if(new URL(event.senderFrame.url).origin!==origin)throw Error()}catch{throw Error('不允许的请求来源')}}
if(single)app.whenReady().then(async()=>{
  try{
    settings=await readSettings();await persist(settings);port=await freePort();origin=`http://127.0.0.1:${port}`;
    session.defaultSession.setPermissionCheckHandler((wc,permission,requestingOrigin)=>permission==='media'&&requestingOrigin===origin);
    session.defaultSession.setPermissionRequestHandler((wc,permission,callback,details)=>{
      const requested=details.mediaTypes||[];callback(permission==='media'&&new URL(wc.getURL()).origin===origin&&requested.length>0&&requested.every(t=>t==='audio'));
    });
    session.defaultSession.webRequest.onHeadersReceived((details,callback)=>callback({responseHeaders:{...details.responseHeaders,'Content-Security-Policy':["default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; object-src 'none'; frame-src 'none'; base-uri 'self'"]}}));
    ipcMain.handle('settings:get',event=>{senderAllowed(event);return publicSettings()});
    ipcMain.handle('settings:save',async(event,input)=>{senderAllowed(event);const next=validate(input);await persist(next);settings=next;await stopBackend();await startBackend();return publicSettings();});
    ipcMain.handle('source:open',async(event,value)=>{senderAllowed(event);const url=new URL(value);if(url.protocol!=='https:'||url.username||url.password||!['www.bilibili.com','www.songhaomath.com','www.bjwmb.gov.cn','ocw.mit.edu'].includes(url.hostname))throw Error('来源链接无效');await shell.openExternal(url.href);});
    ipcMain.handle('app:version',event=>{senderAllowed(event);return app.getVersion()});
    const workspaceFile=path.join(app.getPath('userData'),'workspace.json');
    function readWorkspace(){if(fs.existsSync(workspaceFile)){try{return JSON.parse(fs.readFileSync(workspaceFile,'utf8'))}catch{}}return {userId:'user-'+crypto.randomUUID(),live:[],course:[]};}
    let workspaceState=readWorkspace();fs.writeFileSync(workspaceFile,JSON.stringify(workspaceState));
    ipcMain.handle('workspace:get',event=>{senderAllowed(event);return workspaceState});
    ipcMain.handle('workspace:save',async(event,input)=>{
      senderAllowed(event);if(!input||!Array.isArray(input.live)||!Array.isArray(input.course))throw Error('工作区格式无效');
      const data={userId:workspaceState.userId,live:input.live.slice(-40),course:input.course.slice(-40),selectedProfile:String(input.selectedProfile||'').slice(0,100),motion:input.motion==='subtle'?'subtle':'full',sound:{effects:input.sound?.effects!==false,voice:input.sound?.voice!==false,pack:input.sound?.pack==='bright'?'bright':'gentle'}};
      const content=JSON.stringify(data);if(content.length>4_000_000)throw Error('工作区内容过大，请先导出笔记');
      const temp=workspaceFile+'.tmp';await fs.promises.writeFile(temp,content);await fs.promises.rename(temp,workspaceFile);workspaceState=data;return true;
    });
    ipcMain.handle('file:save-text',async(event,input)=>{senderAllowed(event);if(!input||typeof input.content!=='string'||input.content.length>10_000_000)throw Error('导出内容无效');const name=String(input.name||'课程笔记.md').replace(/[\\/:*?"<>|]/g,'_');const result=await dialog.showSaveDialog(win,{defaultPath:name,filters:[{name:'Markdown 笔记',extensions:['md']}]});if(result.canceled)return false;await fs.promises.writeFile(result.filePath,input.content,'utf8');return true;});
    await startBackend();
    win=new BrowserWindow({width:1450,height:960,minWidth:1060,minHeight:740,title:'synkore·拓境',backgroundColor:'#f6f5f0',autoHideMenuBar:true,icon:path.join(root,'web/assets/app-icon.png'),show:false,webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webgl:true,autoplayPolicy:'no-user-gesture-required'}});
    Menu.setApplicationMenu(Menu.buildFromTemplate([{label:'synkore',submenu:[{role:'reload',label:'重新载入界面'},{role:'toggleDevTools',label:'开发工具'},{type:'separator'},{role:'quit',label:'退出'}]},{label:'编辑',submenu:[{role:'undo'},{role:'redo'},{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'}]},{label:'视图',submenu:[{role:'resetZoom'},{role:'zoomIn'},{role:'zoomOut'},{role:'togglefullscreen'}]}]));
    win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    win.webContents.on('will-navigate',(event,url)=>{if(new URL(url).origin!==origin)event.preventDefault();});
    win.once('ready-to-show',()=>win.show());await win.loadURL(origin);
    app.on('second-instance',()=>{if(win){if(win.isMinimized())win.restore();win.focus();}});
  }catch(e){dialog.showErrorBox('synkore 启动失败',e.message);await stopBackend();app.quit();}
});
app.on('window-all-closed',()=>app.quit());
app.on('before-quit',event=>{if(quitting)return;event.preventDefault();quitting=true;stopBackend().finally(()=>app.quit());});
