"""One catalog, selection and text job shared by desktop and the silent T5 terminal."""
import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from app.public_catalog import COURSES, course_by_id
from app.schemas import Preference, RewriteMode
from app.teachers import teacher_style_prompt
from app.facts import check_facts, _markers


class Library:
    def __init__(self, pipeline, data_dir):
        self.pipeline = pipeline
        self.path = Path(data_dir) / 'library-state.json'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.states = json.loads(self.path.read_text('utf-8')) if self.path.exists() else {}
        self.user = 'desktop-user'
        workspace = self.path.parent.parent / 'workspace.json'
        if workspace.exists():
            self.user = json.loads(workspace.read_text('utf-8')).get('userId', self.user)
        self.link = None
        self.task = None
        self.job = None
        self.events = []

    def bind(self, user):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', user):
            raise ValueError('用户标识无效')
        return self.states.setdefault(user, {'profile_id': 'preset-songhao', 'course_id': COURSES[0]['course_id']})

    def profiles(self):
        return self.pipeline.teacher_profiles.list(self.user)

    def save(self):
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.states, ensure_ascii=False), 'utf-8')
        tmp.replace(self.path)

    def selection(self, user, profile_id=None, course_id=None):
        state = self.bind(user)
        if profile_id is not None:
            self.pipeline.teacher_profiles.get(user, profile_id)
            state['profile_id'] = profile_id
        if course_id is not None:
            if not course_by_id(course_id):
                raise ValueError('课程不存在')
            state['course_id'] = course_id
        self.user = user
        self.save()
        if self.link:
            if profile_id is not None:
                self.link.teacher_page = next((i//4 for i,p in enumerate(self.profiles()) if p.profile_id == profile_id), 0)
            if course_id is not None:
                self.link.course_page = next((i//4 for i,c in enumerate(COURSES) if c['course_id'] == course_id), 0)
            self.link.lists()
        return state.copy()

    def snapshot(self, user):
        selection = self.bind(user)
        return {'courses': COURSES, 'selection': selection, 'job': self.job if self.job and self.job['user_id'] == user else None,
                'events': [e for e in self.events if e['user_id'] == user][-20:],
                'device': {'connected': bool(self.link and self.link.connected),
                           'configured': self.link is not None,
                           'ip': self.link.ip if self.link else '',
                           'reported': self.link.report if self.link else {},
                           'version': self.link.version if self.link else ''}}

    async def rewrite(self, text, profile_id, style=None, user=None):
        p = self.pipeline.teacher_profiles.get(user or self.user, profile_id)
        prompt = teacher_style_prompt(p)
        if text.startswith('【synkore 原创导学示例：') and '\n' not in text:
            return text, []
        # Formula/quantity/condition-bearing sentences are immutable. The model only
        # edits surrounding exposition, so changing a lecture style cannot invent a new example.
        protected = {}
        parts = re.findall(r'[^。！？]+[。！？]?', text)
        masked = []
        for part in parts:
            if any(_markers(part).values()):
                token = '【SYNKORE_KEEP_' + 'A'*(len(protected)+1) + '】'
                protected[token] = part
                masked.append(token)
            else:
                masked.append(part)
        skeleton = ''.join(masked)
        prompt += ('\n硬性约束：输入中的【SYNKORE_KEEP_...】是不可改动的原句占位符，必须按原顺序各输出一次。'
                   '只重写其余中文讲解句与衔接，不得补充定义、变量、公式、例子、标题编号或新的知识。'
                   '不要解释占位符，不要使用 Markdown 或 LaTeX 改写公式。')
        if style:
            prompt += '\n表达要求：' + style
        preference = Preference(mode=RewriteMode.style, style_prompt=prompt, filter_strength='conservative')
        result = await self.pipeline.rewriter.rewrite_post_course(skeleton, preference, skeleton)
        tokens = re.findall(r'【SYNKORE_KEEP_A+】', result)
        if tokens != list(protected):
            return text, ['改写未完整保留原文的公式与条件，本段保留原文']
        for token, original in protected.items():
            result = result.replace(token, original)
        fact = check_facts(text, result, {'scope'})
        return (result, []) if fact.accepted else (text, ['为保留公式、数值与条件，本段保留原文。'])

    def start(self, user, course_id, profile_id):
        if self.task and not self.task.done():
            raise ValueError('已有课程正在转译，请等候完成或取消')
        self.selection(user, profile_id, course_id)
        course = course_by_id(course_id)
        self.job = {'id': uuid.uuid4().hex, 'user_id': user, 'course_id': course_id, 'profile_id': profile_id,
                    'title': course['title'], 'teacher': self.pipeline.teacher_profiles.get(user, profile_id).name,
                    'status': 'processing', 'progress': 0, 'original': course['text'],
                    'result': '', 'warnings': [], 'created': int(time.time()*1000)}
        self.task = asyncio.create_task(self.process(self.job))
        return self.job.copy()

    async def process(self, job):
        try:
            # Bound each call and retain paragraph order; no fabricated recognition of text inputs.
            paragraphs = job['original'].split('\n')
            results = []
            if self.link:
                self.link.emit('pet_state', value='thinking')
            for i, part in enumerate(paragraphs):
                result, warnings = await self.rewrite(part, job['profile_id'], user=job['user_id'])
                results.append(result)
                job['warnings'].extend(warnings)
                job['progress'] = int((i+1)*100/len(paragraphs))
                if self.link:
                    self.link.emit('progress', stage='导学转译', percent=job['progress'])
            job.update(status='done', result='\n\n'.join(results))
            if self.link:
                self.link.result(job['result'])
                self.link.emit('status', message='导学转译完成，完整笔记已同步电脑。')
        except asyncio.CancelledError:
            job['status'] = 'cancelled'
            raise
        except Exception:
            job.update(status='error', error='转译失败，请检查模型设置和网络后重试。')
            if self.link:
                self.link.emit('error', message=job['error'])
        finally:
            tmp = self.path.parent / 'last-library-job.tmp'
            tmp.write_text(json.dumps(job, ensure_ascii=False), 'utf-8')
            tmp.replace(self.path.parent / 'last-library-job.json')

    def cancel(self):
        if self.task and not self.task.done():
            self.task.cancel()

    async def audio(self, pcm, info):
        import io, wave, array, math
        user = info.get('_user', self.user)
        profile_id = info.get('_profile', self.bind(user)['profile_id'])
        samples = array.array('h', pcm)
        if math.sqrt(sum(x*x for x in samples)/max(1,len(samples))) < 110:
            return '声音较轻或静音，请靠近麦克风说话。'
        target = io.BytesIO()
        with wave.open(target, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
        transcript = await self.pipeline.asr.transcribe(target.getvalue(), 'board.wav', 'audio/wav')
        if info.get('mode') == 'teacher':
            profile = await self.pipeline.distill_teacher_text(user, '板上教师样本 ' + time.strftime('%H:%M'), transcript, 'board.wav')
            self.selection(user, profile.profile_id)
            result = '教师画像已建立：' + profile.name
        else:
            styles = ['正式严谨', '简明易懂', '礼貌自然', '简洁直接']
            result, _ = await self.rewrite(transcript, profile_id, styles[int(info.get('style', 0)) % 4], user=user)
        event = {'id': uuid.uuid4().hex, 'user_id': user, 'created': int(time.time()*1000), 'original': transcript, 'result': result}
        self.events.append(event)
        self.events = self.events[-40:]
        return result


def install_library(app, pipeline, settings):
    from fastapi import HTTPException, Query
    from pydantic import BaseModel, Field
    from app.device_link import DeviceLink
    library = Library(pipeline, settings.data_dir)
    app.state.library = library

    class SelectionRequest(BaseModel):
        user_id: str = Field(pattern=r'^[A-Za-z0-9_.-]{1,64}$')
        profile_id: str | None = Field(default=None, max_length=80)
        course_id: str | None = Field(default=None, max_length=80)

    @app.get('/v1/library')
    async def catalog(user_id: str = Query(pattern=r'^[A-Za-z0-9_.-]{1,64}$')):
        return library.snapshot(user_id)

    @app.put('/v1/library/selection')
    async def select(request: SelectionRequest):
        try:
            return library.selection(request.user_id, request.profile_id, request.course_id)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, '教师或课程选项无效') from exc

    @app.post('/v1/library/start')
    async def start(request: SelectionRequest):
        try:
            state = library.bind(request.user_id)
            return library.start(request.user_id, request.course_id or state['course_id'], request.profile_id or state['profile_id'])
        except (ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/v1/library/cancel')
    async def cancel():
        library.cancel()
        return {'status': 'cancelled'}

    @app.on_event('startup')
    async def startup():
        config = Path(settings.data_dir) / 'device-connection.json'
        if config.exists():
            try:
                value = json.loads(config.read_text('utf-8'))
                library.link = DeviceLink(library, value['ip'], value['token'], asyncio.get_running_loop())
                library.link.start()
            except (ValueError, KeyError, OSError):
                # A bad device configuration must never prevent the app opening.
                library.link = None

    @app.on_event('shutdown')
    async def shutdown():
        library.cancel()
        if library.link:
            library.link.stop()
