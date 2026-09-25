'use strict';
const host=document.getElementById('works'),message=document.getElementById('message');
const programFilter=document.getElementById('showcase-program'),sortFilter=document.getElementById('showcase-sort');
let works=[];
function renderWorks(){
  host.replaceChildren();
  const selected=works.filter(row=>!programFilter.value||row.program_title===programFilter.value);
  selected.sort((a,b)=>sortFilter.value==='oldest'?a.published_at.localeCompare(b.published_at):b.published_at.localeCompare(a.published_at));
  message.textContent=selected.length?`显示 ${selected.length} 件经过家长同意的作品。`:'这个分类暂时没有公开作品，可以先体验上面的教师示范。';
  for(const row of selected){
    const card=document.createElement('article');card.className='card work-card';
    const type=document.createElement('span');type.className='eyebrow';type.textContent=row.program_title;card.append(type);
    const title=document.createElement('h3');title.textContent=row.lesson_title;card.append(title);
    if(row.summary){const summary=document.createElement('p');summary.textContent=row.summary;card.append(summary);}
    const maker=document.createElement('p');maker.className='muted';maker.textContent='创作者代号 · '+row.code;card.append(maker);
    const time=document.createElement('p');time.className='muted';time.textContent='发布日期 · '+row.published_at.slice(0,10);card.append(time);
    const link=document.createElement('a');link.className='button';link.href=row.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='打开作品';card.append(link);
    host.append(card);
  }
}
programFilter.onchange=renderWorks;sortFilter.onchange=renderWorks;
fetch('/api/public/showcase').then(async response=>{
  if(!response.ok)throw Error('作品展暂时无法加载，请稍后重试。');
  return response.json();
}).then(rows=>{
  works=rows;
  for(const value of [...new Set(rows.map(row=>row.program_title))].sort()){
    const option=document.createElement('option');option.value=value;option.textContent=value;programFilter.append(option);
  }
  renderWorks();
}).catch(error=>message.textContent=error.message);
