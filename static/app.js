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
  aiRewriteLoading: false,
  aiRewriteApplying: false,
  aiRewriteCardId: '',
  aiRewriteDraft: null,
  aiRewriteStatus: '',
  aiRewriteError: '',
  aiRewriteActiveField: '',
  aiImageGenerating: false,
  aiImageSaving: false,
  aiImageCardId: '',
  aiImagePreviewName: '',
  aiImagePreviewUrl: '',
  aiImagePreviewAlt: '',
  aiNotificationsRequested: false,
  conceptImageScale: 1,

  menuOpen: false,
  flashcardTableWindow: null,
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
  filtersCollapsed: (() => {
    const saved = localStorage.getItem('filtersCollapsed');
    if (saved === '0') return false;
    if (saved === '1') return true;
    // No saved preference yet: default filters to hidden on mobile so the
    // card gets as much vertical space as possible; leave desktop as-is.
    return window.innerWidth <= 720;
  })(),
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
  questionSaving: false,
  questions: [],
  questionIndex: 0,
  questionSessionId: '',
  questionSessionTitle: '',
  questionSessionStartedAt: '',
  questionSessionStartMs: 0,
  questionSessionElapsedBaseSeconds: 0,
  questionTimeLimitSeconds: 0,
  questionSessionMode: 'practice',
  questionSessionFinishedAt: '',
  questionTimerId: 0,
  answerRevealed: false,
  selectedChoiceIndex: null,
  initialCardQueryApplied: false,
  questionHistoryOpen: false,
  questionHistoryLoading: false,
  questionHistoryFilter: 'all',
  questionHistoryItems: [],
  questionHistorySummary: null,
  questionHistoryError: '',
  questionBankOpen: false,
  questionBankLoading: false,
  questionBankItems: [],
  questionBankSummary: null,
  questionBankError: '',
  questionBankSelectedId: '',

};

const $ = (id) => document.getElementById(id);
const cardEl = $('card');
const VIEW_STATE_KEY = 'csFlashcardsViewState:v1';
const AUDIO_SETTINGS_KEY = 'csFlashcardsAudioSettings:v1';
const AUDIO_PRESETS_KEY = 'csFlashcardsAudioPresets:v1';
const PENDING_QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';
const FLASHCARD_TABLE_COLUMN_ORDER_KEY = 'csFlashcardsTableColumnOrder:v1';
const FLASHCARD_TABLE_DEFAULT_COLUMNS = ['bookmark', 'index', 'term', 'english', 'category', 'status'];
const FLASHCARD_TABLE_COLUMNS = {
  bookmark: {
    label: '★',
    width: 42,
    className: 'bookmark-cell',
    render: (card) => `<button class="table-action bookmark-action${isCardBookmarked(card) ? ' active' : ''}" type="button" data-bookmark-card-id="${escapeHtml(card.id)}" aria-label="북마크 토글" title="북마크 토글"${state.bookmarkSaving ? ' disabled' : ''}>${isCardBookmarked(card) ? '★' : '☆'}</button>`,
  },
  index: {
    label: '#',
    width: 56,
    render: (_card, index) => String(index + 1),
  },
  term: {
    label: '용어',
    className: 'term-cell',
    render: (card) => escapeHtml(card.term || card.id),
  },
  english: {
    label: '영문',
    render: (card) => escapeHtml(card.english || '—'),
  },
  category: {
    label: '분류',
    render: (card) => escapeHtml(categoryLabel(card.category)),
  },
  status: {
    label: '상태',
    width: 92,
    render: (card) => `<div class="status-actions">${['O', 'X', ''].map((value) => `<button class="table-action status-action${card.known_status === value ? ' active' : ''}" type="button" data-status-card-id="${escapeHtml(card.id)}" data-status-value="${escapeHtml(value)}" aria-label="상태 ${escapeHtml(statusLabel(value))}" title="${escapeHtml(statusLabel(value))}"${state.markSaving ? ' disabled' : ''}>${escapeHtml(statusLabel(value))}</button>`).join('')}</div>`,
  },
};
const AUDIO_SETTING_IDS = ['speakTerm', 'speakDefinition', 'speakDetail', 'speakRelated', 'speakExam', 'speakDetailMeaning', 'speakDetailUsage', 'termSpeechMode', 'termRepeatCount', 'cardRepeatCount', 'listRepeatCount', 'speechRate', 'speechVoice'];
const QUESTION_TYPE_LABELS = {short: '주관식', subjective: '서술형', multiple_choice: '객관식', essay: '논술형'};
const QUESTION_SESSION_MODE_LABELS = {practice: '일반', bok: '한국은행'};
const CONCEPT_IMAGE_SCALE_DEFAULT = 1;
const CONCEPT_IMAGE_SCALE_MIN = 0.8;
const CONCEPT_IMAGE_SCALE_MAX = 1.8;
const CONCEPT_IMAGE_SCALE_STEP = 0.1;
const BOK_MOCK_CONFIG = {
  subjectiveCount: 8,
  essayCount: 1,
  timeLimitMinutes: 150,
  subjectivePoints: 10,
  essayPoints: 20,
  subjectiveExpectedSeconds: 12 * 60,
  essayExpectedSeconds: 54 * 60,
  subjectiveAnswerGuide: '정의 → 원리 → 장단점/비교 → 예시 → 금융IT 적용 순으로 5~7문장',
  essayAnswerGuide: '정의 → 원리 → 비교 → 사례 → 금융IT 적용 → 결론 순으로 12~15문장',
};
const AI_QUIZ_PROMPT_TYPE_ORDER = ['multiple_choice', 'short', 'subjective', 'essay'];
const AI_QUIZ_TERM_LIMIT = 80;
const QUESTION_HISTORY_FILTER_LABELS = {all: '전체', correct: '맞음', ambiguous: '애매함', wrong: '틀림', unknown: '모름', pending: '미채점'};
const IMPORTED_QUESTION_TYPE_ALIASES = {
  short: 'short',
  short_answer: 'short',
  shortanswer: 'short',
  subjective: 'subjective',
  descriptive: 'subjective',
  essay: 'essay',
  multiple_choice: 'multiple_choice',
  multiplechoice: 'multiple_choice',
  mcq: 'multiple_choice',
  객관식: 'multiple_choice',
  주관식: 'short',
  단답형: 'short',
  서술형: 'subjective',
  논술형: 'essay',
};
// Silent looping WAV: keeps an <audio> element "audible" while auto-listen is
// active so mobile browsers treat the tab as playing media and don't freeze
// its JS timers (which drive the speech queue) when the screen locks or the
// app is backgrounded.
const SILENT_KEEP_ALIVE_AUDIO_SRC = 'data:audio/wav;base64,UklGRvQHAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YdAHAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==';

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

function wikiPageUrl(slug) {
  const normalized = String(slug || '').trim().replace(/^\/+|\/+$/g, '');
  if (!normalized) return '/wiki';
  return `/wiki/page/${encodeURIComponent(normalized).replace(/%2F/g, '/')}`;
}

