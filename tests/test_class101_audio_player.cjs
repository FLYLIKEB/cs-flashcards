const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function setup() {
  function element(id = '') {
    const listeners = new Map();
    const classes = new Set();
    return {
      id, value: '', textContent: '', disabled: false, dataset: {}, open: false,
      listeners, classList: { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) },
      addEventListener(name, callback) {
        if (!listeners.has(name)) listeners.set(name, new Set());
        listeners.get(name).add(callback);
      },
      removeEventListener(name, callback) { listeners.get(name)?.delete(callback); },
      emit(name) { for (const callback of [...(listeners.get(name) || [])]) callback(); },
      click() { if (!this.disabled) this.emit('click'); },
    };
  }
  const nodes = {};
  for (const id of ['interview-audio', 'listen-mode', 'playback-rate', 'listen-status', 'listen-pause', 'listen-stop', 'listen-prev', 'listen-next', 'listen-all']) nodes[id] = element(id);
  nodes['listen-mode'].value = 'both';
  nodes['playback-rate'].value = '1';
  const cards = Array.from({ length: 100 }, (_, index) => {
    const card = element(`question-${index + 1}`);
    nodes[card.id] = card;
    return card;
  });
  const buttons = cards.flatMap((card, index) => ['question', 'answer', 'from-here'].map(kind => {
    const button = element();
    button.dataset = { question: String(index + 1), listen: kind };
    return button;
  }));
  const audio = nodes['interview-audio'];
  Object.assign(audio, {
    src: '', paused: true, ended: false, error: null, currentTime: 0, plays: 0, nextPlay: null,
    load() { this.currentTime = 0; this.paused = true; this.ended = false; this.error = null; },
    removeAttribute(name) { if (name === 'src') this.src = ''; },
    play() {
      this.plays += 1; this.paused = false; this.ended = false; this.emit('play');
      const attempt = this.nextPlay || Promise.resolve(); this.nextPlay = null;
      return attempt;
    },
    pause() { const changed = !this.paused; this.paused = true; if (changed) this.emit('pause'); },
    end() { this.paused = true; this.ended = true; this.emit('ended'); },
  });
  const document = {
    getElementById: id => nodes[id],
    querySelectorAll: selector => selector === '[data-listen]' ? buttons : cards,
  };
  vm.runInNewContext(fs.readFileSync('applications/class101-interview/audio-player.js', 'utf8'), { document, Promise });
  const click = (id, kind) => buttons.find(button => button.dataset.question === String(id) && button.dataset.listen === kind).click();
  const settle = () => new Promise(resolve => setImmediate(resolve));
  return { nodes, cards, audio, click, settle, status: () => nodes['listen-status'].textContent };
}

test('initial state is silent and individual question or answer ends without continuing', async () => {
  const s = setup();
  assert.equal(s.audio.plays, 0);
  assert.equal(s.nodes['listen-pause'].disabled, true);
  for (const kind of ['question', 'answer']) {
    s.click(7, kind); await s.settle();
    assert.equal(s.audio.src, `audio/${kind}-007.mp3`);
    assert.equal(s.cards[6].open, true);
    assert.equal(s.cards[6].classList.contains('is-speaking'), true);
    const count = s.audio.plays;
    s.audio.end(); await s.settle();
    assert.equal(s.audio.plays, count);
    assert.equal(s.audio.src, '');
    assert.equal(s.cards[6].classList.contains('is-speaking'), false);
    assert.match(s.status(), /모두 들었습니다/);
  }
});

test('continuous both mode plays question then answer then next question', async () => {
  const s = setup();
  s.nodes['listen-all'].click(); await s.settle();
  assert.equal(s.audio.src, 'audio/question-001.mp3');
  s.audio.end(); await s.settle();
  assert.equal(s.audio.src, 'audio/answer-001.mp3');
  s.audio.end(); await s.settle();
  assert.equal(s.audio.src, 'audio/question-002.mp3');
  assert.match(s.status(), /3\/200/);
  assert.equal(s.cards[0].classList.contains('is-speaking'), false);
});

test('from-here follows selected question-only or answer-only mode and stops at 100', async () => {
  for (const kind of ['question', 'answer']) {
    const s = setup(); s.nodes['listen-mode'].value = kind;
    s.click(99, 'from-here'); await s.settle();
    assert.equal(s.audio.src, `audio/${kind}-099.mp3`);
    s.audio.end(); await s.settle();
    assert.equal(s.audio.src, `audio/${kind}-100.mp3`);
    assert.equal(s.nodes['listen-next'].disabled, true);
    s.audio.end(); await s.settle();
    assert.match(s.status(), /모두 들었습니다/);
    s.audio.end(); await s.settle();
    assert.equal(s.audio.plays, 2);
  }
});

