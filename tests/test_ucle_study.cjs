const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { normalize, ESSENTIAL } = require('../applications/ucle-interview/study.js');
const ids = Array.from({ length: 200 }, (_, i) => i + 1);
const KEY = 'ucle-interview-study-v1';

function setup(saved, blocked = false) {
  const nodes = {};
  function element(id = '') {
    const listeners = new Map();
    const attrs = new Map();
    return {
      id, hidden: false, disabled: false, value: '', textContent: '', children: [],
      setAttribute(name, value) { attrs.set(name, value); },
      getAttribute(name) { return attrs.get(name); },
      replaceChildren(...children) { this.children = children; },
      addEventListener(name, callback) { listeners.set(name, callback); },
      emit(name) { listeners.get(name)?.({ target: this }); },
      click() { if (!this.disabled) this.emit('click'); },
      focus() {},
    };
  }
  for (const id of ['controls', 'scope-filters', 'priority', 'mode', 'category', 'search', 'saved', 'workspace', 'library', 'pause',
    'break-panel', 'empty', 'actions', 'position', 'session', 'checkpoint', 'picker', 'prev', 'next',
    'reveal', 'done', 'review', 'rest', 'resume', 'more', 'break-title']) nodes[id] = element(id);
  const cards = Array.from({ length: 6 }, (_, index) => {
    const card = element(`question-${index + 1}`);
    card.dataset = { id: String(index + 1), category: index < 3 ? '1' : '2', priority: String(index % 3 + 1) };
    card.textContent = index < 3 ? '지원 동기' : '결제 설계';
    card.heading = element(); card.heading.textContent = card.textContent;
    card.steps = [1, 2, 3].map(step => { const el = element(); el.dataset = { step: String(step) }; return el; });
    card.querySelector = () => card.heading;
    card.querySelectorAll = () => card.steps;
    nodes[card.id] = card;
    return card;
  });
  const storage = new Map([['class101-interview-study-v1', '{"current":99}'], ['csFlashcardsProgress', 'keep']]);
  if (saved !== undefined) storage.set(KEY, typeof saved === 'string' ? saved : JSON.stringify(saved));
  const document = { getElementById: id => nodes[id], querySelectorAll: () => cards, createElement: () => element() };
  const localStorage = {
    getItem(key) { if (blocked) throw Error('blocked'); return storage.get(key) ?? null; },
    setItem(key, value) { if (blocked) throw Error('blocked'); storage.set(key, value); },
  };
  vm.runInNewContext(fs.readFileSync('applications/ucle-interview/study.js', 'utf8'), { document, localStorage });
  return { nodes, cards, storage, state: () => JSON.parse(storage.get(KEY)) };
}

test('corrupt persisted values return usable defaults', () => {
  assert.equal(normalize({ category: 1 }, ids).category, 'all');
  for (const value of [null, false, 'bad', 42]) {
    const state = normalize(value, ids);
    assert.equal(state.current, 1);
    assert.equal(state.step, 0);
    assert.equal(state.mode, 'all');
    assert.equal(state.paused, false);
  }
  const state = normalize({ current: 999, step: '3', done: [1, 1, '2', 0, 200], review: [2, 2, 201],
    batch: [1, 1, 2, 3, 4, 5, 6], mode: 'bad', category: '10', query: 42, paused: 'true' }, ids);
  assert.deepEqual(state, { current: 1, step: 0, done: [1, 200], review: [2], batch: [1, 2, 3, 4, 5],
    mode: 'all', category: 'all', priority: 'all', query: '', paused: false });
});

test('valid position, filters and break survive normalization; query is bounded', () => {
  const state = normalize({ current: 191, step: 3, done: [7], review: [191], batch: [7],
    mode: 'review', category: '9', query: '가'.repeat(300), paused: true }, ids);
  assert.equal(state.current, 191);
  assert.equal(state.category, '9');
  assert.equal(state.step, 3);
  assert.equal(state.paused, true);
  assert.equal(state.query.length, 200);
  assert.equal(ESSENTIAL.length, 15);
  assert.equal(new Set(ESSENTIAL).size, 15);
  assert.ok(ESSENTIAL.every(id => ids.includes(id)));
});