function wikiSlugFromSourcePath(value) {
  const source = String(value || '').trim();
  if (!source || !/\.md$/i.test(source)) return '';
  return source.replace(/^\.\//, '').replace(/^pages\//, '').replace(/\.md$/i, '');
}

function renderSourceLinks(sourceFiles) {
  const parts = String(sourceFiles || '').split(';').map((part) => part.trim()).filter(Boolean);
  if (!parts.length) return '<span class="muted">없음</span>';
  return parts.map((part) => {
    const slug = wikiSlugFromSourcePath(part);
    if (!slug) return `<span class="source-text">${escapeHtml(part)}</span>`;
    const label = escapeHtml(part.replace(/^\.\//, '').replace(/^pages\//, '').replace(/\.md$/i, ''));
    return `<a class="source-link" href="${wikiPageUrl(slug)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  }).join('<span class="source-sep"> · </span>');
}

function primaryWikiSlugForCard(card) {
  const parts = String(card?.source_files || '').split(';').map((part) => part.trim()).filter(Boolean);
  for (const part of parts) {
    const slug = wikiSlugFromSourcePath(part);
    if (slug) return slug;
  }
  return '';
}

function currentCardWikiUrl(card) {
  const slug = primaryWikiSlugForCard(card);
  return slug ? wikiPageUrl(slug) : '/wiki';
}

function renderCardWikiLinks(card) {
  const wikiUrl = currentCardWikiUrl(card);
  const hasSpecificWiki = Boolean(primaryWikiSlugForCard(card));
  ['frontWikiLink', 'backWikiLink'].forEach((id) => {
    const link = $(id);
    if (!link) return;
    link.href = wikiUrl;
    link.title = hasSpecificWiki ? '연결된 위키 문서 열기' : '학습 위키 열기';
    link.setAttribute('aria-label', hasSpecificWiki ? '연결된 위키 문서 열기' : '학습 위키 열기');
  });
}

function applyInitialCardQuery() {
  const params = new URLSearchParams(window.location.search);
  const cardId = String(params.get('card') || '').trim();
  if (!cardId) return false;
  const card = state.cards.find((item) => item.id === cardId);
  if (!card) {
    setMessage(`URL 카드 ${cardId}를 찾지 못했습니다.`, true);
    return false;
  }
  jumpToCard(card);
  const side = String(params.get('side') || '').trim().toLowerCase();
  const page = Number.parseInt(params.get('page') || '', 10);
  state.flipped = side === 'back';
  state.backPage = page === 2 ? 1 : 0;
  renderCard();
  setMessage(`${card.term} 카드로 바로 이동했습니다.`);
  return true;
}
function consumePendingQuestionBankLaunch() {
  let raw = '';
  try {
    raw = window.sessionStorage.getItem(PENDING_QUESTION_BANK_LAUNCH_KEY) || '';
  } catch (_error) {
    return false;
  }
  if (!raw) return false;
  try {
    window.sessionStorage.removeItem(PENDING_QUESTION_BANK_LAUNCH_KEY);
  } catch (_error) {}
  try {
    const parsed = JSON.parse(raw);
    const items = Array.isArray(parsed?.items) ? parsed.items.filter((item) => item && typeof item === 'object') : [];
    if (!items.length) return false;
    const parsedStart = Number.parseInt(String(parsed?.startIndex ?? '0'), 10);
    const startIndex = Number.isInteger(parsedStart) ? parsedStart : 0;
    state.questionBankItems = items;
    state.questionBankSummary = {total: items.length, returned: items.length, limit: items.length};
    state.questionBankError = '';
    state.questionBankOpen = false;
    const selected = items[Math.max(0, Math.min(items.length - 1, startIndex))];
    state.questionBankSelectedId = String(selected?.question_bank_id || '');
    openQuestionBankSession(startIndex);
    return true;
  } catch (_error) {
    return false;
  }
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

function applyFiltersCollapsed() {
  const row = $('filterRow');
  const button = $('filterToggleBtn');
  if (!row || !button) return;
  row.hidden = state.filtersCollapsed;
  document.body.classList.toggle('filters-collapsed', state.filtersCollapsed);
  button.setAttribute('aria-expanded', String(!state.filtersCollapsed));
  button.textContent = state.filtersCollapsed ? '필터 ▾' : '필터 ▴';
}

function toggleFiltersPanel() {
  state.filtersCollapsed = !state.filtersCollapsed;
  localStorage.setItem('filtersCollapsed', state.filtersCollapsed ? '1' : '0');
  applyFiltersCollapsed();
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
      return sum + spellOutUppercaseAcronyms(item.text).replace(/\s+/g, '').length;
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
  const compactLength = Math.max(1, spellOutUppercaseAcronyms(item.text).replace(/\s+/g, '').length);
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

function spellOutUppercaseAcronyms(text) {
  // "TCP" as a whole word gets mangled or skipped by most Korean TTS
  // voices; reading each letter separately ("T. C. P.") is intelligible.
  return String(text || '').replace(/\b[A-Z]{2,}\b/g, (word) => `${word.split('').join('. ')}.`);
}

function speechStartFailureMessage() {
  const isAppleMobile = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (isAppleMobile) return '모바일에서 음성이 시작되지 않았습니다. 화면의 ▶ 버튼을 다시 눌러 음성을 허용해 주세요.';
  return '음성이 시작되지 않아 자동 듣기를 멈췄습니다. 다시 재생해 주세요.';
}

function createUtterance(item, token, markStarted, finish, fail) {
  const utterance = new SpeechSynthesisUtterance(spellOutUppercaseAcronyms(item.text));
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
  updateMediaSessionForCurrentCard();
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

function restartCurrentCardSpeech() {
  if (!state.audioPlaying) return;
  // Invalidate whatever watchdog/timer chain was scheduled before the
  // suspension so its late callbacks can't interleave with the fresh one.
  state.speechToken += 1;
  clearSpeechTimers();
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  speakCurrentAndAdvance();
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

let backgroundKeepAliveAudio = null;

function ensureBackgroundKeepAliveAudio() {
  if (backgroundKeepAliveAudio) return backgroundKeepAliveAudio;
  const audio = new Audio(SILENT_KEEP_ALIVE_AUDIO_SRC);
  audio.loop = true;
  // A tiny nonzero volume (not muted, not zero) keeps mobile browsers from
  // treating the tab as inaudible, which is what lets them exempt it from
  // background-tab JS throttling/suspension once the screen locks.
  audio.volume = 0.01;
  audio.setAttribute('playsinline', 'true');
  backgroundKeepAliveAudio = audio;
  return audio;
}

function startBackgroundPlaybackKeepAlive() {
  ensureBackgroundKeepAliveAudio().play().catch(() => {});
  updateMediaSessionForCurrentCard();
  if ('mediaSession' in navigator) {
    navigator.mediaSession.playbackState = 'playing';
    navigator.mediaSession.setActionHandler('play', () => {
      if (!state.audioPlaying) startAudioPlayback();
    });
    navigator.mediaSession.setActionHandler('pause', () => stopAudioPlayback());
    navigator.mediaSession.setActionHandler('stop', () => stopAudioPlayback());
  }
}

function stopBackgroundPlaybackKeepAlive() {
  if (backgroundKeepAliveAudio) backgroundKeepAliveAudio.pause();
  if ('mediaSession' in navigator) {
    navigator.mediaSession.playbackState = 'paused';
    navigator.mediaSession.setActionHandler('play', null);
    navigator.mediaSession.setActionHandler('pause', null);
    navigator.mediaSession.setActionHandler('stop', null);
  }
}

function updateMediaSessionForCurrentCard() {
  if (!('mediaSession' in navigator) || typeof MediaMetadata === 'undefined') return;
  const card = state.filtered[state.index];
  navigator.mediaSession.metadata = new MediaMetadata({
    title: card?.term || 'CS 플래시카드',
    artist: `${state.index + 1} / ${state.filtered.length}`,
    album: 'CS 개념 플래시카드 자동 듣기',
  });
}

function scrollCardIntoViewOnMobile() {
  if (window.innerWidth > 720) return;
  const card = $('card');
  if (!card) return;
  window.requestAnimationFrame(() => {
    card.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
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
  startBackgroundPlaybackKeepAlive();
  scrollCardIntoViewOnMobile();
  setAudioButtons();
  speakCurrentAndAdvance();
}

function stopAudioPlayback(message = '자동 듣기를 정지했습니다.') {
  state.audioPlaying = false;
  state.speechToken += 1;
  clearSpeechTimers();
  stopSpeechKeepAlive();
  stopBackgroundPlaybackKeepAlive();
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

function buildMarkedCardState(card, status) {
  const previous = {...(card || {})};
  const optimistic = {...previous, known_status: status};
  if (status) {
    optimistic.last_reviewed = new Date().toISOString();
    optimistic.review_count = String((Number.parseInt(previous.review_count || '0', 10) || 0) + 1);
  } else {
    optimistic.last_reviewed = '';
  }
  return optimistic;
}


function setMessage(text, isError = false) {
  const el = $('message');
  el.textContent = text;
  el.style.color = isError ? '#fb7185' : '#aab6cf';
}

function requestAiNotificationPermission() {
  if (state.aiNotificationsRequested || !('Notification' in window) || window.Notification.permission !== 'default') return;
  state.aiNotificationsRequested = true;
  window.Notification.requestPermission().catch(() => {});
}

function notifyAiCompletion(title, body) {
  if (document.visibilityState !== 'hidden' || !('Notification' in window) || window.Notification.permission !== 'granted') return;
  try {
    new window.Notification(title, {body, tag: 'cs-ai-update'});
  } catch (_error) {}
}

function announceAiCompletion(title, body, isError = false) {
  setMessage(body, isError);
  notifyAiCompletion(title, body);
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

function clampConceptImageScale(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return CONCEPT_IMAGE_SCALE_DEFAULT;
  return Math.min(CONCEPT_IMAGE_SCALE_MAX, Math.max(CONCEPT_IMAGE_SCALE_MIN, Math.round(numeric * 100) / 100));
}

function conceptImageScalePercent() {
  return Math.round(clampConceptImageScale(state.conceptImageScale) * 100);
}

function applyConceptImageScale(image = $('backConceptImage')) {
  if (!image) return;
  image.style.setProperty('--concept-image-scale', String(clampConceptImageScale(state.conceptImageScale)));
}

function updateConceptImageZoomControls({hasImage = false} = {}) {
  const zoomOutBtn = $('conceptImageZoomOutBtn');
  const zoomInBtn = $('conceptImageZoomInBtn');
  const zoomBtn = $('conceptImageZoomBtn');
  if (!zoomOutBtn || !zoomInBtn || !zoomBtn) return;
  const scalePercent = conceptImageScalePercent();
  const canZoomOut = hasImage && state.conceptImageScale > CONCEPT_IMAGE_SCALE_MIN;
  const canZoomIn = hasImage && state.conceptImageScale < CONCEPT_IMAGE_SCALE_MAX;
  const zoomOutLabel = hasImage ? `이미지 축소 · ${scalePercent}%` : '축소할 이미지 없음';
  const zoomInLabel = hasImage ? `이미지 확대 · ${scalePercent}%` : '확대할 이미지 없음';
  const zoomDialogLabel = hasImage ? `이미지 크게 보기 · 현재 ${scalePercent}%` : '확대할 이미지 없음';
  zoomOutBtn.disabled = !canZoomOut;
  zoomOutBtn.title = zoomOutLabel;
  zoomOutBtn.dataset.tip = hasImage ? `축소 · ${scalePercent}%` : '이미지 없음';
  zoomOutBtn.setAttribute('aria-label', zoomOutLabel);
  zoomInBtn.disabled = !canZoomIn;
  zoomInBtn.title = zoomInLabel;
  zoomInBtn.dataset.tip = hasImage ? `확대 · ${scalePercent}%` : '이미지 없음';
  zoomInBtn.setAttribute('aria-label', zoomInLabel);
  zoomBtn.disabled = !hasImage;
  zoomBtn.title = zoomDialogLabel;
  zoomBtn.dataset.tip = hasImage ? `크게 보기 · ${scalePercent}%` : '이미지 없음';
  zoomBtn.setAttribute('aria-label', zoomDialogLabel);
}

function stepConceptImageScale(delta) {
  const current = state.filtered[state.index] || null;
  if (!current) return;
  const next = clampConceptImageScale((state.conceptImageScale || CONCEPT_IMAGE_SCALE_DEFAULT) + delta);
  if (Math.abs(next - state.conceptImageScale) < 0.001) {
    renderConceptImage(current);
    return;
  }
  state.conceptImageScale = next;
  renderConceptImage(current);
  setMessage(`${current.term}: 이미지 크기 ${conceptImageScalePercent()}%`);
}
function conceptImageUrl(card) {
  const url = String(card?.concept_image_url || card?.image_url || '').trim();
  if (!url) return '';
  if (url.startsWith('/static/generated/') || url.startsWith('/api/concept-images/')) return '';
  return url;
}

function conceptImagePreviewActive(card) {
  return Boolean(card?.id) && state.aiImageCardId === card.id && state.aiImagePreviewUrl && state.aiImagePreviewName;
}

function clearConceptImagePreview(cardId = null) {
  if (cardId && state.aiImageCardId && state.aiImageCardId !== cardId) return;
  state.aiImageCardId = '';
  state.aiImagePreviewName = '';
  state.aiImagePreviewUrl = '';
  state.aiImagePreviewAlt = '';
}

function bindConceptImageLoadState() {
  const image = $('backConceptImage');
  const placeholder = $('backConceptImagePlaceholder');
  if (!image || !placeholder || image.dataset.loadBound === '1') return;
  image.dataset.loadBound = '1';
  image.addEventListener('load', () => {
    if (!image.dataset.expectedSrc) return;
    image.hidden = false;
    placeholder.hidden = true;
  });
  image.addEventListener('error', () => {
    image.hidden = true;
    placeholder.hidden = false;
  });
}


function conceptImageAlt(card) {
  const explicit = String(card?.concept_image_alt || card?.image_alt || '').trim();
  if (explicit) return explicit;
  const term = card?.term || card?.english || '개념';
  const category = card?.category ? `(${card.category})` : '';
  return `${term}${category} 이해를 돕는 학습용 개념 이미지`;
}

function conceptImageDisplayState(card) {
  const previewActive = conceptImagePreviewActive(card);
  const previewUrl = previewActive ? String(state.aiImagePreviewUrl || '').trim() : '';
  const persistedUrl = conceptImageUrl(card);
  const url = previewUrl || persistedUrl;
  return {
    previewActive,
    url,
    alt: previewActive ? (state.aiImagePreviewAlt || conceptImageAlt(card)) : conceptImageAlt(card),
    hasImage: Boolean(url),
  };
}

async function previewConceptImage() {
  if (!state.filtered.length || state.aiImageGenerating || state.aiImageSaving) return;
  const current = state.filtered[state.index];
  requestAiNotificationPermission();
  state.aiImageCardId = current.id;
  state.aiImageGenerating = true;
  renderConceptImage(current);
  setMessage(`${current.term}: AI 이미지 변경 요청됨. 완료 시 알림합니다.`);
  let previewName = '';
  try {
    const previewRes = await fetch(`/api/cards/${encodeURIComponent(current.id)}/ai-image/preview`, {method: 'POST'});
    if (!previewRes.ok) throw new Error(await responseErrorText(previewRes));
    const previewData = await previewRes.json();
    previewName = String(previewData.preview_name || '');
    const applyRes = await fetch(`/api/cards/${encodeURIComponent(current.id)}/ai-image/apply`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({preview_name: previewName}),
    });
    if (!applyRes.ok) throw new Error(await responseErrorText(applyRes));
    const data = await applyRes.json();
    clearConceptImagePreview(current.id);
    await refreshCards({message: null});
    announceAiCompletion(`AI 이미지 완료 · ${data.card.term}`, `${data.card.term}: AI 이미지 변경 완료`);
  } catch (error) {
    if (previewName) {
      try {
        await fetch(`/api/cards/${encodeURIComponent(current.id)}/ai-image/discard`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({preview_name: previewName}),
        });
      } catch (_discardError) {}
    }
    renderConceptImage(current);
    announceAiCompletion(`AI 이미지 실패 · ${current.term}`, `${current.term}: AI 이미지 생성 실패 - ${error.message || error}`, true);
  } finally {
    state.aiImageGenerating = false;
    state.aiImageSaving = false;
    clearConceptImagePreview(current.id);
    renderConceptImage(state.filtered[state.index] || null);
  }
}



async function discardConceptImagePreview() {
  const current = state.filtered[state.index] || null;
  if (!current || !conceptImagePreviewActive(current) || state.aiImageGenerating || state.aiImageSaving) return;
  const previewName = state.aiImagePreviewName;
  state.aiImageSaving = true;
  renderConceptImage(current);
  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(current.id)}/ai-image/discard`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({preview_name: previewName}),
    });
    if (!res.ok) throw new Error(await responseErrorText(res));
  } catch (error) {
    state.aiImageSaving = false;
    renderConceptImage(current);
    setMessage(`AI 이미지 취소 실패: ${error.message || error}`, true);
    return;
  }
  state.aiImageSaving = false;
  clearConceptImagePreview(current.id);
  renderConceptImage(current);
  setMessage(`${current.term}: AI 이미지 미리보기를 취소했습니다.`);
}

function conceptImageDialogOpen() {
  const dialog = $('conceptImageDialog');
  return Boolean(dialog && !dialog.hidden);
}

function openConceptImageDialog() {
  const image = $('backConceptImage');
  const dialog = $('conceptImageDialog');
  const dialogImage = $('conceptImageDialogImage');
  if (!image || !dialog || !dialogImage || image.hidden) return;
  const src = image.currentSrc || image.getAttribute('src') || '';
  if (!src) return;
  dialogImage.src = src;
  dialogImage.alt = image.alt || '';
  dialog.hidden = false;
  $('conceptImageDialogCloseBtn')?.focus();
}

function closeConceptImageDialog({restoreFocus = true} = {}) {
  const dialog = $('conceptImageDialog');
  const dialogImage = $('conceptImageDialogImage');
  if (!dialog || dialog.hidden) return;
  dialog.hidden = true;
  if (dialogImage) {
    dialogImage.removeAttribute('src');
    dialogImage.alt = '';
  }
  if (restoreFocus) focusAppCard();
}

function renderConceptImage(card) {
  const wrap = $('backConceptImageWrap');
  const image = $('backConceptImage');
  const placeholder = $('backConceptImagePlaceholder');
  const zoomOutBtn = $('conceptImageZoomOutBtn');
  const zoomInBtn = $('conceptImageZoomInBtn');
  const zoomBtn = $('conceptImageZoomBtn');
  const generateBtn = $('conceptImageGenerateBtn');
  if (!wrap || !image || !placeholder || !zoomOutBtn || !zoomInBtn || !zoomBtn || !generateBtn) return;
  bindConceptImageLoadState();
  state.conceptImageScale = clampConceptImageScale(state.conceptImageScale);
  applyConceptImageScale(image);

  if (!card) {
    wrap.hidden = true;
    image.removeAttribute('src');
    image.removeAttribute('title');
    image.alt = '';
    image.dataset.expectedSrc = '';
    image.hidden = true;
    placeholder.hidden = true;
    updateConceptImageZoomControls();
    generateBtn.disabled = true;
    closeConceptImageDialog({restoreFocus: false});
    return;
  }

  const {previewActive, url, alt, hasImage} = conceptImageDisplayState(card);
  const busy = state.aiImageGenerating || state.aiImageSaving;
  const activeBusy = busy && state.aiImageCardId === card.id;
  wrap.hidden = false;
  wrap.classList.toggle('preview-active', previewActive);
  wrap.classList.toggle('is-empty', !hasImage);

  if (hasImage) {
    image.dataset.expectedSrc = url;
    image.alt = alt;
    image.title = previewActive ? `${card.term} AI 이미지 미리보기 크게 보기` : `${card.term} 이미지 크게 보기`;
    image.hidden = false;
    placeholder.hidden = true;
    if (image.getAttribute('src') !== url) image.src = url;
    if (image.complete) {
      const loaded = image.naturalWidth > 0;
      image.hidden = !loaded;
      placeholder.hidden = loaded;
    }
    if (conceptImageDialogOpen()) {
      const dialogImage = $('conceptImageDialogImage');
      if (dialogImage) {
        if (dialogImage.getAttribute('src') !== url) dialogImage.src = url;
        dialogImage.alt = alt;
      }
    }
  } else {
    image.removeAttribute('src');
    image.removeAttribute('title');
    image.alt = '';
    image.dataset.expectedSrc = '';
    image.hidden = true;
    placeholder.hidden = false;
    closeConceptImageDialog({restoreFocus: false});
  }

  updateConceptImageZoomControls({hasImage});
  generateBtn.disabled = busy;
  generateBtn.textContent = activeBusy ? '…' : 'AI';
  generateBtn.title = activeBusy ? 'AI 이미지 생성 중' : 'AI 이미지 재생성';
  generateBtn.dataset.tip = activeBusy ? '생성 중' : 'AI 이미지 재생성';
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
  if (!state.initialCardQueryApplied) {
    state.initialCardQueryApplied = true;
    applyInitialCardQuery();
  }
  $('csvPath').textContent = data.summary.csv_path;
  setAudioButtons();
  updateAudioEstimate();
  consumePendingQuestionBankLaunch();
}

async function refreshCards(options = {}) {
  const {cardId = state.filtered[state.index]?.id, message = '↻'} = options || {};
  if (state.audioPlaying) stopAudioPlayback('정지');
  await loadCards();
  if (cardId) {
    const found = state.filtered.findIndex((card) => card.id === cardId);
    if (found >= 0) state.index = found;
  }
  renderCard();
  if (message) setMessage(message);
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

function aiRewriteDraftFromCard(card) {
  return {
    definition: String(card?.definition || ''),
    detailed_explanation: String(card?.detailed_explanation || ''),
    exam_note: String(card?.exam_note || ''),
    concept_image_alt: String(card?.concept_image_alt || ''),
  };
}

const AI_REWRITE_FIELD_CONFIG = {
  definition: {
    label: '간단 설명',
    previewButtonId: 'definitionAiBtn',
    instruction: '현재 카드의 간단 설명만 1~2문장으로 더 명확하고 면접 답변 친화적으로 다듬어 주세요. 다른 필드는 유지해 주세요.',
  },
  detailed_explanation: {
    label: '상세 설명',
    previewButtonId: 'detailAiBtn',
    instruction: '현재 카드의 상세 설명만 더 이해하기 쉽게 다듬어 주세요. 의미: 와 활용: 구조는 유지하고 다른 필드는 유지해 주세요.',
  },
  exam_note: {
    label: '시험 포인트',
    previewButtonId: 'examAiBtn',
    instruction: '현재 카드의 시험 포인트만 더 짧고 비교 포인트가 잘 보이게 다듬어 주세요. 다른 필드는 유지해 주세요.',
  },
};


function currentAiRewriteDraft(card) {
  if (!card) return null;
  const changedCard = state.aiRewriteCardId !== card.id || !state.aiRewriteDraft;
  if (changedCard) {
    state.aiRewriteCardId = card.id;
    state.aiRewriteDraft = aiRewriteDraftFromCard(card);
    state.aiRewriteStatus = '';
    state.aiRewriteError = '';
    state.aiRewriteActiveField = '';
  }
  return state.aiRewriteDraft;
}

function clearAiRewritePreview(cardId = null) {
  if (cardId && state.aiRewriteCardId && state.aiRewriteCardId !== cardId) return;
  state.aiRewriteDraft = null;
  state.aiRewriteActiveField = '';
  state.aiRewriteStatus = '';
  state.aiRewriteError = '';
}

function aiRewritePreviewActive(card, field) {
  return Boolean(card?.id) && state.aiRewriteCardId === card.id && state.aiRewriteActiveField === field && state.aiRewriteDraft;
}

function aiRewriteDisplayText(card, field) {
  if (aiRewritePreviewActive(card, field)) {
    return String(state.aiRewriteDraft?.[field] || card?.[field] || '');
  }
  return String(card?.[field] || '');
}

function renderAiRewriteControls(card) {
  const busy = state.aiRewriteLoading || state.aiRewriteApplying;
  Object.entries(AI_REWRITE_FIELD_CONFIG).forEach(([field, config]) => {
    const previewBtn = $(config.previewButtonId);
    const row = previewBtn?.closest('.section-title-row') || null;
    if (!previewBtn) return;
    const active = busy && state.aiRewriteActiveField === field && state.aiRewriteCardId === card?.id;
    previewBtn.disabled = busy || !card;
    previewBtn.textContent = active ? '…' : 'AI';
    previewBtn.title = active ? `${config.label} AI 변환 중` : `${config.label} AI 변환`;
    previewBtn.dataset.tip = active ? '변환 중' : `${config.label} AI`;
    row?.classList.toggle('ai-previewing', active);
  });
}



async function responseErrorText(res) {
  const raw = await res.text();
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim();
  } catch (_error) {
    // Fall back to the raw text body.
  }
  return raw || `${res.status}`;
}

async function previewAiRewrite(field) {
  const config = AI_REWRITE_FIELD_CONFIG[field];
  if (!config || !state.filtered.length || state.aiRewriteLoading || state.aiRewriteApplying) return;
  const current = state.filtered[state.index];
  requestAiNotificationPermission();
  state.aiRewriteCardId = current.id;
  state.aiRewriteLoading = true;
  state.aiRewriteError = '';
  state.aiRewriteActiveField = field;
  renderAiRewriteControls(current);
  setMessage(`${current.term}: ${config.label} AI 변경 요청됨. 완료 시 알림합니다.`);
  try {
    const previewRes = await fetch(`/api/cards/${encodeURIComponent(current.id)}/ai-rewrite/preview`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({instruction: config.instruction}),
    });
    if (!previewRes.ok) throw new Error(await responseErrorText(previewRes));
    const previewData = await previewRes.json();
    const nextValue = String(previewData?.proposal?.[field] ?? current?.[field] ?? '');
    const applyRes = await fetch(`/api/cards/${encodeURIComponent(current.id)}/ai-rewrite/apply`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({[field]: nextValue}),
    });
    if (!applyRes.ok) throw new Error(await responseErrorText(applyRes));
    const data = await applyRes.json();
    clearAiRewritePreview(current.id);
    await refreshCards({message: null});
    announceAiCompletion(`AI 변경 완료 · ${data.card.term}`, `${data.card.term}: ${config.label} 변경 완료`);
  } catch (error) {
    renderAiRewriteControls(current);
    announceAiCompletion(`AI 변경 실패 · ${current.term}`, `${current.term}: ${config.label} 변경 실패 - ${error.message || error}`, true);
  } finally {
    state.aiRewriteLoading = false;
    state.aiRewriteApplying = false;
    state.aiRewriteActiveField = '';
    renderAiRewriteControls(state.filtered[state.index] || null);
  }
}


