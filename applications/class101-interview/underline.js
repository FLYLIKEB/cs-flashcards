(() => {
  'use strict';

  function mergeRanges(ranges, length) {
    const valid = ranges.filter(range => Array.isArray(range) && range.length === 2 &&
      range.every(Number.isInteger) && range[0] >= 0 && range[0] < range[1] && range[1] <= length)
      .map(range => [...range]).sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const range of valid) {
      const last = merged[merged.length - 1];
      if (last && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
      else merged.push(range);
    }
    return merged;
  }

  function removeRange(ranges, [start, end]) {
    return ranges.flatMap(([a, b]) => {
      if (b <= start || a >= end) return [[a, b]];
      const result = [];
      if (a < start) result.push([a, start]);
      if (b > end) result.push([end, b]);
      return result;
    });
  }

  function restoredRanges(entry, text) {
    return entry && entry.text === text && Array.isArray(entry.ranges)
      ? mergeRanges(entry.ranges, text.length) : [];
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { mergeRanges, removeRange, restoredRanges };
  }
  if (typeof document === 'undefined') return;

  const toolbar = document.getElementById('underline-tools');
  if (!toolbar) return;
  const add = document.getElementById('underline-add');
  const remove = document.getElementById('underline-remove');
  const status = document.getElementById('underline-status');
  const key = 'class101-interview-underlines-v1';
  const blocks = new Map();
  let saved = {};
  let pending = null;
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || '{}');
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) saved = parsed;
  } catch (_) { /* Invalid or unavailable storage must not prevent reading. */ }

  function render(block) {
    block.element.replaceChildren(...block.original.map(node => node.cloneNode(true)));
    const walker = document.createTreeWalker(block.element, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    let offset = 0;
    for (const node of nodes) {
      const text = node.textContent;
      const hits = block.ranges.filter(([start, end]) => start < offset + text.length && end > offset);
      if (hits.length) {
        const fragment = document.createDocumentFragment();
        let cursor = 0;
        for (const [start, end] of hits) {
          const a = Math.max(0, start - offset);
          const b = Math.min(text.length, end - offset);
          fragment.append(document.createTextNode(text.slice(cursor, a)));
          const mark = document.createElement('span');
          mark.className = 'user-underline';
          mark.textContent = text.slice(a, b);
          fragment.append(mark);
          cursor = b;
        }
        fragment.append(document.createTextNode(text.slice(cursor)));
        node.replaceWith(fragment);
      }
      offset += text.length;
    }
  }

  for (const element of document.querySelectorAll('[data-underline-id]')) {
    const id = element.dataset.underlineId;
    const text = element.textContent;
    const block = { element, text, original: [...element.childNodes].map(node => node.cloneNode(true)),
      ranges: restoredRanges(saved[id], text) };
    blocks.set(id, block);
    if (block.ranges.length) render(block);
  }

  function container(node) {
    return (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement)?.closest('[data-underline-id]');
  }

  function readSelection() {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
    const range = selection.getRangeAt(0);
    const element = container(range.startContainer);
    if (!element || element !== container(range.endContainer)) return null;
    const id = element.dataset.underlineId;
    if (!blocks.has(id) || !range.toString().trim()) return null;
    const prefix = range.cloneRange();
    prefix.selectNodeContents(element);
    prefix.setEnd(range.startContainer, range.startOffset);
    const start = prefix.toString().length;
    return { id, start, end: start + range.toString().length };
  }

  document.addEventListener('selectionchange', () => {
    const selection = readSelection();
    if (!selection && toolbar.contains(document.activeElement)) return;
    pending = selection;
    toolbar.hidden = !pending;
    if (pending) {
      add.disabled = false;
      remove.disabled = !blocks.get(pending.id).ranges.some(([a, b]) => a < pending.end && b > pending.start);
      status.textContent = '선택한 글에 밑줄을 표시하거나 지울 수 있습니다.';
    }
  });

  // Keep the text selection while mouse/touch users press the toolbar.
  toolbar.addEventListener('pointerdown', event => {
    if (event.target.closest('button')) event.preventDefault();
  });

  function apply(erase) {
    if (!pending) return;
    const { id, start, end } = pending;
    const block = blocks.get(id);
    block.ranges = erase ? removeRange(block.ranges, [start, end])
      : mergeRanges([...block.ranges, [start, end]], block.text.length);
    let message = erase ? '선택한 부분의 밑줄을 지웠습니다.' : '밑줄을 저장했습니다.';
    try {
      const entries = Object.create(null);
      for (const [blockId, item] of blocks) {
        if (item.ranges.length) entries[blockId] = { text: item.text, ranges: item.ranges };
      }
      localStorage.setItem(key, JSON.stringify(entries));
    } catch (_) {
      message = '밑줄을 표시했지만 저장하지 못했습니다. 이 브라우저의 저장 공간을 확인해 주세요.';
    }
    window.getSelection()?.removeAllRanges();
    render(block);
    pending = null;
    add.disabled = true;
    remove.disabled = true;
    status.textContent = message;
  }
  add.addEventListener('click', () => apply(false));
  remove.addEventListener('click', () => apply(true));
})();
