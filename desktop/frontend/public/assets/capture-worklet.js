class CaptureProcessor extends AudioWorkletProcessor{
  constructor(){super();this.frames=new Float32Array(2048);this.at=0;}
  process(inputs){const channels=inputs[0];if(!channels?.length)return true;const size=channels[0].length;for(let i=0;i<size;i++){let sample=0;for(const c of channels)sample+=c[i];this.frames[this.at++]=sample/channels.length;if(this.at===this.frames.length){const frame=this.frames;this.frames=new Float32Array(2048);this.at=0;this.port.postMessage(frame,[frame.buffer]);}}return true;}
}
registerProcessor('tingjian-capture',CaptureProcessor);
