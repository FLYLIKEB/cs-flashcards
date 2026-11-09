(() => {
  'use strict';

  function normalizeState(value, ids) {
    const state = value && typeof value === 'object' ? value : {};
    return {
      current: ids.includes(state.current) ? state.current : ids[0],
      done: Array.isArray(state.done) ? [...new Set(state.done.filter(id => ids.includes(id)))] : [],
      revealed: state.revealed === true,
      view: state.view === 'all' ? 'all' : 'single',
      onBreak: state.onBreak === true,
    };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { normalizeState };
  if (typeof document === 'undefined') return;

  const byId = id => document.getElementById(id);
  const cards = [...document.querySelectorAll('details[id^="question-"]')];
  const sections = [...document.querySelectorAll('section[id^="category-"]')];
  const ids = cards.map(card => Number(card.id.slice(9)));
  if (!cards.length || !byId('focus-controls')) return;
  const key = 'class101-interview-study-v1';
  const audio = byId('interview-audio');
  const player = document.querySelector('.audio-player');
  const library = byId('library-panel');
  let state;
  let storageUnavailable = false;
  try { state = normalizeState(JSON.parse(localStorage.getItem(key)), ids); }
  catch (_) { state = normalizeState(null, ids); storageUnavailable = true; }
  let lastAudioSource = '';

  function save() {
    try {
      localStorage.setItem(key, JSON.stringify(state));
      storageUnavailable = false;
    } catch (_) { storageUnavailable = true; }
    byId('focus-save-status').textContent = storageUnavailable
      ? '이 브라우저에서는 학습 위치를 저장하지 못했습니다.'
      : '이 브라우저에 학습 위치가 저장됩니다.';
  }

  function currentCard() { return byId(`question-${state.current}`); }

  function render() {
    const current = currentCard();
    document.body.classList.toggle('focus-mode', state.view === 'single');
    document.body.classList.toggle('study-break', state.onBreak);
    for (const card of cards) card.hidden = state.view === 'single' && card !== current;
    for (const section of sections) {
      section.hidden = state.view === 'single' && !section.contains(current);
    }
    if (current.open !== state.revealed) current.open = state.revealed;
    const index = ids.indexOf(state.current);
    const category = current.closest('section').querySelector('h2');
    byId('focus-position').textContent = `${index + 1} / ${ids.length}`;
    // The count badge is not part of the category name.
    byId('focus-category').textContent = [...category.childNodes]
      .filter(node => node.nodeName !== 'SMALL').map(node => node.textContent).join('').trim();
    byId('focus-completed').textContent = `연습 표시 ${state.done.length}개`;
    byId('focus-progress').max = ids.length;
    byId('focus-progress').value = state.done.length;
    byId('focus-hint').textContent = state.revealed
      ? '내 답변과 비교해 보세요. 준비되면 다음 문항으로 넘어가도 괜찮아요.'
      : '질문을 읽고, 내 말로 답해 보세요. 답변은 준비됐을 때 열어보세요.';
    byId('focus-prev').disabled = index === 0;
    byId('focus-next').disabled = index === ids.length - 1;
    byId('focus-reveal').textContent = state.revealed ? '답변 접기' : '답변 보기';
    byId('focus-reveal').setAttribute('aria-expanded', String(state.revealed));
    byId('focus-reveal').classList.toggle('primary', !state.revealed);
    byId('focus-next').classList.toggle('primary', state.revealed && index < ids.length - 1);
    byId('focus-done').classList.toggle('primary', state.revealed && index === ids.length - 1);
    const done = state.done.includes(state.current);
    byId('focus-done').setAttribute('aria-pressed', String(done));
    byId('focus-done').textContent = done ? '연습 표시됨 ✓' : '이 문항 연습했어요';
    byId('focus-mode').setAttribute('aria-pressed', String(state.view === 'single'));
    byId('focus-mode').textContent = state.view === 'single' ? '전체 보기' : '한 문항씩 보기';
    byId('question-picker').value = String(state.current);
    byId('focus-controls').hidden = false;
    byId('focus-actions').hidden = false;
    byId('study-main').hidden = state.onBreak;
    player.hidden = state.onBreak;
    library.hidden = state.onBreak;
    byId('focus-break').hidden = state.onBreak;
    byId('break-panel').hidden = !state.onBreak;
    byId('break-context').textContent = `${state.current}번 문항에서 쉬고 있어요. 돌아오면 여기서 이어가면 됩니다.`;
  }

  function select(id, { fromAudio = false, reveal } = {}) {
    if (!ids.includes(id)) return;
    if (!fromAudio) {
      byId('listen-stop').click();
      lastAudioSource = '';
    }
    if (id !== state.current) state.revealed = false;
    state.current = id;
    if (typeof reveal === 'boolean') state.revealed = reveal;
    render();
    save();
  }

  byId('focus-prev').addEventListener('click', () => select(ids[ids.indexOf(state.current) - 1]));
  byId('focus-next').addEventListener('click', () => select(ids[ids.indexOf(state.current) + 1]));
  byId('focus-reveal').addEventListener('click', () => {
    state.revealed = !state.revealed;
    render(); save();
  });
  byId('focus-done').addEventListener('click', () => {
    state.done = state.done.includes(state.current)
      ? state.done.filter(id => id !== state.current) : [...state.done, state.current];
    render(); save();
  });
  byId('focus-mode').addEventListener('click', () => {
    state.view = state.view === 'single' ? 'all' : 'single';
    render(); save();
  });
  byId('question-picker').addEventListener('change', event => {
    select(Number(event.target.value));
    library.open = false;
  });
  for (const link of library.querySelectorAll('a[href^="#category-"]')) {
    link.addEventListener('click', event => {
      event.preventDefault();
      const card = document.querySelector(`${link.getAttribute('href')} details[id^="question-"]`);
      if (card) select(Number(card.id.slice(9)));
      library.open = false;
    });
  }
  for (const [id, expanded] of [['expand', true], ['collapse', false]]) {
    byId(id).addEventListener('click', () => {
      state.view = 'all';
      state.revealed = expanded;
      for (const card of cards) card.open = expanded;
      render(); save();
    });
  }
  for (const card of cards) {
    // Only an actual summary interaction selects another card. Queued toggle
    // events from hiding/restoring cards must not steal the current position.
    card.querySelector('summary').addEventListener('click', () => {
      const id = Number(card.id.slice(9));
      if (id !== state.current) {
        byId('listen-stop').click();
        lastAudioSource = '';
        state.current = id;
        state.revealed = card.open;
      }
    });
    card.addEventListener('toggle', () => {
      if (card !== currentCard() || card.open === state.revealed) return;
      state.revealed = card.open;
      render(); save();
    });
  }
  for (const kind of ['question', 'answer', 'from-here']) {
    byId(`focus-listen-${kind}`).addEventListener('click', () => {
      lastAudioSource = '';
      currentCard().querySelector(`[data-listen="${kind}"]`).click();
    });
  }
  byId('focus-break').addEventListener('click', () => {
    audio.pause();
    state.onBreak = true;
    render(); save();
    byId('focus-resume').focus();
  });
  byId('focus-resume').addEventListener('click', () => {
    state.onBreak = false;
    render(); save();
    byId('focus-reveal').focus();
  });

  function syncAudio() {
    const source = audio.getAttribute('src') || '';
    const match = source.match(/(?:^|\/)(question|answer)-(\d{3})\.mp3(?:[?#].*)?$/);
    if (!match || source === lastAudioSource) return;
    if (state.onBreak) { audio.pause(); return; }
    lastAudioSource = source;
    select(Number(match[2]), { fromAudio: true, reveal: match[1] === 'answer' });
  }
  for (const event of ['play', 'loadedmetadata', 'timeupdate']) audio.addEventListener(event, syncAudio);
  audio.addEventListener('emptied', () => { lastAudioSource = ''; });
  render();
  if (state.onBreak) audio.pause();
  save();
})();
