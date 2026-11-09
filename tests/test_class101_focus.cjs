const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { normalizeState } = require('../applications/class101-interview/focus-study.js');

const KEY = 'class101-interview-study-v1';
function setup(saved, failStorage = false) {
  const nodes = {};
  const tasks = [];
  let focused = null;
  function element(id = '') {
    const listeners = new Map();
    const attrs = new Map();
    const classes = new Set();
    return {
      id, hidden: false, value: '', textContent: '', disabled: false,
      classList: { toggle(name, on) { if (on) classes.add(name); else classes.delete(name); }, contains: name => classes.has(name) },
      setAttribute: (name, value) => attrs.set(name, value), getAttribute: name => attrs.get(name) || null,
      addEventListener(name, fn) { if (!listeners.has(name)) listeners.set(name, []); listeners.get(name).push(fn); },
      emit(name, extra = {}) { for (const fn of listeners.get(name) || []) fn({ target: this, preventDefault() {}, ...extra }); },
      click() { if (!this.disabled) this.emit('click'); },
      focus() { focused = id; },
    };
  }
  for (const id of ['focus-controls', 'focus-actions', 'focus-position', 'focus-category', 'focus-hint',
    'focus-completed', 'focus-progress', 'focus-prev', 'focus-next', 'focus-reveal', 'focus-done',
    'focus-listen-question', 'focus-listen-answer', 'focus-listen-from-here', 'focus-mode', 'question-picker', 'library-panel',
    'study-main', 'focus-break', 'break-panel', 'focus-resume', 'break-context', 'focus-save-status',
    'interview-audio', 'listen-stop', 'expand', 'collapse']) nodes[id] = element(id);
  const sections = Array.from({ length: 2 }, (_, index) => {
    const section = element(`category-${index + 1}`);
    section.querySelector = () => ({ childNodes: [{ nodeName: '#text', textContent: `분야 ${index + 1}` }, { nodeName: 'SMALL', textContent: '2문항' }] });
    section.contains = card => card.group === index;
    return section;
  });
  let stops = 0, plays = 0, pauses = 0;
  const audio = nodes['interview-audio'];
  audio.paused = true;
  audio.pause = () => { pauses++; audio.paused = true; audio.emit('pause'); };
  const cards = Array.from({ length: 4 }, (_, index) => {
    const card = element(`question-${index + 1}`);
    card.group = Math.floor(index / 2);
    card.closest = () => sections[card.group];
    let open = false;
    Object.defineProperty(card, 'open', {
      get: () => open,
      set(value) { if (open !== value) { open = value; tasks.push(() => card.emit('toggle')); } },
    });
    const summary = element(`summary-${index + 1}`);
    summary.click = () => { summary.emit('click'); card.open = !card.open; };
    const buttons = {};
    for (const kind of ['question', 'answer']) {
      buttons[kind] = element();
      buttons[kind].click = () => {
        plays++;
        card.open = true; // audio-player.js opens a card before assigning its source.
        audio.setAttribute('src', `audio/${kind}-${String(index + 1).padStart(3, '0')}.mp3`);
        audio.emit('emptied');
        audio.paused = false;
        audio.emit('play');
      };
    }
    card.querySelector = selector => selector === 'summary' ? summary : buttons[selector.includes('"answer"') ? 'answer' : 'question'];
    nodes[card.id] = card;
    return card;
  });
  const links = sections.map(section => {
    const link = element(); link.setAttribute('href', `#${section.id}`); return link;
  });
  nodes['library-panel'].querySelectorAll = () => links;
  nodes['listen-stop'].addEventListener('click', () => {
    stops++; audio.setAttribute('src', ''); audio.paused = true; audio.emit('emptied');
  });
  const player = element('player');
  const storage = new Map([['class101-interview-underlines-v1', '{"keep":"mine"}']]);
  if (saved !== undefined) storage.set(KEY, typeof saved === 'string' ? saved : JSON.stringify(saved));
  const document = {
    body: element('body'),
    getElementById: id => nodes[id],
    querySelectorAll: selector => selector.startsWith('details') ? cards : sections,
    querySelector: selector => selector === '.audio-player' ? player : cards[Number(selector.match(/category-(\d+)/)[1]) === 1 ? 0 : 2],
  };
  const localStorage = {
    getItem(key) { if (failStorage) throw new Error('blocked'); return storage.get(key) || null; },
    setItem(key, value) { if (failStorage) throw new Error('blocked'); storage.set(key, value); },
  };
  vm.runInNewContext(fs.readFileSync('applications/class101-interview/focus-study.js', 'utf8'), { document, localStorage });
  function flush() { for (let count = 0; tasks.length && count < 100; count++) tasks.shift()(); assert.equal(tasks.length, 0); }
  flush();
  return { nodes, cards, sections, audio, player, storage, links, document, flush,
    state: () => JSON.parse(storage.get(KEY)), counts: () => ({ stops, plays, pauses }), focused: () => focused };
}

test('sanitizes persisted state without accepting unknown cards or duplicate completion', () => {
  assert.deepEqual(normalizeState({ current: 90, done: [1, 1, '2', 99, 3], revealed: 'yes', onBreak: 1, view: 'all' }, [1, 2, 3]),
    { current: 1, done: [1, 3], revealed: false, view: 'all', onBreak: false });
});

