import {escapeHtml as esc} from './core.mjs';
import './library.css';

export function openSource(url){
  if(window.desktop?.openSource)return window.desktop.openSource(url);
  window.open(url,'_blank','noopener,noreferrer');
}

export function initLibrary({userId,json,toast,setProfile,onCourse,onBoardResult,refreshProfiles}){
  const $=id=>document.getElementById(id);
  const host=document.createElement('section');host.className='library-strip';
  host.innerHTML=`<div class="library-top"><div><p class="eyebrow">A SMALL STUDY LIBRARY</p><h3>从一门熟悉的课开始</h3></div><span id="device-sync" role="status">正在连接课程库…</span></div><div class="library-choices"><label>课程<select id="library-course" aria-label="选择常见课程"></select></label><button id="library-source" class="text-link">查看公开课程 ↗</button></div><p id="library-topics" class="library-topics"></p><details class="library-preview"><summary>预览原创导学讲稿</summary><p id="library-text"></p></details><div class="library-bottom"><p>内置内容为 synkore 原创导学示例，非完整课程录音。也可继续上传自己的整节课。</p><button id="library-start" class="secondary-button">转译这份导学</button></div><div id="library-job" class="library-job" hidden><span id="library-job-text"></span><progress id="library-job-progress" max="100" value="0"></progress><button id="library-cancel" class="text-link">取消</button></div>`;
  $('course-drop').before(host);
  let courses=[],pending=0,polling=false,lastCourse='',lastTeachers='',stopped=false;
  let lastJob='',lastStatus='';
  const seenBoard=new Set();
  const preview=()=>{const c=courses.find(c=>c.course_id===$('library-course').value);if(c){$('library-topics').textContent=c.topics.join(' / ');$('library-text').textContent=c.text;}};
  async function select(fields){pending++;try{await json('/v1/library/selection',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,...fields})});}catch(e){toast(e.message,true);}finally{pending--;void poll();}}
  $('library-course').onchange=()=>{preview();void select({course_id:$('library-course').value});};
  $('library-source').onclick=()=>{const c=courses.find(c=>c.course_id===$('library-course').value);if(c)void openSource(c.source_url);};
  $('library-start').onclick=async()=>{try{await json('/v1/library/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,course_id:$('library-course').value,profile_id:$('course-profile').value||null})});void poll();}catch(e){toast(e.message,true);}};
  $('library-cancel').onclick=async()=>{await json('/v1/library/cancel',{method:'POST'});void poll();};
  async function poll(){
    if(stopped||polling||pending)return;polling=true;
    try{
      const data=await json('/v1/library?user_id='+encodeURIComponent(userId));
      if(pending)return;
      const signature=data.courses.map(c=>c.course_id).join();
      if(signature!==lastCourse){courses=data.courses;lastCourse=signature;$('library-course').innerHTML=courses.map(c=>`<option value="${esc(c.course_id)}">${esc(c.title)}</option>`).join('');}
      $('library-course').value=data.selection.course_id;preview();setProfile(data.selection.profile_id);
      $('device-sync').textContent=data.device.connected?`开发板已同步 · ${data.device.version}`:data.device.configured?'开发板重连中 · 课程库可用':(window.SYNKORE_CLOUD?'云端课程库 · 硬件请用桌面版':'本机课程库 · 开发板未配置');
      $('device-sync').classList.toggle('connected',data.device.connected);
      const job=data.job;
      const busy=job?.status==='processing';$('library-start').disabled=busy;$('library-job').hidden=!job;
      if(job){$('library-job-progress').value=job.progress;$('library-cancel').hidden=!busy;
        $('library-job-text').textContent=job.title+' · '+({processing:`正在转译 ${job.progress}%`,done:'已完成 · 笔记已同步',cancelled:'已取消',error:job.error}[job.status]||job.status);
        if(job.status==='done'&&lastJob!==job.id){lastJob=job.id;onCourse(job);toast('课程导学转译完成，已同步到笔记。');}
        if(job.status==='error'&&lastStatus!==job.id){lastStatus=job.id;toast(job.error,true);}
      }
      for(const event of data.events||[])if(!seenBoard.has(event.id)){seenBoard.add(event.id);onBoardResult(event);}
      // Board-created profiles are reflected without reloading the page or resetting the active form.
      const teachers=await json('/v1/teachers?user_id='+encodeURIComponent(userId));
      const teacherSignature=teachers.items.map(p=>p.profile_id).join();
      if(teacherSignature!==lastTeachers){lastTeachers=teacherSignature;await refreshProfiles();setProfile(data.selection.profile_id);}
    }catch{$('device-sync').textContent='课程库暂未连接，正在重试';}finally{polling=false;}
  }
  void poll();const timer=setInterval(()=>void poll(),1500);
  window.addEventListener('pagehide',()=>{stopped=true;clearInterval(timer);},{once:true});
  return {selectProfile:id=>id?select({profile_id:id}):Promise.resolve()};
}
