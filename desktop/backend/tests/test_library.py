import asyncio
from dataclasses import replace
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.library import Library
from app.device_link import DeviceLink
from app.public_catalog import COURSES
from .test_teachers import make_pipeline, TRANSCRIPT

def test_presets_are_readonly_scoped_and_sourced(tmp_path):
    pipeline=make_pipeline(tmp_path)
    presets=pipeline.teacher_profiles.list('a')
    assert len(presets)==3
    assert all(p.is_preset and p.sources and not p.voice_consent for p in presets)
    assert pipeline.teacher_profiles.get('b','preset-yishu').user_id=='b'
    assert not (tmp_path/'teachers.json').exists()
    assert len(COURSES)==6 and all(c['text'].startswith('【synkore 原创导学示例') for c in COURSES)

def test_selection_persists_and_navigation_round_trips(tmp_path):
    pipeline=make_pipeline(tmp_path)
    library=Library(pipeline,tmp_path)
    loop=asyncio.new_event_loop()
    try:
        link=DeviceLink(library,'192.168.1.9','test-pairing-value',loop)
        link.connected=True;library.link=link
        library.selection('a','preset-yishu','python')
        assert link.course_page==1
        messages=[]
        while not link.out.empty():messages.append(link.out.get_nowait())
        assert any(m['op']=='course_list' and m['selected_id']=='python' and any(c['id']=='python' for c in m['items']) for m in messages)
        link.message({'op':'teacher_select','teacher_id':'preset-liyongle'})
        assert library.snapshot('a')['selection']['profile_id']=='preset-liyongle'
        link.message({'op':'course_select','course_id':'nav:course:-1'})
        assert library.snapshot('a')['selection']['course_id']=='calculus-1'
        assert Library(pipeline,tmp_path).snapshot('a')['selection']==library.snapshot('a')['selection']
    finally:loop.close()

def test_library_job_preserves_facts_and_keeps_users_separate(tmp_path):
    async def run():
        pipeline=make_pipeline(tmp_path)
        async def bad_rewrite(*args):return '错误的数值是 9999。'
        pipeline.rewriter.rewrite_post_course=bad_rewrite
        library=Library(pipeline,tmp_path)
        job=library.start('a','calculus-1','preset-songhao')
        await library.task
        actual=library.snapshot('a')['job']
        assert actual['status']=='done' and actual['progress']==100
        assert '9999' not in actual['result'] and '1/3' in actual['result']
        assert actual['warnings']
        assert library.snapshot('b')['job'] is None
        assert library.snapshot('a')['selection']['course_id']==job['course_id']
    asyncio.run(run())

def test_library_api_validates_options_and_accepts_public_profiles(tmp_path):
    pipeline=make_pipeline(tmp_path)
    settings=replace(Settings.from_env(),data_dir=tmp_path)
    with TestClient(create_app(settings,pipeline)) as client:
        data=client.get('/v1/library',params={'user_id':'a'}).json()
        assert len(data['courses'])==6
        assert 'token' not in data['device']
        assert client.put('/v1/library/selection',json={'user_id':'a','profile_id':'preset-yishu','course_id':'physics'}).status_code==200
        assert client.put('/v1/library/selection',json={'user_id':'a','course_id':'missing'}).status_code==422
        assert client.get('/v1/library',params={'user_id':'../secret'}).status_code==422

def test_math_sentences_are_immutable_while_exposition_changes(tmp_path):
    async def run():
        pipeline=make_pipeline(tmp_path)
        async def rewrite(text,*args):
            assert '(x²' not in text
            return text.replace('极限描述','先看极限：它描述')
        pipeline.rewriter.rewrite_post_course=rewrite
        library=Library(pipeline,tmp_path)
        text='极限描述函数的趋近趋势。例如 (x²−1)/(x−1) 在 x 趋于 1 时的极限为 2。不能直接把分母为零的式子当成函数值。'
        result,warnings=await library.rewrite(text,'preset-songhao')
        assert not warnings and result.startswith('先看极限：它描述')
        assert text[text.index('例如'):]==result[result.index('例如'):]
    asyncio.run(run())

def test_board_segments_stay_in_recording_order(tmp_path):
    async def run():
        library=Library(make_pipeline(tmp_path),tmp_path)
        link=DeviceLink(library,'192.168.1.9','test-pairing-value',asyncio.get_running_loop())
        link.connected=True;library.link=link
        order=[]
        async def audio(pcm,info):
            await asyncio.sleep(.02 if pcm==b'aa' else 0)
            order.append(pcm)
            return '识别结果'
        library.audio=audio
        link.submit_audio(b'aa',{'mode':'live'},link.connection)
        link.submit_audio(b'bb',{'mode':'live'},link.connection)
        await asyncio.gather(*link.audio_tasks)
        assert order==[b'aa',b'bb']
    asyncio.run(run())
