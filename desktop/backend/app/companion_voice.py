"""Two explicitly selected MiMo companion voices; no operating-system TTS."""
import asyncio
import base64
import hashlib
import json
import re
import os
import subprocess
import imageio_ffmpeg
from pathlib import Path
from typing import Literal
import httpx
from pydantic import BaseModel, Field
from app.providers.base import ProviderError
from app.speech_accuracy import speech_matches

VOICE_PACKS={
    'gentle':{'voice':'custom-gentle','direction':'25到35岁女性的柔和女中低音普通话，音色有温暖的胸腔共鸣和极轻的气息质感，声带松弛，轻声贴近地说话，语速缓慢从容，每秒约三个字。像在安静的房间陪伴一个熟悉的朋友，笑意很淡，停顿自然，句尾轻轻落下；声音圆润、安抚、低重音。不要播音、客服或朗诵腔，不夹嗓，不夸张耳语，不制造口水音。'},
    'bright':{'voice':'custom-bright','direction':'18到25岁年轻女性的轻盈清亮普通话，较高的头腔位置，音色薄而通透，和低沉温暖的女中音明显不同。以很轻的音量、放松的气流说短句，带自然笑意和一点机灵俏皮，每秒约四个字，重音很轻，句尾偶尔微微上扬。像小伙伴轻声分享一个小发现，柔软、有呼吸感。不要尖锐高亢，不大声兴奋，不刻意卖萌，不用播音或客服腔。'},
}

def companion_payload(pack,text,anchor=None):
    audio={'format':'wav'}
    model='mimo-v2.5-tts-voicedesign'
    if anchor:
        model='mimo-v2.5-tts-voiceclone';audio['voice']='data:audio/wav;base64,'+base64.b64encode(anchor).decode('ascii')
    direction=VOICE_PACKS[pack]['direction']+'逐字准确朗读 assistant 中的原文；不添加开场白、笑声或原文没有的语气词，不漏字、不换词、不改数字。'
    if '摸摸' in text:direction+='词语“摸摸”读 mō mō，两个字都是第一声，不是“某某”；拼音提示不读出来。'
    return {'model':model,'messages':[{'role':'user','content':direction},{'role':'assistant','content':text}],'audio':audio}

class CompanionSpeechRequest(BaseModel):
    user_id:str=Field(default='synkore-companion',max_length=64,pattern=r'^[A-Za-z0-9_.-]+$')
    text:str=Field(min_length=1,max_length=100)
    pack:Literal['gentle','bright']='gentle'

class CompanionVoice:
    def __init__(self,settings,audio_dir):
        self.settings=settings;self.audio_dir=Path(audio_dir);self.lock=asyncio.Lock()
        self.index=self.audio_dir/'companion-cache-index.json'
        try:
            values=json.loads(self.index.read_text('utf-8'))
            self.owned=[s for s in values if isinstance(s,str) and re.fullmatch(r'[a-f0-9]{32}\.wav',s)] if isinstance(values,list) else []
        except (OSError,ValueError):self.owned=[]
    async def speak(self,request):
        if not self.settings.tts_api_key:raise ProviderError('请先在模型设置中填写 MiMo 密钥')
        if self.settings.tts_provider!='mimo':raise ProviderError('幽灵语音包需要 MiMo 语音服务')
        preset=VOICE_PACKS[request.pack]
        # User/key-specific filenames prevent cached speech crossing model accounts.
        key=hashlib.sha256((self.settings.tts_api_key+request.user_id+request.pack+request.text+'v1.4.2').encode()).hexdigest()[:32]
        filename=key+'.wav';dest=self.audio_dir/filename
        async with self.lock:
            if dest.exists():return '/v1/audio/'+filename
            anchor=Path(os.environ.get('COURSE_WEB_DIR',str(self.settings.root_dir/'static')))/'assets/voice16'/request.pack/'anchor.wav'
            payload=companion_payload(request.pack,request.text,anchor.read_bytes() if anchor.exists() else None)
            try:
                async with httpx.AsyncClient(timeout=65) as client:
                    response=await client.post(self.settings.tts_base_url+'/chat/completions',headers={'api-key':self.settings.tts_api_key},json=payload)
                    response.raise_for_status()
                value=base64.b64decode(response.json()['choices'][0]['message']['audio']['data'],validate=True)
                if not value.startswith(b'RIFF') or len(value)<44:raise ValueError('Invalid audio')
            except httpx.HTTPStatusError as e:
                raise ProviderError(f'MiMo 语音返回 HTTP {e.response.status_code}，请检查服务配置') from None
            except (httpx.HTTPError,ValueError,KeyError,TypeError):
                raise ProviderError('MiMo 语音暂时未能生成，请稍后再试') from None
            self.audio_dir.mkdir(parents=True,exist_ok=True)
            raw=dest.with_suffix('.raw.wav');temp=dest.with_suffix('.tmp.wav');raw.write_bytes(value)
            try:
                tempo='atempo=1.18,' if request.pack=='gentle' else ''
                await asyncio.to_thread(subprocess.run,[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-v','error','-i',str(raw),'-af',tempo+f'lowpass=f={6400 if request.pack=="gentle" else 7200},loudnorm=I=-24:LRA=6:TP=-6,afade=t=in:d=0.035','-ar','24000','-ac','1','-c:a','pcm_s16le',str(temp)],check=True,timeout=20,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=0x08000000 if os.name=='nt' else 0)
                encoded=base64.b64encode(temp.read_bytes()).decode('ascii')
                check={'model':'mimo-v2.5-asr','messages':[{'role':'user','content':[{'type':'input_audio','input_audio':{'data':'data:audio/wav;base64,'+encoded}}]}],'asr_options':{'language':'zh'}}
                async with httpx.AsyncClient(timeout=65) as client:
                    response=await client.post(self.settings.tts_base_url+'/chat/completions',headers={'api-key':self.settings.tts_api_key},json=check)
                    response.raise_for_status()
                recognized=response.json()['choices'][0]['message']['content']
                if not speech_matches(request.text,recognized):raise ProviderError('这句语音与文字核对未通过，已停止播放，请重试。')
                temp.replace(dest)
            except (OSError,subprocess.SubprocessError):raise ProviderError('语音柔化处理失败，请稍后重试') from None
            except (httpx.HTTPError,KeyError,ValueError,TypeError):raise ProviderError('语音校验服务暂不可用，已停止播报，请稍后重试。') from None
            finally:
                raw.unlink(missing_ok=True);temp.unlink(missing_ok=True)
            self.owned.append(filename)
            while len(self.owned)>80:
                old=self.owned.pop(0)
                if old!=filename:(self.audio_dir/old).unlink(missing_ok=True)
            self.index.write_text(json.dumps(self.owned),'utf-8')
            return '/v1/audio/'+filename
