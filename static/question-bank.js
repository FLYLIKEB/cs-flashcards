const QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';
const QUESTION_BANK_COLUMN_ORDER_KEY = 'csQuestionBankTableColumnOrder:v1';
const QUESTION_BANK_PRACTICE_COLLAPSED_KEY = 'csQuestionBankPracticeCollapsed:v1';
const QUESTION_TYPE_LABELS = {short: '주관식', subjective: '서술형', multiple_choice: '객관식', essay: '논술형'};
const QUESTION_BANK_ATTEMPT_STATUS_LABELS = {unseen: '안푼', wrong: '틀린', correct: '맞은'};
const QUESTION_BANK_COLUMNS = [
  {key: 'index', label: '#', width: '56px'},
  {key: 'prompt', label: '문제', width: '24rem', cellClassName: 'term-cell'},
  {key: 'type', label: '형식', width: '6rem'},
  {key: 'topic', label: '키워드', width: '8.5rem'},
  {key: 'issuer', label: '기관', width: '6.25rem'},
  {key: 'difficulty', label: '난이도', width: '5rem'},
  {key: 'source', label: '출처', width: '7rem'},
];
const FILTER_FIELDS = [
  {key: 'q', id: 'bankPageQueryInput', label: '통합 검색'},
  {key: 'attempt_status', id: 'bankPageAttemptStatusSelect', label: '풀이상태'},
  {key: 'topic', id: 'bankPageTopicInput', label: '문제유형 검색'},
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
  practiceCollapsed: true,
  filtersCollapsed: true,
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
  if (items.length > limitedItems.length) parts.push(`<span class="question-keyword-more">+${items.length - limitedItems.length}</span>`);
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
  return true;
}

