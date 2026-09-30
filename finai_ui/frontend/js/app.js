export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const root = parentElement;
  const app = root.querySelector('#finai-root');
  const left = root.querySelector('#left');
  const ai = root.querySelector('#ai');
  const leftToggle = root.querySelector('#leftToggle');
  const aiClose = root.querySelector('#aiClose');
  const desktopAI = root.querySelector('#desktopAI');
  const mobileAI = root.querySelector('#mobileAI');
  const mobileMenu = root.querySelector('#mobileMenu');
  const chatBody = root.querySelector('#chatBody');
  const chatInput = root.querySelector('#chatInput');
  const sendChat = root.querySelector('#sendChat');
  const mobileOverlay = root.querySelector('#mobileOverlay');

  if (!app || !left || !ai) return;

  // The component is already rendered below Streamlit's native toolbar.
  // Do NOT use app.getBoundingClientRect().top as the fixed-element offset:
  // that value changes with the page position and was causing the mobile
  // header to appear in the middle of the dashboard after scrolling.
  function updateViewportOffset() {
    const nativeHeader = document.querySelector(
      'header[data-testid="stHeader"], [data-testid="stHeader"]'
    );
    const headerBottom = nativeHeader
      ? Math.max(0, nativeHeader.getBoundingClientRect().bottom)
      : 0;

    const offset = headerBottom;
    const viewportHeight = Math.max(320, window.innerHeight - offset);

    app.style.setProperty('--finai-top-offset', `${offset}px`);
    app.style.setProperty('--finai-vh', `${viewportHeight}px`);
  }

  function applyActivePage() {
    const currentPage = data && data.page ? String(data.page) : '';
    root.querySelectorAll('.nav-item[data-page]').forEach(item => {
      const active = item.dataset.page === currentPage;
      item.classList.toggle('active', active);
      item.setAttribute('aria-current', active ? 'page' : 'false');
    });
  }

  function isMobile() { return window.innerWidth <= 800; }

  function setAI(open) {
    ai.classList.toggle('closed', !open);
    ai.setAttribute('aria-hidden', String(!open));
    if (open && chatBody) {
      requestAnimationFrame(() => { chatBody.scrollTop = chatBody.scrollHeight; });
    }
  }

  function closeDrawer() {
    left.classList.remove('mobile-open');
    if (mobileOverlay) {
      mobileOverlay.classList.remove('show');
      mobileOverlay.setAttribute('aria-hidden', 'true');
    }
  }

  function openDrawer() {
    left.classList.add('mobile-open');
    if (mobileOverlay) {
      mobileOverlay.classList.add('show');
      mobileOverlay.setAttribute('aria-hidden', 'false');
    }
  }

  function toggleDrawer() {
    if (left.classList.contains('mobile-open')) closeDrawer();
    else openDrawer();
  }

  function bindNavigation() {
    root.querySelectorAll('.nav-item[data-page]').forEach(item => {
      if (item.dataset.finaiBound === '1') return;
      item.dataset.finaiBound = '1';
      const go = () => { closeDrawer(); setTriggerValue('navigate', item.dataset.page); };
      item.addEventListener('click', go);
      item.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); }
      });
    });
  }

  function bindButtons() {
    if (leftToggle && leftToggle.dataset.finaiBound !== '1') {
      leftToggle.dataset.finaiBound = '1';
      leftToggle.addEventListener('click', () => {
        if (isMobile()) toggleDrawer();
        else app.classList.toggle('left-collapsed');
      });
    }

    if (mobileMenu && mobileMenu.dataset.finaiBound !== '1') {
      mobileMenu.dataset.finaiBound = '1';
      mobileMenu.addEventListener('click', toggleDrawer);
    }


    if (mobileOverlay && mobileOverlay.dataset.finaiBound !== '1') {
      mobileOverlay.dataset.finaiBound = '1';
      mobileOverlay.addEventListener('click', closeDrawer);
    }

    if (desktopAI && desktopAI.dataset.finaiBound !== '1') {
      desktopAI.dataset.finaiBound = '1';
      desktopAI.addEventListener('click', () => setTriggerValue('ai', {action:'open'}));
    }

    if (mobileAI && mobileAI.dataset.finaiBound !== '1') {
      mobileAI.dataset.finaiBound = '1';
      mobileAI.addEventListener('click', () => setTriggerValue('ai', {action:'open'}));
    }

    if (aiClose && aiClose.dataset.finaiBound !== '1') {
      aiClose.dataset.finaiBound = '1';
      aiClose.addEventListener('click', () => setTriggerValue('ai', {action:'close'}));
    }
  }

  function bindChat() {
    if (!chatInput || !sendChat || sendChat.dataset.finaiBound === '1') return;
    sendChat.dataset.finaiBound = '1';

    function submit() {
      const text = chatInput.value.trim();
      if (!text || sendChat.disabled) return;
      sendChat.disabled = true;
      chatInput.disabled = true;
      setTriggerValue('chat', {
        text,
        nonce: `${Date.now()}_${Math.random().toString(36).slice(2)}`
      });
    }

    sendChat.addEventListener('click', submit);
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); submit(); }
    });
  }

  applyActivePage();
  bindNavigation();
  bindButtons();
  bindChat();
  setAI(Boolean(data && data.ai_open));
  updateViewportOffset();
  window.addEventListener('resize', updateViewportOffset, {passive:true});
  requestAnimationFrame(updateViewportOffset);
}
