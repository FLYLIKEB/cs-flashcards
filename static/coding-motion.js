(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const audio = document.getElementById('lessonAudio');
  const host = document.getElementById('lessonCards');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  let story = null, clip = null, svg, nodesLayer, edgesLayer, request = 0;
  const elements = new Map();
  let onTick = () => {};
  const colors = {
    default: ['var(--motion-default-fill)', 'var(--motion-default-ink)'],
    blue: ['var(--motion-active-fill)', 'var(--motion-active-ink)'],
    green: ['var(--motion-success-fill)', 'var(--motion-success-ink)'],
    red: ['var(--motion-danger-fill)', 'var(--motion-danger-ink)'],
    muted: ['var(--motion-muted-fill)', 'var(--motion-muted-ink)'],
  };
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
    const end = clip.cues[frame.cue].end;
    const span = Math.min(0.65, (end - start) / 2);
    const phase = reduce.matches || index === 0 ? 1 : Math.min(1, Math.max(0, (time - start) / span));
    const eased = phase * phase * (3 - 2 * phase);
    const nodes = window.CodingMotionLayout.transition(previous, frame, eased);
    const positions = new Map(nodes.map(node => [node.id, node]));
    const height = frame.nodes[0]?.id === 'problem-introduction' ? 240 : story.height;
    svg.setAttribute('viewBox', `0 0 640 ${height}`);
    svg.style.aspectRatio = `640 / ${height}`;
    for (const [id, group] of elements) {
      if (!positions.has(id)) { group.remove(); elements.delete(id); }
    }
    for (const node of nodes) {
      const {id, x, y, w, h} = node;
      let group = elements.get(id);
      if (!group) {
        group = el('g', {'data-node': id}); group.append(el('rect'), el('text'));
        nodesLayer.append(group); elements.set(id, group);
      }
      group.dataset.component = node.component || 'introduction';
      group.dataset.tone = node.tone || 'default';
      group.setAttribute('transform', `translate(${x} ${y})`);
      group.setAttribute('opacity', node.opacity);
      const [fill, ink] = colors[node.tone] || colors.default;
      const rect = group.firstChild;
      for (const [key, value] of Object.entries({x:-w/2, y:-h/2, width:w, height:h, rx:10,
        fill:node.container ? 'none' : fill, stroke:node.container ? 'var(--motion-active-fill)' : 'var(--motion-stroke)', 'stroke-width':node.tone === 'blue' && !reduce.matches ? 1.5 + 2 * Math.max(0, 1 - (time-start)/.65) : 1.5})) rect.setAttribute(key, value);
      const text = group.lastChild;
      text.setAttribute('fill', ink);
      text.style.fontSize = `${node.fontSize}px`;
      const lines = node.lines;
      const full = lines.join('\n');
      const introducing = id === 'problem-introduction';
      const visible = introducing ? window.CodingTypewriter.count(full, time, start, end) : Array.from(full).length;
      const key = `${full}:${visible}`;
      if (text.dataset.rendered !== key) {
        text.dataset.rendered = key; text.replaceChildren();
        let remaining = visible;
        lines.forEach((line, i) => {
          const span = el('tspan', {x:introducing ? -window.CodingMotionLayout.textWidth(line, node.fontSize)/2 : 0,
            y:(i-(lines.length-1)/2)*node.lineHeight+node.fontSize*.3});
          if (introducing) span.style.textAnchor = 'start';
          const chars = window.CodingTypewriter.characters(line);
          span.textContent = introducing ? chars.slice(0, Math.max(0, remaining)).join('') : line;
          remaining -= chars.length + 1;
          text.append(span);
        });
      }
    }
    edgesLayer.replaceChildren();
    for (const edge of frame.edges || []) {
      const a = positions.get(edge.from), b = positions.get(edge.to);
      if (!a || !b || a.opacity < 1 || b.opacity < 1) continue;
      const dx = b.x-a.x, dy = b.y-a.y;
      const trim = p => 1 / Math.max(Math.abs(dx)/(p.w/2+5), Math.abs(dy)/(p.h/2+5), 1);
      const ta=trim(a), tb=trim(b);
      edgesLayer.append(el('path', {d:`M ${a.x+dx*ta} ${a.y+dy*ta} L ${b.x-dx*tb} ${b.y-dy*tb}`, fill:'none', stroke:'var(--motion-edge)', 'stroke-width':2.5, 'marker-end':'url(#motionArrow)'}));
    }
    if (phase === 1) for (const edge of frame.edgeLabels || []) {
      const label = el('text', {x:edge.x, y:edge.y+edge.fontSize*.3, class:'motion-edge-label'});
      label.style.fontSize = `${edge.fontSize}px`; label.textContent=edge.label; edgesLayer.append(label);
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
      cancelAnimationFrame(request); request = 0; story = value ? window.CodingMotionLayout.prepare(value) : null; clip = sound; elements.clear();
      if (!story || !clip?.cues) { story = null; host.classList.remove('has-motion'); return false; }
      host.replaceChildren(); host.classList.add('has-motion');
      svg = el('svg', {viewBox:'0 0 640 240', role:'img', class:'motion-canvas'});
      const defs=el('defs'), marker=el('marker', {id:'motionArrow', viewBox:'0 0 10 10', refX:9, refY:5, markerWidth:5, markerHeight:5, orient:'auto-start-reverse'});
      marker.append(el('path', {d:'M 0 0 L 10 5 L 0 10 z', fill:'var(--motion-edge)'})); defs.append(marker);
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
