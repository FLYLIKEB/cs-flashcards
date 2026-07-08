const state = {
  cards: [],
  filtered: [],
  index: 0,
  flipped: false,
  summary: null,
  audioPlaying: false,
  markSaving: false,
  speechHighlight: null,
  speechCurrent: null,
  speechUtterance: null,
  audioContext: null,
  speechTimers: [],
  speechFallbackTimers: [],
  speechToken: 0,
  speechKeepAlive: null,
  controlsCollapsed: localStorage.getItem('controlsCollapsed') !== '0',
  backPage: 0,
  statusFilter: '',
  importanceFilter: '',
  difficultyFilter: '',
  bokFilter: '',
  randomMode: false,
  conceptHistory: [],
  renderedCardId: null,
  renderedFlipped: false,
};

const $ = (id) => document.getElementById(id);
const cardEl = $('card');
const VIEW_STATE_KEY = 'csFlashcardsViewState:v1';

function readSavedViewState() {
  try {
    return JSON.parse(localStorage.getItem(VIEW_STATE_KEY) || '{}');
  } catch (_error) {
    return {};
  }
}

function restoreViewState() {
  const saved = readSavedViewState();
  if ($('searchInput')) $('searchInput').value = saved.search || '';
  if ($('categorySelect') && saved.category && [...$('categorySelect').options].some((option) => option.value === saved.category)) {
    $('categorySelect').value = saved.category;
  }
  if ($('importanceSelect')) $('importanceSelect').value = saved.importance || '';
  if ($('difficultySelect')) $('difficultySelect').value = saved.difficulty || '';
  if ($('bokSelect')) $('bokSelect').value = saved.bok || '';
  state.statusFilter = saved.statusFilter || '';
  const savedIndex = Number(saved.index);
  state.index = Number.isInteger(savedIndex) && savedIndex >= 0 ? savedIndex : 0;
  updateStatFilterButtons();
}

function saveViewState() {
  try {
    localStorage.setItem(VIEW_STATE_KEY, JSON.stringify({
      search: $('searchInput')?.value || '',
      category: $('categorySelect')?.value || '',
      importance: $('importanceSelect')?.value || '',
      difficulty: $('difficultySelect')?.value || '',
      bok: $('bokSelect')?.value || '',
      statusFilter: state.statusFilter || '',
      index: state.index || 0,
    }));
  } catch (_error) {}
}


const CATEGORY_META = {
  '데이터베이스': {emoji: '🗄️', className: 'cat-database'},
  '운영체제': {emoji: '⚙️', className: 'cat-os'},
  '네트워크': {emoji: '🌐', className: 'cat-network'},
  '자료구조·알고리즘': {emoji: '🧩', className: 'cat-algorithm'},
  '프로그래밍 언어': {emoji: '💻', className: 'cat-language'},
  '소프트웨어공학': {emoji: '🏗️', className: 'cat-software'},
  '컴퓨터구조': {emoji: '🧠', className: 'cat-architecture'},
  '보안': {emoji: '🛡️', className: 'cat-security'},
  '클라우드·분산시스템': {emoji: '☁️', className: 'cat-cloud'},
  '인공지능·데이터': {emoji: '🤖', className: 'cat-ai'},
  '금융IT·신기술': {emoji: '💳', className: 'cat-finance'},
};

function categoryMeta(category) {
  return CATEGORY_META[category] || {emoji: '📘', className: 'cat-default'};
}

function categoryLabel(category) {
  const meta = categoryMeta(category);
  return `${meta.emoji} ${category || '미분류'}`;
}

function applyCategoryTheme(category) {
  const meta = categoryMeta(category);
  cardEl.classList.remove(...Object.values(CATEGORY_META).map((item) => item.className), 'cat-default');
  cardEl.classList.add(meta.className);
}


const CATEGORY_COLORS = {
  '데이터베이스': '#2563eb',
  '운영체제': '#475569',
  '네트워크': '#0891b2',
  '자료구조·알고리즘': '#7c3aed',
  '프로그래밍 언어': '#16a34a',
  '소프트웨어공학': '#ca8a04',
  '컴퓨터구조': '#9333ea',
  '보안': '#dc2626',
  '클라우드·분산시스템': '#0284c7',
  '인공지능·데이터': '#db2777',
  '금융IT·신기술': '#0f766e',
};