test('pause/resume preserves position, native controls sync, and stop clears queue', async () => {
  const s = setup(); s.click(5, 'from-here'); await s.settle();
  s.audio.currentTime = 12;
  s.nodes['listen-pause'].click();
  assert.equal(s.audio.paused, true); assert.match(s.status(), /일시정지/);
  s.nodes['listen-pause'].click(); await s.settle();
  assert.equal(s.audio.paused, false); assert.equal(s.audio.currentTime, 12);
  s.audio.pause(); assert.equal(s.nodes['listen-pause'].textContent, '이어서 듣기');
  await s.audio.play(); assert.match(s.status(), /재생 중/);
  s.nodes['listen-stop'].click();
  s.audio.end(); await s.settle();
  assert.equal(s.audio.src, ''); assert.match(s.status(), /정지/);
  assert.equal(s.nodes['listen-next'].disabled, true);
});

test('next/previous respect selected queue boundaries and speed carries between clips', async () => {
  const s = setup(); s.click(100, 'from-here'); await s.settle();
  assert.equal(s.nodes['listen-prev'].disabled, true);
  s.nodes['playback-rate'].value = '1.5'; s.nodes['playback-rate'].emit('change');
  assert.equal(s.audio.playbackRate, 1.5);
  s.nodes['listen-next'].click(); await s.settle();
  assert.equal(s.audio.src, 'audio/answer-100.mp3');
  assert.equal(s.audio.playbackRate, 1.5); assert.equal(s.nodes['listen-next'].disabled, true);
  s.nodes['listen-prev'].click(); await s.settle();
  assert.equal(s.audio.src, 'audio/question-100.mp3');
  assert.equal(s.audio.playbackRate, 1.5);
});

test('rejected playback and media errors display a recoverable error instead of advancing', async () => {
  const s = setup(); s.audio.nextPlay = Promise.reject(new Error('blocked'));
  s.click(12, 'from-here'); await s.settle();
  assert.match(s.status(), /재생하지 못했습니다/);
  assert.equal(s.audio.src, 'audio/question-012.mp3');
  s.nodes['listen-pause'].click(); await s.settle();
  assert.match(s.status(), /재생 중/);
  s.audio.error = { code: 4 }; s.audio.emit('error');
  assert.match(s.status(), /재생하지 못했습니다/);
  s.nodes['listen-next'].click(); await s.settle();
  assert.equal(s.audio.src, 'audio/answer-012.mp3');
  assert.match(s.status(), /재생 중/);
});

test('rapid replacement ignores stale play rejection and old ended callback', async () => {
  const s = setup(); let rejectOld;
  s.audio.nextPlay = new Promise((_, reject) => { rejectOld = reject; });
  s.click(1, 'from-here');
  const oldEnded = [...s.audio.listeners.get('ended')][0];
  s.click(80, 'answer'); await s.settle();
  rejectOld(new Error('old aborted')); oldEnded(); await s.settle();
  assert.equal(s.audio.src, 'audio/answer-080.mp3');
  assert.match(s.status(), /80번 답변.*재생 중/);
  // A queued ended event dispatched to the new listener is ignored while not ended.
  s.audio.emit('ended'); await s.settle();
  assert.equal(s.audio.src, 'audio/answer-080.mp3');
});

test('stop remains stopped after a pending play settles', async () => {
  const s = setup(); let resolveOld;
  s.audio.nextPlay = new Promise(resolve => { resolveOld = resolve; });
  s.click(20, 'question'); s.nodes['listen-stop'].click();
  resolveOld(); await s.settle();
  assert.equal(s.audio.src, ''); assert.equal(s.audio.paused, true);
  assert.match(s.status(), /정지/); assert.equal(s.nodes['listen-pause'].disabled, true);
});

test('pause then resume ignores the original play attempt rejection on the same source', async () => {
  const s = setup(); let rejectOld;
  s.audio.nextPlay = new Promise((_, reject) => { rejectOld = reject; });
  s.click(4, 'from-here');
  s.nodes['listen-pause'].click();
  s.nodes['listen-pause'].click(); await s.settle();
  rejectOld(new Error('pause aborted initial request')); await s.settle();
  assert.match(s.status(), /재생 중/);
  assert.equal(s.audio.src, 'audio/question-004.mp3');
  s.audio.end(); await s.settle();
  assert.equal(s.audio.src, 'audio/answer-004.mp3');
});

test('pause during a pending load cancels intent even when media is still paused', async () => {
  const s = setup(); let rejectOld;
  s.audio.play = function () {
    this.plays += 1;
    return new Promise((_, reject) => { rejectOld = reject; });
  };
  s.click(3, 'question');
  assert.match(s.status(), /불러오는 중/);
  s.nodes['listen-pause'].click();
  assert.equal(s.audio.plays, 1);
  assert.match(s.status(), /일시정지/);
  rejectOld(new Error('cancelled')); await s.settle();
  assert.match(s.status(), /일시정지/);
});