test('one question begins closed; reveal is progressive and navigation never marks practice', () => {
  const s = setup();
  assert.deepEqual(s.cards.map(card => card.hidden), [false, true, true, true, true, true]);
  assert.ok(s.cards[0].steps.every(step => step.hidden));
  s.nodes.reveal.click();
  assert.deepEqual(s.cards[0].steps.map(step => step.hidden), [false, true, true]);
  s.nodes.reveal.click(); s.nodes.reveal.click();
  assert.ok(s.cards[0].steps.every(step => !step.hidden));
  s.nodes.next.click();
  assert.equal(s.state().current, 2);
  assert.equal(s.state().step, 0);
  assert.deepEqual(s.state().done, []);
  assert.equal(s.storage.get('class101-interview-study-v1'), '{"current":99}');
  assert.equal(s.storage.get('csFlashcardsProgress'), 'keep');
});

test('manual marks and break reload preserve state without automatic resume', () => {
  const s = setup();
  s.nodes.next.click(); s.nodes.reveal.click(); s.nodes.done.click(); s.nodes.review.click(); s.nodes.pause.click();
  const restored = setup(s.state());
  assert.equal(restored.nodes.workspace.hidden, true);
  assert.equal(restored.nodes['break-panel'].hidden, false);
  assert.deepEqual(restored.state().done, [2]);
  assert.deepEqual(restored.state().review, [2]);
  restored.nodes.resume.click();
  assert.equal(restored.state().current, 2);
  assert.equal(restored.state().step, 1);
  assert.equal(restored.nodes.workspace.hidden, false);
  restored.nodes.done.click();
  assert.deepEqual(restored.state().done, []);
  assert.deepEqual(restored.state().batch, []);
});

test('five unique manual practice marks show optional rest and new batch keeps progress', () => {
  const s = setup();
  for (let i = 0; i < 5; i++) { s.nodes.done.click(); if (i < 4) s.nodes.next.click(); }
  assert.equal(s.nodes.checkpoint.hidden, false);
  assert.equal(s.state().done.length, 5);
  s.nodes.more.click();
  assert.equal(s.nodes.checkpoint.hidden, true);
  assert.deepEqual(s.state().batch, []);
  assert.equal(s.state().done.length, 5);
});

test('empty review or search can recover and removing last review hides stale question', () => {
  const s = setup();
  s.nodes.review.click();
  s.nodes.mode.value = 'review'; s.nodes.mode.emit('change');
  s.nodes.review.click();
  assert.equal(s.nodes.empty.hidden, false);
  assert.equal(s.nodes.actions.hidden, true);
  assert.ok(s.cards.every(card => card.hidden));
  s.nodes.mode.value = 'all'; s.nodes.mode.emit('change');
  s.nodes.search.value = 'no-such-question'; s.nodes.search.emit('input');
  assert.equal(s.nodes.empty.hidden, false);
  s.nodes.search.value = '결제'; s.nodes.search.emit('input');
  assert.equal(s.nodes.empty.hidden, true);
  assert.equal(s.state().current, 4);
  assert.equal(s.nodes.picker.children.length, 3);
});

test('malformed or unavailable storage still allows study with truthful failure message', () => {
  const malformed = setup('{broken');
  assert.equal(malformed.state().current, 1);
  const blocked = setup(undefined, true);
  blocked.nodes.next.click();
  assert.equal(blocked.cards[1].hidden, false);
  assert.match(blocked.nodes.saved.textContent, /저장할 수 없어요/);
});

test('priority and category intersect and saved v1 progress migrates without losing marks', () => {
  const s = setup({ current: 4, done: [4], review: [4] });
  assert.equal(s.state().priority, 'all');
  s.nodes.priority.value = '2'; s.nodes.priority.emit('change');
  assert.deepEqual(s.nodes.picker.children.map(x => x.value), ['2', '5']);
  s.nodes.category.value = '2'; s.nodes.category.emit('change');
  assert.deepEqual(s.nodes.picker.children.map(x => x.value), ['5']);
  const restored = setup(s.state());
  assert.equal(restored.state().priority, '2');
  assert.equal(restored.state().category, '2');
  assert.equal(restored.state().current, 5);
  assert.deepEqual(restored.state().done, [4]);
  assert.deepEqual(restored.state().review, [4]);
  assert.equal(normalize({priority: '4'}, ids).priority, 'all');
});
