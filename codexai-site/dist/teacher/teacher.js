'use strict';
const $ = id => document.getElementById(id);
let key = '', selectedClass = '', catalog = null, consents = [], leads = [], assignments = [], freeWorks = [], siteContent = null, collections = [], events = [];
const msg = text => { $('message').textContent = text; };
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: {'X-Admin-Token': key, ...(options.headers || {})} });
  if (response.headers.get('content-type')?.startsWith('text/csv')) {
    if (!response.ok) throw Error('名单下载失败');
    return response.blob();
  }
  const data = await response.json().catch(()=>{throw Error('暂时连不上教师服务，请检查网络后重试。');});
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
    const [nextCatalog, nextAssignments, slots, nextFreeWorks, nextConsents, nextLeads, nextSiteContent, nextCollections, nextEvents]=await Promise.all([
      api('/api/admin/catalog'),api('/api/admin/assignments'),api('/api/admin/slots'),
      api('/api/admin/independent'),api('/api/admin/consents'),api('/api/admin/consultations'),
      api('/api/admin/site-content'),api('/api/admin/collections'),api('/api/admin/publication-events')]);
    catalog=nextCatalog;
    assignments=nextAssignments;
    freeWorks=nextFreeWorks;
    consents=nextConsents;
    leads=nextLeads;
    siteContent=nextSiteContent;
    collections=nextCollections;
    events=nextEvents;
    $('dashboard').hidden=false;
    const classes=catalog.classes;
    if(!classes.some(x=>x.class_id===selectedClass))selectedClass=classes[0]?.class_id||'';
    fillSelect('filter-class',classes,'class_id','class_id');$('filter-class').value=selectedClass;
    fillSelect('lesson-program',catalog.programs);fillSelect('enroll-program',catalog.programs);
    fillSelect('marketing-program',catalog.programs);
    fillSelect('collection-program',catalog.programs.filter(x=>x.kind==='camp'));
    fillSelect('lesson-filter',[{id:'',title:'全部课题'},...catalog.lessons]);
    fillSelect('free-filter',[{category:'',title:'全部类别'},...[...new Set(freeWorks.filter(x=>x.code.startsWith(selectedClass+'-')).map(x=>x.category))].map(category=>({category,title:category}))],'category','title');
    fillSelect('enroll-student-program',catalog.programs);
    fillSelect('enroll-student',slots.filter(x=>x.class_id===selectedClass),'code','code');
    renderLessons();renderMarketing();renderSiteContent();renderCollections();renderAssignments(assignments.filter(x=>x.class_id===selectedClass));
    renderFree(freeWorks.filter(x=>x.code.startsWith(selectedClass+'-')));renderConsents();renderLeads();renderOverview();
    msg(selectedClass?`正在查看 ${selectedClass}，共有 ${assignments.filter(x=>x.class_id===selectedClass).length} 项课题任务。`:'请先创建一个班级。');
  } catch(error) { $('dashboard').hidden=true;msg(error.message); }
}
function renderCollectionStudents(){
  const programId=Number($('collection-program').value);
  const codes=[...new Set(assignments.filter(x=>x.program_id===programId&&x.class_id===selectedClass).map(x=>x.code))];
  fillSelect('collection-student',codes.map(code=>({code})),'code','code');
}
function renderCollections(){
  renderCollectionStudents();
  const host=$('collection-list');host.replaceChildren();
  for(const item of collections.filter(x=>x.code.startsWith(selectedClass+'-'))){
    const row=document.createElement('div');row.className='lesson';
    const name=document.createElement('span');name.textContent=`${item.code} · ${item.program_title} · ${item.active?'链接有效':'已撤销'}`;row.append(name);
    if(item.url){link(row,'打开作品集',item.url);button(row,'复制链接',async()=>{
      try{await navigator.clipboard.writeText(item.url);msg('作品集链接已复制。');}catch{msg('复制失败，请打开链接后复制地址。');}
    },true);}
    button(row,item.active?'撤销作品集链接':'重新生成链接',async()=>{
      if(item.active&&!confirm('撤销后旧作品集链接会失效，确定继续？'))return;
      await action('/api/admin/collections',payload({code:item.code,program_id:item.program_id,active:!item.active}));
    },true);
    host.append(row);
  }
  if(!host.children.length){const empty=document.createElement('p');empty.className='muted';empty.textContent='当前班级还没有营期作品集。';host.append(empty);}
}
function faqRow(q='',a=''){
  const row=document.createElement('div');row.className='faq-row';
  const question=document.createElement('label');question.textContent='问题';
  const qInput=document.createElement('input');qInput.className='faq-question';qInput.value=q;qInput.maxLength=160;question.append(qInput);row.append(question);
  const answer=document.createElement('label');answer.textContent='回答';
  const aInput=document.createElement('textarea');aInput.className='faq-answer';aInput.value=a;aInput.maxLength=600;aInput.rows=2;answer.append(aInput);row.append(answer);
  button(row,'删除',()=>row.remove(),true);$('faq-editor').append(row);
}
function renderSiteContent(){
  $('teacher-intro').value=siteContent.teacher_intro||'';
  $('demo-title').value=siteContent.demo_title||'';
  $('demo-summary').value=siteContent.demo_summary||'';
  $('faq-editor').replaceChildren();
  for(const item of siteContent.faqs||[])faqRow(item.q,item.a);
  $('wechat-qr-preview').hidden=!siteContent.wechat_qr_available;
  if(siteContent.wechat_qr_available)$('wechat-qr-preview').src='/api/public/wechat-qr?v='+Date.now();
}
function renderMarketing(){
  const program=catalog.programs.find(x=>String(x.id)===$('marketing-program').value);
  if(!program)return;
  $('marketing-status').value=program.marketing_status||'draft';
  for(const name of ['summary','audience','outcome','duration','parent_role']){
    $('marketing-'+name.replace('_','-')).value=program['marketing_'+name]||'';
  }
  $('marketing-preview').href=`https://codexai.site/courses/${program.slug==='workshop01'?'money':program.slug}/`;
  $('marketing-preview').hidden=program.marketing_status==='draft'||program.marketing_status==='archived';
}
function renderOverview(){
  const host=$('overview');host.replaceChildren();
  const pending=assignments.filter(x=>x.status==='待审核').length+freeWorks.filter(x=>x.status==='待审核').length;
  const cards=[['待审核作品',pending],['待跟进咨询',leads.filter(x=>x.status==='新咨询').length],
    ['家长分享中、未公开',assignments.filter(x=>x.published_at&&!x.listed).length+freeWorks.filter(x=>x.published_submission_id&&!x.listed).length],
    ['已发布作品',assignments.filter(x=>x.published_at).length+freeWorks.filter(x=>x.published_submission_id).length]];
  for(const [name,count] of cards){const p=document.createElement('p');p.textContent=`${name}：${count}`;host.append(p);}
  const recent=$('recent-events');recent.replaceChildren();
  for(const item of events.filter(x=>x.code.startsWith(selectedClass+'-')).slice(0,5)){
    const p=document.createElement('p');p.className='muted';p.textContent=`${item.created_at.slice(0,16).replace('T',' ')} · ${item.code} · ${item.title} · ${item.action}`;recent.append(p);
  }
  if(!recent.children.length){const p=document.createElement('p');p.className='muted';p.textContent='这个班级还没有发布记录。';recent.append(p);}
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
  const filter=$('review-filter').value,lesson=$('lesson-filter').value;
  for(const item of items.filter(x=>(!filter||(x.status||'未提交')===filter)&&(!lesson||String(x.lesson_id)===lesson))){
    const tr=document.createElement('tr');
    const identity=cell(tr,`${item.code}\n${item.program_title} · 第 ${item.day_no} 天\n${item.lesson_title}`);identity.style.whiteSpace='pre-line';
    const state=cell(tr,item.status||'未提交');if(item.error){const note=document.createElement('p');note.textContent=item.error;state.append(note);}
    const actions=cell(tr,'');
    button(actions,'查看版本',()=>showVersions(item.code,'course',item.lesson_id),true);
    if(item.status==='待审核'){
      if(item.preview_url)link(actions,'打开预览',item.preview_url);
      button(actions,'确认发布',async()=>{if(!confirm(`已经检查 ${item.code} 的《${item.lesson_title}》，确认发布？`))return;await action(`/api/admin/publish/${item.submission_id}`);});
      button(actions,'退回修改',async()=>{const reason=prompt('告诉孩子需要修改什么：');if(!reason?.trim())return;await action(`/api/admin/reject/${item.submission_id}`,{headers:{'Content-Type':'application/json'},body:JSON.stringify({reason})});},true);
    }
    const delivery=cell(tr,'');
    if(item.published_at){
      if(item.url)link(delivery,'打开家长作品',item.url);
      if(item.url){
      button(delivery,'复制链接',async()=>{try{await navigator.clipboard.writeText(item.url);msg('已复制作品链接');}catch{msg('复制失败，请直接打开链接复制地址');}},true);
      button(delivery,'显示二维码',()=>{showQr(item.qr,item.url);},true);
      }
      button(delivery,item.url?'撤销分享':'重新生成分享链接',async()=>{
        if(item.url&&!confirm('撤销后原链接和二维码会立即失效，确定继续？'))return;
        await action(`/api/admin/course/${item.lesson_id}/share`,payload({code:item.code,active:!item.url}));
      },true);
      if(item.url)button(delivery,'登记家长同意',()=>openConsent(item.code,item.lesson_id,null,item.lesson_title),true);
      button(delivery,item.listed?'已在作品展 · 点击隐藏':'加入作品展',async()=>{await action(`/api/admin/visibility/${item.code}/${item.lesson_id}`,{headers:{'Content-Type':'application/json'},body:JSON.stringify({listed:!item.listed})});},true);
    }
    host.append(tr);
  }
  if(!items.length){const tr=document.createElement('tr');const td=cell(tr,'这个班级还没有课题任务。先创建班级，并给它分配课程。');td.colSpan=4;host.append(tr);}
}
function showQr(qr,url){$('qr-image').src=qr;$('qr-link').textContent=url;$('qr-dialog').showModal();}
async function showVersions(code,kind,id){
  try{
    const versions=await api(`/api/admin/versions?code=${encodeURIComponent(code)}&kind=${kind}&id=${id}`);
    const host=$('versions-list');host.replaceChildren();
    for(const version of versions){
      const row=document.createElement('div');row.className='lesson';
      const title=document.createElement('div');title.textContent=`#${version.id} · ${version.status} · ${version.received_at}${version.error?' · '+version.error:''}`;row.append(title);
      if(version.preview_url)link(row,'预览',version.preview_url);
      if(version.status==='已发布')button(row,'回退到此版',async()=>{
        if(!confirm(`把 ${code} 的家长作品回退到版本 #${version.id}？公开作品展会先下架。`))return;
        try{await api(`/api/admin/rollback/${version.id}`,{method:'POST'});$('versions-dialog').close();await refresh();msg(`已回退到版本 #${version.id}。`);}catch(error){msg(error.message);}
      },true);
      host.append(row);
    }
    if(!versions.length){const empty=document.createElement('p');empty.textContent='暂无版本。';host.append(empty);}
    $('versions-dialog').showModal();
  }catch(error){msg(error.message);}
}
function openConsent(code,lessonId,freeId,title){
  $('consent-code').value=code;$('consent-lesson').value=lessonId||'';$('consent-free').value=freeId||'';
  $('consent-work').textContent=`${code} · ${title}`;$('consent-date').value=new Date().toISOString().slice(0,10);
  $('consent-dialog').showModal();
}
function renderFree(items){
  const host=$('free-rows');host.replaceChildren();
  const category=$('free-filter').value;
  for(const item of items.filter(x=>!category||x.category===category)){
    const tr=document.createElement('tr');
    const identity=cell(tr,`${item.code}\n${item.title}\n${item.category} · ${item.summary}`);identity.style.whiteSpace='pre-line';
    const state=cell(tr,item.status||'尚未上传');if(item.error){const p=document.createElement('p');p.textContent=item.error;state.append(p);}
    const review=cell(tr,'');
    button(review,'查看版本',()=>showVersions(item.code,'independent',item.id),true);
    if(item.status==='待审核'){
      if(item.preview_url)link(review,'打开预览',item.preview_url);
      button(review,'确认发布',async()=>{if(!confirm(`已检查 ${item.code} 的《${item.title}》，确认发布？`))return;await action(`/api/admin/publish/${item.submission_id}`);});
      button(review,'退回修改',async()=>{const reason=prompt('告诉孩子需要修改什么：');if(!reason?.trim())return;await action(`/api/admin/reject/${item.submission_id}`,payload({reason}));},true);
    }
    const delivery=cell(tr,'');
    if(item.published_submission_id){
      if(item.url){
        link(delivery,'打开作品',item.url);
        button(delivery,'复制链接',async()=>{try{await navigator.clipboard.writeText(item.url);msg('已复制作品链接');}catch{msg('复制失败，请打开作品后复制地址');}},true);
        button(delivery,'二维码',()=>showQr(item.qr,item.url),true);
        button(delivery,'登记家长同意',()=>openConsent(item.code,null,item.id,item.title),true);
      }
      button(delivery,item.url?'撤销分享':'重新生成分享链接',async()=>{
        if(item.url&&!confirm('撤销后原链接和二维码会立即失效，确定继续？'))return;
        await action(`/api/admin/independent/${item.id}/share`,payload({active:!item.url}));
      },true);
      button(delivery,item.listed?'从作品展移除':'加入作品展',async()=>{
        await action(`/api/admin/independent/${item.id}/visibility`,payload({listed:!item.listed}));
      },true);
    }
    host.append(tr);
  }
  if(!items.length){const tr=document.createElement('tr'),td=cell(tr,'这个班级还没有自由创作作品。');td.colSpan=4;host.append(tr);}
}
function renderConsents(){
  const host=$('consent-list');host.replaceChildren();
  for(const item of consents.filter(x=>x.code.startsWith(selectedClass+'-'))){
    const row=document.createElement('div');row.className='lesson';
    const note=document.createElement('div');
    note.textContent=`${item.code} · ${item.lesson_id?'课程课题 '+item.lesson_id:'自由作品 '+item.independent_id} · ${item.guardian_ref} · ${item.consent_at} · ${item.channel} · 凭据：${item.evidence_ref}${item.revoked_at?' · 已撤回':''}`;
    row.append(note);
    if(!item.revoked_at)button(row,'登记撤回',async()=>{
      if(!confirm('确认家长已撤回公开展示同意？作品会从公开展移除。'))return;
      await action(`/api/admin/consents/${item.id}/revoke`);
    },true);
    host.append(row);
  }
  if(!host.children.length){const p=document.createElement('p');p.className='muted';p.textContent='当前班级尚无公开展示同意记录。';host.append(p);}
}
function renderLeads(){
  const host=$('lead-rows'),filter=$('lead-filter').value,source=$('source-filter').value;host.replaceChildren();
  const sourceSelect=$('source-filter');sourceSelect.replaceChildren();
  const all=document.createElement('option');all.value='';all.textContent='全部来源';sourceSelect.append(all);
  for(const value of [...new Set(leads.map(x=>x.source||'直接访问'))].sort()){
    const option=document.createElement('option');option.value=value;option.textContent=value;sourceSelect.append(option);
  }
  sourceSelect.value=source;
  for(const item of leads.filter(x=>(!filter||x.status===filter)&&(!source||(x.source||'直接访问')===source))){
    const tr=document.createElement('tr');
    const where=cell(tr,`${item.created_at.slice(0,16).replace('T',' ')}\n${item.source||'直接访问'}\n${item.entry_path}`);where.style.whiteSpace='pre-line';
    const detail=cell(tr,`${item.parent_name} · ${item.contact_kind} ${item.contact}\n孩子年龄：${item.child_age}\n感兴趣：${item.interest}${item.message?'\n留言：'+item.message:''}`);detail.style.whiteSpace='pre-line';
    const follow=cell(tr,'');
    const status=document.createElement('select');
    for(const value of ['新咨询','已联系','已约体验','已报名','暂不跟进']){
      const option=document.createElement('option');option.value=value;option.textContent=value;status.append(option);
    }
    status.value=item.status;status.setAttribute('aria-label',`${item.parent_name} 的跟进状态`);follow.append(status);
    const note=document.createElement('input');note.value=item.note;note.maxLength=500;note.placeholder='跟进备注';note.setAttribute('aria-label',`${item.parent_name} 的跟进备注`);follow.append(note);
    button(follow,'保存跟进',async()=>{
      try{await api(`/api/admin/consultations/${item.id}`,payload({status:status.value,note:note.value.trim()}));await refresh();msg('咨询状态已保存。');}
      catch(error){msg(error.message);}
    },true);
    button(follow,'删除',async()=>{
      if(!confirm(`确定删除 ${item.parent_name} 的咨询记录？此操作不能恢复。`))return;
      await action(`/api/admin/consultations/${item.id}/delete`);
    },true);
    host.append(tr);
  }
  if(!host.children.length){const tr=document.createElement('tr'),td=cell(tr,'当前没有符合筛选条件的咨询。');td.colSpan=3;host.append(tr);}
}
async function action(path, options={}){try{await api(path,{method:'POST',...options});await refresh();}catch(error){msg(error.message);}}
function payload(value){return{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)};}
$('login').onclick=()=>{key=$('key').value.trim();$('key').value='';refresh();};
$('logout').onclick=()=>{key='';catalog=null;$('dashboard').hidden=true;msg('已退出教师工作台');};
$('create-class').onclick=async()=>{const class_id=$('class-id').value.trim().toLowerCase(),count=Number($('count').value);if(!confirm(`创建 ${count} 个学生账号？`))return;try{await api('/api/admin/classes',payload({class_id,count}));selectedClass=class_id;await refresh();msg('班级已创建。请下载名单，分别发给孩子。');}catch(e){msg(e.message);}};
$('create-program').onclick=async()=>{const value={title:$('program-title').value.trim(),slug:$('program-slug').value.trim().toLowerCase(),kind:$('program-kind').value,days:Number($('program-days').value),description:$('program-description').value.trim()};try{await api('/api/admin/programs',payload(value));await refresh();msg(`课程 ${value.title} 已创建，请继续添加课题。`);}catch(e){msg(e.message);}};
$('marketing-program').onchange=renderMarketing;
$('collection-program').onchange=renderCollectionStudents;
$('create-collection').onclick=async()=>{
  const code=$('collection-student').value,program_id=Number($('collection-program').value);
  if(!code||!program_id)return msg('请先选择已报名创作营的学生。');
  try{await api('/api/admin/collections',payload({code,program_id,active:true}));await refresh();msg('作品集已生成，可把链接交给家长。');}
  catch(error){msg(error.message);}
};
$('save-marketing').onclick=async()=>{
  const id=Number($('marketing-program').value);
  if(!id)return msg('请先选择课程。');
  const value={status:$('marketing-status').value};
  for(const name of ['summary','audience','outcome','duration','parent_role'])value[name]=$('marketing-'+name.replace('_','-')).value.trim();
  try{await api(`/api/admin/programs/${id}/marketing`,payload(value));await refresh();msg('课程对外信息已保存。');}
  catch(error){msg(error.message);}
};
$('add-faq').onclick=()=>faqRow();
$('save-content').onclick=async()=>{
  const faqs=[...$('faq-editor').querySelectorAll('.faq-row')].map(row=>({
    q:row.querySelector('.faq-question').value.trim(),a:row.querySelector('.faq-answer').value.trim()}));
  const value={teacher_intro:$('teacher-intro').value.trim(),demo_title:$('demo-title').value.trim(),
    demo_summary:$('demo-summary').value.trim(),faqs};
  try{await api('/api/admin/site-content',payload(value));await refresh();msg('网站内容已保存，公开页面会更新。');}
  catch(error){msg(error.message);}
};
$('upload-wechat-qr').onclick=async()=>{
  const file=$('wechat-qr-file').files[0];
  if(!file)return msg('请先选择真实的微信二维码图片。');
  if(file.size>2_000_000)return msg('二维码图片不能超过 2MB。');
  try{await api('/api/admin/wechat-qr',{method:'POST',headers:{'Content-Type':file.type},body:file});
    $('wechat-qr-file').value='';await refresh();msg('二维码已上传，请用手机扫码确认。');}
  catch(error){msg(error.message);}
};
$('create-lesson').onclick=async()=>{const value={program_id:Number($('lesson-program').value),title:$('lesson-title').value.trim(),slug:$('lesson-slug').value.trim().toLowerCase(),day_no:Number($('lesson-day').value)};try{await api('/api/admin/lessons',payload(value));await refresh();msg(`课题 ${value.title} 已添加，请上传起始包。`);}catch(e){msg(e.message);}};
$('enroll').onclick=async()=>{const program_id=Number($('enroll-program').value);if(!selectedClass)return msg('请先选择班级');try{await api('/api/admin/enroll-class',payload({class_id:selectedClass,program_id}));await refresh();msg('课程已分配给全班。学生登录后即可看到。');}catch(e){msg(e.message);}};
$('assign-student').onclick=async()=>{const code=$('enroll-student').value,program_id=Number($('enroll-student-program').value);if(!code)return msg('请先选择一位学生');try{await api('/api/admin/enroll-student',payload({code,program_id}));await refresh();msg(`课程已分配给 ${code}。`);}catch(e){msg(e.message);}};
$('filter-class').onchange=()=>{selectedClass=$('filter-class').value;refresh();};
$('refresh').onclick=refresh;
$('csv').onclick=async()=>{if(!selectedClass)return msg('请先创建班级');try{const blob=await api('/api/admin/roster.csv?class_id='+encodeURIComponent(selectedClass));const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=selectedClass+'-账号名单.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){msg(e.message);}};
$('qr-close').onclick=()=>$('qr-dialog').close();
$('versions-close').onclick=()=>$('versions-dialog').close();
$('lead-filter').onchange=renderLeads;
$('source-filter').onchange=renderLeads;
$('review-filter').onchange=()=>renderAssignments(assignments.filter(x=>x.class_id===selectedClass));
$('lesson-filter').onchange=()=>renderAssignments(assignments.filter(x=>x.class_id===selectedClass));
$('free-filter').onchange=()=>renderFree(freeWorks.filter(x=>x.code.startsWith(selectedClass+'-')));
$('export-leads').onclick=async()=>{
  try{const blob=await api('/api/admin/consultations.csv');const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='codexai-咨询线索.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  catch(error){msg(error.message);}
};
$('cancel-consent').onclick=()=>$('consent-dialog').close();
$('save-consent').onclick=async()=>{
  const value={code:$('consent-code').value,lesson_id:$('consent-lesson').value?Number($('consent-lesson').value):null,
    independent_id:$('consent-free').value?Number($('consent-free').value):null,
    guardian_ref:$('guardian-ref').value.trim(),channel:$('consent-channel').value,
    consent_at:$('consent-date').value,evidence_ref:$('evidence-ref').value.trim()};
  try{await api('/api/admin/consents',payload(value));$('consent-dialog').close();$('guardian-ref').value='';$('evidence-ref').value='';await refresh();msg('家长同意已登记。现在可以选择加入公开作品展。');}
  catch(error){msg(error.message);}
};
