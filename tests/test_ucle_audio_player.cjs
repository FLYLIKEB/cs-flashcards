const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const key = 'ucle-interview-voice-v1';
const flush = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

function setup(options = {}) {
  const node = () => {
    const events = new Map();
    return {
      hidden: false, disabled: false, checked: true, value: '1', textContent: '', attrs: {},
      addEventListener(name, fn) { if (!events.has(name)) events.set(name, []); events.get(name).push(fn); },
      emit(name) { for (const fn of events.get(name) || []) fn({ target: this }); },
      click() { if (!this.disabled) this.emit('click'); },
      setAttribute(name, value) { this.attrs[name] = value; },
      removeAttribute(name) { delete this[name]; },
    };
  };
  const nodes = Object.fromEntries(['voice-panel', 'voice-audio', 'voice-play', 'voice-restart', 'voice-rate', 'voice-auto', 'voice-status'].map(id => [id, node()]));
  const audio = nodes['voice-audio'];
  Object.assign(audio, {
    currentTime: 0, paused: true, ended: false, error: null, plays: 0, loads: 0,
    load() { this.loads++; this.currentTime = 0; this.ended = false; this.paused = true; this.error = null; },
    play() { this.plays++; this.paused = false; this.emit('play'); return options.play ? options.play(this) : Promise.resolve(); },
    pause() { const changed = !this.paused; this.paused = true; if (changed) this.emit('pause'); },
    end() { this.currentTime = 4; this.ended = true; this.paused = true; this.emit('ended'); },
  });
  let state = { current: 1, ids: [1, 3, 7], paused: false, ...options.state };
  const listeners = [];
  const selections = [], reveals = [];
  const emit = (patch, reason = 'manual') => { state = { ...state, ...patch }; listeners.forEach(fn => fn({ ...state, ids: [...state.ids], reason })); };
  const study = {
    snapshot: () => ({ ...state, ids: [...state.ids] }),
    select(id) { selections.push(id); emit({ current: id }, 'audio'); },
    reveal(step) { reveals.push(step); emit({}, 'audio'); },
    subscribe(fn) { listeners.push(fn); return () => listeners.splice(listeners.indexOf(fn), 1); },
  };
  const storage = new Map([['class101-interview-study-v1', 'untouched']]);
  if (options.saved) storage.set(key, JSON.stringify(options.saved));
  const localStorage = {
    getItem(k) { if (options.blocked) throw Error('storage blocked'); return storage.get(k) ?? null; },
    setItem(k, v) { if (options.blocked) throw Error('storage blocked'); storage.set(k, v); },
  };
  const window = Object.assign(node(), { UcleStudy: study });
  let fetches = 0;
  const tracks = [1, 3, 7].map(id => ({ id, path: `audio/question-${String(id).padStart(3, '0')}.mp3`, duration: 4,
    sections: [0, 1, 2, 3].map(step => ({ step, start: step, end: step + 1, text: `section ${step}` })) }));
  const fetch = () => { fetches++; return options.fetch ? options.fetch() : Promise.resolve({ ok: true, json: async () => ({ tracks }) }); };
  vm.runInNewContext(fs.readFileSync('applications/ucle-interview/audio-player.js', 'utf8'), {
    document: { getElementById: id => nodes[id] }, window, localStorage, fetch,
  });
  return { nodes, audio, window, storage, emit, selections, reveals, state: () => state, fetches: () => fetches, tracks };
}

test('first click starts one actual source and real section timing reveals exact stages, including seek back', async () => {
  const s = setup();
  assert.equal(s.audio.plays, 0); assert.equal(s.fetches(), 0);
  assert.equal(s.nodes['voice-play'].textContent, '음성으로 시작하기');
  s.nodes['voice-play'].click();
  assert.equal(s.audio.plays, 1); // synchronous user activation, not after manifest fetch
  assert.equal(s.audio.src, 'audio/question-001.mp3');
  await flush();
  s.audio.currentTime = 2.2; s.audio.emit('timeupdate'); assert.equal(s.reveals.at(-1), 2);
  s.audio.currentTime = 0.2; s.audio.emit('seeked'); assert.equal(s.reveals.at(-1), 0);
  assert.equal(s.nodes['voice-play'].textContent, '일시정지');
  assert.equal(s.storage.get('class101-interview-study-v1'), 'untouched');
});

