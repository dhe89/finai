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

  if (!app || !left || !ai) return;

  // Streamlit's native toolbar/header sits above the component. Fixed elements
  // inside the component must start below the actual component top, otherwise
  // the AI overlay can visually cover the Streamlit header.
  function updateViewportOffset() {
    const rect = app.getBoundingClientRect();
    const offset = Math.max(0, rect.top);
    app.style.setProperty('--finai-top-offset', `${offset}px`);
    app.style.setProperty('--finai-vh', `${Math.max(320, window.innerHeight - offset)}px`);
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
  }

  function bindNavigation() {
    root.querySelectorAll('.nav-item[data-page]').forEach(item => {
      if (item.dataset.finaiBound === '1') return;
      item.dataset.finaiBound = '1';
      const go = () => setTriggerValue('navigate', item.dataset.page);
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
        if (isMobile()) left.classList.toggle('mobile-open');
        else app.classList.toggle('left-collapsed');
      });
    }

    if (mobileMenu && mobileMenu.dataset.finaiBound !== '1') {
      mobileMenu.dataset.finaiBound = '1';
      mobileMenu.addEventListener('click', () => left.classList.toggle('mobile-open'));
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

  bindNavigation();
  bindButtons();
  bindChat();
  setAI(Boolean(data && data.ai_open));
  updateViewportOffset();
  window.addEventListener('resize', updateViewportOffset, {passive:true});
  requestAnimationFrame(updateViewportOffset);
}
