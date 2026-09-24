'use strict';
const host=document.getElementById('works'),message=document.getElementById('message');
fetch('/api/public/showcase').then(async response=>{
  if(!response.ok)throw Error('作品展暂时无法加载，请稍后重试。');
  return response.json();
}).then(rows=>{
  if(!rows.length){message.textContent='首批学生作品仍在准备中。可以先体验上面的教师示范作品。';return;}
  message.textContent=`目前展示 ${rows.length} 件经过家长同意的作品。`;
  for(const row of rows){
    const card=document.createElement('article');card.className='card work-card';
    const type=document.createElement('span');type.className='eyebrow';type.textContent=row.program_title;card.append(type);
    const title=document.createElement('h3');title.textContent=row.lesson_title;card.append(title);
    if(row.summary){const summary=document.createElement('p');summary.textContent=row.summary;card.append(summary);}
    const maker=document.createElement('p');maker.className='muted';maker.textContent='创作者代号 · '+row.code;card.append(maker);
    const link=document.createElement('a');link.className='button';link.href=row.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent='打开作品';card.append(link);
    host.append(card);
  }
}).catch(error=>message.textContent=error.message);