test('ended advances only through current filtered IDs and stops on final question', async () => {
  const s = setup(); s.nodes['voice-play'].click(); await flush();
  s.audio.end(); await flush();
  assert.deepEqual(s.selections, [3]); assert.equal(s.audio.src, 'audio/question-003.mp3');
  s.audio.end(); await flush(); assert.deepEqual(s.selections, [3, 7]);
  s.audio.end(); await flush(); assert.equal(s.audio.plays, 3);
  assert.match(s.nodes['voice-status'].textContent, /모두 들었어요/);
  assert.equal(s.fetches(), 1);
});

test('auto-off, pause/resume, restart, native controls and rate preferences are truthful', async () => {
  const s = setup({ saved: { rate: 1.2, automatic: false } });
  s.nodes['voice-play'].click(); await flush();
  assert.equal(s.audio.playbackRate, 1.2);
  s.audio.currentTime = 2;
  s.nodes['voice-play'].click(); assert.equal(s.audio.paused, true);
  s.nodes['voice-play'].click(); await flush(); assert.equal(s.audio.currentTime, 2);
  s.audio.pause(); assert.equal(s.nodes['voice-play'].textContent, '이어서 듣기');
  await s.audio.play(); await flush(); assert.equal(s.nodes['voice-play'].textContent, '일시정지');
  s.nodes['voice-restart'].click(); await flush(); assert.equal(s.audio.currentTime, 0);
  s.audio.end(); assert.deepEqual(s.selections, []);
  s.nodes['voice-rate'].value = '1.5'; s.nodes['voice-rate'].emit('change');
  assert.equal(s.audio.playbackRate, 1.5);
  assert.deepEqual(JSON.parse(s.storage.get(key)), { rate: 1.5, automatic: false });
  const reloaded = setup({ saved: JSON.parse(s.storage.get(key)) });
  assert.equal(reloaded.audio.plays, 0); assert.equal(reloaded.nodes['voice-rate'].value, '1.5');
});

test('manual question, filter and break changes stop audio; manual answer reveal does not', async () => {
  const s = setup(); s.nodes['voice-play'].click(); await flush();
  s.emit({}); assert.equal(s.audio.paused, false);
  s.emit({ ids: [1, 7] }); assert.equal(s.audio.paused, true); assert.equal(s.audio.src, undefined);
  s.nodes['voice-play'].click(); await flush();
  s.emit({ paused: true }); assert.equal(s.audio.paused, true); assert.equal(s.nodes['voice-panel'].hidden, true);
  s.emit({ paused: false }); assert.equal(s.audio.paused, true);
  s.nodes['voice-play'].click(); await flush();
  s.emit({ current: 7 }); assert.equal(s.audio.src, undefined);
  s.audio.end(); assert.deepEqual(s.selections, []);
});

test('stale manifest and play promises cannot resurrect playback after navigation or pause', async () => {
  const loading = deferred(), playing = deferred();
  const s = setup({ fetch: () => loading.promise, play: () => playing.promise });
  s.nodes['voice-play'].click(); s.emit({ current: 3 });
  loading.resolve({ ok: true, json: async () => ({ tracks: s.tracks }) });
  playing.resolve(); await flush();
  assert.equal(s.audio.plays, 1); assert.equal(s.audio.paused, true); assert.equal(s.audio.src, undefined);
  const pending = deferred(); const p = setup({ play: () => pending.promise });
  p.nodes['voice-play'].click(); p.nodes['voice-play'].click();
  pending.reject(Error('old blocked play')); await flush();
  assert.match(p.nodes['voice-status'].textContent, /일시정지/);
  assert.equal(p.audio.paused, true);
});

test('media or manifest errors never advance and explicit replay retries', async () => {
  let failures = true;
  const s = setup({ fetch: () => failures ? Promise.reject(Error('offline')) : Promise.resolve({ ok: true, json: async () => ({ tracks: s.tracks }) }) });
  s.nodes['voice-play'].click(); await flush();
  assert.match(s.nodes['voice-status'].textContent, /다시 시도/);
  s.audio.end(); assert.deepEqual(s.selections, []);
  failures = false; s.nodes['voice-play'].click(); await flush();
  assert.equal(s.fetches(), 2); assert.equal(s.audio.paused, false);
  s.audio.error = { code: 3 }; s.audio.emit('error'); s.audio.end();
  assert.deepEqual(s.selections, []); assert.match(s.nodes['voice-status'].textContent, /다시 시도/);
});