async function applyAiRewrite(field) {
  const config = AI_REWRITE_FIELD_CONFIG[field];
  if (!config || !state.filtered.length || state.aiRewriteLoading || state.aiRewriteApplying) return;
  const current = state.filtered[state.index];
  const draft = currentAiRewriteDraft(current);
  if (!draft || !aiRewritePreviewActive(current, field)) return;
  state.aiRewriteApplying = true;
  renderAiRewriteControls(current);
  setMessage(`${current.term}: ${config.label} 저장 중...`);
  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(current.id)}/ai-rewrite/apply`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({[field]: draft[field]}),
    });
    if (!res.ok) throw new Error(await responseErrorText(res));
    const data = await res.json();
    clearAiRewritePreview(current.id);
    await refreshCards({cardId: data.card.id, message: null});
    setMessage(`${data.card.term}: ${config.label} 저장 완료`);
  } catch (error) {
    renderAiRewriteControls(current);
    setMessage(`AI 초안 적용 실패: ${error.message || error}`, true);
  } finally {
    state.aiRewriteApplying = false;
    renderAiRewriteControls(state.filtered[state.index] || null);
  }
}

function discardAiRewrite(field) {
  const current = state.filtered[state.index] || null;
  if (!current || !aiRewritePreviewActive(current, field) || state.aiRewriteLoading || state.aiRewriteApplying) return;
  clearAiRewritePreview(current.id);
  renderCard();
  setMessage(`${current.term}: AI 초안을 취소했습니다.`);
}

function renderPersonalControls(card) {
  renderBookmarkControls(card);
  renderMemoControls(card);
  renderAiRewriteControls(card);
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

function flashcardTableSummaryText() {
  const parts = [];
  const searchValue = String($('searchInput')?.value || '').trim();
  const categoryValue = $('categorySelect')?.value || '';
  if (searchValue) parts.push(`검색 ${searchValue}`);
  if (categoryValue) parts.push(categoryLabel(categoryValue));
  if (state.importanceFilter) parts.push(`중요도 ${state.importanceFilter}`);
  if (state.difficultyFilter) parts.push(`난도 ${state.difficultyFilter}`);
  if (state.bokFilter) parts.push(`기출 ${state.bokFilter}`);
  if (state.statusFilter) parts.push(`상태 ${statusLabel(state.statusFilter)}`);
  if (state.bookmarkFilter) parts.push('북마크만');
  return parts.join(' · ') || '전체 카드';
}

function selectCardFromFlashcardTable(cardId) {
  if (state.questionMode) toggleQuestionMode(false);
  const card = state.cards.find((item) => item.id === cardId);
  if (!card) {
    setMessage('표 목록에서 선택한 카드를 찾지 못했습니다.', true);
    return false;
  }
  const filteredIndex = state.filtered.findIndex((item) => item.id === cardId);
  if (filteredIndex >= 0) {
    state.index = filteredIndex;
    state.flipped = false;
    state.backPage = 0;
    renderCard();
    setMessage(`${card.term} 카드로 이동했습니다.`);
    return true;
  }
  return jumpToCard(card);
}

window.__csFlashcardsSelectCardFromTable = selectCardFromFlashcardTable;

function flashcardTablePopupRequested() {
  try {
    return new URLSearchParams(window.location.search).get('popup') === 'flashcard-table';
  } catch (_error) {
    return false;
  }
}

function registerFlashcardTableWindow(popupWindow = null) {
  if (!popupWindow || popupWindow.closed) return false;
  state.flashcardTableWindow = popupWindow;
  renderFlashcardTableWindow();
  return true;
}

function flashcardTableColumnOrder() {
  const fallback = [...FLASHCARD_TABLE_DEFAULT_COLUMNS];
  try {
    const saved = JSON.parse(localStorage.getItem(FLASHCARD_TABLE_COLUMN_ORDER_KEY) || '[]');
    if (!Array.isArray(saved)) return fallback;
    const filtered = saved.filter((key, index) => FLASHCARD_TABLE_DEFAULT_COLUMNS.includes(key) && saved.indexOf(key) === index);
    return [...filtered, ...fallback.filter((key) => !filtered.includes(key))];
  } catch (_error) {
    return fallback;
  }
}

function saveFlashcardTableColumnOrder(order) {
  try {
    localStorage.setItem(FLASHCARD_TABLE_COLUMN_ORDER_KEY, JSON.stringify(order));
  } catch (_error) {}
}

function moveFlashcardTableColumn(sourceKey, targetKey) {
  if (!FLASHCARD_TABLE_DEFAULT_COLUMNS.includes(sourceKey) || !FLASHCARD_TABLE_DEFAULT_COLUMNS.includes(targetKey) || sourceKey === targetKey) return false;
  const order = flashcardTableColumnOrder();
  const fromIndex = order.indexOf(sourceKey);
  const toIndex = order.indexOf(targetKey);
  if (fromIndex < 0 || toIndex < 0) return false;
  order.splice(toIndex, 0, ...order.splice(fromIndex, 1));
  saveFlashcardTableColumnOrder(order);
  renderFlashcardTableWindow();
  return true;
}

function refreshAfterFlashcardTableMutation(card) {
  syncUpdatedCard(card);
  if (state.statusFilter || state.bookmarkFilter) {
    applyFilters(card.id);
    return;
  }
  renderStats(summaryFromRows(rowsForHeaderStats()));
  renderFlashcardTableWindow();
}

async function toggleFlashcardBookmarkFromTable(cardId) {
  if (!cardId || state.bookmarkSaving) return false;
  const current = state.cards.find((item) => item.id === cardId);
  if (!current) {
    setMessage('표 목록에서 선택한 카드를 찾지 못했습니다.', true);
    return false;
  }
  const previous = {...current};
  const nextBookmarked = !isCardBookmarked(current);
  const optimistic = {...current, bookmarked: bookmarkValue(nextBookmarked)};

  state.bookmarkSaving = true;
  setBookmarkButtonsDisabled(true);
  updateCardInCollections(optimistic);
  refreshAfterFlashcardTableMutation(optimistic);
  if ($('bookmarkListDialog') && !$('bookmarkListDialog').hidden) renderBookmarkList();
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
    refreshAfterFlashcardTableMutation(data.card);
    if ($('bookmarkListDialog') && !$('bookmarkListDialog').hidden) renderBookmarkList();
    setMessage(`${data.card.term}: 북마크 ${isCardBookmarked(data.card) ? '저장 완료' : '해제 완료'}`);
    return true;
  } catch (error) {
    updateCardInCollections(previous);
    refreshAfterFlashcardTableMutation(previous);
    if ($('bookmarkListDialog') && !$('bookmarkListDialog').hidden) renderBookmarkList();
    setMessage(`북마크 저장 실패: ${error.message || error}`, true);
    return false;
  } finally {
    state.bookmarkSaving = false;
    renderPersonalControls(state.filtered[state.index] || null);
    renderFlashcardTableWindow();
  }
}

async function setFlashcardStatusFromTable(cardId, status) {
  if (!cardId || state.markSaving || !['O', 'X', ''].includes(status)) return false;
  const current = state.cards.find((item) => item.id === cardId);
  if (!current) {
    setMessage('표 목록에서 선택한 카드를 찾지 못했습니다.', true);
    return false;
  }
  const previous = {...current};
  const optimistic = buildMarkedCardState(previous, status);

  state.markSaving = true;
  setMarkButtonsDisabled(true);
  updateCardInCollections(optimistic);
  refreshAfterFlashcardTableMutation(optimistic);
  setMessage(`${optimistic.term}: ${statusLabel(status)} 저장 중...`);

  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(current.id)}/mark`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({known_status: status}),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    updateCardInCollections(data.card);
    state.summary = data.summary;
    refreshAfterFlashcardTableMutation(data.card);
    setMessage(`${data.card.term}: ${statusLabel(status)} 저장 완료`);
    return true;
  } catch (error) {
    updateCardInCollections(previous);
    refreshAfterFlashcardTableMutation(previous);
    setMessage(`저장 실패: ${error.message || error}`, true);
    return false;
  } finally {
    state.markSaving = false;
    setMarkButtonsDisabled(false);
    renderFlashcardTableWindow();
  }
}

window.__csFlashcardsRegisterTableWindow = registerFlashcardTableWindow;
window.__csFlashcardsMoveTableColumn = moveFlashcardTableColumn;
window.__csFlashcardsToggleBookmarkFromTable = toggleFlashcardBookmarkFromTable;
window.__csFlashcardsSetStatusFromTable = setFlashcardStatusFromTable;
window.__csFlashcardsTableClosed = () => {
  state.flashcardTableWindow = null;
};

function syncFlashcardTableWindowSelection() {
  const popup = state.flashcardTableWindow;
  if (!popup || popup.closed) {
    state.flashcardTableWindow = null;
    return false;
  }
  const doc = popup.document;
  const rows = [...doc.querySelectorAll('[data-row-card-id]')];
  const summary = doc.querySelector('.summary');
  if (summary) summary.textContent = `${flashcardTableSummaryText()} · ${state.filtered.length}개 · 현재 ${state.filtered.length ? state.index + 1 : 0}`;
  if (!rows.length) return false;
  const currentCardId = state.filtered[state.index]?.id || '';
  rows.forEach((row) => row.classList.toggle('current-row', row.dataset.rowCardId === currentCardId));
  return true;
}
function renderFlashcardTableWindow() {
  const popup = state.flashcardTableWindow;
  if (!popup || popup.closed) {
    state.flashcardTableWindow = null;
    return;
  }
  const rows = state.filtered;
  const currentCardId = rows[state.index]?.id || '';
  const summaryText = flashcardTableSummaryText();
  const columnOrder = flashcardTableColumnOrder();
  // Shared table shell owns draggable="true", data-column-key, dragstart, and drop-target header behavior.
  const columns = columnOrder.map((key) => {
    const column = FLASHCARD_TABLE_COLUMNS[key];
    return {
      key,
      label: column.label,
      width: column.width ? `${column.width}px` : '',
      headerClassName: column.className || '',
      cellClassName: column.className || '',
    };
  });
  const popupConfig = {
    columns,
    rows: rows.map((card, index) => ({
      id: card.id,
      className: card.id === currentCardId ? 'current-row' : '',
      attributes: {'data-row-card-id': card.id},
      cells: Object.fromEntries(columnOrder.map((key) => [key, FLASHCARD_TABLE_COLUMNS[key].render(card, index)])),
    })),
  };
  const popupConfigJson = JSON.stringify(popupConfig).replace(/</g, '\\u003c');
  try {
    popup.document.open();
    popup.document.write(`<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>플래시카드 표 목록</title>
  <link rel="stylesheet" href="/static/table-shell.css" />
</head>
<body class="cs-table-page">
  <main class="cs-table-shell">
    <div class="cs-table-meta">
      <div>
        <h1 class="cs-table-title">플래시카드 표 목록</h1>
        <p class="summary cs-table-summary">${escapeHtml(summaryText)} · ${rows.length}개 · 현재 ${rows.length ? state.index + 1 : 0}</p>
        <p class="hint cs-table-hint">열 제목 드래그로 순서 변경 · 행 클릭 이동 · 별/O/X/– 바로 수정</p>
      </div>
    </div>
    <div id="flashcardTableMount"></div>
  </main>
  <script src="/static/table-shell.js"></script>
  <script>
    const invokeOpener = (callbackName, ...args) => {
      const openerRef = window.opener;
      if (!openerRef || openerRef.closed || typeof openerRef[callbackName] !== 'function') return false;
      window.setTimeout(() => {
        try {
          openerRef[callbackName](...args);
          window.focus();
        } catch (_error) {}
      }, 0);
      return true;
    };
    const config = ${popupConfigJson};
    const mount = document.getElementById('flashcardTableMount');
    window.CSTableShell.renderTable(mount, {
      columns: config.columns,
      rows: config.rows,
      emptyText: '현재 조건에 맞는 카드가 없습니다.',
      tableMinWidth: '720px',
      onAction: (event) => {
        const bookmarkButton = event.target.closest('[data-bookmark-card-id]');
        if (bookmarkButton) {
          event.preventDefault();
          invokeOpener('__csFlashcardsToggleBookmarkFromTable', bookmarkButton.dataset.bookmarkCardId || '');
          return true;
        }
        const statusButton = event.target.closest('[data-status-card-id]');
        if (statusButton) {
          event.preventDefault();
          invokeOpener('__csFlashcardsSetStatusFromTable', statusButton.dataset.statusCardId || '', statusButton.dataset.statusValue || '');
          return true;
        }
        return false;
      },
      onRowActivate: (row) => {
        invokeOpener('__csFlashcardsSelectCardFromTable', row?.attributes?.['data-row-card-id'] || row?.id || '');
      },
      onColumnMove: (sourceKey, targetKey) => {
        invokeOpener('__csFlashcardsMoveTableColumn', sourceKey, targetKey);
      },
    });
    window.addEventListener('beforeunload', () => {
      invokeOpener('__csFlashcardsTableClosed');
    });
  </script>
</body>
</html>`);
    popup.document.close();
  } catch (_error) {
    state.flashcardTableWindow = null;
    setMessage('표 목록 창을 새로 열어주세요.', true);
  }
}

function bootstrapFlashcardTablePopupWindow() {
  if (!flashcardTablePopupRequested()) return false;
  const openerRef = window.opener;
  if (!openerRef || openerRef.closed || typeof openerRef.__csFlashcardsRegisterTableWindow !== 'function') {
    document.body.innerHTML = '<div style="padding:16px;font:12px -apple-system,BlinkMacSystemFont,Segoe UI,Noto Sans KR,sans-serif;color:#444;">원본 창을 먼저 연 뒤 다시 시도하세요.</div>';
    return true;
  }
  openerRef.__csFlashcardsRegisterTableWindow(window);
  return true;
}
function openFlashcardTableWindow() {
  toggleMenu(false);
  if (state.flashcardTableWindow && !state.flashcardTableWindow.closed) {
    renderFlashcardTableWindow();
    state.flashcardTableWindow.focus();
    return;
  }
  const popupUrl = new window.URL(window.location.href);
  popupUrl.searchParams.set('popup', 'flashcard-table');
  const popup = window.open(popupUrl.toString(), 'csFlashcardTableWindow', 'popup=yes,width=1120,height=760,resizable=yes,scrollbars=yes');
  if (!popup) {
    setMessage('팝업이 차단되어 표 목록을 열지 못했습니다.', true);
    return;
  }
  state.flashcardTableWindow = popup;
  renderFlashcardTableWindow();
  popup.focus();
}