function xmlEscape(value) {
  return String(value || '').replace(/[&<>"]/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
}

function categorySymbolSvg(category, color) {
  const stroke = xmlEscape(color);
  const soft = 'opacity="0.18"';
  const shapes = {
    '데이터베이스': `<ellipse cx="176" cy="82" rx="62" ry="20" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M114 82v86c0 12 28 22 62 22s62-10 62-22V82" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M114 126c0 12 28 22 62 22s62-10 62-22" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/>` ,
    '운영체제': `<circle cx="176" cy="136" r="52" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M176 62v32M176 178v32M102 136h32M218 136h32M124 84l23 23M205 165l23 23M228 84l-23 23M147 165l-23 23" stroke="${stroke}" stroke-width="8" stroke-linecap="round" ${soft}/>` ,
    '네트워크': `<circle cx="106" cy="96" r="18" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><circle cx="232" cy="88" r="18" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><circle cx="170" cy="178" r="22" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M123 101l90-10M116 112l40 49M221 104l-37 55" stroke="${stroke}" stroke-width="7" stroke-linecap="round" ${soft}/>` ,
    '자료구조·알고리즘': `<path d="M98 86h66v44H98zM188 86h66v44h-66zM143 166h66v44h-66z" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M164 108h24M176 130v36" stroke="${stroke}" stroke-width="8" stroke-linecap="round" ${soft}/>` ,
    '프로그래밍 언어': `<path d="M132 92l-48 44 48 44M220 92l48 44-48 44M194 78l-36 116" fill="none" stroke="${stroke}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" ${soft}/>` ,
    '소프트웨어공학': `<path d="M92 174l84-92 84 92" fill="none" stroke="${stroke}" stroke-width="9" stroke-linecap="round" ${soft}/><path d="M120 174v-48h112v48M144 174v-24h64v24" fill="none" stroke="${stroke}" stroke-width="8" stroke-linejoin="round" ${soft}/>` ,
    '컴퓨터구조': `<rect x="102" y="74" width="148" height="116" rx="20" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M126 54v28M162 54v28M198 54v28M234 54v28M126 190v28M162 190v28M198 190v28M234 190v28M82 104h28M82 140h28M242 104h28M242 140h28" stroke="${stroke}" stroke-width="7" stroke-linecap="round" ${soft}/>` ,
    '보안': `<path d="M176 58l78 30v50c0 50-31 82-78 104-47-22-78-54-78-104V88z" fill="none" stroke="${stroke}" stroke-width="9" stroke-linejoin="round" ${soft}/><path d="M142 140l22 22 48-54" fill="none" stroke="${stroke}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" ${soft}/>` ,
    '클라우드·분산시스템': `<path d="M112 168h128c25 0 42-15 42-36 0-20-16-35-38-35-9-28-35-47-66-47-35 0-63 24-70 58-23 2-40 15-40 34 0 16 13 26 44 26z" fill="none" stroke="${stroke}" stroke-width="9" stroke-linejoin="round" ${soft}/><path d="M132 204h88M176 168v36" stroke="${stroke}" stroke-width="8" stroke-linecap="round" ${soft}/>` ,
    '인공지능·데이터': `<path d="M124 108c0-28 20-50 52-50s52 22 52 50c0 19-9 32-22 43v31h-60v-31c-13-11-22-24-22-43z" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M146 208h60M154 232h44M150 118h52M176 92v52" stroke="${stroke}" stroke-width="8" stroke-linecap="round" ${soft}/>` ,
    '금융IT·신기술': `<rect x="92" y="82" width="168" height="112" rx="20" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M92 118h168M130 156h42M206 156h20" stroke="${stroke}" stroke-width="8" stroke-linecap="round" ${soft}/><circle cx="176" cy="218" r="18" fill="none" stroke="${stroke}" stroke-width="7" ${soft}/>` ,
  };
  return shapes[category] || `<circle cx="176" cy="136" r="70" fill="none" stroke="${stroke}" stroke-width="8" ${soft}/><path d="M136 136h80M176 96v80" stroke="${stroke}" stroke-width="8" stroke-linecap="round" ${soft}/>`;
}

function frontIllustrationUrl(card) {
  const category = card?.category || '';
  const color = CATEGORY_COLORS[category] || '#1f3a5f';
  const meta = categoryMeta(category);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="560" viewBox="0 0 900 560">
    <circle cx="450" cy="280" r="210" fill="${xmlEscape(color)}" opacity="0.055"/>
    <circle cx="450" cy="280" r="132" fill="none" stroke="${xmlEscape(color)}" stroke-width="14" opacity="0.05"/>
    <g transform="translate(98 8) scale(2)">${categorySymbolSvg(category, color)}</g>
    <text x="450" y="174" text-anchor="middle" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans KR',sans-serif" font-size="124" font-weight="800" fill="${xmlEscape(color)}" opacity="0.07">${xmlEscape(meta.emoji)}</text>
  </svg>`;
  return `url("data:image/svg+xml,${encodeURIComponent(svg)}")`;
}

function applyFrontIllustration(card) {
  document.querySelector('.front')?.style.setProperty('--front-illustration', frontIllustrationUrl(card));
}


function googleSearchQuery(card) {
  return [card?.category, card?.term, card?.english].filter(Boolean).join(' ');
}

function googleSearchUrl(card) {
  const params = new URLSearchParams({
    q: googleSearchQuery(card),
    udm: '50',
  });
  return `https://www.google.com/search?${params.toString()}`;
}

function normalizeTerm(value) {
  return String(value || '').trim().toLowerCase();
}

function findCardByConcept(concept) {
  const target = normalizeTerm(concept);
  if (!target) return null;
  return state.cards.find((card) => normalizeTerm(card.term) === target)
    || state.cards.find((card) => normalizeTerm(card.english) === target)
    || state.cards.find((card) => normalizeTerm(card.term).includes(target) || target.includes(normalizeTerm(card.term)));
}

function currentViewSnapshot() {
  const current = state.filtered[state.index] || null;
  return {
    cardId: current?.id || '',
    index: state.index || 0,
    flipped: Boolean(state.flipped),
    backPage: state.backPage || 0,
    backScrollTop: document.querySelector('.back-scroll')?.scrollTop || 0,
    search: $('searchInput')?.value || '',
    category: $('categorySelect')?.value || '',
    importance: $('importanceSelect')?.value || '',
    difficulty: $('difficultySelect')?.value || '',
    bok: $('bokSelect')?.value || '',
    statusFilter: state.statusFilter || '',
  };
}

function updateConceptBackButton() {
  const button = $('conceptBackBtn');
  if (!button) return;
  const previous = state.conceptHistory[state.conceptHistory.length - 1];
  button.hidden = !previous;
  button.disabled = !previous;
  if (previous) {
    const target = state.cards.find((card) => card.id === previous.cardId);
    const label = target ? `${target.term} · 이전 필터로 돌아가기` : '이전 개념과 필터로 돌아가기';
    button.title = label;
    button.setAttribute('aria-label', label);
  }
}

function restoreViewSnapshot(snapshot) {
  if (!snapshot) return false;
  if ($('searchInput')) $('searchInput').value = snapshot.search || '';
  if ($('categorySelect')) $('categorySelect').value = snapshot.category || '';
  if ($('importanceSelect')) $('importanceSelect').value = snapshot.importance || '';
  if ($('difficultySelect')) $('difficultySelect').value = snapshot.difficulty || '';
  if ($('bokSelect')) $('bokSelect').value = snapshot.bok || '';
  state.statusFilter = snapshot.statusFilter || '';
  state.index = Number.isInteger(snapshot.index) ? snapshot.index : 0;
  updateStatFilterButtons();
  applyFilters(snapshot.cardId || null);
  if (snapshot.cardId) {
    const found = state.filtered.findIndex((card) => card.id === snapshot.cardId);
    if (found >= 0) state.index = found;
  }
  state.flipped = Boolean(snapshot.flipped);
  state.backPage = snapshot.backPage || 0;
  renderCard();
  window.requestAnimationFrame(() => {
    const scrollArea = document.querySelector('.back-scroll');
    if (scrollArea) scrollArea.scrollTop = snapshot.backScrollTop || 0;
  });
  return true;
}

function goBackToPreviousConcept() {
  const previous = state.conceptHistory.pop();
  if (!restoreViewSnapshot(previous)) {
    updateConceptBackButton();
    setMessage('돌아갈 개념 기록이 없습니다.', true);
    return;
  }
  updateConceptBackButton();
  const restored = state.filtered[state.index];
  setMessage(restored ? `${restored.term} · 이전 필터 복원` : '이전 필터 복원');
  focusAppCard();
}

function jumpToCard(card, {rememberCurrent = false} = {}) {
  if (!card) return false;
  const snapshot = rememberCurrent ? currentViewSnapshot() : null;
  if (snapshot && snapshot.cardId === card.id) {
    setMessage(`${card.term}`);
    return true;
  }
  $('searchInput').value = '';
  if ($('categorySelect')) $('categorySelect').value = '';
  if ($('importanceSelect')) $('importanceSelect').value = '';
  if ($('difficultySelect')) $('difficultySelect').value = '';
  if ($('bokSelect')) $('bokSelect').value = '';
  state.importanceFilter = '';
  state.difficultyFilter = '';
  state.bokFilter = '';
  state.statusFilter = '';
  updateStatFilterButtons();
  state.filtered = [...state.cards];
  const found = state.filtered.findIndex((item) => item.id === card.id);
  if (found < 0) return false;
  if (snapshot) state.conceptHistory.push(snapshot);
  state.index = found;
  state.flipped = true;
  state.backPage = 0;
  renderCard();
  setMessage(`${card.term}`);
  focusAppCard();
  return true;
}

function findCardForJump(value) {
  const query = String(value || '').trim();
  if (!query) return null;
  const numeric = Number(query);
  if (Number.isInteger(numeric) && numeric >= 1 && numeric <= state.cards.length) {
    return state.cards[numeric - 1];
  }
  const normalized = normalizeTerm(query);
  const idQuery = query.toUpperCase();
  return state.cards.find((card) => card.id.toUpperCase() === idQuery)
    || state.cards.find((card) => normalizeTerm(card.term) === normalized)
    || state.cards.find((card) => normalizeTerm(card.english) === normalized)
    || state.cards.find((card) => normalizeTerm(card.term).includes(normalized) || normalizeTerm(card.english).includes(normalized));
}

function jumpFromInput(value = null) {
  const query = String(value ?? ($('positionInput')?.value || '')).trim();
  const numeric = Number(query);
  if (Number.isInteger(numeric) && numeric >= 1 && numeric <= state.filtered.length) {
    state.index = numeric - 1;
    state.flipped = false;
    state.backPage = 0;
    playMoveSound(1);
    renderCard();
    return;
  }
  setMessage('범위를 벗어났습니다.', true);
  renderCard();
}

function focusAppCard() {
  window.setTimeout(() => {
    try {
      cardEl.focus({preventScroll: true});
    } catch (_error) {
      cardEl.focus();
    }
  }, 0);
}

function focusSearchInput() {
  const input = $('searchInput');
  if (!input) return;
  try {
    input.focus({preventScroll: true});
  } catch (_error) {
    input.focus();
  }
  input.select();
  setMessage('검색어 입력 후 Enter/Esc로 카드로 돌아가기');
}

function returnFocusFromSearchInput(event) {
  if (!['Enter', 'Escape'].includes(event.key)) return;
  event.preventDefault();
  event.currentTarget.blur();
  focusAppCard();
}

function restoreAppFocusAfterSearch(openedWindow = null) {
  [0, 80, 240, 600].forEach((delay) => {
    window.setTimeout(() => {
      try { openedWindow?.blur?.(); } catch (_error) {}
      try { window.focus(); } catch (_error) {}
      focusAppCard();
    }, delay);
  });
}

function openCurrentGoogleSearch(event = null) {
  const link = state.flipped ? $('backGoogleSearchLink') : $('frontGoogleSearchLink');
  if (!link || !link.href || link.getAttribute('href') === '#') return;
  event?.preventDefault?.();
  event?.currentTarget?.blur?.();
  const opened = window.open(link.href, 'cs-google-ai-search', 'popup,width=1120,height=820');
  restoreAppFocusAfterSearch(opened);
  window.setTimeout(() => {
    try { if (opened) opened.opener = null; } catch (_error) {}
  }, 800);
  setMessage('검색을 열고 CS 카드로 포커스를 되돌렸습니다.');
}

function applyControlsCollapsed() {
  const panel = $('controlsPanel');
  const button = $('controlsToggle');
  if (!panel || !button) return;
  panel.classList.toggle('collapsed', state.controlsCollapsed);
  document.body.classList.toggle('controls-collapsed', state.controlsCollapsed);
  button.setAttribute('aria-expanded', String(!state.controlsCollapsed));
  button.textContent = state.controlsCollapsed ? '⚙' : '⚙';
}

function toggleControlsPanel() {
  state.controlsCollapsed = !state.controlsCollapsed;
  localStorage.setItem('controlsCollapsed', state.controlsCollapsed ? '1' : '0');
  applyControlsCollapsed();
}

function selectedSpeechParts() {
  return {
    term: $('speakTerm').checked,
    definition: $('speakDefinition').checked,
    detail: $('speakDetail').checked,
    related: $('speakRelated').checked,
    exam: $('speakExam').checked,
  };
}

function speechRate() {
  const rate = Number($('speechRate')?.value || 1);
  return Number.isFinite(rate) ? Math.min(2, Math.max(1, rate)) : 1;
}

function plainRelated(text) {
  return parseRelated(text).join(', ');
}

function speechItemsForCard(card) {
  const parts = selectedSpeechParts();
  const items = [];
  if (parts.term) {
    items.push({key: 'term', text: card.term, targetText: card.term, prefixLength: 0});
  }
  if (parts.definition) {
    const prefix = '간단설명. ';
    const targetText = card.definition || '';
    items.push({key: 'definition', text: `${prefix}${targetText}`, targetText, prefixLength: prefix.length});
  }
  if (parts.detail) {
    detailedSections(card.detailed_explanation).forEach((section) => {
      const prefix = `상세설명. ${section.label}. `;
      items.push({key: 'detail', detailLabel: section.label, text: `${prefix}${section.content}`, targetText: section.content, prefixLength: prefix.length});
    });
  }
  if (parts.related) {
    const prefix = '관련개념. ';
    const targetText = plainRelated(card.related_concepts);
    items.push({key: 'related', text: `${prefix}${targetText}`, targetText, prefixLength: prefix.length});
  }
  if (parts.exam) {
    const prefix = '시험포인트. ';
    const targetText = card.exam_note || '';
    items.push({key: 'exam', text: `${prefix}${targetText}`, targetText, prefixLength: prefix.length});
  }
  return items.filter((item) => item.text.replace(/[.\s]/g, '').length > 0);
}


function preferredVoiceForItem(_item) {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  if (!voices.length) return null;
  const koreanVoices = voices.filter((voice) => /ko|Korean|한국|한국어/i.test(`${voice.lang} ${voice.name}`));
  const pool = koreanVoices.length ? koreanVoices : voices;
  return pool.find((voice) => /female|여성|woman|heami|yuna|유나/i.test(voice.name))
    || pool[0];
}

function speechPitchForItem(_item) {
  return 1;
}

function speechRateForItem(item) {
  const baseRate = speechRate();
  return baseRate;
}

function estimateSpeechSeconds() {
  if (!state.filtered.length) return 0;
  const chars = state.filtered.reduce((total, card) => {
    return total + speechItemsForCard(card).reduce((sum, item) => sum + item.text.replace(/\s+/g, '').length, 0);
  }, 0);
  const baseCharsPerSecond = 7.2;
  const speechSeconds = chars / (baseCharsPerSecond * speechRate());
  const transitionSeconds = Math.max(0, state.filtered.length - 1) * 0.62;
  const chimeSeconds = state.filtered.length * 0.26;
  return Math.ceil(speechSeconds + transitionSeconds + chimeSeconds);
}

function formatDuration(seconds) {
  if (!seconds) return '0초';
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}시간 ${mins}분`;
  }
  if (minutes > 0) return `${minutes}분 ${rest}초`;
  return `${rest}초`;
}

function updateAudioEstimate() {
  const el = $('audioEstimate');
  if (!el) return;
  const parts = selectedSpeechParts();
  if (!Object.values(parts).some(Boolean)) {
    el.textContent = '항목 선택';
    return;
  }
  if (!state.filtered.length) {
    el.textContent = '0개';
    return;
  }
  const seconds = estimateSpeechSeconds();
  el.textContent = `≈ ${formatDuration(seconds)} · ${state.filtered.length}`;
}

function isMobileSpeechDevice() {
  const ua = navigator.userAgent || '';
  return /Android|iPhone|iPad|iPod|Mobile/i.test(ua)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function nextSpeechDelayMs() {
  // Mobile browsers can keep ducking TTS for a moment after a WebAudio cue.
  // Leave a wider quiet gap before advancing to the next card name.
  return isMobileSpeechDevice() ? 540 : 360;
}


function clearSpeechTimers() {
  state.speechTimers.forEach((timer) => window.clearTimeout(timer));
  state.speechTimers = [];
  clearSpeechFallbackTimers();
}

function clearSpeechFallbackTimers() {
  state.speechFallbackTimers.forEach((timer) => window.clearTimeout(timer));
  state.speechFallbackTimers = [];
}

function setSpeechTimer(callback, delay) {
  const timer = window.setTimeout(() => {
    state.speechTimers = state.speechTimers.filter((item) => item !== timer);
    callback();
  }, delay);
  state.speechTimers.push(timer);
  return timer;
}

function setSpeechFallbackTimer(callback, delay) {
  const timer = window.setTimeout(() => {
    state.speechFallbackTimers = state.speechFallbackTimers.filter((item) => item !== timer);
    callback();
  }, delay);
  state.speechFallbackTimers.push(timer);
  return timer;
}

function estimatedItemDurationMs(item) {
  const compactLength = Math.max(1, String(item.text || '').replace(/\s+/g, '').length);
  const charsPerSecond = item.key === 'term' ? 5.8 : 6.8;
  const seconds = compactLength / (charsPerSecond * speechRateForItem(item));
  return Math.max(850, Math.ceil(seconds * 1000) + 450);
}


function speechWordStartForCharIndex(text, charIndex) {
  const source = String(text || '');
  const matches = [...source.matchAll(/\S+/g)];
  if (!matches.length) return -1;
  const safeCharIndex = Math.max(0, charIndex || 0);
  let active = matches.find((match) => safeCharIndex >= match.index && safeCharIndex < match.index + match[0].length);
  if (!active) active = matches.find((match) => safeCharIndex < match.index) || matches[matches.length - 1];
  return active.index;
}

function setSpeechCurrentCharIndex(charIndex, {nativeBoundary = false} = {}) {
  const current = state.speechCurrent;
  if (!current) return false;
  const nextCharIndex = Math.max(0, charIndex || 0);
  const source = String(current.targetText || current.text || '');
  const nextWordStart = speechWordStartForCharIndex(source, nextCharIndex);
  const previousWordStart = current.wordStart;
  current.charIndex = nextCharIndex;
  current.wordStart = nextWordStart;
  if (nativeBoundary && !current.usesNativeBoundary) {
    current.usesNativeBoundary = true;
    clearSpeechFallbackTimers();
  }
  return nextWordStart !== previousWordStart;
}

function scheduleFallbackWordHighlight(item, token) {
  const source = String(item.targetText || item.text || '');
  const words = [...source.matchAll(/\S+/g)];
  if (!words.length) return;
  const duration = estimatedItemDurationMs(item);
  words.forEach((match, index) => {
    const at = Math.min(duration - 160, Math.round((index / Math.max(1, words.length)) * duration));
    setSpeechFallbackTimer(() => {
      if (!state.audioPlaying || state.speechToken !== token || !state.speechCurrent) return;
      if (state.speechCurrent.key !== item.key || state.speechCurrent.usesNativeBoundary) return;
      if (setSpeechCurrentCharIndex(match.index || 0)) renderCard();
    }, at);
  });
}

function speechStartFailureMessage() {
  const isAppleMobile = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (isAppleMobile) return '모바일에서 음성이 시작되지 않았습니다. 화면의 ▶ 버튼을 다시 눌러 음성을 허용해 주세요.';
  return '음성이 시작되지 않아 자동 듣기를 멈췄습니다. 다시 재생해 주세요.';
}

function createUtterance(item, token, markStarted, finish, fail) {
  const utterance = new SpeechSynthesisUtterance(item.text);
  utterance.lang = 'ko-KR';
  const preferredVoice = preferredVoiceForItem(item);
  if (preferredVoice) utterance.voice = preferredVoice;
  utterance.rate = speechRateForItem(item);
  utterance.pitch = speechPitchForItem(item);
  utterance.onstart = () => {
    markStarted();
    // Do not overlap WebAudio chimes with short term utterances on mobile;
    // iOS/Android commonly duck or clip the beginning of TTS in that case.
    if (item.key === 'term' && !isMobileSpeechDevice()) playCardStartSound();
  };
  utterance.onboundary = (event) => {
    markStarted();
    if (!state.audioPlaying || !state.speechCurrent || state.speechToken !== token) return;
    if (event.name && event.name !== 'word') return;
    const rawCharIndex = Number(event.charIndex);
    if (!Number.isFinite(rawCharIndex) || rawCharIndex < item.prefixLength) return;
    const nextCharIndex = rawCharIndex - item.prefixLength;
    if (setSpeechCurrentCharIndex(nextCharIndex, {nativeBoundary: true})) renderCard();
  };
  utterance.onend = () => {
    markStarted();
    finish();
  };
  utterance.onerror = (event) => {
    if (event.error === 'interrupted' || event.error === 'canceled') return;
    fail();
  };
  return utterance;
}

function speakQueue(items, done) {
  if (!state.audioPlaying) return;
  clearSpeechTimers();
  const item = items.shift();
  if (!item) {
    state.speechHighlight = null;
    state.speechCurrent = null;
    state.speechUtterance = null;
    renderCard();
    done();
    return;
  }
  const token = ++state.speechToken;
  let finished = false;
  let started = false;
  let attempts = 0;
  let watchdogExtensions = 0;
  const maxAttempts = 2;

  const isCurrentSpeech = () => state.audioPlaying && state.speechToken === token;
  const markStarted = () => { started = true; };
  const finish = () => {
    if (finished || !isCurrentSpeech()) return;
    finished = true;
    clearSpeechTimers();
    state.speechUtterance = null;
    speakQueue(items, done);
  };
  const fail = () => {
    if (finished || !isCurrentSpeech()) return;
    stopAudioPlayback(speechStartFailureMessage());
  };

  state.speechHighlight = item.key;
  state.speechCurrent = {
    ...item,
    charIndex: 0,
    wordStart: speechWordStartForCharIndex(item.targetText || item.text || '', 0),
    usesNativeBoundary: false,
  };
  state.flipped = item.key !== 'term';
  state.backPage = item.key === 'exam' ? 1 : 0;
  renderCard();

  const finishWhenSpeechIsIdle = () => {
    if (finished || !isCurrentSpeech()) return;
    const synthesis = window.speechSynthesis;
    if (synthesis?.speaking && !started) markStarted();
    if ((synthesis?.speaking || synthesis?.pending) && watchdogExtensions < 24) {
      watchdogExtensions += 1;
      setSpeechTimer(finishWhenSpeechIsIdle, 500);
      return;
    }
    if (!started) {
      if (attempts < maxAttempts) {
        speak();
      } else {
        fail();
      }
      return;
    }
    finish();
  };

  const verifySpeechStarted = () => {
    if (finished || !isCurrentSpeech() || started) return;
    const synthesis = window.speechSynthesis;
    if (synthesis?.speaking || synthesis?.pending) {
      if (synthesis.speaking) markStarted();
      setSpeechTimer(verifySpeechStarted, 500);
      return;
    }
    if (attempts < maxAttempts) {
      speak();
    } else {
      fail();
    }
  };

  function speak() {
    if (!isCurrentSpeech()) return;
    attempts += 1;
    watchdogExtensions = 0;
    started = false;
    scheduleFallbackWordHighlight(item, token);
    setSpeechTimer(verifySpeechStarted, 900);
    setSpeechTimer(finishWhenSpeechIsIdle, estimatedItemDurationMs(item) + 1800);
    try {
      window.speechSynthesis.resume?.();
      const utterance = createUtterance(item, token, markStarted, finish, fail);
      state.speechUtterance = utterance;
      window.speechSynthesis.speak(utterance);
    } catch (_error) {
      fail();
    }
  }

  // 모바일 Safari/Chrome은 사용자 탭 직후가 아니면 첫 utterance를 무시할 수 있다.
  // 특히 앞면(용어)은 딜레이 없이 즉시 speak()를 호출해야 무음 스킵이 줄어든다.
  speak();
}

function setAudioButtons() {
  $('playAudioBtn').textContent = state.audioPlaying ? '…' : '▶';
  $('playAudioBtn').disabled = state.audioPlaying;
  $('stopAudioBtn').disabled = !state.audioPlaying;
  if ($('collapsedPlayBtn')) $('collapsedPlayBtn').disabled = state.audioPlaying;
  if ($('collapsedStopBtn')) $('collapsedStopBtn').disabled = !state.audioPlaying;
}

function speakCurrentAndAdvance() {
  if (!state.audioPlaying || !state.filtered.length) {
    state.audioPlaying = false;
    setAudioButtons();
    return;
  }
  const card = state.filtered[state.index];
  const items = speechItemsForCard(card);
  state.flipped = false;
  state.backPage = 0;
  state.speechHighlight = null;
  renderCard();
  if (!items.length) {
    window.setTimeout(moveAudioNext, 220);
    return;
  }
  setMessage(`▶ ${state.index + 1}/${state.filtered.length} · ${card.term}`);
  speakQueue([...items], moveAudioNext);
}



function ensureAudioContext() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  if (!state.audioContext || state.audioContext.state === 'closed') {
    state.audioContext = new AudioContextClass();
  }
  return state.audioContext;
}

function withAudioContext(callback) {
  const context = ensureAudioContext();
  if (!context) return;
  const run = () => {
    try { callback(context); } catch (_error) {}
  };
  if (context.state === 'suspended') {
    context.resume().then(run).catch(() => {});
  } else {
    run();
  }
}

function unlockAudioContext() {
  withAudioContext((context) => {
    const gain = context.createGain();
    gain.gain.value = 0.0001;
    gain.connect(context.destination);
    const oscillator = context.createOscillator();
    oscillator.connect(gain);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.02);
  });
}

function playCardStartSound() {
  withAudioContext((context) => {
    const now = context.currentTime;
    const gain = context.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.16, now + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
    gain.connect(context.destination);
    [523.25, 659.25].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(frequency, now + index * 0.045);
      oscillator.connect(gain);
      oscillator.start(now + index * 0.045);
      oscillator.stop(now + index * 0.045 + 0.12);
    });
  });
}

function playToneSequence(frequencies, {volume = 0.12, duration = 0.11, gap = 0.045, type = 'sine'} = {}) {
  withAudioContext((context) => {
    const now = context.currentTime;
    const gain = context.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(volume, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + frequencies.length * gap + duration + 0.08);
    gain.connect(context.destination);
    frequencies.forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      oscillator.type = type;
      oscillator.frequency.setValueAtTime(frequency, now + index * gap);
      oscillator.connect(gain);
      oscillator.start(now + index * gap);
      oscillator.stop(now + index * gap + duration);
    });
  });
}

function playMoveSound(direction = 1) {
  playToneSequence(direction >= 0 ? [440, 587.33] : [587.33, 440], {volume: 0.07, duration: 0.08, gap: 0.035});
}

function playShuffleSound() {
  playToneSequence([392, 523.25, 493.88], {volume: 0.075, duration: 0.07, gap: 0.032, type: 'triangle'});
}

function playMarkSound(status) {
  if (status === 'O') {
    playToneSequence([523.25, 659.25, 783.99], {volume: 0.11, duration: 0.095, gap: 0.045});
  } else {
    playToneSequence([392, 329.63], {volume: 0.095, duration: 0.12, gap: 0.055, type: 'triangle'});
  }
}

function playCardDoneSound() {
  withAudioContext((context) => {
    const now = context.currentTime;
    const master = context.createGain();
    master.gain.setValueAtTime(0.0001, now);
    master.gain.exponentialRampToValueAtTime(0.22, now + 0.018);
    master.gain.exponentialRampToValueAtTime(0.0001, now + 0.34);
    master.connect(context.destination);

    [784, 1046.5, 1318.5].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      oscillator.type = 'triangle';
      oscillator.frequency.setValueAtTime(frequency, now + index * 0.075);
      oscillator.connect(master);
      oscillator.start(now + index * 0.075);
      oscillator.stop(now + index * 0.075 + 0.18);
    });
  });
}

function moveAudioNext() {
  if (!state.audioPlaying) return;
  playCardDoneSound();
  if (!state.filtered.length || state.index >= state.filtered.length - 1) {
    window.setTimeout(() => stopAudioPlayback('자동 듣기가 끝났습니다.'), 260);
    return;
  }
  state.index += 1;
  window.setTimeout(speakCurrentAndAdvance, nextSpeechDelayMs());
}

function startSpeechKeepAlive() {
  stopSpeechKeepAlive();
  if (!('speechSynthesis' in window)) return;
  state.speechKeepAlive = window.setInterval(() => {
    if (!state.audioPlaying) return;
    try {
      if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
        window.speechSynthesis.pause();
        window.speechSynthesis.resume();
      }
    } catch (_error) {}
  }, 7000);
}

function stopSpeechKeepAlive() {
  if (state.speechKeepAlive) {
    window.clearInterval(state.speechKeepAlive);
    state.speechKeepAlive = null;
  }
}

function startAudioPlayback() {
  if (!('speechSynthesis' in window)) {
    setMessage('이 브라우저는 음성 합성을 지원하지 않습니다.', true);
    return;
  }
  unlockAudioContext();
  window.speechSynthesis.cancel();
  window.speechSynthesis.getVoices();
  if (!state.filtered.length) {
    setMessage('재생할 카드가 없습니다.', true);
    return;
  }
  const parts = selectedSpeechParts();
  if (!Object.values(parts).some(Boolean)) {
    setMessage('들을 항목을 하나 이상 체크하세요.', true);
    return;
  }
  state.audioPlaying = true;
  startSpeechKeepAlive();
  setAudioButtons();
  speakCurrentAndAdvance();
}

function stopAudioPlayback(message = '자동 듣기를 정지했습니다.') {
  state.audioPlaying = false;
  state.speechToken += 1;
  clearSpeechTimers();
  stopSpeechKeepAlive();
  state.speechHighlight = null;
  state.speechCurrent = null;
  state.speechUtterance = null;
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  setAudioButtons();
  setMessage(message);
}

function isBokAppeared(card) {
  return String(card?.bok_appeared || '').trim().toUpperCase() === 'O';
}

function setBokBadge(id, card) {
  const el = $(id);
  if (!el) return;
  const visible = isBokAppeared(card);
  el.hidden = !visible;
  el.textContent = '한은';
  el.title = '한국은행 기출/면접 출처 포함';
}

function ratingValue(value) {
  return ['상', '중', '하'].includes(String(value || '').trim()) ? String(value).trim() : '중';
}

function importanceLabel(value) {
  return {'상': '⭐⭐⭐', '중': '⭐⭐', '하': '⭐'}[ratingValue(value)] || '⭐⭐';
}

function difficultyLabel(value) {
  return {'상': '▲▲▲', '중': '▲▲', '하': '▲'}[ratingValue(value)] || '▲▲';
}

function ratingTitle(kind, value) {
  const label = kind === 'importance' ? '중요도' : '난이도';
  return `${label} ${ratingValue(value)}`;
}

function ratingClass(kind, value) {
  const levelClass = {'상': 'level-high', '중': 'level-mid', '하': 'level-low'}[ratingValue(value)] || 'level-mid';
  return `badge rating ${kind} ${levelClass}`;
}

function statusLabel(value) {
  if (value === 'O') return 'O';
  if (value === 'X') return 'X';
  return '–';
}

function setMessage(text, isError = false) {
  const el = $('message');
  el.textContent = text;
  el.style.color = isError ? '#fb7185' : '#aab6cf';
}

function parseRelated(text) {
  const matches = [...(text || '').matchAll(/\[\[([^\]]+)\]\]/g)].map((m) => m[1]);
  if (matches.length) return matches;
  return (text || '').split(',').map((x) => x.trim()).filter(Boolean);
}

function detailedSections(text) {
  const source = String(text || '').trim();
  if (!source) return [];
  const labels = ['의미', '동작/활용', '활용', '관련 개념', '구분 포인트', '시험 대비'];
  return labels.map((label, index) => {
    const start = source.indexOf(`${label}:`);
    if (start < 0) return null;
    const contentStart = start + label.length + 1;
    const nextPositions = labels
      .slice(index + 1)
      .map((nextLabel) => source.indexOf(`${nextLabel}:`, contentStart))
      .filter((position) => position >= 0);
    const end = nextPositions.length ? Math.min(...nextPositions) : -1;
    const content = source.slice(contentStart, end >= 0 ? end : undefined).trim();
    return content ? {label, content} : null;
  }).filter(Boolean);
}

function highlightTermsHtml(text, terms = []) {
  const source = String(text || '');
  const cleanTerms = [...new Set(terms.map((term) => String(term || '').trim()).filter((term) => term.length >= 2))]
    .sort((a, b) => b.length - a.length);
  if (!cleanTerms.length) return escapeHtml(source);
  const escapedTerms = cleanTerms.map((term) => term.replace(/[.*+?^${}()|[\\\]]/g, '\\$&'));
  const pattern = new RegExp(`(${escapedTerms.join('|')})`, 'gi');
  let html = '';
  let lastIndex = 0;
  source.replace(pattern, (match, _value, offset) => {
    html += escapeHtml(source.slice(lastIndex, offset));
    html += `<strong class="term-emphasis">${escapeHtml(match)}</strong>`;
    lastIndex = offset + match.length;
    return match;
  });
  html += escapeHtml(source.slice(lastIndex));
  return html;
}

function cardTerms(card) {
  return [card?.term, card?.english].filter(Boolean);
}

function speechChunkSizeForKey(key) {
  return ['definition', 'detail', 'exam'].includes(key) ? 3 : 2;
}

function isHardPhraseEnd(word) {
  return /[.!?。！？]"?'?$/.test(String(word || ''));
}

function speechChunkRange(matches, activeIndex, key) {
  if (!matches.length || activeIndex < 0) return null;
  const chunkSize = speechChunkSizeForKey(key);
  let start = Math.floor(activeIndex / chunkSize) * chunkSize;
  let end = Math.min(matches.length - 1, start + chunkSize - 1);

  for (let index = activeIndex - 1; index >= start; index -= 1) {
    if (isHardPhraseEnd(matches[index][0])) {
      start = index + 1;
      break;
    }
  }
  for (let index = activeIndex; index < end; index += 1) {
    if (isHardPhraseEnd(matches[index][0])) {
      end = index;
      break;
    }
  }

  return {
    start: matches[start].index,
    end: matches[end].index + matches[end][0].length,
  };
}

function currentWordHtml(text, key, detailLabel = null, terms = []) {
  const source = String(text || '');
  const current = state.speechCurrent;
  const shouldHighlight = current
    && current.key === key
    && (detailLabel === null || current.detailLabel === detailLabel);
  if (!shouldHighlight) return highlightTermsHtml(source, terms);

  const charIndex = Math.max(0, current.charIndex || 0);
  const matches = [...source.matchAll(/\S+/g)];
  let activeIndex = matches.findIndex((match) => charIndex >= match.index && charIndex < match.index + match[0].length);
  if (activeIndex < 0) {
    activeIndex = matches.findIndex((match) => charIndex < match.index);
    if (activeIndex < 0 && matches.length) activeIndex = matches.length - 1;
  }
  const range = speechChunkRange(matches, activeIndex, key);
  if (!range) return highlightTermsHtml(source, terms);

  return `${escapeHtml(source.slice(0, range.start))}<span class="current-word">${escapeHtml(source.slice(range.start, range.end))}</span>${escapeHtml(source.slice(range.end))}`;
}

function detailMeta(label) {
  return {
    '의미': {icon: '○', title: '의미'},
    '활용': {icon: '⌁', title: '활용'},
    '동작/활용': {icon: '⌁', title: '활용'},
    '관련 개념': {icon: '↔', title: '연결'},
    '구분 포인트': {icon: '◇', title: '구분'},
    '시험 대비': {icon: '✓', title: '시험'},
  }[label] || {icon: '·', title: label};
}

function renderDetailedExplanation(text, terms = []) {
  const sections = detailedSections(text);
  if (!sections.length) return `<div class="detail-card"><p>${currentWordHtml(text || '', 'detail', null, terms)}</p></div>`;
  return sections.map((section) => {
    const meta = detailMeta(section.label);
    return `
      <article class="detail-card detail-${escapeHtml(section.label.replace(/[^가-힣A-Za-z0-9]/g, '-'))}">
        <div class="detail-heading">
          <span class="detail-icon" aria-hidden="true">${escapeHtml(meta.icon)}</span>
          <div>
            <div class="detail-label" data-raw-label="${escapeHtml(section.label)}">${escapeHtml(meta.title)}</div>
          </div>
        </div>
        <p>${currentWordHtml(section.content, 'detail', section.label, terms)}</p>
      </article>
    `;
  }).join('');
}


function uniqueRelatedConcepts(text) {
  return [...new Set(parseRelated(text).map((item) => item.trim()).filter(Boolean))];
}

function conceptNodeHtml(cardOrName, {kind = 'direct', count = 0} = {}) {
  const target = typeof cardOrName === 'string' ? findCardByConcept(cardOrName) : cardOrName;
  const label = typeof cardOrName === 'string' ? cardOrName : cardOrName?.term;
  const missing = target ? '' : ' graph-missing';
  const countBadge = count > 1 ? `<em>${count}</em>` : '';
  const targetTerm = target?.term || label;
  return `
    <button class="concept-node graph-${kind}${missing}" type="button" data-term="${escapeHtml(targetTerm)}" title="${escapeHtml(target?.english || targetTerm || '')}">
      <strong>${escapeHtml(target?.term || label || '')}</strong>
      ${countBadge}
    </button>
  `;
}

function relatedTargetCards(card) {
  return uniqueRelatedConcepts(card.related_concepts)
    .map((name) => findCardByConcept(name) || {term: name, english: '', category: '', related_concepts: ''})
    .filter((item) => normalizeTerm(item.term) !== normalizeTerm(card.term));
}

function expandedConcepts(card, directCards) {
  const directTerms = new Set(directCards.map((item) => normalizeTerm(item.term)));
  directTerms.add(normalizeTerm(card.term));
  const scores = new Map();

  directCards.forEach((direct) => {
    const realDirect = findCardByConcept(direct.term);
    if (!realDirect) return;
    uniqueRelatedConcepts(realDirect.related_concepts).forEach((name) => {
      const target = findCardByConcept(name);
      const normalized = normalizeTerm(target?.term || name);
      if (!normalized || directTerms.has(normalized)) return;
      const previous = scores.get(normalized) || {name, card: target, count: 0, via: []};
      previous.count += 1;
      previous.via.push(realDirect.term);
      if (target) previous.card = target;
      scores.set(normalized, previous);
    });
  });

  return [...scores.values()]
    .sort((a, b) => b.count - a.count || (a.card?.category || '').localeCompare(b.card?.category || '') || a.name.localeCompare(b.name))
    .slice(0, 3);
}

function renderConceptGraph(card) {
  const directCards = relatedTargetCards(card).slice(0, 4);
  const expanded = expandedConcepts(card, directCards);
  if (!directCards.length) {
    return '<div class="graph-empty muted">—</div>';
  }

  const directHtml = directCards.map((target) => conceptNodeHtml(target, {kind: 'direct'})).join('');
  const expandedHtml = expanded.map((item) => conceptNodeHtml(item.card || item.name, {kind: 'expanded', count: item.count})).join('');

  return `
    <div class="graph-mini-row graph-direct-links">${directHtml}</div>
    ${expandedHtml ? `<div class="graph-mini-row graph-expanded-links">${expandedHtml}</div>` : ''}
  `;
}

function conceptImageUrl(card) {
  const url = String(card?.concept_image_url || card?.image_url || '').trim();
  if (!url) return '';
  if (url.startsWith('/static/generated/') || url.startsWith('/api/concept-images/')) return '';
  return url;
}

function isDirectImageUrl(url) {
  try {
    const parsed = new window.URL(url, window.location.origin);
    return /\.(avif|gif|jpe?g|png|svg|webp)$/i.test(parsed.pathname);
  } catch (_error) {
    return /\.(avif|gif|jpe?g|png|svg|webp)(\?.*)?$/i.test(url);
  }
}

function conceptImageAlt(card) {
  const explicit = String(card?.concept_image_alt || card?.image_alt || '').trim();
  if (explicit) return explicit;
  const term = card?.term || card?.english || '개념';
  const category = card?.category ? `(${card.category})` : '';
  return `${term}${category} 이해를 돕는 학습용 개념 이미지`;
}

function renderConceptImage(card) {
  const wrap = $('backConceptImageWrap');
  const image = $('backConceptImage');
  if (!wrap || !image) return;

  const url = conceptImageUrl(card);
  if (!url || !isDirectImageUrl(url)) {
    wrap.hidden = true;
    image.removeAttribute('src');
    image.removeAttribute('title');
    image.alt = '';
    image.hidden = false;
    return;
  }

  image.hidden = false;
  image.src = url;
  image.alt = conceptImageAlt(card);
  image.title = `${googleSearchQuery(card)} 구글 AI 검색`;
  wrap.hidden = false;
}

async function loadCards() {
  const res = await fetch('/api/cards');
  if (!res.ok) throw new Error(await res.text());
  const data = await res.json();
  state.cards = data.cards;
  state.summary = data.summary;
  buildCategoryOptions(data.summary.categories || []);
  restoreViewState();
  applyFilters();
  $('csvPath').textContent = data.summary.csv_path;
  setAudioButtons();
  updateAudioEstimate();
}

async function refreshCards() {
  if (state.audioPlaying) stopAudioPlayback('정지');
  const currentId = state.filtered[state.index]?.id;
  await loadCards();
  if (currentId) {
    const found = state.filtered.findIndex((card) => card.id === currentId);
    if (found >= 0) state.index = found;
  }
  renderCard();
  setMessage('↻');
}

function buildCategoryOptions(categories) {
  const current = $('categorySelect')?.value || '';
  if (!$('categorySelect')) return;
  $('categorySelect').innerHTML = '<option value="">▦ *</option>' +
    categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(categoryLabel(category))}</option>`).join('');
  $('categorySelect').value = categories.includes(current) ? current : '';
}

