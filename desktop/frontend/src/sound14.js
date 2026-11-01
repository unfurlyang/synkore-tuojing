import './sound.css';
export function initSound({initial={},onChange}={}){
  const PREVIEW='你好呀，我是你的小幽灵。慢慢来，我会陪着你。';
  let prefs={effects:initial.effects!==false,voice:initial.voice!==false,pack:initial.pack==='bright'?'bright':'gentle'};
  let context,armed=false,controller,audio,url,voiceTimer,sequence=0,lastSpoken='',lastAt=0,currentText=document.querySelector('#ghost-message')?.textContent?.trim()||PREVIEW;
  const card=document.querySelector('.companion-card'),canvas=document.querySelector('#ghost-canvas');
  document.querySelector('.gesture-hint')?.remove();
  const manifest=fetch('/assets/voice16/manifest.json').then(r=>r.ok?r.json():null).catch(()=>null);
  const tools=document.createElement('div');tools.className='sound-tools';
  tools.innerHTML='<div class="voice-pack-picker" role="group" aria-label="幽灵语音包"><button type="button" id="voice-gentle">温柔</button><button type="button" id="voice-bright">灵动</button></div><button type="button" id="preview-ghost-voice">试听这句话</button><button type="button" id="toggle-effects" aria-label="切换操作音效"></button><button type="button" id="toggle-ghost-voice" aria-label="切换幽灵语音"></button><span id="voice-availability" role="status"></span>';card.append(tools);
  const availability=tools.querySelector('#voice-availability');
  const label=()=>prefs.pack==='bright'?'灵动':'温柔';
  const topToggle=document.querySelector('#voice-pack-toggle');
  function sync(){tools.querySelector('#toggle-effects').textContent=prefs.effects?'♪ 音效开':'♪ 音效关';tools.querySelector('#toggle-effects').setAttribute('aria-pressed',String(prefs.effects));tools.querySelector('#toggle-ghost-voice').textContent=prefs.voice?'幽灵语音开':'幽灵语音关';tools.querySelector('#toggle-ghost-voice').setAttribute('aria-pressed',String(prefs.voice));for(const pack of ['gentle','bright'])tools.querySelector('#voice-'+pack).setAttribute('aria-pressed',String(prefs.pack===pack));if(topToggle){topToggle.textContent=label();topToggle.setAttribute('aria-label','切换幽灵语气，当前'+label());topToggle.setAttribute('aria-pressed',String(prefs.pack==='bright'));topToggle.title='切换到'+(prefs.pack==='bright'?'温柔':'灵动')+'语音';}}
  function cancel(){sequence++;controller?.abort();controller=null;if(audio){audio.pause();audio=null;}if(url){URL.revokeObjectURL(url);url=null;}clearTimeout(voiceTimer);canvas.dataset.voiceSpeaking='false';}
  function quiet(){return !!document.querySelector('#synkore-intro')||canvas.dataset.captureActive==='true'||['speaking','listening'].includes(canvas.dataset.state)||document.querySelector('#capture-status')?.textContent==='正在聆听'||[...document.querySelectorAll('audio')].some(a=>!a.paused);}
  function unlock(){armed=true;if(!context)context=new AudioContext();void context.resume().catch(()=>{});}
  document.addEventListener('pointerdown',unlock);document.addEventListener('keydown',unlock);
  const notes={click:[660],nav:[440,660],pet:[520,650,780],highfive:[900,1200],sleep:[520,390,260],wake:[330,520,780],success:[523,659,784,1047],error:[240,185],record:[392,587],stop:[587,392]};
  function effect(kind){if(!prefs.effects||!armed||quiet()||!context)return;const t=context.currentTime;for(const [i,hz]of(notes[kind]||notes.click).entries()){const o=context.createOscillator(),g=context.createGain();o.type=kind==='highfive'?'triangle':'sine';o.frequency.setValueAtTime(hz,t+i*.065);g.gain.setValueAtTime(0,t+i*.065);g.gain.linearRampToValueAtTime(.032,t+i*.065+.008);g.gain.exponentialRampToValueAtTime(.0001,t+i*.065+.16);o.connect(g);g.connect(context.destination);o.start(t+i*.065);o.stop(t+i*.065+.18);o.onended=()=>{o.disconnect();g.disconnect();};}canvas.dataset.lastSound=kind;}
  async function speak(text,force=false){
    if(!prefs.voice||!armed||quiet()||!text)return;
    const pack=prefs.pack,now=performance.now(),identity=pack+text;
    if(!force&&(identity===lastSpoken||now-lastAt<1700))return;
    cancel();const id=sequence;lastSpoken=identity;lastAt=now;
    const request=new AbortController();controller=request;
    try{
      const library=await manifest;if(id!==sequence)return;
      let location=library?.packs?.[pack]?.clips?.[text];
      const headers={'X-App-Token':document.querySelector('meta[name=app-token]').content};
      if(!location){
        availability.textContent='正在准备'+label()+'语音…';
        const result=await fetch('/v1/companion/speech',{method:'POST',headers:{...headers,'Content-Type':'application/json'},signal:request.signal,body:JSON.stringify({user_id:'synkore-companion',text,pack})});
        if(!result.ok){const problem=await result.json().catch(()=>({}));throw Error(typeof problem.detail==='string'?problem.detail:'语音暂不可用，请稍后重试');}
        const data=await result.json();if(data.verified!==true||data.text!==text||data.pack!==pack||!/^\/v1\/audio\/[a-f0-9]{32}\.wav$/.test(data.audio_url))throw Error('语音与文字校验失败，已停止播报');location=data.audio_url;
      }
      if(!/^\/(assets\/voice16\/(gentle|bright)\/[a-f0-9]{16}|v1\/audio\/[a-f0-9]{32})\.wav$/.test(location))throw Error('语音地址无效');
      const result=await fetch(location,{headers,signal:request.signal});if(!result.ok)throw Error('语音加载失败');const blob=await result.blob();
      if(location.startsWith('/assets/')){const check=library?.checks?.[location];if(!check||check.text!==text)throw Error('语音包文字校验失败，已停止播报');const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()))].map(v=>v.toString(16).padStart(2,'0')).join('');if(digest!==check.sha256)throw Error('语音包文件校验失败，已停止播报');}
      if(id!==sequence||request.signal.aborted||quiet())return;
      url=URL.createObjectURL(blob);audio=new Audio(url);audio.volume=pack==='gentle'?.58:.54;
      audio.onplay=()=>{if(id!==sequence)return;document.dispatchEvent(new CustomEvent('synkore-voice-text',{detail:{text}}));canvas.dataset.voiceSpeaking='true';canvas.dataset.lastSpoken=text;canvas.dataset.voicePack=pack;};
      audio.onended=audio.onerror=()=>{if(id===sequence)cancel();};
      await audio.play();availability.textContent=label()+' · 自然语音';
    }catch(error){if(id===sequence&&error.name!=='AbortError'){availability.textContent=error.message;cancel();}}
  }
  document.addEventListener('synkore-message',event=>{cancel();currentText=event.detail.text;voiceTimer=setTimeout(()=>speak(currentText,true),150);});
  document.addEventListener('synkore-character',event=>effect(event.detail.kind));
  document.addEventListener('click',event=>{const button=event.target.closest('button');if(!button||button.disabled||button.id==='voice-pack-toggle'||button.closest('.sound-tools')||button.closest('.character-play')||button.closest('.companion-actions'))return;effect(button.matches('[data-view]')?'nav':button.id==='start-listen'?'record':button.id==='stop-listen'?'stop':'click');});
  window.addEventListener('synkore-feedback',event=>effect(event.detail.kind));
  tools.querySelector('#toggle-effects').onclick=()=>{prefs.effects=!prefs.effects;sync();onChange?.({...prefs});if(prefs.effects)effect('nav');};
  tools.querySelector('#toggle-ghost-voice').onclick=()=>{prefs.voice=!prefs.voice;if(!prefs.voice)cancel();sync();onChange?.({...prefs});if(prefs.voice)speak(currentText,true);};
  function choosePack(pack){cancel();prefs.pack=pack;sync();onChange?.({...prefs});unlock();speak(currentText,true);}
  for(const pack of ['gentle','bright'])tools.querySelector('#voice-'+pack).onclick=()=>choosePack(pack);
  if(topToggle)topToggle.onclick=()=>choosePack(prefs.pack==='bright'?'gentle':'bright');
  tools.querySelector('#preview-ghost-voice').onclick=()=>{unlock();speak(currentText,true);};
  const observer=new MutationObserver(()=>{if(quiet())cancel();});observer.observe(canvas,{attributes:true,attributeFilter:['data-state','data-capture-active']});
  window.addEventListener('beforeunload',()=>{cancel();void context?.close();});sync();availability.textContent=label()+' · 本地语音包';return {effect,speak};
}
