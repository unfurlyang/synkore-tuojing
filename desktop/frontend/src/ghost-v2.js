import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';

const clamp=THREE.MathUtils.clamp;
const ACTIVE=new Set(['listening','thinking','speaking']);
const POSE_DURATION={greet:1.6,pet:1.7,highfive:1.8,wink:1.0,success:1.5,error:1.5,wake:1.2};

/** Runtime gestures are layered over business state; a pet never starts a recording. */
export class GhostCompanion{
  constructor(canvas,onReaction){
    this.canvas=canvas;this.onReaction=onReaction;this.state='idle';this.energy=0;
    this.pointer={x:0,y:0};this.turn=0;this.pitch=0;this.velocity=0;this.spin=0;
    this.pose=null;this.asleep=false;this.motionLevel='full';this.nextBlink=2.7;
    this.blinkAt=-100;this.lastInput=performance.now();this.lastFrame=0;
    this.media=matchMedia('(prefers-reduced-motion: reduce)');this.events=new AbortController();
    try{this.init();}catch(error){this.fallback(error);}
  }
  get reduced(){return this.media.matches||this.motionLevel==='subtle';}
  setMotion(level){this.motionLevel=level==='subtle'?'subtle':'full';this.velocity=0;this.canvas.dataset.motion=this.reduced?'subtle':'full';if(this.reduced)this.clearParticles();}
  fallback(error){document.querySelector('#model-loading').hidden=true;document.querySelector('#ghost-fallback').hidden=false;this.canvas.hidden=true;this.error=String(error);}
  init(){
    this.scene=new THREE.Scene();this.camera=new THREE.PerspectiveCamera(32,1,.1,60);
    this.camera.position.set(0,.25,6.9);this.camera.lookAt(0,-.04,0);
    this.renderer=new THREE.WebGLRenderer({canvas:this.canvas,alpha:true,antialias:true,powerPreference:'low-power'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));this.renderer.setClearColor(0,0);
    this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=.95;
    const pmrem=new THREE.PMREMGenerator(this.renderer),room=new RoomEnvironment();
    this.env=pmrem.fromScene(room,.04);this.scene.environment=this.env.texture;room.dispose();pmrem.dispose();
    this.scene.environmentIntensity=.65;this.scene.add(new THREE.HemisphereLight(0xf9fff0,0x7f8a77,.9));
    const key=new THREE.DirectionalLight(0xfff5df,2.2);key.position.set(-3,5,5);this.scene.add(key);
    const rim=new THREE.DirectionalLight(0xd9edc6,1.3);rim.position.set(4,2,-2);this.scene.add(rim);
    this.pivot=new THREE.Group();this.scene.add(this.pivot);
    const shadowCanvas=document.createElement('canvas');shadowCanvas.width=shadowCanvas.height=128;
    const ctx=shadowCanvas.getContext('2d'),gradient=ctx.createRadialGradient(64,64,1,64,64,60);
    gradient.addColorStop(0,'rgba(59,78,43,.24)');gradient.addColorStop(1,'rgba(59,78,43,0)');ctx.fillStyle=gradient;ctx.fillRect(0,0,128,128);
    this.shadow=new THREE.Mesh(new THREE.PlaneGeometry(3,1),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(shadowCanvas),transparent:true,depthWrite:false}));
    this.shadow.rotation.x=-Math.PI/2;this.shadow.position.set(0,-1.52,0);this.scene.add(this.shadow);
    this.raycaster=new THREE.Raycaster();this.parts={};this.particles=[];
    this.createParticlePool();this.createHand();this.createSleepSign();
    new GLTFLoader().load('/assets/ghost.glb',gltf=>{
      gltf.scene.updateMatrixWorld(true);const meshes=[];gltf.scene.traverse(object=>{if(object.isMesh)meshes.push(object)});
      for(const mesh of meshes){
        mesh.geometry=mesh.geometry.clone();mesh.geometry.applyMatrix4(mesh.matrixWorld);mesh.position.set(0,0,0);mesh.quaternion.identity();mesh.scale.setScalar(1);
        mesh.geometry.computeBoundingBox();const center=mesh.geometry.boundingBox.getCenter(new THREE.Vector3());mesh.geometry.translate(-center.x,-center.y,-center.z);mesh.position.copy(center);
        mesh.userData.rest=center.clone();mesh.material=mesh.material.clone();this.pivot.add(mesh);this.parts[mesh.name]=mesh;
      }
      this.createCheeks();this.pivot.rotation.y=-.28;this.loaded=true;this.canvas.dataset.meshCount=String(meshes.length);
    },undefined,error=>this.fallback(error));
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(this.canvas.parentElement);this.resize();
    this.bindInputs();this.start=performance.now();this.visible=!document.hidden;this.animate();
  }
  createCheeks(){
    const geometry=new THREE.SphereGeometry(.105,20,12);
    this.cheeks=[-1,1].map(side=>{const material=new THREE.MeshStandardMaterial({color:'#e3a18c',transparent:true,opacity:0,roughness:.7});const cheek=new THREE.Mesh(geometry,material);cheek.scale.set(1,.45,.10);cheek.position.set(side*.55,-.015,.451);this.pivot.add(cheek);return cheek;});
  }
  createHand(){
    this.hand=new THREE.Group();this.hand.visible=false;this.hand.position.set(1.15,-.05,.15);this.pivot.add(this.hand);
    const material=new THREE.MeshStandardMaterial({color:'#eeeae0',roughness:.4});
    const palm=new THREE.Mesh(new THREE.SphereGeometry(.18,20,12),material);palm.scale.set(.8,1,.45);this.hand.add(palm);
    for(let i=0;i<4;i++){const finger=new THREE.Mesh(new THREE.CapsuleGeometry(.033,.13,4,12),material);finger.position.set((i-1.5)*.073,.18+(i===0||i===3?-.035:0),0);finger.rotation.z=(1.5-i)*.15;this.hand.add(finger);}
    const thumb=new THREE.Mesh(new THREE.CapsuleGeometry(.045,.08,4,12),material);thumb.position.set(-.16,.015,0);thumb.rotation.z=-.65;this.hand.add(thumb);
  }
  makeSpriteTexture(kind){
    const canvas=document.createElement('canvas');canvas.width=canvas.height=64;const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';
    if(kind==='heart'){ctx.beginPath();ctx.moveTo(32,51);ctx.bezierCurveTo(-7,27,13,2,32,20);ctx.bezierCurveTo(51,2,71,27,32,51);ctx.fill();}
    else if(kind==='z'){ctx.font='500 38px Georgia';ctx.textAlign='center';ctx.fillText('z',32,47);}
    else{ctx.beginPath();for(let i=0;i<8;i++){const a=i*Math.PI/4-Math.PI/2,r=i%2?7:27;const x=32+Math.cos(a)*r,y=32+Math.sin(a)*r;i?ctx.lineTo(x,y):ctx.moveTo(x,y);}ctx.closePath();ctx.fill();}
    return new THREE.CanvasTexture(canvas);
  }
  createParticlePool(){
    this.starTexture=this.makeSpriteTexture('star');this.heartTexture=this.makeSpriteTexture('heart');
    for(let i=0;i<24;i++){const material=new THREE.SpriteMaterial({map:this.starTexture,color:'#c98b4f',transparent:true,opacity:0,depthWrite:false});const sprite=new THREE.Sprite(material);sprite.visible=false;this.scene.add(sprite);this.particles.push({sprite,life:0,duration:1,v:new THREE.Vector3()});}
  }
  createSleepSign(){this.sleepSigns=[];this.zTexture=this.makeSpriteTexture('z');for(let i=0;i<3;i++){const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:this.zTexture,color:'#8e9d77',transparent:true,opacity:0,depthWrite:false}));sprite.scale.setScalar(.18+i*.025);this.scene.add(sprite);this.sleepSigns.push(sprite);}}
  burst(kind='star',count=12){
    if(this.reduced)return;
    let available=this.particles.filter(p=>p.life<=0);for(const particle of available.slice(0,count)){
      particle.life=particle.duration=1.0+Math.random()*.6;particle.sprite.visible=true;
      particle.sprite.material.map=kind==='heart'?this.heartTexture:this.starTexture;particle.sprite.material.color.set(kind==='heart'?'#d49c83':['#c49a62','#9fb486','#dcc99d'][Math.floor(Math.random()*3)]);
      particle.sprite.material.rotation=Math.random()*Math.PI;particle.sprite.position.set((Math.random()-.5)*1.2,.25+Math.random()*.6,.7);
      const size=.07+Math.random()*.08;particle.sprite.scale.setScalar(size);particle.v.set((Math.random()-.5)*1.8,.7+Math.random()*.8,.1+Math.random()*.35);
    }
    this.canvas.dataset.bursts=String((Number(this.canvas.dataset.bursts)||0)+1);
  }
  clearParticles(){for(const particle of this.particles||[]){particle.life=0;particle.sprite.visible=false;}}
  bindInputs(){
    const options={signal:this.events.signal};
    window.addEventListener('pointermove',event=>{const rect=this.canvas.getBoundingClientRect();this.pointer.x=clamp((event.clientX-rect.left-rect.width/2)/Math.max(rect.width/2,1),-1,1);this.pointer.y=clamp((event.clientY-rect.top-rect.height/2)/Math.max(rect.height/2,1),-1,1);},options);
    window.addEventListener('pointerdown',()=>{this.lastInput=performance.now();},options);
    window.addEventListener('keydown',()=>{this.lastInput=performance.now();},options);
    this.canvas.addEventListener('pointerenter',()=>{this.lastInput=performance.now();this.canvas.parentElement.classList.add('is-engaged');},options);
    this.canvas.addEventListener('pointerleave',()=>{this.canvas.parentElement.classList.remove('is-engaged');this.canvas.dataset.hoverPart='';},options);
    this.canvas.addEventListener('pointerdown',event=>{
      if(!this.loaded)return;this.lastInput=performance.now();if(this.asleep)this.sleep(false);
      this.drag={x:event.clientX,y:event.clientY,lastX:event.clientX,lastTime:performance.now(),yaw:this.turn,pitch:this.pitch,v:0,hit:this.hit(event)};
      this.velocity=0;this.spin=0;this.canvas.setPointerCapture(event.pointerId);
      clearTimeout(this.pressTimer);this.pressTimer=setTimeout(()=>{if(this.drag){this.drag.held=true;this.react('pet');}},550);
    },options);
    this.canvas.addEventListener('pointermove',event=>{
      if(this.drag&&Math.hypot(event.clientX-this.drag.x,event.clientY-this.drag.y)>8)clearTimeout(this.pressTimer);
      if(this.drag){const now=performance.now(),dt=Math.max(8,now-this.drag.lastTime);this.turn=this.drag.yaw+(event.clientX-this.drag.x)*.012;this.pitch=clamp(this.drag.pitch+(event.clientY-this.drag.y)*.004,-.22,.22);this.drag.v=(event.clientX-this.drag.lastX)*.012/(dt/1000);this.drag.lastX=event.clientX;this.drag.lastTime=now;this.canvas.dataset.dragged='true';}
      else if(performance.now()-(this.lastHit||0)>90){this.lastHit=performance.now();this.canvas.dataset.hoverPart=this.hit(event)||'';}
    },options);
    this.canvas.addEventListener('pointerup',event=>{
      clearTimeout(this.pressTimer);if(!this.drag)return;if(this.drag.held){this.drag=null;if(this.canvas.hasPointerCapture(event.pointerId))this.canvas.releasePointerCapture(event.pointerId);return;}const moved=Math.hypot(event.clientX-this.drag.x,event.clientY-this.drag.y);
      if(moved<8){const hit=this.drag.hit;if(hit?.startsWith('Eye'))this.react('wink');else if(hit==='Ghost_body'&&this.pointer.y<-.3)this.react('pet');else if(hit)this.react('greet');}
      else{this.velocity=this.reduced?0:clamp(this.drag.v,-3.5,3.5);this.canvas.dataset.interaction='drag';}
      this.drag=null;if(this.canvas.hasPointerCapture(event.pointerId))this.canvas.releasePointerCapture(event.pointerId);
    },options);
    this.canvas.addEventListener('pointercancel',()=>{clearTimeout(this.pressTimer);this.drag=null;this.velocity=0;},options);
    this.canvas.addEventListener('contextmenu',event=>{event.preventDefault();this.react('wink');},options);
    this.canvas.addEventListener('dblclick',event=>{event.preventDefault();this.react('success');},options);
    this.canvas.addEventListener('keydown',event=>{
      if(['Space','Enter'].includes(event.code)){event.preventDefault();event.stopPropagation();this.react('greet');}
      if(event.code==='ArrowLeft'||event.code==='ArrowRight'){event.preventDefault();this.turn+=(event.code==='ArrowLeft'?-1:1)*.35;this.canvas.dataset.interaction='rotate';}
    },options);
    document.addEventListener('visibilitychange',()=>{this.visible=!document.hidden;this.lastFrame=0;},options);
  }
  hit(event){const rect=this.canvas.getBoundingClientRect();this.raycaster.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1),this.camera);return this.raycaster.intersectObjects(Object.values(this.parts),false)[0]?.object.name||null;}
  resize(){const {width,height}=this.canvas.parentElement.getBoundingClientRect();if(!width||!height)return;this.renderer.setSize(width,height,false);this.camera.aspect=width/height;this.camera.updateProjectionMatrix();}
  setState(state){if(this.state===state)return;this.state=state;this.canvas.dataset.state=state;if(ACTIVE.has(state)&&this.asleep)this.sleep(false);}
  setEnergy(level){this.energy=clamp(level*12,0,1);}
  react(kind='greet'){
    if(!this.loaded){this.onReaction?.(kind);return;}
    if(this.asleep)this.sleep(false);this.lastInput=performance.now();this.pose={kind,start:performance.now(),duration:POSE_DURATION[kind]||1.5};
    this.canvas.dataset.interaction=kind;this.canvas.dataset.reactions=String((Number(this.canvas.dataset.reactions)||0)+1);
    if(kind==='success')window.dispatchEvent(new Event('synkore-confetti'));
    if(kind==='pet')this.burst('heart',9);else if(['highfive','success'].includes(kind))this.burst('star',14);
    this.onReaction?.(kind);this.emit(kind);
  }
  emit(kind){this.canvas.dispatchEvent(new CustomEvent('synkore-character',{bubbles:true,detail:{kind,asleep:this.asleep}}));}
  greet(){this.react('greet');}
  rotate(){this.lastInput=performance.now();if(this.asleep)this.sleep(false);if(this.reduced)this.turn+=Math.PI/2;else this.spin+=Math.PI*2;this.canvas.dataset.interaction='rotate';this.emit('rotate');}
  reset(){this.turn=0;this.pitch=0;this.velocity=0;this.spin=0;this.sleep(false);this.react('greet');}
  sleep(value=!this.asleep){if(value&&ACTIVE.has(this.state))return;this.asleep=Boolean(value);this.lastInput=performance.now();this.canvas.dataset.asleep=String(this.asleep);if(!value)this.pose={kind:'wake',start:performance.now(),duration:1.2};this.onReaction?.(value?'sleep':'wake');this.emit(value?'sleep':'wake');}
  animate=()=>{
    this.frame=requestAnimationFrame(this.animate);if(!this.visible)return;
    const now=performance.now();if(now-this.lastFrame<1000/(this.reduced?15:30))return;
    const dt=this.lastFrame?Math.min((now-this.lastFrame)/1000,.08):.033;this.lastFrame=now;const t=(now-this.start)/1000;
    if(this.loaded){
      if(this.state==='idle'&&!this.asleep&&now-this.lastInput>60000)this.sleep(true);
      if(t>this.nextBlink){this.blinkAt=t;this.nextBlink=t+3+Math.random()*4;}
      const blink=t-this.blinkAt;let eyes=blink>=0&&blink<.20?Math.max(.065,Math.abs(blink-.1)*10):1;
      const pose=this.pose,age=pose?(now-pose.start)/1000:99;const activePose=pose&&age<pose.duration?pose.kind:null;
      if(pose&&age>=pose.duration)this.pose=null;
      const progress=activePose?age/pose.duration:0,pulse=activePose?Math.sin(progress*Math.PI):0;
      let bounce=0,roll=0,squash=1,mouthX=1,mouthY=1;
      if(!this.reduced){
        if(['greet','wake'].includes(activePose)){bounce=pulse*.20;roll=Math.sin(progress*Math.PI*3)*.08;}
        if(activePose==='pet'){bounce=-pulse*.09;squash=1-pulse*.065;eyes=.10;mouthX=1+pulse*.16;}
        if(activePose==='highfive'){bounce=pulse*.12;roll=-pulse*.09;}
        if(activePose==='success'){bounce=Math.abs(Math.sin(progress*Math.PI*2))*.15;eyes=.18;mouthX=1.15;}
        if(activePose==='error'){roll=Math.sin(progress*Math.PI*5)*.045;mouthX=.48;mouthY=.35;}
      }
      if(this.asleep){eyes=.065;mouthX=.55;mouthY=.45;}
      if(this.reduced&&activePose==='pet')eyes=.15;
      if(!this.drag&&!this.reduced){this.turn+=this.velocity*dt;this.velocity*=Math.exp(-6*dt);}
      const thinking=this.state==='thinking',listening=this.state==='listening',speaking=this.state==='speaking'||this.canvas.dataset.voiceSpeaking==='true';
      const float=this.reduced?0:Math.sin(t*(this.asleep?.85:1.5))*.055;
      this.pivot.position.y=float+bounce+(listening&&!this.reduced?this.energy*.018:0);
      const yaw=this.turn+this.spin-.28+(this.reduced||this.asleep?0:this.pointer.x*.13)+(thinking&&!this.reduced?Math.sin(t*1.8)*.06:0);
      const blend=1-Math.exp(-dt*8);
      this.pivot.rotation.y+=(yaw-this.pivot.rotation.y)*blend;
      this.pivot.rotation.x+=((this.pitch+(this.asleep?.10:0)+(thinking?-.035:0))-this.pivot.rotation.x)*blend;
      this.pivot.rotation.z+=((this.reduced?0:Math.sin(t)*.019)+roll+(thinking?-.065:0)-this.pivot.rotation.z)*blend;
      this.pivot.scale.set(1+(1-squash)*.5,squash,1);this.shadow.scale.setScalar(1-Math.max(bounce,0)*.3);this.shadow.material.opacity=1-Math.max(bounce,0)*.7;
      for(const name of ['Eye_L','Eye_R']){const eye=this.parts[name];if(!eye)continue;eye.scale.y=activePose==='wink'&&name==='Eye_L'?.07:eyes*(listening?1.06:1);eye.position.x=eye.userData.rest.x+(this.reduced||this.asleep?0:this.pointer.x*.028);eye.position.y=eye.userData.rest.y+(this.reduced||this.asleep?0:-this.pointer.y*.022);}
      const mouth=this.parts.Smile;if(mouth){mouth.scale.x=thinking?.72:mouthX;mouth.scale.y=speaking?1+(this.canvas.dataset.voiceSpeaking==='true'?Math.abs(Math.sin(t*12))*.5:this.energy*.9):mouthY;}
      this.cheeks?.forEach(cheek=>cheek.material.opacity=activePose==='pet'?pulse*.65:activePose==='success'?pulse*.35:0);
      this.hand.visible=activePose==='highfive';if(this.hand.visible){this.hand.position.set(1.14,.10+pulse*.55,.25+pulse*.3);this.hand.rotation.z=-.35+Math.sin(progress*Math.PI*3)*.18;this.hand.scale.setScalar(this.reduced?.9:Math.min(1,Math.sin(progress*Math.PI)*2));}
      for(let i=0;i<3;i++){const led=this.parts['LED_'+i];if(!led)continue;led.material.emissive.set(ACTIVE.has(this.state)?'#d48a42':'#000000');led.material.emissiveIntensity=ACTIVE.has(this.state)?(.30+(this.reduced?0:Math.sin(t*4-i)*.22)+this.energy*.2):0;}
      for(const [i,sign]of this.sleepSigns.entries()){const phase=(t*.38+i*.33)%1;sign.visible=this.asleep&&!this.reduced;sign.position.set(.72+phase*.45,1.0+phase*.7,.45);sign.material.opacity=sign.visible?Math.sin(phase*Math.PI)*.7:0;}
    }
    for(const particle of this.particles){if(particle.life<=0)continue;particle.life-=dt;particle.sprite.position.addScaledVector(particle.v,dt);particle.v.y-=dt*.65;particle.sprite.material.opacity=Math.max(0,particle.life/particle.duration)*.85;particle.sprite.material.rotation+=dt*.5;if(particle.life<=0)particle.sprite.visible=false;}
    this.energy*=Math.exp(-dt*6);this.renderer.render(this.scene,this.camera);
    if(this.loaded&&this.renderer.info.render.calls>2){this.canvas.dataset.loaded='true';this.canvas.dataset.renderCalls=String(this.renderer.info.render.calls);document.querySelector('#model-loading').hidden=true;}
  }
  dispose(){cancelAnimationFrame(this.frame);this.events.abort();this.resizeObserver?.disconnect();this.env?.dispose();const geometries=new Set(),materials=new Set();this.scene?.traverse(object=>{if(object.geometry)geometries.add(object.geometry);for(const material of object.material?(Array.isArray(object.material)?object.material:[object.material]):[])materials.add(material);});geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());this.starTexture?.dispose();this.heartTexture?.dispose();this.zTexture?.dispose();this.shadow?.material.map?.dispose();this.renderer?.dispose();}
}
