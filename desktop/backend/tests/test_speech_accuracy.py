import asyncio
import pytest
from app.providers.base import AudioData,ProviderError
from app.speech_accuracy import speech_matches,VerifiedTTS

def test_matching_ignores_punctuation_but_not_words_numbers_or_negation():
    assert speech_matches('你好呀，我在这里。','你好呀 我在这里！')
    assert not speech_matches('不要加热。','要加热。')
    assert not speech_matches('温度为-3。','温度为3。')
    assert not speech_matches('这是35%。','这是53%。')
    assert not speech_matches('摸摸收到了。','默默收到了。')
    assert not speech_matches('','')

def test_verified_tts_retries_mismatch_and_never_exposes_unchecked_stream():
    class TTS:
        name='test-tts';calls=0
        async def synthesize(self,text,*args):self.calls+=1;return AudioData(b'audio','audio/wav','.wav')
    class ASR:
        calls=0
        async def transcribe(self,*args):self.calls+=1;return '错误文本' if self.calls==1 else '准确文字。'
    base=TTS();gate=VerifiedTTS(base,ASR())
    assert not hasattr(gate,'synthesize_stream')
    assert asyncio.run(gate.synthesize('准确文字。')).content==b'audio'
    assert base.calls==2

def test_verified_tts_blocks_after_two_mismatches():
    class TTS:
        name='test-tts'
        async def synthesize(self,*args):return AudioData(b'audio','audio/wav','.wav')
    class ASR:
        async def transcribe(self,*args):return '这句话不对'
    with pytest.raises(ProviderError,match='核对未通过'):asyncio.run(VerifiedTTS(TTS(),ASR()).synthesize('准确文字'))
