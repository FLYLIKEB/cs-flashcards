const QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';
const QUESTION_BANK_COLUMN_ORDER_KEY = 'csQuestionBankTableColumnOrder:v1';
const QUESTION_BANK_PRACTICE_COLLAPSED_KEY = 'csQuestionBankPracticeCollapsed:v1';
const QUESTION_BANK_FILTER_STATE_KEY = 'csQuestionBankFilters:v1';
const QUESTION_TYPE_LABELS = {short: '주관식', subjective: '서술형', multiple_choice: '객관식', essay: '논술형'};
const QUESTION_BANK_ATTEMPT_STATUS_LABELS = {unseen: '안푼', wrong: '틀린', correct: '맞은'};
const QUESTION_ATTEMPT_RESULT_LABELS = {correct: '맞음', ambiguous: '애매함', wrong: '틀림', unknown: '모름', pending: '미채점'};
const QUESTION_BANK_REVIEW_FILTER_LABELS = {attempted: '푼 문제', pending: '미채점', wrong: '틀린·애매', note: '오답노트'};
const QUESTION_BANK_COLUMNS = [
  {key: 'index', label: '#', width: '56px'},
  {key: 'attempt_status', label: '풀이상태', width: '6rem'},
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
  practiceActiveId: '',
  practiceLoaded: false,
  practiceStartIndex: 0,
  practiceNonce: 0,
  practiceCollapsed: true,
  filtersCollapsed: true,
  practiceSummary: null,
  practiceResultSetKey: '',
  practiceSessionState: null,
  reviewCollapsed: true,
  reviewLoaded: false,
  reviewDirty: true,
  reviewItems: [],
  reviewSummary: null,
  reviewLoading: false,
  reviewError: '',
  reviewFilter: 'attempted',
  reviewNonce: 0,
  reviewSavingId: '',
};


let pendingLoadTimer = 0;
let categoryGuideLastFocused = null;
const CATEGORY_GUIDE_FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
let pendingPracticeLaunch = null;

function canRestoreFocusToElement(element) {
  return Boolean(
    element
    && typeof element.focus === 'function'
    && element.isConnected !== false
    && !element.hasAttribute?.('disabled')
    && element.getAttribute?.('aria-hidden') !== 'true'
    && !element.closest?.('[hidden], [aria-hidden="true"]')
  );
}

function focusElement(element) {
  if (!element || typeof element.focus !== 'function') return false;
  try {
    element.focus({preventScroll: true});
    return true;
  } catch (_error) {
    try {
      element.focus();
      return true;
    } catch (_error2) {
      return false;
    }
  }
}

function categoryGuideFocusableElements(dialog) {
  if (!dialog || dialog.hidden) return [];
  return [...dialog.querySelectorAll(CATEGORY_GUIDE_FOCUSABLE_SELECTOR)].filter((element) => !element.hasAttribute('hidden') && !element.closest('[hidden]'));
}
let activeQuestionBankLoadRequest = 0;
let questionBankLoadAbortController = null;

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

function questionAttemptStatusKey(item) {
  const value = String(item?.question_attempt_status || '').trim();
  return Object.prototype.hasOwnProperty.call(QUESTION_BANK_ATTEMPT_STATUS_LABELS, value) ? value : 'unseen';
}

function questionAttemptStatusLabel(item) {
  const explicit = String(item?.question_attempt_status_label || '').trim();
  return explicit || QUESTION_BANK_ATTEMPT_STATUS_LABELS[questionAttemptStatusKey(item)] || QUESTION_BANK_ATTEMPT_STATUS_LABELS.unseen;
}

function questionAttemptTone(item) {
  const status = questionAttemptStatusKey(item);
  if (status === 'wrong') return 'attempt-wrong';
  if (status === 'correct') return 'attempt-correct';
  return 'attempt-default';
}

function practiceSummaryQuestionBankIds(summary) {
  return Array.isArray(summary?.questionBankIds)
    ? summary.questionBankIds.map((value) => String(value || '').trim()).filter(Boolean)
    : [];
}

function questionBankSliceMatchesPracticeSummary(summary = bankState.practiceSummary) {
  if (!summary || typeof summary !== 'object') return false;
  const summaryIds = practiceSummaryQuestionBankIds(summary);
  if (!summaryIds.length) return false;
  const currentIds = bankState.items
    .map((item) => String(item?.question_bank_id || '').trim())
    .filter(Boolean);
  if (currentIds.length !== summaryIds.length) return false;
  return currentIds.every((value, index) => value === summaryIds[index]);
}

function finishedPracticeSummary() {
  if (!bankState.practiceSummary || typeof bankState.practiceSummary !== 'object') return null;
  if (!bankState.practiceSummary.finishedAt) return null;
  return questionBankSliceMatchesPracticeSummary(bankState.practiceSummary) ? bankState.practiceSummary : null;
}

function selectedIndex(fallback = 0) {
  const found = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === bankState.selectedId);
  return found >= 0 ? found : Math.max(0, Math.min(bankState.items.length - 1, fallback));
}

function selectedItem() {
  if (!bankState.items.length) return null;
  return bankState.items[selectedIndex(bankState.practiceStartIndex)] || bankState.items[0] || null;
}
function practiceActiveIndex() {
  const found = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === bankState.practiceActiveId);
  return found >= 0 ? found : Math.max(0, Math.min(bankState.items.length - 1, bankState.practiceStartIndex));
}

function practiceItem() {
  if (!bankState.items.length) return null;
  return bankState.items[practiceActiveIndex()] || bankState.items[0] || null;
}

function questionBankResultSetKey(items = bankState.items) {
  return (Array.isArray(items) ? items : []).map((item) => String(item?.question_bank_id || '')).join('\u001f');
}

