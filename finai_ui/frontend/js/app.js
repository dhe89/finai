(function(){
  const app=document.getElementById('app');
  const left=document.getElementById('left');
  const leftToggle=document.getElementById('leftToggle');
  const ai=document.getElementById('ai');
  const aiClose=document.getElementById('aiClose');
  const desktopAI=document.querySelectorAll('.desktop-ai-trigger');
  const mobileAI=document.querySelectorAll('.mobile-ai');
  const mobileMenu=document.getElementById('mobileMenu');
  const overlay=document.getElementById('mobileOverlay');
  const chatBody=document.getElementById('chatBody');
  const chatInput=document.getElementById('chatInput');
  const sendChat=document.getElementById('sendChat');
  const pageViews=document.querySelectorAll('.page-view[data-page-view]');
  const navItems=document.querySelectorAll('.nav-item[data-page]');

  let leftCollapsed=false;
  let aiOpen=false;
  let currentPage=document.querySelector('.page-view.active')?.dataset.pageView || 'kinerja';

  function isMobile(){ return window.innerWidth <= 800; }

  function setAI(open){
    aiOpen=!!open;
    if(!ai) return;
    ai.classList.toggle('closed',!aiOpen);
    ai.setAttribute('aria-hidden',String(!aiOpen));
    // Never auto-focus the input. This prevents mobile keyboard/viewport zoom.
  }

  function setSidebarCollapsed(collapsed){
    leftCollapsed=!!collapsed;
    if(!app || !leftToggle) return;
    app.classList.toggle('left-collapsed',leftCollapsed);
    leftToggle.setAttribute('aria-label',leftCollapsed?'Expand navigation':'Collapse navigation');
  }

  function closeDrawer(){
    if(left) left.classList.remove('mobile-open');
    if(overlay) overlay.classList.remove('show');
  }

  function syncResponsive(){
    if(isMobile()){
      if(app) app.classList.remove('left-collapsed');
      if(left && overlay) overlay.classList.toggle('show',left.classList.contains('mobile-open'));
    }else{
      closeDrawer();
    }
  }

  function setActivePage(page, updateUrl){
    if(!page) return;
    const target=document.querySelector('.page-view[data-page-view="'+page+'"]');
    if(!target) return;

    currentPage=page;
    pageViews.forEach(view=>view.classList.toggle('active',view===target));
    navItems.forEach(item=>{
      const active=item.dataset.page===page;
      item.classList.toggle('active',active);
      if(active) item.setAttribute('aria-current','page');
      else item.removeAttribute('aria-current');
    });

    if(updateUrl){
      try{
        const url=new URL(window.top.location.href);
        if(page==='kinerja') url.searchParams.delete('page');
        else url.searchParams.set('page',page);
        window.top.history.replaceState({},'',url.toString());
      }catch(e){ /* Streamlit iframe may restrict top history; page still changes locally. */ }
    }

    const main=target.querySelector('.main');
    if(main) main.scrollTop=0;
    closeDrawer();
  }

  navItems.forEach(item=>{
    item.addEventListener('click',()=>setActivePage(item.dataset.page,true));
    item.addEventListener('keydown',e=>{
      if(e.key==='Enter'||e.key===' '){
        e.preventDefault();
        setActivePage(item.dataset.page,true);
      }
    });
  });

  if(leftToggle){
    leftToggle.addEventListener('click',()=>{
      if(isMobile()){
        if(left) left.classList.toggle('mobile-open');
        if(left && overlay) overlay.classList.toggle('show',left.classList.contains('mobile-open'));
      }else{
        setSidebarCollapsed(!leftCollapsed);
      }
    });
  }

  if(mobileMenu){
    mobileMenu.addEventListener('click',()=>{
      if(left) left.classList.toggle('mobile-open');
      if(left && overlay) overlay.classList.toggle('show',left.classList.contains('mobile-open'));
    });
  }

  if(overlay) overlay.addEventListener('click',closeDrawer);
  window.addEventListener('resize',syncResponsive);

  if(aiClose) aiClose.addEventListener('click',()=>setAI(false));
  desktopAI.forEach(btn=>btn.addEventListener('click',()=>setAI(true)));
  mobileAI.forEach(btn=>btn.addEventListener('click',()=>setAI(true)));

  function appendMessage(text,user){
    if(!chatBody) return;
    const msg=document.createElement('div');
    msg.className='msg'+(user?' user':'');
    if(user){
      const bubble=document.createElement('div');
      bubble.className='bubble';
      bubble.textContent=text;
      msg.appendChild(bubble);
    }else{
      const bot=document.createElement('div');
      bot.className='bot';
      bot.textContent='✦';
      const body=document.createElement('div');
      body.className='msgtext';
      body.innerHTML=text;
      msg.appendChild(bot);
      msg.appendChild(body);
    }
    chatBody.appendChild(msg);
    chatBody.scrollTop=chatBody.scrollHeight;
  }

  function safe(text){
    return String(text).replace(/[<>&"]/g,function(s){
      return {'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[s];
    });
  }

  function dummyResponse(text){
    const t=text.toLowerCase();
    if(t.includes('laba')||t.includes('profit')){
      return 'Berdasarkan data dummy, <b>Net Profit</b> bulan ini adalah <b>699.1</b>, turun dibanding bulan lalu sebesar <b>13.94%</b>. Untuk analisis lebih lanjut, coba cek Revenue, Operating Expense, dan CKPN.';
    }
    if(t.includes('asset')){
      return 'Total Asset pada periode ini adalah <b>190,510.7</b>. Dibanding bulan lalu sebesar <b>194,349.9</b>, nilainya turun sekitar <b>1.98%</b>.';
    }
    if(t.includes('credit')||t.includes('kredit')){
      return 'Total Credit pada periode ini adalah <b>104,549.2</b>, sedangkan bulan lalu <b>106,885.6</b>. Ini masih berupa respons simulasi dari data prototype.';
    }
    return 'Saya memahami pertanyaan Anda: <b>'+safe(text)+'</b><br><span class="muted">Ini adalah respons dummy untuk prototype. Nantinya bagian ini dapat dihubungkan ke engine AI dan evidence financial reporting.</span>';
  }

  function send(){
    if(!chatInput) return;
    const text=chatInput.value.trim();
    if(!text) return;
    appendMessage(text,true);
    chatInput.value='';
    setTimeout(()=>appendMessage(dummyResponse(text),false),450);
  }

  if(sendChat) sendChat.addEventListener('click',send);
  if(chatInput) chatInput.addEventListener('keydown',e=>{
    if(e.key==='Enter' && !e.shiftKey){e.preventDefault();send();}
  });

  setSidebarCollapsed(false);
  setAI(false);
  setActivePage(currentPage,false);
  syncResponsive();
})();