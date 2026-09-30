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
  const SERVER_AI_OPEN = false;
  const SERVER_PAGE = null;

  let leftCollapsed=false;
  let aiOpen=SERVER_AI_OPEN;

  function isMobile(){ return window.innerWidth <= 800; }

  function setAI(open){
    aiOpen=!!open;
    ai.classList.toggle('closed',!aiOpen);
    ai.setAttribute('aria-hidden',String(!aiOpen));
    if(aiOpen && chatBody){
      requestAnimationFrame(()=>{ chatBody.scrollTop=chatBody.scrollHeight; });
    }
  }

  function setSidebarCollapsed(collapsed){
    leftCollapsed=!!collapsed;
    app.classList.toggle('left-collapsed',leftCollapsed);
    if(leftToggle){
      leftToggle.setAttribute('aria-label',leftCollapsed?'Expand navigation':'Collapse navigation');
    }
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

  function clearAiQueryParam(){
    try{
      const url=new URL(window.top.location.href);
      url.searchParams.delete('ai');
      window.top.history.replaceState({},'',url.toString());
    }catch(e){}
  }

  document.querySelectorAll('.nav-item[data-page]').forEach(item=>{
    item.addEventListener('click',()=>navigate(item.dataset.page));
    item.addEventListener('keydown',e=>{
      if(e.key==='Enter'||e.key===' '){e.preventDefault();navigate(item.dataset.page);}
    });
  });

  if(leftToggle) leftToggle.addEventListener('click',()=>{
    if(isMobile()){
      left.classList.toggle('mobile-open');
      overlay.classList.toggle('show',left.classList.contains('mobile-open'));
    }else{
      setSidebarCollapsed(!leftCollapsed);
    }
  });

  if(aiClose) aiClose.addEventListener('click',()=>{
    setAI(false);
    clearAiQueryParam();
  });

  if(desktopAI) desktopAI.addEventListener('click',()=>setAI(true));
  if(mobileAI) mobileAI.addEventListener('click',()=>setAI(true));

  if(mobileMenu) mobileMenu.addEventListener('click',()=>{
    left.classList.toggle('mobile-open');
    overlay.classList.toggle('show',left.classList.contains('mobile-open'));
  });

  if(overlay) overlay.addEventListener('click',closeDrawer);
  window.addEventListener('resize',syncResponsive);

  function submitMessage(){
    const text=chatInput.value.trim();
    if(!text || sendChat.disabled) return;

    // Keep the overlay visible while Streamlit processes the request.
    setAI(true);
    sendChat.disabled=true;
    chatInput.disabled=true;

    const url=new URL(window.top.location.href);
    url.searchParams.set('ai','1');
    url.searchParams.set('finai_q',text);
    url.searchParams.set('finai_n',String(Date.now())+'_'+Math.random().toString(36).slice(2));

    // The message is rendered server-side on the next app run, so the user
    // bubble and AI reply persist after the component iframe is recreated.
    window.top.location.href=url.toString();
  }

  if(sendChat) sendChat.addEventListener('click',submitMessage);
  if(chatInput) chatInput.addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      e.preventDefault();
      submitMessage();
    }
  });

  // IMPORTANT: do not focus the input automatically on mobile. That used to
  // open the keyboard and make the AI overlay appear visually broken.
  setSidebarCollapsed(false);
  setAI(SERVER_AI_OPEN);
  syncResponsive();
})();
