(() => {
  'use strict';
  const data = window.EMMAUS_SCRIPTURE_PREVIEWS;
  if (!data?.passages) return;
  const selector = 'a[href^="https://www.bible.com/bible/46/"]';
  const card = document.createElement('aside');
  card.className = 'scripture-preview';
  card.id = 'scripturePreview';
  card.setAttribute('role', 'region');
  card.setAttribute('aria-label', '經文預覽');
  card.tabIndex = 0;
  card.hidden = true;
  card.innerHTML = '<div class="scripture-preview-head"><div><span class="scripture-preview-kicker">經文預覽</span><h2></h2></div><button class="scripture-preview-close" type="button" aria-label="關閉經文預覽">×</button></div><p class="scripture-preview-extent"></p><div class="scripture-preview-verses"></div><p class="scripture-preview-version"></p><a class="scripture-preview-open" target="_blank" rel="noopener noreferrer">開啟原經文網頁 ↗</a><span id="scripturePreviewHint" class="scripture-preview-sr-only">經文預覽已開啟。按向下鍵進入預覽，使用方向鍵或 Page Down 捲動，按 Escape 關閉。</span>';
  document.body.append(card);
  const status = document.createElement('span');
  status.className = 'scripture-preview-sr-only';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  document.body.append(status);
  const heading = card.querySelector('h2');
  const extent = card.querySelector('.scripture-preview-extent');
  const verses = card.querySelector('.scripture-preview-verses');
  const version = card.querySelector('.scripture-preview-version');
  const original = card.querySelector('.scripture-preview-open');
  const closeButton = card.querySelector('.scripture-preview-close');
  let activeLink = null;
  let pinned = false;
  let hoverTimer = 0;
  let hideTimer = 0;
  let press = null;
  let blockedClick = null;
  let blockedUntil = 0;
  let lastInput = 'keyboard';
  let returningFocus = false;
  let touchY = null;
  const touches = new Set();

  function linkAt(target) { return target instanceof Element && !card.contains(target) ? target.closest(selector) : null; }
  function reference(link) {
    const match = new URL(link.href).pathname.match(/^\/bible\/46\/([0-9A-Z]+)\.(\d+)(?:\.(\d+(?:-\d+)?))?\.CUNP-/);
    return match ? `${match[1]} ${match[2]}${match[3] ? ':' + match[3] : ''}` : null;
  }
  function stopTimers() { clearTimeout(hoverTimer); clearTimeout(hideTimer); }
  function cancelPress(closePreview = false) {
    if (press) {
      clearTimeout(press.timer);
      if (closePreview && press.triggered && activeLink === press.link) close();
    }
    card.classList.remove('is-pressing');
    press = null;
  }
  function close() {
    stopTimers();
    const restoreFocus = card.contains(document.activeElement);
    const previousLink = activeLink;
    if (activeLink) activeLink.removeAttribute('aria-describedby');
    card.hidden = true;
    card.classList.remove('is-pinned', 'is-above-touch', 'is-pressing');
    card.style.removeProperty('--preview-touch-space');
    activeLink = null;
    pinned = false;
    touchY = null;
    status.textContent = '';
    if (restoreFocus) {
      returningFocus = true;
      const target = previousLink?.isConnected ? previousLink : document.querySelector('#graphDetails, main');
      if (target) {
        if (!target.matches('a, button, input, select, textarea, [tabindex]')) target.tabIndex = -1;
        target.focus({ preventScroll: true });
      }
      returningFocus = false;
    }
  }
  function position() {
    if (!activeLink || card.hidden) return;
    if (pinned && window.innerWidth <= 640) {
      card.style.left = card.style.top = '';
      if (touchY !== null) {
        // Leave room for the held finger and mobile safe areas on either edge.
        const above = Math.max(0, touchY - 76);
        const below = Math.max(0, window.innerHeight - touchY - 76);
        card.classList.toggle('is-above-touch', above >= below);
        card.style.setProperty('--preview-touch-space', `${Math.max(above, below)}px`);
      } else {
        card.classList.remove('is-above-touch');
        card.style.removeProperty('--preview-touch-space');
      }
      return;
    }
    card.classList.remove('is-above-touch');
    card.style.removeProperty('--preview-touch-space');
    const anchor = activeLink.getBoundingClientRect();
    const width = card.offsetWidth;
    const height = card.offsetHeight;
    const left = Math.max(12, Math.min(anchor.left, window.innerWidth - width - 12));
    const below = anchor.bottom + 8;
    const top = below + height <= window.innerHeight - 12 ? below : Math.max(12, anchor.top - height - 8);
    card.style.left = `${left}px`;
    card.style.top = `${top}px`;
  }
  function open(link, pin = false, announce = false, pressY = null) {
    const ref = reference(link);
    const item = data.passages[ref];
    if (!item) return false;
    // Moving back onto the same active link must not reset a reader's position.
    if (activeLink === link && !card.hidden) {
      stopTimers();
      if (pin) {
        pinned = true;
        touchY = pressY;
        card.classList.add('is-pinned');
        position();
      }
      return true;
    }
    if (activeLink && activeLink !== link) activeLink.removeAttribute('aria-describedby');
    stopTimers();
    activeLink = link;
    pinned = pin;
    touchY = pin ? pressY : null;
    heading.textContent = item.label;
    const first = Number(ref.match(/:(\d+)/)?.[1] || 1);
    const end = Number(ref.match(/:(\d+)(?:-(\d+))?$/)?.slice(1).filter(Boolean).at(-1) || first + item.total - 1);
    const numbers = (item.verses || []).flatMap(verse => {
      if (Array.isArray(verse.coveredNumbers)) return verse.coveredNumbers;
      const range = /^(\d+)[–-](\d+)$/.exec(verse.numberLabel || '');
      return range ? Array.from({ length: Number(range[2]) - Number(range[1]) + 1 }, (_, i) => Number(range[1]) + i) : [verse.number];
    });
    const complete = Number.isInteger(item.total) && item.total > 0 && end - first + 1 === item.total
      && numbers.length === item.total && numbers.every((number, i) => number === first + i)
      && item.verses.every(verse => typeof verse.text === 'string' && verse.text.trim());
    extent.textContent = complete ? `全段 ${item.total} 節` : '預覽資料不完整，請重新整理；仍有問題時可開啟原經文網頁。';
    extent.classList.toggle('is-incomplete', !complete);
    verses.replaceChildren(...(complete ? item.verses : []).map(verse => {
      const row = document.createElement('p');
      row.className = 'scripture-preview-verse';
      const number = document.createElement('strong');
      number.textContent = verse.numberLabel || verse.number;
      const text = document.createElement('span');
      text.textContent = verse.text;
      row.append(number, text);
      return row;
    }));
    version.replaceChildren(document.createTextNode(`預覽：${data.source.label}。與外連的新標點版本文字可能不同。 `));
    const source = document.createElement('a');
    source.href = data.source.url;
    source.target = '_blank';
    source.rel = 'noopener noreferrer';
    source.textContent = '文字來源 ↗';
    version.append(source);
    original.href = link.href;
    card.classList.toggle('is-pinned', pin);
    card.hidden = false;
    card.scrollTop = 0;
    link.setAttribute('aria-describedby', 'scripturePreviewHint');
    position();
    if (announce) status.textContent = `${item.label} 經文預覽已開啟。按向下鍵進入預覽，按 Escape 關閉。`;
    return true;
  }
  function scheduleClose() {
    clearTimeout(hideTimer);
    if (!pinned) hideTimer = setTimeout(() => {
      if (!card.matches(':hover') && !activeLink?.matches(':hover') && !card.contains(document.activeElement)) close();
    }, 160);
  }

  document.addEventListener('pointerover', event => {
    if (event.pointerType === 'touch' || pinned) return;
    const link = linkAt(event.target);
    if (!link || link.contains(event.relatedTarget)) return;
    stopTimers();
    hoverTimer = setTimeout(() => open(link), 180);
  });
  document.addEventListener('pointerout', event => {
    if (event.pointerType === 'touch') return;
    const link = linkAt(event.target);
    if (link && !link.contains(event.relatedTarget)) {
      clearTimeout(hoverTimer);
      if (link === activeLink) scheduleClose();
    }
  });
  card.addEventListener('pointerenter', () => clearTimeout(hideTimer));
  card.addEventListener('pointerleave', scheduleClose);
  document.addEventListener('focusin', event => {
    if (returningFocus) return;
    if (card.contains(event.target)) return;
    const link = linkAt(event.target);
    if (link && lastInput === 'keyboard') open(link, false, true);
    else if (!pinned || lastInput === 'keyboard') close();
  });
  document.addEventListener('pointerdown', event => {
    lastInput = 'pointer';
    if (event.pointerType !== 'touch') return;
    blockedClick = null;
    touches.add(event.pointerId);
    if (touches.size > 1) { cancelPress(true); return; }
    const link = linkAt(event.target);
    if (!link || card.contains(event.target)) return;
    cancelPress();
    const next = { id: event.pointerId, link, x: event.clientX, y: event.clientY, timer: 0, triggered: false };
    next.timer = setTimeout(() => {
      if (press !== next) return;
      if (open(link, true, false, next.y)) {
        next.triggered = true;
        card.classList.add('is-pressing');
      }
    }, 480);
    press = next;
  }, true);
  document.addEventListener('pointermove', event => {
    if (press?.id === event.pointerId && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 12) cancelPress(true);
  }, true);
  function endTouch(event) {
    touches.delete(event.pointerId);
    if (press?.id !== event.pointerId) return;
    const triggered = press.triggered;
    const link = press.link;
    const x = press.x;
    const y = press.y;
    cancelPress();
    if (triggered) {
      // A browser may cancel the held pointer as the card appears; keep the preview open.
      blockedClick = { link, x, y };
      blockedUntil = performance.now() + 700;
      if (event.cancelable) event.preventDefault();
      closeButton.focus({ preventScroll: true });
    }
  }
  document.addEventListener('pointerup', endTouch, true);
  document.addEventListener('pointercancel', endTouch, true);
  document.addEventListener('contextmenu', event => {
    if (linkAt(event.target) && (press || (blockedClick && performance.now() < blockedUntil))) event.preventDefault();
  }, true);
  document.addEventListener('click', event => {
    if (blockedClick && performance.now() < blockedUntil && linkAt(event.target) === blockedClick.link && Math.hypot(event.clientX - blockedClick.x, event.clientY - blockedClick.y) < 32) {
      event.preventDefault();
      event.stopImmediatePropagation();
      blockedClick = null;
      return;
    }
    if (pinned && !card.contains(event.target)) close();
  }, true);
  document.addEventListener('keydown', event => {
    lastInput = 'keyboard';
    if (event.key === 'Escape' && !card.hidden) {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    if (event.key === 'ArrowDown' && event.target === activeLink && !card.hidden) {
      event.preventDefault();
      pinned = true;
      card.classList.add('is-pinned');
      position();
      card.focus({ preventScroll: true });
      return;
    }
    if (!card.hidden && card.contains(event.target)) {
      const step = Math.max(40, card.clientHeight - card.querySelector('.scripture-preview-head').offsetHeight - 24);
      const scroll = { ArrowDown: 40, ArrowUp: -40, PageDown: step, PageUp: -step, Home: -card.scrollHeight, End: card.scrollHeight }[event.key];
      if (scroll !== undefined) {
        event.preventDefault();
        card.scrollTop += scroll;
      }
    }
  });
  window.addEventListener('scroll', event => {
    if (card.contains(event.target)) return;
    cancelPress(true);
    if (!pinned && !card.hidden) close();
    else if (pinned) position();
  }, true);
  window.addEventListener('resize', position);
  closeButton.addEventListener('click', close);
})();