function summaryFromRows(rows) {
  const known = rows.filter((card) => card.known_status === 'O').length;
  const unknown = rows.filter((card) => card.known_status === 'X').length;
  return {
    ...(state.summary || {}),
    total: rows.length,
    known,
    unknown,
    unreviewed: rows.length - known - unknown,
  };
}

function renderStats(summary) {
  $('statTotal').textContent = summary.total;
  $('statKnown').textContent = summary.known;
  $('statUnknown').textContent = summary.unknown;
  $('statUnreviewed').textContent = summary.unreviewed;
  updateStatFilterButtons();
}

function setMarkButtonsDisabled(disabled) {
  ['knownBtn', 'unknownBtn', 'unreviewedBtn'].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = disabled;
  });
}

function advanceAfterMark(markedId) {
  if (!state.filtered.length) return;
  const currentIndex = state.filtered.findIndex((card) => card.id === markedId);
  if (currentIndex >= 0 && state.filtered.length > 1) {
    state.index = (currentIndex + 1) % state.filtered.length;
  } else {
    state.index = Math.min(state.index, state.filtered.length - 1);
  }
  state.flipped = false;
  state.backPage = 0;
  renderCard();
}

function resetBackScroll() {
  const scrollArea = document.querySelector('.back-scroll');
  if (scrollArea) scrollArea.scrollTop = 0;
}