function formatQuestionAttemptUpdatedAt(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('ko-KR', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
}

function questionHistoryCardIds() {
  if (state.cards.length && !state.filtered.length) return [];
  const pool = state.filtered.length ? state.filtered : state.cards;
  return [...new Set(pool.map((card) => String(card?.id || '').trim()).filter(Boolean))];
}

function questionHistoryRequestUrl() {
  const params = new URLSearchParams({
    result: state.questionHistoryFilter || 'all',
    limit: '200',
  });
  questionHistoryCardIds().forEach((cardId) => params.append('card_id', cardId));
  return `/api/questions/attempts?${params.toString()}`;
}

function renderQuestionHistoryDialog() {
  const summaryEl = $('questionHistorySummary');
  const body = $('questionHistoryBody');
  document.querySelectorAll('[data-question-history-filter]').forEach((button) => {
    button.classList.toggle('active', button.dataset.questionHistoryFilter === state.questionHistoryFilter);
  });
  if (summaryEl) {
    if (state.questionHistoryLoading) {
      summaryEl.textContent = '현재 필터 기준 문제 기록을 불러오는 중입니다.';
    } else if (state.questionHistoryError) {
      summaryEl.textContent = `문제 기록 로딩 실패: ${state.questionHistoryError}`;
    } else {
      const summary = state.questionHistorySummary || {selected_card_count: questionHistoryCardIds().length, total: 0, correct: 0, ambiguous: 0, wrong: 0, unknown: 0, pending: 0};
      summaryEl.textContent = `카드 ${summary.selected_card_count || 0} · 전체 ${summary.total || 0} · 맞음 ${summary.correct || 0} · 애매 ${summary.ambiguous || 0} · 틀림 ${summary.wrong || 0} · 모름 ${summary.unknown || 0} · 미채점 ${summary.pending || 0}`;
    }
  }
  if (!body) return;
  if (state.questionHistoryLoading) {
    body.innerHTML = '<p class="muted empty-list">문제 기록을 불러오는 중입니다...</p>';
    return;
  }
  if (state.questionHistoryError) {
    body.innerHTML = `<p class="error-text empty-list">문제 기록을 불러오지 못했습니다. ${escapeHtml(state.questionHistoryError)}</p>`;
    return;
  }
  const items = Array.isArray(state.questionHistoryItems) ? state.questionHistoryItems : [];
  if (!items.length) {
    body.innerHTML = '<p class="muted empty-list">선택한 조건에 해당하는 문제 기록이 없습니다.</p>';
    return;
  }
  body.innerHTML = items.map((item) => {
    const title = escapeHtml(item.term || item.card_id || '카드');
    const typeLabel = escapeHtml(QUESTION_TYPE_LABELS[item.question_type] || item.question_type || '문제');
    const category = escapeHtml(item.category || '미분류');
    const resultLabel = escapeHtml(QUESTION_HISTORY_FILTER_LABELS[item.result_key] || item.result_label || '기록');
    const updatedAt = formatQuestionAttemptUpdatedAt(item.updated_at);
    const prompt = String(item.prompt || '').trim();
    const bodyText = String(item.body || '').trim();
    const answerText = escapeHtml(item.user_answer || '미입력');
    const wrongNote = String(item.wrong_note || '').trim();
    const sessionMeta = [
      String(item.session_title || '').trim(),
      questionSessionModeLabel(item.session_mode || 'practice'),
      String(item.section || '').trim(),
      Number.isInteger(item.points) ? `${item.points}점` : '',
      item.question_order ? `문항 ${item.question_order}` : '',
      Number.isInteger(item.expected_time_seconds) ? `권장 ${formatElapsedClock(item.expected_time_seconds)}` : '',
      Number.isInteger(item.question_elapsed_seconds) ? `문항 ${formatElapsedClock(item.question_elapsed_seconds)}` : '',
      updatedAt ? `저장 ${escapeHtml(updatedAt)}` : '',
    ].filter(Boolean).join(' · ');
    return `
      <article class="question-history-item">
        <div class="question-history-item-head">
          <div class="question-history-item-heading">
            <strong>${title}</strong>
            <p class="question-history-item-meta">${category} · ${typeLabel}</p>
            ${sessionMeta ? `<p class="question-history-session-meta">${sessionMeta}</p>` : ''}
          </div>
          <span class="question-history-result ${escapeHtml(item.result_key || 'pending')}">${resultLabel}</span>
        </div>
        <div class="question-history-copy">
          ${prompt ? `<p class="question-history-item-prompt">${escapeHtml(prompt)}</p>` : ''}
          ${bodyText ? `<p class="question-history-item-body">${escapeHtml(bodyText)}</p>` : ''}
        </div>
        <div class="question-history-fields">
          <p class="question-history-field"><span>내 답</span><strong>${answerText}</strong></p>
          ${wrongNote ? `<p class="question-history-field note"><span>오답</span><strong>${escapeHtml(wrongNote)}</strong></p>` : ''}
        </div>
        <div class="question-history-item-actions">
          <button class="question-history-open-card" type="button" data-question-history-card-id="${escapeHtml(item.card_id || '')}">카드</button>
        </div>
      </article>`;
  }).join('');
}

async function loadQuestionHistory() {
  if (state.questionHistoryLoading) return;
  state.questionHistoryLoading = true;
  state.questionHistoryError = '';
  renderQuestionHistoryDialog();
  const cardIds = questionHistoryCardIds();
  if (state.cards.length && !cardIds.length) {
    state.questionHistoryItems = [];
    state.questionHistorySummary = {selected_card_count: 0, total: 0, correct: 0, ambiguous: 0, wrong: 0, unknown: 0, pending: 0, returned: 0, filter: state.questionHistoryFilter || 'all'};
    state.questionHistoryLoading = false;
    renderQuestionHistoryDialog();
    return;
  }
  try {
    const res = await fetch(questionHistoryRequestUrl());
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.questionHistoryItems = Array.isArray(data.items) ? data.items : [];
    state.questionHistorySummary = data.summary || null;
  } catch (error) {
    state.questionHistoryItems = [];
    state.questionHistorySummary = null;
    state.questionHistoryError = error.message || String(error);
  } finally {
    state.questionHistoryLoading = false;
    renderQuestionHistoryDialog();
  }
}

function openQuestionHistory() {
  toggleMenu(false);
  state.questionHistoryOpen = true;
  const dialog = $('questionHistoryDialog');
  if (dialog) dialog.hidden = false;
  renderQuestionHistoryDialog();
  loadQuestionHistory();
}

function closeQuestionHistory() {
  state.questionHistoryOpen = false;
  const dialog = $('questionHistoryDialog');
  if (dialog) dialog.hidden = true;
}

function setQuestionHistoryFilter(filter) {
  const normalized = String(filter || '').trim().toLowerCase();
  if (!QUESTION_HISTORY_FILTER_LABELS[normalized]) return;
  state.questionHistoryFilter = normalized;
  renderQuestionHistoryDialog();
  if (state.questionHistoryOpen) loadQuestionHistory();
}

function jumpToQuestionHistoryCard(cardId) {
  const card = state.cards.find((item) => item.id === cardId);
  if (!card) {
    setMessage('원본 카드를 찾지 못했습니다.', true);
    return;
  }
  closeQuestionHistory();
  toggleQuestionMode(false);
  if (jumpToCard(card)) {
    state.flipped = true;
    renderCard();
    setMessage(`${card.term} 카드로 이동했습니다.`);
  }
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


function normalizeQuestionSessionMode(value) {
  return String(value || '').trim().toLowerCase() === 'bok' ? 'bok' : 'practice';
}

function questionSessionModeValue() {
  return normalizeQuestionSessionMode($('questionSessionModeSelect')?.value || state.questionSessionMode || 'practice');
}

function syncQuestionSessionModeSelect(mode) {
  const select = $('questionSessionModeSelect');
  const normalized = normalizeQuestionSessionMode(mode);
  if (select && [...select.options].some((option) => option.value === normalized)) select.value = normalized;
}

function questionSessionModeLabel(mode = state.questionSessionMode) {
  return QUESTION_SESSION_MODE_LABELS[normalizeQuestionSessionMode(mode)] || QUESTION_SESSION_MODE_LABELS.practice;
}

function questionSessionIsBok(mode = state.questionSessionMode) {
  return normalizeQuestionSessionMode(mode) === 'bok';
}

function applyQuestionSessionModePreset(mode = questionSessionModeValue()) {
  if (!questionSessionIsBok(mode)) return;
  if ($('questionCountSelect')) $('questionCountSelect').value = String(BOK_MOCK_CONFIG.subjectiveCount + BOK_MOCK_CONFIG.essayCount);
  if ($('questionTimeLimitSelect')) $('questionTimeLimitSelect').value = String(BOK_MOCK_CONFIG.timeLimitMinutes);
  if ($('questionTypeShort')) $('questionTypeShort').checked = false;
  if ($('questionTypeSubjective')) $('questionTypeSubjective').checked = true;
  if ($('questionTypeMultipleChoice')) $('questionTypeMultipleChoice').checked = false;
  if ($('questionTypeEssay')) $('questionTypeEssay').checked = true;
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
function syncQuestionTimeLimitSelect(seconds) {
  const select = $('questionTimeLimitSelect');
  if (!select || !Number.isFinite(seconds) || seconds < 0 || seconds % 60 !== 0) return;
  const minutes = String(Math.floor(seconds / 60));
  if ([...select.options].some((option) => option.value === minutes)) select.value = minutes;
}

function questionRevealLocked(question = currentQuestion()) {
  const current = hydrateQuestionState(question);
  return Boolean(current) && questionSessionIsBok(current.sessionMode || state.questionSessionMode) && !state.questionSessionFinishedAt;
}

function questionImportDialog() {
  return $('questionImportDialog');
}

function setQuestionImportError(message = '') {
  const errorEl = $('questionImportError');
  if (errorEl) errorEl.textContent = String(message || '').trim();
}

function openQuestionImportDialog() {
  toggleMenu(false);
  setQuestionImportError('');
  const dialog = questionImportDialog();
  if (dialog) dialog.hidden = false;
  window.setTimeout(() => $('questionImportInput')?.focus(), 0);
}

function closeQuestionImportDialog() {
  setQuestionImportError('');
  const dialog = questionImportDialog();
  if (dialog) dialog.hidden = true;
}

function extractImportJsonText(rawText) {
  const text = String(rawText || '').trim();
  if (!text) throw new Error('붙여넣은 문제 세트가 비어 있습니다.');
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]?.trim()) return fenced[1].trim();
  if (text.startsWith('{') || text.startsWith('[')) return text;
  const objectIndex = text.indexOf('{');
  const arrayIndex = text.indexOf('[');
  const startIndex = objectIndex === -1 ? arrayIndex : arrayIndex === -1 ? objectIndex : Math.min(objectIndex, arrayIndex);
  if (startIndex < 0) return text;
  const startChar = text[startIndex];
  const endChar = startChar === '[' ? ']' : '}';
  const endIndex = text.lastIndexOf(endChar);
  return endIndex > startIndex ? text.slice(startIndex, endIndex + 1).trim() : text.slice(startIndex).trim();
}

function normalizeImportedStringArray(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || '').trim()).filter(Boolean);
  }
  const text = String(value || '').trim();
  if (!text) return [];
  return text
    .split(/\n|;/)
    .map((item) => item.replace(/^[-*\d.)\s]+/, '').trim())
    .filter(Boolean);
}

function importedQuestionType(value) {
  const raw = String(value || '').trim();
  const normalizedKey = normalizeTerm(raw).replace(/\s+/g, '_');
  const normalized = IMPORTED_QUESTION_TYPE_ALIASES[normalizedKey];
  if (!normalized || !QUESTION_TYPE_LABELS[normalized]) {
    throw new Error(`지원하지 않는 문제 유형입니다: ${raw || '(비어 있음)'}`);
  }
  return normalized;
}

function importedQuestionSetPayload(rawText) {
  const parsed = JSON.parse(extractImportJsonText(rawText));
  if (Array.isArray(parsed)) {
    return {title: '', timeLimitSeconds: null, sessionMode: 'practice', questions: parsed};
  }
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.questions)) {
    throw new Error('최상위 JSON은 문제 배열 또는 questions 배열을 가진 객체여야 합니다.');
  }
  const minutes = Number.parseInt(parsed.time_limit_minutes ?? parsed.duration_minutes ?? parsed.timeLimitMinutes ?? '', 10);
  const seconds = Number.parseInt(parsed.time_limit_seconds ?? parsed.duration_seconds ?? parsed.timeLimitSeconds ?? '', 10);
  return {
    title: String(parsed.title || parsed.name || '').trim(),
    timeLimitSeconds: Number.isFinite(seconds) && seconds >= 0 ? seconds : Number.isFinite(minutes) && minutes >= 0 ? minutes * 60 : null,
    sessionMode: normalizeQuestionSessionMode(parsed.session_mode ?? parsed.exam_mode ?? parsed.mode ?? 'practice'),
    questions: parsed.questions,
  };
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
  if (questionSessionIsBok(questionSessionModeValue())) {
    return `${termText} 로 한국은행 컴퓨터공학 직렬 스타일 전공필기 ${BOK_MOCK_CONFIG.subjectiveCount}문항과 전공논술 ${BOK_MOCK_CONFIG.essayCount}문항을 ${BOK_MOCK_CONFIG.timeLimitMinutes}분 모의고사 형식으로 만들어줘. 정답은 별도 구분해줘. 자체 퀴즈생성 기능을 활용해줘.`;
  }
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

function currentQuestionCard() {
  const question = currentQuestion();
  if (!question?.card_id) return null;
  return state.cards.find((item) => item.id === question.card_id)
    || state.filtered.find((item) => item.id === question.card_id)
    || null;
}
function resolveImportedCard(rawQuestion, index) {
  const explicitId = String(rawQuestion.card_id ?? rawQuestion.cardId ?? rawQuestion.id ?? '').trim();
  if (explicitId) {
    const byId = state.cards.find((card) => String(card?.id || '').trim() === explicitId);
    if (byId) return byId;
    throw new Error(`${index + 1}번 문항의 card_id를 찾지 못했습니다: ${explicitId}`);
  }
  const candidates = [rawQuestion.concept_term, rawQuestion.term, rawQuestion.concept, rawQuestion.keyword, rawQuestion.title]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
  for (const candidate of candidates) {
    const normalized = normalizeTerm(candidate);
    const found = state.cards.find((card) => {
      const cardId = normalizeTerm(card?.id || '');
      const term = normalizeTerm(card?.term || '');
      const english = normalizeTerm(card?.english || '');
      return normalized && (normalized === cardId || normalized === term || normalized === english);
    });
    if (found) return found;
  }
  throw new Error(`${index + 1}번 문항의 개념을 현재 카드에서 찾지 못했습니다.`);
}

function importedAnswerIndex(rawQuestion, choices, answerText, index) {
  const explicit = Number.parseInt(rawQuestion.answer_index ?? rawQuestion.answerIndex ?? rawQuestion.correct_index ?? rawQuestion.correctIndex ?? '', 10);
  if (Number.isInteger(explicit) && explicit >= 0 && explicit < choices.length) return explicit;
  const normalizedAnswer = normalizeTerm(answerText);
  const foundIndex = choices.findIndex((choice) => normalizeTerm(choice) === normalizedAnswer);
  if (foundIndex >= 0) return foundIndex;
  throw new Error(`${index + 1}번 객관식 문항의 정답이 보기 목록에 없습니다.`);
}

function buildImportedQuestions(rawQuestions) {
  if (!Array.isArray(rawQuestions) || !rawQuestions.length) {
    throw new Error('가져올 문제 배열이 비어 있습니다.');
  }
  return rawQuestions.map((rawQuestion, index) => {
    if (!rawQuestion || typeof rawQuestion !== 'object') {
      throw new Error(`${index + 1}번 문항 형식이 올바르지 않습니다.`);
    }
    const card = resolveImportedCard(rawQuestion, index);
    const importedTypeSource = rawQuestion.question_type ?? rawQuestion.type ?? rawQuestion.format ?? rawQuestion.kind ?? (rawQuestion.choices || rawQuestion.options ? 'multiple_choice' : 'subjective');
    const type = importedQuestionType(importedTypeSource);
    const prompt = String(rawQuestion.prompt ?? rawQuestion.question ?? '').trim();
    const body = String(rawQuestion.body ?? rawQuestion.context ?? rawQuestion.description ?? '').trim();
    const answer = String(rawQuestion.answer ?? rawQuestion.model_answer ?? rawQuestion.sample_answer ?? '').trim();
    const explanation = String(rawQuestion.explanation ?? rawQuestion.commentary ?? rawQuestion.finance_it_application ?? '').trim();
    const rubric = normalizeImportedStringArray(rawQuestion.rubric ?? rawQuestion.scoring_points ?? rawQuestion.grading_points ?? rawQuestion.trap_points);
    const choices = type === 'multiple_choice' ? normalizeImportedStringArray(rawQuestion.choices ?? rawQuestion.options) : [];
    const topic = String(rawQuestion.topic ?? rawQuestion.question_topic ?? rawQuestion.problem_type ?? rawQuestion.subject ?? rawQuestion.category ?? card.category ?? '').trim();
    const fieldName = String(rawQuestion.field_name ?? rawQuestion.field ?? rawQuestion.domain ?? rawQuestion.area ?? '').trim();
    const keywords = normalizeImportedStringArray(rawQuestion.keywords ?? rawQuestion.keyword ?? rawQuestion.tags ?? rawQuestion.tag_list);
    const difficulty = String(rawQuestion.difficulty ?? rawQuestion.level ?? '').trim();
    const issuer = String(rawQuestion.issuer ?? rawQuestion.organization ?? rawQuestion.exam_org ?? rawQuestion.bank ?? '').trim();
    const sourceLocation = String(rawQuestion.source_location ?? rawQuestion.source ?? rawQuestion.exam_source ?? rawQuestion.reference ?? '').trim();
    const section = String(rawQuestion.section ?? rawQuestion.exam_section ?? rawQuestion.part ?? '').trim();
    const pointsValue = Number.parseInt(rawQuestion.points ?? rawQuestion.score ?? rawQuestion.weight ?? '', 10);
    const expectedMinutes = Number.parseInt(rawQuestion.expected_time_minutes ?? rawQuestion.estimated_minutes ?? rawQuestion.recommended_minutes ?? '', 10);
    const expectedSecondsValue = Number.parseInt(rawQuestion.expected_time_seconds ?? rawQuestion.estimated_seconds ?? rawQuestion.recommended_seconds ?? '', 10);
    const answerGuide = String(rawQuestion.answer_guide ?? rawQuestion.response_guide ?? rawQuestion.length_guide ?? '').trim();
    const sessionMode = normalizeQuestionSessionMode(rawQuestion.session_mode ?? rawQuestion.exam_mode ?? rawQuestion.mode ?? 'practice');
    if (!prompt) throw new Error(`${index + 1}번 문항의 prompt가 비어 있습니다.`);
    if (type === 'multiple_choice' && choices.length < 2) {
      throw new Error(`${index + 1}번 객관식 문항에는 보기 2개 이상이 필요합니다.`);
    }
    return {
      id: `import-${Date.now()}-${index + 1}`,
      questionBankId: String(rawQuestion.question_bank_id ?? rawQuestion.questionBankId ?? '').trim(),
      card_id: card.id,
      type,
      type_label: QUESTION_TYPE_LABELS[type],
      term: String(rawQuestion.concept_term || rawQuestion.term || card.term || card.english || card.id || '').trim(),
      category: topic || String(card.category || '').trim(),
      topic,
      fieldName,
      keywords,
      difficulty,
      issuer,
      sourceLocation,
      prompt,
      body,
      answer,
      explanation,
      rubric,
      choices,
      section,
      points: Number.isInteger(pointsValue) ? pointsValue : null,
      expectedTimeSeconds: Number.isInteger(expectedSecondsValue) && expectedSecondsValue >= 0
        ? expectedSecondsValue
        : Number.isInteger(expectedMinutes) && expectedMinutes >= 0 ? expectedMinutes * 60 : null,
      answerGuide,
      sessionMode,
      questionOrder: Number.parseInt(rawQuestion.question_order ?? rawQuestion.order ?? '', 10) || index + 1,
      answer_index: type === 'multiple_choice' ? importedAnswerIndex(rawQuestion, choices, answer, index) : null,
    };
  });
}

function questionBankEntryPayload(question) {
  const current = hydrateQuestionState({...question});
  if (!current) return null;
  return {
    question_bank_id: current.questionBankId || '',
    card_id: current.card_id || '',
    question_type: current.type || '',
    prompt: current.prompt || '',
    body: current.body || '',
    answer: current.answer || '',
    explanation: current.explanation || '',
    rubric: Array.isArray(current.rubric) ? current.rubric : [],
    choices: Array.isArray(current.choices) ? current.choices : [],
    answer_index: Number.isInteger(current.answer_index) ? current.answer_index : null,
    topic: current.topic || current.category || '',
    field_name: current.fieldName || current.field_name || '',
    keywords: Array.isArray(current.keywords) ? current.keywords : [],
    difficulty: current.difficulty || '',
    issuer: current.issuer || '',
    source_location: current.sourceLocation || current.source_location || '',
    section: current.section || '',
    points: Number.isInteger(current.points) ? current.points : null,
    expected_time_seconds: Number.isInteger(current.expectedTimeSeconds) ? current.expectedTimeSeconds : null,
    answer_guide: current.answerGuide || '',
    session_mode: current.sessionMode || 'practice',
  };
}

