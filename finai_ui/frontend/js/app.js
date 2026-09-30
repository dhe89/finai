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
    if(!ai) return;
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
    if(!left || !overlay) return;
    left.classList.remove('mobile-open');
    overlay.classList.remove('show');
  }

  function syncResponsive(){
    if(isMobile()){
      app.classList.remove('left-collapsed');
      if(overlay){
        overlay.classList.toggle('show',!!left && left.classList.contains('mobile-open'));
      }
    }else{
      closeDrawer();
    }
  }

  // components.html runs in an iframe. Use the parent/top document for app
  // navigation, with fallbacks for browsers that restrict direct top navigation.
  function navigate(page){
    const current=window.location.href;
    const base=current.split('#')[0];
    const url=new URL(base, window.location.origin);
    if(page==='kinerja') url.searchParams.delete('page');
    else url.searchParams.set('page',page);

    const target=url.toString();
    try{
      window.top.location.assign(target);
      return;
    }catch(e){}
    try{
      window.parent.location.assign(target);
      return;
    }catch(e){}
    try{
      window.open(target,'_top');
    }catch(e){
      console.error('FinAI navigation failed:',e);
    }
  }

  function setTopQuery(params){
    const base=window.location.href.split('#')[0];
    const url=new URL(base, window.location.origin);
    Object.entries(params).forEach(([key,value])=>{
      if(value===null || value==='') url.searchParams.delete(key);
      else url.searchParams.set(key,value);
    });
    return url.toString();
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
      if(overlay) overlay.classList.toggle('show',left.classList.contains('mobile-open'));
    }else{
      setSidebarCollapsed(!leftCollapsed);
    }
  });

  if(aiClose) aiClose.addEventListener('click',()=>{
    setAI(false);
    try{
      const url=new URL(window.location.href);
      url.searchParams.delete('ai');
      window.history.replaceState({},'',url.toString());
    }catch(e){}
  });

  if(desktopAI) desktopAI.addEventListener('click',()=>setAI(true));
  if(mobileAI) mobileAI.addEventListener('click',()=>setAI(true));

  if(mobileMenu) mobileMenu.addEventListener('click',()=>{
    left.classList.toggle('mobile-open');
    if(overlay) overlay.classList.toggle('show',left.classList.contains('mobile-open'));
  });

  if(overlay) overlay.addEventListener('click',closeDrawer);
  window.addEventListener('resize',syncResponsive);

  function submitMessage(){
    if(!chatInput || !sendChat) return;
    const text=chatInput.value.trim();
    if(!text || sendChat.disabled) return;

    // Keep the overlay open while Python processes the message.
    setAI(true);
    sendChat.disabled=true;
    chatInput.disabled=true;

    const nonce=String(Date.now())+'_'+Math.random().toString(36).slice(2);
    const target=setTopQuery({ai:'1',finai_q:text,finai_n:nonce});

    // User activation is preserved here. Try parent/top navigation first,
    // then the _top browsing-context fallback.
    try{
      window.top.location.assign(target);
      return;
    }catch(e){}
    try{
      window.parent.location.assign(target);
      return;
    }catch(e){}
    try{
      window.open(target,'_top');
    }catch(e){
      sendChat.disabled=false;
      chatInput.disabled=false;
      console.error('FinAI chat transport failed:',e);
    }
  }

  if(sendChat) sendChat.addEventListener('click',submitMessage);
  if(chatInput) chatInput.addEventListener('keydown',e=>{
    if(e.key==='Enter'){
      e.preventDefault();
      submitMessage();
    }
  });

  // Never autofocus the chat input. This is especially important on mobile.
  setSidebarCollapsed(false);
  setAI(SERVER_AI_OPEN);
  syncResponsive();
})();