function setBackPage(page) {
  const nextPage = Math.max(0, Math.min(1, page));
  if (nextPage === state.backPage) return;
  state.backPage = nextPage;
  renderBackPage();
  resetBackScroll();
}

function renderBackPage() {
  const page = state.backPage || 0;
  $('backPageOne')?.classList.toggle('active', page === 0);
  $('backPageTwo')?.classList.toggle('active', page === 1);
  if ($('backPageText')) $('backPageText').textContent = `${page + 1} / 2`;
  if ($('backPagePrev')) $('backPagePrev').disabled = page === 0;
  if ($('backPageNext')) $('backPageNext').disabled = page === 1;
}

function applyFilters(keepCurrentId = null) {
  if (state.audioPlaying) stopAudioPlayback('필터가 바뀌어 자동 듣기를 정지했습니다.');
  const query = $('searchInput').value.trim().toLowerCase();
  const category = $('categorySelect')?.value || '';
  state.importanceFilter = $('importanceSelect')?.value || '';
  state.difficultyFilter = $('difficultySelect')?.value || '';
  state.bokFilter = $('bokSelect')?.value || '';
  const status = state.statusFilter;
  const importance = state.importanceFilter;
  const difficulty = state.difficultyFilter;
  const bok = state.bokFilter;
  state.filtered = state.cards.filter((c) => {
    const haystack = [c.id, c.term, c.english, c.category, c.bok_appeared === 'O' ? '한국은행 한은 BOK' : '', c.importance, c.difficulty, c.definition, c.detailed_explanation, c.related_concepts, c.exam_note].join(' ').toLowerCase();
    const statusOk = !status || (status === 'unreviewed' ? !c.known_status : c.known_status === status);
    const bokOk = !bok || (bok === 'O' ? isBokAppeared(c) : !isBokAppeared(c));
    return (!query || haystack.includes(query))
      && (!category || c.category === category)
      && (!importance || c.importance === importance)
      && (!difficulty || c.difficulty === difficulty)
      && bokOk
      && statusOk;
  });
  if (keepCurrentId) {
    const found = state.filtered.findIndex((c) => c.id === keepCurrentId);
    state.index = found >= 0 ? found : Math.min(state.index, Math.max(0, state.filtered.length - 1));
  } else {
    state.index = Math.min(state.index, Math.max(0, state.filtered.length - 1));
  }
  state.flipped = false;
  state.backPage = 0;
  renderCard();
  renderStats(summaryFromRows(state.filtered));
  updateAudioEstimate();
}

