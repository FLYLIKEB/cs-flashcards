(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const audio = document.getElementById('lessonAudio');
  const host = document.getElementById('lessonCards');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  let story = null, clip = null, svg, nodesLayer, edgesLayer, request = 0;
  const elements = new Map();
  let onTick = () => {};
  const colors = {default: ['#ffffff', '#334155'], blue: ['#1769e0', '#ffffff'], green: ['#d6f5e8', '#116044'], red: ['#ffe2e2', '#a32f39'], muted: ['#e8ecf1', '#7b8795']};
  function el(tag, attrs = {}) {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  }
  function draw() {
    if (!story) return;
    const time = audio.currentTime || 0;
    let index = 0;
    for (let i = 1; i < story.frames.length; i++) {
      if (time >= clip.cues[story.frames[i].cue].start) index = i;
    }
    const frame = story.frames[index], previous = story.frames[Math.max(0, index - 1)];
    const start = clip.cues[frame.cue].start;
    const span = Math.min(0.85, (clip.cues[frame.cue].end - start) / 2);
    const phase = reduce.matches || index === 0 ? 1 : Math.min(1, Math.max(0, (time - start) / span));
    const eased = phase * phase * (3 - 2 * phase);
    const old = new Map(previous.nodes.map(node => [node.id, node]));
    const next = new Map(frame.nodes.map(node => [node.id, node]));
    const positions = new Map();
    const ids = new Set([...old.keys(), ...next.keys()]);
    for (const [id, group] of elements) {
      if (!ids.has(id)) { group.remove(); elements.delete(id); }
    }
    for (const id of ids) {
      const target = next.get(id), source = old.get(id);
      const node = target || source;
      const before = source || node;
      const x = before.x + (node.x - before.x) * eased;
      const y = before.y + (node.y - before.y) * eased;
      const w = (before.w || 90) + ((node.w || 90) - (before.w || 90)) * eased;
      const h = (before.h || 44) + ((node.h || 44) - (before.h || 44)) * eased;
      positions.set(id, {x, y, w, h});
      let group = elements.get(id);
      if (!group) {
        group = el('g', {'data-node': id}); group.append(el('rect'), el('text'));
        nodesLayer.append(group); elements.set(id, group);
      }
      group.setAttribute('transform', `translate(${x} ${y})`);
      group.setAttribute('opacity', !target ? 1 - eased : !source ? eased : 1);
      const [fill, ink] = colors[node.tone] || colors.default;
      const rect = group.firstChild;
      for (const [key, value] of Object.entries({x: -w / 2, y: -h / 2, width:w, height:h, rx:10, fill, stroke:node.tone === 'blue' ? fill : '#d8e0eb', 'stroke-width':1.5})) rect.setAttribute(key, value);
      const text = group.lastChild;
      text.setAttribute('fill', ink);
      if (text.dataset.label !== node.label) {
        text.dataset.label = node.label; text.replaceChildren();
        const lines = node.label.split('\n');
        lines.forEach((line, i) => {
          const lineHeight = id === 'problem-introduction' ? 34 : 24;
          const span = el('tspan', {x:0, y:(i - (lines.length - 1) / 2) * lineHeight + 7});
          span.textContent = line; text.append(span);
        });
      }
    }
    edgesLayer.replaceChildren();
    for (const edge of frame.edges || []) {
      const a = positions.get(edge.from), b = positions.get(edge.to);
      if (!a || !b) continue;
      const dx = b.x-a.x, dy = b.y-a.y;
      const trim = p => 1 / Math.max(Math.abs(dx)/(p.w/2 + 5), Math.abs(dy)/(p.h/2 + 5), 1);
      const ta=trim(a), tb=trim(b);
      edgesLayer.append(el('path', {d:`M ${a.x+dx*ta} ${a.y+dy*ta} L ${b.x-dx*tb} ${b.y-dy*tb}`, fill:'none', stroke:'#7b91ad', 'stroke-width':2.5, 'marker-end':'url(#motionArrow)'}));
      if (edge.label) {
        const label = el('text', {x:(a.x+b.x)/2, y:(a.y+b.y)/2-9, class:'motion-edge-label'});
        label.textContent=edge.label; edgesLayer.append(label);
      }
    }
    svg.dataset.frame = String(index);
    svg.setAttribute('aria-label', frame.nodes.map(n => n.label.replaceAll('\n', ' ')).join(' · '));
  }
  function tick() {
    draw(); onTick();
    request = !audio.paused && !audio.ended ? requestAnimationFrame(tick) : 0;
  }
  function sync() {
    cancelAnimationFrame(request); request = 0; tick();
  }
  ['play', 'pause', 'seeked', 'timeupdate', 'ended', 'loadedmetadata'].forEach(event => audio.addEventListener(event, sync));
  reduce.addEventListener('change', draw);
  window.CodingMotion = {
    onTick(callback) { onTick = callback; },
    mount(value, sound) {
      cancelAnimationFrame(request); request = 0; story = value; clip = sound; elements.clear();
      if (!story || !clip?.cues) { story = null; host.classList.remove('has-motion'); return false; }
      host.replaceChildren(); host.classList.add('has-motion');
      svg = el('svg', {viewBox:'0 0 640 240', role:'img', class:'motion-canvas'});
      const defs=el('defs'), marker=el('marker', {id:'motionArrow', viewBox:'0 0 10 10', refX:9, refY:5, markerWidth:5, markerHeight:5, orient:'auto-start-reverse'});
      marker.append(el('path', {d:'M 0 0 L 10 5 L 0 10 z', fill:'#7b91ad'})); defs.append(marker);
      edgesLayer=el('g', {class:'motion-edges'}); nodesLayer=el('g', {class:'motion-nodes'});
      svg.append(defs, edgesLayer, nodesLayer); host.append(svg); draw(); return true;
    },
    validate(lessons, scripts, media) {
      for (const lesson of lessons) {
        const source = scripts.find(p => p.id === lesson.id), sound = media.find(p => p.id === lesson.id);
        if (!source || lesson.scenes.length !== source.scenes.length) throw new Error('motion scenes');
        lesson.scenes.forEach((scene, s) => {
          if (!scene.frames?.length || scene.frames[0].cue !== 0) throw new Error('motion frames');
          scene.frames.forEach((frame, i) => {
            if (!Number.isInteger(frame.cue) || frame.cue < 0 || (sound?.scenes[s].cues && frame.cue >= sound.scenes[s].cues.length) || (i && frame.cue <= scene.frames[i-1].cue)) throw new Error('motion cue');
            const ids = new Set(frame.nodes.map(n => n.id));
            if (ids.size !== frame.nodes.length || frame.nodes.some(n => typeof n.id !== 'string' || typeof n.label !== 'string' || !Number.isFinite(n.x) || !Number.isFinite(n.y))) throw new Error('motion node');
            if ((frame.edges || []).some(e => !ids.has(e.from) || !ids.has(e.to))) throw new Error('motion edge');
          });
        });
      }
    }
  };
})();
