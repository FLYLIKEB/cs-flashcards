const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { sentenceAt } = require('../applications/class101-interview/reading-highlight.js');

test('sentence timing excludes intro and gaps and changes exactly at a boundary', () => {
  const timings = [{ start: 1, end: 3 }, { start: 3, end: 7 }];
  assert.equal(sentenceAt(timings, 0.9), null);
  assert.deepEqual(sentenceAt(timings, 2), { index: 0, progress: 50 });
  assert.deepEqual(sentenceAt(timings, 3), { index: 1, progress: 0 });
  assert.equal(sentenceAt(timings, 7), null);
  assert.equal(sentenceAt([{ start: 2, end: 1 }], 2), null);
  assert.equal(sentenceAt(null, 2), null);
  assert.equal(sentenceAt(timings, NaN), null);
});

function setup() {
  function span() {
    const classes = new Set();
    const styles = new Map();
    return { classes, styles,
      classList: { add: value => classes.add(value), remove: value => classes.delete(value) },
      style: { setProperty: (key, value) => styles.set(key, value), removeProperty: key => styles.delete(key) },
      getBoundingClientRect: () => ({ top: 700, bottom: 750 }) };
  }
  const sentences = [span(), span()];
  const question = span();
  const listeners = {};
  const audio = { src: 'audio/answer-001.mp3', currentTime: 0, paused: false, ended: false, error: null,
    getAttribute: () => audio.src,
    addEventListener: (name, callback) => { listeners[name] = callback; } };
  const follow = { checked: true };
  const data = { textContent: JSON.stringify({ 'answer-001': [{ start: 1, end: 3 }, { start: 3, end: 7 }],
    'question-001': [{ start: 1, end: 4 }] }) };
  const card = { querySelector: selector => selector.includes('"question"') ? question
    : sentences[Number(selector.match(/data-sentence="(\d+)"/)[1])] };
  const playerRect = { top: 0, bottom: 160 };
  const document = {
    getElementById: id => ({ 'interview-audio': audio, 'sentence-timings': data, 'follow-reading': follow,
      'question-1': card })[id],
    querySelector: () => ({ getBoundingClientRect: () => playerRect }),
  };
  const scrolls = [];
  const frames = new Map();
  let frameId = 0;
  const window = { innerHeight: 600, selection: '', reduced: false,
    getSelection: () => ({ toString: () => window.selection }),
    matchMedia: () => ({ matches: window.reduced }),
    scrollBy: options => scrolls.push(options),
    requestAnimationFrame: callback => { frames.set(++frameId, callback); return frameId; },
    cancelAnimationFrame: id => frames.delete(id) };
  vm.runInNewContext(fs.readFileSync('applications/class101-interview/reading-highlight.js', 'utf8'), { document, window });
  return { audio, follow, sentences, question, window, scrolls, span, frames, playerRect,
    emit: (event, time = audio.currentTime) => { audio.currentTime = time; listeners[event](); } };
}

test('play, pause, seeking and source replacement track media time without changing personal marks', () => {
  const s = setup();
  s.sentences[0].classes.add('user-underline');
  s.emit('timeupdate', 2);
  assert.equal(s.sentences[0].styles.get('--reading-progress'), '50.00%');
  s.audio.paused = true; s.emit('pause');
  assert.equal(s.sentences[0].styles.get('--reading-progress'), '50.00%');
  s.emit('seeked', 5);
  assert.equal(s.sentences[0].classes.has('is-reading'), false);
  assert.equal(s.sentences[0].classes.has('user-underline'), true);
  assert.equal(s.sentences[1].styles.get('--reading-progress'), '50.00%');
  s.audio.src = 'audio/question-001.mp3'; s.emit('loadstart', 0);
  assert.equal(s.sentences[1].classes.has('is-reading'), false);
  s.audio.paused = false; s.emit('timeupdate', 2);
  assert.equal(s.question.classes.has('is-reading'), true);
  s.audio.ended = true; s.emit('ended');
  assert.equal(s.question.classes.has('is-reading'), false);
});

test('underline DOM replacement resolves the current live span without repeated scrolling', () => {
  const s = setup();
  s.emit('timeupdate', 2);
  const old = s.sentences[0];
  s.sentences[0] = s.span();
  s.emit('timeupdate', 2.5);
  assert.equal(old.classes.has('is-reading'), false);
  assert.equal(s.sentences[0].styles.get('--reading-progress'), '75.00%');
  assert.equal(s.scrolls.length, 1);
});

test('following respects selection, checkbox, paused state and reduced motion', () => {
  const s = setup();
  s.window.selection = 'selected text'; s.emit('timeupdate', 2);
  assert.equal(s.scrolls.length, 0);
  s.window.selection = ''; s.window.reduced = true; s.emit('timeupdate', 4);
  assert.equal(s.scrolls[0].behavior, 'instant');
  assert.equal(s.scrolls[0].top, 524);
  s.follow.checked = false; s.emit('timeupdate', 2);
  assert.equal(s.scrolls.length, 1);
  s.follow.checked = true; s.audio.paused = true; s.emit('seeked', 4);
  assert.equal(s.scrolls.length, 1);
});

test('stop, error and unrecognized sources clear the highlight', () => {
  for (const event of ['emptied', 'error']) {
    const s = setup(); s.emit('timeupdate', 2); s.emit(event);
    assert.equal(s.sentences[0].classes.has('is-reading'), false);
  }
  const s = setup(); s.emit('timeupdate', 2);
  s.audio.src = ''; s.emit('timeupdate');
  assert.equal(s.sentences[0].classes.has('is-reading'), false);
});

test('a player below the text and a collapsed answer do not cause incorrect following', () => {
  const s = setup();
  s.playerRect.top = 800; s.playerRect.bottom = 960;
  s.emit('timeupdate', 2);
  assert.equal(s.scrolls[0].top, 684);
  s.sentences[1].getBoundingClientRect = () => ({ top: 0, bottom: 0 });
  s.emit('timeupdate', 4);
  assert.equal(s.scrolls.length, 1);
});

test('animation uses media time, stops when paused, and respects reduced motion', () => {
  const s = setup(); s.emit('play', 2);
  assert.equal(s.frames.size, 1);
  const [id, callback] = [...s.frames][0];
  s.frames.delete(id); s.audio.currentTime = 2.5; callback();
  assert.equal(s.sentences[0].styles.get('--reading-progress'), '75.00%');
  assert.equal(s.frames.size, 1);
  s.audio.paused = true; s.emit('pause');
  assert.equal(s.frames.size, 0);
  s.window.reduced = true; s.audio.paused = false; s.emit('play');
  assert.equal(s.frames.size, 0);
  s.emit('timeupdate', 4);
  assert.equal(s.sentences[1].styles.get('--reading-progress'), '25.00%');
});
