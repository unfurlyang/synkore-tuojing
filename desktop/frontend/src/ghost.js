import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {RoomEnvironment} from 'three/addons/environments/RoomEnvironment.js';

export class GhostCompanion{
  constructor(canvas,onGreet){
    this.canvas=canvas;this.onGreet=onGreet;this.state='idle';this.energy=0;this.pointer={x:0,y:0};this.spin=0;this.turn=0;this.bounceAt=-100;this.nextBlink=3;this.blinkAt=-100;this.reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    try{this.init();}catch(error){this.fallback(error);}
  }
  fallback(error){document.querySelector('#model-loading').hidden=true;document.querySelector('#ghost-fallback').hidden=false;this.canvas.hidden=true;this.error=String(error);}
  init(){
    this.scene=new THREE.Scene();this.camera=new THREE.PerspectiveCamera(32,1,.1,60);this.camera.position.set(0,.25,6.9);this.camera.lookAt(0,-.04,0);
    this.renderer=new THREE.WebGLRenderer({canvas:this.canvas,alpha:true,antialias:true,powerPreference:'low-power'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));this.renderer.setClearColor(0,0);this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=.95;
    const pmrem=new THREE.PMREMGenerator(this.renderer),room=new RoomEnvironment();this.env=pmrem.fromScene(room,.04);this.scene.environment=this.env.texture;room.dispose();pmrem.dispose();
    this.scene.environmentIntensity=.65;this.scene.add(new THREE.HemisphereLight(0xf9fff0,0x7f8a77,.9));
    const key=new THREE.DirectionalLight(0xfff5df,2.2);key.position.set(-3,5,5);this.scene.add(key);
    const rim=new THREE.DirectionalLight(0xd9edc6,1.3);rim.position.set(4,2,-2);this.scene.add(rim);
    this.pivot=new THREE.Group();this.scene.add(this.pivot);
    const textureCanvas=document.createElement('canvas');textureCanvas.width=textureCanvas.height=128;const ctx=textureCanvas.getContext('2d'),g=ctx.createRadialGradient(64,64,1,64,64,60);g.addColorStop(0,'rgba(59,78,43,.23)');g.addColorStop(1,'rgba(59,78,43,0)');ctx.fillStyle=g;ctx.fillRect(0,0,128,128);
    this.shadow=new THREE.Mesh(new THREE.PlaneGeometry(3,1),new THREE.MeshBasicMaterial({map:new THREE.CanvasTexture(textureCanvas),transparent:true,depthWrite:false}));this.shadow.rotation.x=-Math.PI/2;this.shadow.position.set(0,-1.52,0);this.scene.add(this.shadow);
    new GLTFLoader().load('/assets/ghost.glb',gltf=>{
      gltf.scene.updateMatrixWorld(true);const meshes=[];gltf.scene.traverse(o=>{if(o.isMesh)meshes.push(o)});
      this.parts={};for(const mesh of meshes){mesh.geometry=mesh.geometry.clone();mesh.geometry.applyMatrix4(mesh.matrixWorld);mesh.position.set(0,0,0);mesh.quaternion.identity();mesh.scale.setScalar(1);mesh.geometry.computeBoundingBox();const center=mesh.geometry.boundingBox.getCenter(new THREE.Vector3());mesh.geometry.translate(-center.x,-center.y,-center.z);mesh.position.copy(center);mesh.userData.rest=center.clone();this.pivot.add(mesh);this.parts[mesh.name]=mesh;mesh.material=mesh.material.clone();}
      this.pivot.rotation.y=-.28;this.pivot.rotation.z=.035;this.loaded=true;this.canvas.dataset.meshCount=String(meshes.length);
    },undefined,e=>this.fallback(e));
    this.resizeObserver=new ResizeObserver(()=>this.resize());this.resizeObserver.observe(this.canvas.parentElement);this.resize();
    window.addEventListener('pointermove',e=>{const r=this.canvas.getBoundingClientRect();this.pointer.x=Math.max(-1,Math.min(1,(e.clientX-r.left-r.width/2)/Math.max(r.width,1)));this.pointer.y=Math.max(-1,Math.min(1,(e.clientY-r.top-r.height/2)/Math.max(r.height,1)));});
    this.canvas.addEventListener('pointerdown',e=>{this.drag={x:e.clientX,start:e.clientX,yaw:this.turn};this.canvas.setPointerCapture(e.pointerId);});
    this.canvas.addEventListener('pointermove',e=>{if(this.drag)this.turn=this.drag.yaw+(e.clientX-this.drag.x)*.012;});
    this.canvas.addEventListener('pointerup',e=>{if(this.drag&&Math.abs(e.clientX-this.drag.start)<7)this.greet();this.drag=null;});
    this.canvas.addEventListener('pointercancel',()=>this.drag=null);
    this.canvas.addEventListener('keydown',e=>{if(e.code==='Space'||e.code==='Enter'){e.preventDefault();e.stopPropagation();this.greet();}});
    this.start=performance.now();this.last=0;this.visible=true;document.addEventListener('visibilitychange',()=>{this.visible=!document.hidden});this.animate();
  }
  resize(){const {width,height}=this.canvas.parentElement.getBoundingClientRect();this.renderer.setSize(width,height,false);this.camera.aspect=width/height;this.camera.updateProjectionMatrix();}
  setState(state){this.state=state;this.canvas.dataset.state=state;}
  setEnergy(level){this.energy=Math.min(1,Math.max(0,level*12));}
  greet(){this.bounceAt=(performance.now()-this.start)/1000;this.blinkAt=this.bounceAt+.22;this.onGreet?.();}
  rotate(){if(this.reduced){this.turn+=Math.PI/2}else this.spin+=Math.PI*2;}
  reset(){this.turn=0;this.spin=0;this.pointer={x:0,y:0};this.greet();}
  animate=()=>{
    this.frame=requestAnimationFrame(this.animate);if(!this.visible)return;const now=performance.now();if(now-this.last<1000/(this.reduced?12:30))return;this.last=now;const t=(now-this.start)/1000;
    if(this.loaded){
      if(t>this.nextBlink){this.blinkAt=t;this.nextBlink=t+3+Math.random()*4;}
      const blink=t-this.blinkAt,eyeScale=blink>=0&&blink<.2?Math.max(.07,Math.abs(blink-.1)*10):1;
      const happy=t-this.bounceAt,dance=happy>=0&&happy<1.1?Math.sin(happy*Math.PI/1.1)*.27:0;
      this.pivot.position.y=(this.reduced?0:Math.sin(t*1.5)*.065)+dance;
      const thinking=this.state==='thinking';const targetYaw=this.turn-.28+(this.reduced?0:this.pointer.x*.16)+(thinking?Math.sin(t*2)*.08:0);
      this.pivot.rotation.y+=(targetYaw+this.spin-this.pivot.rotation.y)*.075;
      this.pivot.rotation.z+=((this.reduced?0:Math.sin(t)*.024)+(thinking?-.09:0)-this.pivot.rotation.z)*.08;
      this.shadow.scale.setScalar(1-dance*.25);this.shadow.material.opacity=1-dance*.6;
      for(const name of ['Eye_L','Eye_R']){const eye=this.parts[name];if(!eye)continue;eye.scale.y=eyeScale*(this.state==='listening'?1.1:1);eye.position.x=eye.userData.rest.x+(this.reduced?0:this.pointer.x*.025);eye.position.y=eye.userData.rest.y+(this.reduced?0:-this.pointer.y*.02);}
      const mouth=this.parts.Smile;if(mouth){mouth.scale.y=this.state==='speaking'?1+Math.abs(Math.sin(t*13))*.8:1;mouth.scale.x=this.state==='thinking'?.7:1;}
      for(let i=0;i<3;i++){const led=this.parts['LED_'+i];if(!led)continue;const active=this.state==='listening'||thinking||this.state==='speaking';led.material.emissive.set(active?'#d48a42':'#000000');led.material.emissiveIntensity=active?.35+Math.sin(t*4-i)*.25+this.energy*.3:0;}
    }
    this.energy*=.92;this.renderer.render(this.scene,this.camera);
    if(this.loaded&&this.renderer.info.render.calls>2){this.canvas.dataset.loaded='true';this.canvas.dataset.renderCalls=String(this.renderer.info.render.calls);document.querySelector('#model-loading').hidden=true;}
  }
  dispose(){cancelAnimationFrame(this.frame);this.resizeObserver?.disconnect();this.env?.dispose();this.scene?.traverse(o=>{o.geometry?.dispose();if(o.material){for(const m of Array.isArray(o.material)?o.material:[o.material])m.dispose();}});this.renderer?.dispose();}
}
