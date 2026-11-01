export class AppError extends Error { constructor(message,status=400){super(message);this.status=status;} }
export const uuid=()=>crypto.randomUUID().replaceAll('-','');
export const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'}});
export function text(value,max=12000,min=1){if(typeof value!=='string'||value.trim().length<min||value.length>max)throw new AppError(`请输入 ${min}–${max} 字的有效内容`,422);return value.trim();}
export function b64(bytes){let s='';for(let i=0;i<bytes.length;i+=16384)s+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(s);}
export function unb64(value){if(typeof value!=='string'||value.length>18000000)throw new AppError('模型音频格式无效',502);return Uint8Array.from(atob(value),c=>c.charCodeAt(0));}
export function normalizeSpeech(value){return value.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]/gu,'');}
export function markers(s){return [...s.matchAll(/[-+]?\d+(?:\.\d+)?(?:[%％])?|\b[A-Za-z][A-Za-z0-9_]*\b|不能|不会|不要|没有|未必|不一定|至少|最多|不超过|不|未|无|可能|预计|大概|建议/g)].map(m=>m[0]).sort();}
export function sameFacts(a,b){return JSON.stringify(markers(a))===JSON.stringify(markers(b));}
export function protectSentences(input){const saved={};let i=0;const masked=(input.match(/[^。！？]+[。！？]?/g)||[input]).map(part=>{if(markers(part).length){const token=`【SYNKORE_KEEP_${'A'.repeat(++i)}】`;saved[token]=part;return token;}return part;}).join('');return {masked,saved};}
export function restoreSentences(candidate,saved){const tokens=candidate.match(/【SYNKORE_KEEP_A+】/g)||[];if(JSON.stringify(tokens)!==JSON.stringify(Object.keys(saved)))throw new AppError('未完整保留原句');for(const [token,s]of Object.entries(saved))candidate=candidate.replace(token,s);return candidate;}
export function wavPcm(bytes){
 if(bytes.length<44||bytes.length>10000000)throw new AppError('在线音频最多 5 分钟，请使用桌面 App 处理长课',413);
 const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),ascii=(i,n)=>String.fromCharCode(...bytes.subarray(i,i+n));
 if(ascii(0,4)!=='RIFF'||ascii(8,4)!=='WAVE')throw new AppError('请使用浏览器转换后的 WAV 音频',415);
 let fmt=false,pcm;
 for(let i=12;i+8<=bytes.length;){const size=v.getUint32(i+4,true);if(i+8+size>bytes.length)throw new AppError('音频文件不完整',422);
  if(ascii(i,4)==='fmt '){if(size<16||v.getUint16(i+8,true)!==1||v.getUint16(i+10,true)!==1||v.getUint32(i+12,true)!==16000||v.getUint16(i+22,true)!==16)throw new AppError('需要 16kHz 单声道 PCM16 音频',415);fmt=true;}
  if(ascii(i,4)==='data')pcm=bytes.subarray(i+8,i+8+size);i+=8+size+(size%2);
 }
 if(!fmt||!pcm?.length||pcm.length%2||pcm.length>9600000)throw new AppError('音频为空、损坏或超过 5 分钟',422);return pcm;
}
export function encodeWav(pcm){const bytes=new Uint8Array(44+pcm.length),v=new DataView(bytes.buffer);for(const [s,o]of [['RIFF',0],['WAVEfmt ',8],['data',36]])for(let i=0;i<s.length;i++)bytes[o+i]=s.charCodeAt(i);v.setUint32(4,bytes.length-8,true);v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);v.setUint32(40,pcm.length,true);bytes.set(pcm,44);return bytes;}
export function wavChunks(bytes,seconds=90){const pcm=wavPcm(bytes),parts=[];for(let i=0;i<pcm.length;i+=seconds*32000)parts.push(encodeWav(pcm.subarray(i,i+seconds*32000)));return parts;}
export function ndjsonStream(run){const enc=new TextEncoder();return new Response(new ReadableStream({async start(controller){let closed=false;const emit=data=>{if(!closed)try{controller.enqueue(enc.encode(JSON.stringify(data)+'\n'));}catch{closed=true;}};try{await run(emit);}catch(e){emit({type:'error',detail:e instanceof AppError?e.message:'本次处理未完成，请稍后重试。'});}finally{if(!closed)controller.close();}}}),{headers:{'Content-Type':'application/x-ndjson; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});}
