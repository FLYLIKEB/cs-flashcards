/* Shared geometry for narrated data structures. Authored values and cue order stay intact. */
(function (root) {
  'use strict';
  const WIDTH = 640, GAP = 8, PAD = 16;
  const chars = text => Array.from(text);
  function textWidth(text, size = 24) {
    return chars(text).reduce((sum, c) => sum + size * (/\s/.test(c) ? .34 : /[\u1100-\u11ff\u2e80-\uffef]/.test(c) ? 1 : /[MW@]/.test(c) ? .9 : .65), 0);
  }
  function wrap(text, width, size) {
    const lines = [];
    for (const paragraph of text.split('\n')) {
      let line = '';
      for (const char of chars(paragraph)) {
        if (line && textWidth(line + char, size) > width) { lines.push(line); line = ''; }
        line += char;
      }
      lines.push(line);
    }
    return lines;
  }
  function fit(node) {
    const fontSize = node.id === 'problem-introduction' ? 26 : node.id === 'note' ? 22 : 24;
    const w = Math.min(WIDTH - PAD * 2, Math.max(node.w || 90, 48));
    const lines = wrap(node.label, w - 20, fontSize);
    const lineHeight = fontSize + 4;
    return {...node, w, h: Math.max(node.h || 44, lines.length * lineHeight + 12), fontSize, lineHeight, lines};
  }
  function overlap(a, b, gap = 0) {
    return Math.abs(a.x-b.x) < (a.w+b.w)/2 + gap - .001 && Math.abs(a.y-b.y) < (a.h+b.h)/2 + gap - .001;
  }
  function bounds(nodes) {
    return {left:Math.min(...nodes.map(n=>n.x-n.w/2)), right:Math.max(...nodes.map(n=>n.x+n.w/2)),
      top:Math.min(...nodes.map(n=>n.y-n.h/2)), bottom:Math.max(...nodes.map(n=>n.y+n.h/2))};
  }
  function array(nodes, options = {}) {
    if (!nodes.length) return [];
    const sorted = [...nodes].sort((a,b)=>a.x-b.x), y = options.y ?? sorted[0].y;
    const available = options.width || WIDTH - PAD * 2;
    const left = options.left ?? PAD;
    const slot = (available-GAP*(nodes.length-1))/nodes.length;
    const fitted=sorted.map(n=>fit({...n,y}));
    if(!options.width&&!options.left&&fitted.every((n,i)=>n.x-n.w/2>=PAD&&n.x+n.w/2<=WIDTH-PAD&&(!i||!overlap(n,fitted[i-1],GAP))))return fitted;
    return sorted.map((n,i)=>fit({...n, x:left+slot/2+i*(slot+GAP), y, w:Math.min(n.w||90,slot)}));
  }
  function queue(nodes, options = {}) { return array(nodes, options); }
  function stack(nodes, options = {}) {
    const sorted = [...nodes].sort((a,b)=>b.y-a.y), x=options.x??sorted[0]?.x??320;
    if (options.horizontal) return array(nodes, {y:options.top ?? PAD + 24});
    const sized=sorted.map(n=>fit({...n,w:Math.max(n.w||90,Math.min(180,textWidth(n.label)+20))})), top=options.top??PAD;
    let y=top;
    for(let i=sized.length-1;i>=0;i--){sized[i]={...sized[i],x,y:y+sized[i].h/2};y+=sized[i].h+GAP;}
    return sized;
  }
  function grid(nodes, columns=3) {
    const sorted=[...nodes].sort((a,b)=>a.y-b.y||a.x-b.x), sized=sorted.map(fit);
    const cellW=Math.max(...sized.map(n=>n.w)), cellH=Math.max(...sized.map(n=>n.h));
    const start=(WIDTH-columns*cellW-(columns-1)*GAP)/2;
    return sized.map((n,i)=>({...n,w:cellW,h:cellH,x:start+cellW/2+(i%columns)*(cellW+GAP),y:PAD+cellH/2+Math.floor(i/columns)*(cellH+GAP)}));
  }
  // Graph/timeline x positions carry meaning; only separate colliding vertical lanes.
  function graph(nodes) { return reflow(nodes.map(fit).map(n=>[n])).flat(); }
  function reflow(blocks) {
    const placed=[];
    for(const original of [...blocks].sort((a,b)=>bounds(a).top-bounds(b).top)) {
      const b=bounds(original), dx=b.left<PAD?PAD-b.left:b.right>WIDTH-PAD?WIDTH-PAD-b.right:0;
      let block=original.map(n=>({...n,x:n.x+dx,y:n.y+Math.max(0,PAD-b.top)}));
      for(let pass=0;pass<=placed.length;pass++) {
        const conflicts=placed.filter(old=>old.some(a=>block.some(n=>overlap(a,n,GAP))));
        if(!conflicts.length)break;
        const shift=Math.max(...conflicts.map(old=>bounds(old).bottom))+GAP-bounds(block).top;
        block=block.map(n=>({...n,y:n.y+shift}));
      }
      placed.push(block);
    }
    return placed;
  }
  function frameLayout(frame) {
    if(frame.nodes[0]?.id==='problem-introduction') {
      const node=fit({...frame.nodes[0],w:600,h:224,x:320,y:120});
      return {...frame,edges:frame.edges||[],nodes:[node],height:240};
    }
    const original=frame.nodes, nodes=original.filter(n=>n.label&&n.id!=='note'), claimed=new Set(), blocks=[];
    function take(selected, layout, type) {
      selected=selected.filter(n=>!claimed.has(n.id));if(!selected.length)return;
      selected.forEach(n=>claimed.add(n.id));blocks.push(layout(selected).map(n=>({...n,component:type})));
    }
    const cells=nodes.filter(n=>/^cell\d+$|^c\d\d$/.test(n.id));
    if(cells.length>=4)take(cells,ns=>grid(ns,3),'grid');
    const queueLabel=nodes.find(n=>n.id==='queue');
    if(queueLabel) {
      const members=nodes.filter(n=>/^q\d+$/.test(n.id)||(/^req\d+$/.test(n.id)&&Math.abs(n.y-queueLabel.y)<8));
      take([queueLabel,...members],ns=>queue(ns,{y:queueLabel.y}),'queue');
    }
    const stackNodes=nodes.filter(n=>(/^open\d+$/.test(n.id)&&n.x===200)||/^pos\d+$/.test(n.id));
    if(stackNodes.length)take(stackNodes,ns=>stack(ns,{top:Math.min(...ns.map(n=>n.y-(n.h||44)/2)),horizontal:Math.max(...ns.map(n=>n.x))-Math.min(...ns.map(n=>n.x))>100}),'stack');
    const connected=new Set((frame.edges||[]).flatMap(e=>[e.from,e.to]));
    take(nodes.filter(n=>connected.has(n.id)),graph,'graph');
    const rows=new Map();
    for(const n of nodes.filter(n=>!claimed.has(n.id))) {const row=rows.get(n.y)||[];row.push(n);rows.set(n.y,row);}
    for(const row of rows.values()) {
      const isArray=row.length>1&&row.every(n=>/^(?:v|value|answer|request|req|src|p|idx|a|b|d|r)\d+$/.test(n.id));
      if(isArray)take(row,array,'array');
      else for(const n of row)take([n],ns=>ns.map(n=>fit({...n,w:Math.max(n.w||90,Math.min(220,textWidth(n.label)+20))})),'annotation');
    }
    let arranged=reflow(blocks).flat();
    const notes=original.filter(n=>n.id==='note');
    for(const note of notes) {
      const sized=fit({...note,w:WIDTH-PAD*2});
      sized.x=320;sized.y=Math.max(174,...arranged.map(n=>n.y+n.h/2))+GAP+sized.h/2;
      arranged.push({...sized,component:'caption'});
    }
    const mapped=new Map(arranged.map(n=>[n.id,n]));
    // A sliding-window outline is a container, not another card over its values.
    for(const n of original.filter(n=>!n.label)) {
      const members=original.filter(v=>/^v\d+$/.test(v.id)&&Math.abs(v.x-n.x)<(n.w||90)/2).map(v=>mapped.get(v.id)).filter(Boolean);
      const b=members.length?bounds(members):null;
      mapped.set(n.id,{...n,container:true,w:b?b.right-b.left+12:n.w,h:b?b.bottom-b.top+12:n.h,x:b?(b.left+b.right)/2:n.x,y:b?(b.top+b.bottom)/2:n.y,lines:[],fontSize:24,lineHeight:32});
    }
    const output=original.map(n=>mapped.get(n.id));
    return {...frame,edges:frame.edges||[],nodes:output,height:Math.max(240,...output.map(n=>n.y+n.h/2+PAD))};
  }
  function edgeLabels(frame) {
    const cards=frame.nodes.filter(n=>!n.container), labels=[];
    for(const edge of frame.edges||[]) {
      if(!edge.label)continue;
      const a=cards.find(n=>n.id===edge.from),b=cards.find(n=>n.id===edge.to);
      if(!a||!b)continue;
      const label={...edge,w:textWidth(edge.label,22)+12,h:30,fontSize:22};
      let placed=null;
      for(const offset of [-22,22,-48,48,-76,76]) {
        const candidate={...label,x:Math.max(label.w/2+PAD,Math.min(WIDTH-PAD-label.w/2,(a.x+b.x)/2)),y:(a.y+b.y)/2+offset};
        if(candidate.y-candidate.h/2>=PAD&&![...cards,...labels].some(n=>overlap(n,candidate,4))){placed=candidate;break;}
      }
      if(!placed)placed={...label,x:320,y:Math.max(...[...cards,...labels].map(n=>n.y+n.h/2))+GAP+label.h/2};
      labels.push(placed);
    }
    return labels;
  }
  function positions(previous,next,phase) {
    const old=new Map(previous.nodes.map(n=>[n.id,n])),current=new Map(next.nodes.map(n=>[n.id,n]));
    return [...next.nodes,...previous.nodes.filter(n=>!current.has(n.id))].map(n=>{
      const a=old.get(n.id)||n,b=current.get(n.id)||n;
      return {...n,x:a.x+(b.x-a.x)*phase,y:a.y+(b.y-a.y)*phase,w:a.w+(b.w-a.w)*phase,h:a.h+(b.h-a.h)*phase,opacity:!current.has(n.id)?1-phase:!old.has(n.id)?phase:1};
    });
  }
  function collides(nodes) {
    const cards=nodes.filter(n=>!n.container&&n.opacity!==0);
    return cards.some((a,i)=>cards.slice(i+1).some(b=>overlap(a,b,2)));
  }
  function prepare(scene) {
    const frames=scene.frames.map(frameLayout);
    frames.forEach(f=>{f.edgeLabels=edgeLabels(f);f.height=Math.max(f.height,...f.edgeLabels.map(n=>n.y+n.h/2+PAD));});
    const height=Math.max(...frames.map(f=>f.height));
    frames.forEach((frame,i)=>{
      if(!i)return;
      const previous=frames[i-1], old=new Map(previous.nodes.map(n=>[n.id,n]));
      const textChanges=frame.nodes.some(n=>{const a=old.get(n.id);return a&&(a.label!==n.label||a.w!==n.w||a.h!==n.h);});
      // Swept rectangles conservatively include the entire travel path. When paths
      // intersect, fade out before relocating, so fast crossings cannot be missed.
      const paths=frame.nodes.filter(n=>!n.container).map(n=>{
        const a=old.get(n.id)||n;
        const left=Math.min(a.x-a.w/2,n.x-n.w/2),right=Math.max(a.x+a.w/2,n.x+n.w/2);
        const top=Math.min(a.y-a.h/2,n.y-n.h/2),bottom=Math.max(a.y+a.h/2,n.y+n.h/2);
        return {x:(left+right)/2,y:(top+bottom)/2,w:right-left,h:bottom-top};
      });
      const vanished=previous.nodes.filter(n=>!n.container&&!frame.nodes.some(v=>v.id===n.id));
      frame.fadeTransition=textChanges||collides([...paths,...vanished]);
    });
    return {...scene,frames,height};
  }
  function transition(previous,next,phase) {
    if(phase>=1)return next.nodes.map(n=>({...n,opacity:1}));
    if(phase<=0)return previous.nodes.map(n=>({...n,opacity:1}));
    if(next.fadeTransition) return (phase<.5?previous.nodes:next.nodes).map(n=>({...n,opacity:phase<.5?1-phase*2:(phase-.5)*2}));
    return positions(previous,next,phase);
  }
  const api={array,queue,stack,grid,graph,prepare,transition,overlap,textWidth};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CodingMotionLayout=api;
})(typeof window!=='undefined'?window:globalThis);
