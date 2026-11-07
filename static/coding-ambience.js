(() => {
  'use strict';
  const voice = document.getElementById('lessonAudio');
  const bed = document.getElementById('lessonAmbience');
  const toggle = document.getElementById('ambienceEnabled');
  const volume = document.getElementById('ambienceVolume');
  const label = document.getElementById('ambienceLevel');
  const notice = document.getElementById('ambienceStatus');
  const key = 'csCodingAmbience:v1';
  let enabled = true, level = 16, generation = 0;
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (typeof saved?.enabled === 'boolean') enabled = saved.enabled;
    if (Number.isFinite(saved?.level)) level = Math.max(0, Math.min(30, saved.level));
  } catch (_) { /* Storage is optional. */ }
  function render() {
    toggle.checked = enabled;
    volume.value = level;
    volume.disabled = !enabled;
    label.textContent = `${level}%`;
    bed.volume = level / 100;
  }
  function stop() { generation++; bed.pause(); }
  async function start() {
    stop();
    if (!enabled || !level || voice.paused || voice.ended || voice.muted || !voice.volume || document.hidden) return;
    const ticket = generation;
    try {
      await bed.play();
      if (ticket !== generation) return;
      if (voice.paused || document.hidden) bed.pause();
      else notice.textContent = '';
    } catch (_) {
      if (ticket === generation) notice.textContent = '배경음을 재생하지 못했어요. 배경음을 껐다 켜면 다시 시도합니다.';
    }
  }
  function save() {
    try { localStorage.setItem(key, JSON.stringify({enabled, level})); } catch (_) { /* Keep playback usable. */ }
  }
  toggle.onchange = () => {
    enabled = toggle.checked; notice.textContent = ''; render(); save(); start();
  };
  volume.oninput = () => {
    level = Math.max(0, Math.min(30, Number(volume.value) || 0));
    render(); save();
    if (!level) stop(); else if (bed.paused) start();
  };
  voice.addEventListener('playing', start);
  voice.addEventListener('volumechange', start);
  ['pause', 'ended', 'waiting', 'emptied', 'error'].forEach(event => voice.addEventListener(event, stop));
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
  window.addEventListener('pagehide', stop);
  bed.addEventListener('error', () => { stop(); notice.textContent = '배경음을 불러오지 못했어요. 강의는 계속 들을 수 있어요.'; });
  render();
})();