async function persistQuestionBankEntries(questions) {
  const payload = {
    questions: questions.map((question) => questionBankEntryPayload(question)).filter(Boolean),
  };
  if (!payload.questions.length) return {items: [], count: 0};
  const res = await fetch('/api/question-bank', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function mergeQuestionBankEntries(questions, savedItems) {
  return questions.map((question, index) => {
    const stored = savedItems[index] || {};
    return {
      ...question,
      questionBankId: String(stored.question_bank_id || question.questionBankId || question.question_bank_id || ''),
      topic: String(stored.topic || question.topic || question.category || ''),
      fieldName: String(stored.field_name || question.fieldName || question.field_name || ''),
      keywords: Array.isArray(stored.keywords) ? stored.keywords : Array.isArray(question.keywords) ? question.keywords : [],
      difficulty: String(stored.difficulty || question.difficulty || ''),
      issuer: String(stored.issuer || question.issuer || ''),
      sourceLocation: String(stored.source_location || question.sourceLocation || question.source_location || ''),
    };
  });
}

async function importQuestionsFromText() {
  if (state.questionLoading || state.questionSaving) return;
  state.questionLoading = true;
  renderQuestionPanel();
  try {
    const payload = importedQuestionSetPayload($('questionImportInput')?.value || '');
    const parsedQuestions = buildImportedQuestions(payload.questions);
    const saved = await persistQuestionBankEntries(parsedQuestions);
    const questions = mergeQuestionBankEntries(parsedQuestions, saved.items || []);
    syncQuestionSessionModeSelect(payload.sessionMode);
    if (Number.isFinite(payload.timeLimitSeconds) && payload.timeLimitSeconds >= 0) {
      syncQuestionTimeLimitSelect(payload.timeLimitSeconds);
    }
    commitCurrentQuestionElapsed();
    resetQuestionSessionState();
    state.questionMode = true;
    prepareQuestionSession(questions, {
      title: payload.title || `가져온 모의 세트 · 카드 ${questions.length}`,
      timeLimitSeconds: Number.isFinite(payload.timeLimitSeconds) ? payload.timeLimitSeconds : null,
      mode: payload.sessionMode,
    });
    closeQuestionImportDialog();
    renderQuestionPanel();
    setMessage(`가져온 모의 세트 ${questions.length}문항을 불러왔습니다.`);
  } catch (error) {
    setQuestionImportError(error.message || String(error));
  } finally {
    state.questionLoading = false;
    renderQuestionPanel();
  }
}

function questionBankFilterValues() {
  return {
    q: $('questionBankQueryInput')?.value?.trim() || '',
    topic: $('questionBankTopicInput')?.value?.trim() || '',
    field_name: $('questionBankFieldInput')?.value?.trim() || '',
    issuer: $('questionBankIssuerInput')?.value?.trim() || '',
    source_location: $('questionBankSourceInput')?.value?.trim() || '',
    difficulty: $('questionBankDifficultySelect')?.value || '',
    question_type: $('questionBankTypeSelect')?.value || '',
    section: $('questionBankSectionInput')?.value?.trim() || '',
    limit: '500',
  };
}

function questionBankQueryString() {
  const params = new URLSearchParams();
  Object.entries(questionBankFilterValues()).forEach(([key, value]) => {
    if (!value) return;
    params.set(key, value);
  });
  return params.toString();
}

async function fetchQuestionBankEntries() {
  const qs = questionBankQueryString();
  const res = await fetch(`/api/question-bank${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function questionBankItemToQuestion(item, index) {
  return hydrateQuestionState({
    id: `bank-${item.question_bank_id || index + 1}`,
    questionBankId: String(item.question_bank_id || ''),
    card_id: String(item.card_id || ''),
    type: String(item.question_type || 'subjective'),
    type_label: QUESTION_TYPE_LABELS[item.question_type] || item.question_type || '문제',
    term: String(item.term || item.card_id || ''),
    category: String(item.topic || item.card_category || '미분류'),
    topic: String(item.topic || ''),
    fieldName: String(item.field_name || ''),
    keywords: Array.isArray(item.keywords) ? item.keywords : [],
    difficulty: String(item.difficulty || ''),
    issuer: String(item.issuer || ''),
    sourceLocation: String(item.source_location || ''),
    prompt: String(item.prompt || ''),
    body: String(item.body || ''),
    answer: String(item.answer || ''),
    explanation: String(item.explanation || ''),
    rubric: Array.isArray(item.rubric) ? item.rubric : [],
    choices: Array.isArray(item.choices) ? item.choices : [],
    answer_index: Number.isInteger(item.answer_index) ? item.answer_index : null,
    section: String(item.section || ''),
    points: Number.isInteger(item.points) ? item.points : null,
    expectedTimeSeconds: Number.isInteger(item.expected_time_seconds) ? item.expected_time_seconds : null,
    answerGuide: String(item.answer_guide || ''),
    sessionMode: normalizeQuestionSessionMode(item.session_mode || 'practice'),
    questionOrder: index + 1,
  });
}

function renderQuestionBankBrowser() {
  const panel = $('questionBankBrowser');
  const list = $('questionBankList');
  const summary = $('questionBankSummary');
  const error = $('questionBankError');
  const toggle = $('questionBankToggleBtn');
  if (!panel || !list || !summary || !error) return;
  panel.hidden = !state.questionBankOpen;
  if (toggle) {
    toggle.textContent = state.questionBankOpen ? '문제은행 닫기' : '문제은행';
    toggle.setAttribute('aria-expanded', state.questionBankOpen ? 'true' : 'false');
  }
  if (!state.questionBankOpen) return;
  const total = Number(state.questionBankSummary?.total || 0);
  const returned = Number(state.questionBankSummary?.returned || state.questionBankItems.length || 0);
  summary.textContent = state.questionBankLoading
    ? '문제은행을 불러오는 중입니다.'
    : `총 ${total}문항 · 현재 ${returned}문항 · 표의 행을 누르면 해당 문제부터 풉니다.`;
  error.textContent = state.questionBankError || '';
  if (!state.questionBankItems.length) {
    list.innerHTML = '<tr><td colspan="7" class="question-bank-empty muted">조건에 맞는 문제가 없습니다.</td></tr>';
    return;
  }
  list.innerHTML = state.questionBankItems.map((item, index) => {
    const active = state.questionBankSelectedId && state.questionBankSelectedId === String(item.question_bank_id || '');
    const prompt = escapeHtml(markdownPreviewText(item.prompt || `문제 ${index + 1}`) || `문제 ${index + 1}`);
    const typeLabel = escapeHtml(questionTypeBadge(item) || '');
    const topic = escapeHtml(item.topic || item.card_category || '');
    const issuer = escapeHtml(item.issuer || '');
    const difficulty = escapeHtml(item.difficulty || '');
    const source = escapeHtml(item.source_location || '');
    const preview = markdownPreviewText(item.body || item.answer || item.explanation || '').slice(0, 96);
    return `<tr class="question-bank-row${active ? ' active' : ''}" data-question-bank-index="${index}"><td class="question-bank-col-index">${index + 1}</td><td class="question-bank-col-title"><button class="question-bank-row-trigger" type="button" data-question-bank-index="${index}"><span class="question-bank-item-title">${prompt}</span>${preview ? `<span class="question-bank-item-preview">${escapeHtml(preview)}</span>` : ''}</button></td><td class="question-bank-col-type">${typeLabel || '—'}</td><td class="question-bank-col-field">${topic || '—'}</td><td class="question-bank-col-issuer">${issuer || '—'}</td><td class="question-bank-col-difficulty">${difficulty || '—'}</td><td class="question-bank-col-source">${source || '—'}</td></tr>`;
  }).join('');
}

function openQuestionBankSession(startIndex = 0) {
  if (!state.questionBankItems.length) {
    setMessage('문제은행 목록이 비어 있습니다.', true);
    return;
  }
  commitCurrentQuestionElapsed();
  resetQuestionSessionState();
  state.questionMode = true;
  const questions = state.questionBankItems.map((item, index) => questionBankItemToQuestion(item, index));
  const start = Math.max(0, Math.min(questions.length - 1, startIndex));
  const firstMode = questions.find((item) => item?.sessionMode)?.sessionMode || 'practice';
  prepareQuestionSession(questions, {
    title: `문제은행 세트 · ${state.questionBankItems.length}문항`,
    mode: firstMode,
  });
  state.questionIndex = start;
  state.answerRevealed = Boolean(state.questions[start]?.answerRevealed);
  state.selectedChoiceIndex = Number.isInteger(state.questions[start]?.selectedChoiceIndex) ? state.questions[start].selectedChoiceIndex : null;
  state.questionBankSelectedId = String(state.questionBankItems[start]?.question_bank_id || '');
  activateCurrentQuestionTimer();
  renderQuestionPanel();
  setMessage(`문제은행 ${state.questionBankItems.length}문항을 불러왔습니다.`);
}

async function loadQuestionBankBrowser() {
  state.questionBankLoading = true;
  state.questionBankError = '';
  renderQuestionBankBrowser();
  try {
    const data = await fetchQuestionBankEntries();
    state.questionBankItems = Array.isArray(data.items) ? data.items : [];
    state.questionBankSummary = data.summary || {total: state.questionBankItems.length, returned: state.questionBankItems.length};
    if (!state.questionBankSelectedId && state.questionBankItems[0]?.question_bank_id) {
      state.questionBankSelectedId = String(state.questionBankItems[0].question_bank_id);
    }
  } catch (error) {
    state.questionBankItems = [];
    state.questionBankSummary = {total: 0, returned: 0};
    state.questionBankError = error.message || String(error);
  } finally {
    state.questionBankLoading = false;
    renderQuestionBankBrowser();
  }
}

function toggleQuestionBankBrowser(force = !state.questionBankOpen) {
  const next = Boolean(force);
  state.questionBankOpen = next;
  renderQuestionBankBrowser();
  if (next && !state.questionBankItems.length && !state.questionBankLoading) {
    loadQuestionBankBrowser().catch(() => {});
  }
}


function hydrateQuestionState(question) {
  if (!question) return null;
  if (typeof question.userAnswer !== 'string') question.userAnswer = '';
  if (typeof question.wrongNote !== 'string') question.wrongNote = '';
  if (typeof question.answerRevealed !== 'boolean') question.answerRevealed = false;
  if (!Number.isInteger(question.selectedChoiceIndex)) question.selectedChoiceIndex = null;
  if (question.gradedCorrect !== true && question.gradedCorrect !== false) question.gradedCorrect = null;
  if (typeof question.attemptSavedAt !== 'string') question.attemptSavedAt = '';
  if (typeof question.judgment !== 'string' || !QUESTION_HISTORY_FILTER_LABELS[question.judgment]) question.judgment = 'pending';
  if (!Number.isInteger(question.questionElapsedSeconds)) question.questionElapsedSeconds = 0;
  if (typeof question.questionStartedAt !== 'string') question.questionStartedAt = '';
  if (typeof question.answeredAt !== 'string') question.answeredAt = '';
  if (typeof question.sessionId !== 'string') question.sessionId = '';
  if (typeof question.sessionTitle !== 'string') question.sessionTitle = '';
  if (!Number.isInteger(question.questionOrder)) question.questionOrder = null;
  if (!Number.isInteger(question.timeLimitSeconds)) question.timeLimitSeconds = state.questionTimeLimitSeconds || 0;
  if (!Number.isInteger(question.sessionElapsedSeconds)) question.sessionElapsedSeconds = null;
  if (typeof question.sessionMode !== 'string') question.sessionMode = state.questionSessionMode || 'practice';
  if (typeof question.section !== 'string') question.section = '';
  if (!Number.isInteger(question.points)) question.points = null;
  if (!Number.isInteger(question.expectedTimeSeconds)) question.expectedTimeSeconds = null;
  if (typeof question.answerGuide !== 'string') question.answerGuide = '';
  if (typeof question.questionBankId !== 'string') question.questionBankId = String(question.question_bank_id || '');
  if (typeof question.topic !== 'string') question.topic = String(question.category || '');
  if (typeof question.fieldName !== 'string') question.fieldName = String(question.field_name || '');
  if (!Array.isArray(question.keywords)) question.keywords = [];
  if (typeof question.difficulty !== 'string') question.difficulty = '';
  if (typeof question.issuer !== 'string') question.issuer = '';
  if (typeof question.sourceLocation !== 'string') question.sourceLocation = String(question.source_location || '');
  if (!Number.isFinite(question.questionActiveSinceMs)) question.questionActiveSinceMs = 0;
  return question;
}

function questionTypeBadge(question) {
  if (!question) return '';
  return question.type_label || (QUESTION_TYPE_LABELS[question.type] || question.type || '문제');
}

function questionNeedsManualGrading(question) {
  return question?.type !== 'multiple_choice';
}

function timeLimitValue() {
  const minutes = Number.parseInt($('questionTimeLimitSelect')?.value || '90', 10);
  return Number.isFinite(minutes) && minutes > 0 ? minutes * 60 : 0;
}

function formatElapsedClock(seconds) {
  const safeSeconds = Math.max(0, Number.parseInt(seconds || 0, 10) || 0);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const rest = safeSeconds % 60;
  return hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
}

function questionJudgmentLabel(judgment) {
  return QUESTION_HISTORY_FILTER_LABELS[judgment] || QUESTION_HISTORY_FILTER_LABELS.pending;
}

function questionJudgmentCounts() {
  const counts = {correct: 0, ambiguous: 0, wrong: 0, unknown: 0, pending: 0};
  state.questions.forEach((item) => {
    const question = hydrateQuestionState(item);
    const key = QUESTION_HISTORY_FILTER_LABELS[question?.judgment] ? question.judgment : 'pending';
    counts[key] += 1;
  });
  return counts;
}

function currentQuestionSessionElapsedSeconds() {
  const base = Math.max(0, Number.parseInt(state.questionSessionElapsedBaseSeconds || 0, 10) || 0);
  if (!state.questionSessionStartMs) return base;
  return base + Math.max(0, Math.floor((Date.now() - state.questionSessionStartMs) / 1000));
}

function currentQuestionElapsedSeconds(question = currentQuestion()) {
  const current = hydrateQuestionState(question);
  if (!current) return 0;
  const base = Math.max(0, Number.parseInt(current.questionElapsedSeconds || 0, 10) || 0);
  if (!current.questionActiveSinceMs) return base;
  return base + Math.max(0, Math.floor((Date.now() - current.questionActiveSinceMs) / 1000));
}

function stopQuestionTimer() {
  if (!state.questionTimerId) return;
  window.clearInterval(state.questionTimerId);
  state.questionTimerId = 0;
}

function updateQuestionSummaryLine() {
  const summary = $('questionSummary');
  if (!summary) return;
  const total = state.questions.length;
  const current = hydrateQuestionState(currentQuestion());
  if (state.questionLoading) {
    summary.textContent = '문제 생성 중...';
    return;
  }
  if (state.questionSaving) {
    summary.textContent = '문제 기록 저장 중...';
    return;
  }
  if (state.markSaving) {
    summary.textContent = '카드 상태 저장 중...';
    return;
  }
  if (!total || !current) {
    if (questionSessionIsBok(questionSessionModeValue())) {
      summary.textContent = `한국은행 모드 · 전공필기 ${BOK_MOCK_CONFIG.subjectiveCount}문항 + 전공논술 ${BOK_MOCK_CONFIG.essayCount}문항 · ${BOK_MOCK_CONFIG.timeLimitMinutes}분`;
      return;
    }
    const limitSeconds = timeLimitValue();
    summary.textContent = limitSeconds
      ? `현재 필터 기준으로 ${Math.round(limitSeconds / 60)}분 모의 세트를 생성합니다.`
      : '현재 필터 기준으로 제한 시간 없이 모의 세트를 생성합니다.';
    return;
  }
  const counts = questionJudgmentCounts();
  const parts = [
    questionSessionModeLabel(current.sessionMode || state.questionSessionMode),
    `${state.questionIndex + 1} / ${total}`,
    `총 ${formatElapsedClock(currentQuestionSessionElapsedSeconds())}`,
    `현재 ${formatElapsedClock(currentQuestionElapsedSeconds(current))}`,
  ];
  const limitSeconds = Number.isInteger(current.timeLimitSeconds) ? current.timeLimitSeconds : state.questionTimeLimitSeconds;
  if (limitSeconds > 0) {
    parts.push(`남은 ${formatElapsedClock(Math.max(0, limitSeconds - currentQuestionSessionElapsedSeconds()))}`);
  }
  if (current.section) parts.push(current.section);
  if (Number.isInteger(current.points)) parts.push(`${current.points}점`);
  if (Number.isInteger(current.expectedTimeSeconds) && current.expectedTimeSeconds > 0) {
    parts.push(`권장 ${formatElapsedClock(current.expectedTimeSeconds)}`);
  }
  parts.push(`맞음 ${counts.correct}`);
  parts.push(`애매 ${counts.ambiguous}`);
  parts.push(`틀림 ${counts.wrong}`);
  parts.push(`모름 ${counts.unknown}`);
  parts.push(`미채점 ${counts.pending}`);
  if (state.questionSessionFinishedAt) parts.push('세트 종료');
  summary.textContent = parts.join(' · ');
}

function startQuestionTimer() {
  if (state.questionTimerId || !state.questionMode || !state.questions.length || !state.questionSessionStartMs || state.questionSessionFinishedAt) return;
  state.questionTimerId = window.setInterval(() => {
    updateQuestionSummaryLine();
  }, 1000);
}

function commitCurrentQuestionElapsed() {
  const question = hydrateQuestionState(currentQuestion());
  if (!question || !question.questionActiveSinceMs) return;
  question.questionElapsedSeconds = currentQuestionElapsedSeconds(question);
  question.questionActiveSinceMs = 0;
}

function activateCurrentQuestionTimer() {
  const question = hydrateQuestionState(currentQuestion());
  if (!question || !state.questionMode || state.questionSessionFinishedAt) return;
  if (!question.questionStartedAt) question.questionStartedAt = new Date().toISOString();
  if (!question.questionActiveSinceMs) question.questionActiveSinceMs = Date.now();
  startQuestionTimer();
}

function resetQuestionSessionState() {
  stopQuestionTimer();
  state.questionSessionId = '';
  state.questionSessionTitle = '';
  state.questionSessionStartedAt = '';
  state.questionSessionStartMs = 0;
  state.questionSessionElapsedBaseSeconds = 0;
  state.questionTimeLimitSeconds = 0;
  state.questionSessionMode = questionSessionModeValue();
  state.questionSessionFinishedAt = '';
}

function buildQuestionSessionTitle(mode = questionSessionModeValue()) {
  const normalizedMode = normalizeQuestionSessionMode(mode);
  const stamp = new Date().toLocaleString('ko-KR', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
  if (questionSessionIsBok(normalizedMode)) {
    return `한국은행 모의 세트 ${stamp} · 전공필기 ${BOK_MOCK_CONFIG.subjectiveCount} + 전공논술 ${BOK_MOCK_CONFIG.essayCount} · ${BOK_MOCK_CONFIG.timeLimitMinutes}분`;
  }
  const typeText = selectedQuestionTypeLabelsForPrompt().join('/') || '혼합형';
  const limitSeconds = timeLimitValue();
  const limitLabel = limitSeconds ? `${Math.round(limitSeconds / 60)}분` : '무제한';
  return `모의 세트 ${stamp} · 카드 ${state.filtered.length} · ${typeText} · ${limitLabel}`;
}

function prepareQuestionSession(questions, options = {}) {
  const sessionStartedAt = new Date().toISOString();
  const importedTitle = String(options.title || '').trim();
  const importedLimit = Number.isFinite(options.timeLimitSeconds) && options.timeLimitSeconds >= 0
    ? Math.floor(options.timeLimitSeconds)
    : null;
  const sessionMode = normalizeQuestionSessionMode(options.mode || questionSessionModeValue());
  syncQuestionSessionModeSelect(sessionMode);
  state.questionSessionId = `mock-${Date.now()}`;
  state.questionSessionMode = sessionMode;
  state.questionSessionTitle = importedTitle || buildQuestionSessionTitle(sessionMode);
  state.questionSessionStartedAt = sessionStartedAt;
  state.questionSessionStartMs = Date.now();
  state.questionSessionElapsedBaseSeconds = 0;
  state.questionTimeLimitSeconds = importedLimit ?? timeLimitValue();
  state.questionSessionFinishedAt = '';
  state.questions = questions.map((item, index) => hydrateQuestionState({
    ...item,
    judgment: 'pending',
    questionElapsedSeconds: 0,
    questionStartedAt: '',
    answeredAt: '',
    sessionMode: normalizeQuestionSessionMode(item?.sessionMode || sessionMode),
    section: String(item?.section || '').trim(),
    points: Number.isInteger(item?.points) ? item.points : null,
    expectedTimeSeconds: Number.isInteger(item?.expectedTimeSeconds) ? item.expectedTimeSeconds : null,
    answerGuide: String(item?.answerGuide || '').trim(),
    questionOrder: Number.isInteger(item?.questionOrder) ? item.questionOrder : index + 1,
    sessionId: state.questionSessionId,
    sessionTitle: state.questionSessionTitle,
    timeLimitSeconds: Number.isInteger(item?.timeLimitSeconds) ? item.timeLimitSeconds : state.questionTimeLimitSeconds,
    questionActiveSinceMs: 0,
  }));
  state.questionIndex = 0;
  state.answerRevealed = false;
  state.selectedChoiceIndex = null;
  activateCurrentQuestionTimer();
  updateQuestionSummaryLine();
}

function selectedAnswerText(question) {
  const current = hydrateQuestionState(question);
  if (!current) return '';
  if (Array.isArray(current.choices) && Number.isInteger(current.selectedChoiceIndex)) {
    return String(current.choices[current.selectedChoiceIndex] || '');
  }
  return String(current.userAnswer || '');
}

function questionResultText(question) {
  const current = hydrateQuestionState(question);
  if (!current || current.judgment === 'pending') return '';
  return `${questionJudgmentLabel(current.judgment)} 저장됨`;
}

function syncUpdatedCard(card) {
  if (!card?.id) return;
  const allIndex = state.cards.findIndex((item) => item.id === card.id);
  if (allIndex >= 0) state.cards[allIndex] = card;
  const filteredIndex = state.filtered.findIndex((item) => item.id === card.id);
  if (filteredIndex >= 0) state.filtered[filteredIndex] = card;
  if (state.renderedCardId === card.id) renderCard();
}

function questionAttemptPayload(question) {
  const current = hydrateQuestionState(question);
  if (!current) return null;
  return {
    question_id: current.id,
    question_bank_id: current.questionBankId || current.question_bank_id || '',
    card_id: current.card_id,
    question_type: current.type,
    prompt: current.prompt || '',
    body: current.body || '',
    user_answer: selectedAnswerText(current),
    selected_choice_index: Number.isInteger(current.selectedChoiceIndex) ? current.selectedChoiceIndex : null,
    is_correct: current.judgment === 'correct' ? true : ['ambiguous', 'wrong', 'unknown'].includes(current.judgment) ? false : null,
    judgment: current.judgment || 'pending',
    wrong_note: current.wrongNote || '',
    session_id: current.sessionId || state.questionSessionId || '',
    session_title: current.sessionTitle || state.questionSessionTitle || '',
    session_mode: current.sessionMode || state.questionSessionMode || 'practice',
    section: current.section || '',
    points: Number.isInteger(current.points) ? current.points : null,
    expected_time_seconds: Number.isInteger(current.expectedTimeSeconds) ? current.expectedTimeSeconds : null,
    answer_guide: current.answerGuide || '',
    question_order: current.questionOrder || (state.questionIndex + 1),
    question_elapsed_seconds: currentQuestionElapsedSeconds(current),
    session_elapsed_seconds: currentQuestionSessionElapsedSeconds(),
    time_limit_seconds: Number.isInteger(current.timeLimitSeconds) ? current.timeLimitSeconds : state.questionTimeLimitSeconds,
    question_started_at: current.questionStartedAt || '',
    answered_at: current.answeredAt || '',
  };
}

async function postQuestionAttempt(question) {
  const payload = questionAttemptPayload(question);
  if (!payload) throw new Error('문제 저장 데이터가 없습니다.');
  const res = await fetch('/api/questions/attempt', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function saveQuestionAttempt(question, {quiet = false} = {}) {
  const current = hydrateQuestionState(question);
  if (!current || state.questionLoading || state.questionSaving) return null;
  if (current === currentQuestion()) commitCurrentQuestionElapsed();
  state.questionSaving = true;
  renderQuestionPanel();
  try {
    const data = await postQuestionAttempt(current);
    current.attemptSavedAt = String(data.attempt?.updated_at || new Date().toISOString());
    current.gradedCorrect = data.attempt?.is_correct === true ? true : data.attempt?.is_correct === false ? false : null;
    current.judgment = data.attempt?.judgment || current.judgment || 'pending';
    current.wrongNote = String(data.attempt?.wrong_note || current.wrongNote || '');
    current.answeredAt = String(data.attempt?.answered_at || current.answeredAt || '');
    current.questionStartedAt = String(data.attempt?.question_started_at || current.questionStartedAt || '');
    current.sessionMode = String(data.attempt?.session_mode || current.sessionMode || state.questionSessionMode || 'practice');
    current.section = String(data.attempt?.section || current.section || '');
    current.points = Number.isInteger(data.attempt?.points) ? data.attempt.points : current.points;
    current.expectedTimeSeconds = Number.isInteger(data.attempt?.expected_time_seconds) ? data.attempt.expected_time_seconds : current.expectedTimeSeconds;
    current.answerGuide = String(data.attempt?.answer_guide || current.answerGuide || '');
    current.questionElapsedSeconds = Number.isInteger(data.attempt?.question_elapsed_seconds) ? data.attempt.question_elapsed_seconds : current.questionElapsedSeconds;
    current.sessionElapsedSeconds = Number.isInteger(data.attempt?.session_elapsed_seconds) ? data.attempt.session_elapsed_seconds : current.sessionElapsedSeconds;
    if (Number.isInteger(data.attempt?.selected_choice_index)) current.selectedChoiceIndex = data.attempt.selected_choice_index;
    syncUpdatedCard(data.card);
    if (state.questionHistoryOpen) loadQuestionHistory();
    if (!quiet) setMessage(questionResultText(current) || '문제 채점 저장 완료');
    return data;
  } catch (error) {
    if (!quiet) setMessage(`문제 채점 저장 실패: ${error.message || error}`, true);
    throw error;
  } finally {
    state.questionSaving = false;
    activateCurrentQuestionTimer();
    renderQuestionPanel();
  }
}

async function finishQuestionSession() {
  if (!state.questions.length || state.questionLoading || state.questionSaving) return;
  commitCurrentQuestionElapsed();
  state.questionSessionElapsedBaseSeconds = currentQuestionSessionElapsedSeconds();
  state.questionSessionStartMs = 0;
  state.questionSessionFinishedAt = new Date().toISOString();
  stopQuestionTimer();
  state.questionSaving = true;
  renderQuestionPanel();
  try {
    const settled = await Promise.allSettled(state.questions.map((question) => postQuestionAttempt(question)));
    let failures = 0;
    settled.forEach((result, index) => {
      if (result.status !== 'fulfilled') {
        failures += 1;
        return;
      }
      const current = hydrateQuestionState(state.questions[index]);
      const payload = result.value || {};
      current.attemptSavedAt = String(payload.attempt?.updated_at || current.attemptSavedAt || '');
      current.gradedCorrect = payload.attempt?.is_correct === true ? true : payload.attempt?.is_correct === false ? false : null;
      current.judgment = payload.attempt?.judgment || current.judgment || 'pending';
      current.wrongNote = String(payload.attempt?.wrong_note || current.wrongNote || '');
      current.answeredAt = String(payload.attempt?.answered_at || current.answeredAt || '');
      current.questionStartedAt = String(payload.attempt?.question_started_at || current.questionStartedAt || '');
      current.sessionMode = String(payload.attempt?.session_mode || current.sessionMode || state.questionSessionMode || 'practice');
      current.section = String(payload.attempt?.section || current.section || '');
      current.points = Number.isInteger(payload.attempt?.points) ? payload.attempt.points : current.points;
      current.expectedTimeSeconds = Number.isInteger(payload.attempt?.expected_time_seconds) ? payload.attempt.expected_time_seconds : current.expectedTimeSeconds;
      current.answerGuide = String(payload.attempt?.answer_guide || current.answerGuide || '');
      current.questionElapsedSeconds = Number.isInteger(payload.attempt?.question_elapsed_seconds) ? payload.attempt.question_elapsed_seconds : current.questionElapsedSeconds;
      syncUpdatedCard(payload.card);
    });
    if (state.questionHistoryOpen) loadQuestionHistory();
    const counts = questionJudgmentCounts();
    const summaryText = `세트 종료 · 총 ${formatElapsedClock(currentQuestionSessionElapsedSeconds())} · 맞음 ${counts.correct} · 애매 ${counts.ambiguous} · 틀림 ${counts.wrong} · 모름 ${counts.unknown} · 미채점 ${counts.pending}`;
    const finishMessage = questionSessionIsBok(state.questionSessionMode) ? `${summaryText} · 이제 정답 확인 가능` : summaryText;
    setMessage(failures ? `${finishMessage} · 저장 실패 ${failures}건` : finishMessage, failures > 0);
  } finally {
    state.questionSaving = false;
    renderQuestionPanel();
  }
}

function setQuestionJudgment(judgment) {
  const question = hydrateQuestionState(currentQuestion());
  if (!question) return;
  question.answerRevealed = true;
  question.judgment = QUESTION_HISTORY_FILTER_LABELS[judgment] ? judgment : 'pending';
  question.answeredAt = new Date().toISOString();
  question.gradedCorrect = judgment === 'correct' ? true : ['ambiguous', 'wrong', 'unknown'].includes(judgment) ? false : null;
  if (question.judgment === 'correct') question.wrongNote = '';
  state.answerRevealed = true;
  renderQuestionPanel();
  saveQuestionAttempt(question).catch(() => {});
}

function saveCurrentWrongNote() {
  const question = hydrateQuestionState(currentQuestion());
  if (!question) return;
  question.answerRevealed = true;
  if (!QUESTION_HISTORY_FILTER_LABELS[question.judgment] || question.judgment === 'pending') {
    question.judgment = 'wrong';
  }
  question.answeredAt = question.answeredAt || new Date().toISOString();
  question.gradedCorrect = question.judgment === 'correct' ? true : false;
  state.answerRevealed = true;
  renderQuestionPanel();
  saveQuestionAttempt(question).catch(() => {});
}

function setQuestionControlsDisabled(disabled) {
  ['generateQuestionsBtn', 'openAiQuizSearchBtn', 'questionHistoryBtn', 'prevQuestionBtn', 'revealAnswerBtn', 'nextQuestionBtn', 'openQuestionCardBtn', 'questionCountSelect', 'questionTimeLimitSelect', 'questionSessionModeSelect', 'finishQuestionSessionBtn', 'openQuestionImportBtn', 'questionImportApplyBtn', 'questionBankToggleBtn', 'questionBankRefreshBtn', 'questionBankLoadBtn', 'questionBankCloseBtn', 'questionBankQueryInput', 'questionBankTopicInput', 'questionBankFieldInput', 'questionBankIssuerInput', 'questionBankSourceInput', 'questionBankDifficultySelect', 'questionBankTypeSelect', 'questionBankSectionInput'].forEach((id) => {
    const element = $(id);
    if (element) element.disabled = disabled;
  });
  document.querySelectorAll('.question-type-row input').forEach((input) => { input.disabled = disabled; });
}

function renderQuestionSessionReview() {
  const review = $('questionSessionReview');
  if (!review) return;
  if (!state.questionMode || !state.questions.length || !state.questionSessionFinishedAt) {
    review.hidden = true;
    review.innerHTML = '';
    return;
  }
  const current = hydrateQuestionState(currentQuestion());
  const counts = questionJudgmentCounts();
  const totalPoints = state.questions.reduce((sum, item) => {
    const question = hydrateQuestionState(item);
    return sum + (Number.isInteger(question?.points) ? question.points : 0);
  }, 0);
  const currentSection = String(current?.section || '').trim();
  review.hidden = false;
  review.innerHTML = `
    <div class="question-session-summary">
      <strong>${escapeHtml(state.questionSessionTitle || '모의 세트')}</strong>
      <p>${escapeHtml(questionSessionModeLabel(current?.sessionMode || state.questionSessionMode))} · 총 ${formatElapsedClock(currentQuestionSessionElapsedSeconds())}${totalPoints ? ` · 총 ${totalPoints}점` : ''}${currentSection ? ` · 현재 ${escapeHtml(currentSection)}` : ''}</p>
      <ul>
        <li>맞음 ${counts.correct} · 애매 ${counts.ambiguous} · 틀림 ${counts.wrong} · 모름 ${counts.unknown} · 미채점 ${counts.pending}</li>
        <li>${questionSessionIsBok(current?.sessionMode || state.questionSessionMode) ? '정답을 확인하며 문항별 부분점수 관점으로 회고를 남기세요.' : '문항별 채점과 오답노트를 확인하세요.'}</li>
      </ul>
    </div>`;
}

function renderQuestionPanel() {
  const panel = $('questionPanel');
  if (!panel) return;
  panel.hidden = !state.questionMode;
  document.body.classList.toggle('question-mode-active', state.questionMode);
  const card = $('questionCard');
  updateRandomButtons();
  updateQuestionPracticeButton();
  renderQuestionBankBrowser();
  if (!state.questionMode) {
    stopQuestionTimer();
    renderQuestionSessionReview();
    return;
  }

  setQuestionControlsDisabled(state.questionLoading || state.questionSaving || state.markSaving);
  const total = state.questions.length;
  const question = hydrateQuestionState(currentQuestion());
  const reviewCard = currentQuestionCard();
  if (question) {
    state.answerRevealed = Boolean(question.answerRevealed);
    state.selectedChoiceIndex = Number.isInteger(question.selectedChoiceIndex) ? question.selectedChoiceIndex : null;
    if (question.questionBankId) state.questionBankSelectedId = String(question.questionBankId);
    activateCurrentQuestionTimer();
  } else {
    state.answerRevealed = false;
    state.selectedChoiceIndex = null;
    stopQuestionTimer();
  }
  updateQuestionSummaryLine();
  renderQuestionSessionReview();
  if (!card) return;
  if (state.questionLoading) {
    card.innerHTML = '<div class="question-card-empty muted">문제를 생성하는 중입니다...</div>';
    return;
  }
  if (!question) {
    card.innerHTML = '<div class="question-card-empty muted">문제 생성, 가져오기, 또는 문제은행 목록에서 문항을 불러오세요.</div>';
    return;
  }

  const revealLocked = questionRevealLocked(question);
  const reviewDisabled = state.questionLoading || state.questionSaving || state.markSaving || !reviewCard;
  const reviewStatus = reviewCard?.known_status || '';
  const reviewStatusText = reviewCard
    ? `카드 상태 ${statusLabel(reviewStatus)}`
    : '원본 카드를 찾지 못했습니다.';
  const reviewBoxHtml = `
    <div class="question-review-box">
      <div class="question-review-head">
        <span class="question-review-label">카드</span>
        <span class="question-review-status">${escapeHtml(reviewStatusText)}</span>
      </div>
      <div class="question-review-actions">
        <button class="mark known${reviewStatus === 'O' ? ' active' : ''}" type="button" data-question-mark="O" aria-label="이 개념을 안다로 표시" title="안다 (O)" ${reviewDisabled ? 'disabled' : ''}>O</button>
        <button class="mark unknown${reviewStatus === 'X' ? ' active' : ''}" type="button" data-question-mark="X" aria-label="이 개념을 모른다로 표시" title="모른다 (X)" ${reviewDisabled ? 'disabled' : ''}>X</button>
        <button class="mark unreviewed${!reviewStatus ? ' active' : ''}" type="button" data-question-mark="" aria-label="이 개념을 미복습으로 표시" title="미복습 (–)" ${reviewDisabled ? 'disabled' : ''}>–</button>
      </div>
    </div>`;
  const choices = Array.isArray(question.choices) ? question.choices : [];
  const choiceHtml = choices.length ? `
    <div class="question-surface question-choice-surface">
      <ol class="question-choices">
        ${choices.map((choice, index) => {
          const isAnswer = question.answerRevealed && index === question.answer_index;
          const isSelected = index === question.selectedChoiceIndex;
          return `<li><button class="question-choice${isAnswer ? ' answer' : ''}${isSelected ? ' selected' : ''}" type="button" data-choice-index="${index}" ${state.questionSaving || state.markSaving ? 'disabled' : ''}>${renderMarkdownInline(choice)}</button></li>`;
        }).join('')}
      </ol>
    </div>` : '';
  const answerGuideHtml = question.answerGuide
    ? `<div class="question-answer-guide question-markdown"><strong>답안 가이드</strong>${renderQuestionMarkdown(question.answerGuide)}</div>`
    : '';
  const draftPlaceholder = revealLocked
    ? '세트 종료 전까지 정답이 공개되지 않습니다. 실전처럼 답안을 먼저 작성하세요.'
    : '여기에 답안을 적고 정답/해설을 본 뒤 결과를 저장하세요.';
  const draftHtml = questionNeedsManualGrading(question) ? `
    <div class="question-answer-draft question-surface">
      <label class="question-answer-label" for="questionAnswerInput">내 답안</label>
      <textarea id="questionAnswerInput" class="question-answer-input" rows="${question.type === 'essay' ? 6 : 4}" placeholder="${escapeHtml(draftPlaceholder)}" ${state.questionSaving || state.markSaving ? 'disabled' : ''}>${escapeHtml(question.userAnswer || '')}</textarea>
      ${answerGuideHtml}
    </div>` : (answerGuideHtml ? `<div class="question-answer-draft question-surface">${answerGuideHtml}</div>` : '');
  const rubric = Array.isArray(question.rubric) && question.rubric.length ? `
    <div class="question-rubric">
      <strong>채점 포인트</strong>
      <ul>${question.rubric.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>
    </div>` : '';
  const resultText = questionResultText(question);
  const resultTone = question.judgment === 'pending' ? '' : question.judgment;
  const resultHtml = resultText ? `<p class="question-grade-status ${resultTone}">${escapeHtml(resultText)}</p>` : '';
  const gradeHtml = question.answerRevealed ? `
    <div class="question-grade-row">
      <strong>풀이 결과</strong>
      <div class="question-grade-actions">
        ${[
          ['correct', '맞음'],
          ['ambiguous', '애매함'],
          ['wrong', '틀림'],
          ['unknown', '모름'],
        ].map(([key, label]) => `<button class="question-grade-button ${key}${question.judgment === key ? ' active' : ''}" type="button" data-question-judgment="${key}" ${state.questionSaving || state.markSaving ? 'disabled' : ''}>${label} 저장</button>`).join('')}
      </div>
      ${resultHtml}
    </div>` : resultHtml;
  const wrongNoteHtml = question.answerRevealed && ['ambiguous', 'wrong', 'unknown'].includes(question.judgment) ? `
    <div class="question-wrong-note-box">
      <label class="question-answer-label" for="questionWrongNoteInput">오답노트</label>
      <textarea id="questionWrongNoteInput" class="question-wrong-note" rows="3" placeholder="왜 애매했는지, 왜 틀렸는지, 다음에 무엇을 다시 볼지 적으세요." ${state.questionSaving || state.markSaving ? 'disabled' : ''}>${escapeHtml(question.wrongNote || '')}</textarea>
      <div class="question-wrong-note-actions">
        <button class="question-grade-button wrong-note-save" type="button" data-question-wrong-note-save="1" ${state.questionSaving || state.markSaving ? 'disabled' : ''}>오답노트 저장</button>
      </div>
    </div>` : '';
  const answer = question.answerRevealed ? `
    <div class="question-answer question-surface question-answer-surface">
      <strong>정답/모범답안</strong>
      <div class="question-answer-markdown">${renderQuestionMarkdown(question.answer || '')}</div>
      ${question.explanation ? `<div class="question-explanation-markdown">${renderQuestionMarkdown(question.explanation)}</div>` : ''}
      ${rubric}
      ${gradeHtml}
      ${wrongNoteHtml}
    </div>` : '';
  const sessionMode = question.sessionMode || state.questionSessionMode;
  const sessionModeLabelText = questionSessionModeLabel(sessionMode);
  const lockNoticeHtml = revealLocked ? `
    <div class="question-session-lock question-side-note">
      <strong>한은 모드</strong>
      <p>세트 종료 전까지 정답과 해설이 잠겨 있습니다. 전 문항을 먼저 풀고 제출한 뒤 문항별로 회고하세요.</p>
    </div>` : '';
  const sideStateHtml = revealLocked
    ? lockNoticeHtml
    : `<div class="question-side-note">
        <span class="question-side-note-label">풀이 상태</span>
        <p>${escapeHtml(question.answerRevealed ? '정답과 해설을 확인하고 채점 결과를 남기세요.' : '답안을 먼저 작성한 뒤 정답/해설을 열어 비교하세요.')}</p>
      </div>`;
  const sessionMeta = [
    state.questionSessionTitle || question.sessionTitle,
    sessionModeLabelText,
    question.section || '',
    question.fieldName || '',
    question.issuer || '',
    question.sourceLocation || '',
    question.difficulty ? `난이도 ${question.difficulty}` : '',
    Number.isInteger(question.points) ? `${question.points}점` : '',
    question.questionOrder ? `문항 ${question.questionOrder}` : '',
    Number.isInteger(question.expectedTimeSeconds) ? `권장 ${formatElapsedClock(question.expectedTimeSeconds)}` : '',
    `문항 시간 ${formatElapsedClock(currentQuestionElapsedSeconds(question))}`,
  ].filter(Boolean).join(' · ');
  const progressPercent = total ? Math.max(0, Math.min(100, Math.round(((state.questionIndex + 1) / total) * 100))) : 0;
  const questionPosition = total ? `문항 ${state.questionIndex + 1} / ${total}` : '문항';
  const bodyHtml = question.body ? `<div class="question-body question-surface">${renderQuestionMarkdown(question.body)}</div>` : '';
  card.innerHTML = `
    <div class="question-card-shell">
      <div class="question-card-progress" aria-hidden="true"><span style="width:${progressPercent}%"></span></div>
      <div class="question-card-head">
        <div class="question-card-head-copy">
          <p class="question-card-kicker">${escapeHtml(sessionModeLabelText)} · ${escapeHtml(questionPosition)}</p>
          <h2 class="question-card-title">${escapeHtml(questionTypeBadge(question))} · ${escapeHtml(question.category || '미분류')}</h2>
          <p class="question-session-meta">${escapeHtml(sessionMeta)}</p>
        </div>
        <div class="question-meta">
          <span class="badge">${escapeHtml(questionTypeBadge(question))}</span>
          <span class="badge">${escapeHtml(question.category || '미분류')}</span>
          ${question.fieldName ? `<span class="badge">${escapeHtml(question.fieldName)}</span>` : ''}
          ${question.issuer ? `<span class="badge">${escapeHtml(question.issuer)}</span>` : ''}
          ${question.difficulty ? `<span class="badge">난이도 ${escapeHtml(question.difficulty)}</span>` : ''}
          ${question.section ? `<span class="badge">${escapeHtml(question.section)}</span>` : ''}
          ${Number.isInteger(question.points) ? `<span class="badge">${escapeHtml(String(question.points))}점</span>` : ''}
          ${question.judgment !== 'pending' ? `<span class="badge">${escapeHtml(questionJudgmentLabel(question.judgment))}</span>` : ''}
        </div>
      </div>
      <div class="question-card-grid">
        <div class="question-main-stack">
          <div class="question-prompt question-surface">${renderQuestionMarkdown(question.prompt || '문제')}</div>
          ${bodyHtml}
          ${choiceHtml}
          ${draftHtml}
          ${answer}
        </div>
        <aside class="question-side-stack">
          ${sideStateHtml}
          ${reviewBoxHtml}
        </aside>
      </div>
    </div>
  `;
  $('prevQuestionBtn').disabled = state.questionLoading || state.questionSaving || state.markSaving || state.questionIndex <= 0;
  $('nextQuestionBtn').disabled = state.questionLoading || state.questionSaving || state.markSaving || state.questionIndex >= total - 1;
  $('revealAnswerBtn').disabled = state.questionLoading || state.questionSaving || state.markSaving || !question || revealLocked;
  if ($('revealAnswerBtn')) {
    $('revealAnswerBtn').textContent = revealLocked ? '정답 잠금' : '정답';
    $('revealAnswerBtn').title = revealLocked ? '한은 모드는 세트 종료 전 정답이 공개되지 않습니다.' : '정답/해설 보기';
  }
  $('openQuestionCardBtn').disabled = state.questionLoading || state.questionSaving || state.markSaving || !reviewCard;
  if ($('finishQuestionSessionBtn')) {
    $('finishQuestionSessionBtn').disabled = state.questionLoading || state.questionSaving || state.markSaving || !total;
    $('finishQuestionSessionBtn').textContent = questionSessionIsBok(question.sessionMode || state.questionSessionMode) && !state.questionSessionFinishedAt ? '제출' : '종료';
  }
}

async function requestGeneratedQuestions({cardIds, types, count, seed}) {
  const res = await fetch('/api/questions/generate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({card_ids: cardIds, types, count, seed}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function shuffledQuestionCards(cards) {
  const items = [...cards];
  for (let index = items.length - 1; index > 0; index -= 1) {
    const nextIndex = Math.floor(Math.random() * (index + 1));
    [items[index], items[nextIndex]] = [items[nextIndex], items[index]];
  }
  return items;
}

function withBokQuestionMeta(question, {section, points, expectedTimeSeconds, answerGuide, order}) {
  return {
    ...question,
    sessionMode: 'bok',
    section,
    points,
    expectedTimeSeconds,
    answerGuide,
    questionOrder: order,
  };
}

async function generateBokExamQuestions(seed) {
  const totalNeeded = BOK_MOCK_CONFIG.subjectiveCount + BOK_MOCK_CONFIG.essayCount;
  if (state.filtered.length < totalNeeded) {
    throw new Error(`한은 모드는 현재 필터 카드가 최소 ${totalNeeded}개 필요합니다.`);
  }
  const shuffled = shuffledQuestionCards(state.filtered);
  const subjectiveIds = shuffled.slice(0, BOK_MOCK_CONFIG.subjectiveCount).map((card) => card.id);
  const essayIds = shuffled.slice(BOK_MOCK_CONFIG.subjectiveCount, totalNeeded).map((card) => card.id);
  const [subjectiveData, essayData] = await Promise.all([
    requestGeneratedQuestions({cardIds: subjectiveIds, types: ['subjective'], count: BOK_MOCK_CONFIG.subjectiveCount, seed}),
    requestGeneratedQuestions({cardIds: essayIds, types: ['essay'], count: BOK_MOCK_CONFIG.essayCount, seed: seed + 1}),
  ]);
  const subjectiveQuestions = (subjectiveData.questions || []).slice(0, BOK_MOCK_CONFIG.subjectiveCount).map((question, index) => withBokQuestionMeta(question, {
    section: '전공필기',
    points: BOK_MOCK_CONFIG.subjectivePoints,
    expectedTimeSeconds: BOK_MOCK_CONFIG.subjectiveExpectedSeconds,
    answerGuide: BOK_MOCK_CONFIG.subjectiveAnswerGuide,
    order: index + 1,
  }));
  const essayQuestions = (essayData.questions || []).slice(0, BOK_MOCK_CONFIG.essayCount).map((question, index) => withBokQuestionMeta(question, {
    section: '전공논술',
    points: BOK_MOCK_CONFIG.essayPoints,
    expectedTimeSeconds: BOK_MOCK_CONFIG.essayExpectedSeconds,
    answerGuide: BOK_MOCK_CONFIG.essayAnswerGuide,
    order: BOK_MOCK_CONFIG.subjectiveCount + index + 1,
  }));
  return [...subjectiveQuestions, ...essayQuestions];
}

async function generateQuestionsFromCurrentFilter() {
  if (state.questionLoading || state.questionSaving) return;
  if (!state.filtered.length) {
    setMessage('문제를 만들 카드가 없습니다. 필터를 바꿔주세요.', true);
    return;
  }
  commitCurrentQuestionElapsed();
  resetQuestionSessionState();
  state.questionMode = true;
  state.questionLoading = true;
  state.questionSaving = false;
  state.answerRevealed = false;
  state.selectedChoiceIndex = null;
  renderQuestionPanel();
  try {
    const seed = Date.now();
    const mode = questionSessionModeValue();
    applyQuestionSessionModePreset(mode);
    const questions = questionSessionIsBok(mode)
      ? await generateBokExamQuestions(seed)
      : (await requestGeneratedQuestions({
          cardIds: state.filtered.map((card) => card.id),
          types: selectedQuestionTypes(),
          count: questionCountValue(),
          seed,
        })).questions || [];
    prepareQuestionSession(questions.map((item) => hydrateQuestionState({...item})), {mode});
    setMessage(questionSessionIsBok(mode) ? '한국은행 모의 세트 9문항 생성 완료' : `모의 세트 ${state.questions.length}문항 생성 완료`);
  } catch (error) {
    state.questions = [];
    resetQuestionSessionState();
    setMessage(`문제 생성 실패: ${error.message || error}`, true);
  } finally {
    state.questionLoading = false;
    renderQuestionPanel();
  }
}

function toggleQuestionMode(force = !state.questionMode) {
  const nextMode = Boolean(force);
  if (nextMode && state.audioPlaying) stopAudioPlayback('문제 풀이 모드로 전환해 자동 듣기를 정지했습니다.');
  if (!nextMode) {
    commitCurrentQuestionElapsed();
    state.questionSessionElapsedBaseSeconds = currentQuestionSessionElapsedSeconds();
    state.questionSessionStartMs = 0;
    stopQuestionTimer();
    closeQuestionHistory();
  } else if (state.questions.length && !state.questionSessionFinishedAt && !state.questionSessionStartMs) {
    state.questionSessionStartMs = Date.now();
    activateCurrentQuestionTimer();
  }
  state.questionMode = nextMode;
  if (state.questionMode && state.questionBankOpen && !state.questionBankItems.length && !state.questionBankLoading) {
    loadQuestionBankBrowser().catch(() => {});
  }
  renderQuestionPanel();
  setMessage(state.questionMode ? (state.questions.length ? '모의 세트를 다시 열었습니다.' : '문제 풀이를 열었습니다. 생성 버튼, 가져오기, 또는 문제은행을 사용하세요.') : '문제 풀이를 닫았습니다.');
}


function openQuestionPracticeFromMenu() {
  toggleMenu(false);
  toggleQuestionMode(true);
}

function revealQuestionAnswer() {
  const question = hydrateQuestionState(currentQuestion());
  if (!question) return;
  if (questionRevealLocked(question)) {
    setMessage('한은 모드는 세트 종료 전 정답을 공개하지 않습니다. 제출 후 확인하세요.', true);
    return;
  }
  question.answerRevealed = true;
  state.answerRevealed = true;
  renderQuestionPanel();
}

function moveQuestion(delta) {
  if (!state.questions.length) return;
  commitCurrentQuestionElapsed();
  state.questionIndex = Math.max(0, Math.min(state.questions.length - 1, state.questionIndex + delta));
  const question = hydrateQuestionState(currentQuestion());
  state.answerRevealed = Boolean(question?.answerRevealed);
  state.selectedChoiceIndex = Number.isInteger(question?.selectedChoiceIndex) ? question.selectedChoiceIndex : null;
  activateCurrentQuestionTimer();
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
  commitCurrentQuestionElapsed();
  toggleQuestionMode(false);
  jumpToCard(card);
  state.flipped = true;
  renderCard();
  setMessage(`${card.term} 원본 카드로 이동했습니다.`);
}


async function markQuestionSourceCard(status) {
  const question = currentQuestion();
  const current = currentQuestionCard();
  if (!question) return;
  if (!current) {
    setMessage('원본 카드를 찾지 못했습니다.', true);
    return;
  }
  if (state.questionLoading || state.questionSaving || state.markSaving) return;
  const previous = {...current};
  const optimistic = buildMarkedCardState(previous, status);

  state.markSaving = true;
  syncUpdatedCard(optimistic);
  renderStats(summaryFromRows(rowsForHeaderStats()));
  renderQuestionPanel();
  setMessage(`${optimistic.term}: ${statusLabel(status)} 저장 중...`);

  try {
    const res = await fetch(`/api/cards/${encodeURIComponent(current.id)}/mark`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({known_status: status}),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    state.summary = data.summary;
    syncUpdatedCard(data.card);
    renderStats(summaryFromRows(rowsForHeaderStats()));
    setMessage(`${data.card.term}: ${statusLabel(status)} 저장 완료`);
  } catch (error) {
    syncUpdatedCard(previous);
    renderStats(summaryFromRows(rowsForHeaderStats()));
    setMessage(`저장 실패: ${error.message || error}`, true);
  } finally {
    state.markSaving = false;
    renderQuestionPanel();
  }
}

function selectQuestionChoice(index) {
  const question = hydrateQuestionState(currentQuestion());
  if (!question) return;
  question.selectedChoiceIndex = index;
  question.userAnswer = Array.isArray(question.choices) ? String(question.choices[index] || '') : '';
  question.answeredAt = new Date().toISOString();
  state.selectedChoiceIndex = index;
  if (questionRevealLocked(question)) {
    question.answerRevealed = false;
    question.gradedCorrect = null;
    state.answerRevealed = false;
    renderQuestionPanel();
    return;
  }
  question.answerRevealed = true;
  question.gradedCorrect = index === question.answer_index;
  state.answerRevealed = true;
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
  commitCurrentQuestionElapsed();
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
    state.questionSaving = false;
    resetQuestionSessionState();
    renderQuestionPanel();
  }
  if (state.questionHistoryOpen) loadQuestionHistory();
  updateAudioEstimate();
  renderFlashcardTableWindow();
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
    renderCardWikiLinks(null);
    state.renderedCardId = null;
    state.renderedFlipped = false;
    resetBackScroll();
    updateConceptBackButton();
    renderPersonalControls(null);
    saveViewState();
    syncFlashcardTableWindowSelection();
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
  renderCardWikiLinks(c);

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
  $('definition').innerHTML = currentWordHtml(aiRewriteDisplayText(c, 'definition'), 'definition', null, emphasisTerms);
  $('detail').innerHTML = renderDetailedExplanation(aiRewriteDisplayText(c, 'detailed_explanation'), emphasisTerms);
  $('sources').innerHTML = renderSourceLinks(c.source_files);
  $('examNote').innerHTML = currentWordHtml(aiRewriteDisplayText(c, 'exam_note'), 'exam', null, emphasisTerms);
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
  syncFlashcardTableWindowSelection();
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

function safeMarkdownUrl(url) {
  const raw = String(url || '').trim();
  if (!raw) return '';
  if (raw.startsWith('/')) return raw;
  if (raw.startsWith('./') || raw.startsWith('../')) return raw;
  if (/^https?:\/\//i.test(raw)) return raw;
  if (/^data:image\//i.test(raw)) return raw;
  return '';
}

function markdownPreviewText(source) {
  return String(source || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\(([^)]+)\)/g, ' ')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/[*_`>|-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function renderMarkdownInline(source) {
  const tokens = [];
  const stash = (html) => `\u0000${tokens.push(html) - 1}\u0000`;
  let text = String(source || '');
  text = text.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g, (_match, alt, url, title) => {
    const safeUrl = safeMarkdownUrl(url);
    if (!safeUrl) return '';
    const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
    return stash(`<figure class="question-md-figure"><img class="question-md-image" src="${escapeHtml(safeUrl)}" alt="${escapeHtml(alt)}" loading="lazy"${titleAttr} />${alt ? `<figcaption>${escapeHtml(alt)}</figcaption>` : ''}</figure>`);
  });
  text = text.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g, (_match, label, url, title) => {
    const safeUrl = safeMarkdownUrl(url);
    if (!safeUrl) return escapeHtml(label);
    const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
    return stash(`<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer"${titleAttr}>${escapeHtml(label)}</a>`);
  });
  text = text.replace(/`([^`]+)`/g, (_match, code) => stash(`<code>${escapeHtml(code)}</code>`));
  text = escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+)__/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/_([^_]+)_/g, '<em>$1</em>')
    .replace(/~~([^~]+)~~/g, '<del>$1</del>')
    .replace(/\n/g, '<br />');
  return text.replace(/\u0000(\d+)\u0000/g, (_match, index) => tokens[Number(index)] || '');

}

function renderMarkdownTable(lines) {
  const cells = (line) => String(line || '').trim().replace(/^\||\|$/g, '').split('|').map((cell) => renderMarkdownInline(cell.trim()));
  const header = cells(lines[0]);
  const body = lines.slice(2).map((line) => cells(line));
  return `<div class="question-md-table-wrap"><table class="question-md-table"><thead><tr>${header.map((cell) => `<th>${cell}</th>`).join('')}</tr></thead><tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function renderQuestionMarkdown(source) {
  const text = String(source || '').replace(/\r\n?/g, '\n');
  if (!text.trim()) return '';
  const lines = text.split('\n');
  const html = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }
    if (/^```/.test(trimmed)) {
      const fence = trimmed.slice(3).trim();
      const code = [];
      index += 1;
      while (index < lines.length && !/^```/.test(lines[index].trim())) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      html.push(`<pre class="question-md-pre"><code class="language-${escapeHtml(fence || 'text')}">${escapeHtml(code.join('\n'))}</code></pre>`);
      continue;
    }
    if (trimmed.includes('|') && index + 1 < lines.length && /^\s*\|?\s*[:-]-*.*\|/.test(lines[index + 1])) {
      const tableLines = [line, lines[index + 1]];
      index += 2;
      while (index < lines.length && lines[index].includes('|') && lines[index].trim()) {
        tableLines.push(lines[index]);
        index += 1;
      }
      html.push(renderMarkdownTable(tableLines));
      continue;
    }
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = Math.min(6, heading[1].length);
      html.push(`<h${level} class="question-md-h${level}">${renderMarkdownInline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }
    if (/^>\s?/.test(trimmed)) {
      const quote = [];
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
        quote.push(lines[index].trim().replace(/^>\s?/, ''));
        index += 1;
      }
      html.push(`<blockquote class="question-md-blockquote">${quote.map((part) => `<p>${renderMarkdownInline(part)}</p>`).join('')}</blockquote>`);
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ''));
        index += 1;
      }
      html.push(`<ul class="question-md-list">${items.map((item) => `<li>${renderMarkdownInline(item)}</li>`).join('')}</ul>`);
      continue;
    }
    if (/^\d+[.)]\s+/.test(trimmed)) {
      const items = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+[.)]\s+/, ''));
        index += 1;
      }
      html.push(`<ol class="question-md-list ordered">${items.map((item) => `<li>${renderMarkdownInline(item)}</li>`).join('')}</ol>`);
      continue;
    }
    const paragraph = [trimmed];
    index += 1;
    while (index < lines.length) {
      const next = lines[index].trim();
      if (!next || /^```/.test(next) || /^(#{1,6})\s+/.test(next) || /^>\s?/.test(next) || /^[-*]\s+/.test(next) || /^\d+[.)]\s+/.test(next)) break;
      if (next.includes('|') && index + 1 < lines.length && /^\s*\|?\s*[:-]-*.*\|/.test(lines[index + 1])) break;
      paragraph.push(next);
      index += 1;
    }
    html.push(`<p>${renderMarkdownInline(paragraph.join('\n'))}</p>`);
  }
  return `<div class="question-markdown">${html.join('')}</div>`;
}

function updateRandomButtons() {
  const button = $('shuffleBtn');
  if (!button) return;
  button.classList.toggle('active', state.randomMode);
  button.setAttribute('aria-pressed', String(state.randomMode));
}

function updateQuestionPracticeButton() {
  const button = $('questionPracticeBtn');
  if (!button) return;
  button.classList.toggle('active', state.questionMode);
  button.setAttribute('aria-pressed', String(state.questionMode));
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
  const previous = {...current};
  const optimistic = buildMarkedCardState(previous, status);

  state.markSaving = true;
  setMarkButtonsDisabled(true);
  syncUpdatedCard(optimistic);
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
    state.summary = data.summary;
    syncUpdatedCard(data.card);
    applyFilters(data.card.id);
    advanceAfterMark(data.card.id);
    setMessage(`${data.card.term}: ${statusLabel(status)} 저장 완료`);
  } catch (error) {
    syncUpdatedCard(previous);
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
$('filterToggleBtn').addEventListener('click', toggleFiltersPanel);
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
$('questionSessionModeSelect')?.addEventListener('change', () => {
  state.questionSessionMode = questionSessionModeValue();
  if (questionSessionIsBok(state.questionSessionMode)) applyQuestionSessionModePreset(state.questionSessionMode);
  if (!state.questions.length || state.questionSessionFinishedAt) updateQuestionSummaryLine();
  renderQuestionPanel();
});
$('generateQuestionsBtn')?.addEventListener('click', generateQuestionsFromCurrentFilter);
$('openQuestionImportBtn')?.addEventListener('click', openQuestionImportDialog);
$('questionBankToggleBtn')?.addEventListener('click', () => toggleQuestionBankBrowser());
$('questionBankRefreshBtn')?.addEventListener('click', () => loadQuestionBankBrowser().catch(() => {}));
$('questionBankLoadBtn')?.addEventListener('click', () => openQuestionBankSession(0));
$('questionBankCloseBtn')?.addEventListener('click', () => toggleQuestionBankBrowser(false));
['questionBankQueryInput', 'questionBankTopicInput', 'questionBankFieldInput', 'questionBankIssuerInput', 'questionBankSourceInput', 'questionBankDifficultySelect', 'questionBankTypeSelect', 'questionBankSectionInput'].forEach((id) => {
  $(id)?.addEventListener('change', () => loadQuestionBankBrowser().catch(() => {}));
  $(id)?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      loadQuestionBankBrowser().catch(() => {});
    }
  });
});

