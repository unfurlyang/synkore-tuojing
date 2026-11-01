"""Strict re-recognition gate. An ASR match is a check, never proof of pronunciation."""
import re
import unicodedata
from app.providers.base import ProviderError

def speech_key(text):
    value=unicodedata.normalize('NFKC',str(text)).lower()
    value=re.sub(r'(?<=\d)\.(?=\d)','点',value)
    value=re.sub(r'(?<![\w\u4e00-\u9fff])-(?=\d)','负',value)
    value=re.sub(r'(\d+(?:点\d+)?)%',r'百分之\1',value)
    for symbol,spoken in [('=','等于'),('+','加'),('-','减'),('×','乘'),('÷','除以'),('/','除以'),('%','百分比')]:value=value.replace(symbol,spoken)
    return ''.join(c for c in value if c.isalnum())

def speech_matches(expected,recognized):
    return bool(speech_key(expected)) and speech_key(expected)==speech_key(recognized)

class VerifiedTTS:
    """Buffer a complete sentence, then release only after matching re-recognition.

    Deliberately has no synthesize_stream: unchecked PCM must never reach playback.
    Existing pipeline emits audio_file after this verification, and keeps text on failure.
    """
    def __init__(self,tts,asr):
        self.tts,self.asr=tts,asr;self.name=tts.name;self.configured=getattr(tts,'configured',True)
    async def synthesize(self,text,*args):
        for _ in range(2):
            audio=await self.tts.synthesize(text,*args)
            if audio is None:return None
            recognized=await self.asr.transcribe(audio.content,'spoken'+audio.extension,audio.content_type)
            if speech_matches(text,recognized):return audio
        raise ProviderError('语音与文字核对未通过，已停止这段播报；文字仍可阅读，请重试。')
