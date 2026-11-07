const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise the real player and async media flow without a browser or audio device.
async function setup(problem = 1, scene = 4, savedNextScene = 0) {
  function element() {
    const attrs = {}, classes = new Set();
    return {textContent:'', checked:true, value:'1', hidden:false, dataset:{}, children:[],
      style:{setProperty(){}}, classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),
        toggle(k,on){if(on)classes.add(k);else classes.delete(k);}},
      setAttribute(k,v){attrs[k]=v;},getAttribute:k=>attrs[k],removeAttribute(k){delete attrs[k];},
      addEventListener(){},replaceChildren(...children){this.children=children;},append(child){this.children.push(child);}};
  }
  const nodes = new Proxy({}, {get(target,id){return target[id] ||= element();}});
  const audio = nodes.lessonAudio;
  Object.assign(audio, {currentTime:0,duration:10,readyState:4,paused:true,ended:false,plays:0,
    load(){this.currentTime=0;this.ended=false;this.paused=true;},
    pause(){this.paused=true;},play(){this.paused=false;this.ended=false;this.plays++;return Promise.resolve();}});
  const scripts = Array.from({length:30},(_,i)=>({id:i+1,scenes:Array.from({length:5},(_,j)=>({
    title:`Problem ${i+1} scene ${j}`,caption:'caption',narration:'explanation',items:['1'],active:0}))}));
  const tracks = scripts.map(lesson=>({id:lesson.id,scenes:lesson.scenes.map((_,j)=>({
    src:`/static/coding-audio/${lesson.id}-${j}.mp3`,duration:10,cues:[{start:0,end:10,text:'explanation'}]}))}));
  const window = {addEventListener(){},clearTimeout(){},setTimeout(){},requestAnimationFrame:f=>f(),
    CodingMotion:{onTick(){},mount(){return true;},validate(){}},
    CodingCode:{mount(){},update(){},validate(){}},
    CodingTypewriter:{render(node,text){node.textContent=text;}}};
  const document = {getElementById:id=>nodes[id],createElement:element,addEventListener(){}};
  const fetch = async url=>({ok:true,status:200,json:async()=>url.includes('coding-lessons')?scripts:
    url.includes('manifest')?{lessons:tracks}:[]});
  vm.runInNewContext(fs.readFileSync('static/coding-lesson.js','utf8'),
    {window,document,fetch,localStorage:{getItem(){return null;},setItem(){}}});
  let current = problem;
  const events = [];
  window.CodingLesson.setProblem(problem,scene);
  window.CodingLesson.init({getJavaSolution:()=>'',
    onProgress:(index,done)=>events.push(['progress',current,index,done]),
    onCompletedScene:index=>events.push(['completed',current,index]),
    onNextLesson(){events.push(['next',current]);if(current===30)return false;
      window.CodingLesson.setProblem(++current,savedNextScene);return true;}});
  const settle = ()=>new Promise(resolve=>setImmediate(resolve));
  await settle();
  assert.equal(nodes.lessonPlay.disabled,false);
  async function play(){nodes.lessonPlay.onclick();await settle();}
  async function end(){audio.currentTime=10;audio.ended=true;audio.paused=true;audio.onended();await settle();}
  return {nodes,audio,events,play,end,settle,current:()=>current};
}

test('last scene records completion before automatically playing the next problem from its introduction',async()=>{
  const s=await setup();await s.play();await s.end();
  assert.equal(s.current(),2);assert.equal(s.audio.src,'/static/coding-audio/2-0.mp3');
  assert.equal(s.audio.currentTime,0);assert.equal(s.audio.paused,false);
  assert.deepEqual(s.events.slice(0,3),[['completed',1,4],['progress',1,4,true],['next',1]]);
  assert.match(s.nodes.lessonPosition.textContent,/^1 \/ 5/);
});

test('automatic playback continues intermediate scenes and respects the off switch',async()=>{
  const s=await setup(3,2);await s.play();await s.end();
  assert.equal(s.audio.src,'/static/coding-audio/3-3.mp3');assert.equal(s.audio.paused,false);
  s.nodes.lessonAuto.checked=false;await s.end();
  assert.equal(s.audio.src,'/static/coding-audio/3-3.mp3');assert.equal(s.audio.paused,true);
  assert.equal(s.events.filter(e=>e[0]==='next').length,0);
});

test('automatic playback off keeps a finished problem available for manual continuation',async()=>{
  const s=await setup();s.nodes.lessonAuto.checked=false;await s.play();await s.end();
  assert.equal(s.current(),1);assert.equal(s.audio.paused,true);assert.equal(s.nodes.lessonNextProblem.hidden,false);
  assert.equal(s.events.filter(e=>e[0]==='next').length,0);
});

test('problem 30 stops once without wrapping or replaying on duplicate ended events',async()=>{
  const s=await setup(30);await s.play();await s.end();await s.end();
  assert.equal(s.current(),30);assert.equal(s.audio.paused,true);assert.equal(s.audio.plays,1);
  assert.equal(s.nodes.lessonNextProblem.hidden,true);
  assert.equal(s.events.filter(e=>e[0]==='completed').length,1);
});

test('restart returns to scene zero and replays even when already on scene zero',async()=>{
  const s=await setup(7,3);await s.play();s.audio.currentTime=6;
  s.nodes.lessonRestart.onclick();await s.settle();
  assert.equal(s.audio.src,'/static/coding-audio/7-0.mp3');assert.equal(s.audio.currentTime,0);
  assert.equal(s.audio.paused,false);assert.equal(s.current(),7);
  s.audio.currentTime=4;s.nodes.lessonRestart.onclick();await s.settle();
  assert.equal(s.audio.currentTime,0);assert.equal(s.audio.paused,false);
  assert.deepEqual(s.events.filter(e=>e[0]==='progress'),[['progress',7,0,false],['progress',7,0,false]]);
});

// A previously visited lesson may have saved a later scene; a playlist starts it at zero.
test('automatic and manual next reset a previously visited problem to its introduction',async()=>{
  for(const automatic of [true,false]) {
    const s=await setup(1,4,3);s.nodes.lessonAuto.checked=automatic;
    await s.play();await s.end();
    if(!automatic){s.nodes.lessonNextProblem.onclick();await s.settle();}
    assert.equal(s.current(),2);assert.equal(s.audio.src,'/static/coding-audio/2-0.mp3');
    assert.equal(s.audio.currentTime,0);assert.equal(s.audio.paused,false);
  }
});
