(() => {
  'use strict';

  const audio = document.getElementById('interview-audio');
  const mode = document.getElementById('listen-mode');
  const rate = document.getElementById('playback-rate');
  const status = document.getElementById('listen-status');
  const pauseButton = document.getElementById('listen-pause');
  const stopButton = document.getElementById('listen-stop');
  const previousButton = document.getElementById('listen-prev');
  const nextButton = document.getElementById('listen-next');
  const cards = [...document.querySelectorAll('details[id^="question-"]')];
  const ids = cards.map(card => Number(card.id.slice('question-'.length)));
  let queue = [];
  let index = -1;
  let generation = 0;
  let playAttempt = 0;
  let phase = 'idle';
  let activeCard = null;
  let unbind = () => {};

  function label() {
    const item = queue[index];
    return `${item.id}번 ${item.kind === 'question' ? '질문' : '답변'} · ${index + 1}/${queue.length}`;
  }

  function controls() {
    const active = index >= 0 && queue.length > 0;
    pauseButton.disabled = !active;
    stopButton.disabled = !active;
    previousButton.disabled = !active || index === 0;
    nextButton.disabled = !active || index === queue.length - 1;
    pauseButton.textContent = phase === 'paused' || phase === 'error' ? '이어서 듣기' : '일시정지';
  }

  function finish(message) {
    generation += 1;
    unbind();
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    queue = [];
    index = -1;
    phase = 'idle';
    if (activeCard) activeCard.classList.remove('is-speaking');
    activeCard = null;
    status.textContent = message;
    controls();
  }

  function failed(token) {
    if (token !== generation || index < 0) return;
    phase = 'error';
    status.textContent = `${label()} · 음성을 재생하지 못했습니다. 이어서 듣기를 눌러 다시 시도하거나 다음 항목을 선택해 주세요.`;
    controls();
  }

  function play(token) {
    const attemptId = ++playAttempt;
    phase = 'loading';
    status.textContent = `${label()} · 불러오는 중`;
    controls();
    try {
      const attempt = audio.play();
      Promise.resolve(attempt).then(() => {
        if (token !== generation || attemptId !== playAttempt || audio.paused || phase === 'error') return;
        phase = 'playing';
        status.textContent = `${label()} · 재생 중`;
        controls();
      }).catch(() => {
        if (attemptId === playAttempt && phase !== 'paused') failed(token);
      });
    } catch (_) {
      failed(token);
    }
  }

  function loadTrack(nextIndex) {
    if (nextIndex < 0 || nextIndex >= queue.length) return;
    const token = ++generation;
    unbind();
    audio.pause();
    index = nextIndex;
    const item = queue[index];
    if (activeCard) activeCard.classList.remove('is-speaking');
    activeCard = document.getElementById(`question-${item.id}`);
    activeCard.open = true;
    activeCard.classList.add('is-speaking');
    const handlers = {
      ended: () => {
        // A queued event from a replaced source must not advance the new queue.
        if (token !== generation || !audio.ended || phase === 'error') return;
        if (index + 1 < queue.length) loadTrack(index + 1);
        else finish('선택한 음성을 모두 들었습니다.');
      },
      error: () => {
        if (audio.error) failed(token);
      },
      play: () => {
        if (token !== generation || audio.paused) return;
        phase = 'playing';
        status.textContent = `${label()} · 재생 중`;
        controls();
      },
      pause: () => {
        if (token !== generation || !audio.paused || audio.ended || phase === 'error') return;
        playAttempt += 1;
        phase = 'paused';
        status.textContent = `${label()} · 일시정지`;
        controls();
      },
    };
    for (const [event, handler] of Object.entries(handlers)) audio.addEventListener(event, handler);
    unbind = () => {
      for (const [event, handler] of Object.entries(handlers)) audio.removeEventListener(event, handler);
    };
    audio.src = `audio/${item.kind}-${String(item.id).padStart(3, '0')}.mp3`;
    audio.load();
    audio.defaultPlaybackRate = Number(rate.value);
    audio.playbackRate = Number(rate.value);
    play(token);
  }

  function start(id, kind) {
    if (!ids.includes(id)) return;
    if (kind === 'question' || kind === 'answer') {
      queue = [{ id, kind }];
    } else {
      const kinds = mode.value === 'both' ? ['question', 'answer'] : [mode.value];
      if (kinds.some(value => value !== 'question' && value !== 'answer')) return;
      queue = ids.slice(ids.indexOf(id)).flatMap(number => kinds.map(value => ({ id: number, kind: value })));
    }
    loadTrack(0);
  }

  document.getElementById('listen-all').addEventListener('click', () => start(ids[0], 'from-here'));
  for (const button of document.querySelectorAll('[data-listen]')) {
    button.addEventListener('click', () => start(Number(button.dataset.question), button.dataset.listen));
  }
  pauseButton.addEventListener('click', () => {
    if (index < 0) return;
    if (phase === 'error') {
      loadTrack(index);
    } else if (audio.paused && phase !== 'loading') {
      play(generation);
    } else {
      playAttempt += 1;
      audio.pause();
      phase = 'paused';
      status.textContent = `${label()} · 일시정지`;
      controls();
    }
  });
  stopButton.addEventListener('click', () => finish('재생을 정지했습니다.'));
  previousButton.addEventListener('click', () => loadTrack(index - 1));
  nextButton.addEventListener('click', () => loadTrack(index + 1));
  rate.addEventListener('change', () => {
    audio.defaultPlaybackRate = Number(rate.value);
    audio.playbackRate = Number(rate.value);
  });
  status.textContent = '질문이나 답변을 선택해 들어보세요.';
  controls();
})();