function renderCard() {
  cardEl.classList.toggle('flipped', state.flipped);
  renderBackPage();
  const total = state.filtered.length;
  if (document.activeElement !== $('positionInput')) $('positionInput').value = total ? String(state.index + 1) : '0';
  $('positionInput').max = String(total || 0);
  $('positionTotal').textContent = String(total || 0);
  if (!total) {
    $('frontTerm').textContent = '카드 없음';
    $('frontEnglish').textContent = '필터 조건을 바꿔주세요.';
    $('frontCategory').textContent = '-';
    $('frontStatus').textContent = '-';
    $('frontImportance').textContent = '-';
    $('frontDifficulty').textContent = '-';
    setBokBadge('frontBok', null);
    setBokBadge('backBok', null);
    applyCategoryTheme('');
    applyFrontIllustration({term: '카드 없음', english: '', category: ''});
    renderConceptImage(null);
    $('conceptGraph').innerHTML = '<div class="graph-empty muted">표시할 그래프가 없습니다.</div>';
    ['frontGoogleSearchLink', 'backGoogleSearchLink'].forEach((id) => { $(id).href = '#'; });
    state.renderedCardId = null;
    state.renderedFlipped = false;
    resetBackScroll();
    updateConceptBackButton();
    saveViewState();
    return;
  }

  const c = state.filtered[state.index];
  const shouldResetBackScroll = state.renderedCardId !== c.id || (state.flipped && !state.renderedFlipped);
  applyCategoryTheme(c.category);
  applyFrontIllustration(c);
  $('frontCategory').textContent = categoryLabel(c.category);
  $('frontStatus').textContent = statusLabel(c.known_status);
  setBokBadge('frontBok', c);
  setBokBadge('backBok', c);
  $('frontImportance').textContent = importanceLabel(c.importance);
  $('frontDifficulty').textContent = difficultyLabel(c.difficulty);
  $('frontCategory').className = `badge category-badge ${categoryMeta(c.category).className}`;
  $('backCategory').className = `badge category-badge ${categoryMeta(c.category).className}`;
  $('frontStatus').className = `badge status ${c.known_status === 'O' ? 'o' : c.known_status === 'X' ? 'x' : ''}`;
  $('frontImportance').className = ratingClass('importance', c.importance);
  $('frontDifficulty').className = ratingClass('difficulty', c.difficulty);
  $('frontImportance').title = ratingTitle('importance', c.importance);
  $('frontDifficulty').title = ratingTitle('difficulty', c.difficulty);
  $('frontTerm').innerHTML = currentWordHtml(c.term, 'term');
  $('frontEnglish').textContent = c.english || '';
  const googleUrl = googleSearchUrl(c);
  const googleQuery = googleSearchQuery(c);
  $('frontGoogleSearchLink').href = googleUrl;
  $('frontGoogleSearchLink').title = `${googleQuery} 구글 검색`;
  $('backGoogleSearchLink').href = googleUrl;
  $('backGoogleSearchLink').title = `${googleQuery} 구글 검색`;

  $('backCategory').textContent = categoryLabel(c.category);
  $('backImportance').textContent = importanceLabel(c.importance);
  $('backDifficulty').textContent = difficultyLabel(c.difficulty);
  $('backImportance').className = ratingClass('importance', c.importance);
  $('backDifficulty').className = ratingClass('difficulty', c.difficulty);
  $('backImportance').title = ratingTitle('importance', c.importance);
  $('backDifficulty').title = ratingTitle('difficulty', c.difficulty);
  $('backId').textContent = c.id;
  $('backTerm').innerHTML = `${currentWordHtml(c.term, 'term')}${c.english ? ' / ' + escapeHtml(c.english) : ''}`;
  renderConceptImage(c);
  const emphasisTerms = cardTerms(c);
  $('definition').innerHTML = currentWordHtml(c.definition || '', 'definition', null, emphasisTerms);
  $('detail').innerHTML = renderDetailedExplanation(c.detailed_explanation, emphasisTerms);
  $('sources').textContent = c.source_files || '';
  $('examNote').innerHTML = currentWordHtml(c.exam_note || '', 'exam', null, emphasisTerms);
  const related = parseRelated(c.related_concepts);
  $('related').innerHTML = related.map((r) => `<button class="chip" type="button" data-term="${escapeHtml(r)}">${currentWordHtml(r, 'related')}</button>`).join('') || '<span class="muted">없음</span>';
  $('conceptGraph').innerHTML = renderConceptGraph(c);
  bindConceptGraphNodes();
  applySpeechHighlight();
  if (shouldResetBackScroll) resetBackScroll();
  state.renderedCardId = c.id;
  state.renderedFlipped = state.flipped;
  updateConceptBackButton();
  saveViewState();
}


