const QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';
const QUESTION_BANK_COLUMN_ORDER_KEY = 'csQuestionBankTableColumnOrder:v1';
const QUESTION_BANK_PRACTICE_COLLAPSED_KEY = 'csQuestionBankPracticeCollapsed:v1';
const QUESTION_TYPE_LABELS = {short: '주관식', subjective: '서술형', multiple_choice: '객관식', essay: '논술형'};
const QUESTION_BANK_COLUMNS = [
  {key: 'index', label: '#', width: '64px'},
  {key: 'prompt', label: '문제', width: '38rem', cellClassName: 'term-cell'},
  {key: 'type', label: '형식', width: '8rem'},
  {key: 'topic', label: '키워드', width: '15rem'},
  {key: 'issuer', label: '기관', width: '9rem'},
  {key: 'difficulty', label: '난이도', width: '7rem'},
  {key: 'source', label: '출처', width: '13rem'},
];
const FILTER_FIELDS = [
  {key: 'q', id: 'bankPageQueryInput', label: '통합 검색'},
  {key: 'topic', id: 'bankPageTopicInput', label: '문제유형'},
  {key: 'field_name', id: 'bankPageFieldInput', label: '분야'},
  {key: 'category', id: 'bankPageCategoryInput', label: '카테고리'},
  {key: 'issuer', id: 'bankPageIssuerInput', label: '출제기관'},
  {key: 'source_location', id: 'bankPageSourceInput', label: '출제위치'},
  {key: 'difficulty', id: 'bankPageDifficultySelect', label: '난이도'},
  {key: 'question_type', id: 'bankPageTypeSelect', label: '형식'},
  {key: 'section', id: 'bankPageSectionInput', label: '섹션'},
];
const $ = (id) => document.getElementById(id);

const bankState = {
  items: [],
  summary: null,
  loading: false,
  error: '',
  selectedId: '',
  practiceLoaded: false,
  practiceStartIndex: 0,
  practiceNonce: 0,
  practiceCollapsed: false,
};

let pendingLoadTimer = 0;

function escapeHtml(value) {
  return window.CSTableShell?.escapeHtml ? window.CSTableShell.escapeHtml(value) : String(value ?? '');
}

