const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('desktop',Object.freeze({
  openSource:url=>ipcRenderer.invoke('source:open',url),
  settings:()=>ipcRenderer.invoke('settings:get'),
  saveSettings:value=>ipcRenderer.invoke('settings:save',value),
  saveText:(name,content)=>ipcRenderer.invoke('file:save-text',{name,content}),
  version:()=>ipcRenderer.invoke('app:version')
  ,workspace:()=>ipcRenderer.invoke('workspace:get'),
  saveWorkspace:value=>ipcRenderer.invoke('workspace:save',value)
}));
