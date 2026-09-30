(function(){
  const app=document.getElementById('app');
  const left=document.getElementById('left');
  const ai=document.getElementById('ai');
  const leftToggle=document.getElementById('leftToggle');
  const aiClose=document.getElementById('aiClose');
  const desktopAI=document.getElementById('desktopAI');
  const mobileAI=document.getElementById('mobileAI');
  const mobileMenu=document.getElementById('mobileMenu');
  const overlay=document.getElementById('mobileOverlay');
  const chatBody=document.getElementById('chatBody');
  const chatInput=document.getElementById('chatInput');
  const sendChat=document.getElementById('sendChat');

  let leftCollapsed=false;
  let aiOpen=false;

  function isMobile(){ return window.innerWidth <= 800; }

  function setAI(open){
    aiOpen=!!open;
    ai.classList.toggle('closed',!aiOpen);
    ai.setAttribute('aria-hidden',String(!aiOpen));
    // Deliberately no focus() here. Opening the AI must not summon the mobile keyboard.
  }

  function setSidebarCollapsed(collapsed){
    leftCollapsed=!!collapsed;
    app.classList.toggle('left-collapsed',leftCollapsed);
    leftToggle.setAttribute('aria-label',leftCollapsed?'Expand navigation':'Collapse navigation');
  }

  function closeDrawer(){
    left.classList.remove('mobile-open');
    overlay.classList.remove('show');
  }

  function syncResponsive(){
    if(isMobile()){
      app.classList.remove('left-collapsed');
      overlay.classList.toggle('show',left.classList.contains('mobile-open'));
    }else{
      closeDrawer();
    }
  }

  function navigate(page){
    const url=new URL(window.top.location.href);
    if(page==='kinerja') url.searchParams.delete('page');
    else url.searchParams.set('page',page);
    window.top.location.href=url.toString();
  }

  document.querySelectorAll('.nav-item[data-page]').forEach(item=>{
    item.addEventListener('click',()=>navigate(item.dataset.page));
    item.addEventListener('keydown',e=>{
      if(e.key==='Enter'||e.key===' '){e.preventDefault();navigate(item.dataset.page);}
    });
  });

  leftToggle.addEventListener('click',()=>{
    if(isMobile()){
      left.classList.toggle('mobile-open');
      overlay.classList.toggle('show',left.classList.contains('mobile-open'));
    }else{
      setSidebarCollapsed(!leftCollapsed);
    }
  });

  if(aiClose) aiClose.addEventListener('click',()=>setAI(false));
  if(desktopAI) desktopAI.addEventListener('click',()=>setAI(true));
  if(mobileAI) mobileAI.addEventListener('click',()=>setAI(true));

  mobileMenu.addEventListener('click',()=>{
    left.classList.toggle('mobile-open');
    overlay.classList.toggle('show',left.classList.contains('mobile-open'));
  });

  overlay.addEventListener('click',closeDrawer);
  window.addEventListener('resize',syncResponsive);

  function appendMessage(text,user){
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
    return text.replace(/[<>&"]/g,function(s){
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
    const text=chatInput.value.trim();
    if(!text)return;
    appendMessage(text,true);
    chatInput.value='';
    setTimeout(()=>appendMessage(dummyResponse(text),false),450);
  }

  sendChat.addEventListener('click',send);
  chatInput.addEventListener('keydown',e=>{
    if(e.key==='Enter'){e.preventDefault();send();}
  });

  // Required initial state.
  setSidebarCollapsed(false);
  setAI(false);
  syncResponsive();
})();