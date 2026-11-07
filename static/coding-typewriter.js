(() => {
  'use strict';
  const preference = 'csCodingTyping:v1';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const toggle = document.getElementById('lessonTyping');
  const segmenter = typeof Intl.Segmenter === 'function' ? new Intl.Segmenter('ko', {granularity: 'grapheme'}) : null;
  const characters = text => segmenter ? Array.from(segmenter.segment(text), part => part.segment) : Array.from(text);
  let enabled = true;
  try { enabled = localStorage.getItem(preference) !== 'off'; } catch (_) { /* Optional preference. */ }
  toggle.checked = enabled;
  toggle.onchange = () => {
    enabled = toggle.checked;
    try { localStorage.setItem(preference, enabled ? 'on' : 'off'); } catch (_) { /* Optional preference. */ }
    document.getElementById('lessonAudio').dispatchEvent(new Event('timeupdate'));
  };
  reduce.addEventListener?.('change', () => document.getElementById('lessonAudio').dispatchEvent(new Event('timeupdate')));
  const cache = new WeakMap();
  function count(text, time, start, end) {
    const length = characters(text).length;
    if (!enabled || reduce.matches) return length;
    const duration = Math.min(1.2, Math.max(.2, length * .018), Math.max(.01, end - start) * .35);
    const progress = Math.max(0, Math.min(1, (time - start) / duration));
    return Math.min(length, Math.floor(8 + (length - Math.min(8, length)) * progress));
  }
  function render(element, text, time, start, end) {
    let state = cache.get(element);
    if (!state || state.text !== text || state.front.parentNode !== element) {
      const front = document.createElement('span'), remainder = document.createElement('span');
      front.setAttribute('aria-hidden', 'true'); remainder.setAttribute('aria-hidden', 'true');
      remainder.className = 'typing-remainder';
      element.replaceChildren(front, remainder);
      element.setAttribute('aria-label', text);
      state = {text, front, remainder, parts: characters(text), shown: -1};
      cache.set(element, state);
    }
    const shown = count(text, time, start, end);
    if (shown === state.shown) return;
    state.front.textContent = state.parts.slice(0, shown).join('');
    state.remainder.textContent = state.parts.slice(shown).join('');
    state.shown = shown;
  }
  window.CodingTypewriter = {count, characters, render};
})();
