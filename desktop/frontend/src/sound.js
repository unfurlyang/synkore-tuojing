import './sound.css';
export function initSound({initial={},onChange}={}){
  let cloudController,cloudAudio,cloudUrl;
  let prefs={effects:initial.effects!==false,voice:initial.voice!==false},context,armed=false,lastSpoken='',lastAt=0,voiceTimer;
  const card=document.querySelector('.companion-card'),canvas=document.querySelector('#ghost-canvas');
  document.querySelector('.gesture-hint')?.remove();
  const tools=document.createElement('div');tools.className='sound-tools';tools.innerHTML='<button type="button" id="toggle-effects" aria-label="切换操作音效"></button><button type="button" id="toggle-ghost-voice" aria-label="切换幽灵语音"></button><button type="button" id="preview-ghost-voice">试听声音</button><span id="voice-availability" role="status"></span>';card.append(tools);
  function sync(){document.querySelector('#toggle-effects').textContent=prefs.effects?'♪ 音效开':'♪ 音效关';document.querySelector('#toggle-effects').setAttribute('aria-pressed',String(prefs.effects));document.querySelector('#toggle-ghost-voice').textContent=prefs.voice?'◖ 幽灵语音开':'◖ 幽灵语音关';document.querySelector('#toggle-ghost-voice').setAttribute('aria-pressed',String(prefs.voice));}
  function cancel(){cloudController?.abort();cloudController=null;if(cloudAudio){cloudAudio.pause();cloudAudio=null;}if(cloudUrl){URL.revokeObjectURL(cloudUrl);cloudUrl=null;}clearTimeout(voiceTimer);window.speechSynthesis?.cancel();canvas.dataset.voiceSpeaking='false';}
  function quiet(){return ['speaking','listening'].includes(canvas.dataset.state)||document.querySelector('#capture-status')?.textContent==='正在聆听'||[...document.querySelectorAll('audio')].some(a=>!a.paused);}
  function unlock(){if(!armed)armed=true;if(!context)context=new AudioContext();void context.resume();}
  document.addEventListener('pointerdown',unlock);document.addEventListener('keydown',unlock);
  const notes={click:[660],nav:[440,660],pet:[520,650,780],highfive:[900,1200],sleep:[520,390,260],wake:[330,520,780],success:[523,659,784,1047],error:[240,185],record:[392,587],stop:[587,392]};
  function effect(kind){if(!prefs.effects||!armed||quiet()||!context)return;const t=context.currentTime;for(const [i,hz]of(notes[kind]||notes.click).entries()){const o=context.createOscillator(),g=context.createGain();o.type=kind==='highfive'?'triangle':'sine';o.frequency.setValueAtTime(hz,t+i*.065);g.gain.setValueAtTime(0,t+i*.065);g.gain.linearRampToValueAtTime(.045,t+i*.065+.008);g.gain.exponentialRampToValueAtTime(.0001,t+i*.065+.16);o.connect(g);g.connect(context.destination);o.start(t+i*.065);o.stop(t+i*.065+.18);o.onended=()=>{o.disconnect();g.disconnect();};}canvas.dataset.lastSound=kind;}
  async function speak(text,force=false){if(!prefs.voice||!armed||quiet()||!text)return;const now=performance.now();if(!force&&(text===lastSpoken||now-lastAt<1700))return;cancel();const voices=window.speechSynthesis?.getVoices()||[],voice=voices.find(v=>/^zh/i.test(v.lang)&&v.localService)||voices.find(v=>/^zh/i.test(v.lang));if(!voice){
      lastSpoken=text;lastAt=now;const controller=new AbortController();cloudController=controller;
      try{
        const headers={'Content-Type':'application/json','X-App-Token':document.querySelector('meta[name=app-token]').content};
        const response=await fetch('/v1/companion/speech',{method:'POST',headers,signal:controller.signal,body:JSON.stringify({user_id:'synkore-companion',text})});
        if(!response.ok)throw Error('请先配置 MiMo 语音服务');const data=await response.json();
        if(!/^\/v1\/audio\/[a-f0-9]{32}\.(wav|mp3|ogg)$/.test(data.audio_url))throw Error('语音返回无效');
        const audio=await fetch(data.audio_url,{headers:{'X-App-Token':headers['X-App-Token']},signal:controller.signal});if(!audio.ok)throw Error('语音加载失败');
        const blob=await audio.blob();if(controller.signal.aborted||quiet())return;
        cloudUrl=URL.createObjectURL(blob);cloudAudio=new Audio(cloudUrl);cloudAudio.volume=.65;
        cloudAudio.onplay=()=>{canvas.dataset.voiceSpeaking='true';canvas.dataset.lastSpoken=text;};
        cloudAudio.onended=cloudAudio.onerror=()=>{canvas.dataset.voiceSpeaking='false';};
        await cloudAudio.play();document.querySelector('#voice-availability').textContent='MiMo 中文语音';
      }catch(error){if(error.name!=='AbortError')document.querySelector('#voice-availability').textContent=error.message;}
      return;
    }lastSpoken=text;lastAt=now;const utterance=new SpeechSynthesisUtterance(text);utterance.lang=voice.lang;utterance.voice=voice;utterance.rate=1.07;utterance.pitch=1.18;utterance.volume=.65;utterance.onstart=()=>{canvas.dataset.voiceSpeaking='true';canvas.dataset.lastSpoken=text;};utterance.onend=utterance.onerror=()=>{canvas.dataset.voiceSpeaking='false';};window.speechSynthesis.speak(utterance);}
  document.addEventListener('synkore-message',event=>{clearTimeout(voiceTimer);voiceTimer=setTimeout(()=>speak(event.detail.text),100);});
  document.addEventListener('synkore-character',event=>effect(event.detail.kind));
  document.addEventListener('click',event=>{const button=event.target.closest('button');if(!button||button.disabled||button.closest('.sound-tools')||button.closest('.character-play')||button.closest('.companion-actions'))return;effect(button.matches('[data-view]')?'nav':button.id==='start-listen'?'record':button.id==='stop-listen'?'stop':'click');});
  window.addEventListener('synkore-feedback',event=>effect(event.detail.kind));
  document.querySelector('#toggle-effects').onclick=()=>{prefs.effects=!prefs.effects;sync();onChange?.({...prefs});if(prefs.effects)effect('nav');};
  document.querySelector('#toggle-ghost-voice').onclick=()=>{prefs.voice=!prefs.voice;if(!prefs.voice)cancel();sync();onChange?.({...prefs});if(prefs.voice)speak('你好，我是 synkore。很高兴陪你一起学习。',true);};
  document.querySelector('#preview-ghost-voice').onclick=()=>{unlock();effect('success');speak('你好，我是你的小幽灵。今天也一起认真听课吧。',true);};
  const observer=new MutationObserver(()=>{if(quiet())cancel();});observer.observe(canvas,{attributes:true,attributeFilter:['data-state']});
  window.addEventListener('beforeunload',()=>{cancel();void context?.close();});sync();return {effect,speak};
}
