from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings

def test_local_api_token_and_ui_entry(monkeypatch,tmp_path):
    monkeypatch.setenv('DATA_DIR',str(tmp_path/'data'))
    monkeypatch.setenv('LOCAL_APP_TOKEN','desktop-test-token')
    ui=tmp_path/'web';ui.mkdir();(ui/'assets').mkdir()
    (ui/'index.html').write_text('<html><meta name="app-token" content="__LOCAL_APP_TOKEN__">synkore</html>',encoding='utf-8')
    (ui/'assets'/'ok.txt').write_text('asset',encoding='utf-8')
    monkeypatch.setenv('COURSE_WEB_DIR',str(ui))
    client=TestClient(create_app(Settings.from_env()))
    assert client.get('/v1/health').status_code==200
    assert client.get('/v1/preferences/test-user').status_code==401
    assert client.get('/v1/preferences/test-user',headers={'X-App-Token':'wrong'}).status_code==401
    assert client.get('/v1/preferences/test-user',headers={'X-App-Token':'desktop-test-token'}).status_code==200
    root=client.get('/')
    assert 'desktop-test-token' in root.text and '__LOCAL_APP_TOKEN__' not in root.text
    assert root.headers['x-content-type-options']=='nosniff'
    assert client.get('/assets/ok.txt').text=='asset'
    health=client.get('/v1/health').json()
    assert health['max_upload_bytes']==64*1024*1024
    assert not any('key' in k.lower() for k in health)
