(() => {
  function sync(){
    document.getElementById('balance').closest('.feature').classList.toggle('wide-amount',document.getElementById('balance').textContent.length>9);
    document.getElementById('wish-preview').textContent=document.getElementById('wish-name').textContent;
    document.getElementById('wish-preview-progress').value=document.getElementById('wish-progress').value;
    document.getElementById('wish-preview-gap').textContent=document.getElementById('wish-gap').textContent;
    document.getElementById('wish-ring').style.setProperty('--pct',document.getElementById('wish-progress').value);
  }
  document.querySelectorAll('[data-pane]').forEach(button=>button.onclick=()=>{
    document.querySelectorAll('[data-view]').forEach(view=>view.hidden=view.dataset.view!==button.dataset.pane);
    document.querySelectorAll('.nav [data-pane]').forEach(b=>{if(b.dataset.pane===button.dataset.pane)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current')});
    window.scrollTo({top:0,behavior:'instant'});
  });
  document.getElementById('open-entry').onclick=()=>document.getElementById('entry-dialog').showModal();
  document.getElementById('open-help').onclick=()=>document.getElementById('help-dialog').showModal();
  document.querySelectorAll('[data-close]').forEach(button=>button.onclick=()=>document.getElementById(button.dataset.close).close());
  document.addEventListener('money-saved',()=>{sync();document.getElementById('entry-dialog').close()});
  sync();
})();
