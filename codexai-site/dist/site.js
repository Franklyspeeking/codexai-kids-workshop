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
  const form=document.getElementById('consult-form');
  if(!form)return;
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
