(() => {
  'use strict';
  const KEY = 'ucle-interview-study-v1';
  const ESSENTIAL = [1, 2, 4, 11, 15, 21, 22, 51, 86, 156, 190, 191, 192, 193, 198];
  function normalize(value, ids) {
    const s = value && typeof value === 'object' ? value : {};
    const validIds = list => Array.isArray(list) ? [...new Set(list.filter(id => ids.includes(id)))] : [];
    return {
      current: ids.includes(s.current) ? s.current : ids[0],
      step: [0, 1, 2, 3].includes(s.step) ? s.step : 0,
      done: validIds(s.done), review: validIds(s.review), batch: validIds(s.batch).slice(0, 5),
      mode: ['all', 'essential', 'review'].includes(s.mode) ? s.mode : 'all',
      priority: ['all', '1', '2', '3'].includes(s.priority) ? s.priority : 'all',
      category: typeof s.category === 'string' && /^(all|[1-9])$/.test(s.category) ? s.category : 'all',
      query: typeof s.query === 'string' ? s.query.slice(0, 200) : '',
      paused: s.paused === true,
    };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { normalize, ESSENTIAL };
  if (typeof document === 'undefined') return;
  const $ = id => document.getElementById(id);
  const cards = [...document.querySelectorAll('.card')];
  const ids = cards.map(card => Number(card.dataset.id));
  const subscribers = new Set();
  const questionLinks = cards.map(card => {
    const id = Number(card.dataset.id);
    const makeButton = (text, label) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = text;
      button.setAttribute('aria-label', label);
      button.title = label;
      button.addEventListener('click', () => move(id));
      return button;
    };
    const label = `${id}. ${card.querySelector('h2').textContent}`;
    return { card, number: makeButton(String(id), label), title: makeButton(`${card.dataset.priority}순위 · ${label}`, label) };
  });
  $('question-map').replaceChildren(...questionLinks.map(link => link.number));
  $('question-list').replaceChildren(...questionLinks.map(link => link.title));
  $('question-browser').hidden = false;
  let state;
  let storageError = false;
  try { state = normalize(JSON.parse(localStorage.getItem(KEY)), ids); }
  catch (_) { state = normalize(null, ids); storageError = true; }
  $('controls').hidden = false;
  $('mode').value = state.mode;
  $('category').value = state.category;
  $('priority').value = state.priority;
  $('search').value = state.query;
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); storageError = false; }
    catch (_) { storageError = true; }
    $('saved').textContent = storageError
      ? '이 브라우저에서는 저장할 수 없어요. 창을 닫으면 연습 위치가 사라질 수 있어요.'
      : '보던 질문과 연습 표시는 이 브라우저에 저장됩니다.';
  }
  function filtered() {
    const query = state.query.trim().toLocaleLowerCase();
    return cards.filter(card => {
      const id = Number(card.dataset.id);
      return (state.mode === 'all' || (state.mode === 'essential' ? ESSENTIAL.includes(id) : state.review.includes(id)))
        && (state.priority === 'all' || card.dataset.priority === state.priority)
        && (state.category === 'all' || card.dataset.category === state.category)
        && (!query || card.textContent.toLocaleLowerCase().includes(query));
    });
  }
  function focusQuestion() {
    const card = document.getElementById(`question-${state.current}`);
    if (card && !card.hidden) card.querySelector('h2').focus({ preventScroll: true });
  }
  function snapshot() {
    return { current: state.current, paused: state.paused, ids: filtered().map(card => Number(card.dataset.id)) };
  }
  function render(reason = 'manual') {
    const visible = filtered();
    if (visible.length && !visible.some(card => Number(card.dataset.id) === state.current)) {
      state.current = Number(visible[0].dataset.id);
      state.step = 0;
    }
    const index = visible.findIndex(card => Number(card.dataset.id) === state.current);
    const current = visible[index];
    $('question-count').textContent = `${visible.length}문항`;
    for (const link of questionLinks) {
      for (const button of [link.number, link.title]) {
        button.hidden = !visible.includes(link.card);
        button.setAttribute('aria-current', String(link.card === current));
      }
    }
    for (const card of cards) {
      card.hidden = card !== current;
      for (const step of card.querySelectorAll('[data-step]')) step.hidden = Number(step.dataset.step) > state.step;
    }
    $('workspace').hidden = state.paused;
    $('library').hidden = state.paused;
    $('scope-filters').hidden = state.paused;
    $('pause').hidden = state.paused;
    $('break-panel').hidden = !state.paused;
    $('empty').hidden = !!current;
    $('actions').hidden = !current;
    $('position').textContent = current ? `${index + 1} / ${visible.length}문항 · 전체 연습 표시 ${state.done.length}개` : '조건에 맞는 질문 0개';
    $('session').textContent = `이번 묶음 ${state.batch.length} / 5문항 · 표시하지 않고 넘어가도 괜찮아요.`;
    $('checkpoint').hidden = state.batch.length < 5;
    $('picker').replaceChildren(...visible.map(card => {
      const option = document.createElement('option');
      option.value = card.dataset.id;
      option.textContent = `${card.dataset.priority}순위 · ${card.dataset.id}. ${card.querySelector('h2').textContent}`;
      option.selected = Number(card.dataset.id) === state.current;
      return option;
    }));
    $('picker').disabled = !current;
    $('prev').disabled = index <= 0;
    $('next').disabled = index < 0 || index >= visible.length - 1;
    $('reveal').textContent = ['1. 한 줄 핵심 보기', '2. 말하기용 답변 보기', '3. 쉬운 풀이 보기', '답변 접고 다시 말해보기'][state.step];
    $('reveal').setAttribute('aria-expanded', String(state.step > 0));
    $('reveal').setAttribute('aria-controls', current ? current.id : 'cards');
    for (const key of ['done', 'review']) $(key).setAttribute('aria-pressed', String(state[key].includes(state.current)));
    $('done').textContent = state.done.includes(state.current) ? '연습했어요 ✓ · 취소' : '이 문항 연습했어요';
    $('review').textContent = state.review.includes(state.current) ? '다시 볼 질문 ✓ · 빼기' : '다시 볼 질문에 담기';
    save();
    for (const listener of subscribers) listener({ ...snapshot(), reason });
  }
  function move(id) { state.current = id; state.step = 0; render('navigate'); focusQuestion(); }
  function pause() { state.paused = true; render(); $('break-title').focus(); }
  $('reveal').addEventListener('click', () => { state.step = (state.step + 1) % 4; render(); });
  for (const [name, delta] of [['prev', -1], ['next', 1]]) {
    $(name).addEventListener('click', () => {
      const list = filtered();
      const index = list.findIndex(card => Number(card.dataset.id) === state.current);
      if (list[index + delta]) move(Number(list[index + delta].dataset.id));
    });
  }
  $('picker').addEventListener('change', event => { move(Number(event.target.value)); $('library').open = false; });
  for (const name of ['mode', 'category', 'priority', 'search']) {
    $(name).addEventListener(name === 'search' ? 'input' : 'change', event => {
      state[name === 'search' ? 'query' : name] = event.target.value;
      state.step = 0;
      render('filter');
    });
  }
  for (const name of ['done', 'review']) {
    $(name).addEventListener('click', () => {
      const removing = state[name].includes(state.current);
      state[name] = removing ? state[name].filter(id => id !== state.current) : [...state[name], state.current];
      if (name === 'done') {
        if (removing) state.batch = state.batch.filter(id => id !== state.current);
        else if (!state.batch.includes(state.current) && state.batch.length < 5) state.batch.push(state.current);
      }
      render();
    });
  }
  $('pause').addEventListener('click', pause);
  $('rest').addEventListener('click', pause);
  $('resume').addEventListener('click', () => { state.paused = false; render(); focusQuestion(); });
  $('more').addEventListener('click', () => { state.batch = []; render(); focusQuestion(); });
  globalThis.UcleStudy = {
    snapshot,
    select(id) {
      if (state.paused || !snapshot().ids.includes(id)) return false;
      state.current = id;
      state.step = 0;
      render('audio');
      return true;
    },
    reveal(step) {
      if (![0, 1, 2, 3].includes(step) || state.step === step) return;
      state.step = step;
      render('audio');
    },
    subscribe(listener) {
      subscribers.add(listener);
      return () => subscribers.delete(listener);
    },
  };
  render();
})();
