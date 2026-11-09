(() => {
  'use strict';

  function sentenceAt(timings, time) {
    if (!Array.isArray(timings) || !Number.isFinite(time)) return null;
    const index = timings.findIndex(item => item && Number.isFinite(item.start) &&
      Number.isFinite(item.end) && item.start >= 0 && item.end > item.start &&
      time >= item.start && time < item.end);
    if (index < 0) return null;
    const { start, end } = timings[index];
    return { index, progress: (time - start) / (end - start) * 100 };
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { sentenceAt };
  if (typeof document === 'undefined') return;
  const audio = document.getElementById('interview-audio');
  const data = document.getElementById('sentence-timings');
  const follow = document.getElementById('follow-reading');
  if (!audio || !data) return;
  let timings;
  try { timings = JSON.parse(data.textContent); } catch (_) { return; }
  if (!timings || typeof timings !== 'object' || Array.isArray(timings)) return;
  let active = null;
  let activeKey = '';
  let animationFrame = null;

  function stopAnimation() {
    if (animationFrame !== null) window.cancelAnimationFrame(animationFrame);
    animationFrame = null;
  }

  function clear() {
    if (active) {
      active.classList.remove('is-reading');
      active.style.removeProperty('--reading-progress');
    }
    active = null;
    activeKey = '';
  }

  function followSentence(element) {
    if (!follow?.checked || audio.paused || window.getSelection()?.toString()) return;
    const rect = element.getBoundingClientRect();
    if (rect.bottom <= rect.top) return;
    const player = document.querySelector('.audio-player')?.getBoundingClientRect();
    const top = Math.max(16, player?.top <= 0 && player.bottom > 0 ? player.bottom + 16 : 16);
    if (rect.top >= top && rect.bottom <= window.innerHeight - 24) return;
    window.scrollBy({ top: rect.top - top,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
  }

  function update() {
    const source = (audio.getAttribute('src') || '').match(/(?:^|\/)((question|answer)-(\d{3}))\.mp3(?:[?#].*)?$/);
    if (!source || audio.ended || audio.error) { clear(); return; }
    const position = sentenceAt(timings[source[1]], audio.currentTime);
    if (!position) { clear(); return; }
    const card = document.getElementById(`question-${Number(source[3])}`);
    // Personal underline edits replace descendants: always resolve the live span.
    const sentence = card?.querySelector(`[data-speech-kind="${source[2]}"][data-sentence="${position.index}"]`);
    if (!sentence) { clear(); return; }
    const key = `${source[1]}:${position.index}`;
    const changed = activeKey !== key;
    if (active !== sentence) {
      clear();
      active = sentence;
    }
    activeKey = key;
    active.classList.add('is-reading');
    active.style.setProperty('--reading-progress', `${position.progress.toFixed(2)}%`);
    if (changed) followSentence(active);
  }

  function animate() {
    animationFrame = null;
    update();
    if (!audio.paused && !audio.ended && !audio.error &&
        !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      animationFrame = window.requestAnimationFrame(animate);
    }
  }

  audio.addEventListener('play', () => { stopAnimation(); animate(); });
  audio.addEventListener('pause', () => { stopAnimation(); update(); });
  for (const event of ['timeupdate', 'loadedmetadata', 'seeking', 'seeked']) {
    audio.addEventListener(event, update);
  }
  for (const event of ['emptied', 'ended', 'error', 'loadstart']) {
    audio.addEventListener(event, () => { stopAnimation(); clear(); });
  }
})();