function questionBankReviewIds(items = bankState.items) {
  const seen = new Set();
  return (Array.isArray(items) ? items : [])
    .map((item) => String(item?.question_bank_id || '').trim())
    .filter((value) => {
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
}

function questionBankReviewResultKey(item) {
  const resultKey = String(item?.result_key || item?.judgment || 'pending').trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(QUESTION_ATTEMPT_RESULT_LABELS, resultKey) ? resultKey : 'pending';
}

function questionBankReviewSummaryFromItems(items = bankState.reviewItems) {
  const summary = {
    total: 0,
    correct: 0,
    ambiguous: 0,
    wrong: 0,
    unknown: 0,
    pending: 0,
    note_count: 0,
    selected_question_bank_count: questionBankReviewIds().length,
  };
  (Array.isArray(items) ? items : []).forEach((item) => {
    const resultKey = questionBankReviewResultKey(item);
    summary.total += 1;
    summary[resultKey] += 1;
    if (String(item?.wrong_note || '').trim()) summary.note_count += 1;
  });
  return summary;
}

function questionBankReviewCounts(summary = bankState.reviewSummary) {
  const source = summary && typeof summary === 'object' ? summary : questionBankReviewSummaryFromItems();
  const attempted = Number(source.total || bankState.reviewItems.length || 0);
  const correct = Number(source.correct || 0);
  const ambiguous = Number(source.ambiguous || 0);
  const wrong = Number(source.wrong || 0);
  const unknown = Number(source.unknown || 0);
  const pending = Number(source.pending || 0);
  const notes = Number(source.note_count || bankState.reviewItems.filter((item) => String(item?.wrong_note || '').trim()).length || 0);
  return {
    attempted,
    correct,
    ambiguous,
    wrong,
    unknown,
    pending,
    wrongish: ambiguous + wrong + unknown,
    notes,
    selected: Number(source.selected_question_bank_count || questionBankReviewIds().length || 0),
  };
}

function formatQuestionBankAttemptUpdatedAt(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString('ko-KR', {month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'});
}

function questionBankReviewRequestPayload(questionBankIds = questionBankReviewIds()) {
  return {
    question_bank_ids: questionBankIds,
    limit: 200,
  };
}

function questionBankReviewItemMatchesFilter(item, filter = bankState.reviewFilter) {
  const resultKey = questionBankReviewResultKey(item);
  if (filter === 'pending') return resultKey === 'pending';
  if (filter === 'wrong') return ['ambiguous', 'wrong', 'unknown'].includes(resultKey);
  if (filter === 'note') return Boolean(String(item?.wrong_note || '').trim());
  return true;
}

function visibleQuestionBankReviewItems() {
  return (Array.isArray(bankState.reviewItems) ? bankState.reviewItems : []).filter((item) => questionBankReviewItemMatchesFilter(item));
}

function questionBankReviewAttemptSnapshot(item) {
  const questionBankId = String(item?.question_bank_id || '').trim();
  if (!questionBankId) return null;
  return {
    question_bank_id: questionBankId,
    question_id: String(item?.question_id || '').trim(),
    user_answer: String(item?.user_answer || ''),
    selected_choice_index: Number.isInteger(item?.selected_choice_index) ? item.selected_choice_index : null,
    judgment: questionBankReviewResultKey(item),
    wrong_note: String(item?.wrong_note || ''),
    session_id: String(item?.session_id || '').trim(),
    session_title: String(item?.session_title || '').trim(),
    session_mode: String(item?.session_mode || '').trim(),
    section: String(item?.section || '').trim(),
    points: Number.isInteger(item?.points) ? item.points : null,
    expected_time_seconds: Number.isInteger(item?.expected_time_seconds) ? item.expected_time_seconds : null,
    answer_guide: String(item?.answer_guide || '').trim(),
    question_order: Number.isInteger(item?.question_order) ? item.question_order : null,
    question_elapsed_seconds: Number.isInteger(item?.question_elapsed_seconds) ? item.question_elapsed_seconds : null,
    session_elapsed_seconds: Number.isInteger(item?.session_elapsed_seconds) ? item.session_elapsed_seconds : null,
    time_limit_seconds: Number.isInteger(item?.time_limit_seconds) ? item.time_limit_seconds : null,
    question_started_at: String(item?.question_started_at || '').trim(),
    answered_at: String(item?.answered_at || '').trim(),
    updated_at: String(item?.updated_at || '').trim(),
    answer_revealed: true,
  };
}

function practiceLaunchSessionState(launchItems, {forcePractice = false} = {}) {
  const ids = new Set((Array.isArray(launchItems) ? launchItems : []).map((item) => String(item?.question_bank_id || '').trim()).filter(Boolean));
  const attempts = {};
  bankState.reviewItems.forEach((item) => {
    const questionBankId = String(item?.question_bank_id || '').trim();
    if (!questionBankId || !ids.has(questionBankId)) return;
    const snapshot = questionBankReviewAttemptSnapshot(item);
    if (!snapshot) return;
    if (forcePractice) snapshot.session_mode = 'practice';
    attempts[questionBankId] = snapshot;
  });
  return Object.keys(attempts).length ? {attemptsByQuestionBankId: attempts} : null;
}

function questionBankReviewLaunchSessionState(item, reviewItems = visibleQuestionBankReviewItems()) {
  const questionBankId = String(item?.question_bank_id || '').trim();
  if (!questionBankId) return null;
  const sessionItems = (Array.isArray(reviewItems) ? reviewItems : [])
    .map((entry) => questionBankReviewAttemptSnapshot(entry))
    .filter(Boolean);
  if (!sessionItems.length) return null;
  return {
    reviewQuestionBankId: questionBankId,
    reviewQuestionBankIds: sessionItems.map((entry) => entry.question_bank_id),
    attemptsByQuestionBankId: Object.fromEntries(sessionItems.map((entry) => [entry.question_bank_id, entry])),
  };
}

function questionAttemptStatusFromReviewJudgment(judgment = 'pending') {
  if (judgment === 'correct') return 'correct';
  if (['ambiguous', 'wrong', 'unknown'].includes(judgment)) return 'wrong';
  return 'unseen';
}

function syncPracticeSessionReviewAttempt(item) {
  const snapshot = questionBankReviewAttemptSnapshot(item);
  if (!snapshot || !bankState.practiceSessionState || typeof bankState.practiceSessionState !== 'object') return;
  const attempts = bankState.practiceSessionState.attemptsByQuestionBankId && typeof bankState.practiceSessionState.attemptsByQuestionBankId === 'object'
    ? bankState.practiceSessionState.attemptsByQuestionBankId
    : {};
  bankState.practiceSessionState = {
    ...bankState.practiceSessionState,
    attemptsByQuestionBankId: {
      ...attempts,
      [snapshot.question_bank_id]: snapshot,
    },
  };
}

function updateQuestionBankReviewItem(questionBankId, updates = {}) {
  const targetId = String(questionBankId || '').trim();
  if (!targetId) return null;
  const index = bankState.reviewItems.findIndex((entry) => String(entry?.question_bank_id || '') === targetId);
  if (index < 0) return null;
  const resultKey = questionBankReviewResultKey({result_key: updates.result_key || updates.judgment || bankState.reviewItems[index]?.result_key || bankState.reviewItems[index]?.judgment || 'pending'});
  const nextItem = {
    ...bankState.reviewItems[index],
    ...updates,
    result_key: resultKey,
    judgment: resultKey,
    result_label: QUESTION_ATTEMPT_RESULT_LABELS[resultKey] || String(updates.result_label || bankState.reviewItems[index]?.result_label || ''),
  };
  bankState.reviewItems[index] = nextItem;
  bankState.reviewSummary = questionBankReviewSummaryFromItems();
  syncPracticeSessionReviewAttempt(nextItem);
  return nextItem;
}

function questionBankReviewAttemptPayload(item, judgment = questionBankReviewResultKey(item)) {
  const questionBankId = String(item?.question_bank_id || '').trim();
  if (!questionBankId) return null;
  return {
    question_id: String(item?.question_id || '').trim(),
    question_bank_id: questionBankId,
    card_id: String(item?.card_id || '').trim(),
    question_type: String(item?.question_type || 'subjective'),
    prompt: String(item?.prompt || ''),
    body: String(item?.body || ''),
    user_answer: String(item?.user_answer || ''),
    selected_choice_index: Number.isInteger(item?.selected_choice_index) ? item.selected_choice_index : null,
    is_correct: judgment === 'correct' ? true : ['ambiguous', 'wrong', 'unknown'].includes(judgment) ? false : null,
    judgment,
    wrong_note: judgment === 'correct' ? '' : String(item?.wrong_note || ''),
    session_id: String(item?.session_id || '').trim(),
    session_title: String(item?.session_title || '').trim(),
    session_mode: String(item?.session_mode || 'practice').trim(),
    section: String(item?.section || '').trim(),
    points: Number.isInteger(item?.points) ? item.points : null,
    expected_time_seconds: Number.isInteger(item?.expected_time_seconds) ? item.expected_time_seconds : null,
    answer_guide: String(item?.answer_guide || '').trim(),
    question_order: Number.isInteger(item?.question_order) ? item.question_order : null,
    question_elapsed_seconds: Number.isInteger(item?.question_elapsed_seconds) ? item.question_elapsed_seconds : null,
    session_elapsed_seconds: Number.isInteger(item?.session_elapsed_seconds) ? item.session_elapsed_seconds : null,
    time_limit_seconds: Number.isInteger(item?.time_limit_seconds) ? item.time_limit_seconds : null,
    question_started_at: String(item?.question_started_at || '').trim(),
    answered_at: String(item?.answered_at || new Date().toISOString()),
  };
}

async function saveQuestionBankReviewJudgment(questionBankId, judgment) {
  const normalizedId = String(questionBankId || '').trim();
  const normalizedJudgment = String(judgment || '').trim().toLowerCase();
  if (!normalizedId || !Object.prototype.hasOwnProperty.call(QUESTION_ATTEMPT_RESULT_LABELS, normalizedJudgment)) return;
  if (bankState.reviewSavingId || bankState.reviewLoading) return;
  const currentItem = (Array.isArray(bankState.reviewItems) ? bankState.reviewItems : []).find((item) => String(item?.question_bank_id || '') === normalizedId);
  if (!currentItem) return;
  const payload = questionBankReviewAttemptPayload(currentItem, normalizedJudgment);
  if (!payload) return;
  bankState.reviewSavingId = normalizedId;
  bankState.reviewError = '';
  renderQuestionBankReview();
  try {
    const res = await fetch('/api/questions/attempt', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    updateQuestionBankReviewItem(normalizedId, data.attempt || payload);
    renderQuestionBankReview();
  } catch (error) {
    bankState.reviewError = error.message || String(error);
  } finally {
    bankState.reviewSavingId = '';
    renderQuestionBankReview();
  }
}

function practiceLaunchPayload(startIndex, sessionState = bankState.practiceSessionState, launchItems = bankState.items) {
  const payload = {items: Array.isArray(launchItems) ? launchItems : bankState.items, startIndex};
  if (sessionState && typeof sessionState === 'object') payload.sessionState = sessionState;
  return payload;
}

function persistPracticeLaunch(startIndex, sessionState = bankState.practiceSessionState, launchItems = bankState.items) {
  window.sessionStorage.setItem(QUESTION_BANK_LAUNCH_KEY, JSON.stringify(practiceLaunchPayload(startIndex, sessionState, launchItems)));
}

function restartPracticeFrame(startIndex, sessionState = bankState.practiceSessionState, launchItems = bankState.items) {
  const frame = $('bankPagePracticeFrame');
  persistPracticeLaunch(startIndex, sessionState, launchItems);
  bankState.practiceNonce += 1;
  bankState.practiceResultSetKey = questionBankResultSetKey();
  if (frame) frame.src = practiceFrameUrl();
}

function confirmPracticeRestart(startIndex) {
  const nextNumber = selectedIndex(startIndex) + 1;
  return window.confirm(`현재 풀이 세트의 작성 내용이 새 세트를 다시 열 때까지 화면에서 사라집니다. ${nextNumber}번 문제로 다시 시작할까요?`);
}




function practiceFrameUrl() {
  return `/?question-bank-embed=1&question-bank-run=${Date.now()}-${bankState.practiceNonce}`;
}

function practiceFrameDocument() {
  const frame = $('bankPagePracticeFrame');
  if (!frame) return null;
  try {
    return frame.contentWindow?.document || null;
  } catch (_error) {
    return null;
  }
}

function embeddedPracticeHasUnsavedState() {
  if (!bankState.practiceLoaded) return false;
  const doc = practiceFrameDocument();
  if (!doc) return false;
  const shell = doc.querySelector('.question-card-shell');
  return shell ? shell.dataset.questionDirty === '1' : false;
}

function persistedPracticeCollapsed() {
  try {
    return window.localStorage.getItem(QUESTION_BANK_PRACTICE_COLLAPSED_KEY) !== '0';
  } catch (_error) {
    return true;
  }
}
function persistPracticeCollapsedState(collapsed) {
  try {
    window.localStorage.setItem(QUESTION_BANK_PRACTICE_COLLAPSED_KEY, collapsed ? '1' : '0');
  } catch (_error) {
    // Ignore storage failures.
  }
}

function navigationType() {
  return window.performance?.getEntriesByType?.('navigation')?.[0]?.type || '';
}
function isReloadNavigation() {
  return navigationType() === 'reload';
}
function isHistoryNavigation() {
  return navigationType() === 'back_forward';
}
function shouldRestorePersistedQuestionBankState() {
  return isReloadNavigation() || isHistoryNavigation();
}
const canRestorePersistedQuestionBankState = shouldRestorePersistedQuestionBankState();
function persistedSelectionRestoreState() {
  return canRestorePersistedQuestionBankState ? (persistedFilterState()?.selection || null) : null;
}
function persistedPracticeRestoreState() {
  return canRestorePersistedQuestionBankState ? (persistedFilterState()?.practice || null) : null;
}
let restoredSelectionState = persistedSelectionRestoreState();
let restoredPracticeState = persistedPracticeRestoreState();
let shouldRestorePracticePane = canRestorePersistedQuestionBankState && Boolean(restoredPracticeState?.loaded) && !persistedPracticeCollapsed();

function persistedFilterState() {
  try {
    const raw = window.localStorage.getItem(QUESTION_BANK_FILTER_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch (_error) {
    return null;
  }
}

function persistedFiltersCollapsed() {
  return canRestorePersistedQuestionBankState ? persistedFilterState()?.filtersCollapsed !== false : true;
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
  const attemptStatus = questionAttemptStatusKey(item);
  if (attemptStatus !== 'unseen') bits.push(`<span class="question-bank-summary-pill ${questionAttemptTone(item)}">${escapeHtml(questionAttemptStatusLabel(item))}</span>`);
  const typeLabel = questionTypeLabel(item);
  if (typeLabel) bits.push(`<span class="question-bank-summary-pill ${pillTone('type', item.question_type)}">${escapeHtml(typeLabel)}</span>`);
  if (item?.difficulty) bits.push(`<span class="question-bank-summary-pill ${pillTone('difficulty', item.difficulty)}">난이도 ${escapeHtml(item.difficulty)}</span>`);
  if (item?.issuer) bits.push(`<span class="question-bank-summary-pill">${escapeHtml(item.issuer)}</span>`);
  return bits;
}

function selectedPrompt(item, fallback = '문제를 선택하세요.') {
  return markdownPreviewText(item?.prompt || '').slice(0, 120) || fallback;
}

function questionBankCategoryBreakdown() {
  return Array.isArray(bankState.summary?.category_breakdown) ? bankState.summary.category_breakdown : [];
}

function activeFilterEntries() {
  const values = filterValues();
  return FILTER_FIELDS.map((field) => ({...field, value: String(values[field.key] || '').trim()})).filter((field) => field.value);
}

function categoryGuideFilterSummary() {
  const entries = activeFilterEntries();
  if (!entries.length) return '전체 문제은행 기준';
  const labels = entries.slice(0, 4).map((entry) => `${entry.label} ${entry.value}`);
  if (entries.length > 4) labels.push(`외 ${entries.length - 4}개`);
  return `현재 필터 반영: ${labels.join(' · ')}`;
}

function categoryGuideStarterCount(entry) {
  return Number(entry?.multiple_choice_count || 0) + Number(entry?.short_count || 0);
}

function categoryGuideWrittenCount(entry) {
  return Number(entry?.subjective_count || 0) + Number(entry?.essay_count || 0);
}

function categoryGuideOutstandingCount(entry) {
  return Number(entry?.unseen_count || 0) + Number(entry?.wrong_count || 0);
}

function categoryGuidePriorityScore(entry) {
  return (categoryGuideOutstandingCount(entry) * 4)
    + (categoryGuideStarterCount(entry) * 3)
    + (Number(entry?.medium_difficulty_count || 0) * 2)
    + Number(entry?.total || 0);
}

function categoryGuideStartingSetSize(entry) {
  const total = Number(entry?.total || 0);
  if (total >= 45) return '25문항';
  if (total >= 30) return '20문항';
  if (total >= 18) return '15문항';
  return '10문항';
}

function categoryGuideReason(entry) {
  const reasons = [];
  const outstanding = categoryGuideOutstandingCount(entry);
  const starter = categoryGuideStarterCount(entry);
  const written = categoryGuideWrittenCount(entry);
  const medium = Number(entry?.medium_difficulty_count || 0);
  const high = Number(entry?.high_difficulty_count || 0);
  const low = Number(entry?.low_difficulty_count || 0);
  if (outstanding) reasons.push(`안푼·틀린 ${outstanding}문항`);
  reasons.push(starter >= written
    ? `객관식·주관식 ${starter}문항으로 초반 회전용`
    : `서술·논술 ${written}문항 비중으로 후반 정리용`);
  if (medium >= Math.max(high, low)) reasons.push(`중 난도 ${medium}문항 중심`);
  else if (high > medium) reasons.push(`상 난도 ${high}문항 비중 높음`);
  else reasons.push(`하 난도 ${low}문항으로 가볍게 착수 가능`);
  return reasons.join(' · ');
}

function categoryGuideRows() {
  return questionBankCategoryBreakdown()
    .map((entry) => ({
      category: String(entry?.category || '미분류').trim() || '미분류',
      total: Number(entry?.total || 0),
      multiple_choice_count: Number(entry?.multiple_choice_count || 0),
      short_count: Number(entry?.short_count || 0),
      subjective_count: Number(entry?.subjective_count || 0),
      essay_count: Number(entry?.essay_count || 0),
      high_difficulty_count: Number(entry?.high_difficulty_count || 0),
      medium_difficulty_count: Number(entry?.medium_difficulty_count || 0),
      low_difficulty_count: Number(entry?.low_difficulty_count || 0),
      unseen_count: Number(entry?.unseen_count || 0),
      correct_count: Number(entry?.correct_count || 0),
      wrong_count: Number(entry?.wrong_count || 0),
    }))
    .filter((entry) => entry.total > 0)
    .sort((left, right) => categoryGuidePriorityScore(right) - categoryGuidePriorityScore(left)
      || right.total - left.total
      || left.category.localeCompare(right.category, 'ko'));
}

function renderCategoryGuideDialog() {
  const summary = $('bankPageCategoryGuideSummary');
  const body = $('bankPageCategoryGuideBody');
  if (summary) {
    if (bankState.loading) {
      summary.textContent = '현재 문제은행을 다시 계산하는 중입니다.';
    } else if (bankState.error) {
      summary.textContent = '문제은행을 먼저 정상적으로 불러와야 카테고리 순서를 계산할 수 있습니다.';
    } else {
      summary.textContent = `${categoryGuideFilterSummary()} · 총 ${Number(bankState.summary?.total || 0)}문항 · 안푼/틀린 + 객관식/주관식 + 중 난도 순으로 우선순위를 계산했습니다.`;
    }
  }
  if (!body) return;
  if (bankState.loading) {
    body.innerHTML = '<p class="question-bank-guide-empty">문제은행 기준표를 계산하는 중입니다.</p>';
    return;
  }
  if (bankState.error) {
    body.innerHTML = `<p class="question-bank-guide-empty">${escapeHtml(bankState.error)}</p>`;
    return;
  }
  const rows = categoryGuideRows();
  if (!rows.length) {
    body.innerHTML = '<p class="question-bank-guide-empty">현재 조건에서는 추천할 카테고리가 없습니다.</p>';
    return;
  }
  body.innerHTML = `
    <div class="question-bank-guide-intro">
      <p class="question-bank-guide-copy">남은 양이 많고, 객관식·주관식과 중 난도 비중이 큰 카테고리를 먼저 두었습니다. <strong>남은/총</strong>은 현재 필터 안에서 <strong>안푼 + 틀린</strong> 문항 수입니다.</p>
    </div>
    <div class="question-bank-guide-table-wrap">
      <table class="question-bank-guide-table">
        <thead>
          <tr>
            <th scope="col">순서</th>
            <th scope="col">카테고리</th>
            <th scope="col">남은/총</th>
            <th scope="col">첫 세트</th>
            <th scope="col">형식 구성</th>
            <th scope="col">난이도</th>
            <th scope="col">설명</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((entry, index) => {
            const outstanding = categoryGuideOutstandingCount(entry);
            return `
              <tr>
                <td>${escapeHtml(String(index + 1))}</td>
                <th scope="row">${escapeHtml(entry.category)}</th>
                <td>${escapeHtml(`${outstanding} / ${entry.total}`)}</td>
                <td>${escapeHtml(categoryGuideStartingSetSize(entry))}</td>
                <td>${escapeHtml(`객관 ${entry.multiple_choice_count} · 주관 ${entry.short_count} · 서술/논술 ${categoryGuideWrittenCount(entry)}`)}</td>
                <td>${escapeHtml(`중 ${entry.medium_difficulty_count} · 상 ${entry.high_difficulty_count} · 하 ${entry.low_difficulty_count}`)}</td>
                <td>${escapeHtml(categoryGuideReason(entry))}</td>
              </tr>
            `;
          }).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function openCategoryGuideDialog() {
  const dialog = $('bankPageCategoryGuideDialog');
  if (!dialog) return;
  categoryGuideLastFocused = canRestoreFocusToElement(document.activeElement) ? document.activeElement : null;
  renderCategoryGuideDialog();
  dialog.hidden = false;
  document.body.classList.add('question-bank-dialog-open');
  window.setTimeout(() => {
    focusElement($('bankPageCategoryGuideCloseBtn') || categoryGuideFocusableElements(dialog)[0] || dialog);
  }, 0);
}

function closeCategoryGuideDialog({restoreFocus = true} = {}) {
  const dialog = $('bankPageCategoryGuideDialog');
  if (!dialog || dialog.hidden) return;
  dialog.hidden = true;
  document.body.classList.remove('question-bank-dialog-open');
  const focusTarget = restoreFocus && canRestoreFocusToElement(categoryGuideLastFocused) ? categoryGuideLastFocused : null;
  categoryGuideLastFocused = null;
  focusElement(focusTarget);
}

function trapTabKeyWithinCategoryGuideDialog(event) {
  if (event.key !== 'Tab') return false;
  const dialog = $('bankPageCategoryGuideDialog');
  if (!dialog || dialog.hidden) return false;
  const focusable = categoryGuideFocusableElements(dialog);
  if (!focusable.length) {
    event.preventDefault();
    focusElement(dialog);
    return true;
  }
  const currentIndex = focusable.findIndex((element) => element === document.activeElement);
  const nextIndex = event.shiftKey
    ? (currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1)
    : (currentIndex < 0 || currentIndex === focusable.length - 1 ? 0 : currentIndex + 1);
  const movingOutside = event.shiftKey ? document.activeElement === focusable[0] : document.activeElement === focusable[focusable.length - 1];
  if (currentIndex < 0 || movingOutside) {
    event.preventDefault();
    focusElement(focusable[nextIndex]);
    return true;
  }
  return false;
}

function handleOpenCategoryGuideDialogKeydown(event) {
  const dialog = $('bankPageCategoryGuideDialog');
  if (!dialog || dialog.hidden) return false;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeCategoryGuideDialog();
    return true;
  }
  return trapTabKeyWithinCategoryGuideDialog(event);
}

function fieldByKey(key) {
  return FILTER_FIELDS.find((field) => field.key === key) || null;
}
function ensureSelectValue(select, value = '') {
  if (!select) return;
  const normalizedValue = String(value || '').trim();
  [...select.querySelectorAll('option[data-dynamic-filter-value="true"]')].forEach((option) => option.remove());
  if (!normalizedValue) {
    select.value = '';
    return;
  }
  const hasMatchingOption = [...select.options].some((option) => String(option.value || '').trim() === normalizedValue);
  if (!hasMatchingOption) {
    const option = document.createElement('option');
    option.value = normalizedValue;
    option.textContent = normalizedValue;
    option.dataset.dynamicFilterValue = 'true';
    select.append(option);
  }
  select.value = normalizedValue;
}

function setFilterValue(key, value = '') {
  const field = fieldByKey(key);
  if (!field) return;
  const node = $(field.id);
  if (!node) return;
  if (node.tagName === 'SELECT') {
    ensureSelectValue(node, value);
    return;
  }
  node.value = value;
}

function clearFilterField(key) {
  setFilterValue(key, '');
  persistFilterState();
  loadQuestionBankPage().catch(() => {});
}
function questionBankItemMatchesAttemptStatusFilter(item, attemptStatus = filterValues().attempt_status) {
  if (!attemptStatus) return true;
  return String(item?.question_attempt_status || 'unseen') === String(attemptStatus || '');
}


function applyEmbeddedQuestionBankUpdate(item, summary = null, finishedAt = '') {
  if (summary && typeof summary === 'object') bankState.practiceSummary = {...summary, finishedAt: String(finishedAt || '')};
  const questionBankId = String(item?.question_bank_id || '').trim();
  if (!questionBankId) {
    renderHeader();
    renderOverviewCards();
    renderPracticePane();
    return;
  }
  const index = bankState.items.findIndex((entry) => String(entry?.question_bank_id || '') === questionBankId);
  if (index < 0) {
    loadQuestionBankPage().catch(() => {});
    return;
  }
  const nextItem = {...bankState.items[index], ...item};
  bankState.items[index] = nextItem;
  if (bankState.reviewLoaded) {
    const updatedReviewItem = updateQuestionBankReviewItem(questionBankId, {
      result_key: String(item?.question_attempt_judgment || item?.result_key || '').trim().toLowerCase(),
      judgment: String(item?.question_attempt_judgment || item?.judgment || '').trim().toLowerCase(),
      updated_at: String(item?.question_attempt_updated_at || item?.updated_at || '').trim(),
    });
    if (!updatedReviewItem) {
      bankState.reviewLoaded = false;
      bankState.reviewDirty = true;
    }
  } else {
    bankState.reviewLoaded = false;
    bankState.reviewDirty = true;
  }
  if (!questionBankItemMatchesAttemptStatusFilter(nextItem)) {
    loadQuestionBankPage().catch(() => {});
    return;
  }
  renderTable();
  renderPracticePane();
  if (!bankState.reviewCollapsed) renderQuestionBankReview();
}


function isCompactQuestionBankViewport() {
  return typeof window.matchMedia === 'function'
    ? window.matchMedia('(max-width: 900px)').matches
    : Number(window.innerWidth || 0) <= 900;
}

function syncCompactQuestionBankViewport() {
  if (!bankState.practiceLoaded || !isCompactQuestionBankViewport()) return;
  if (!bankState.practiceCollapsed) {
    window.scrollTo?.({top: 0, left: 0, behavior: 'auto'});
    return;
  }
  document.querySelector('.question-bank-table-selection')?.scrollIntoView?.({block: 'start', inline: 'nearest'});
}

function applyPracticeViewState() {
  const practiceFocus = bankState.practiceLoaded && !bankState.practiceCollapsed;
  document.body.classList.toggle('question-bank-practice-collapsed', !practiceFocus);
  document.body.classList.toggle('question-bank-practice-focus', practiceFocus);
}

function applyFilterViewState() {
  const region = $('bankPageFiltersRegion');
  document.body.classList.toggle('question-bank-filters-collapsed', bankState.filtersCollapsed);
  if (region) region.hidden = bankState.filtersCollapsed;
}

function reviewNeedsRefresh() {
  return !bankState.reviewLoaded || bankState.reviewDirty || Boolean(bankState.reviewError);
}

function renderReviewToggle() {
  const toggleButton = $('bankPageToggleReviewBtn');
  const body = $('bankPageReviewBody');
  if (toggleButton) {
    toggleButton.textContent = bankState.reviewCollapsed ? '리뷰 열기' : '리뷰 숨기기';
    toggleButton.setAttribute('aria-expanded', String(!bankState.reviewCollapsed));
  }
  if (body) body.hidden = bankState.reviewCollapsed;
}

async function ensureQuestionBankReviewLoaded({force = false} = {}) {
  renderReviewToggle();
  if (bankState.reviewCollapsed || bankState.loading) {
    renderQuestionBankReview();
    return false;
  }
  if (!force && !reviewNeedsRefresh()) {
    renderQuestionBankReview();
    return false;
  }
  await loadQuestionBankReview();
  return true;
}

function setReviewCollapsed(collapsed) {
  bankState.reviewCollapsed = Boolean(collapsed);
  renderReviewToggle();
  if (bankState.reviewCollapsed) {
    renderQuestionBankReview();
    return;
  }
  ensureQuestionBankReviewLoaded().catch(() => {});
}

function toggleReviewCollapsed() {
  setReviewCollapsed(!bankState.reviewCollapsed);
}

function renderFilterToggle() {
  const toggleButton = $('bankPageToggleFiltersBtn');
  if (!toggleButton) return;
  const count = activeFilterEntries().length;
  toggleButton.textContent = bankState.filtersCollapsed
    ? `필터 열기${count ? ` (${count})` : ''}`
    : '필터 숨기기';
  toggleButton.setAttribute('aria-controls', 'bankPageFiltersRegion');
  toggleButton.setAttribute('aria-expanded', String(!bankState.filtersCollapsed));
}

function persistFilterState() {
  try {
    window.localStorage.setItem(QUESTION_BANK_FILTER_STATE_KEY, JSON.stringify({
      filters: filterValues(),
      filtersCollapsed: bankState.filtersCollapsed,
      selection: {
        selectedId: String(bankState.selectedId || ''),
        startIndex: selectedIndex(bankState.practiceStartIndex),
      },
      practice: {
        loaded: bankState.practiceLoaded,
        selectedId: bankState.practiceLoaded ? String(bankState.practiceActiveId || bankState.selectedId || '') : '',
        startIndex: bankState.practiceLoaded ? practiceActiveIndex() : bankState.practiceStartIndex,
      },
    }));


  } catch (_error) {
    // Ignore storage failures.
  }
}

function setFiltersCollapsed(collapsed, {persist = true} = {}) {
  bankState.filtersCollapsed = Boolean(collapsed);
  applyFilterViewState();
  renderFilterToggle();
  if (persist) persistFilterState();
}

function toggleFiltersCollapsed() {
  setFiltersCollapsed(!bankState.filtersCollapsed);
}

function renderPracticeToggle() {
  const toggleButton = $('bankPageTogglePracticeBtn');
  if (!toggleButton) return;
  const showingPractice = bankState.practiceLoaded && !bankState.practiceCollapsed;
  toggleButton.textContent = showingPractice ? '문제은행 보기' : '문제 풀이 보기';
  toggleButton.setAttribute('aria-pressed', String(showingPractice));
  toggleButton.removeAttribute('aria-expanded');
  toggleButton.disabled = !bankState.practiceLoaded;
}

function setPracticeCollapsed(collapsed, {persist = true} = {}) {
  bankState.practiceCollapsed = Boolean(collapsed);
  applyPracticeViewState();
  renderPracticeToggle();
  renderOverviewCards();
  renderHeader();
  if (bankState.practiceCollapsed) ensureSelectedRowVisible();
  syncCompactQuestionBankViewport();
  if (!persist) return;
  persistPracticeCollapsedState(bankState.practiceCollapsed);
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

function hasUrlFilterState() {
  const params = new URLSearchParams(window.location.search);
  return FILTER_FIELDS.some(({key}) => params.has(key)) || params.has('status') || params.has('card_category');
}

function applyFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search);
  setFilterValue('q', params.get('q') || '');
  setFilterValue('attempt_status', params.get('attempt_status') || params.get('status') || '');
  setFilterValue('topic', params.get('topic') || '');
  setFilterValue('field_name', params.get('field_name') || '');
  setFilterValue('category', params.get('category') || params.get('card_category') || '');
  setFilterValue('issuer', params.get('issuer') || '');
  setFilterValue('source_location', params.get('source_location') || '');
  setFilterValue('difficulty', params.get('difficulty') || '');
  setFilterValue('question_type', params.get('question_type') || '');
  setFilterValue('section', params.get('section') || '');
}

function applyFiltersFromState(filters = {}) {
  FILTER_FIELDS.forEach(({key}) => setFilterValue(key, filters[key] || ''));
}

function restoreFilterState() {
  const storedState = canRestorePersistedQuestionBankState ? persistedFilterState() : null;
  if (hasUrlFilterState()) {
    applyFiltersFromUrl();
    return;
  }
  if (storedState?.filters) {
    applyFiltersFromState(storedState.filters);
    return;
  }
  applyFiltersFromUrl();
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
  ensureSelectValue(select, selectedValue);
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
  ensureSelectValue(select, selectedValue);
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
  ensureSelectValue(select, selectedValue);
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
  const hash = window.location.hash || '';
  const next = `${qs ? `/question-bank?${qs}` : '/question-bank'}${hash}`;
  if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== next) window.history.replaceState({}, '', next);
}

async function fetchEntries({signal} = {}) {
  const params = new URLSearchParams(queryString());
  params.set('__ts', String(Date.now()));
  const qs = params.toString();
  const res = await fetch(`/api/question-bank${qs ? `?${qs}` : ''}`, {cache: 'no-store', signal});
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function resetFilters() {
  FILTER_FIELDS.forEach(({key}) => setFilterValue(key, ''));
  persistFilterState();
  loadQuestionBankPage().catch(() => {});
}

function scheduleLoad() {
  persistFilterState();
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
  const practiceSummary = finishedPracticeSummary();
  if (summary) {
    if (bankState.loading) {
      summary.textContent = '문제은행을 정리하는 중입니다.';
    } else if (!bankState.items.length) {
      summary.textContent = bankState.error ? '조회 조건을 확인하고 다시 불러오세요.' : '조건에 맞는 문제를 찾지 못했습니다.';
    } else if (showingPractice && practiceSummary) {
      summary.textContent = `채점 완료 · 점수 ${practiceSummary.scoreLabel} · ${practiceSummary.scoreDetail}`;
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
        practiceSummary ? `<span class="question-bank-header-chip question-bank-header-chip-strong">점수 ${escapeHtml(practiceSummary.scoreLabel)}</span>` : '',
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
  const practiceSummary = finishedPracticeSummary();
  mount.innerHTML = practiceSummary
    ? [
        metricCard('점수', practiceSummary.scoreLabel, practiceSummary.scoreDetail || '', 'score'),
        metricCard('맞음', String(practiceSummary.correct || 0), `전체 ${practiceSummary.totalQuestions || 0}문항`, 'correct'),
        metricCard('오답', String(practiceSummary.wrongCount || 0), `틀림 ${practiceSummary.wrong || 0} · 애매 ${practiceSummary.ambiguous || 0} · 모름 ${practiceSummary.unknown || 0}`, 'wrong'),
        metricCard('풀이', practiceSummary.pending ? `미채점 ${practiceSummary.pending}` : '채점 완료', practiceState),
      ].join('')
    : [
        metricCard('목록', total ? `${returned}/${total}` : String(returned)),
        metricCard('선택', selectedLabel),
        metricCard('필터', filterCount ? `${filterCount}개` : '없음'),
        metricCard('풀이', practiceState),
      ].join('');
}

function selectQuestionBankItem(questionBankId, {launchPractice = false, sessionState = null} = {}) {
  const index = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === String(questionBankId || ''));
  if (index < 0) return;
  bankState.selectedId = String(bankState.items[index]?.question_bank_id || '');
  bankState.practiceStartIndex = index;
  bankState.practiceSessionState = sessionState && typeof sessionState === 'object' ? sessionState : null;
  persistFilterState();

  renderTable();
  renderPracticePane();
  ensureSelectedRowVisible();
  if (launchPractice) launch(index, {sessionState: bankState.practiceSessionState});
}

function bindQuestionBankRowTriggerActions() {
  $('bankPageList')?.querySelectorAll('[data-question-bank-row-index]').forEach((button) => {
    button.addEventListener('click', () => {
      const index = Number.parseInt(button.dataset.questionBankRowIndex || '', 10);
      if (!Number.isInteger(index)) return;
      launch(index);
    });
  });
}

function launchQuestionBankReview(questionBankId) {
  const reviewItem = (Array.isArray(bankState.reviewItems) ? bankState.reviewItems : []).find((item) => String(item?.question_bank_id || '') === String(questionBankId || ''));
  selectQuestionBankItem(questionBankId, {
    launchPractice: true,
    sessionState: questionBankReviewLaunchSessionState(reviewItem),
  });
}

function bindQuestionBankReviewActions() {
  $('bankPageReviewFilters')?.querySelectorAll('[data-review-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      const nextFilter = String(button.dataset.reviewFilter || 'attempted');
      if (!QUESTION_BANK_REVIEW_FILTER_LABELS[nextFilter]) return;
      bankState.reviewFilter = nextFilter;
      renderQuestionBankReview();
    });
  });
  $('bankPageReviewList')?.querySelectorAll('.question-bank-review-jump[data-question-bank-review-id]').forEach((button) => {
    button.addEventListener('click', () => launchQuestionBankReview(button.dataset.questionBankReviewId || ''));
  });
  $('bankPageReviewList')?.querySelectorAll('[data-question-bank-review-id][data-question-bank-review-judgment]').forEach((button) => {
    button.addEventListener('click', () => saveQuestionBankReviewJudgment(
      button.dataset.questionBankReviewId || '',
      button.dataset.questionBankReviewJudgment || 'pending',
    ).catch(() => {}));
  });
}

function reviewFieldHtml(label, value, emptyText = '—') {
  const text = String(value || '').trim() || emptyText;
  return `<div class="question-bank-review-field"><span class="question-bank-review-field-label">${escapeHtml(label)}</span><p class="question-bank-review-field-value">${escapeHtml(text)}</p></div>`;
}

function renderQuestionBankReview() {
  const summary = $('bankPageReviewSummary');
  const body = $('bankPageReviewBody');
  const stats = $('bankPageReviewStats');
  const filters = $('bankPageReviewFilters');
  const list = $('bankPageReviewList');
  const counts = questionBankReviewCounts();
  const selectedCount = questionBankReviewIds().length;
  const visibleItems = visibleQuestionBankReviewItems();
  renderReviewToggle();
  if (summary) {
    if (bankState.reviewCollapsed) {
      summary.textContent = bankState.loading
        ? '문제은행을 불러오는 중입니다.'
        : !selectedCount
          ? '현재 목록에 리뷰할 문제은행 문항이 없습니다.'
          : `현재 목록 ${selectedCount}문항 · 리뷰 닫힘 · 열면 풀이 기록과 오답노트를 불러옵니다.`;
    } else if (bankState.loading || bankState.reviewLoading) {
      summary.textContent = '현재 문제은행 풀이 기록을 불러오는 중입니다.';
    } else if (bankState.reviewError) {
      summary.textContent = `풀이 기록 로딩 실패: ${bankState.reviewError}`;
    } else {
      summary.textContent = `현재 목록 ${selectedCount}문항 중 풀었던 문제 ${counts.attempted}개 · 틀린/애매 ${counts.wrongish}개 · 오답노트 ${counts.notes}개`;
    }
  }
  if (!body || body.hidden || !stats || !filters || !list) return;
  if (stats) {
    stats.innerHTML = [
      metricCard('푼 문제', String(counts.attempted)),
      metricCard('맞은 문제', String(counts.correct)),
      metricCard('틀린·애매', String(counts.wrongish)),
      metricCard('오답노트', String(counts.notes)),
    ].join('');
  }
  if (filters) {
    filters.innerHTML = Object.entries(QUESTION_BANK_REVIEW_FILTER_LABELS).map(([key, label]) => {
      const count = key === 'wrong'
        ? counts.wrongish
        : key === 'note'
          ? counts.notes
          : key === 'pending'
            ? counts.pending
            : counts.attempted;
      const active = bankState.reviewFilter === key;
      return `<button type="button" class="cs-table-button question-bank-review-filter${active ? ' is-active' : ''}" data-review-filter="${escapeHtml(key)}" aria-pressed="${active ? 'true' : 'false'}">${escapeHtml(label)} ${escapeHtml(String(count))}</button>`;
    }).join('');
  }
  if (bankState.loading || bankState.reviewLoading) {
    list.innerHTML = '<p class="question-bank-review-empty">현재 문제은행 풀이 기록을 불러오는 중입니다.</p>';
    bindQuestionBankReviewActions();
    return;
  }
  if (bankState.reviewError) {
    list.innerHTML = `<p class="question-bank-review-empty">${escapeHtml(bankState.reviewError)}</p>`;
    bindQuestionBankReviewActions();
    return;
  }
  if (!selectedCount) {
    list.innerHTML = '<p class="question-bank-review-empty">현재 목록에 리뷰할 문제은행 문항이 없습니다.</p>';
    bindQuestionBankReviewActions();
    return;
  }
  if (!bankState.reviewItems.length) {
    list.innerHTML = '<p class="question-bank-review-empty">현재 목록에서 아직 저장된 풀이 기록이 없습니다. 문제를 풀고 채점하거나 오답노트를 저장하면 여기 모입니다.</p>';
    bindQuestionBankReviewActions();
    return;
  }
  if (!visibleItems.length) {
    list.innerHTML = '<p class="question-bank-review-empty">선택한 필터에 해당하는 풀이 기록이 없습니다.</p>';
    bindQuestionBankReviewActions();
    return;
  }
  list.innerHTML = visibleItems.map((item) => {
    const questionBankId = String(item?.question_bank_id || '');
    const active = bankState.selectedId && bankState.selectedId === questionBankId;
    const saving = bankState.reviewSavingId === questionBankId;
    const updatedAt = formatQuestionBankAttemptUpdatedAt(item?.updated_at || '');
    const meta = [
      String(item?.term || '').trim(),
      String(item?.category || item?.topic || '').trim(),
      questionTypeLabel(item),
      String(item?.session_title || '').trim(),
      updatedAt ? `저장 ${updatedAt}` : '',
    ].filter(Boolean).join(' · ');
    const resultKey = questionBankReviewResultKey(item);
    const resultLabel = QUESTION_ATTEMPT_RESULT_LABELS[resultKey] || String(item?.result_label || '기록');
    const answerText = markdownPreviewText(item?.answer || '').slice(0, 280);
    return `
      <article class="question-bank-review-item${active ? ' is-active' : ''}${saving ? ' is-saving' : ''}">
        <div class="question-bank-review-item-head">
          <div>
            <h3 class="question-bank-review-item-title">${escapeHtml(markdownPreviewText(item?.prompt || '문제'))}</h3>
            ${meta ? `<p class="question-bank-review-item-meta">${escapeHtml(meta)}</p>` : ''}
          </div>
          <span class="question-bank-review-result ${escapeHtml(resultKey)}">${escapeHtml(resultLabel)}</span>
        </div>
        ${reviewFieldHtml('내 답', String(item?.user_answer || '').trim(), '미입력')}
        ${String(item?.wrong_note || '').trim() ? reviewFieldHtml('오답노트', String(item?.wrong_note || '').trim()) : ''}
        ${answerText ? reviewFieldHtml('정답/해설', answerText) : ''}
        <div class="question-bank-review-item-actions">
          <button type="button" class="cs-table-button question-bank-review-jump" data-question-bank-review-id="${escapeHtml(questionBankId)}" ${saving ? 'disabled' : ''}>풀이 보기</button>
          <div class="question-bank-review-judgments" aria-label="풀이 기록 채점 버튼">
            ${[
              ['correct', '맞음'],
              ['ambiguous', '애매함'],
              ['wrong', '틀림'],
              ['unknown', '모름'],
            ].map(([key, label]) => `<button type="button" class="cs-table-button question-bank-review-judgment${resultKey === key ? ' is-active' : ''}" data-question-bank-review-id="${escapeHtml(questionBankId)}" data-question-bank-review-judgment="${escapeHtml(key)}" aria-pressed="${resultKey === key ? 'true' : 'false'}" ${saving ? 'disabled' : ''}>${escapeHtml(label)}</button>`).join('')}
          </div>
        </div>
      </article>`;
  }).join('');
  bindQuestionBankReviewActions();
}

async function loadQuestionBankReview() {
  const questionBankIds = questionBankReviewIds();
  const requestNonce = bankState.reviewNonce + 1;
  bankState.reviewNonce = requestNonce;
  if (!questionBankIds.length) {
    bankState.reviewItems = [];
    bankState.reviewSummary = {total: 0, correct: 0, ambiguous: 0, wrong: 0, unknown: 0, pending: 0, note_count: 0, selected_question_bank_count: 0};
    bankState.reviewError = '';
    bankState.reviewLoaded = true;
    bankState.reviewDirty = false;
    bankState.reviewLoading = false;
    renderQuestionBankReview();
    return;
  }
  bankState.reviewLoading = true;
  bankState.reviewError = '';
  renderQuestionBankReview();
  try {
    const res = await fetch('/api/question-bank/attempts/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      cache: 'no-store',
      body: JSON.stringify(questionBankReviewRequestPayload(questionBankIds)),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    if (requestNonce !== bankState.reviewNonce) return;
    bankState.reviewItems = Array.isArray(data.items) ? data.items : [];
    bankState.reviewSummary = data.summary || null;
    bankState.reviewLoaded = true;
    bankState.reviewDirty = false;
  } catch (error) {
    if (requestNonce !== bankState.reviewNonce) return;
    bankState.reviewItems = [];
    bankState.reviewSummary = null;
    bankState.reviewLoaded = false;
    bankState.reviewDirty = true;
    bankState.reviewError = error.message || String(error);
  } finally {
    if (requestNonce !== bankState.reviewNonce) return;
    bankState.reviewLoading = false;
    renderQuestionBankReview();
  }
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
    const attemptTone = questionAttemptTone(item);
    const attemptStatus = questionAttemptStatusKey(item);
    const prompt = escapeHtml(markdownPreviewText(item.prompt || `문제 ${index + 1}`) || `문제 ${index + 1}`);
    const preview = markdownPreviewText(item.body || item.answer || item.explanation || '').slice(0, 44);
    return {
      id: String(item.question_bank_id || index + 1),
      className: [active ? 'current-row active' : '', attemptStatus === 'wrong' ? 'question-bank-row-state-wrong' : '', attemptStatus === 'correct' ? 'question-bank-row-state-correct' : ''].filter(Boolean).join(' '),
      attributes: {'aria-current': active ? 'true' : 'false'},
      cells: {
        index: `<span class="question-bank-row-number${attemptStatus === 'wrong' ? ' is-wrong' : attemptStatus === 'correct' ? ' is-correct' : ''}">${index + 1}</span>`,
        attempt_status: `<span class="question-bank-summary-pill ${attemptTone}">${escapeHtml(questionAttemptStatusLabel(item))}</span>`,
        prompt: `<button class="question-bank-row-trigger" type="button" data-question-bank-row-index="${index}"><span class="question-bank-item-title">${prompt}</span>${preview ? `<span class="question-bank-item-preview">${escapeHtml(preview)}</span>` : ''}</button>`,
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
  const item = bankState.practiceLoaded ? practiceItem() : selectedItem();
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
  const start = bankState.practiceLoaded ? practiceActiveIndex() : selectedIndex(bankState.practiceStartIndex);
  if (!bankState.practiceLoaded) {
    summary.textContent = `현재 목록 ${bankState.items.length}문항 · ${start + 1}번 선택 · 새 풀이를 시작하세요.`;
    status.innerHTML = [
      `<span class="question-bank-practice-pill">선택 ${escapeHtml(`${start + 1} / ${bankState.items.length}`)}</span>`,
      ...summaryBits(item),
    ].filter(Boolean).join('');
    placeholder.textContent = bankState.error || '문제를 선택하면 문제은행은 숨기고 풀이 화면만 보이도록 전환합니다.';
    placeholder.hidden = false;
    frame.hidden = true;
    applyPracticeViewState();
    return;
  }
  const practiceSummary = finishedPracticeSummary();
  summary.textContent = practiceSummary
    ? `현재 목록 ${bankState.items.length}문항 · 채점 완료 · 점수 ${practiceSummary.scoreLabel} · ${selectedPrompt(item, `문제 ${start + 1}`).slice(0, 58)}`
    : `현재 목록 ${bankState.items.length}문항 · ${start + 1}번부터 풀이 중 · ${selectedPrompt(item, `문제 ${start + 1}`).slice(0, 58)}`;
  status.innerHTML = [
    `<span class="question-bank-practice-pill">현재 ${escapeHtml(`${start + 1} / ${bankState.items.length}`)}</span>`,
    practiceSummary ? `<span class="question-bank-practice-pill attempt-correct">점수 ${escapeHtml(practiceSummary.scoreLabel)}</span>` : '',
    practiceSummary ? `<span class="question-bank-practice-pill attempt-correct">맞음 ${escapeHtml(String(practiceSummary.correct || 0))}</span>` : '',
    practiceSummary ? `<span class="question-bank-practice-pill attempt-wrong">오답 ${escapeHtml(String(practiceSummary.wrongCount || 0))}</span>` : '',
    ...summaryBits(item),
  ].filter(Boolean).join('');
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
    : `총 ${total} · 현재 ${returned}문항 · 필터 ${filterCount}`;
  error.textContent = bankState.error || '';
  renderPracticeToggle();
  renderHeader();
  renderOverviewCards();
  renderQuestionBankReview();
  renderCategoryGuideDialog();
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
      launch(index);
    },
    onColumnMove: (sourceKey, targetKey) => {
      window.CSTableShell.moveColumnOrder(QUESTION_BANK_COLUMN_ORDER_KEY, QUESTION_BANK_COLUMNS.map((column) => column.key), sourceKey, targetKey);
      renderTable();
    },
  });
  bindQuestionBankRowTriggerActions();
}

function ensureSelectedRowVisible() {
  const row = document.querySelector('#bankPageList [aria-current="true"]');
  if (!row || typeof row.scrollIntoView !== 'function') return;
  row.scrollIntoView({block: 'nearest', inline: 'nearest'});
}


function applyPracticeLaunch(startIndex = 0, {reveal = true, sessionState = bankState.practiceSessionState, launchItems = null} = {}) {
  launch(startIndex, {reveal, sessionState, launchItems}).catch(() => {});
}

function renderLaunchState() {
  renderTable();
  ensureSelectedRowVisible();
  renderPracticePane();
}
function resetPracticeSession({message = '', collapse = true} = {}) {
  bankState.practiceLoaded = false;
  bankState.practiceActiveId = '';
  bankState.practiceSummary = null;
  bankState.practiceSessionState = null;
  bankState.practiceResultSetKey = '';
  if (collapse) bankState.practiceCollapsed = true;
  if (message) bankState.error = message;
}

async function launch(startIndex = 0, {reveal = true, single = false} = {}) {
  const syncLaunchUi = typeof renderLaunchState === 'function'
    ? renderLaunchState
    : () => {
      renderTable();
      ensureSelectedRowVisible();
      renderPracticePane();
    };
  if (!bankState.items.length) {
    bankState.error = '문제은행 목록이 비어 있습니다.';
    syncLaunchUi();
    return false;
  }
  const options = arguments[1] && typeof arguments[1] === 'object' ? arguments[1] : {};
  const safeStart = Math.max(0, Math.min(bankState.items.length - 1, Number.isInteger(startIndex) ? startIndex : 0));
  const sourceItem = bankState.items[safeStart];
  const requestedLaunchItems = Array.isArray(options.launchItems) ? options.launchItems.filter((item) => item && typeof item === 'object') : null;
  const launchItems = requestedLaunchItems?.length
    ? requestedLaunchItems
    : single
      ? [{...sourceItem, session_mode: 'practice', sessionMode: 'practice'}]
      : bankState.items;
  const frameStartIndex = single ? 0 : safeStart;
  const targetId = String(sourceItem?.question_bank_id || '');
  const currentId = String(bankState.practiceActiveId || '');
  let nextSessionState = options.sessionState && typeof options.sessionState === 'object' ? options.sessionState : null;
  if (bankState.practiceLoaded && targetId && targetId === currentId && !nextSessionState && !single) {
    if (reveal) setPracticeCollapsed(false);
    ensureSelectedRowVisible();
    return false;
  }
  if (!nextSessionState) {
    try {
      if (!bankState.reviewLoaded || bankState.reviewDirty) await loadQuestionBankReview();
      nextSessionState = practiceLaunchSessionState(launchItems, {forcePractice: single});
    } catch (_error) {
      nextSessionState = null;
    }
  }
  if (bankState.practiceLoaded && embeddedPracticeHasUnsavedState() && !confirmPracticeRestart(safeStart)) {
    bankState.error = '현재 풀이 세트를 유지했습니다. 다시 시작하려면 선택한 행을 다시 누르세요.';
    syncLaunchUi();
    return false;
  }
  pendingPracticeLaunch = bankState.loading
    ? {startIndex: frameStartIndex, reveal, sessionState: nextSessionState, launchItems}
    : null;
  bankState.selectedId = targetId;
  bankState.practiceActiveId = targetId;
  bankState.practiceLoaded = true;
  bankState.practiceStartIndex = safeStart;
  bankState.practiceSummary = null;
  bankState.practiceSessionState = nextSessionState;
  if (reveal) setPracticeCollapsed(false);
  persistFilterState();
  restartPracticeFrame(frameStartIndex, nextSessionState, launchItems);
  bankState.error = '';
  syncLaunchUi();
  return true;
}
async function loadQuestionBankPage() {
  const requestId = activeQuestionBankLoadRequest + 1;
  activeQuestionBankLoadRequest = requestId;
  if (questionBankLoadAbortController) {
    questionBankLoadAbortController.abort();
  }
  const controller = typeof window.AbortController === 'function' ? new window.AbortController() : null;
  questionBankLoadAbortController = controller;
  const selectedIdBeforeRequest = String(bankState.selectedId || '');
  const practiceActiveIdBeforeRequest = String(bankState.practiceActiveId || '');
  let currentRestoredSelectionState = null;
  let currentRestoredPracticeState = null;
  let restorePracticePane = false;
  try {
    currentRestoredSelectionState = restoredSelectionState ?? null;
  } catch (_error) {}
  try {
    currentRestoredPracticeState = restoredPracticeState ?? null;
  } catch (_error) {}
  try {
    restorePracticePane = Boolean(shouldRestorePracticePane);
  } catch (_error) {}
  const restoredSelectionSelectedId = String(currentRestoredSelectionState?.selectedId || '');
  const restoredPracticeSelectedId = String(currentRestoredPracticeState?.selectedId || '');
  const shouldPreferPracticeSelection = Boolean(currentRestoredPracticeState?.loaded);
  const shouldRestoreSelectionByIndex = !selectedIdBeforeRequest && !bankState.practiceLoaded && !shouldPreferPracticeSelection && Number.isInteger(currentRestoredSelectionState?.startIndex);
  bankState.loading = true;
  bankState.error = '';
  bankState.reviewItems = [];
  bankState.reviewSummary = null;
  bankState.reviewLoaded = false;
  bankState.reviewDirty = true;
  bankState.reviewError = '';
  bankState.reviewLoading = false;
  syncUrl();
  renderTable();
  renderPracticePane();
  try {
    const data = await fetchEntries({signal: controller?.signal});
    if (requestId !== activeQuestionBankLoadRequest) return;
    const currentSelectedId = String(bankState.selectedId || '');
    const targetSelectedId = currentSelectedId
      || selectedIdBeforeRequest
      || (shouldPreferPracticeSelection ? restoredPracticeSelectedId : '')
      || restoredSelectionSelectedId
      || restoredPracticeSelectedId;
    bankState.items = Array.isArray(data.items) ? data.items : [];
    bankState.summary = data.summary || {total: bankState.items.length, returned: bankState.items.length};
    if (bankState.practiceSummary && !questionBankSliceMatchesPracticeSummary(bankState.practiceSummary)) {
      bankState.practiceSummary = null;
    }
    populateTopicOptions(bankState.summary?.available_topics || [], filterValues().topic);
    populateFieldNameOptions(bankState.summary?.available_field_names || [], filterValues().field_name);
    populateIssuerOptions(bankState.summary?.available_issuers || [], filterValues().issuer);
    populateCategoryOptions(bankState.summary?.available_categories || [], filterValues().category);
    const nextIndex = bankState.items.findIndex((item) => String(item?.question_bank_id || '') === targetSelectedId);
    const resolvedSelectionIndex = nextIndex >= 0
      ? nextIndex
      : shouldRestoreSelectionByIndex
        ? Math.max(0, Math.min(bankState.items.length - 1, currentRestoredSelectionState.startIndex))
        : 0;
    bankState.selectedId = String(bankState.items[resolvedSelectionIndex]?.question_bank_id || '');
    bankState.practiceStartIndex = resolvedSelectionIndex;
    const preservingHiddenPractice = bankState.practiceLoaded && bankState.practiceCollapsed && !pendingPracticeLaunch;
    if (!bankState.items.length) {
      pendingPracticeLaunch = null;
      if (typeof shouldRestorePracticePane !== 'undefined') shouldRestorePracticePane = false;
      if (typeof restoredSelectionState !== 'undefined') restoredSelectionState = null;
      if (typeof restoredPracticeState !== 'undefined') restoredPracticeState = null;
      bankState.selectedId = '';
      bankState.practiceStartIndex = 0;
      if (preservingHiddenPractice) {
        resetPracticeSession({
          message: '현재 필터에서 숨겨둔 풀이 문항이 제외되었습니다. 현재 선택 문항으로 새 풀이를 시작하세요.',
        });
      } else {
        resetPracticeSession();
      }
      persistFilterState();
    } else if (pendingPracticeLaunch) {
      const launchRequest = pendingPracticeLaunch;
      pendingPracticeLaunch = null;
      if (typeof shouldRestorePracticePane !== 'undefined') shouldRestorePracticePane = false;
      if (typeof restoredPracticeState !== 'undefined') restoredPracticeState = null;
      persistFilterState();
      applyPracticeLaunch(launchRequest.startIndex, {reveal: launchRequest.reveal, sessionState: launchRequest.sessionState, launchItems: launchRequest.launchItems});
    } else if (restorePracticePane && !bankState.practiceLoaded) {
      const restoreIndex = nextIndex >= 0
        ? nextIndex
        : Math.max(0, Math.min(bankState.items.length - 1, Number.isInteger(currentRestoredPracticeState?.startIndex) ? currentRestoredPracticeState.startIndex : bankState.practiceStartIndex));
      if (typeof shouldRestorePracticePane !== 'undefined') shouldRestorePracticePane = false;
      if (typeof restoredPracticeState !== 'undefined') restoredPracticeState = null;
      persistFilterState();
      applyPracticeLaunch(restoreIndex, {reveal: true});
    } else if (bankState.practiceLoaded && nextIndex < 0) {
      if (preservingHiddenPractice) {
        resetPracticeSession({
          message: '현재 필터에서 숨겨둔 풀이 문항이 제외되었습니다. 현재 선택 문항으로 새 풀이를 시작하세요.',
        });
      } else {
        resetPracticeSession();
      }
      persistFilterState();
    } else {
      pendingPracticeLaunch = null;
      if (bankState.practiceLoaded && !bankState.practiceActiveId) bankState.practiceActiveId = practiceActiveIdBeforeRequest || bankState.selectedId;
      persistFilterState();
    }
  } catch (error) {
    if (error?.name === 'AbortError' || requestId !== activeQuestionBankLoadRequest) return;
    bankState.items = [];
    bankState.summary = {total: 0, returned: 0};
    bankState.reviewItems = [];
    bankState.reviewSummary = null;
    bankState.reviewLoaded = false;
    bankState.reviewDirty = true;
    bankState.reviewError = '';
    bankState.reviewLoading = false;
    populateTopicOptions([], filterValues().topic);
    populateFieldNameOptions([], filterValues().field_name);
    populateIssuerOptions([], filterValues().issuer);
    populateCategoryOptions([], filterValues().category);
    bankState.error = error.message || String(error);
    pendingPracticeLaunch = null;
    bankState.practiceLoaded = false;
    bankState.practiceActiveId = '';
    persistFilterState();
  } finally {
    if (requestId !== activeQuestionBankLoadRequest) return;
    if (questionBankLoadAbortController === controller) {
      questionBankLoadAbortController = null;
    }
    bankState.loading = false;
    renderTable();
    renderPracticePane();
    if (!bankState.items.length) {
      bankState.practiceResultSetKey = '';
      renderQuestionBankReview();
      return;
    }
    if (bankState.reviewCollapsed) {
      renderQuestionBankReview();
      return;
    }
    await ensureQuestionBankReviewLoaded({force: true});
  }
}

restoreFilterState();
setPracticeCollapsed(canRestorePersistedQuestionBankState ? persistedPracticeCollapsed() : true, {persist: false});
if (!canRestorePersistedQuestionBankState) persistPracticeCollapsedState(true);
setFiltersCollapsed(persistedFiltersCollapsed(), {persist: false});
setReviewCollapsed(true);
renderTable();
renderPracticePane();
loadQuestionBankPage().catch(() => {});

$('bankPageRefreshBtn')?.addEventListener('click', () => loadQuestionBankPage().catch(() => {}));
$('bankPageLaunchBtn')?.addEventListener('click', () => launch(0));
$('bankPageLaunchSelectedBtn')?.addEventListener('click', () => launch(selectedIndex(bankState.practiceStartIndex)));
$('bankPageLaunchSingleBtn')?.addEventListener('click', () => launch(selectedIndex(bankState.practiceStartIndex), {single: true}));
$('bankPageTogglePracticeBtn')?.addEventListener('click', togglePracticeCollapsed);
$('bankPageToggleFiltersBtn')?.addEventListener('click', toggleFiltersCollapsed);
$('bankPageToggleReviewBtn')?.addEventListener('click', toggleReviewCollapsed);
$('bankPageResetFiltersBtn')?.addEventListener('click', resetFilters);
$('bankPageCategoryGuideBtn')?.addEventListener('click', openCategoryGuideDialog);
$('bankPageCategoryGuideCloseBtn')?.addEventListener('click', () => closeCategoryGuideDialog());
$('bankPageCategoryGuideDialog')?.addEventListener('click', (event) => {
  if (event.target === event.currentTarget) closeCategoryGuideDialog();
});
$('bankPageCategoryGuideDialog')?.addEventListener('keydown', (event) => {
  handleOpenCategoryGuideDialogKeydown(event);
});
$('bankPagePracticeExitBtn')?.addEventListener('click', () => setPracticeCollapsed(true));

['bankPageQueryInput', 'bankPageTopicInput', 'bankPageSourceInput', 'bankPageSectionInput'].forEach((id) => {
  $(id)?.addEventListener('input', scheduleLoad);
  $(id)?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      persistFilterState();
      window.clearTimeout(pendingLoadTimer);
      loadQuestionBankPage().catch(() => {});
    }
  });
});

['bankPageAttemptStatusSelect', 'bankPageFieldInput', 'bankPageCategoryInput', 'bankPageIssuerInput', 'bankPageDifficultySelect', 'bankPageTypeSelect'].forEach((id) => {
  $(id)?.addEventListener('change', () => {
    persistFilterState();
    loadQuestionBankPage().catch(() => {});
  });
});
window.addEventListener('keydown', (event) => {
  handleOpenCategoryGuideDialogKeydown(event);
});

window.addEventListener('message', (event) => {
  if (event.origin && event.origin !== window.location.origin) return;
  const data = event?.data;
  if (!data || data.type !== 'cs-flashcards-question-bank-updated') return;
  applyEmbeddedQuestionBankUpdate(data.item || null, data.summary || null, data.finishedAt || '');
});

function applyQuestionBankLayoutMode(mode) {
  const horizontal = mode === 'horizontal';
  document.body.classList.toggle('question-bank-layout-horizontal', horizontal);
  const practiceCard = document.querySelector('.question-bank-practice-card');
  if (practiceCard) practiceCard.dataset.layoutMode = horizontal ? 'horizontal' : 'vertical';
}

window.addEventListener('message', (event) => {
  const frame = $('bankPagePracticeFrame');
  if (!frame || event.source !== frame.contentWindow) return;
  if (event.origin && event.origin !== window.location.origin) return;
  const data = event?.data;
  if (!data || data.type !== 'cs-flashcards-question-layout') return;
  applyQuestionBankLayoutMode(data.mode);
});
