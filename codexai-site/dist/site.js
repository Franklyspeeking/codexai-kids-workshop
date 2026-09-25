'use strict';
(() => {
  const query=new URLSearchParams(location.search);
  const source=(query.get('src')||query.get('utm_source')||'').trim().slice(0,80);
  if(source && /^[\p{L}\p{N}_ .-]{1,80}$/u.test(source)) sessionStorage.setItem('codexai_source',source);
  const recorded=sessionStorage.getItem('codexai_source')||'';
  for(const link of document.querySelectorAll('[data-track-consult]')){
    if(recorded){const target=new URL(link.href);target.searchParams.set('src',recorded);link.href=target.toString();}
  }
  for(const button of document.querySelectorAll('[data-copy-wechat]')){
    button.addEventListener('click',async()=>{
      const notice=document.getElementById('wechat-status');
      try{await navigator.clipboard.writeText('NicolasGoesed');if(notice)notice.textContent='微信号已复制。请打开微信，在“添加朋友”中粘贴搜索。';}
      catch{if(notice)notice.textContent='请手动复制微信号 NicolasGoesed，在微信“添加朋友”中搜索。';}
    });
  }
  if(document.querySelector('.faq-list,#teacher-profile,#about-text,#wechat-qr-block,#demo-title')){
    fetch('/api/public/site-content').then(response=>{
      if(!response.ok)throw Error('网站内容暂时不可用');
      return response.json();
    }).then(content=>{
      const faq=document.querySelector('.faq-list');
      if(faq&&Array.isArray(content.faqs)&&content.faqs.length){
        faq.replaceChildren();
        for(const item of content.faqs){
          const details=document.createElement('details');
          const question=document.createElement('summary');question.textContent=item.q;details.append(question);
          const answer=document.createElement('p');answer.textContent=item.a;details.append(answer);
          faq.append(details);
        }
      }
      const profile=document.getElementById('teacher-profile');
      if(profile&&content.teacher_intro){
        const intro=document.getElementById('teacher-intro');
        if(intro)intro.textContent=content.teacher_intro.split(/\n\s*\n/)[0];
      }
      const about=document.getElementById('about-text');
      if(about&&content.teacher_intro){
        about.replaceChildren();
        for(const paragraph of content.teacher_intro.split(/\n\s*\n/).filter(Boolean)){
          const item=document.createElement('p');item.textContent=paragraph;about.append(item);
        }
      }
      const demoTitle=document.getElementById('demo-title');
      if(demoTitle){demoTitle.textContent=content.demo_title;document.getElementById('demo-summary').textContent=content.demo_summary;}
      if(content.wechat_qr_available&&document.getElementById('wechat-qr-block')){
        document.getElementById('wechat-qr-image').src='/api/public/wechat-qr';
        document.getElementById('wechat-qr-block').hidden=false;
        document.getElementById('wechat-qr-pending').hidden=true;
      }
    }).catch(()=>{});
  }
  const homeDirections=document.getElementById('home-directions');
  if(document.querySelector('#home-money-status,#money-list-status,#money-detail-status')){
    fetch('/api/public/courses').then(response=>response.ok?response.json():null).then(courses=>{
      if(!courses||courses.some(course=>course.slug==='workshop01'))return;
      const homeStatus=document.getElementById('home-money-status');
      if(homeStatus)homeStatus.textContent='首个课程主题';
      const homeNote=document.getElementById('home-open-note');
      if(homeNote)homeNote.textContent='“零花钱计划师”目前暂停咨询。其他主题的开放情况请查看课程页。';
      const listStatus=document.getElementById('money-list-status');
      if(listStatus)listStatus.textContent='课程介绍 · 暂未开放咨询';
      const listTag=document.getElementById('money-list-tag');
      if(listTag){listTag.textContent='暂停咨询';listTag.classList.add('soon');}
      const listIntro=document.getElementById('course-status-intro');
      if(listIntro)listIntro.textContent='具体开放情况请以课程状态为准。';
      const detailStatus=document.getElementById('money-detail-status');
      if(detailStatus)detailStatus.textContent='首课 · 暂停咨询';
      const detailAction=document.getElementById('money-detail-consult');
      if(detailAction)detailAction.textContent='询问后续安排';
    }).catch(()=>{});
  }
  if(homeDirections){
    fetch('/api/public/courses').then(response=>response.ok?response.json():[]).then(courses=>{
      let opened=0;
      for(const course of courses.filter(item=>item.slug!=='workshop01')){
        for(const card of homeDirections.querySelectorAll('.poster')){
          if(card.querySelector('h3')?.textContent!==course.title)continue;
          const tag=card.querySelector('.tag');tag.textContent='开放咨询';tag.classList.remove('soon');
          const link=document.createElement('a');link.href=course.url;link.textContent='了解这门课程 →';card.querySelector('div').append(link);
          opened++;
        }
      }
      if(opened)document.getElementById('home-directions-copy').textContent=`其中 ${opened} 个主题已开放咨询；其他主题仍在准备中。具体以课程页为准。`;
    }).catch(()=>{});
  }
  const form=document.getElementById('consult-form');
  if(!form)return;
  fetch('/api/public/courses').then(response=>response.ok?response.json():[]).then(courses=>{
    const select=document.getElementById('interest');
    for(const course of courses){
      if([...select.options].some(option=>option.value===course.title))continue;
      const option=document.createElement('option');option.value=course.title;option.textContent=course.title;select.add(option);
    }
    const requested=query.get('course');
    const selected=courses.find(course=>course.slug===requested);
    if(selected)select.value=selected.title;
  }).catch(()=>{});
  form.addEventListener('submit',async event=>{
    event.preventDefault();
    const submit=form.querySelector('button[type=submit]');
    const notice=document.getElementById('consult-status');
    const data=new FormData(form);
    const body={parent_name:String(data.get('parent_name')||'').trim(),
      contact_kind:String(data.get('contact_kind')||''),contact:String(data.get('contact')||'').trim(),
      child_age:String(data.get('child_age')||''),interest:String(data.get('interest')||''),
      message:String(data.get('message')||'').trim(),company:String(data.get('company')||''),
      source:recorded,entry_path:location.pathname,consent:data.get('consent')==='on'};
    submit.disabled=true;notice.textContent='正在提交，请稍等…';
    try{
      const response=await fetch('/api/public/consultations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const result=await response.json().catch(()=>{throw Error('暂时连不上咨询服务，请改用微信号联系老师。');});
      if(!response.ok)throw Error(result.error||'提交未成功，请稍后重试');
      notice.textContent='已收到咨询，老师会用你留下的方式联系你。';
      form.reset();
    }catch(error){notice.textContent=error.message;}
    finally{submit.disabled=false;}
  });
})();
