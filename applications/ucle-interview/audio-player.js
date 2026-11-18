(() => {
  'use strict';
  const study = window.UcleStudy;
  const $ = id => document.getElementById(id);
  const audio = $('voice-audio');
  if (!study || !audio) return;
  const panel = $('voice-panel');
  const playButton = $('voice-play');
  const restartButton = $('voice-restart');
  const rate = $('voice-rate');
  const automatic = $('voice-auto');
  const status = $('voice-status');
  const key = 'ucle-interview-voice-v1';
  const rates = [0.8, 1, 1.2, 1.5];
  let previous = study.snapshot();
  let manifestPromise = null;
  let tracks = new Map();
  let track = null;
  let generation = 0;
  let wanted = false;
  let phase = 'idle';
  let revealedStep = -1;

  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (rates.includes(saved?.rate)) rate.value = String(saved.rate);
    if (typeof saved?.automatic === 'boolean') automatic.checked = saved.automatic;
  } catch (_) { /* Playback remains usable when preferences cannot be read. */ }
  if (!rates.includes(Number(rate.value))) rate.value = '1';
  function savePreferences() {
    try { localStorage.setItem(key, JSON.stringify({ rate: Number(rate.value), automatic: automatic.checked })); }
    catch (_) { /* Preferences are optional; never block listening. */ }
  }
  function controls() {
    const state = study.snapshot();
    const available = !state.paused && state.ids.includes(state.current);
    panel.hidden = state.paused;
    playButton.disabled = !available;
    restartButton.disabled = !available;
    playButton.textContent = wanted ? '일시정지' : phase === 'paused' ? '이어서 듣기'
      : ['ended', 'error'].includes(phase) ? '다시 듣기' : '음성으로 시작하기';
    playButton.setAttribute('aria-pressed', String(wanted));
  }
  function setStatus(message) { status.textContent = message; controls(); }
  function fail(token) {
    if (token !== generation) return;
    generation += 1;
    wanted = false;
    phase = 'error';
    audio.pause();
    setStatus('음성을 불러오거나 재생하지 못했어요. 재생 버튼을 눌러 다시 시도해 주세요.');
  }
  function manifest() {
    if (!manifestPromise) {
      manifestPromise = fetch('audio/manifest.json').then(response => {
        if (!response.ok) throw new Error('manifest unavailable');
        return response.json();
      }).then(data => {
        const entries = new Map();
        if (!Array.isArray(data.tracks) || !data.tracks.length) throw new Error('empty manifest');
        for (const item of data.tracks) {
          if (!Number.isInteger(item.id) || item.id < 1 || entries.has(item.id)
              || item.path !== `audio/question-${String(item.id).padStart(3, '0')}.mp3`
              || !Number.isFinite(item.duration) || item.duration <= 0
              || !Array.isArray(item.sections) || item.sections.length !== 4) throw new Error('invalid track');
          let end = 0;
          item.sections.forEach((section, index) => {
            if (section.step !== index || !Number.isFinite(section.start) || !Number.isFinite(section.end)
                || section.start < end || section.end <= section.start || section.end > item.duration) throw new Error('invalid timing');
            end = section.end;
          });
          entries.set(item.id, item);
        }
        tracks = entries;
        return entries;
      }).catch(error => { manifestPromise = null; throw error; });
    }
    return manifestPromise;
  }
  function syncSection() {
    if (!track || phase === 'error') return;
    const item = tracks.get(track.id);
    if (!item) return;
    let step = 0;
    for (const section of item.sections) if (audio.currentTime >= section.start) step = section.step;
    if (step !== revealedStep) { revealedStep = step; study.reveal(step); }
  }
  function loadTimings(token) {
    manifest().then(entries => {
      if (token !== generation || !track) return;
      if (!entries.has(track.id)) { fail(token); return; }
      syncSection();
    }).catch(() => fail(token));
  }
  function stop(message) {
    generation += 1;
    wanted = false;
    phase = 'idle';
    track = null;
    revealedStep = -1;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    setStatus(message);
  }
  function pause() {
    generation += 1;
    wanted = false;
    phase = 'paused';
    audio.pause();
    setStatus('일시정지했어요. 재생을 누르면 이어서 들을 수 있어요.');
  }
  function start(restart = false) {
    const state = study.snapshot();
    if (state.paused || !state.ids.includes(state.current)) return;
    const token = ++generation;
    const reset = restart || !track || track.id !== state.current || phase === 'error' || audio.ended;
    wanted = false;
    phase = 'loading';
    if (reset) {
      audio.pause();
      track = { id: state.current };
      revealedStep = 0;
      study.reveal(0);
      audio.src = `audio/question-${String(track.id).padStart(3, '0')}.mp3`;
      audio.load();
    }
    wanted = true;
    audio.defaultPlaybackRate = Number(rate.value);
    audio.playbackRate = Number(rate.value);
    setStatus(`${state.current}번 · 음성을 불러오고 있어요.`);
    // Start within the click gesture; loading metadata must not consume mobile activation.
    try {
      Promise.resolve(audio.play()).then(() => {
        if (token !== generation) { if (!wanted) audio.pause(); return; }
        if (!audio.paused && phase !== 'error') {
          phase = 'playing';
          setStatus(`${track.id}번 · 질문과 답변을 듣고 있어요.`);
        }
      }).catch(() => fail(token));
    } catch (_) { fail(token); }
    loadTimings(token);
  }
  playButton.addEventListener('click', () => { if (wanted) pause(); else start(); });
  restartButton.addEventListener('click', () => start(true));
  rate.addEventListener('change', () => {
    if (!rates.includes(Number(rate.value))) rate.value = '1';
    audio.defaultPlaybackRate = Number(rate.value);
    audio.playbackRate = Number(rate.value);
    savePreferences();
  });
  automatic.addEventListener('change', savePreferences);
  audio.addEventListener('play', () => {
    if (audio.paused) return;
    const state = study.snapshot();
    if (!track || state.paused || state.current !== track.id || !state.ids.includes(track.id)) {
      stop('현재 질문에서 재생 버튼을 눌러 주세요.'); return;
    }
    if (!wanted) { generation += 1; wanted = true; loadTimings(generation); }
    phase = 'playing';
    setStatus(`${track.id}번 · 질문과 답변을 듣고 있어요.`);
  });
  audio.addEventListener('pause', () => {
    if (audio.paused && !audio.ended && wanted && phase !== 'error') pause();
  });
  audio.addEventListener('error', () => { if (track && audio.error) fail(generation); });
  audio.addEventListener('timeupdate', syncSection);
  audio.addEventListener('seeked', syncSection);
  audio.addEventListener('ended', () => {
    if (!track || !audio.ended || !wanted || phase === 'error') return;
    const state = study.snapshot();
    const index = state.ids.indexOf(track.id);
    if (state.paused || state.current !== track.id || index < 0) { stop('재생을 멈췄어요.'); return; }
    if (!tracks.has(track.id)) { fail(generation); return; }
    wanted = false;
    phase = 'ended';
    if (automatic.checked && index + 1 < state.ids.length) {
      study.select(state.ids[index + 1]);
      start(true);
    } else {
      setStatus(index + 1 === state.ids.length ? '선택한 질문을 모두 들었어요.' : '한 문항을 들었어요. 다음 질문은 직접 선택할 수 있어요.');
    }
  });
  study.subscribe(state => {
    const questionChanged = state.current !== previous.current;
    const changed = questionChanged || state.ids.join(',') !== previous.ids.join(',');
    previous = state;
    if (state.paused || state.reason === 'filter') {
      stop(state.paused ? '쉬는 동안 음성도 멈췄어요.' : '연습 범위가 바뀌었어요. 재생을 누르면 여기부터 들어요.');
    } else if (state.reason === 'navigate' && questionChanged && wanted) {
      // A direct next/previous/picker gesture continues the user's active listening intent.
      start(true);
    } else if (state.reason !== 'audio' && changed) {
      stop('질문이 바뀌었어요. 재생을 누르면 여기부터 들어요.');
    } else controls();
  });
  window.addEventListener('pagehide', () => { if (track || wanted) pause(); });
  setStatus('재생을 한 번 누르면 질문 → 답변 → 다음 질문으로 이어집니다.');
})();
