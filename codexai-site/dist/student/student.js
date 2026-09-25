'use strict';
const $ = id => document.getElementById(id);
const msg = value => { $('message').textContent = value; };
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(()=>{throw Error('暂时连不上创作服务，请检查网络后重试。');});
  if (!response.ok) throw Error(data.error || '操作失败，请稍后重试');
  return data;
}
function add(parent, tag, value = '', className = '') {
  const item = document.createElement(tag);
  item.textContent = value;
  if (className) item.className = className;
  parent.append(item);
  return item;
}
function link(parent, label, href) {
  const item = add(parent, 'a', label, 'button secondary');
  item.href = href;
  item.target = '_blank';
  item.rel = 'noopener noreferrer';
  return item;
}
function renderDelivery(card, item) {
  if (!item.url) return;
  add(card, 'p', item.listed ? '家长可打开 · 已获同意公开展示' : '家长可打开 · 未进入公开作品展', 'work-meta');
  const tools = add(card, 'div', '', 'actions');
  link(tools, '打开作品', item.url);
  if (item.qr) link(tools, '家长扫码', item.qr);
  const copy = add(tools, 'button', '复制家长链接', 'secondary');
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(item.url); msg('链接已复制，可以发给家长。'); }
    catch { msg('复制失败，请打开作品后从地址栏复制。'); }
  };
}
function renderHistory(card, versions) {
  if (!versions?.length) return;
  const details=add(card,'details');
  add(details,'summary',`提交历史（${versions.length} 次）`);
  const list=add(details,'ul');
  for(const version of versions){
    const text=`${version.received_at.slice(0,16).replace('T',' ')} · ${version.status}${version.error?' · 老师建议：'+version.error:''}`;
    add(list,'li',text);
  }
}
function uploadField(card, path, label) {
  const row = add(card, 'div');
  const field = add(row, 'label', '上传完整的网页 ZIP：');
  const picker = add(field, 'input');
  picker.type = 'file'; picker.accept = '.zip,application/zip';
  const send = add(row, 'button', '提交给老师审核');
  send.onclick = async () => {
    const file = picker.files[0];
    if (!file) return msg('请先选择 ZIP 文件。');
    if (file.size > 25_000_000) return msg('ZIP 不能超过 25MB。');
    send.disabled = true; msg('正在上传并检查，请稍等…');
    try {
      await api(path, {method:'POST', headers:{'Content-Type':'application/zip'}, body:file});
      await refresh(); msg(`《${label}》上传成功，等待老师审核。`);
    } catch(error) { msg(error.message); }
    finally { send.disabled = false; }
  };
}
function renderFree(rows) {
  const host = $('free-works'); host.replaceChildren();
  if (!rows.length) {
    add(host,'p','这里还没有自由作品。你可以从一个生活中的小问题开始。','muted');
    return;
  }
  for (const item of rows) {
    const card = add(host,'article','','card');
    add(card,'span',item.category,'eyebrow');
    add(card,'h3',item.title);
    add(card,'p',item.summary);
    add(card,'span',item.status || '还未上传', 'status '+(item.status==='已发布'?'published':item.status==='待审核'?'pending':''));
    if (item.error) add(card,'p','老师的修改建议：'+item.error,'feedback');
    if (item.received_at) add(card,'p','最近提交：'+item.received_at.slice(0,10),'work-meta');
    uploadField(card,`/api/student/independent/${item.id}/submit`,item.title);
    renderDelivery(card,item);
    renderHistory(card,item.versions);
  }
}
function renderCourses(data) {
  const host = $('programs'); host.replaceChildren();
  const groups = new Map();
  for (const row of data.lessons) {
    if (!groups.has(row.program_id)) groups.set(row.program_id,[]);
    groups.get(row.program_id).push(row);
  }
  if (!groups.size) return add(host,'p','老师还没有为你安排课程。自由创作区仍然可以使用。','muted');
  for (const rows of groups.values()) {
    const first = rows[0], section = add(host,'section','','program');
    add(section,'span',first.kind==='camp'?`${first.days} 天创作营`:'半天创作课','eyebrow');
    add(section,'h3',first.program_title);
    const collection=data.collections?.find(item=>item.program_id===first.program_id);
    if(collection)link(section,'打开给家长的阶段作品集',collection.url);
    if (first.description) add(section,'p',first.description,'muted');
    const grid = add(section,'div','','topic');
    for (const item of rows) {
      const card = add(grid,'article','','card');
      add(card,'span',`第 ${item.day_no} 天 · ${item.lesson_title}`,'eyebrow');
      add(card,'h3',item.lesson_title);
      add(card,'span',item.status || '未提交','status '+(item.status==='已发布'?'published':item.status==='待审核'?'pending':''));
      if (item.error) add(card,'p','老师的修改建议：'+item.error,'feedback');
      if (item.starter_available) {
        const starter = add(card,'a','下载起始包','button secondary');
        starter.href = `/api/student/lessons/${item.lesson_id}/starter.zip`;
        starter.download = `${item.lesson_slug}-starter.zip`;
      } else add(card,'p','老师还未准备起始包。','muted');
      uploadField(card,`/api/student/submit/${item.lesson_id}`,item.lesson_title);
      renderDelivery(card,item);
      renderHistory(card,item.versions);
    }
  }
}
async function refresh() {
  try {
    const [dashboard, independent] = await Promise.all([
      api('/api/student/dashboard'), api('/api/student/independent')
    ]);
    $('identity').textContent = '我的编号：'+dashboard.code;
    $('login-card').hidden = true; $('dashboard').hidden = false;
    renderFree(independent); renderCourses(dashboard);
    msg('作品和课程状态已更新。');
  } catch(error) {
    $('dashboard').hidden = true; $('login-card').hidden = false; msg(error.message);
  }
}
$('create-free').onclick = async () => {
  const value = {
    title:$('free-title').value.trim(), category:$('free-category').value.trim(),
    summary:$('free-summary').value.trim()
  };
  try {
    const project = await api('/api/student/independent',{
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(value)
    });
    $('free-title').value = ''; $('free-category').value = ''; $('free-summary').value = '';
    await refresh(); msg(`《${project.title}》已创建。请上传你的网页 ZIP。`);
  } catch(error) { msg(error.message); }
};
$('login').onclick = async () => {
  const code = $('code').value.trim().toLowerCase(), token = $('token').value.trim();
  try {
    await api('/api/student/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code,token})});
    $('token').value = ''; await refresh();
  } catch(error) { msg(error.message); }
};
$('logout').onclick = async () => {
  try { await api('/api/student/logout',{method:'POST'}); } catch {}
  $('dashboard').hidden = true; $('login-card').hidden = false; msg('已退出。');
};
$('refresh').onclick = refresh;
refresh();
