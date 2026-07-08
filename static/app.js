const state = {
  cards: [],
  filtered: [],
  index: 0,
  flipped: false,
  summary: null,
  audioPlaying: false,
  markSaving: false,
  bookmarkSaving: false,
  memoSaving: false,
  menuOpen: false,
  speechHighlight: null,
  speechCurrent: null,
  speechUtterance: null,
  audioContext: null,
  speechTimers: [],
  speechFallbackTimers: [],
  speechToken: 0,
  speechKeepAlive: null,
  audioListRepeatIndex: 0,
  controlsCollapsed: localStorage.getItem('controlsCollapsed') !== '0',
  backPage: 0,
  statusFilter: '',
  bookmarkFilter: false,
  importanceFilter: '',
  difficultyFilter: '',
  bokFilter: '',
  randomMode: false,
  conceptHistory: [],
  renderedCardId: null,
  renderedFlipped: false,
  questionMode: false,
  questionLoading: false,
  questions: [],
  questionIndex: 0,
  answerRevealed: false,
  selectedChoiceIndex: null,
};

const $ = (id) => document.getElementById(id);
const cardEl = $('card');
const VIEW_STATE_KEY = 'csFlashcardsViewState:v1';
const AUDIO_SETTINGS_KEY = 'csFlashcardsAudioSettings:v1';
const AUDIO_PRESETS_KEY = 'csFlashcardsAudioPresets:v1';
const AUDIO_SETTING_IDS = ['speakTerm', 'speakDefinition', 'speakDetail', 'speakRelated', 'speakExam', 'speakDetailMeaning', 'speakDetailUsage', 'termSpeechMode', 'termRepeatCount', 'cardRepeatCount', 'listRepeatCount', 'speechRate', 'speechVoice'];
const QUESTION_TYPE_LABELS = {short: '주관식', subjective: '서술형', multiple_choice: '객관식', essay: '논술형'};
const AI_QUIZ_PROMPT_TYPE_ORDER = ['multiple_choice', 'short', 'subjective', 'essay'];
const AI_QUIZ_TERM_LIMIT = 80;

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
  state.bookmarkFilter = Boolean(saved.bookmarkFilter);
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
      bookmarkFilter: Boolean(state.bookmarkFilter),
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

function googleAiSearchUrl(query) {
  const params = new URLSearchParams({q: String(query || ''), udm: '50'});
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
    bookmarkFilter: Boolean(state.bookmarkFilter),
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
  state.bookmarkFilter = Boolean(snapshot.bookmarkFilter);
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
  state.bookmarkFilter = false;
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

function selectIntValue(id, fallback = 1, min = 1, max = 5) {
  const value = Number($(id)?.value || fallback);
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value)));
}

function termSpeechMode() {
  return $('termSpeechMode')?.value === 'ko_en' ? 'ko_en' : 'ko';
}

function termRepeatCount() {
  return selectIntValue('termRepeatCount', 1, 1, 5);
}

function cardRepeatCount() {
  return selectIntValue('cardRepeatCount', 1, 1, 5);
}

function listRepeatCount() {
  if ($('listRepeatCount')?.value === 'infinite') return Infinity;
  return selectIntValue('listRepeatCount', 1, 1, 5);
}

function selectedDetailSpeechSections() {
  return {
    meaning: $('speakDetailMeaning')?.checked !== false,
    usage: $('speakDetailUsage')?.checked !== false,
  };
}

function shouldSpeakDetailSection(label) {
  const sections = selectedDetailSpeechSections();
  if (label === '의미') return sections.meaning;
  if (label === '활용' || label === '동작/활용') return sections.usage;
  return false;
}

function termSpeechText(card) {
  const korean = String(card?.term || '').trim();
  const english = String(card?.english || '').trim();
  if (termSpeechMode() === 'ko_en' && english) return `${korean}. ${english}`.trim();
  return korean;
}

function collectAudioSettings() {
  const settings = {};
  AUDIO_SETTING_IDS.forEach((id) => {
    const element = $(id);
    if (!element) return;
    settings[id] = element.type === 'checkbox' ? element.checked : element.value;
  });
  return settings;
}

function applyAudioSettings(settings = {}) {
  AUDIO_SETTING_IDS.forEach((id) => {
    const element = $(id);
    if (!element || !(id in settings)) return;
    if (element.type === 'checkbox') {
      element.checked = Boolean(settings[id]);
    } else if ([...element.options].some((option) => option.value === String(settings[id]))) {
      element.value = String(settings[id]);
    }
  });
}

function saveAudioSettings() {
  try {
    localStorage.setItem(AUDIO_SETTINGS_KEY, JSON.stringify(collectAudioSettings()));
  } catch (_error) {}
}

function restoreAudioSettings() {
  try {
    applyAudioSettings(JSON.parse(localStorage.getItem(AUDIO_SETTINGS_KEY) || '{}'));
  } catch (_error) {}
}

function loadAudioPresets() {
  try {
    const presets = JSON.parse(localStorage.getItem(AUDIO_PRESETS_KEY) || '[]');
    return Array.isArray(presets) ? presets.filter((preset) => preset && preset.id && preset.name && preset.settings) : [];
  } catch (_error) {
    return [];
  }
}

function saveAudioPresets(presets) {
  try {
    localStorage.setItem(AUDIO_PRESETS_KEY, JSON.stringify(presets));
  } catch (_error) {}
}

