const QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';
const QUESTION_BANK_COLUMN_ORDER_KEY = 'csQuestionBankTableColumnOrder:v1';
const QUESTION_BANK_PRACTICE_COLLAPSED_KEY = 'csQuestionBankPracticeCollapsed:v1';
const QUESTION_TYPE_LABELS = {short: '주관식', subjective: '서술형', multiple_choice: '객관식', essay: '논술형'};
const QUESTION_BANK_COLUMNS = [
  {key: 'index', label: '#', width: '56px'},
  {key: 'prompt', label: '문제', width: '36rem', cellClassName: 'term-cell'},
  {key: 'type', label: '형식', width: '8.5rem'},
  {key: 'topic', label: '문제유형', width: '12rem'},
  {key: 'issuer', label: '기관', width: '9rem'},
  {key: 'difficulty', label: '난이도', width: '7rem'},
  {key: 'source', label: '출처', width: '13rem'},
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

function questionTypeLabel(item) {
  return QUESTION_TYPE_LABELS[String(item?.question_type || '').trim()] || String(item?.question_type || '문제');
}

function selectedIndex(fallback = 0) {
  const found = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === bankState.selectedId);
  return found >= 0 ? found : Math.max(0, Math.min(bankState.items.length - 1, fallback));
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

function renderPracticeToggle() {
  const toggleButton = $('bankPageTogglePracticeBtn');
  if (!toggleButton) return;
  const expanded = !bankState.practiceCollapsed;
  toggleButton.textContent = expanded ? '풀이 숨기기' : '풀이 보기';
  toggleButton.setAttribute('aria-expanded', String(expanded));
}

function setPracticeCollapsed(collapsed, {persist = true} = {}) {
  bankState.practiceCollapsed = Boolean(collapsed);
  document.body.classList.toggle('question-bank-practice-collapsed', bankState.practiceCollapsed);
  renderPracticeToggle();
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

function tableRows() {
  return bankState.items.map((item, index) => {
    const active = bankState.selectedId && bankState.selectedId === String(item.question_bank_id || '');
    const prompt = escapeHtml(markdownPreviewText(item.prompt || `문제 ${index + 1}`) || `문제 ${index + 1}`);
    const typeLabel = escapeHtml(questionTypeLabel(item));
    const topic = escapeHtml(item.topic || item.card_category || '');
    const issuer = escapeHtml(item.issuer || '');
    const difficulty = escapeHtml(item.difficulty || '');
    const source = escapeHtml(item.source_location || '');
    const preview = markdownPreviewText(item.body || item.answer || item.explanation || '').slice(0, 96);
    return {
      id: String(item.question_bank_id || index + 1),
      className: active ? 'current-row active' : '',
      cells: {
        index: String(index + 1),
        prompt: `<span class="question-bank-row-trigger"><span class="question-bank-item-title">${prompt}</span>${preview ? `<span class="question-bank-item-preview">${escapeHtml(preview)}</span>` : ''}</span>`,
        type: typeLabel || '—',
        topic: topic || '—',
        issuer: issuer || '—',
        difficulty: difficulty || '—',
        source: source || '—',
      },
    };
  });
}

function renderPracticePane() {
  const summary = $('bankPagePracticeSummary');
  const placeholder = $('bankPagePracticePlaceholder');
  const frame = $('bankPagePracticeFrame');
  if (!summary || !placeholder || !frame) return;
  if (!bankState.items.length) {
    summary.textContent = bankState.loading ? '문제은행 목록을 불러온 뒤 오른쪽에 문제 풀이를 연결합니다.' : '표에 표시할 문제가 없습니다.';
    placeholder.textContent = bankState.loading ? '문제 목록을 불러오는 중입니다.' : '현재 조건에 맞는 문제은행 항목이 없습니다.';
    placeholder.hidden = false;
    frame.hidden = true;
    return;
  }
  const start = selectedIndex(bankState.practiceStartIndex);
  const selected = bankState.items[start];
  const prompt = markdownPreviewText(selected?.prompt || '').slice(0, 46) || `문제 ${start + 1}`;
  summary.textContent = bankState.practiceLoaded
    ? `현재 목록 ${bankState.items.length}문항 · ${start + 1}번부터 풀이 · ${prompt}`
    : `현재 목록 ${bankState.items.length}문항 · 왼쪽 행을 클릭하면 여기서 바로 풉니다.`;
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
  summary.textContent = bankState.loading
    ? '문제은행을 불러오는 중입니다.'
    : `총 ${total}문항 · 현재 ${returned}문항 · ${bankState.practiceCollapsed ? '문제 풀이 패널 숨김 상태' : '문제 풀이와 문제은행 표를 한 화면에서 함께 사용 중입니다.'}`;
  error.textContent = bankState.error || '';
  window.CSTableShell.renderTable(mount, {
    columns: QUESTION_BANK_COLUMNS,
    rows: tableRows(),
    storageKey: QUESTION_BANK_COLUMN_ORDER_KEY,
    tableMinWidth: '1100px',
    emptyText: '조건에 맞는 문제가 없습니다.',
    onRowActivate: (_row, index) => {
      bankState.selectedId = String(bankState.items[index]?.question_bank_id || '');
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

    const nextIndex = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === previousSelectedId);
    bankState.selectedId = String(bankState.items[nextIndex >= 0 ? nextIndex : 0]?.question_bank_id || '');
  } catch (error) {
    bankState.items = [];
    bankState.summary = {total: 0, returned: 0};
    populateIssuerOptions([], filterValues().issuer);
    bankState.error = error.message || String(error);
    bankState.practiceLoaded = false;
  } finally {
    bankState.loading = false;
    renderTable();
    renderPracticePane();
    if (bankState.items.length) launch(selectedIndex(), {reveal: false});
  }
}

applyFiltersFromUrl();
setPracticeCollapsed(persistedPracticeCollapsed(), {persist: false});
renderTable();
renderPracticePane();
loadQuestionBankPage().catch(() => {});

$('bankPageRefreshBtn')?.addEventListener('click', () => loadQuestionBankPage().catch(() => {}));
$('bankPageLaunchBtn')?.addEventListener('click', () => launch(selectedIndex()));
$('bankPageTogglePracticeBtn')?.addEventListener('click', togglePracticeCollapsed);
['bankPageQueryInput', 'bankPageTopicInput', 'bankPageFieldInput', 'bankPageIssuerInput', 'bankPageSourceInput', 'bankPageDifficultySelect', 'bankPageTypeSelect', 'bankPageSectionInput'].forEach((id) => {
  $(id)?.addEventListener('change', () => loadQuestionBankPage().catch(() => {}));
  $(id)?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      loadQuestionBankPage().catch(() => {});
    }
  });
});
