export default function(component) {
  const { data, setTriggerValue, parentElement } = component;
  const root = parentElement;
  const app = root.querySelector('#app');
  const left = root.querySelector('#left');
  const ai = root.querySelector('#ai');
  const chatBody = root.querySelector('#chatBody');

  if (!app || !left || !ai) return;

  const shell = app;
  const qs = (selector) => shell.querySelector(selector);

  function updateViewportOffset() {
    const nativeHeader = document.querySelector(
      'header[data-testid="stHeader"], [data-testid="stHeader"]'
    );
    const headerBottom = nativeHeader
      ? Math.max(0, nativeHeader.getBoundingClientRect().bottom)
      : 0;
    // The component is rendered below Streamlit's native toolbar.
    // Use only the native header bottom as the fixed-UI offset. Using the
    // component/root position here would change when the page scrolls and
    // can also be a non-HTMLElement in Components V2, which has no .style.
    const topOffset = headerBottom;
    const viewportHeight = Math.max(320, window.innerHeight - topOffset);

    app.style.setProperty('--finai-top-offset', `${topOffset}px`);
    app.style.setProperty('--finai-vh', `${viewportHeight}px`);
  }

  function isMobile() {
    // Components V2 can report a viewport width that differs from the
    // browser's media-query viewport on mobile. Use the actual component
    // width so the shell switches reliably to the mobile layout.
    const width = shell.getBoundingClientRect().width;
    return width <= 800;
  }

  function applyResponsiveMode() {
    shell.classList.toggle('finai-mobile', isMobile());
  }

  function applyActivePage() {
    const currentPage = data && data.page ? String(data.page) : '';
    shell.querySelectorAll('.nav-item[data-page]').forEach(item => {
      const active = item.dataset.page === currentPage;
      item.classList.toggle('active', active);
      item.setAttribute('aria-current', active ? 'page' : 'false');
    });
  }

  function setAI(open) {
    ai.classList.toggle('closed', !open);
    ai.setAttribute('aria-hidden', String(!open));
    if (open && chatBody) {
      requestAnimationFrame(() => {
        chatBody.scrollTop = chatBody.scrollHeight;
      });
    }
  }

  function closeDrawer() {
    left.classList.remove('mobile-open');
    const overlay = qs('#mobileOverlay');
    if (overlay) {
      overlay.classList.remove('show');
      overlay.setAttribute('aria-hidden', 'true');
    }
  }

  function openDrawer() {
    left.classList.add('mobile-open');
    const overlay = qs('#mobileOverlay');
    if (overlay) {
      overlay.classList.add('show');
      overlay.setAttribute('aria-hidden', 'false');
    }
  }

  function toggleDrawer() {
    if (left.classList.contains('mobile-open')) closeDrawer();
    else openDrawer();
  }

  function setCollapsed(collapsed) {
    app.classList.toggle('left-collapsed', collapsed);
    app.dataset.leftCollapsed = collapsed ? '1' : '0';
    const toggle = qs('#leftToggle');
    if (toggle) {
      toggle.setAttribute('aria-expanded', String(!collapsed));
      toggle.setAttribute(
        'aria-label',
        collapsed ? 'Expand navigation' : 'Collapse navigation'
      );
      toggle.setAttribute(
        'title',
        collapsed ? 'Expand navigation' : 'Collapse navigation'
      );
      // A compact chevron avoids the toggle colliding with the centered logo
      // when the desktop sidebar is collapsed.
      if (!isMobile()) toggle.textContent = collapsed ? '›' : '☰';
    }
  }

  function bindNavigation() {
    shell.querySelectorAll('.nav-item[data-page]').forEach(item => {
      if (item.dataset.finaiBound === '1') return;
      item.dataset.finaiBound = '1';

      const go = () => {
        closeDrawer();
        setTriggerValue('navigate', item.dataset.page);
      };

      item.addEventListener('click', go);
      item.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          go();
        }
      });
    });
  }

  function appendOptimisticUser(text) {
    if (!chatBody) return;

    // Remove the welcome state once the first real message is sent.
    const welcome = chatBody.querySelector('.msg.welcome');
    if (welcome) welcome.remove();

    const user = document.createElement('div');
    user.className = 'msg user optimistic-user';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = text;
    user.appendChild(bubble);
    chatBody.appendChild(user);

    const typing = document.createElement('div');
    typing.className = 'msg typing-msg optimistic-typing';
    typing.innerHTML =
      '<div class="bot">✦</div>' +
      '<div class="typing-bubble" aria-label="AI sedang menganalisis">' +
      '<span></span><span></span><span></span>' +
      '</div>';
    chatBody.appendChild(typing);

    requestAnimationFrame(() => {
      chatBody.scrollTop = chatBody.scrollHeight;
    });
  }

  function bindButtons() {
    // Delegated handler is intentional: it remains reliable when Streamlit
    // updates/reuses the component DOM after a rerun.
    if (app.dataset.finaiEventsBound !== '1') {
      app.dataset.finaiEventsBound = '1';

      shell.addEventListener('click', event => {
        const toggle = event.target.closest('#leftToggle');
        if (toggle && shell.contains(toggle)) {
          event.preventDefault();
          event.stopPropagation();

          if (isMobile()) {
            toggleDrawer();
          } else {
            const collapsed = !app.classList.contains('left-collapsed');
            setCollapsed(collapsed);
          }
          return;
        }

        const mobileMenu = event.target.closest('#mobileMenu');
        if (mobileMenu && shell.contains(mobileMenu)) {
          event.preventDefault();
          toggleDrawer();
          return;
        }

        const overlay = event.target.closest('#mobileOverlay');
        if (overlay && shell.contains(overlay)) {
          closeDrawer();
          return;
        }

        const desktopAI = event.target.closest('#desktopAI');
        const mobileAI = event.target.closest('#mobileAI');
        if ((desktopAI || mobileAI) && shell.contains(desktopAI || mobileAI)) {
          event.preventDefault();
          setTriggerValue('ai', {action:'open'});
          return;
        }

        const aiClose = event.target.closest('#aiClose');
        if (aiClose && shell.contains(aiClose)) {
          event.preventDefault();
          setTriggerValue('ai', {action:'close'});
          return;
        }
      });

      shell.addEventListener('keydown', event => {
        const toggle = event.target.closest('#leftToggle');
        if (toggle && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          if (isMobile()) toggleDrawer();
          else setCollapsed(!app.classList.contains('left-collapsed'));
        }
      });
    }
  }

  function bindNavigationClicks() {
    // Navigation is bound separately because it changes Streamlit state.
    bindNavigation();
  }

  function bindChat() {
    const chatInput = qs('#chatInput');
    const sendChat = qs('#sendChat');
    if (!chatInput || !sendChat || sendChat.dataset.finaiBound === '1') return;

    sendChat.dataset.finaiBound = '1';

    function submit() {
      const text = chatInput.value.trim();
      if (!text || sendChat.disabled) return;

      // Render immediately in the browser before the Python/OpenRouter roundtrip.
      appendOptimisticUser(text);

      sendChat.disabled = true;
      chatInput.disabled = true;
      chatInput.value = '';
      chatInput.placeholder = 'AI sedang menganalisis...';

      setTriggerValue('chat', {
        text,
        nonce: `${Date.now()}_${Math.random().toString(36).slice(2)}`
      });
    }

    sendChat.addEventListener('click', submit);
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        submit();
      }
    });
  }

  applyActivePage();
  bindNavigationClicks();
  bindButtons();
  bindChat();
  setAI(Boolean(data && data.ai_open));

  // Preserve a client-side collapse state across component rerenders.
  if (app.dataset.leftCollapsed === undefined) {
    app.dataset.leftCollapsed = '0';
  }
  setCollapsed(app.dataset.leftCollapsed === '1');

  applyResponsiveMode();
  updateViewportOffset();

  if (!app.dataset.finaiResizeBound) {
    app.dataset.finaiResizeBound = '1';
    window.addEventListener('resize', () => {
      applyResponsiveMode();
      updateViewportOffset();
    }, {passive:true});
  }

  requestAnimationFrame(updateViewportOffset);
}
