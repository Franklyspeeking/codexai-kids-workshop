'use strict';
const $ = id => document.getElementById(id);
let key = '', selectedClass = '', catalog = null;
const msg = text => { $('message').textContent = text; };
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: {'X-Admin-Token': key, ...(options.headers || {})} });
  if (response.headers.get('content-type')?.startsWith('text/csv')) {
    if (!response.ok) throw Error('名单下载失败');
    return response.blob();
  }
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '操作失败');
  return data;
}
function button(parent, label, click, secondary=false) {
  const el=document.createElement('button');el.type='button';el.textContent=label;if(secondary)el.className='secondary';el.onclick=click;parent.append(el);return el;
}
function link(parent, label, href) {
  const el=document.createElement('a');el.textContent=label;el.href=href;el.target='_blank';el.rel='noopener noreferrer';parent.append(el);return el;
}
function cell(row, value) {const el=document.createElement('td');el.textContent=value;row.append(el);return el;}
function fillSelect(id, items, valueKey='id', textKey='title') {
  const el=$(id), keep=el.value;el.replaceChildren();
  for(const item of items){const opt=document.createElement('option');opt.value=item[valueKey];opt.textContent=item[textKey];el.append(opt);}
  if(items.some(x=>String(x[valueKey])===keep))el.value=keep;
}
async function refresh() {
  try {
    const [nextCatalog, assignments]=await Promise.all([api('/api/admin/catalog'),api('/api/admin/assignments')]);
    catalog=nextCatalog;
    $('dashboard').hidden=false;
    const classes=catalog.classes;
    if(!classes.some(x=>x.class_id===selectedClass))selectedClass=classes[0]?.class_id||'';
    fillSelect('filter-class',classes,'class_id','class_id');$('filter-class').value=selectedClass;
    fillSelect('lesson-program',catalog.programs);fillSelect('enroll-program',catalog.programs);
    renderLessons();renderAssignments(assignments.filter(x=>x.class_id===selectedClass));
    msg(selectedClass?`正在查看 ${selectedClass}，共有 ${assignments.filter(x=>x.class_id===selectedClass).length} 项课题任务。`:'请先创建一个班级。');
  } catch(error) { $('dashboard').hidden=true;msg(error.message); }
}
function renderLessons() {
  const host=$('lesson-list');host.replaceChildren();
  for(const item of catalog.lessons){
    const program=catalog.programs.find(p=>p.id===item.program_id),row=document.createElement('div');row.className='lesson';
    const name=document.createElement('div');name.textContent=`${program?.title||''} · 第 ${item.day_no} 天 · ${item.title}（${item.slug}）`;row.append(name);
    const controls=document.createElement('div');controls.className='actions';
    const state=document.createElement('span');state.className='muted';state.textContent=item.starter_available?'起始包已准备':'尚无起始包';controls.append(state);
    if(item.format==='web'){
      const picker=document.createElement('input');picker.type='file';picker.accept='.zip,application/zip';picker.setAttribute('aria-label',`给 ${item.title} 选择起始包`);controls.append(picker);
      button(controls,'上传起始包',async()=>{const file=picker.files[0];if(!file)return msg('请先选择 ZIP 起始包');try{await api(`/api/admin/lessons/${item.id}/starter`,{method:'POST',headers:{'Content-Type':'application/zip'},body:file});await refresh();msg(`${item.title} 的起始包已更新`);}catch(e){msg(e.message);}});
    }
    row.append(controls);host.append(row);
  }
}
function renderAssignments(items) {
  const host=$('rows');host.replaceChildren();
  for(const item of items){
    const tr=document.createElement('tr');
    const identity=cell(tr,`${item.code}\n${item.program_title} · 第 ${item.day_no} 天\n${item.lesson_title}`);identity.style.whiteSpace='pre-line';
    const state=cell(tr,item.status||'未提交');if(item.error){const note=document.createElement('p');note.textContent=item.error;state.append(note);}
    const actions=cell(tr,'');
    if(item.status==='待审核'){
      if(item.preview_url)link(actions,'打开预览',item.preview_url);
      button(actions,'确认发布',async()=>{if(!confirm(`已经检查 ${item.code} 的《${item.lesson_title}》，确认发布？`))return;await action(`/api/admin/publish/${item.submission_id}`);});
      button(actions,'退回修改',async()=>{const reason=prompt('告诉孩子需要修改什么：');if(!reason?.trim())return;await action(`/api/admin/reject/${item.submission_id}`,{headers:{'Content-Type':'application/json'},body:JSON.stringify({reason})});},true);
    }
    const delivery=cell(tr,'');
    if(item.url){
      link(delivery,'打开家长作品',item.url);
      button(delivery,'复制链接',async()=>{try{await navigator.clipboard.writeText(item.url);msg('已复制作品链接');}catch{msg('复制失败，请直接打开链接复制地址');}},true);
      button(delivery,'显示二维码',()=>{$('qr-image').src=item.format==='money'?`https://codexai.site/api/works/${item.code}/qr.png`:`https://codexai.site/api/projects/${item.code}/${item.lesson_slug}/qr.png`;$('qr-link').textContent=item.url;$('qr-dialog').showModal();},true);
      button(delivery,item.listed?'已在作品展 · 点击隐藏':'加入作品展',async()=>{await action(`/api/admin/visibility/${item.code}/${item.lesson_id}`,{headers:{'Content-Type':'application/json'},body:JSON.stringify({listed:!item.listed})});},true);
    }
    host.append(tr);
  }
  if(!items.length){const tr=document.createElement('tr');const td=cell(tr,'这个班级还没有课题任务。先创建班级，并给它分配课程。');td.colSpan=4;host.append(tr);}
}
async function action(path, options={}){try{await api(path,{method:'POST',...options});await refresh();}catch(error){msg(error.message);}}
function payload(value){return{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)};}
$('login').onclick=()=>{key=$('key').value.trim();$('key').value='';refresh();};
$('logout').onclick=()=>{key='';catalog=null;$('dashboard').hidden=true;msg('已退出教师工作台');};
$('create-class').onclick=async()=>{const class_id=$('class-id').value.trim().toLowerCase(),count=Number($('count').value);if(!confirm(`创建 ${count} 个学生账号？`))return;try{await api('/api/admin/classes',payload({class_id,count}));selectedClass=class_id;await refresh();msg('班级已创建。请下载名单，分别发给孩子。');}catch(e){msg(e.message);}};
$('create-program').onclick=async()=>{const value={title:$('program-title').value.trim(),slug:$('program-slug').value.trim().toLowerCase(),kind:$('program-kind').value,days:Number($('program-days').value),description:$('program-description').value.trim()};try{await api('/api/admin/programs',payload(value));await refresh();msg(`课程 ${value.title} 已创建，请继续添加课题。`);}catch(e){msg(e.message);}};
$('create-lesson').onclick=async()=>{const value={program_id:Number($('lesson-program').value),title:$('lesson-title').value.trim(),slug:$('lesson-slug').value.trim().toLowerCase(),day_no:Number($('lesson-day').value)};try{await api('/api/admin/lessons',payload(value));await refresh();msg(`课题 ${value.title} 已添加，请上传起始包。`);}catch(e){msg(e.message);}};
$('enroll').onclick=async()=>{const program_id=Number($('enroll-program').value);if(!selectedClass)return msg('请先选择班级');try{await api('/api/admin/enroll-class',payload({class_id:selectedClass,program_id}));await refresh();msg('课程已分配给全班。学生登录后即可看到。');}catch(e){msg(e.message);}};
$('filter-class').onchange=()=>{selectedClass=$('filter-class').value;refresh();};
$('refresh').onclick=refresh;
$('csv').onclick=async()=>{if(!selectedClass)return msg('请先创建班级');try{const blob=await api('/api/admin/roster.csv?class_id='+encodeURIComponent(selectedClass));const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=selectedClass+'-账号名单.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){msg(e.message);}};
$('qr-close').onclick=()=>$('qr-dialog').close();