function applySpeechHighlight() {
  document.querySelectorAll('.speaking-section').forEach((element) => element.classList.remove('speaking-section'));
  const current = state.speechCurrent;
  if (!current) return;
  const target = {
    term: state.flipped ? document.querySelector('.back-term-line') : document.querySelector('.front-term-line'),
    definition: $('definition').closest('section'),
    detail: current.detailLabel
      ? [...document.querySelectorAll('.detail-card')].find((card) => card.querySelector('.detail-label')?.dataset.rawLabel === current.detailLabel)
      : $('detail'),
    related: $('related').closest('section'),
    exam: $('examNote').closest('section'),
  }[current.key];
  if (target) target.classList.add('speaking-section');
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function updateRandomButtons() {
  ['shuffleBtn'].forEach((id) => {
    const button = $(id);
    if (!button) return;
    button.classList.toggle('active', state.randomMode);
    button.setAttribute('aria-pressed', String(state.randomMode));
  });
}

function toggleRandomMode() {
  state.randomMode = !state.randomMode;
  updateRandomButtons();
  playShuffleSound();
  setMessage(state.randomMode ? '↯ ON' : '↯ OFF');
}

function move(delta) {
  if (state.audioPlaying) stopAudioPlayback('수동 이동으로 자동 듣기를 정지했습니다.');
  if (!state.filtered.length) return;
  if (state.randomMode && state.filtered.length > 1) {
    let nextIndex = state.index;
    while (nextIndex === state.index) nextIndex = Math.floor(Math.random() * state.filtered.length);
    state.index = nextIndex;
    playShuffleSound();
  } else {
    state.index = (state.index + delta + state.filtered.length) % state.filtered.length;
    playMoveSound(delta);
  }
  state.flipped = false;
  state.backPage = 0;
  renderCard();
}

function randomCard() {
  if (state.audioPlaying) stopAudioPlayback('랜덤 이동으로 자동 듣기를 정지했습니다.');
  if (!state.filtered.length) return;
  state.index = Math.floor(Math.random() * state.filtered.length);
  playShuffleSound();
  state.flipped = false;
  state.backPage = 0;
  renderCard();
}

async function mark(status) {
  if (!state.filtered.length || state.markSaving) return;
  const current = state.filtered[state.index];
  const idx = state.cards.findIndex((c) => c.id === current.id);
  const previous = idx >= 0 ? {...state.cards[idx]} : {...current};
  const optimistic = {...previous, known_status: status};
  if (status) {
    optimistic.last_reviewed = new Date().toISOString();
    optimistic.review_count = String((Number.parseInt(previous.review_count || '0', 10) || 0) + 1);
  } else {
    optimistic.last_reviewed = '';
  }

  state.markSaving = true;
  setMarkButtonsDisabled(true);
  if (idx >= 0) state.cards[idx] = optimistic;
  const filteredIdx = state.filtered.findIndex((c) => c.id === current.id);
  if (filteredIdx >= 0) state.filtered[filteredIdx] = optimistic;
  applyFilters(current.id);
  advanceAfterMark(current.id);
  playMarkSound(status);
  setMessage(`${optimistic.term}: ${statusLabel(status)} 저장 중...`);

  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(current.id)}/mark`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({known_status: status}),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    const savedIdx = state.cards.findIndex((c) => c.id === current.id);
    if (savedIdx >= 0) state.cards[savedIdx] = data.card;
    state.summary = data.summary;
    applyFilters(data.card.id);
    advanceAfterMark(data.card.id);
    setMessage(`${data.card.term}: ${statusLabel(status)} 저장 완료`);
  } catch (error) {
    const restoreIdx = state.cards.findIndex((c) => c.id === current.id);
    if (restoreIdx >= 0) state.cards[restoreIdx] = previous;
    applyFilters(current.id);
    setMessage(`저장 실패: ${error.message || error}`, true);
  } finally {
    state.markSaving = false;
    setMarkButtonsDisabled(false);
  }
}

cardEl.addEventListener('click', (e) => {
  if (e.target.closest('button, a')) return;
  const rect = cardEl.getBoundingClientRect();
  const edge = Math.max(78, rect.width * 0.12);
  if (e.clientX - rect.left <= edge) { move(-1); return; }
  if (rect.right - e.clientX <= edge) { move(1); return; }
  state.speechHighlight = null;
  state.speechCurrent = null;
  state.flipped = !state.flipped;
  if (state.flipped) state.backPage = 0;
  renderCard();
});
function updateStatFilterButtons() {
  document.querySelectorAll('[data-status-filter]').forEach((button) => {
    button.classList.toggle('active', button.dataset.statusFilter === state.statusFilter);
  });
}

function setStatusFilter(status) {
  state.statusFilter = status;
  state.index = 0;
  updateStatFilterButtons();
  applyFilters();
}

function reloadFromLogo(event) {
  event?.preventDefault?.();
  event?.stopPropagation?.();
  if (state.audioPlaying) stopAudioPlayback('정지');
  window.location.reload();
}

$('logoRefreshBtn').addEventListener('click', reloadFromLogo);
$('logoRefreshBtn').addEventListener('touchend', reloadFromLogo, {passive: false});
document.querySelectorAll('[data-status-filter]').forEach((button) => button.addEventListener('click', () => setStatusFilter(button.dataset.statusFilter)));
$('controlsToggle').addEventListener('click', toggleControlsPanel);
$('positionInput').addEventListener('change', () => jumpFromInput());
$('positionInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); jumpFromInput(); $('positionInput').blur(); } });
$('backPagePrev').addEventListener('click', () => setBackPage(state.backPage - 1));
$('backPageNext').addEventListener('click', () => setBackPage(state.backPage + 1));
$('conceptBackBtn')?.addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  goBackToPreviousConcept();
});
$('shuffleBtn').addEventListener('click', toggleRandomMode);
$('knownBtn').addEventListener('click', () => mark('O'));
$('unknownBtn').addEventListener('click', () => mark('X'));
$('unreviewedBtn').addEventListener('click', () => mark(''));
$('playAudioBtn').addEventListener('click', startAudioPlayback);
$('stopAudioBtn').addEventListener('click', () => stopAudioPlayback());
$('collapsedPlayBtn').addEventListener('click', startAudioPlayback);
$('collapsedStopBtn').addEventListener('click', () => stopAudioPlayback());
['speakTerm', 'speakDefinition', 'speakDetail', 'speakRelated', 'speakExam', 'speechRate'].forEach((id) => {
  $(id).addEventListener('change', updateAudioEstimate);
});
$('searchInput').addEventListener('input', () => { state.index = 0; applyFilters(); });
$('searchInput').addEventListener('keydown', returnFocusFromSearchInput);
['frontGoogleSearchLink', 'backGoogleSearchLink'].forEach((id) => {
  $(id)?.addEventListener('click', openCurrentGoogleSearch);
});
$('backConceptImageWrap')?.addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  openCurrentGoogleSearch(event);
});
['categorySelect', 'importanceSelect', 'difficultySelect', 'bokSelect'].forEach((id) => {
  $(id)?.addEventListener('change', () => { state.index = 0; applyFilters(); });
});
function goToConceptTerm(term) {
  const card = findCardByConcept(term);
  if (!jumpToCard(card, {rememberCurrent: true})) {
    setMessage(`${term} 카드를 찾지 못했습니다.`, true);
  }
}

function handleConceptJump(e) {
  const btn = e.target.closest('[data-term]');
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  goToConceptTerm(btn.dataset.term);
}

function bindConceptGraphNodes() {
  document.querySelectorAll('#conceptGraph [data-term]').forEach((node) => {
    node.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      goToConceptTerm(node.dataset.term);
    };
  });
}

$('related').addEventListener('click', handleConceptJump);
$('conceptGraph').addEventListener('click', handleConceptJump, true);
$('conceptGraph').addEventListener('mousedown', (e) => {
  if (e.target.closest('[data-term]')) e.preventDefault();
}, true);

document.addEventListener('keydown', (e) => {
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
    if (e.key === 'Escape') {
      document.activeElement.blur();
      focusAppCard();
    }
    return;
  }

  const key = e.key.toLowerCase();
  if (e.key === ' ') { e.preventDefault(); state.flipped = !state.flipped; if (state.flipped) state.backPage = 0; renderCard(); }
  else if (state.flipped && e.key === 'ArrowUp') { e.preventDefault(); setBackPage(state.backPage - 1); }
  else if (state.flipped && e.key === 'ArrowDown') { e.preventDefault(); setBackPage(state.backPage + 1); }
  else if (e.key === 'ArrowLeft') move(-1);
  else if (e.key === 'ArrowRight') move(1);
  else if (key === 'o' || e.key === '.') mark('O');
  else if (key === 'x') { e.preventDefault(); mark('X'); }
  else if (key === 'r') toggleRandomMode();
  else if (e.key === 'Enter') { e.preventDefault(); state.audioPlaying ? stopAudioPlayback() : startAudioPlayback(); }
  else if (key === 'f' || e.key === '/') { e.preventDefault(); focusSearchInput(); }
  else if (key === 'g') { e.preventDefault(); openCurrentGoogleSearch(e); }
});

applyControlsCollapsed();
updateRandomButtons();

loadCards().catch((err) => {
  setMessage(`로딩 실패: ${err.message}`, true);
  applyFrontIllustration({term: '로딩 실패', english: '', category: ''});
  $('frontTerm').textContent = '로딩 실패';
  $('frontEnglish').textContent = err.message;
});
