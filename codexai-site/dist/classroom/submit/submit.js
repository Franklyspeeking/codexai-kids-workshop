'use strict';
const $ = id => document.getElementById(id);
const result = $('result');
let publishedUrl = '';
let polling = false, checking = false;
function show(message, error = false) { result.textContent = message; result.classList.toggle('error', error); }
function credentials() {
  const code = $('code').value.trim().toLowerCase(), token = $('token').value.trim();
  if (!/^[a-z][a-z0-9-]{2,30}$/.test(code) || !token) throw Error('请检查老师给的作品编号和上传码');
  return {code, token};
}
async function request(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(()=>{throw Error('暂时连不上上传服务，请检查网络后重试。');});
  if (!response.ok) throw Error(data.error || '服务器暂时无法处理，请稍后重试');
  return data;
}
function delivery(data) {
  $('delivery').hidden = !data.url;
  if (!data.url) return;
  publishedUrl = data.url;
  $('work-link').href = data.url;
  $('work-link').textContent = data.url;
  $('qr').src = data.qr;
}
async function check() {
  if (checking) return;
  checking = true;
  try {
    const {code, token} = credentials();
    const data = await request('/api/status/' + encodeURIComponent(code), {headers: {'X-Upload-Token': token}});
    show(data.status + (data.error ? '：' + data.error : '') + (data.status === '待审核' ? '。老师确认后，这里会显示家长链接。' : ''));
    polling = data.status === '待审核';
    delivery(data);
  } catch (error) { polling = false; show(error.message, true); }
  finally { checking = false; }
}
$('submit-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = $('send');
  try {
    const {code, token} = credentials(), file = $('zip').files[0];
    if (!file || !file.name.toLowerCase().endsWith('.zip')) throw Error('请选择 ZIP 压缩包');
    if (file.size > 25_000_000) throw Error('压缩包不能超过 25MB');
    button.disabled = true; show('正在上传并检查文件，请稍等…');
    const data = await request('/api/submit/' + encodeURIComponent(code), {
      method: 'POST', headers: {'X-Upload-Token': token, 'Content-Type': 'application/zip'}, body: file
    });
    show(data.message); delivery({}); polling = true;
  } catch (error) { show(error.message, true); }
  finally { button.disabled = false; }
});
$('check').addEventListener('click', check);
$('copy').addEventListener('click', async () => { try { await navigator.clipboard.writeText(publishedUrl); show('家长链接已复制'); } catch { show('请长按链接复制', true); } });
setInterval(() => { if (polling) check(); }, 10000);
