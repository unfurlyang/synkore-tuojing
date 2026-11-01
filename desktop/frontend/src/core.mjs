export function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function clock(seconds){const n=Math.max(0,Math.floor(seconds));return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;}
export function encodeWav(samples,rate=16000){
  const result=new ArrayBuffer(44+samples.length*2),v=new DataView(result);let at=0;
  const str=(offset,text)=>{for(let i=0;i<text.length;i++)v.setUint8(offset+i,text.charCodeAt(i))};
  str(0,'RIFF');v.setUint32(4,result.byteLength-8,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,samples.length*2,true);
  for(const value of samples){const s=Math.max(-1,Math.min(1,value));v.setInt16(44+at*2,s<0?s*32768:s*32767,true);at++;}return result;
}
export async function* ndjson(response){
  if(!response.ok){let detail;try{detail=(await response.json()).detail}catch{};throw new Error(typeof detail==='string'?detail:`处理失败（${response.status}）`);}
  if(!response.body)throw Error('当前环境不支持流式返回');
  const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
  try{while(true){const{value,done}=await reader.read();pending+=decoder.decode(value||new Uint8Array(),{stream:!done});if(pending.length>4_000_000)throw Error('单条返回内容过大');let pos;while((pos=pending.indexOf('\n'))>=0){const line=pending.slice(0,pos).trim();pending=pending.slice(pos+1);if(line)yield JSON.parse(line);}if(done)break;}if(pending.trim())yield JSON.parse(pending);}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
export class VoiceSegmenter{
  constructor(rate,onSegment){this.rate=rate;this.onSegment=onSegment;this.reset();}
  reset(){this.pre=[];this.frames=[];this.speaking=false;this.elapsed=0;this.voice=0;this.silence=0;}
  push(input){const frame=new Float32Array(input),ms=frame.length/this.rate*1000;let sum=0;for(const n of frame)sum+=n*n;const rms=Math.sqrt(sum/Math.max(frame.length,1));
    this.pre.push(frame);while(this.pre.reduce((n,x)=>n+x.length,0)>this.rate*.3&&this.pre.length>1)this.pre.shift();
    if(rms>.014){if(!this.speaking){this.speaking=true;this.frames=[...this.pre];this.elapsed=this.voice=this.silence=0;}else this.frames.push(frame);this.elapsed+=ms;this.voice+=ms;this.silence=0;if(this.elapsed>=6000)this.flush();}
    else if(this.speaking){this.frames.push(frame);this.elapsed+=ms;this.silence+=ms;if((this.silence>=650&&this.voice>=300)||this.elapsed>=6000)this.flush();}return rms;
  }
  flush(){if(!this.frames.length){this.reset();return;}const parts=this.frames,size=parts.reduce((n,x)=>n+x.length,0),voice=this.voice;this.reset();if(size/this.rate<.35||voice<180)return;const data=new Float32Array(size);let i=0;for(const a of parts){data.set(a,i);i+=a.length;}this.onSegment(data,this.rate);}
}
export class PCMDecoder{
  constructor(){this.carry=null;}
  decode(bytes){let input=bytes;if(this.carry!==null){input=new Uint8Array(bytes.length+1);input[0]=this.carry;input.set(bytes,1);}this.carry=input.length%2?input[input.length-1]:null;const view=new DataView(input.buffer,input.byteOffset,input.byteLength),out=new Float32Array(Math.floor(input.length/2));for(let i=0;i<out.length;i++)out[i]=view.getInt16(i*2,true)/32768;return out;}
}
export function notesMarkdown(title,items){let text=`# ${title}\n\n`;for(const [i,item]of items.entries()){text+=`## 第 ${i+1} 段\n\n`;const original=item.corrected||item.raw;if(original)text+=`### 原文\n\n${original}\n\n`;text+=`### ${item.kind==='course'?'课后重述':'课堂重点'}\n\n${item.final||'（未生成结果）'}\n\n`;if(item.warnings?.length)text+=`> ${item.warnings.join('\n> ')}\n\n`;}return text;}
export function allowedAudioUrl(url){if(typeof url!=='string'||!/^\/v1\/audio\/[a-f0-9]{32}\.(wav|mp3|ogg)$/.test(url))return null;return url;}
