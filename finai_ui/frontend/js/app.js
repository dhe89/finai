export default function(component) {
  const { data, setStateValue, setTriggerValue, parentElement } = component;
  const root = parentElement;
  const shell = root && root.querySelector ? root.querySelector('#finai-root') : null;
  const app = root && root.querySelector ? root.querySelector('#app') : null;
  const left = root && root.querySelector ? root.querySelector('#left') : null;
  const ai = root && root.querySelector ? root.querySelector('#ai') : null;
  const chatBody = root && root.querySelector ? root.querySelector('#chatBody') : null;

  if (!root || !shell || !app || !left || !ai) return;
  const qs = (selector) => root.querySelector(selector);

  function updateViewportOffset() {
    const shellRect = shell.getBoundingClientRect();
    const appRect = app.getBoundingClientRect();
    const mobile = shellRect.width <= 800;
    const header = qs('.mobile-head');
    const shellTop = Math.max(0, appRect.top - shellRect.top);
    const appHeight = Math.max(320, appRect.height);
    const mobileHeaderHeight = mobile && header ? Math.max(0, header.getBoundingClientRect().height) : 0;
    const aiTop = mobile ? shellTop + mobileHeaderHeight : shellTop;
    const aiHeight = Math.max(320, appHeight - (mobile ? mobileHeaderHeight : 0));
    shell.style.setProperty('--finai-ai-top', `${aiTop}px`);
    shell.style.setProperty('--finai-ai-height', `${aiHeight}px`);
    const nativeHeader = document.querySelector('header[data-testid="stHeader"], [data-testid="stHeader"]');
    const nativeHeaderBottom = nativeHeader ? Math.max(0, nativeHeader.getBoundingClientRect().bottom) : 0;
    const topOffset = mobile ? nativeHeaderBottom : Math.max(0, shellRect.top);
    shell.style.setProperty('--finai-top-offset', `${topOffset}px`);
    shell.style.setProperty('--finai-vh', `${Math.max(320, window.innerHeight - topOffset)}px`);
  }

  function isMobile() {
    return shell && typeof shell.getBoundingClientRect === 'function'
      ? shell.getBoundingClientRect().width <= 800
      : window.matchMedia('(max-width: 800px)').matches;
  }

  function applyResponsiveMode() {
    const mobile = isMobile();
    shell.classList.toggle('finai-mobile', mobile);
    if (!mobile) {
      left.classList.remove('mobile-open');
      const overlay = qs('#mobileOverlay');
      if (overlay) { overlay.classList.remove('show'); overlay.setAttribute('aria-hidden', 'true'); }
    }
  }

  function applyActivePage() {
    const currentPage = data && data.page ? String(data.page) : '';
    root.querySelectorAll('.nav-item[data-page]').forEach(item => {
      const active = item.dataset.page === currentPage;
      item.classList.toggle('active', active);
      item.setAttribute('aria-current', active ? 'page' : 'false');
    });
  }

  function setAI(open) {
    ai.classList.toggle('closed', !open);
    ai.setAttribute('aria-hidden', String(!open));
    const floatingAI = qs('#floatingAI');
    if (floatingAI) floatingAI.hidden = Boolean(open);
    if (open && chatBody) requestAnimationFrame(() => { chatBody.scrollTop = chatBody.scrollHeight; });
  }

  function closeDrawer() {
    left.classList.remove('mobile-open');
    const overlay = qs('#mobileOverlay');
    if (overlay) { overlay.classList.remove('show'); overlay.setAttribute('aria-hidden', 'true'); }
  }

  function openDrawer() {
    if (!isMobile()) return;
    left.classList.add('mobile-open');
    const overlay = qs('#mobileOverlay');
    if (overlay) { overlay.classList.add('show'); overlay.setAttribute('aria-hidden', 'false'); }
  }

  function toggleDrawer() { left.classList.contains('mobile-open') ? closeDrawer() : openDrawer(); }

  function setCollapsed(collapsed) {
    shell.classList.toggle('desktop-collapsed', collapsed);
    shell.dataset.leftCollapsed = collapsed ? '1' : '0';
    const toggle = qs('#leftToggle');
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(!collapsed));
      toggle.setAttribute('aria-label', collapsed ? 'Expand navigation' : 'Collapse navigation');
      toggle.setAttribute('title', collapsed ? 'Expand navigation' : 'Collapse navigation');
      if (!isMobile()) toggle.textContent = collapsed ? '›' : '☰';
    }
  }

  function bindNavigation() {
    const periodSelect = qs('#periodSelect');
    if (periodSelect) {
      const serverPeriod = data && data.period ? String(data.period) : '';
      if (serverPeriod && periodSelect.value !== serverPeriod) periodSelect.value = serverPeriod;
      if (periodSelect.dataset.finaiPeriodBound !== '1') {
        periodSelect.dataset.finaiPeriodBound = '1';
        periodSelect.addEventListener('change', () => { if (periodSelect.value) setStateValue('period', periodSelect.value); });
      }
    }
    root.querySelectorAll('.nav-item[data-page]').forEach(item => {
      if (item.dataset.finaiBound === '1') return;
      item.dataset.finaiBound = '1';
      const go = () => { closeDrawer(); closeHeaderDropdowns(); setStateValue('navigate', item.dataset.page); };
      item.addEventListener('click', go);
      item.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });
  }

  function closeHeaderDropdowns() {
    root.querySelectorAll('.topnav-actions details[open], .mobile-user-actions details[open]').forEach(d => d.removeAttribute('open'));
  }

  function bindHeaderDropdowns() {
    if (shell.dataset.finaiHeaderDropdownsBound === '1') return;
    shell.dataset.finaiHeaderDropdownsBound = '1';

    // Native <details> toggling is used for reliable open/close state. Any
    // click outside the currently open menu closes it immediately. Clicking
    // the other header button switches menus instead of leaving both open.
    document.addEventListener('pointerdown', event => {
      const target = event.target;
      const insideShell = shell.contains(target);
      const detail = target.closest && target.closest('.topnav-actions details, .mobile-user-actions details');
      const open = shell.querySelector('.topnav-actions details[open], .mobile-user-actions details[open]');
      if (!insideShell || !detail) {
        if (open) open.removeAttribute('open');
        return;
      }
      if (target.closest('.menu-item')) {
        closeHeaderDropdowns();
        return;
      }
      if (open && open !== detail) open.removeAttribute('open');
    }, true);

    root.addEventListener('click', event => {
      if (event.target.closest('.nav-item, #mobileMenu, #leftToggle, #mobileOverlay, #desktopAI, #mobileAI, #floatingAI, #aiClose')) {
        closeHeaderDropdowns();
      }
    }, true);

    root.addEventListener('toggle', event => {
      if (!event.target.matches('.topnav-actions details, .mobile-user-actions details') || !event.target.open) return;
      root.querySelectorAll('.topnav-actions details[open], .mobile-user-actions details[open]').forEach(d => {
        if (d !== event.target) d.removeAttribute('open');
      });
    }, true);
  }

  function appendOptimisticUser(text) {
    if (!chatBody) return;
    const welcome = chatBody.querySelector('.msg.welcome');
    if (welcome) welcome.remove();
    const user = document.createElement('div'); user.className = 'msg user optimistic-user';
    const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.textContent = text; user.appendChild(bubble); chatBody.appendChild(user);
    const typing = document.createElement('div'); typing.className = 'msg typing-msg optimistic-typing';
    typing.innerHTML = '<div class="bot">✦</div><div class="typing-bubble" aria-label="AI sedang menganalisis"><span></span><span></span><span></span></div>';
    chatBody.appendChild(typing);
    requestAnimationFrame(() => { chatBody.scrollTop = chatBody.scrollHeight; });
  }

  function bindButtons() {
    if (shell.dataset.finaiEventsBound === '1') return;
    shell.dataset.finaiEventsBound = '1';
    root.addEventListener('click', event => {
      const toggle = event.target.closest('#leftToggle');
      if (toggle && root.contains(toggle)) { event.preventDefault(); event.stopPropagation(); closeHeaderDropdowns(); if (isMobile()) toggleDrawer(); else setCollapsed(!shell.classList.contains('desktop-collapsed')); return; }
      const mobileMenu = event.target.closest('#mobileMenu');
      if (mobileMenu && root.contains(mobileMenu)) { event.preventDefault(); closeHeaderDropdowns(); toggleDrawer(); return; }
      const overlay = event.target.closest('#mobileOverlay');
      if (overlay && root.contains(overlay)) { closeDrawer(); closeHeaderDropdowns(); return; }
      const desktopAI = event.target.closest('#desktopAI'), mobileAI = event.target.closest('#mobileAI'), floatingAI = event.target.closest('#floatingAI');
      if ((desktopAI || mobileAI || floatingAI) && root.contains(desktopAI || mobileAI || floatingAI)) { event.preventDefault(); closeHeaderDropdowns(); setTriggerValue('ai', {action:'open'}); return; }
      const aiClose = event.target.closest('#aiClose');
      if (aiClose && root.contains(aiClose)) { event.preventDefault(); closeHeaderDropdowns(); setTriggerValue('ai', {action:'close'}); return; }
    });
    root.addEventListener('keydown', event => {
      const toggle = event.target.closest('#leftToggle');
      if (toggle && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); closeHeaderDropdowns(); if (isMobile()) toggleDrawer(); else setCollapsed(!shell.classList.contains('desktop-collapsed')); }
    });
  }

  function bindChat() {
    const chatInput = qs('#chatInput'), sendChat = qs('#sendChat');
    if (!chatInput || !sendChat || sendChat.dataset.finaiBound === '1') return;
    sendChat.dataset.finaiBound = '1';
    function submit() {
      const text = chatInput.value.trim(); if (!text || sendChat.disabled) return;
      appendOptimisticUser(text); sendChat.disabled = true; chatInput.disabled = true; chatInput.value = ''; chatInput.placeholder = 'AI sedang menganalisis...';
      setTriggerValue('chat', {text, nonce: `${Date.now()}_${Math.random().toString(36).slice(2)}`});
    }
    sendChat.addEventListener('click', submit);
    chatInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); submit(); } });
  }

  applyActivePage();
  bindNavigation();
  bindHeaderDropdowns();
  bindButtons();
  bindChat();
  setAI(Boolean(data && data.ai_open));
  if (shell.dataset.leftCollapsed === undefined) shell.dataset.leftCollapsed = '0';
  setCollapsed(shell.dataset.leftCollapsed === '1');
  updateViewportOffset();
  applyResponsiveMode();
  if (shell.dataset.finaiResizeBound !== '1') {
    shell.dataset.finaiResizeBound = '1';
    window.addEventListener('resize', () => { updateViewportOffset(); applyResponsiveMode(); }, {passive:true});
  }
  requestAnimationFrame(() => { updateViewportOffset(); applyResponsiveMode(); });
}
