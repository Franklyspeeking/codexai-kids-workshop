'use strict';
const $ = id => document.getElementById(id);
let key = '';
let selectedClass = '';
function message(text) { $('message').textContent = text; }
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
function addCell(row, text) { const td = document.createElement('td'); td.textContent = text; row.append(td); return td; }
function addButton(parent, label, onClick, secondary = false) { const button = document.createElement('button'); button.textContent = label; if (secondary) button.className = 'secondary'; button.onclick = onClick; parent.append(button); return button; }
async function refresh() {
  try {
    const slots = await api('/api/admin/slots');
    $('dashboard').hidden = false;
    $('rows').replaceChildren();
    const classes = [...new Set(slots.map(slot => slot.class_id))].sort().reverse();
    if (!classes.includes(selectedClass)) selectedClass = classes[0] || '';
    $('filter-class').replaceChildren();
    for (const name of classes) { const option = document.createElement('option'); option.value = name; option.textContent = name; $('filter-class').append(option); }
    $('filter-class').value = selectedClass;
    const current = slots.filter(slot => slot.class_id === selectedClass);
    for (const slot of current) {
      const tr = document.createElement('tr');
      addCell(tr, slot.code + '\n上传码：' + slot.upload_token).style.whiteSpace = 'pre-line';
      addCell(tr, (slot.status || '未提交') + (slot.error ? '\n' + slot.error : '')).style.whiteSpace = 'pre-line';
      const actions = addCell(tr, '');
      if (slot.status === '待审核') {
        const preview = document.createElement('a');
        preview.href = 'https://www.codexai.site/preview/' + encodeURIComponent(slot.preview_token) + '/money/';
        preview.target = '_blank'; preview.rel = 'noopener'; preview.textContent = '打开隔离预览'; actions.append(preview);
        addButton(actions, '确认发布', async () => { if (!confirm('已经测试这个孩子的作品，确认公开发布？')) return; await action('/api/admin/publish/' + slot.submission_id); });
        addButton(actions, '退回修改', async () => { const reason = prompt('告诉孩子需要修改什么：'); if (!reason?.trim()) return; await action('/api/admin/reject/' + slot.submission_id, {headers: {'Content-Type':'application/json'}, body: JSON.stringify({reason})}); }, true);
      }
      const delivery = addCell(tr, '');
      if (slot.url) {
        const link = document.createElement('a'); link.href = slot.url; link.target = '_blank'; link.rel = 'noopener'; link.textContent = slot.url; delivery.append(link);
        addButton(delivery, '复制链接', async () => { await navigator.clipboard.writeText(slot.url); message('已复制 ' + slot.code + ' 的链接'); }, true);
        addButton(delivery, '显示二维码', () => { $('qr-image').src = '/api/works/' + encodeURIComponent(slot.code) + '/qr.png'; $('qr-link').textContent = slot.url; $('qr-dialog').showModal(); }, true);
      }
      $('rows').append(tr);
    }
    message('已载入 ' + selectedClass + ' 的 ' + current.length + ' 个学生编号。');
  } catch (error) { $('dashboard').hidden = true; message(error.message); }
}
async function action(path, options = {}) { try { await api(path, {method:'POST', ...options}); await refresh(); } catch (error) { message(error.message); } }
$('login').onclick = () => { key = $('key').value.trim(); $('key').value = ''; refresh(); };
$('logout').onclick = () => { key = ''; $('key').value = ''; $('dashboard').hidden = true; message('已退出'); };
$('create').onclick = async () => {
  const class_id = $('class-id').value.trim().toLowerCase(), count = Number($('count').value);
  if (!confirm('生成 ' + count + ' 个学生编号？同一个班级编号不能重复创建。')) return;
  try { await api('/api/admin/classes', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({class_id,count})}); selectedClass = class_id; await refresh(); message('班级已建立。请下载名单并分发各自的上传码。'); } catch (error) { message(error.message); }
};
$('refresh').onclick = refresh;
$('filter-class').onchange = () => { selectedClass = $('filter-class').value; refresh(); };
$('csv').onclick = async () => { try { if (!selectedClass) throw Error('请先创建班级'); const blob = await api('/api/admin/roster.csv?class_id=' + encodeURIComponent(selectedClass)); const href = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = href; a.download = selectedClass + '-编号与上传码.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(href), 1000); } catch (error) { message(error.message); } };
$('qr-close').onclick = () => $('qr-dialog').close();
