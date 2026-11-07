const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const lessons = ['01-15','16-30'].flatMap(p=>JSON.parse(fs.readFileSync(`static/coding-motion-${p}.json`)));
const byId = Object.fromEntries(lessons.map(l=>[l.id,l]));
test('authored examples retain ordering, FIFO, stack and grid semantics',()=>{
 const result=byId[1].scenes[2].frames.at(-1).nodes.filter(n=>n.tone==='green').sort((a,b)=>a.x-b.x);
 assert.deepEqual(result.map(n=>n.label),['b','a','c']);
 const queue=byId[13].scenes[1].frames.at(-1).nodes.filter(n=>/^q\d/.test(n.id)).sort((a,b)=>a.x-b.x);
 assert.deepEqual(queue.map(n=>n.label),['1','3']);
 const stack=byId[9].scenes[1].frames[1].nodes.filter(n=>/^open/.test(n.id)&&n.x===200).sort((a,b)=>b.y-a.y);
 assert.ok(stack.length>=1);
 const grid=byId[24].scenes[2].frames.at(-1).nodes.filter(n=>/^c\d\d$/.test(n.id));
 assert.equal(grid.find(n=>n.id==='c22').label,'2');
 assert.ok(grid.find(n=>n.id==='c00').y<grid.find(n=>n.id==='c20').y);
});
const layout = require('../static/coding-motion-layout.js');
function checkFrame(frame,height){
 const visible=frame.nodes.filter(n=>n.opacity!==0);
 const nodes=visible.filter(n=>!n.container);
 for(const n of visible){assert.ok(n.x-n.w/2>=-0.01&&n.x+n.w/2<=640.01,`x ${n.id}`);assert.ok(n.y-n.h/2>=-0.01&&n.y+n.h/2<=height+.01,`y ${n.id}`);}
 for(let i=0;i<nodes.length;i++)for(const b of nodes.slice(i+1))assert.equal(layout.overlap(nodes[i],b),false,`${nodes[i].id} overlaps ${b.id}`);
}
test('every authored frame retains all labels/edges/cues without overlapping cards',()=>{
 for(const lesson of lessons)for(const scene of lesson.scenes){
  const prepared=layout.prepare(scene);
  for(let i=0;i<prepared.frames.length;i++){
   const frame=prepared.frames[i],source=scene.frames[i];
   assert.equal(frame.cue,source.cue);assert.deepEqual(frame.edges,source.edges||[]);
   assert.deepEqual(frame.nodes.map(n=>[n.id,n.label]),source.nodes.map(n=>[n.id,n.label]));
   checkFrame(frame,prepared.height);
   for(const n of frame.nodes.filter(n=>n.label)){
    assert.equal(n.lines.join(''),n.label.replaceAll('\n',''));
    assert.ok(n.lines.every(line=>layout.textWidth(line,n.fontSize)<=n.w-15),`${lesson.id}/${i} ${n.id} text width`);
    assert.ok(n.lines.length*n.lineHeight<=n.h-10,`${n.id} text height`);
   }
  }
 }
});
test('array and queue share horizontal slots; stack and grid preserve their ordering',()=>{
 const ns=['a','b','c'].map((id,i)=>({id,label:id,x:i*80+100,y:50}));
 assert.deepEqual(layout.array(ns).map(n=>n.id),['a','b','c']);
 assert.deepEqual(layout.queue(ns).map(n=>n.x),layout.array(ns).map(n=>n.x));
 const stack=layout.stack(ns);assert.ok(stack[0].y>stack[1].y&&stack[1].y>stack[2].y);
 const grid=layout.grid([...ns,...ns.map(n=>({...n,id:n.id+'2'}))],3);assert.equal(grid[0].y,grid[2].y);assert.ok(grid[3].y>grid[0].y);
});
test('all transition samples keep visible cards apart and end exactly on the next frame',()=>{
 for(const l of lessons)for(const s of l.scenes){const p=layout.prepare(s);
  for(let i=1;i<p.frames.length;i++){
   for(let step=0;step<=20;step++)checkFrame({nodes:layout.transition(p.frames[i-1],p.frames[i],step/20)},p.height);
   assert.deepEqual(layout.transition(p.frames[i-1],p.frames[i],1).map(n=>[n.id,n.x,n.y]),p.frames[i].nodes.map(n=>[n.id,n.x,n.y]));
  }
 }
});
test('edge labels stay clear of cards and each other, and all scene heights remain bounded',()=>{
 for(const lesson of lessons)for(const scene of lesson.scenes){
  const prepared=layout.prepare(scene);assert.ok(prepared.height<=340,`lesson ${lesson.id}: ${prepared.height}`);
  for(const frame of prepared.frames){
   const labels=frame.edgeLabels;
   assert.deepEqual(labels.map(n=>n.label),frame.edges.filter(e=>e.label).map(e=>e.label));
   checkFrame({...frame,nodes:[...frame.nodes,...labels]},prepared.height);
  }
 }
});
test('authored array indices stay aligned and horizontal stack entries retain their x ordering',()=>{
 const input=byId[10].scenes[0].frames.find(f=>f.nodes.some(n=>n.id==='value0')),frame=layout.prepare({frames:[input]}).frames[0];
 for(let i=0;i<4;i++)assert.equal(frame.nodes.find(n=>n.id===`value${i}`).x,frame.nodes.find(n=>n.id===`answer${i}`).x);
 const before=input.nodes.filter(n=>/^pos/.test(n.id)).sort((a,b)=>a.x-b.x).map(n=>n.id);
 assert.deepEqual(frame.nodes.filter(n=>/^pos/.test(n.id)).sort((a,b)=>a.x-b.x).map(n=>n.id),before);
});