function persistedFiltersCollapsed() {
  return true;
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

function metricCard(label, value, detail = '', tone = '') {
  return `<article class="question-bank-metric-card${tone ? ` ${tone}` : ''}"><span class="question-bank-metric-label">${escapeHtml(label)}</span><strong class="question-bank-metric-value">${escapeHtml(value)}</strong>${detail ? `<p class="question-bank-metric-detail">${escapeHtml(detail)}</p>` : ''}</article>`;
}

function summaryBits(item) {
  if (!item) return [];
  const bits = [];
  const typeLabel = questionTypeLabel(item);
  if (typeLabel) bits.push(`<span class="question-bank-summary-pill ${pillTone('type', item.question_type)}">${escapeHtml(typeLabel)}</span>`);
  if (item?.difficulty) bits.push(`<span class="question-bank-summary-pill ${pillTone('difficulty', item.difficulty)}">난이도 ${escapeHtml(item.difficulty)}</span>`);
  if (item?.issuer) bits.push(`<span class="question-bank-summary-pill">${escapeHtml(item.issuer)}</span>`);
  return bits;
}

function selectedPrompt(item, fallback = '문제를 선택하세요.') {
  return markdownPreviewText(item?.prompt || '').slice(0, 120) || fallback;
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
  if (node) node.value = value;
}

function clearFilterField(key) {
  setFilterValue(key, '');
  loadQuestionBankPage().catch(() => {});
}

function applyPracticeViewState() {
  const practiceFocus = bankState.practiceLoaded && !bankState.practiceCollapsed;
  document.body.classList.toggle('question-bank-practice-collapsed', !practiceFocus);
  document.body.classList.toggle('question-bank-practice-focus', practiceFocus);
}

function applyFilterViewState() {
  document.body.classList.toggle('question-bank-filters-collapsed', bankState.filtersCollapsed);
}

function renderFilterToggle() {
  const toggleButton = $('bankPageToggleFiltersBtn');
  if (!toggleButton) return;
  const count = activeFilterEntries().length;
  toggleButton.textContent = bankState.filtersCollapsed
    ? `필터 열기${count ? ` (${count})` : ''}`
    : '필터 숨기기';
  toggleButton.setAttribute('aria-expanded', String(!bankState.filtersCollapsed));
}

function setFiltersCollapsed(collapsed) {
  bankState.filtersCollapsed = Boolean(collapsed);
  applyFilterViewState();
  renderFilterToggle();
}

function toggleFiltersCollapsed() {
  setFiltersCollapsed(!bankState.filtersCollapsed);
}

function renderPracticeToggle() {
  const toggleButton = $('bankPageTogglePracticeBtn');
  if (!toggleButton) return;
  const showingPractice = bankState.practiceLoaded && !bankState.practiceCollapsed;
  toggleButton.textContent = showingPractice ? '문제은행 보기' : '문제 풀이 보기';
  toggleButton.setAttribute('aria-expanded', String(showingPractice));
  toggleButton.disabled = !bankState.practiceLoaded;
}

function setPracticeCollapsed(collapsed, {persist = true} = {}) {
  bankState.practiceCollapsed = Boolean(collapsed);
  applyPracticeViewState();
  renderPracticeToggle();
  renderOverviewCards();
  renderHeader();
  if (bankState.practiceCollapsed) ensureSelectedRowVisible();
  if (!persist) return;
  try {
    window.localStorage.setItem(QUESTION_BANK_PRACTICE_COLLAPSED_KEY, bankState.practiceCollapsed ? '1' : '0');
  } catch (_error) {
    // Ignore storage failures.
  }
}

function togglePracticeCollapsed() {
  if (!bankState.practiceLoaded) return;
  setPracticeCollapsed(!bankState.practiceCollapsed);
}

function filterValues() {
  return {
    q: $('bankPageQueryInput')?.value?.trim() || '',
    attempt_status: $('bankPageAttemptStatusSelect')?.value || '',
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
  if ($('bankPageAttemptStatusSelect')) $('bankPageAttemptStatusSelect').value = params.get('attempt_status') || params.get('status') || '';
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
  const options = ['<option value="">출제기관</option>'];
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
  const options = ['<option value="">카테고리</option>'];
  (Array.isArray(categories) ? categories : []).forEach((category) => {
    const value = String(category || '').trim();
    if (!value) return;
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
  });
  select.innerHTML = options.join('');
  select.value = (Array.isArray(categories) && categories.includes(selectedValue)) ? selectedValue : '';
}

function populateTopicOptions(topics, selected = '') {
  const input = $('bankPageTopicInput');
  const datalist = $('bankPageTopicOptions');
  if (!input || !datalist) return;
  const selectedValue = String(selected || input.value || new URLSearchParams(window.location.search).get('topic') || '').trim();
  datalist.innerHTML = (Array.isArray(topics) ? topics : [])
    .map((topic) => String(topic || '').trim())
    .filter(Boolean)
    .map((topic) => `<option value="${escapeHtml(topic)}"></option>`)
    .join('');
  input.value = selectedValue;
}


function populateFieldNameOptions(fieldNames, selected = '') {
  const select = $('bankPageFieldInput');
  if (!select) return;
  const selectedValue = String(selected || select.value || new URLSearchParams(window.location.search).get('field_name') || '').trim();
  const options = ['<option value="">분야</option>'];
  (Array.isArray(fieldNames) ? fieldNames : []).forEach((fieldName) => {
    const value = String(fieldName || '').trim();
    if (!value) return;
    options.push(`<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`);
  });
  select.innerHTML = options.join('');
  select.value = (Array.isArray(fieldNames) && fieldNames.includes(selectedValue)) ? selectedValue : '';
}

function queryString() {
  const params = new URLSearchParams();
  Object.entries(filterValues()).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  params.set('limit', '200');
  return params.toString();
}

function syncUrl() {
  const qs = queryString();
  const next = qs ? `/question-bank?${qs}` : '/question-bank';
  if (`${window.location.pathname}${window.location.search}` !== next) window.history.replaceState({}, '', next);
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
  }, 180);
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
  const current = selectedIndex(bankState.practiceStartIndex) + 1;
  const showingPractice = bankState.practiceLoaded && !bankState.practiceCollapsed;
  if (summary) {
    if (bankState.loading) {
      summary.textContent = '문제은행을 정리하는 중입니다.';
    } else if (!bankState.items.length) {
      summary.textContent = bankState.error ? '조회 조건을 확인하고 다시 불러오세요.' : '조건에 맞는 문제를 찾지 못했습니다.';
    } else if (showingPractice) {
      summary.textContent = `${current}번 문제 풀이 화면`;
    } else {
      summary.textContent = `총 ${total}문항 · 현재 ${returned}문항 · 선택 문제 바로 풀이`;
    }
  }
  if (!chips) return;
  const practiceChip = bankState.practiceLoaded
    ? `<button type="button" id="bankPageHeaderPracticeToggle" class="question-bank-header-chip question-bank-header-chip-button${showingPractice ? ' is-active' : ''}">${showingPractice ? '문제은행 보기' : '문제 풀이 보기'}</button>`
    : '<span class="question-bank-header-chip">문제 풀이 대기</span>';
  chips.innerHTML = showingPractice
    ? [
        practiceChip,
        bankState.items.length ? `<span class="question-bank-header-chip question-bank-header-chip-strong">선택 ${escapeHtml(`${current}번`)}</span>` : '',
      ].join('')
    : [
        `<span class="question-bank-header-chip">표시 ${escapeHtml(String(returned || 0))}</span>`,
        `<span class="question-bank-header-chip">필터 ${escapeHtml(String(filterCount))}</span>`,
        practiceChip,
        bankState.items.length ? `<span class="question-bank-header-chip question-bank-header-chip-strong">선택 ${escapeHtml(`${current}번`)}</span>` : '',
      ].join('');
  bindHeaderChipActions();
}