$('openAiQuizSearchBtn')?.addEventListener('click', openAiQuizSearch);
$('questionHistoryBtn')?.addEventListener('click', openQuestionHistory);
$('closeQuestionModeBtn')?.addEventListener('click', () => toggleQuestionMode(false));
$('finishQuestionSessionBtn')?.addEventListener('click', finishQuestionSession);
$('questionImportApplyBtn')?.addEventListener('click', importQuestionsFromText);
$('questionBankList')?.addEventListener('click', (event) => {
  const target = event.target.closest('[data-question-bank-index]');
  if (!target) return;
  const index = Number.parseInt(target.dataset.questionBankIndex || '', 10);
  if (Number.isInteger(index)) openQuestionBankSession(index);
});

$('prevQuestionBtn')?.addEventListener('click', () => moveQuestion(-1));
$('nextQuestionBtn')?.addEventListener('click', () => moveQuestion(1));
$('revealAnswerBtn')?.addEventListener('click', revealQuestionAnswer);
$('openQuestionCardBtn')?.addEventListener('click', openQuestionSourceCard);
$('questionCard')?.addEventListener('click', (event) => {
  const choice = event.target.closest('[data-choice-index]');
  if (choice) {
    selectQuestionChoice(Number.parseInt(choice.dataset.choiceIndex, 10));
    return;
  }
  const questionMark = event.target.closest('[data-question-mark]');
  if (questionMark) {
    markQuestionSourceCard(questionMark.dataset.questionMark || '');
    return;
  }
  const judgmentButton = event.target.closest('[data-question-judgment]');
  if (judgmentButton) {
    setQuestionJudgment(judgmentButton.dataset.questionJudgment || 'pending');
    return;
  }
  if (event.target.closest('[data-question-wrong-note-save="1"]')) {
    saveCurrentWrongNote();
  }
});