test('pagehide pauses without resume, empty filter disables play, and blocked storage is harmless', async () => {
  const s = setup({ blocked: true }); s.nodes['voice-play'].click(); await flush();
  s.window.emit('pagehide'); assert.equal(s.audio.paused, true);
  s.nodes['voice-rate'].value = '1.5'; s.nodes['voice-rate'].emit('change');
  assert.equal(s.audio.playbackRate, 1.5);
  s.emit({ ids: [] }); assert.equal(s.nodes['voice-play'].disabled, true);
  s.nodes['voice-play'].click(); assert.equal(s.audio.plays, 1);
});


test('invalid manifest timing stops playback and cannot advance', async () => {
  const s = setup({ fetch: () => Promise.resolve({ ok: true, json: async () => ({ tracks: s.tracks }) }) });
  s.tracks[0].sections[2].start = -1;
  s.nodes['voice-play'].click(); await flush();
  assert.equal(s.audio.paused, true);
  assert.equal(s.nodes['voice-play'].textContent, '다시 듣기');
  s.audio.end(); assert.deepEqual(s.selections, []);
});


test('direct navigation continues active audio from the new question even with auto-next off', async () => {
  const s = setup({ saved: { rate: 1.5, automatic: false } });
  s.nodes['voice-play'].click(); await flush();
  s.audio.currentTime = 2.4;
  s.emit({ current: 3 }, 'navigate');
  assert.equal(s.audio.src, 'audio/question-003.mp3');
  assert.equal(s.audio.currentTime, 0);
  assert.equal(s.audio.paused, false);
  assert.equal(s.audio.plays, 2);
  assert.equal(s.audio.playbackRate, 1.5);
  assert.equal(s.reveals.at(-1), 0);
  await flush();
  s.emit({ current: 1 }, 'navigate'); await flush();
  assert.equal(s.audio.src, 'audio/question-001.mp3');
  assert.equal(s.audio.plays, 3);
  s.emit({ current: 1 }, 'navigate');
  assert.equal(s.audio.plays, 3); // selecting the current question is not a restart
  s.audio.end();
  assert.deepEqual(s.selections, []); // automatic advance remains disabled
});

test('idle, paused, ended and failed navigation never starts playback', async () => {
  const idle = setup(); idle.emit({ current: 3 }, 'navigate');
  assert.equal(idle.audio.plays, 0);
  for (const state of ['paused', 'ended', 'error']) {
    const s = setup({ saved: { automatic: false } });
    s.nodes['voice-play'].click(); await flush();
    if (state === 'paused') s.audio.pause();
    else if (state === 'ended') s.audio.end();
    else { s.audio.error = { code: 3 }; s.audio.emit('error'); }
    s.emit({ current: 3 }, 'navigate'); await flush();
    assert.equal(s.audio.plays, 1, state);
    assert.equal(s.audio.paused, true, state);
    assert.equal(s.audio.src, undefined, state);
  }
});

test('rapid next gestures replace pending audio and ignore old rejected or fulfilled play promises', async () => {
  const pending = [deferred(), deferred(), deferred()];
  const s = setup({ play: audio => pending[audio.plays - 1].promise });
  s.nodes['voice-play'].click();
  s.emit({ current: 3 }, 'navigate');
  s.emit({ current: 7 }, 'navigate');
  assert.equal(s.audio.plays, 3);
  assert.equal(s.audio.src, 'audio/question-007.mp3');
  pending[0].reject(Error('abandoned source'));
  pending[1].resolve();
  pending[2].resolve(); await flush();
  assert.equal(s.audio.paused, false);
  assert.match(s.nodes['voice-status'].textContent, /7번/);
  assert.equal(s.nodes['voice-play'].textContent, '일시정지');
  assert.deepEqual(s.selections, []);
});

test('explicit filters stop active listening even when resulting IDs are unchanged', async () => {
  const s = setup(); s.nodes['voice-play'].click(); await flush();
  s.emit({}, 'filter');
  assert.equal(s.audio.paused, true);
  assert.equal(s.audio.src, undefined);
  s.emit({ current: 3 }, 'navigate');
  assert.equal(s.audio.plays, 1);
  s.nodes['voice-play'].click(); await flush();
  s.emit({ current: 7, paused: true }, 'navigate');
  assert.equal(s.audio.paused, true);
  assert.equal(s.audio.plays, 2);
});