function markdownPreviewText(source) {
  return String(source || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/\[[^\]]*\]\([^)]*\)/g, ' ')
    .replace(/[#>*_`|~-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function normalizeQuestionKeywords(value) {
  const rawItems = Array.isArray(value) ? value : String(value || '').split(/[;,\n]/);
  const seen = new Set();
  return rawItems
    .map((item) => String(item || '').trim())
    .filter((item) => {
      if (!item) return false;
      const key = item.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function keywordCardQueryUrl(keyword) {
  const text = String(keyword || '').trim();
  if (!text || text === '한국은행' || /^20\d{2}$/.test(text) || /(학술|논술|전산)/.test(text)) return '';
  return `/?card_query=${encodeURIComponent(text)}&side=back`;
}

function renderQuestionKeywordLinks(keywords, {limit = Number.POSITIVE_INFINITY} = {}) {
  const items = normalizeQuestionKeywords(keywords);
  if (!items.length) return '—';
  const limitedItems = Number.isFinite(limit) ? items.slice(0, limit) : items;
  const parts = limitedItems.map((keyword) => {
    const url = keywordCardQueryUrl(keyword);
    const text = escapeHtml(keyword);
    return url
      ? `<a class="question-keyword-link" href="${url}" title="${text} 카드 보기">${text}</a>`
      : `<span class="question-keyword-text">${text}</span>`;
  });
  if (items.length > limitedItems.length) {
    parts.push(`<span class="question-keyword-more">+${items.length - limitedItems.length}</span>`);
  }
  return parts.join('<span class="question-keyword-sep"> · </span>');
}

function questionTypeLabel(item) {
  return QUESTION_TYPE_LABELS[String(item?.question_type || '').trim()] || String(item?.question_type || '문제');
}

function selectedIndex(fallback = 0) {
  const found = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === bankState.selectedId);
  return found >= 0 ? found : Math.max(0, Math.min(bankState.items.length - 1, fallback));
}

function selectedItem() {
  if (!bankState.items.length) return null;
  return bankState.items[selectedIndex(bankState.practiceStartIndex)] || bankState.items[0] || null;
}

function practiceFrameUrl() {
  return `/?question-bank-embed=1&question-bank-run=${Date.now()}-${bankState.practiceNonce}`;
}

function persistedPracticeCollapsed() {
  try {
    return window.localStorage.getItem(QUESTION_BANK_PRACTICE_COLLAPSED_KEY) === '1';
  } catch (_error) {
    return false;
  }
}

function pillTone(prefix, rawValue) {
  const value = String(rawValue || '').trim();
  if (!value) return `${prefix}-default`;
  if (prefix === 'difficulty') {
    if (value === '상') return 'difficulty-high';
    if (value === '중') return 'difficulty-mid';
    if (value === '하') return 'difficulty-low';
  }
  if (prefix === 'type') {
    if (value === 'short') return 'type-short';
    if (value === 'subjective') return 'type-subjective';
    if (value === 'multiple_choice') return 'type-multiple-choice';
    if (value === 'essay') return 'type-essay';
  }
  return `${prefix}-default`;
}

function metricCard(label, value, detail, tone = '') {
  return `<article class="question-bank-metric-card${tone ? ` ${tone}` : ''}"><span class="question-bank-metric-label">${escapeHtml(label)}</span><strong class="question-bank-metric-value">${escapeHtml(value)}</strong><p class="question-bank-metric-detail">${escapeHtml(detail)}</p></article>`;
}

function summaryBits(item) {
  if (!item) return [];
  const bits = [];
  const typeLabel = questionTypeLabel(item);
  if (typeLabel) bits.push(`<span class="question-bank-summary-pill ${pillTone('type', item.question_type)}">${escapeHtml(typeLabel)}</span>`);
  if (item?.difficulty) bits.push(`<span class="question-bank-summary-pill ${pillTone('difficulty', item.difficulty)}">난이도 ${escapeHtml(item.difficulty)}</span>`);
  if (item?.issuer) bits.push(`<span class="question-bank-summary-pill">${escapeHtml(item.issuer)}</span>`);
  if (item?.source_location) bits.push(`<span class="question-bank-summary-pill">${escapeHtml(item.source_location)}</span>`);
  return bits;
}

function selectedPrompt(item, fallback = '문제를 선택하세요.') {
  return markdownPreviewText(item?.prompt || '').slice(0, 110) || fallback;
}

function activeFilterEntries() {
  const values = filterValues();
  return FILTER_FIELDS.map((field) => ({...field, value: String(values[field.key] || '').trim()})).filter((field) => field.value);
}

function fieldByKey(key) {
  return FILTER_FIELDS.find((field) => field.key === key) || null;
}

function setFilterValue(key, value = '') {
  const field = fieldByKey(key);
  if (!field) return;
  const node = $(field.id);
  if (!node) return;
  node.value = value;
}

function clearFilterField(key) {
  setFilterValue(key, '');
  loadQuestionBankPage().catch(() => {});
}

function renderPracticeToggle() {
  const toggleButton = $('bankPageTogglePracticeBtn');
  if (!toggleButton) return;
  const expanded = !bankState.practiceCollapsed;
  toggleButton.textContent = expanded ? '풀이 패널 숨기기' : '풀이 패널 보기';
  toggleButton.setAttribute('aria-expanded', String(expanded));
}

function setPracticeCollapsed(collapsed, {persist = true} = {}) {
  bankState.practiceCollapsed = Boolean(collapsed);
  document.body.classList.toggle('question-bank-practice-collapsed', bankState.practiceCollapsed);
  renderPracticeToggle();
  renderOverviewCards();
  renderHeader();
  if (!persist) return;
  try {
    window.localStorage.setItem(QUESTION_BANK_PRACTICE_COLLAPSED_KEY, bankState.practiceCollapsed ? '1' : '0');
  } catch (_error) {
    // Ignore storage failures.
  }
}

function togglePracticeCollapsed() {
  setPracticeCollapsed(!bankState.practiceCollapsed);
}

function filterValues() {
  return {
    q: $('bankPageQueryInput')?.value?.trim() || '',
    topic: $('bankPageTopicInput')?.value?.trim() || '',
    field_name: $('bankPageFieldInput')?.value?.trim() || '',
    category: $('bankPageCategoryInput')?.value?.trim() || '',
    issuer: $('bankPageIssuerInput')?.value?.trim() || '',
    source_location: $('bankPageSourceInput')?.value?.trim() || '',
    difficulty: $('bankPageDifficultySelect')?.value || '',
    question_type: $('bankPageTypeSelect')?.value || '',
    section: $('bankPageSectionInput')?.value?.trim() || '',
  };
}

function applyFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  if ($('bankPageQueryInput')) $('bankPageQueryInput').value = params.get('q') || '';
  if ($('bankPageTopicInput')) $('bankPageTopicInput').value = params.get('topic') || '';
  if ($('bankPageFieldInput')) $('bankPageFieldInput').value = params.get('field_name') || '';
  if ($('bankPageCategoryInput')) $('bankPageCategoryInput').value = params.get('category') || params.get('card_category') || '';
  if ($('bankPageIssuerInput')) $('bankPageIssuerInput').value = params.get('issuer') || '';
  if ($('bankPageSourceInput')) $('bankPageSourceInput').value = params.get('source_location') || '';
  if ($('bankPageDifficultySelect')) $('bankPageDifficultySelect').value = params.get('difficulty') || '';
  if ($('bankPageTypeSelect')) $('bankPageTypeSelect').value = params.get('question_type') || '';
  if ($('bankPageSectionInput')) $('bankPageSectionInput').value = params.get('section') || '';
}

function populateIssuerOptions(issuers, selected = '') {
  const select = $('bankPageIssuerInput');
  if (!select) return;
  const selectedValue = String(selected || select.value || new URLSearchParams(window.location.search).get('issuer') || '').trim();
  const options = ['<option value="">출제기관 *</option>'];
  (Array.isArray(issuers) ? issuers : []).forEach((issuer) => {
    const value = String(issuer || '').trim();
    if (!value) return;
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
  });
  select.innerHTML = options.join('');
  select.value = (Array.isArray(issuers) && issuers.includes(selectedValue)) ? selectedValue : '';
}

function populateCategoryOptions(categories, selected = '') {
  const select = $('bankPageCategoryInput');
  if (!select) return;
  const selectedValue = String(selected || select.value || new URLSearchParams(window.location.search).get('category') || '').trim();
  const options = ['<option value="">카테고리 *</option>'];
  (Array.isArray(categories) ? categories : []).forEach((category) => {
    const value = String(category || '').trim();
    if (!value) return;
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
  });
  select.innerHTML = options.join('');
  select.value = (Array.isArray(categories) && categories.includes(selectedValue)) ? selectedValue : '';
}

function queryString() {
  const params = new URLSearchParams();
  Object.entries(filterValues()).forEach(([key, value]) => {
    if (!value) return;
    params.set(key, value);
  });
  params.set('limit', '200');
  return params.toString();
}

function syncUrl() {
  const qs = queryString();
  const next = qs ? `/question-bank?${qs}` : '/question-bank';
  if (`${window.location.pathname}${window.location.search}` !== next) {
    window.history.replaceState({}, '', next);
  }
}

async function fetchEntries() {
  const qs = queryString();
  const res = await fetch(`/api/question-bank${qs ? `?${qs}` : ''}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function resetFilters() {
  FILTER_FIELDS.forEach(({key}) => setFilterValue(key, ''));
  loadQuestionBankPage().catch(() => {});
}

function scheduleLoad() {
  window.clearTimeout(pendingLoadTimer);
  pendingLoadTimer = window.setTimeout(() => {
    loadQuestionBankPage().catch(() => {});
  }, 220);
}

function bindHeaderChipActions() {
  const toggle = $('bankPageHeaderPracticeToggle');
  if (!toggle) return;
  toggle.addEventListener('click', togglePracticeCollapsed);
}

function renderHeader() {
  const summary = $('bankPageHeaderSummary');
  const chips = $('bankPageHeaderChips');
  const total = Number(bankState.summary?.total || 0);
  const returned = Number(bankState.summary?.returned || bankState.items.length || 0);
  const filterCount = activeFilterEntries().length;
  const item = selectedItem();
  if (summary) {
    if (bankState.loading) {
      summary.textContent = '문제은행과 풀이 흐름을 정리하는 중입니다.';
    } else if (!bankState.items.length) {
      summary.textContent = bankState.error ? '조회 조건을 확인하고 다시 불러오세요.' : '조건에 맞는 문제를 찾지 못했습니다.';
    } else {
      summary.textContent = `총 ${total}문항 중 ${returned}문항을 보고 있고, ${selectedIndex(bankState.practiceStartIndex) + 1}번 문제부터 바로 이어서 풀 수 있습니다.`;
    }
  }
  if (chips) {
    const practiceLabel = bankState.practiceCollapsed ? '풀이 패널 보기' : '풀이 패널 숨기기';
    chips.innerHTML = [
      `<span class="question-bank-header-chip">표시 ${escapeHtml(String(returned || 0))}</span>`,
      `<span class="question-bank-header-chip">필터 ${escapeHtml(String(filterCount))}</span>`,
      `<button type="button" id="bankPageHeaderPracticeToggle" class="question-bank-header-chip question-bank-header-chip-button${bankState.practiceCollapsed ? ' is-collapsed' : ''}">${escapeHtml(practiceLabel)}</button>`,
      item ? `<span class="question-bank-header-chip question-bank-header-chip-strong">선택 ${escapeHtml(`${selectedIndex(bankState.practiceStartIndex) + 1}번`)}</span>` : '',
    ].join('');
    bindHeaderChipActions();
  }
}


function renderOverviewCards() {
  const mount = $('bankPageOverviewCards');
  if (!mount) return;
  const total = Number(bankState.summary?.total || 0);
  const returned = Number(bankState.summary?.returned || bankState.items.length || 0);
  const filterCount = activeFilterEntries().length;
  const item = selectedItem();
  const selectedLabel = item ? `${selectedIndex(bankState.practiceStartIndex) + 1}번` : '없음';
  const practiceState = bankState.practiceCollapsed ? '숨김' : (bankState.practiceLoaded ? '연결됨' : '대기');
  mount.innerHTML = [
    metricCard('표시 목록', `${returned}문항`, total ? `전체 ${total}문항 중 현재 보이는 범위` : '목록을 불러오고 있습니다.', 'is-primary'),
    metricCard('현재 선택', selectedLabel, item ? '아래 현재 선택 카드에서 문제 요약과 시작 지점을 바로 확인합니다.' : '문제를 고르면 바로 선택 상태가 연결됩니다.'),
    metricCard('적용 필터', `${filterCount}개`, filterCount ? '활성 필터 칩을 눌러 개별 조건을 바로 제거할 수 있습니다.' : '지금은 전체 흐름을 넓게 훑는 상태입니다.'),
    metricCard('풀이 패널', practiceState, bankState.practiceCollapsed ? '표에 집중하도록 오른쪽 패널을 접어 둔 상태입니다.' : '오른쪽에서 같은 문제 세트를 이어서 풉니다.'),
  ].join('');
}

function bindActiveFilterChipActions() {
  const mount = $('bankPageActiveFilters');
  if (!mount) return;
  mount.querySelectorAll('[data-filter-key]').forEach((button) => {
    button.addEventListener('click', () => clearFilterField(button.dataset.filterKey || ''));
  });
}

function renderActiveFilters() {
  const mount = $('bankPageActiveFilters');
  if (!mount) return;
  const entries = activeFilterEntries();
  if (!entries.length) {
    mount.innerHTML = '<span class="question-bank-filter-empty">필터 없이 전체 흐름을 보고 있습니다.</span>';
    return;
  }
  mount.innerHTML = entries.map((entry) => {
    const displayValue = entry.key === 'question_type'
      ? (QUESTION_TYPE_LABELS[entry.value] || entry.value)
      : entry.value;
    return `<button type="button" class="question-bank-filter-chip" data-filter-key="${escapeHtml(entry.key)}" aria-label="${escapeHtml(entry.label)} 필터 제거"><strong>${escapeHtml(entry.label)}</strong><span>${escapeHtml(displayValue)}</span><span class="question-bank-filter-chip-remove">지우기</span></button>`;
  }).join('');
  bindActiveFilterChipActions();
}

function renderSelectionSummary() {
  const mount = $('bankPageSelectionSummary');
  if (!mount) return;
  const item = selectedItem();
  if (!item) {
    mount.innerHTML = '<div class="question-bank-selection-empty">문제를 불러오면 여기에서 현재 선택과 풀이 시작점을 요약합니다.</div>';
    return;
  }
  const preview = markdownPreviewText(item.body || item.answer || item.explanation || '').slice(0, 140);
  const keywords = renderQuestionKeywordLinks(item.keywords, {limit: 5});
  mount.innerHTML = `
    <article class="question-bank-selection-card-body">
      <div class="question-bank-selection-copy">
        <p class="question-bank-selection-index">현재 ${escapeHtml(String(selectedIndex(bankState.practiceStartIndex) + 1))}번 · ${escapeHtml(String(bankState.items.length))}문항 중</p>
        <h3 class="question-bank-selection-title">${escapeHtml(selectedPrompt(item, '선택된 문제가 없습니다.'))}</h3>
        <p class="question-bank-selection-preview">${escapeHtml(preview || '본문 미리보기가 없어서 문제 제목 중심으로 풀이를 시작합니다.')}</p>
      </div>
      <div class="question-bank-selection-meta">${summaryBits(item).join('')}</div>
      <div class="question-bank-selection-keywords">${keywords === '—' ? '<span class="question-bank-selection-keywords-empty">연결 키워드가 없습니다.</span>' : keywords}</div>
    </article>
  `;
}

function tableRows() {
  return bankState.items.map((item, index) => {
    const active = bankState.selectedId && bankState.selectedId === String(item.question_bank_id || '');
    const prompt = escapeHtml(markdownPreviewText(item.prompt || `문제 ${index + 1}`) || `문제 ${index + 1}`);
    const typeLabel = questionTypeLabel(item);
    const topic = renderQuestionKeywordLinks(item.keywords, {limit: 4});
    const issuer = escapeHtml(item.issuer || '—');
    const difficulty = escapeHtml(item.difficulty || '—');
    const source = escapeHtml(item.source_location || '—');
    const preview = markdownPreviewText(item.body || item.answer || item.explanation || '').slice(0, 96);
    return {
      id: String(item.question_bank_id || index + 1),
      className: active ? 'current-row active' : '',
      attributes: {'aria-current': active ? 'true' : 'false'},
      cells: {
        index: `<span class="question-bank-row-number">${index + 1}</span>`,
        prompt: `<div class="question-bank-row-trigger"><span class="question-bank-item-title">${prompt}</span>${preview ? `<span class="question-bank-item-preview">${escapeHtml(preview)}</span>` : ''}</div>`,
        type: `<span class="question-bank-type-pill ${pillTone('type', item.question_type)}">${escapeHtml(typeLabel || '문제')}</span>`,
        topic: `<div class="question-bank-keyword-list">${topic}</div>`,
        issuer,
        difficulty: `<span class="question-bank-difficulty-pill ${pillTone('difficulty', item.difficulty)}">${difficulty}</span>`,
        source,
      },
    };
  });
}

function renderPracticePane() {
  const summary = $('bankPagePracticeSummary');
  const status = $('bankPagePracticeStatus');
  const placeholder = $('bankPagePracticePlaceholder');
  const frame = $('bankPagePracticeFrame');
  const item = selectedItem();
  if (!summary || !status || !placeholder || !frame) return;
  if (!bankState.items.length) {
    summary.textContent = bankState.loading ? '문제은행 목록을 불러온 뒤 오른쪽에 문제 풀이를 연결합니다.' : '표에 표시할 문제가 없습니다.';
    status.innerHTML = '<span class="question-bank-practice-empty">목록이 준비되면 여기서 바로 풀이를 시작합니다.</span>';
    placeholder.textContent = bankState.loading ? '문제 목록을 불러오는 중입니다.' : '현재 조건에 맞는 문제은행 항목이 없습니다.';
    placeholder.hidden = false;
    frame.hidden = true;
    return;
  }
  const start = selectedIndex(bankState.practiceStartIndex);
  const prompt = selectedPrompt(item, `문제 ${start + 1}`).slice(0, 64);
  summary.textContent = bankState.practiceLoaded
    ? `현재 목록 ${bankState.items.length}문항 · ${start + 1}번부터 풀이 중 · ${prompt}`
    : `현재 목록 ${bankState.items.length}문항 · 선택한 문제부터 오른쪽에서 이어서 풉니다.`;
  status.innerHTML = [
    `<span class="question-bank-practice-pill">현재 ${escapeHtml(`${start + 1} / ${bankState.items.length}`)}</span>`,
    ...summaryBits(item),
  ].join('');
  placeholder.textContent = `선택된 ${start + 1}번 문제부터 현재 목록 전체를 오른쪽에서 이어서 풀 수 있습니다.`;
  placeholder.hidden = bankState.practiceLoaded;
  frame.hidden = !bankState.practiceLoaded;
}

function renderTable() {
  const summary = $('bankPageSummary');
  const mount = $('bankPageList');
  const error = $('bankPageError');
  if (!summary || !mount || !error || !window.CSTableShell) return;
  const total = Number(bankState.summary?.total || 0);
  const returned = Number(bankState.summary?.returned || bankState.items.length || 0);
  const filterCount = activeFilterEntries().length;
  const practiceText = bankState.practiceCollapsed ? '풀이 패널은 접혀 있고 표에 집중하는 상태입니다.' : '오른쪽 풀이 패널과 같은 세트가 연결되어 있습니다.';
  summary.textContent = bankState.loading
    ? '문제은행을 불러오는 중입니다.'
    : `총 ${total}문항 · 현재 ${returned}문항 · 필터 ${filterCount}개 · ${practiceText}`;
  error.textContent = bankState.error || '';
  renderHeader();
  renderOverviewCards();
  renderActiveFilters();
  renderSelectionSummary();
  window.CSTableShell.renderTable(mount, {
    columns: QUESTION_BANK_COLUMNS,
    rows: tableRows(),
    storageKey: QUESTION_BANK_COLUMN_ORDER_KEY,
    tableMinWidth: '1180px',
    emptyText: '조건에 맞는 문제가 없습니다.',
    onRowActivate: (_row, index) => {
      bankState.selectedId = String(bankState.items[index]?.question_bank_id || '');
      bankState.practiceStartIndex = index;
      renderTable();
      renderPracticePane();
      launch(index);
    },
    onColumnMove: (sourceKey, targetKey) => {
      window.CSTableShell.moveColumnOrder(QUESTION_BANK_COLUMN_ORDER_KEY, QUESTION_BANK_COLUMNS.map((column) => column.key), sourceKey, targetKey);
      renderTable();
    },
  });
}

function ensureSelectedRowVisible() {
  const row = document.querySelector('#bankPageList [aria-current="true"]');
  if (!row || typeof row.scrollIntoView !== 'function') return;
  row.scrollIntoView({block: 'nearest', inline: 'nearest'});
}


function launch(startIndex = 0, {reveal = true} = {}) {
  if (!bankState.items.length) {
    bankState.error = '문제은행 목록이 비어 있습니다.';
    renderTable();
    renderPracticePane();
    return;
  }
  const safeStart = selectedIndex(startIndex);
  const frame = $('bankPagePracticeFrame');
  bankState.selectedId = String(bankState.items[safeStart]?.question_bank_id || '');
  bankState.practiceLoaded = true;
  bankState.practiceStartIndex = safeStart;
  if (reveal) setPracticeCollapsed(false);
  renderTable();
  renderPracticePane();
  ensureSelectedRowVisible();
  try {
    window.sessionStorage.setItem(QUESTION_BANK_LAUNCH_KEY, JSON.stringify({
      items: bankState.items,
      startIndex: safeStart,
    }));
  } catch (error) {
    bankState.error = error.message || String(error);
    renderTable();
    renderPracticePane();
    return;
  }
  bankState.practiceNonce += 1;
  if (frame) frame.src = practiceFrameUrl();
}

async function loadQuestionBankPage() {
  bankState.loading = true;
  bankState.error = '';
  syncUrl();
  renderTable();
  renderPracticePane();
  try {
    const data = await fetchEntries();
    const previousSelectedId = bankState.selectedId;
    bankState.items = Array.isArray(data.items) ? data.items : [];
    bankState.summary = data.summary || {total: bankState.items.length, returned: bankState.items.length};
    populateIssuerOptions(bankState.summary?.available_issuers || [], filterValues().issuer);
    populateCategoryOptions(bankState.summary?.available_categories || [], filterValues().category);

    const nextIndex = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === previousSelectedId);
    bankState.selectedId = String(bankState.items[nextIndex >= 0 ? nextIndex : 0]?.question_bank_id || '');
    bankState.practiceStartIndex = nextIndex >= 0 ? nextIndex : 0;
    if (!bankState.items.length) bankState.practiceLoaded = false;
  } catch (error) {
    bankState.items = [];
    bankState.summary = {total: 0, returned: 0};
    populateIssuerOptions([], filterValues().issuer);
    populateCategoryOptions([], filterValues().category);
    bankState.error = error.message || String(error);
    bankState.practiceLoaded = false;
  } finally {
    bankState.loading = false;
    renderTable();
    renderPracticePane();
    if (bankState.items.length) launch(selectedIndex(bankState.practiceStartIndex), {reveal: false});
  }
}

applyFiltersFromUrl();
setPracticeCollapsed(persistedPracticeCollapsed(), {persist: false});
renderTable();
renderPracticePane();
loadQuestionBankPage().catch(() => {});

$('bankPageRefreshBtn')?.addEventListener('click', () => loadQuestionBankPage().catch(() => {}));
$('bankPageLaunchBtn')?.addEventListener('click', () => launch(0));
$('bankPageLaunchSelectedBtn')?.addEventListener('click', () => launch(selectedIndex(bankState.practiceStartIndex)));
$('bankPageTogglePracticeBtn')?.addEventListener('click', togglePracticeCollapsed);
$('bankPageResetFiltersBtn')?.addEventListener('click', resetFilters);

['bankPageQueryInput', 'bankPageTopicInput', 'bankPageFieldInput', 'bankPageSourceInput', 'bankPageSectionInput'].forEach((id) => {
  $(id)?.addEventListener('input', scheduleLoad);
  $(id)?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      window.clearTimeout(pendingLoadTimer);
      loadQuestionBankPage().catch(() => {});
    }
  });
});

['bankPageCategoryInput', 'bankPageIssuerInput', 'bankPageDifficultySelect', 'bankPageTypeSelect'].forEach((id) => {
  $(id)?.addEventListener('change', () => loadQuestionBankPage().catch(() => {}));
});