$('questionCard')?.addEventListener('input', (event) => {
  const question = hydrateQuestionState(currentQuestion());
  if (!question) return;
  if (event.target.matches('.question-answer-input')) {
    question.userAnswer = event.target.value || '';
    return;
  }
  if (event.target.matches('.question-wrong-note')) {
    question.wrongNote = event.target.value || '';
  }
});
$('knownBtn').addEventListener('click', () => mark('O'));
$('unknownBtn').addEventListener('click', () => mark('X'));
$('unreviewedBtn').addEventListener('click', () => mark(''));
$('bookmarkBtn').addEventListener('click', toggleBookmark);
$('copyBookmarksBtn').addEventListener('click', copyBookmarkedTerms);
$('memoSaveBtn').addEventListener('click', saveMemo);
$('conceptImageGenerateBtn')?.addEventListener('click', previewConceptImage);
$('conceptImageZoomOutBtn')?.addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  stepConceptImageScale(-CONCEPT_IMAGE_SCALE_STEP);
});
$('conceptImageZoomInBtn')?.addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  stepConceptImageScale(CONCEPT_IMAGE_SCALE_STEP);
});
$('conceptImageZoomBtn')?.addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  openConceptImageDialog();
});

[
  ['definitionAiBtn', () => previewAiRewrite('definition')],
  ['detailAiBtn', () => previewAiRewrite('detailed_explanation')],
  ['examAiBtn', () => previewAiRewrite('exam_note')],
].forEach(([id, handler]) => {
  $(id)?.addEventListener('click', handler);
});
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
$('flashcardTableBtn')?.addEventListener('click', openFlashcardTableWindow);
$('bookmarkFilterBtn').addEventListener('click', toggleBookmarkFilter);
$('questionPracticeBtn')?.addEventListener('click', openQuestionPracticeFromMenu);
$('memoListCloseBtn').addEventListener('click', closeMemoList);
$('bookmarkListCloseBtn').addEventListener('click', closeBookmarkList);
$('questionHistoryCloseBtn')?.addEventListener('click', closeQuestionHistory);
$('questionImportCloseBtn')?.addEventListener('click', closeQuestionImportDialog);
$('conceptImageDialogCloseBtn')?.addEventListener('click', () => closeConceptImageDialog());

