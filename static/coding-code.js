(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let source = '', mapping = null, lines = [], last = '', selected = [];
  function row(number, text, active = false) {
    const item = document.createElement('span');
    item.className = 'code-row' + (active ? ' is-current' : '');
    item.dataset.line = number;
    const label = document.createElement('span');
    label.className = 'code-number'; label.textContent = number; label.setAttribute('aria-hidden', 'true');
    const code = document.createElement('code'); code.textContent = text || ' ';
    item.append(label, code);
    if (active) item.setAttribute('aria-current', 'true');
    return item;
  }
  function follow() {
    if (!$('lessonFullCode').open) return;
    const box = $('lessonCodeSource');
    const active = box.querySelector('.is-current');
    if (active && (active.offsetTop < box.scrollTop || active.offsetTop + active.offsetHeight > box.scrollTop + box.clientHeight)) {
      box.scrollTop = Math.max(0, active.offsetTop - box.clientHeight / 3);
    }
  }
  $('lessonFullCode').addEventListener('toggle', follow);
  window.CodingCode = {
    mount(value, links) {
      if (source === value && mapping === links) return;
      source = value || ''; mapping = links; last = ''; selected = [];
      lines = source.trimEnd().split('\n');
      $('lessonCodePanel').hidden = !source;
      $('lessonCodeSource').replaceChildren(...lines.map((text, index) => row(index + 1, text)));
      $('lessonCode').replaceChildren();
      $('lessonCodeRange').textContent = '';
      $('lessonCodeNote').textContent = '';
      $('lessonFullCode').open = false;
    },
    update(sceneIndex, cueIndex) {
      const key = `${sceneIndex}:${cueIndex}`;
      if (!source || key === last) return;
      last = key;
      const cue = mapping?.scenes[sceneIndex]?.cues[cueIndex];
      selected = cue?.lines.filter(n => Number.isInteger(n) && n > 0 && n <= lines.length) || [];
      $('lessonCode').hidden = !selected.length;
      $('lessonCodeRange').textContent = selected.length ? `${selected.join(' · ')}줄` : 'Java';
      $('lessonCodeNote').textContent = cue?.note || '설명과 코드의 연결을 불러오지 못했어요. 전체 코드는 아래에서 확인할 수 있어요.';
      const indent = selected.length ? Math.min(...selected.map(n => lines[n - 1].match(/^\s*/)[0].length)) : 0;
      $('lessonCode').replaceChildren(...selected.map(n => row(n, lines[n - 1].slice(indent), true)));
      for (const item of $('lessonCodeSource').children) {
        const active = selected.includes(Number(item.dataset.line));
        item.classList.toggle('is-current', active);
        if (active) item.setAttribute('aria-current', 'true'); else item.removeAttribute('aria-current');
      }
      follow();
    },
    validate(links, lessons, getSource) {
      for (const link of links) {
        const lesson = lessons.find(item => item.id === link.id);
        const source = getSource(link.id);
        if (!lesson || !source || link.scenes.length !== lesson.scenes.length) throw new Error('code links');
        const lines = source.trimEnd().split('\n');
        link.scenes.forEach((scene, index) => {
          if (scene.cues.length !== lesson.scenes[index].segments.length) throw new Error('code cue count');
          for (const cue of scene.cues) {
            if (!Array.isArray(cue.lines) || !cue.lines.length || typeof cue.note !== 'string' || !cue.note.trim() ||
              cue.lines.some(n => !Number.isInteger(n) || n < 1 || n > lines.length)) throw new Error('code line');
          }
        });
      }
    }
  };
})();
