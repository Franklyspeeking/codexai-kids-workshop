'use strict';
fetch('/api/public/courses').then(async response=>{
  if(!response.ok)throw Error('课程列表暂时无法更新');
  return response.json();
}).then(courses=>{
  const offerings=courses.filter(course=>course.slug!=='workshop01');
  const host=document.getElementById('open-course-list');
  for(const course of offerings){
    const card=document.createElement('article');card.className='card';
    const tag=document.createElement('span');tag.className='tag';tag.textContent=course.kind==='camp'?'创作营 · 开放咨询':'半天课 · 开放咨询';card.append(tag);
    const title=document.createElement('h3');title.textContent=course.title;card.append(title);
    const summary=document.createElement('p');summary.textContent=course.summary;card.append(summary);
    const outcome=document.createElement('p');outcome.className='muted';outcome.textContent=`${course.duration} · ${course.audience} · ${course.outcome}`;card.append(outcome);
    const link=document.createElement('a');link.className='button';link.href=course.url;link.textContent='了解课程';card.append(link);
    host.append(card);
    for(const direction of document.querySelectorAll('.course-list .poster')){
      if(direction.querySelector('h3')?.textContent===course.title)direction.hidden=true;
    }
  }
  if(offerings.length)document.getElementById('more-open-courses').hidden=false;
  if(offerings.length)document.getElementById('course-status-intro').textContent='下方“已开放咨询”课程可以了解当前安排；其余海报展示后续课程方向。';
  const remaining=[...document.querySelectorAll('.course-list .poster')].filter(card=>!card.hidden).length;
  const heading=document.getElementById('direction-count');
  if(heading)heading.textContent=remaining?`还有 ${remaining} 个生活里的创作方向。`:'更多课程方向正在策划中。';
}).catch(()=>{});
