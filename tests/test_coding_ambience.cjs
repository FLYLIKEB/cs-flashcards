const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup(saved = null, reject = false) {
  const nodes = {};
  for (const id of ['lessonAudio','lessonAmbience','ambienceEnabled','ambienceVolume','ambienceLevel','ambienceStatus']) {
    nodes[id] = {paused:true, volume:1, textContent:'', handlers:{}, addEventListener(k,f){this.handlers[k]=f;}, pause(){this.paused=true;}, play(){ if(reject)return Promise.reject(Error('blocked')); this.paused=false;return Promise.resolve(); }};
  }
  const document = {hidden:false,getElementById:id=>nodes[id],addEventListener(k,f){this[k]=f;}};
  const storage = {value:saved,getItem(){return this.value;},setItem(k,v){this.value=v;}};
  vm.runInNewContext(fs.readFileSync('static/coding-ambience.js','utf8'), {document,localStorage:storage,window:{addEventListener() {}}});
  return {nodes,document,storage,voice:nodes.lessonAudio,bed:nodes.lessonAmbience};
}
test('starts only with voice; pauses on buffering, ending and hidden page',async()=>{
 const {voice,bed,document}=setup();assert.equal(bed.paused,true);assert.equal(bed.volume,.16);
 voice.paused=false;await voice.handlers.playing();assert.equal(bed.paused,false);
 voice.handlers.waiting();assert.equal(bed.paused,true);
 await voice.handlers.playing();assert.equal(bed.paused,false);
 voice.handlers.ended();assert.equal(bed.paused,true);
 await voice.handlers.playing();document.hidden=true;document.visibilitychange();assert.equal(bed.paused,true);
});
test('off preference and volume cap survive reload; muting and stop during start stay silent',async()=>{
 const {nodes,voice,bed,storage}=setup('{"enabled":false,"level":99}');
 assert.equal(bed.volume,.3);voice.paused=false;await voice.handlers.playing();assert.equal(bed.paused,true);
 nodes.ambienceEnabled.checked=true;nodes.ambienceEnabled.onchange();await Promise.resolve();assert.equal(bed.paused,false);
 nodes.ambienceVolume.value=0;nodes.ambienceVolume.oninput();assert.equal(bed.paused,true);assert.equal(JSON.parse(storage.value).level,0);
 nodes.ambienceVolume.value=16;nodes.ambienceVolume.oninput();voice.paused=true;voice.handlers.pause();await Promise.resolve();assert.equal(bed.paused,true);
});
test('background failure leaves narration running and displays recovery',async()=>{
 const {nodes,voice,bed}=setup(null,true);voice.paused=false;await voice.handlers.playing();
 assert.equal(voice.paused,false);assert.equal(bed.paused,true);assert.match(nodes.ambienceStatus.textContent,/재생하지 못/);
});
test('an earlier play promise cannot pause a newer start',async()=>{
 const {voice,bed}=setup();const pending=[];bed.play=()=>{bed.paused=false;return new Promise(r=>pending.push(r));};
 voice.paused=false;const first=voice.handlers.playing();const second=voice.handlers.playing();
 pending[0]();await first;assert.equal(bed.paused,false);
 pending[1]();await second;assert.equal(bed.paused,false);
});