test('default is one closed question, one primary action, no autoplay and untouched underlines', () => {
  const s = setup();
  assert.deepEqual(s.cards.map(c => c.hidden), [false, true, true, true]);
  assert.equal(s.cards[0].open, false);
  assert.equal(s.nodes['focus-reveal'].classList.contains('primary'), true);
  assert.equal(s.nodes['focus-next'].classList.contains('primary'), false);
  assert.equal(s.nodes['focus-prev'].disabled, true);
  assert.equal(s.nodes['focus-category'].textContent, '분야 1');
  assert.equal(s.counts().plays, 0);
  assert.equal(s.storage.get('class101-interview-underlines-v1'), '{"keep":"mine"}');
});

test('reveal and self-assessed completion survive reload without advancing or autoplay', () => {
  const s = setup();
  s.nodes['focus-reveal'].click(); s.flush(); s.nodes['focus-done'].click();
  assert.equal(s.state().current, 1);
  assert.equal(s.cards[0].open, true);
  assert.deepEqual(s.state().done, [1]);
  const restored = setup(s.state());
  assert.equal(restored.cards[0].open, true);
  assert.equal(restored.nodes['focus-progress'].value, 1);
  assert.equal(restored.nodes['focus-done'].getAttribute('aria-pressed'), 'true');
  assert.equal(restored.counts().plays, 0);
  restored.nodes['focus-done'].click(); assert.deepEqual(restored.state().done, []);
});

test('manual navigation stops audio and opens only requested card without stale-toggle jumps', () => {
  const s = setup();
  s.nodes['focus-reveal'].click();
  s.nodes['focus-next'].click(); s.flush();
  assert.equal(s.state().current, 2);
  assert.equal(s.cards[1].open, false);
  assert.equal(s.counts().stops, 1);
  s.nodes['question-picker'].value = '4'; s.nodes['question-picker'].emit('change'); s.flush();
  assert.equal(s.nodes['focus-next'].disabled, true);
  s.nodes['focus-reveal'].click(); s.flush();
  assert.equal(s.nodes['focus-done'].classList.contains('primary'), true);
  assert.equal(s.nodes['focus-next'].classList.contains('primary'), false);
  s.links[0].click(); s.flush();
  assert.equal(s.state().current, 1);
  assert.equal(s.nodes['library-panel'].open, false);
});

test('audio follows continuous tracks without interrupting queue and reveals answers only', () => {
  const s = setup();
  s.nodes['focus-listen-question'].click(); s.flush();
  assert.equal(s.cards[0].open, false);
  s.nodes['focus-listen-answer'].click(); s.flush();
  assert.equal(s.cards[0].open, true);
  s.cards[2].open = true;
  s.audio.setAttribute('src', 'audio/question-003.mp3'); s.audio.emit('emptied'); s.audio.emit('play'); s.flush();
  assert.equal(s.state().current, 3);
  assert.deepEqual(s.cards.map(c => c.hidden), [true, true, false, true]);
  assert.equal(s.cards[2].open, false);
  assert.equal(s.counts().stops, 0);
  s.audio.setAttribute('src', 'audio/answer-003.mp3'); s.audio.emit('loadedmetadata'); s.flush();
  assert.equal(s.cards[2].open, true);
});

test('break pauses and persists, restores paused and resumes same position without playback', () => {
  const s = setup(); s.nodes['focus-next'].click(); s.nodes['focus-reveal'].click(); s.flush();
  s.nodes['focus-break'].click();
  assert.equal(s.counts().pauses, 1);
  assert.equal(s.nodes['study-main'].hidden, true);
  assert.equal(s.player.hidden, true);
  assert.equal(s.focused(), 'focus-resume');
  const restored = setup(s.state());
  assert.equal(restored.nodes['break-panel'].hidden, false);
  assert.equal(restored.counts().plays, 0);
  restored.nodes['focus-resume'].click();
  assert.equal(restored.nodes['study-main'].hidden, false);
  assert.equal(restored.state().current, 2);
  assert.equal(restored.cards[1].open, true);
  assert.equal(restored.counts().plays, 0);
});

test('all view allows native question navigation, expand/collapse never changes library disclosure', () => {
  const s = setup(); s.nodes['focus-mode'].click();
  assert.equal(s.cards.some(c => c.hidden), false);
  s.cards[2].querySelector('summary').click(); s.flush();
  assert.equal(s.state().current, 3);
  s.nodes['library-panel'].open = true;
  s.nodes['expand'].click(); s.flush();
  assert.equal(s.cards.every(c => c.open), true);
  assert.equal(s.state().current, 3);
  s.nodes['collapse'].click(); s.flush();
  assert.equal(s.cards.some(c => c.open), false);
  assert.equal(s.nodes['library-panel'].open, true);
});

test('invalid or blocked storage does not prevent studying or claim successful persistence', () => {
  const bad = setup('{broken');
  assert.equal(bad.state().current, 1);
  const blocked = setup(undefined, true);
  blocked.nodes['focus-next'].click(); blocked.flush();
  assert.equal(blocked.cards[1].hidden, false);
  assert.match(blocked.nodes['focus-save-status'].textContent, /저장하지 못했습니다/);
});
