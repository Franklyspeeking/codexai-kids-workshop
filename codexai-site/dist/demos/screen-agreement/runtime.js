'use strict';
const C=window.COURSE, seed=window.SEED, $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone=x=>JSON.parse(JSON.stringify(x)), key=`maker-product-v2-${C.id}`;
function read(k,fallback){try{const v=localStorage.getItem(k);return v?JSON.parse(v):clone(fallback)}catch{return clone(fallback)}}
let state=read(key,seed), timer;
function toast(message){let n=$('#toast');n.textContent=message;n.hidden=false;clearTimeout(timer);timer=setTimeout(()=>n.hidden=true,3400)}
function save(){try{localStorage.setItem(key,JSON.stringify(state))}catch{toast('浏览器无法保存；请导出作品留存。')}}
function download(name,data,type='application/json'){const blob=new Blob([typeof data==='string'?data:JSON.stringify(data,null,2)],{type});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
function form(id,fn){$('#'+id)?.addEventListener('submit',e=>{e.preventDefault();const v=Object.fromEntries(new FormData(e.currentTarget));if([...e.currentTarget.querySelectorAll('input[required],textarea[required]')].some(x=>!x.value.trim()))return toast('请填写有效内容，不能只有空格。');fn(v)})}
function on(id,fn){$('#'+id)?.addEventListener('click',fn)}
function actions(selector,fn){$$(selector).forEach(el=>el.addEventListener('click',()=>fn(el.dataset.action,el)))}
function options(arr,selected){return arr.map(x=>`<option ${String(x)===String(selected)?'selected':''}>${esc(x)}</option>`).join('')}
function field(label,name,type='text',value='',extra=''){return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`}
function select(label,name,arr,value){return `<label>${label}<select name="${name}">${options(arr,value)}</select></label>`}
function panel(title,body,cls=''){return `<section class="panel ${cls}"><h2>${esc(title)}</h2>${body}</section>`}
function stat(label,value){return `<div class="stat"><small>${label}</small><b>${value}</b></div>`}
function progress(n){return `<div class="progress" role="progressbar" aria-label="完成进度" aria-valuenow="${Math.round(Math.max(0,Math.min(100,n)))}" aria-valuemin="0" aria-valuemax="100"><i style="width:${Math.max(0,Math.min(100,n))}%"></i></div>`}
function empty(text='还没有记录，来完成第一次尝试吧。'){return `<div class="empty">${text}</div>`}
function uid(){return Date.now().toString(36)+Math.random().toString(36).slice(2,6)}
function today(){const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function money(n){return Number(n).toFixed(2)}
function commit(){save();render()}
document.title=C.productName+' · '+C.title;
document.documentElement.style.setProperty('--accent',C.accent);
document.documentElement.style.setProperty('--ink',C.ink);
document.documentElement.style.setProperty('--paper',C.paper);
$('#page').innerHTML=`<div class="shell"><nav class="top"><div class="brand"><span class="logo">${C.icon}</span>${esc(C.productName)}</div><span>个人本地版 · 自动保存</span></nav><header class="hero"><div><div class="eyebrow">${esc(C.group)}</div><h1>${esc(C.title)}</h1><p>${esc(C.subtitle)}</p></div><div class="stamp"><b>${C.icon}</b><span>${esc(C.productName)}</span></div></header><div class="workspace-nav"><a href="#app">日常使用</a><a href="#workspace">${esc(C.productName)}工作台</a><a href="#data-tools">数据与备份</a></div><main id="app" class="fade"></main><section id="workspace"></section><section id="data-tools" class="panel"><h2>数据与备份</h2><div class="toolbar"><button id="export">导出完整备份</button><button id="import">恢复备份</button><button id="undo">撤销上次操作</button><button id="print">打印 / 保存 PDF</button><button id="reset">恢复初始数据</button></div><input type="file" id="import-file" accept=".json,application/json" hidden><p class="notice" id="save-status">数据仅保存在本机浏览器。请定期导出备份，换设备时再导入。没有云同步。</p></section><footer class="footer notice">${esc(C.productName)} · v2.0 · AI 辅助开发<br>${esc(C.boundary)} 无在线大模型、定位或消息发送。</footer></div><div id="toast" class="toast" role="status" hidden></div><dialog id="reset-dialog"><p>恢复本工具的初始数据？当前记录将被替换；操作前自动保留一份本机备份。</p><div class="row"><button id="cancel-reset">取消</button><button id="confirm-reset" class="primary">确认恢复</button></div></dialog>`;
on('print',()=>window.print());on('reset',()=>$('#reset-dialog').showModal());on('cancel-reset',()=>$('#reset-dialog').close());on('confirm-reset',()=>{try{localStorage.setItem(key+'-before-reset',JSON.stringify(state))}catch{}state=clone(seed);commit();$('#reset-dialog').close();toast('已恢复初始数据，可撤销')});