function renderOverviewCards() {
  const mount = $('bankPageOverviewCards');
  if (!mount) return;
  const total = Number(bankState.summary?.total || 0);
  const returned = Number(bankState.summary?.returned || bankState.items.length || 0);
  const filterCount = activeFilterEntries().length;
  const selectedLabel = bankState.items.length ? `${selectedIndex(bankState.practiceStartIndex) + 1}번` : '없음';
  const practiceState = bankState.practiceLoaded ? (bankState.practiceCollapsed ? '대기' : '풀이 중') : '미시작';
  mount.innerHTML = [
    metricCard('표시', `${returned}${total ? ` / ${total}` : ''}`),
    metricCard('선택', selectedLabel),
    metricCard('필터', filterCount ? `${filterCount}개` : '숨김'),
    metricCard('풀이', practiceState),
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
    mount.innerHTML = '<span class="question-bank-filter-empty">필터 없음</span>';
    renderFilterToggle();
    return;
  }
  mount.innerHTML = entries.map((entry) => {
    const displayValue = entry.key === 'question_type'
      ? (QUESTION_TYPE_LABELS[entry.value] || entry.value)
      : entry.key === 'attempt_status'
        ? (QUESTION_BANK_ATTEMPT_STATUS_LABELS[entry.value] || entry.value)
        : entry.value;
    return `<button type="button" class="question-bank-filter-chip" data-filter-key="${escapeHtml(entry.key)}" aria-label="${escapeHtml(entry.label)} 필터 제거"><strong>${escapeHtml(entry.label)}</strong><span>${escapeHtml(displayValue)}</span><span class="question-bank-filter-chip-remove">×</span></button>`;
  }).join('');

  bindActiveFilterChipActions();
  renderFilterToggle();
}

function renderSelectionSummary() {
  const mount = $('bankPageSelectionSummary');
  if (!mount) return;
  const item = selectedItem();
  if (!item) {
    mount.innerHTML = '<div class="question-bank-selection-empty">표에서 문제를 고르면 바로 이어서 풀 수 있습니다.</div>';
    return;
  }
  const keywords = renderQuestionKeywordLinks(item.keywords, {limit: 2});
  mount.innerHTML = `
    <article class="question-bank-selection-card-body">
      <div class="question-bank-selection-copy">
        <p class="question-bank-selection-index">선택 ${escapeHtml(String(selectedIndex(bankState.practiceStartIndex) + 1))} / ${escapeHtml(String(bankState.items.length))}</p>
        <h3 class="question-bank-selection-title">${escapeHtml(selectedPrompt(item, '선택된 문제가 없습니다.'))}</h3>
      </div>
      <div class="question-bank-selection-meta">${summaryBits(item).join('')}</div>
      ${keywords === '—' ? '' : `<div class="question-bank-selection-keywords">${keywords}</div>`}
    </article>
  `;
}

