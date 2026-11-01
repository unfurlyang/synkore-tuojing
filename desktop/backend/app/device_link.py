"""Authenticated LAN client. Network thread owns socket; app loop owns all model jobs."""
import asyncio
import ipaddress
import json
import queue
import select
import socket
import struct
import threading
import time
from app.public_catalog import COURSES

HEADER = struct.Struct('!4sB3xI')

def recv_exact(sock, size):
    out = bytearray()
    while len(out) < size:
        part = sock.recv(size-len(out))
        if not part:
            raise ConnectionError('disconnected')
        out.extend(part)
    return bytes(out)

def recv_frame(sock):
    magic, kind, size = HEADER.unpack(recv_exact(sock, 12))
    if magic != b'T5VT' or kind not in (1,2) or size > (8192 if kind == 1 else 640000):
        raise ValueError('invalid frame')
    return kind, recv_exact(sock, size)

def send_json(sock, message):
    data = json.dumps(message, ensure_ascii=False).encode('utf-8')
    if len(data) > 8192:
        raise ValueError('control size')
    sock.sendall(HEADER.pack(b'T5VT', 1, len(data)) + data)

class DeviceLink:
    def __init__(self, library, ip, token, loop):
        address = ipaddress.ip_address(ip)
        if address.version != 4 or not address.is_private or address.is_loopback:
            raise ValueError('LAN IPv4 required')
        if not isinstance(token, str) or not 8 <= len(token) <= 128:
            raise ValueError('pairing token invalid')
        self.library, self.ip, self.token, self.loop = library, str(address), token, loop
        self.connected = False
        self.version = ''
        self.out = queue.Queue(maxsize=128)
        self.stop_event = threading.Event()
        self.audio_tasks = set()
        self.audio_lock = asyncio.Lock()
        self.pages = []
        self.teacher_page = 0
        self.course_page = 0
        self.connection = 0
        self.sock = None
        self.report = {}

    def start(self):
        threading.Thread(target=self.run, name='synkore-device', daemon=True).start()

    def stop(self):
        self.stop_event.set()
        if self.sock:
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        for task in list(self.audio_tasks): task.cancel()

    def emit(self, op, **fields):
        if not self.connected: return
        try: self.out.put_nowait({'op': op, **fields})
        except queue.Full: self.connected = False

    def result(self, text):
        self.pages = [text[i:i+300] for i in range(0,len(text),300)] or ['未识别到有效内容，请再试一次。']
        self.emit('result', text=self.pages[0], page=0, total_pages=len(self.pages))
        self.emit('pet_state', value='success')

    def menu(self, items, kind, selected):
        # Four real entries + two navigation entries fit the original six-item firmware menu.
        page = getattr(self, kind+'_page')
        maximum = max(0,(len(items)-1)//4)
        page = max(0,min(page,maximum))
        setattr(self,kind+'_page',page)
        visible = items[page*4:page*4+4]
        label = 'name' if kind == 'teacher' else 'title'
        if page: visible = visible + [{'id':'nav:'+kind+':-1', label:'‹ 上一组'}]
        if page < maximum: visible = visible + [{'id':'nav:'+kind+':1', label:'下一组 ›'}]
        self.emit(kind+'_list', items=visible, selected_id=selected)

    def lists(self):
        state = self.library.bind(self.library.user)
        self.menu([{'id':p.profile_id,'name':p.name[:24]} for p in self.library.profiles()], 'teacher', state['profile_id'])
        self.menu([{'id':c['course_id'],'title':c['title']} for c in COURSES], 'course', state['course_id'])
        self.emit('get_catalog_state')

    def choose(self, kind, value):
        if value.startswith('nav:'):
            parts=value.split(':')
            if len(parts)!=3 or parts[1]!=kind or parts[2] not in ('1','-1'): return
            items = self.library.profiles() if kind=='teacher' else COURSES
            page = max(0,min(getattr(self,kind+'_page')+int(parts[2]),(len(items)-1)//4))
            setattr(self,kind+'_page',page)
            value = items[page*4].profile_id if kind=='teacher' else items[page*4]['course_id']
        if kind == 'teacher': self.library.selection(self.library.user, profile_id=value)
        else: self.library.selection(self.library.user, course_id=value)

    def message(self, message):
        try:
            op=message.get('op')
            if op=='catalog_state':
                self.report = {k: message.get(k) for k in ('rotation','teacher_id','course_id')}
            elif op=='mode': self.lists()
            elif op=='teacher_select': self.choose('teacher', message.get('teacher_id',''))
            elif op=='course_select': self.choose('course', message.get('course_id',''))
            elif op=='course_action':
                value=message.get('job_id','')
                if value.startswith('nav:'):
                    self.choose('course',value); return
                state=self.library.bind(self.library.user)
                self.library.start(self.library.user, value or state['course_id'], state['profile_id'])
            elif op=='cancel':
                self.library.cancel()
                for task in list(self.audio_tasks): task.cancel()
                self.emit('pet_state',value='idle'); self.emit('status',message='已取消，完整记录仍在电脑。')
            elif op=='get_result':
                page=int(message.get('page',0))
                if 0<=page<len(self.pages): self.emit('result',text=self.pages[page],page=page,total_pages=len(self.pages))
        except (ValueError, KeyError, IndexError):
            self.emit('error',message='选项无效或已有任务正在运行，请稍后重试。')

    def submit_audio(self, pcm, info, connection):
        if connection != self.connection or not self.connected: return
        if len(self.audio_tasks)>=2:
            self.emit('stop'); self.emit('status',message='电脑正在处理，已暂停听课，请稍后继续。'); return
        info={**info, '_user': self.library.user,
              '_profile': self.library.bind(self.library.user)['profile_id']}
        task=asyncio.create_task(self.process_audio(pcm,info,connection))
        self.audio_tasks.add(task); task.add_done_callback(self.audio_tasks.discard)

    async def process_audio(self, pcm, info, connection):
        try:
            async with self.audio_lock:
                if not self.connected or connection!=self.connection: return
                self.emit('pet_state',value='thinking')
                text=await self.library.audio(pcm,info)
            if self.connected and connection==self.connection:
                self.lists(); self.result(text); self.emit('status',message='结果已同步电脑，点击翻页查看。')
        except asyncio.CancelledError: raise
        except Exception:
            self.emit('error',message='语音处理失败，请检查模型设置和网络。')

    def run(self):
        while not self.stop_event.is_set():
            try:
                with socket.create_connection((self.ip,8765),timeout=5) as sock:
                    self.sock=sock; sock.settimeout(8)
                    send_json(sock,{'op':'hello','token':self.token})
                    kind,data=recv_frame(sock); hello=json.loads(data)
                    if kind!=1 or hello.get('op')!='hello' or hello.get('protocol',1)!=1: raise ValueError('handshake')
                    while not self.out.empty(): self.out.get_nowait()
                    self.version=str(hello.get('version','')); self.connection+=1; self.connected=True
                    self.loop.call_soon_threadsafe(self.lists)
                    self.emit('status',message='synkore 已连接，教师和课程与电脑同步。')
                    info=None; pcm=None; ping=last_rx=time.monotonic()
                    while self.connected and not self.stop_event.is_set():
                        while not self.out.empty(): send_json(sock,self.out.get_nowait())
                        now=time.monotonic()
                        if now-ping>5: send_json(sock,{'op':'ping'}); ping=now
                        if now-last_rx>18: raise TimeoutError('heartbeat')
                        if not select.select([sock],[],[],.1)[0]: continue
                        kind,data=recv_frame(sock); last_rx=time.monotonic()
                        if kind==2:
                            if info is None or len(data)!=info['bytes'] or len(data)%2: raise ValueError('PCM sequence')
                            pcm=data
                        else:
                            message=json.loads(data); op=message.get('op')
                            if op=='audio':
                                if info is not None or message.get('rate')!=16000 or not 0<int(message.get('bytes',0))<=640000: raise ValueError('PCM format')
                                info=message; pcm=None
                            elif op=='audio_end':
                                if info is None or pcm is None: raise ValueError('PCM missing')
                                self.loop.call_soon_threadsafe(self.submit_audio,pcm,info,self.connection)
                                info=None; pcm=None
                            else: self.loop.call_soon_threadsafe(self.message,message)
            except (OSError,ValueError,KeyError,TypeError):
                pass
            finally:
                self.connected=False; self.sock=None; self.connection+=1
            self.stop_event.wait(2)
