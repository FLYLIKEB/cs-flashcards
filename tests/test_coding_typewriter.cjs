const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup(saved, reduced=false) {
 const toggle={checked:false}, storage={value:saved,getItem(){return this.value;},setItem(k,v){this.value=v;}};
 function node(){return {parentNode:null,textContent:'',setAttribute(){},replaceChildren(...children){this.children=children;children.forEach(c=>c.parentNode=this);}};}
 const document={getElementById:id=>id==='lessonTyping'?toggle:{dispatchEvent(){}},createElement:node};
 const window={};vm.runInNewContext(fs.readFileSync('static/coding-typewriter.js','utf8'),{window,document,localStorage:storage,Intl,matchMedia:()=>({matches:reduced}),Event:class{}});
 return{api:window.CodingTypewriter,toggle,node};
}
test('typing follows cue clock and finishes early; seek reproduces the same prefix',()=>{
 const{api}=setup();const text='요청이 들어온 순서대로 중복을 제거하는 문제입니다.';
 assert.equal(api.count(text,10,10,16),8);
 const midway=api.count(text,10.3,10,16);assert(midway>8&&midway<text.length);
 assert.equal(api.count(text,12,10,16),text.length);
 assert.equal(api.count(text,10.3,10,16),midway);
 assert.equal(api.count('짧음',0,0,.1),2);
});
test('off and reduced motion show the complete text, Korean graphemes stay intact',()=>{
 for(const state of [setup('off'),setup(null,true)])assert.equal(state.api.count('입력과 결과',0,0,10),6);
 const{api,toggle}=setup();assert.equal(api.characters('한👩‍💻').length,2);
 toggle.checked=false;toggle.onchange();assert.equal(api.count('입력과 결과',0,0,10),6);
});
test('hidden remainder reserves full content and can reveal backwards without losing text',()=>{
 const{api,node}=setup();const element=node(),text='배열의 처음부터 끝까지 순서대로 확인해요.';
 api.render(element,text,0,0,5);assert.equal(element.children.map(n=>n.textContent).join(''),text);
 assert.equal(element.children[1].className,'typing-remainder');
 api.render(element,text,2,0,5);assert.equal(element.children[1].textContent,'');
 api.render(element,text,0,0,5);assert(element.children[1].textContent.length>0);
});