$('memoListDialog').addEventListener('click', (event) => {
  if (event.target === $('memoListDialog')) closeMemoList();
});
$('bookmarkListDialog').addEventListener('click', (event) => {
  if (event.target === $('bookmarkListDialog')) closeBookmarkList();
});
$('questionHistoryDialog')?.addEventListener('click', (event) => {
  if (event.target === $('questionHistoryDialog')) closeQuestionHistory();
});
$('questionImportDialog')?.addEventListener('click', (event) => {
  if (event.target === $('questionImportDialog')) closeQuestionImportDialog();
});
$('conceptImageDialog')?.addEventListener('click', (event) => {
  if (event.target === $('conceptImageDialog')) closeConceptImageDialog();
});
$('questionImportInput')?.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault();
    importQuestionsFromText();
  }
});
$('memoListBody').addEventListener('click', (event) => {
  const item = event.target.closest('[data-card-id]');
  if (item) jumpToMemoCard(item.dataset.cardId);
});
$('bookmarkListBody').addEventListener('click', (event) => {
  const item = event.target.closest('[data-card-id]');
  if (item) jumpToBookmarkCard(item.dataset.cardId);
});
$('questionHistoryBody')?.addEventListener('click', (event) => {
  const trigger = event.target.closest('[data-question-history-card-id]');
  if (trigger) jumpToQuestionHistoryCard(trigger.dataset.questionHistoryCardId);
});
document.addEventListener('click', (event) => {
  if (state.menuOpen && !event.target.closest('.header-actions')) toggleMenu(false);
});
document.querySelectorAll('[data-question-history-filter]').forEach((button) => {
  button.addEventListener('click', () => setQuestionHistoryFilter(button.dataset.questionHistoryFilter));
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
  if (event.target.closest('button')) return;
  event.preventDefault();
  event.stopPropagation();
  openConceptImageDialog();
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
  if (e.key === 'Escape' && conceptImageDialogOpen()) {
    e.preventDefault();
    closeConceptImageDialog();
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
  if (key === 'o' || e.key === '.') { e.preventDefault(); markQuestionSourceCard('O'); return; }
  if (key === 'x') { e.preventDefault(); markQuestionSourceCard('X'); return; }
  if (e.key === '-') { e.preventDefault(); markQuestionSourceCard(''); return; }
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

// iOS Safari (even installed as a home-screen PWA) suspends speechSynthesis
// itself somewhere around 1-2 minutes after the screen locks, regardless of
// the background-audio keep-alive trick above -- that part is an OS policy,
// not something a web page can override. The best available mitigation is
// to notice on wake that the queue died mid-card and pick back up
// automatically instead of leaving auto-listen silently stopped.
let hiddenSinceMs = 0;
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    hiddenSinceMs = Date.now();
    if (state.audioPlaying) ensureBackgroundKeepAliveAudio().play().catch(() => {});
    return;
  }
  if (!state.audioPlaying) return;
  const wasHiddenMs = hiddenSinceMs ? Date.now() - hiddenSinceMs : 0;
  hiddenSinceMs = 0;
  window.speechSynthesis.resume?.();
  ensureBackgroundKeepAliveAudio().play().catch(() => {});
  if (wasHiddenMs < 3000) return;
  window.setTimeout(() => {
    if (!state.audioPlaying) return;
    const synth = window.speechSynthesis;
    if (synth.speaking || synth.pending) return;
    restartCurrentCardSpeech();
  }, 400);
});

applyControlsCollapsed();
applyFiltersCollapsed();
restoreAudioSettings();
renderAudioPresets();
populateSpeechVoiceSelect();
updateRandomButtons();
updateQuestionPracticeButton();

if (!bootstrapFlashcardTablePopupWindow()) {
  loadCards().catch((err) => {
    setMessage(`로딩 실패: ${err.message}`, true);
    applyFrontIllustration({term: '로딩 실패', english: '', category: ''});
    $('frontTerm').textContent = '로딩 실패';
    $('frontEnglish').textContent = err.message;
  });
}