function tableRows() {
  return bankState.items.map((item, index) => {
    const active = bankState.selectedId && bankState.selectedId === String(item.question_bank_id || '');
    const prompt = escapeHtml(markdownPreviewText(item.prompt || `문제 ${index + 1}`) || `문제 ${index + 1}`);
    const preview = markdownPreviewText(item.body || item.answer || item.explanation || '').slice(0, 44);
    return {
      id: String(item.question_bank_id || index + 1),
      className: active ? 'current-row active' : '',
      attributes: {'aria-current': active ? 'true' : 'false'},
      cells: {
        index: `<span class="question-bank-row-number">${index + 1}</span>`,
        prompt: `<div class="question-bank-row-trigger"><span class="question-bank-item-title">${prompt}</span>${preview ? `<span class="question-bank-item-preview">${escapeHtml(preview)}</span>` : ''}</div>`,
        type: `<span class="question-bank-type-pill ${pillTone('type', item.question_type)}">${escapeHtml(questionTypeLabel(item) || '문제')}</span>`,
        topic: `<div class="question-bank-keyword-list">${renderQuestionKeywordLinks(item.keywords, {limit: 2})}</div>`,
        issuer: `<span class="question-bank-issuer-text">${escapeHtml(item.issuer || '—')}</span>`,
        difficulty: `<span class="question-bank-difficulty-pill ${pillTone('difficulty', item.difficulty)}">${escapeHtml(item.difficulty || '—')}</span>`,
        source: `<span class="question-bank-source-text">${escapeHtml(item.source_location || '—')}</span>`,
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
    summary.textContent = bankState.loading ? '문제은행 목록을 불러온 뒤 시험형 풀이 화면을 준비합니다.' : '표시할 문제가 없습니다.';
    status.innerHTML = '<span class="question-bank-practice-empty">문제를 고르면 실전형 풀이 화면으로 전환됩니다.</span>';
    placeholder.textContent = bankState.loading ? '문제 목록을 불러오는 중입니다.' : '현재 조건에 맞는 문제은행 항목이 없습니다.';
    placeholder.hidden = false;
    frame.hidden = true;
    applyPracticeViewState();
    return;
  }
  const start = selectedIndex(bankState.practiceStartIndex);
  summary.textContent = `현재 목록 ${bankState.items.length}문항 · ${start + 1}번부터 풀이 중 · ${selectedPrompt(item, `문제 ${start + 1}`).slice(0, 58)}`;
  status.innerHTML = [
    `<span class="question-bank-practice-pill">현재 ${escapeHtml(`${start + 1} / ${bankState.items.length}`)}</span>`,
    ...summaryBits(item),
  ].join('');
  placeholder.textContent = '문제를 선택하면 문제은행은 숨기고 풀이 화면만 보이도록 전환합니다.';
  placeholder.hidden = bankState.practiceLoaded;
  frame.hidden = !bankState.practiceLoaded;
  applyPracticeViewState();
}

function renderTable() {
  const summary = $('bankPageSummary');
  const mount = $('bankPageList');
  const error = $('bankPageError');
  if (!summary || !mount || !error || !window.CSTableShell) return;
  const total = Number(bankState.summary?.total || 0);
  const returned = Number(bankState.summary?.returned || bankState.items.length || 0);
  const filterCount = activeFilterEntries().length;
  summary.textContent = bankState.loading
    ? '문제은행을 불러오는 중입니다.'
    : `총 ${total}문항 · 현재 ${returned}문항 · 필터 ${filterCount}개`;
  error.textContent = bankState.error || '';
  renderHeader();
  renderOverviewCards();
  renderActiveFilters();
  renderSelectionSummary();
  renderFilterToggle();
  window.CSTableShell.renderTable(mount, {
    columns: QUESTION_BANK_COLUMNS,
    rows: tableRows(),
    storageKey: QUESTION_BANK_COLUMN_ORDER_KEY,
    tableMinWidth: '960px',
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
    window.sessionStorage.setItem(QUESTION_BANK_LAUNCH_KEY, JSON.stringify({items: bankState.items, startIndex: safeStart}));
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
    populateTopicOptions(bankState.summary?.available_topics || [], filterValues().topic);
    populateFieldNameOptions(bankState.summary?.available_field_names || [], filterValues().field_name);
    populateIssuerOptions(bankState.summary?.available_issuers || [], filterValues().issuer);
    populateCategoryOptions(bankState.summary?.available_categories || [], filterValues().category);
    const nextIndex = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === previousSelectedId);
    bankState.selectedId = String(bankState.items[nextIndex >= 0 ? nextIndex : 0]?.question_bank_id || '');
    bankState.practiceStartIndex = nextIndex >= 0 ? nextIndex : 0;
    if (!bankState.items.length) bankState.practiceLoaded = false;
  } catch (error) {
    bankState.items = [];
    bankState.summary = {total: 0, returned: 0};
    populateTopicOptions([], filterValues().topic);
    populateFieldNameOptions([], filterValues().field_name);
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
setFiltersCollapsed(persistedFiltersCollapsed());
renderTable();
renderPracticePane();
loadQuestionBankPage().catch(() => {});

$('bankPageRefreshBtn')?.addEventListener('click', () => loadQuestionBankPage().catch(() => {}));
$('bankPageLaunchBtn')?.addEventListener('click', () => launch(0));
$('bankPageLaunchSelectedBtn')?.addEventListener('click', () => launch(selectedIndex(bankState.practiceStartIndex)));
$('bankPageTogglePracticeBtn')?.addEventListener('click', togglePracticeCollapsed);
$('bankPageToggleFiltersBtn')?.addEventListener('click', toggleFiltersCollapsed);
$('bankPageResetFiltersBtn')?.addEventListener('click', resetFilters);
$('bankPagePracticeExitBtn')?.addEventListener('click', () => setPracticeCollapsed(true));

['bankPageQueryInput', 'bankPageTopicInput', 'bankPageSourceInput', 'bankPageSectionInput'].forEach((id) => {
  $(id)?.addEventListener('input', scheduleLoad);
  $(id)?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      window.clearTimeout(pendingLoadTimer);
      loadQuestionBankPage().catch(() => {});
    }
  });
});

['bankPageAttemptStatusSelect', 'bankPageFieldInput', 'bankPageCategoryInput', 'bankPageIssuerInput', 'bankPageDifficultySelect', 'bankPageTypeSelect'].forEach((id) => {
  $(id)?.addEventListener('change', () => loadQuestionBankPage().catch(() => {}));
});
