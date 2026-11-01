import base64,io,wave,json
from dataclasses import replace
import httpx
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app

def test_companion_two_packs_cached_and_validated(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.delenv('LOCAL_APP_TOKEN',raising=False)
    settings=replace(Settings.from_env(),tts_provider='mimo',tts_api_key='test-only-key')
    content=io.BytesIO()
    with wave.open(content,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(bytes(4800))
    calls=[]
    def handler(request):
        payload=json.loads(request.content)
        if payload['model']=='mimo-v2.5-asr':return httpx.Response(200,json={'choices':[{'message':{'content':calls[-1]['messages'][1]['content']}}]})
        calls.append(payload)
        return httpx.Response(200,json={'choices':[{'message':{'audio':{'data':base64.b64encode(content.getvalue()).decode()}}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr('app.companion_voice.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    client=TestClient(create_app(settings))
    one=client.post('/v1/companion/speech',json={'text':'你好呀。','pack':'gentle'})
    two=client.post('/v1/companion/speech',json={'text':'你好呀。','pack':'bright'})
    again=client.post('/v1/companion/speech',json={'text':'你好呀。','pack':'gentle'})
    assert one.status_code==two.status_code==again.status_code==200
    assert one.json()['audio_url']!=two.json()['audio_url']
    assert again.json()['audio_url']==one.json()['audio_url']
    assert len(calls)==2
    assert all(p['model']=='mimo-v2.5-tts-voicedesign' for p in calls)
    assert all('voice' not in p['audio'] for p in calls)
    assert calls[0]['messages'][0]['content']!=calls[1]['messages'][0]['content']
    assert client.get(one.json()['audio_url']).content.startswith(b'RIFF')
    assert client.post('/v1/companion/speech',json={'text':'a','pack':'unknown'}).status_code==422
    assert client.post('/v1/companion/speech',json={'text':'a'*101}).status_code==422
    web=tmp_path/'web';anchor=web/'assets/voice16/gentle/anchor.wav';anchor.parent.mkdir(parents=True);anchor.write_bytes(content.getvalue())
    monkeypatch.setenv('COURSE_WEB_DIR',str(web))
    assert client.post('/v1/companion/speech',json={'text':'再说一句。','pack':'gentle'}).status_code==200
    assert calls[-1]['model']=='mimo-v2.5-tts-voiceclone'
    assert calls[-1]['audio']['voice'].startswith('data:audio/wav;base64,')

def test_companion_requires_local_token(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCAL_APP_TOKEN','local-test-token');monkeypatch.setenv('DATA_DIR',str(tmp_path))
    client=TestClient(create_app())
    assert client.post('/v1/companion/speech',json={'text':'你好'}).status_code==401
