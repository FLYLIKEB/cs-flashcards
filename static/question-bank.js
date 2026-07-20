const QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';
const QUESTION_TYPE_LABELS = {short: '주관식', subjective: '서술형', multiple_choice: '객관식', essay: '논술형'};
const $ = (id) => document.getElementById(id);

const bankState = {
  items: [],
  summary: null,
  loading: false,
  error: '',
  selectedId: '',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
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

function renderTable() {
  const summary = $('bankPageSummary');
  const list = $('bankPageList');
  const error = $('bankPageError');
  if (!summary || !list || !error) return;
  const total = Number(bankState.summary?.total || 0);
  const returned = Number(bankState.summary?.returned || bankState.items.length || 0);
  summary.textContent = bankState.loading
    ? '문제은행을 불러오는 중입니다.'
    : `총 ${total}문항 · 현재 ${returned}문항 · 표의 행을 누르면 해당 문제부터 풉니다.`;
  error.textContent = bankState.error || '';
  if (!bankState.items.length) {
    list.innerHTML = '<tr><td colspan="7" class="question-bank-empty muted">조건에 맞는 문제가 없습니다.</td></tr>';
    return;
  }
  list.innerHTML = bankState.items.map((item, index) => {
    const active = bankState.selectedId && bankState.selectedId === String(item.question_bank_id || '');
    const prompt = escapeHtml(markdownPreviewText(item.prompt || `문제 ${index + 1}`) || `문제 ${index + 1}`);
    const typeLabel = escapeHtml(questionTypeLabel(item));
    const topic = escapeHtml(item.topic || item.card_category || '');
    const issuer = escapeHtml(item.issuer || '');
    const difficulty = escapeHtml(item.difficulty || '');
    const source = escapeHtml(item.source_location || '');
    const preview = markdownPreviewText(item.body || item.answer || item.explanation || '').slice(0, 96);
    return `<tr class="question-bank-row${active ? ' active' : ''}" data-question-bank-index="${index}"><td class="question-bank-col-index">${index + 1}</td><td class="question-bank-col-title"><button class="question-bank-row-trigger" type="button" data-question-bank-index="${index}"><span class="question-bank-item-title">${prompt}</span>${preview ? `<span class="question-bank-item-preview">${escapeHtml(preview)}</span>` : ''}</button></td><td class="question-bank-col-type">${typeLabel || '—'}</td><td class="question-bank-col-field">${topic || '—'}</td><td class="question-bank-col-issuer">${issuer || '—'}</td><td class="question-bank-col-difficulty">${difficulty || '—'}</td><td class="question-bank-col-source">${source || '—'}</td></tr>`;
  }).join('');
}

function launch(startIndex = 0) {
  if (!bankState.items.length) {
    bankState.error = '문제은행 목록이 비어 있습니다.';
    renderTable();
    return;
  }
  const safeStart = Math.max(0, Math.min(bankState.items.length - 1, startIndex));
  try {
    window.sessionStorage.setItem(QUESTION_BANK_LAUNCH_KEY, JSON.stringify({
      items: bankState.items,
      startIndex: safeStart,
    }));
  } catch (error) {
    bankState.error = error.message || String(error);
    renderTable();
    return;
  }
  window.location.href = '/';
}

async function loadQuestionBankPage() {
  bankState.loading = true;
  bankState.error = '';
  syncUrl();
  renderTable();
  try {
    const data = await fetchEntries();
    bankState.items = Array.isArray(data.items) ? data.items : [];
    bankState.summary = data.summary || {total: bankState.items.length, returned: bankState.items.length};
    bankState.selectedId = String(bankState.items[0]?.question_bank_id || '');
  } catch (error) {
    bankState.items = [];
    bankState.summary = {total: 0, returned: 0};
    bankState.error = error.message || String(error);
  } finally {
    bankState.loading = false;
    renderTable();
  }
}

applyFiltersFromUrl();
renderTable();
loadQuestionBankPage().catch(() => {});

$('bankPageRefreshBtn')?.addEventListener('click', () => loadQuestionBankPage().catch(() => {}));
$('bankPageLaunchBtn')?.addEventListener('click', () => launch(0));
['bankPageQueryInput', 'bankPageTopicInput', 'bankPageFieldInput', 'bankPageIssuerInput', 'bankPageSourceInput', 'bankPageDifficultySelect', 'bankPageTypeSelect', 'bankPageSectionInput'].forEach((id) => {
  $(id)?.addEventListener('change', () => loadQuestionBankPage().catch(() => {}));
  $(id)?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      loadQuestionBankPage().catch(() => {});
    }
  });
});
$('bankPageList')?.addEventListener('click', (event) => {
  const row = event.target.closest('[data-question-bank-index]');
  if (!row) return;
  const index = Number.parseInt(row.dataset.questionBankIndex || '', 10);
  if (!Number.isInteger(index)) return;
  bankState.selectedId = String(bankState.items[index]?.question_bank_id || '');
  renderTable();
  launch(index);
});
