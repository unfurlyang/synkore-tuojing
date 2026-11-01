"""Only for automated acceptance tests; never imported by the packaged app."""
import sys,os,io,wave,asyncio
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
os.environ['COURSE_WEB_DIR']=str(ROOT/'web')
os.environ['DATA_DIR']=str(ROOT/'test-results/server-data')
from app.config import Settings
from app.main import create_app
from app.pipeline import VoicePipeline
from app.preferences import PreferenceStore
from app.teachers import TeacherStore
from app.providers.base import AudioData

class ASR:
    name='acceptance-test';configured=True
    async def transcribe(self,*args):return '体积功等于外压乘以体积变化。'
    async def transcribe_stream(self,*args):
        yield '体积功等于外压';await asyncio.sleep(.05);yield '乘以体积变化。'
class Rewrite:
    name='acceptance-test';configured=True
    async def rewrite(self,text,*args):return text
    async def rewrite_stream(self,text,*args):
        yield text[:6];await asyncio.sleep(.05);yield text[6:]
    async def proofread(self,text,*args):return text
    async def rewrite_post_course(self,text,*args):return text
    async def distill(self,text,name):return {'language_features':['用熟悉的例子引入概念'],'teaching_structure':['先举例，再归纳'],'thinking_patterns':['从条件推向结论'],'rewrite_rules':['保留公式','先说明适用条件','再联系例子'],'avoid_features':['无关的口头禅'],'evidence':['体积功等于外压乘以体积变化。']}
class TTS:
    name='acceptance-test';configured=True
    async def synthesize(self,text):
        out=io.BytesIO()
        with wave.open(out,'wb')as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\x00\x00'*2400)
        return AudioData(content=out.getvalue(),content_type='audio/wav',extension='.wav')
    async def synthesize_stream(self,text):yield b'\x00\x00'*2400
data=Path(os.environ['DATA_DIR']);data.mkdir(parents=True,exist_ok=True)
pipeline=VoicePipeline(ASR(),Rewrite(),TTS(),PreferenceStore(data/'preferences.json'),data/'audio',TeacherStore(data/'teachers.json'),Rewrite())
app=create_app(Settings.from_env(),pipeline)
if __name__=='__main__':
    import uvicorn;uvicorn.run(app,host='127.0.0.1',port=8766,log_level='warning')
