let p;
function initProduct(){state._product??={};p=state._product;productDefaults()}
function defaults(v){for(const [k,x] of Object.entries(v))if(p[k]===undefined)p[k]=clone(x)}
const box=(title,body,cls='')=>panel(title,body,cls);
function btn(text,id,cls='primary'){return `<button id="${id}" class="${cls}">${text}</button>`}
function rows(list,fn){return list.length?list.map(fn).join(''):empty('暂无记录。添加第一条，开始使用。')}
function note(t){return `<p class="notice">${t}</p>`}
function dateField(name,value=today()){return field('日期',name,'date',value,'required')}
function deleteButtons(name,fn){$$(`[data-${name}]`).forEach(b=>b.onclick=()=>fn(b.getAttribute('data-'+name)))}
function put(html){$('#workspace').innerHTML=`<h2 class="workspace-title">${C.icon} ${esc(C.productName)}工作台</h2>`+html}
function exportCSV(name,headers,rows){const safe=v=>{let s=String(v??'');if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'};download(name,'\ufeff'+[headers,...rows].map(r=>r.map(safe).join(',')).join('\r\n'),'text/csv;charset=utf-8')}
function monthKey(){return today().slice(0,7)}
function humanTime(n){return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`}
function requireInt(n,min=0,max=100000){return Number.isFinite(+n)&&Number.isInteger(+n)&&+n>=min&&+n<=max}
