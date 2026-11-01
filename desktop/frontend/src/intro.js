import './intro.css';

/** Three seconds from display to removal, independent of model/network readiness. */
export function playIntro({reduced=false,soundEnabled=true}={}){
  const layer=document.getElementById('synkore-intro')||document.createElement('div');layer.id='synkore-intro';layer.className='synkore-intro';layer.setAttribute('role','dialog');layer.setAttribute('aria-label','synkore 入场动画');
  layer.innerHTML='<canvas aria-hidden="true"></canvas><div class="intro-brand"><img src="/assets/ghost-portrait.png" alt=""><strong>synkore</strong><span>让每一堂课，都离你近一点。</span></div><button type="button" class="intro-skip">跳过入场</button>';
  if(reduced)layer.classList.add('intro-gentle');layer.dataset.running='true';document.body.append(layer);
  let introAudio;document.documentElement.dataset.introSound=soundEnabled?'pending':'muted';
  if(soundEnabled){introAudio=new Audio('/assets/synkore-intro.wav');introAudio.volume=.48;introAudio.play().then(()=>{layer.dataset.sound='playing';document.documentElement.dataset.introSound='playing';}).catch(()=>{layer.dataset.sound='blocked';document.documentElement.dataset.introSound='blocked';});}
  const canvas=layer.querySelector('canvas'),ctx=canvas.getContext('2d');const oldFocus=document.activeElement;
  let frame,ended=false,last=0;const start=performance.now();
  function resize(){const ratio=Math.min(devicePixelRatio,1.5);canvas.width=innerWidth*ratio;canvas.height=innerHeight*ratio;ctx?.setTransform(ratio,0,0,ratio,0,0);}
  resize();window.addEventListener('resize',resize);
  const points=Array.from({length:180},(_,i)=>({angle:i*2.39996,r:.25+Math.random()*.8,size:.6+Math.random()*1.7,speed:.3+Math.random()*.7,color:i%5===0?'#cf885d':'#91a77d'}));
  function finish(){if(ended)return;ended=true;introAudio?.pause();clearTimeout(timer);cancelAnimationFrame(frame);window.removeEventListener('resize',resize);window.removeEventListener('keydown',key);const focused=layer.contains(document.activeElement);layer.remove();document.documentElement.dataset.introComplete='true';document.dispatchEvent(new Event('synkore-intro-done')); if(focused&&oldFocus?.isConnected)oldFocus.focus();}
  function key(event){if(event.code==='Escape'){event.preventDefault();event.stopPropagation();finish();}}
  window.addEventListener('keydown',key);layer.querySelector('button').onclick=finish;
  function draw(now){if(ended)return;frame=requestAnimationFrame(draw);if(now-last<32)return;last=now;const t=(now-start)/3000;if(t>=1){finish();return;}if(!ctx||reduced)return;ctx.clearRect(0,0,innerWidth,innerHeight);const radius=Math.min(innerWidth,innerHeight)*.62;
    for(const p of points){const gather=1-Math.pow(1-Math.min(t/.55,1),3),angle=p.angle+t*p.speed*.8,radiusNow=radius*p.r*(1-gather)+(.20+Math.sin(p.angle)*.035)*radius*gather;const x=innerWidth/2+Math.cos(angle)*radiusNow,y=innerHeight/2-40+Math.sin(angle)*radiusNow*.72;ctx.globalAlpha=Math.min(1,t*6)*(.35+p.speed*.5)*(t>.86?(1-t)/.14:1);ctx.fillStyle=p.color;ctx.beginPath();ctx.arc(x,y,p.size,0,Math.PI*2);ctx.fill();}
    ctx.globalAlpha=1;
  }
  const timer=setTimeout(finish,3000);frame=requestAnimationFrame(draw);
  return finish;
}