function renderAudioPresets() {
  const list = $('audioPresetList');
  if (!list) return;
  const presets = loadAudioPresets();
  if (!presets.length) {
    list.innerHTML = '<span class="audio-preset-empty">저장된 프리셋 없음</span>';
    return;
  }
  list.innerHTML = presets.map((preset) => `
    <span class="audio-preset-item">
      <button class="audio-preset-apply" type="button" data-preset-id="${escapeHtml(preset.id)}">${escapeHtml(preset.name)}</button>
      <button class="audio-preset-delete" type="button" data-preset-delete="${escapeHtml(preset.id)}" aria-label="${escapeHtml(preset.name)} 프리셋 삭제">×</button>
    </span>
  `).join('');
}

function nextAudioPresetName(presets) {
  const used = new Set(presets.map((preset) => preset.name));
  let index = presets.length + 1;
  while (used.has(`프리셋 ${index}`)) index += 1;
  return `프리셋 ${index}`;
}

function saveCurrentAudioPreset() {
  const presets = loadAudioPresets();
  const input = $('audioPresetNameInput');
  const name = String(input?.value || '').trim() || nextAudioPresetName(presets);
  const nextPreset = {
    id: `preset-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    settings: collectAudioSettings(),
    updatedAt: new Date().toISOString(),
  };
  const existingIndex = presets.findIndex((preset) => preset.name === name);
  if (existingIndex >= 0) {
    nextPreset.id = presets[existingIndex].id;
    presets[existingIndex] = nextPreset;
  } else {
    presets.push(nextPreset);
  }
  saveAudioPresets(presets.slice(-20));
  if (input) input.value = '';
  renderAudioPresets();
  setMessage(`${name} 프리셋을 저장했습니다.`);
}

function applyAudioPreset(presetId) {
  const preset = loadAudioPresets().find((item) => item.id === presetId);
  if (!preset) return;
  applyAudioSettings(preset.settings || {});
  saveAudioSettings();
  updateAudioEstimate();
  setMessage(`${preset.name} 프리셋을 적용했습니다.`);
}

function deleteAudioPreset(presetId) {
  const presets = loadAudioPresets();
  const target = presets.find((preset) => preset.id === presetId);
  const next = presets.filter((preset) => preset.id !== presetId);
  saveAudioPresets(next);
  renderAudioPresets();
  if (target) setMessage(`${target.name} 프리셋을 삭제했습니다.`);
}

function onAudioSettingChanged() {
  saveAudioSettings();
  updateAudioEstimate();
}

function plainRelated(text) {
  return parseRelated(text).join(', ');
}

function baseSpeechItemsForCard(card) {
  const parts = selectedSpeechParts();
  const items = [];
  if (parts.term) {
    const text = termSpeechText(card);
    const targetText = String(card?.term || '').trim();
    for (let repeat = 0; repeat < termRepeatCount(); repeat += 1) {
      items.push({key: 'term', text, targetText, prefixLength: 0, termRepeatIndex: repeat});
    }
  }
  if (parts.definition) {
    const prefix = '간단설명. ';
    const targetText = card.definition || '';
    items.push({key: 'definition', text: `${prefix}${targetText}`, targetText, prefixLength: prefix.length});
  }
  if (parts.detail) {
    detailedSections(card.detailed_explanation)
      .filter((section) => shouldSpeakDetailSection(section.label))
      .forEach((section) => {
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

function speechSegmentPauseMs(segment, item) {
  if (item.key === 'term') return 0;
  const text = String(segment || '').trim();
  if (!text) return 0;
  if (/[:：]$/.test(text)) return 260;
  if (/[.!?。！？]$/.test(text)) return isMobileSpeechDevice() ? 460 : 340;
  if (/[,;，；]$/.test(text)) return 240;
  return 300;
}

function splitLongSpeechSegment(segment, maxLength = 120) {
  const source = String(segment || '').trim();
  if (source.length <= maxLength) return source ? [source] : [];
  const clauses = source.split(/(?<=[,;:，；：])\s+/).filter(Boolean);
  if (clauses.length <= 1) return [source];
  const chunks = [];
  let current = '';
  clauses.forEach((clause) => {
    const next = current ? `${current} ${clause}` : clause;
    if (next.length > maxLength && current) {
      chunks.push(current);
      current = clause;
    } else {
      current = next;
    }
  });
  if (current) chunks.push(current);
  return chunks;
}

function splitSpeechText(text) {
  const source = String(text || '').replace(/\s+/g, ' ').trim();
  if (!source) return [];
  const sentenceMatches = source.match(/[^.!?。！？]+[.!?。！？]+|[^.!?。！？]+$/g) || [source];
  return sentenceMatches.flatMap((sentence) => splitLongSpeechSegment(sentence.trim())).filter(Boolean);
}

function expandSpeechItemForPauses(item) {
  if (item.key === 'term') return [item];
  const fullTargetText = String(item.targetText || item.text || '').trim();
  const segments = splitSpeechText(fullTargetText);
  if (segments.length <= 1) return [item];
  const prefix = String(item.text || '').slice(0, item.prefixLength || 0);
  const expanded = [];
  let targetOffset = 0;
  segments.forEach((segment, index) => {
    const offset = fullTargetText.indexOf(segment, targetOffset);
    const safeOffset = offset >= 0 ? offset : targetOffset;
    expanded.push({
      ...item,
      text: `${index === 0 ? prefix : ''}${segment}`,
      targetText: segment,
      fullTargetText,
      targetOffset: safeOffset,
      prefixLength: index === 0 ? prefix.length : 0,
      speechSegmentIndex: index,
    });
    targetOffset = safeOffset + segment.length;
    if (index < segments.length - 1) {
      expanded.push({isPause: true, pauseMs: speechSegmentPauseMs(segment, item), key: item.key, detailLabel: item.detailLabel});
    }
  });
  return expanded;
}

function speechItemsForCard(card) {
  const baseItems = baseSpeechItemsForCard(card);
  const items = [];
  for (let repeat = 0; repeat < cardRepeatCount(); repeat += 1) {
    baseItems.forEach((item) => {
      expandSpeechItemForPauses({...item, cardRepeatIndex: repeat}).forEach((expanded) => items.push(expanded));
    });
  }
  return items;
}

function hasPlayableSpeechItems() {
  return state.filtered.some((card) => speechItemsForCard(card).some((item) => !item.isPause));
}

function voiceIdentity(voice) {
  return [voice.voiceURI, voice.name, voice.lang].filter(Boolean).join('||');
}

function isKoreanVoice(voice) {
  return /ko|Korean|한국|한국어/i.test(`${voice.lang} ${voice.name}`);
}

function selectedSpeechVoiceId() {
  return $('speechVoice')?.value || 'auto';
}

function populateSpeechVoiceSelect() {
  const select = $('speechVoice');
  if (!select || !('speechSynthesis' in window)) return;
  const saved = (() => {
    try { return JSON.parse(localStorage.getItem(AUDIO_SETTINGS_KEY) || '{}').speechVoice; } catch (_error) { return null; }
  })();
  const previous = select.value && select.value !== 'auto' ? select.value : saved;
  const voices = window.speechSynthesis.getVoices?.() || [];
  const sorted = [...voices].sort((a, b) => {
    const ak = isKoreanVoice(a) ? 0 : 1;
    const bk = isKoreanVoice(b) ? 0 : 1;
    if (ak !== bk) return ak - bk;
    return `${a.lang} ${a.name}`.localeCompare(`${b.lang} ${b.name}`, 'ko');
  });
  select.innerHTML = '<option value="auto">자동 선택</option>';
  sorted.forEach((voice) => {
    const option = document.createElement('option');
    option.value = voiceIdentity(voice);
    const qualityHint = voice.localService ? '기기' : '브라우저';
    option.textContent = `${isKoreanVoice(voice) ? '🇰🇷 ' : ''}${voice.name} · ${voice.lang || '언어 미상'} · ${qualityHint}`;
    select.appendChild(option);
  });
  if (previous && [...select.options].some((option) => option.value === String(previous))) {
    select.value = String(previous);
  }
}

function preferredVoiceForItem(_item) {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  if (!voices.length) return null;
  const selected = selectedSpeechVoiceId();
  if (selected && selected !== 'auto') {
    const exact = voices.find((voice) => voiceIdentity(voice) === selected)
      || voices.find((voice) => voice.voiceURI === selected || voice.name === selected);
    if (exact) return exact;
  }
  const koreanVoices = voices.filter(isKoreanVoice);
  const pool = koreanVoices.length ? koreanVoices : voices;
  return pool.find((voice) => /female|여성|woman|heami|yuna|유나|siri|google|microsoft/i.test(voice.name))
    || pool[0];
}

function speechPitchForItem(item) {
  if (item.key === 'term') return 1;
  if (item.key === 'definition') return 0.98;
  return 0.96;
}

function speechRateForItem(item) {
  const baseRate = speechRate();
  return baseRate;
}

function estimateSpeechSecondsForOneListPass() {
  if (!state.filtered.length) return 0;
  let pauseSeconds = 0;
  const chars = state.filtered.reduce((total, card) => {
    return total + speechItemsForCard(card).reduce((sum, item) => {
      if (item.isPause) {
        pauseSeconds += (item.pauseMs || 0) / 1000;
        return sum;
      }
      return sum + String(item.text || '').replace(/\s+/g, '').length;
    }, 0);
  }, 0);
  const baseCharsPerSecond = 7.2;
  const speechSeconds = chars / (baseCharsPerSecond * speechRate()) + pauseSeconds;
  const transitionSeconds = Math.max(0, state.filtered.length - 1) * 0.62;
  const chimeSeconds = state.filtered.length * 0.26;
  return Math.ceil(speechSeconds + transitionSeconds + chimeSeconds);
}

function estimateSpeechSeconds() {
  const onePassSeconds = estimateSpeechSecondsForOneListPass();
  const repeatCount = listRepeatCount();
  if (repeatCount === Infinity) return Infinity;
  return onePassSeconds * repeatCount;
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
  const repeatCount = listRepeatCount();
  const onePassSeconds = estimateSpeechSecondsForOneListPass();
  if (repeatCount === Infinity) {
    el.textContent = `≈ ${formatDuration(onePassSeconds)} / 1바퀴 · ∞ 반복 · ${state.filtered.length}`;
    return;
  }
  const seconds = estimateSpeechSeconds();
  el.textContent = `≈ ${formatDuration(seconds)} · 전체 ${repeatCount}바퀴 · ${state.filtered.length}`;
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
  if (item.isPause) return item.pauseMs || 0;
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
  const source = String(current.fullTargetText || current.targetText || current.text || '');
  const absoluteCharIndex = (current.targetOffset || 0) + nextCharIndex;
  const nextWordStart = speechWordStartForCharIndex(source, absoluteCharIndex);
  const previousWordStart = current.wordStart;
  current.charIndex = absoluteCharIndex;
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
  if (item.isPause) {
    const pauseMs = Math.max(0, item.pauseMs || 0);
    setSpeechTimer(() => speakQueue(items, done), pauseMs);
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
    charIndex: item.targetOffset || 0,
    wordStart: speechWordStartForCharIndex(item.fullTargetText || item.targetText || item.text || '', item.targetOffset || 0),
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
  const repeatCount = listRepeatCount();
  const repeatLabel = repeatCount === Infinity ? '∞' : String(repeatCount);
  const repeatText = repeatCount === 1 ? '' : ` · ${state.audioListRepeatIndex + 1}/${repeatLabel}바퀴`;
  setMessage(`▶ ${state.index + 1}/${state.filtered.length}${repeatText} · ${card.term}`);
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
  if (!state.filtered.length) {
    window.setTimeout(() => stopAudioPlayback('자동 듣기가 끝났습니다.'), 260);
    return;
  }
  if (state.index >= state.filtered.length - 1) {
    const repeatCount = listRepeatCount();
    if (repeatCount === Infinity || state.audioListRepeatIndex + 1 < repeatCount) {
      state.audioListRepeatIndex += 1;
      state.index = 0;
      window.setTimeout(speakCurrentAndAdvance, nextSpeechDelayMs());
      return;
    }
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
  populateSpeechVoiceSelect();
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
  if (!hasPlayableSpeechItems()) {
    setMessage('재생할 상세 하위 항목 또는 다른 듣기 항목을 선택하세요.', true);
    return;
  }
  state.audioPlaying = true;
  state.audioListRepeatIndex = 0;
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
  state.audioListRepeatIndex = 0;
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
    bookmarked: rows.filter((card) => isCardBookmarked(card)).length,
    memo_count: rows.filter((card) => String(card.memo || '').trim()).length,
  };
}

function cardMatchesCurrentFilters(card, {includeStatus = true} = {}) {
  const query = $('searchInput').value.trim().toLowerCase();
  const category = $('categorySelect')?.value || '';
  const importance = $('importanceSelect')?.value || '';
  const difficulty = $('difficultySelect')?.value || '';
  const bok = $('bokSelect')?.value || '';
  const status = includeStatus ? state.statusFilter : '';
  const bookmarkOk = !state.bookmarkFilter || isCardBookmarked(card);
  const haystack = [card.id, card.term, card.english, card.category, card.bok_appeared === 'O' ? '한국은행 한은 BOK' : '', card.importance, card.difficulty, card.definition, card.detailed_explanation, card.related_concepts, card.exam_note, card.memo].join(' ').toLowerCase();
  const statusOk = !status || (status === 'unreviewed' ? !card.known_status : card.known_status === status);
  const bokOk = !bok || (bok === 'O' ? isBokAppeared(card) : !isBokAppeared(card));
  return (!query || haystack.includes(query))
    && (!category || card.category === category)
    && (!importance || card.importance === importance)
    && (!difficulty || card.difficulty === difficulty)
    && bokOk
    && statusOk
    && bookmarkOk;
}

function rowsForHeaderStats() {
  return state.cards.filter((card) => cardMatchesCurrentFilters(card, {includeStatus: false}));
}

function renderStats(summary) {
  $('statTotal').textContent = summary.total;
  $('statKnown').textContent = summary.known;
  $('statUnknown').textContent = summary.unknown;
  $('statUnreviewed').textContent = summary.unreviewed;
  updateStatFilterButtons();
  updateBookmarkFilterButton();
}

function isCardBookmarked(card) {
  const value = card?.bookmarked;
  if (value === true || value === 1) return true;
  return ['1', 'true', 'yes', 'y', 'on', 'o'].includes(String(value || '').trim().toLowerCase());
}

function bookmarkValue(bookmarked) {
  return bookmarked ? '1' : '0';
}

function bookmarkedCards() {
  return state.cards.filter((card) => isCardBookmarked(card));
}

function bookmarkFilteredCards() {
  return rowsForHeaderStats().filter((card) => isCardBookmarked(card));
}

function bookmarkedTermsPlainText() {
  return bookmarkedCards().map((card) => String(card.term || '').trim()).filter(Boolean).join(', ');
}

function memoCards() {
  return state.cards.filter((card) => String(card.memo || '').trim());
}

function updateCardInCollections(card) {
  const idx = state.cards.findIndex((item) => item.id === card.id);
  if (idx >= 0) state.cards[idx] = card;
  const filteredIdx = state.filtered.findIndex((item) => item.id === card.id);
  if (filteredIdx >= 0) state.filtered[filteredIdx] = card;
}

function setMarkButtonsDisabled(disabled) {
  ['knownBtn', 'unknownBtn', 'unreviewedBtn'].forEach((id) => {
    const button = $(id);
    if (button) button.disabled = disabled;
  });
}

function setBookmarkButtonsDisabled(disabled) {
  const bookmark = $('bookmarkBtn');
  if (bookmark) bookmark.disabled = disabled || !state.filtered.length;
  const copy = $('copyBookmarksBtn');
  if (copy) copy.disabled = disabled || !bookmarkedCards().length;
}

function setMemoControlsDisabled(disabled) {
  const input = $('memoInput');
  const save = $('memoSaveBtn');
  if (input) input.disabled = disabled || !state.filtered.length;
  if (save) save.disabled = disabled || !state.filtered.length;
}

function renderBookmarkControls(card) {
  const button = $('bookmarkBtn');
  if (button) {
    const active = Boolean(card && isCardBookmarked(card));
    button.textContent = active ? '★' : '☆';
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
    button.title = active ? '북마크 해제' : '북마크';
    button.dataset.tip = active ? '북마크 해제' : '북마크';
  }
  setBookmarkButtonsDisabled(state.bookmarkSaving);
}

function formatMemoUpdatedAt(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return `저장됨 ${date.toLocaleString('ko-KR', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'})}`;
}

function renderMemoControls(card) {
  const input = $('memoInput');
  const updated = $('memoUpdatedAt');
  if (input && document.activeElement !== input) input.value = card?.memo || '';
  if (updated) updated.textContent = card?.memo ? formatMemoUpdatedAt(card.memo_updated_at) : '';
  setMemoControlsDisabled(state.memoSaving);
}

function renderPersonalControls(card) {
  renderBookmarkControls(card);
  renderMemoControls(card);
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  try {
    if (!document.execCommand('copy')) throw new Error('copy command failed');
  } finally {
    textarea.remove();
  }
}

async function copyBookmarkedTerms() {
  const text = bookmarkedTermsPlainText();
  if (!text) {
    setMessage('복사할 북마크가 없습니다.', true);
    return;
  }
  try {
    await writeClipboardText(text);
    setMessage(`북마크 ${bookmarkedCards().length}개 개념명을 복사했습니다.`);
  } catch (error) {
    setMessage(`복사 실패: ${error.message || error}`, true);
  }
}

async function toggleBookmark() {
  if (!state.filtered.length || state.bookmarkSaving) return;
  const current = state.filtered[state.index];
  const previous = {...current};
  const nextBookmarked = !isCardBookmarked(current);
  const optimistic = {...current, bookmarked: bookmarkValue(nextBookmarked)};

  state.bookmarkSaving = true;
  updateCardInCollections(optimistic);
  renderPersonalControls(optimistic);
  renderStats(summaryFromRows(rowsForHeaderStats()));
  setMessage(`${optimistic.term}: 북마크 ${nextBookmarked ? '저장' : '해제'} 중...`);

  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(current.id)}/bookmark`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({bookmarked: nextBookmarked}),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    updateCardInCollections(data.card);
    state.summary = data.summary;
    if (state.bookmarkFilter) {
      applyFilters(data.card.id);
    } else {
      renderStats(summaryFromRows(rowsForHeaderStats()));
      renderPersonalControls(data.card);
    }
    if ($('bookmarkListDialog') && !$('bookmarkListDialog').hidden) renderBookmarkList();
    setMessage(`${data.card.term}: 북마크 ${isCardBookmarked(data.card) ? '저장 완료' : '해제 완료'}`);
  } catch (error) {
    updateCardInCollections(previous);
    renderStats(summaryFromRows(rowsForHeaderStats()));
    renderPersonalControls(previous);
    setMessage(`북마크 저장 실패: ${error.message || error}`, true);
  } finally {
    state.bookmarkSaving = false;
    renderPersonalControls(state.filtered[state.index] || null);
  }
}

async function saveMemo() {
  if (!state.filtered.length || state.memoSaving) return;
  const current = state.filtered[state.index];
  const input = $('memoInput');
  const memo = input ? input.value : '';
  const previous = {...current};
  const optimistic = {...current, memo, memo_updated_at: memo.trim() ? new Date().toISOString() : ''};

  state.memoSaving = true;
  updateCardInCollections(optimistic);
  renderMemoControls(optimistic);
  renderStats(summaryFromRows(rowsForHeaderStats()));
  setMessage(`${current.term}: 메모 저장 중...`);

  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(current.id)}/memo`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({memo}),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    updateCardInCollections(data.card);
    state.summary = data.summary;
    renderStats(summaryFromRows(rowsForHeaderStats()));
    renderMemoControls(data.card);
    if ($('memoListDialog') && !$('memoListDialog').hidden) renderMemoList();
    setMessage(`${data.card.term}: 메모 저장 완료`);
  } catch (error) {
    updateCardInCollections(previous);
    renderMemoControls(previous);
    renderStats(summaryFromRows(rowsForHeaderStats()));
    setMessage(`메모 저장 실패: ${error.message || error}`, true);
  } finally {
    state.memoSaving = false;
    renderMemoControls(state.filtered[state.index] || null);
  }
}

function toggleMenu(open = !state.menuOpen) {
  state.menuOpen = Boolean(open);
  const popover = $('menuPopover');
  const button = $('menuBtn');
  if (popover) popover.hidden = !state.menuOpen;
  if (button) button.setAttribute('aria-expanded', String(state.menuOpen));
  updateBookmarkFilterButton();
}

function updateBookmarkFilterButton() {
  const button = $('bookmarkFilterBtn');
  if (!button) return;
  const count = bookmarkFilteredCards().length;
  button.textContent = state.bookmarkFilter ? `북마크 필터 해제 (${count})` : `북마크만 보기 (${count})`;
  button.classList.toggle('active', state.bookmarkFilter);
}

function setBookmarkFilter(enabled) {
  state.bookmarkFilter = Boolean(enabled);
  state.index = 0;
  toggleMenu(false);
  applyFilters();
  setMessage(state.bookmarkFilter ? '북마크 카드만 표시합니다.' : '북마크 필터를 해제했습니다.');
}

function toggleBookmarkFilter() {
  setBookmarkFilter(!state.bookmarkFilter);
}

function renderMemoList() {
  const body = $('memoListBody');
  if (!body) return;
  const cards = memoCards();
  if (!cards.length) {
    body.innerHTML = '<p class="muted empty-list">저장된 메모가 없습니다.</p>';
    return;
  }
  body.innerHTML = cards.map((card) => `
    <button class="memo-list-item" type="button" data-card-id="${escapeHtml(card.id)}">
      <span class="memo-list-term">${escapeHtml(card.term || card.id)}</span>
      <span class="memo-list-meta">${escapeHtml(card.category || '')}${card.memo_updated_at ? ' · ' + escapeHtml(formatMemoUpdatedAt(card.memo_updated_at)) : ''}</span>
      <span class="memo-list-text">${escapeHtml(card.memo || '')}</span>
    </button>
  `).join('');
}

function openMemoList() {
  toggleMenu(false);
  renderMemoList();
  const dialog = $('memoListDialog');
  if (dialog) dialog.hidden = false;
}

function closeMemoList() {
  const dialog = $('memoListDialog');
  if (dialog) dialog.hidden = true;
}

function renderBookmarkList() {
  const body = $('bookmarkListBody');
  if (!body) return;
  const cards = bookmarkedCards();
  if (!cards.length) {
    body.innerHTML = '<p class="muted empty-list">저장된 북마크가 없습니다.</p>';
    return;
  }
  body.innerHTML = cards.map((card) => `
    <button class="memo-list-item bookmark-list-item" type="button" data-card-id="${escapeHtml(card.id)}">
      <span class="memo-list-term">★ ${escapeHtml(card.term || card.id)}</span>
      <span class="memo-list-meta">${escapeHtml(card.category || '')}${card.english ? ' · ' + escapeHtml(card.english) : ''}</span>
      <span class="memo-list-text">${escapeHtml(card.definition || '')}</span>
    </button>
  `).join('');
}

function openBookmarkList() {
  toggleMenu(false);
  renderBookmarkList();
  const dialog = $('bookmarkListDialog');
  if (dialog) dialog.hidden = false;
}

function closeBookmarkList() {
  const dialog = $('bookmarkListDialog');
  if (dialog) dialog.hidden = true;
}

function jumpToMemoCard(cardId) {
  const card = state.cards.find((item) => item.id === cardId);
  if (!card) return;
  closeMemoList();
  if (jumpToCard(card)) {
    state.flipped = true;
    state.backPage = 1;
    renderCard();
    setMessage(`${card.term} 메모로 이동했습니다.`);
  }
}

function jumpToBookmarkCard(cardId) {
  const card = state.cards.find((item) => item.id === cardId);
  if (!card) return;
  closeBookmarkList();
  if (jumpToCard(card)) {
    setMessage(`${card.term} 북마크로 이동했습니다.`);
  }
}


function selectedQuestionTypes() {
  const checked = [...document.querySelectorAll('.question-type-row input[type="checkbox"]:checked')].map((input) => input.value);
  return checked.length ? checked : ['short', 'subjective', 'multiple_choice', 'essay'];
}


function selectedQuestionTypeLabelsForPrompt() {
  const selected = new Set(selectedQuestionTypes());
  return AI_QUIZ_PROMPT_TYPE_ORDER
    .filter((type) => selected.has(type))
    .map((type) => QUESTION_TYPE_LABELS[type] || type);
}

function questionCountValue() {
  return Number.parseInt($('questionCountSelect')?.value || '10', 10) || 10;
}

function filteredQuestionTerms() {
  const seen = new Set();
  const terms = [];
  (state.filtered.length ? state.filtered : state.cards).forEach((card) => {
    const term = String(card?.term || card?.english || '').trim();
    const key = term.toLowerCase();
    if (!term || seen.has(key)) return;
    seen.add(key);
    terms.push(term);
  });
  return terms;
}

function aiQuizSearchPrompt() {
  const allTerms = filteredQuestionTerms();
  const visibleTerms = allTerms.slice(0, AI_QUIZ_TERM_LIMIT);
  const hasMore = allTerms.length > visibleTerms.length;
  const termText = visibleTerms.join(', ') + (hasMore ? ` 등 현재 선택된 카드 개념 ${allTerms.length}개` : '');
  const typeText = selectedQuestionTypeLabelsForPrompt().join('/') || '객관식/주관식/서술형/논술형';
  return `${termText} 로 ${typeText} 문제 ${questionCountValue()}개 만들어줘. 자체 퀴즈생성 기능을 활용해줘.`;
}

function aiQuizSearchUrl() {
  return googleAiSearchUrl(aiQuizSearchPrompt());
}

function openAiQuizSearch(event = null) {
  if (!state.filtered.length) {
    setMessage('AI 검색에 보낼 카드가 없습니다. 필터를 바꿔주세요.', true);
    return;
  }
  event?.preventDefault?.();
  event?.currentTarget?.blur?.();
  const url = aiQuizSearchUrl();
  const opened = window.open(url, 'cs-google-ai-quiz-search', 'popup,width=1120,height=820');
  restoreAppFocusAfterSearch(opened);
  window.setTimeout(() => {
    try { if (opened) opened.opener = null; } catch (_error) {}
  }, 800);
  const termCount = filteredQuestionTerms().length;
  setMessage(`선택한 ${termCount}개 개념 기준 AI 퀴즈 검색을 열었습니다.`);
}

function currentQuestion() {
  return state.questions[state.questionIndex] || null;
}

function questionTypeBadge(question) {
  if (!question) return '';
  return question.type_label || (QUESTION_TYPE_LABELS[question.type] || question.type || '문제');
}

function setQuestionControlsDisabled(disabled) {
  ['generateQuestionsBtn', 'openAiQuizSearchBtn', 'prevQuestionBtn', 'revealAnswerBtn', 'nextQuestionBtn', 'openQuestionCardBtn', 'questionCountSelect'].forEach((id) => {
    const element = $(id);
    if (element) element.disabled = disabled;
  });
  document.querySelectorAll('.question-type-row input').forEach((input) => { input.disabled = disabled; });
}

function renderQuestionPanel() {
  const panel = $('questionPanel');
  if (!panel) return;
  panel.hidden = !state.questionMode;
  document.body.classList.toggle('question-mode-active', state.questionMode);
  const summary = $('questionSummary');
  const card = $('questionCard');
  updateRandomButtons();
  if (!state.questionMode) return;
  setQuestionControlsDisabled(state.questionLoading);
  const total = state.questions.length;
  const question = currentQuestion();
  if (summary) {
    const filterCount = state.filtered.length;
    summary.textContent = state.questionLoading
      ? '문제 생성 중...'
      : total
        ? `${state.questionIndex + 1} / ${total} · 현재 필터 카드 ${filterCount}개 기준`
        : `현재 필터 카드 ${filterCount}개 기준 · 생성 버튼을 누르세요.`;
  }
  if (!card) return;
  if (state.questionLoading) {
    card.innerHTML = '<div class="question-card-empty muted">문제를 생성하는 중입니다...</div>';
    return;
  }
  if (!question) {
    card.innerHTML = '<div class="question-card-empty muted">문제 생성을 누르면 현재 필터의 카드들로 문제가 만들어집니다.</div>';
    return;
  }

  const choices = Array.isArray(question.choices) ? question.choices : [];
  const choiceHtml = choices.length ? `
    <ol class="question-choices">
      ${choices.map((choice, index) => {
        const isAnswer = state.answerRevealed && index === question.answer_index;
        const isSelected = index === state.selectedChoiceIndex;
        return `<li><button class="question-choice${isAnswer ? ' answer' : ''}${isSelected ? ' selected' : ''}" type="button" data-choice-index="${index}">${escapeHtml(choice)}</button></li>`;
      }).join('')}
    </ol>` : '';
  const rubric = Array.isArray(question.rubric) && question.rubric.length ? `
    <div class="question-rubric">
      <strong>채점 포인트</strong>
      <ul>${question.rubric.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
    </div>` : '';
  const answer = state.answerRevealed ? `
    <div class="question-answer">
      <strong>정답/모범답안</strong>
      <p>${escapeHtml(question.answer || '')}</p>
      ${question.explanation ? `<p class="question-explanation">${escapeHtml(question.explanation)}</p>` : ''}
      ${rubric}
    </div>` : '';
  card.innerHTML = `
    <div class="question-meta">
      <span class="badge">${escapeHtml(questionTypeBadge(question))}</span>
      <span class="badge">${escapeHtml(question.category || '미분류')}</span>
      <span class="badge">${escapeHtml(question.card_id || '')}</span>
    </div>
    <h2>${escapeHtml(question.prompt || '문제')}</h2>
    <p class="question-body">${escapeHtml(question.body || '')}</p>
    ${choiceHtml}
    ${answer}
  `;
  $('prevQuestionBtn').disabled = state.questionLoading || state.questionIndex <= 0;
  $('nextQuestionBtn').disabled = state.questionLoading || state.questionIndex >= total - 1;
  $('revealAnswerBtn').disabled = state.questionLoading || !question;
  $('openQuestionCardBtn').disabled = state.questionLoading || !question;
}

async function generateQuestionsFromCurrentFilter() {
  if (state.questionLoading) return;
  if (!state.filtered.length) {
    setMessage('문제를 만들 카드가 없습니다. 필터를 바꿔주세요.', true);
    return;
  }
  state.questionMode = true;
  state.questionLoading = true;
  state.answerRevealed = false;
  state.selectedChoiceIndex = null;
  renderQuestionPanel();
  try {
    const res = await fetch('/api/questions/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        card_ids: state.filtered.map((card) => card.id),
        types: selectedQuestionTypes(),
        count: questionCountValue(),
        seed: Date.now(),
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.questions = data.questions || [];
    state.questionIndex = 0;
    setMessage(`문제 ${state.questions.length}개 생성 완료`);
  } catch (error) {
    state.questions = [];
    setMessage(`문제 생성 실패: ${error.message || error}`, true);
  } finally {
    state.questionLoading = false;
    renderQuestionPanel();
  }
}

function toggleQuestionMode(force = !state.questionMode) {
  if (state.audioPlaying) stopAudioPlayback('문제 풀이 모드로 전환해 자동 듣기를 정지했습니다.');
  state.questionMode = Boolean(force);
  if (!state.questionMode) {
    renderQuestionPanel();
    setMessage('문제 풀이 모드를 닫았습니다.');
    return;
  }
  renderQuestionPanel();
  if (!state.questions.length) generateQuestionsFromCurrentFilter();
}

function revealQuestionAnswer() {
  if (!currentQuestion()) return;
  state.answerRevealed = true;
  renderQuestionPanel();
}

function moveQuestion(delta) {
  if (!state.questions.length) return;
  state.questionIndex = Math.max(0, Math.min(state.questions.length - 1, state.questionIndex + delta));
  state.answerRevealed = false;
  state.selectedChoiceIndex = null;
  renderQuestionPanel();
}

function openQuestionSourceCard() {
  const question = currentQuestion();
  if (!question) return;
  const card = state.cards.find((item) => item.id === question.card_id);
  if (!card) {
    setMessage('원본 카드를 찾지 못했습니다.', true);
    return;
  }
  toggleQuestionMode(false);
  jumpToCard(card);
  state.flipped = true;
  renderCard();
  setMessage(`${card.term} 원본 카드로 이동했습니다.`);
}

function selectQuestionChoice(index) {
  state.selectedChoiceIndex = index;
  const question = currentQuestion();
  if (question?.type === 'multiple_choice') state.answerRevealed = true;
  renderQuestionPanel();
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
  state.importanceFilter = $('importanceSelect')?.value || '';
  state.difficultyFilter = $('difficultySelect')?.value || '';
  state.bokFilter = $('bokSelect')?.value || '';
  state.filtered = state.cards.filter((card) => cardMatchesCurrentFilters(card));
  if (keepCurrentId) {
    const found = state.filtered.findIndex((c) => c.id === keepCurrentId);
    state.index = found >= 0 ? found : Math.min(state.index, Math.max(0, state.filtered.length - 1));
  } else {
    state.index = Math.min(state.index, Math.max(0, state.filtered.length - 1));
  }
  state.flipped = false;
  state.backPage = 0;
  renderCard();
  renderStats(summaryFromRows(rowsForHeaderStats()));
  if (state.questionMode) {
    state.questions = [];
    state.questionIndex = 0;
    state.answerRevealed = false;
    state.selectedChoiceIndex = null;
    renderQuestionPanel();
  }
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
    renderPersonalControls(null);
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
  renderPersonalControls(c);
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
  ['shuffleBtn', 'questionModeBtn'].forEach((id) => {
    const button = $(id);
    if (!button) return;
    const active = id === 'shuffleBtn' ? state.randomMode : state.questionMode;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
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
  if (e.target.closest('button, a, input, textarea, select, label')) return;
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
$('questionModeBtn')?.addEventListener('click', () => toggleQuestionMode());
$('generateQuestionsBtn')?.addEventListener('click', generateQuestionsFromCurrentFilter);
$('openAiQuizSearchBtn')?.addEventListener('click', openAiQuizSearch);
$('closeQuestionModeBtn')?.addEventListener('click', () => toggleQuestionMode(false));
$('prevQuestionBtn')?.addEventListener('click', () => moveQuestion(-1));
$('nextQuestionBtn')?.addEventListener('click', () => moveQuestion(1));
$('revealAnswerBtn')?.addEventListener('click', revealQuestionAnswer);
$('openQuestionCardBtn')?.addEventListener('click', openQuestionSourceCard);
$('questionCard')?.addEventListener('click', (event) => {
  const choice = event.target.closest('[data-choice-index]');
  if (choice) selectQuestionChoice(Number.parseInt(choice.dataset.choiceIndex, 10));
});
$('knownBtn').addEventListener('click', () => mark('O'));
$('unknownBtn').addEventListener('click', () => mark('X'));
$('unreviewedBtn').addEventListener('click', () => mark(''));
$('bookmarkBtn').addEventListener('click', toggleBookmark);
$('copyBookmarksBtn').addEventListener('click', copyBookmarkedTerms);
$('memoSaveBtn').addEventListener('click', saveMemo);
$('memoInput').addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault();
    event.stopPropagation();
    saveMemo();
  }
});
$('menuBtn').addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  toggleMenu();
});
$('memoListBtn').addEventListener('click', openMemoList);
$('bookmarkListBtn').addEventListener('click', openBookmarkList);
$('bookmarkFilterBtn').addEventListener('click', toggleBookmarkFilter);
$('memoListCloseBtn').addEventListener('click', closeMemoList);
$('bookmarkListCloseBtn').addEventListener('click', closeBookmarkList);
$('memoListDialog').addEventListener('click', (event) => {
  if (event.target === $('memoListDialog')) closeMemoList();
});
$('bookmarkListDialog').addEventListener('click', (event) => {
  if (event.target === $('bookmarkListDialog')) closeBookmarkList();
});
$('memoListBody').addEventListener('click', (event) => {
  const item = event.target.closest('[data-card-id]');
  if (item) jumpToMemoCard(item.dataset.cardId);
});
$('bookmarkListBody').addEventListener('click', (event) => {
  const item = event.target.closest('[data-card-id]');
  if (item) jumpToBookmarkCard(item.dataset.cardId);
});
document.addEventListener('click', (event) => {
  if (state.menuOpen && !event.target.closest('.header-actions')) toggleMenu(false);
});
$('audioPresetSaveBtn')?.addEventListener('click', saveCurrentAudioPreset);
$('audioPresetNameInput')?.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    saveCurrentAudioPreset();
  }
});
$('audioPresetList')?.addEventListener('click', (event) => {
  const applyButton = event.target.closest('[data-preset-id]');
  if (applyButton) {
    applyAudioPreset(applyButton.dataset.presetId);
    return;
  }
  const deleteButton = event.target.closest('[data-preset-delete]');
  if (deleteButton) deleteAudioPreset(deleteButton.dataset.presetDelete);
});
$('playAudioBtn').addEventListener('click', startAudioPlayback);
$('stopAudioBtn').addEventListener('click', () => stopAudioPlayback());
$('collapsedPlayBtn').addEventListener('click', startAudioPlayback);
$('collapsedStopBtn').addEventListener('click', () => stopAudioPlayback());
AUDIO_SETTING_IDS.forEach((id) => {
  $(id)?.addEventListener('change', onAudioSettingChanged);
});
if ('speechSynthesis' in window) {
  populateSpeechVoiceSelect();
  window.speechSynthesis.onvoiceschanged = populateSpeechVoiceSelect;
}
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
  if (document.activeElement?.id === 'memoInput' && (e.metaKey || e.ctrlKey) && e.key === 'Enter') {
    e.preventDefault();
    saveMemo();
    return;
  }
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
    if (e.key === 'Escape') {
      document.activeElement.blur();
      focusAppCard();
    }
    return;
  }

  const key = e.key.toLowerCase();
  if (state.questionMode) {
    if (e.key === 'ArrowLeft') { e.preventDefault(); moveQuestion(-1); return; }
    if (e.key === 'ArrowRight') { e.preventDefault(); moveQuestion(1); return; }
    if (e.key === ' ') { e.preventDefault(); revealQuestionAnswer(); return; }
    if (key === 'q') { e.preventDefault(); toggleQuestionMode(false); return; }
  }
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
  else if (key === 'b') { e.preventDefault(); toggleBookmark(); }
});

applyControlsCollapsed();
restoreAudioSettings();
populateSpeechVoiceSelect();
updateRandomButtons();

loadCards().catch((err) => {
  setMessage(`로딩 실패: ${err.message}`, true);
  applyFrontIllustration({term: '로딩 실패', english: '', category: ''});
  $('frontTerm').textContent = '로딩 실패';
  $('frontEnglish').textContent = err.message;
});
