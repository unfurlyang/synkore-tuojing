import './motion.css';
import {playIntro} from './intro.js';

const EASE='cubic-bezier(.22,.8,.24,1)';

export function initMotion({companion,initial='full',introSound=true,onChange}){
  const root=document.documentElement,media=matchMedia('(prefers-reduced-motion: reduce)');
  let level=initial==='subtle'?'subtle':'full',viewId='',revealObserver;
  const disposables=new AbortController(),options={signal:disposables.signal};
  const seen=new Set(),running=new WeakMap();
  const reduced=()=>level==='subtle'||media.matches;
  const stopIntro=playIntro({reduced:reduced(),soundEnabled:introSound});
  const animate=(node,frames,settings={})=>{
    if(!node||reduced())return;
    running.get(node)?.cancel();const animation=node.animate(frames,{duration:360,easing:EASE,...settings});running.set(node,animation);
    animation.finished.catch(()=>{}).finally(()=>{if(running.get(node)===animation)running.delete(node)});
    return animation;
  };

  const card=document.querySelector('.companion-card'),stage=document.querySelector('#ghost-stage');
  const controls=document.createElement('div');controls.className='character-play';
  controls.setAttribute('aria-label','与 synkore 互动');
  controls.innerHTML='<button type="button" data-ghost-action="pet" title="轻轻摸摸 synkore 的头">摸摸头 <span>♡</span></button><button type="button" data-ghost-action="highfive" title="和 synkore 击个掌">击个掌 <span>✧</span></button><button type="button" data-ghost-action="sleep" aria-pressed="false" title="让 synkore 休息或醒来">休息 <span>z</span></button>';
  card.querySelector('.gesture-hint').before(controls);
  controls.addEventListener('click',event=>{const button=event.target.closest('[data-ghost-action]');if(!button)return;const action=button.dataset.ghostAction;if(action==='sleep')companion.sleep();else companion.react(action);},options);
  const toggle=document.createElement('button');toggle.type='button';toggle.id='voice-pack-toggle';toggle.className='motion-toggle';toggle.setAttribute('aria-label','切换幽灵语气');
  card.querySelector('.companion-heading').insertBefore(toggle,document.querySelector('#reset-ghost'));
  const sleepButton=controls.querySelector('[data-ghost-action=sleep]');
  function applyLevel(){root.dataset.motion=reduced()?'subtle':'full';companion.setMotion(reduced()?'subtle':'full');if(reduced())document.getAnimations().filter(a=>a.effect?.target?.closest?.('.content')).forEach(a=>a.cancel());}
  media.addEventListener('change',applyLevel,options);applyLevel();

  document.querySelector('#ghost-canvas').addEventListener('synkore-character',event=>{
    const{kind,asleep}=event.detail;card.dataset.asleep=String(asleep);sleepButton.setAttribute('aria-pressed',String(asleep));sleepButton.innerHTML=asleep?'叫醒它 <span>☀</span>':'休息 <span>z</span>';
    if(kind==='pet'||kind==='success')animate(card.querySelector('.companion-message'),[{transform:'translateY(3px)',opacity:.65},{transform:'translateY(0)',opacity:1}],{duration:380});
    if(['highfive','success','pet'].includes(kind))stagePulse(kind);
  },options);
  const canvasState=new MutationObserver(()=>{card.dataset.activity=document.querySelector('#ghost-canvas').dataset.state||'idle';});
  canvasState.observe(document.querySelector('#ghost-canvas'),{attributes:true,attributeFilter:['data-state']});
  function stagePulse(kind){if(reduced())return;const pulse=document.createElement('span');pulse.className='stage-pulse';pulse.dataset.kind=kind;stage.append(pulse);const effect=pulse.animate([{transform:'translate(-50%,-50%) scale(.3)',opacity:.4},{transform:'translate(-50%,-50%) scale(1.3)',opacity:0}],{duration:950,easing:'ease-out'});effect.finished.catch(()=>{}).finally(()=>pulse.remove());}
  stage.addEventListener('pointermove',event=>{const rect=stage.getBoundingClientRect();stage.style.setProperty('--pointer-x',`${event.clientX-rect.left}px`);stage.style.setProperty('--pointer-y',`${event.clientY-rect.top}px`);},options);

  const nav=document.querySelector('.sidebar nav'),pill=document.createElement('span');pill.className='nav-motion-pill';pill.setAttribute('aria-hidden','true');nav.prepend(pill);
  function placeNav(){const selected=nav.querySelector('.active');if(selected){pill.style.height=selected.offsetHeight+'px';pill.style.transform=`translateY(${selected.offsetTop}px)`;}}
  const navResize=new ResizeObserver(placeNav);navResize.observe(nav);placeNav();
  function enterView(){
    const view=document.querySelector('.view.active');if(!view||view.id===viewId)return;viewId=view.id;root.dataset.motionView=viewId;placeNav();
    animate(document.querySelector('.page-heading'),[{opacity:.2,transform:'translateY(9px)',filter:'blur(2px)'},{opacity:1,transform:'translateY(0)',filter:'blur(0)'}],{duration:370});
    [...view.children].forEach((node,i)=>animate(node,[{opacity:0,transform:'translateY(14px)'},{opacity:1,transform:'translateY(0)'}],{duration:420,delay:i*45}));
  }
  const views=new MutationObserver(()=>requestAnimationFrame(enterView));document.querySelectorAll('.view').forEach(view=>views.observe(view,{attributes:true,attributeFilter:['class','hidden']}));
  enterView();animate(card,[{opacity:0,transform:'translateY(18px) scale(.98)'},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:550,delay:100});
  revealObserver=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;const node=entry.target;revealObserver.unobserve(node);if(node.dataset.revealed)return;node.dataset.revealed='true';animate(node,[{opacity:.2,transform:'translateY(12px)'},{opacity:1,transform:'translateY(0)'}],{duration:440});}},{threshold:.08});
  document.querySelectorAll('.session-note,.page-footer').forEach(node=>revealObserver.observe(node));

  function newlyInserted(node){
    if(node.nodeType!==1)return;
    const nodes=[...(node.matches('.result-entry,.profile-item')?[node]:[]),...node.querySelectorAll('.result-entry,.profile-item')];
    for(const entry of nodes){const key=entry.id||entry.querySelector('[data-use-profile]')?.dataset.useProfile;if(!key||seen.has(key))continue;seen.add(key);entry.dataset.motionEntered='true';animate(entry,[{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'translateY(0)'}],{duration:360});}
  }
  document.querySelectorAll('.result-entry').forEach(node=>{if(node.id)seen.add(node.id)});
  const inserted=new MutationObserver(mutations=>{for(const mutation of mutations)for(const node of mutation.addedNodes)newlyInserted(node);});
  inserted.observe(document.querySelector('.primary-column'),{childList:true,subtree:true});
  const modalObserver=new MutationObserver(mutations=>{for(const {target}of mutations)if(target.open)animate(target,[{opacity:0,transform:'translateY(14px) scale(.98)'},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:250});});
  document.querySelectorAll('dialog').forEach(node=>modalObserver.observe(node,{attributes:true,attributeFilter:['open']}));

  document.addEventListener('pointerdown',event=>{
    const button=event.target.closest('button');if(!button||button.disabled||reduced()||event.button!==0)return;
    if(!button.matches('.primary-button,.secondary-button,.companion-actions button,.character-play button,.nav-item,.strength-group button'))return;
    const rect=button.getBoundingClientRect(),ripple=document.createElement('span');ripple.className='motion-ripple';const size=Math.max(rect.width,rect.height)*1.7;
    Object.assign(ripple.style,{width:size+'px',height:size+'px',left:event.clientX-rect.left-size/2+'px',top:event.clientY-rect.top-size/2+'px'});button.append(ripple);
    ripple.animate([{transform:'scale(0)',opacity:.22},{transform:'scale(1)',opacity:0}],{duration:600,easing:'ease-out'}).finished.catch(()=>{}).finally(()=>ripple.remove());
  },options);
  document.querySelectorAll('.primary-button').forEach(button=>{
    button.addEventListener('pointermove',event=>{if(reduced()||button.disabled)return;const rect=button.getBoundingClientRect();button.style.setProperty('--button-x',clampOffset((event.clientX-rect.left-rect.width/2)*.018)+'px');button.style.setProperty('--button-y',clampOffset((event.clientY-rect.top-rect.height/2)*.045)+'px');},options);
    button.addEventListener('pointerleave',()=>{button.style.setProperty('--button-x','0px');button.style.setProperty('--button-y','0px');},options);
  });
  function clampOffset(number){return Math.max(-2,Math.min(2,number));}
  const feedback=event=>{if(event.detail?.kind==='error')companion.react('error');else if(event.detail?.kind==='success')companion.react('success');};
  window.addEventListener('synkore-feedback',feedback,options);
  return {level:()=>level,dispose(){stopIntro();disposables.abort();views.disconnect();canvasState.disconnect();inserted.disconnect();modalObserver.disconnect();revealObserver.disconnect();navResize.disconnect();}};
}
