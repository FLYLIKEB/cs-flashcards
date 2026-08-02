import json
import subprocess
import textwrap
import unittest
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def static_text(name: str) -> str:
    return (ROOT / 'static' / name).read_text(encoding='utf-8')


def app_js() -> str:
    return static_text('app.js')


def index_html() -> str:
    return static_text('index.html')


def wiki_html() -> str:
    return static_text('wiki.html')


def question_bank_html() -> str:
    return static_text('question-bank.html')


def wiki_js() -> str:
    return static_text('wiki.js')


def question_bank_js() -> str:
    return static_text('question-bank.js')


def style_css() -> str:
    return static_text('style.css')


def table_shell_css() -> str:
    return static_text('table-shell.css')


def calendar_html() -> str:
    return static_text('calendar.html')


def calendar_js() -> str:
    return static_text('calendar.js')


class StaticFrontendSmokeTests(unittest.TestCase):
    def run_node(self, script: str) -> str:
        completed = subprocess.run(
            ['node', '-e', script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    def run_question_bank_contract_batch(self):
        script = textwrap.dedent(
            """
            const source = __QUESTION_BANK_SOURCE__;
            function sliceBetween(startMarker, endMarker, label) {
              const start = source.indexOf(startMarker);
              const end = source.indexOf(endMarker, start);
              if (start < 0 || end < 0) throw new Error(`${label} not found`);
              return source.slice(start, end);
            }
            const contractChecks = {
              filterRefresh: async () => {
                const fnSource = sliceBetween('async function loadQuestionBankPage() {', '\\nrestoreFilterState();', 'loadQuestionBankPage');
                const bankState = {
                  loading: false,
                  error: 'stale',
                  items: [],
                  summary: {},
                  selectedId: 'beta',
                  practiceActiveId: '',
                  practiceLoaded: false,
                  practiceCollapsed: true,
                  practiceStartIndex: 4,
                  practiceResultSetKey: 'keep',
                  reviewCollapsed: true,
                  reviewLoaded: false,
                  reviewDirty: true,
                  reviewItems: [],
                  reviewSummary: null,
                  reviewError: '',
                  reviewLoading: false,
                };
                let activeQuestionBankLoadRequest = 0;
                let questionBankLoadAbortController = null;
                let restoredPracticeState = null;
                let pendingPracticeLaunch = null;
                let restorePracticePaneOnReload = false;
                const window = {AbortController: class { constructor() { this.signal = {}; } abort() {} }};
                const syncUrl = () => {};
                const renderTable = () => {};
                const renderPracticePane = () => {};
                const renderQuestionBankReview = () => {};
                const filterValues = () => ({topic: '', field_name: '', issuer: '', category: ''});
                const populateTopicOptions = () => {};
                const populateFieldNameOptions = () => {};
                const populateIssuerOptions = () => {};
                const populateCategoryOptions = () => {};
                const persistFilterState = () => {};
                const applyPracticeLaunch = () => {};
                const ensureQuestionBankReviewLoaded = async () => { reviewCalls += 1; };
                let launchCalls = 0;
                let reviewCalls = 0;
                const launch = async () => { launchCalls += 1; };
                const fetchEntries = async () => ({
                  items: [
                    {question_bank_id: 'alpha'},
                    {question_bank_id: 'beta'},
                  ],
                  summary: {total: 2, returned: 2},
                });
                eval(fnSource);
                await loadQuestionBankPage();
                return {
                  launchCalls,
                  reviewCalls,
                  loading: bankState.loading,
                  selectedId: bankState.selectedId,
                  practiceStartIndex: bankState.practiceStartIndex,
                  itemCount: bankState.items.length,
                  reviewLoading: bankState.reviewLoading,
                };
              },
              reviewToggle: async () => {
                const fnSource = sliceBetween('function reviewNeedsRefresh() {', '\\nfunction renderFilterToggle() {', 'review toggle block');
                const elements = {
                  bankPageToggleReviewBtn: {textContent: '', attrs: {}, setAttribute(name, value) { this.attrs[name] = value; }},
                  bankPageReviewBody: {hidden: true},
                };
                const bankState = {
                  loading: false,
                  reviewCollapsed: true,
                  reviewLoaded: false,
                  reviewDirty: true,
                  reviewError: '',
                };
                const $ = (id) => elements[id] || null;
                let renderCalls = 0;
                const renderQuestionBankReview = () => { renderCalls += 1; };
                let loadCalls = 0;
                const loadQuestionBankReview = async () => {
                  loadCalls += 1;
                  bankState.reviewLoaded = true;
                  bankState.reviewDirty = false;
                };
                eval(fnSource);
                setReviewCollapsed(false);
                await Promise.resolve();
                return {
                  collapsed: bankState.reviewCollapsed,
                  loadCalls,
                  renderCalls,
                  buttonText: elements.bankPageToggleReviewBtn.textContent,
                  expanded: elements.bankPageToggleReviewBtn.attrs['aria-expanded'],
                  hidden: elements.bankPageReviewBody.hidden,
                };
              },
              explicitLaunch: async () => {
                const fnSource = sliceBetween('async function launch(startIndex = 0, {reveal = true} = {}) {', '\\nasync function loadQuestionBankPage() {', 'launch');
                const bankState = {
                  items: [
                    {question_bank_id: 'alpha'},
                    {question_bank_id: 'beta'},
                  ],
                  error: '',
                  loading: false,
                  practiceLoaded: true,
                  practiceCollapsed: false,
                  practiceStartIndex: 0,
                  practiceSessionState: null,
                  practiceActiveId: 'alpha',
                  selectedId: 'alpha',
                  practiceSummary: null,
                };
                const setPracticeCollapsed = () => {};
                const persistFilterState = () => {};
                const renderTable = () => {};
                const renderPracticePane = () => {};
                const ensureSelectedRowVisible = () => {};
                const embeddedPracticeHasUnsavedState = () => true;
                let confirmCalls = 0;
                const confirmPracticeRestart = () => {
                  confirmCalls += 1;
                  return false;
                };
                let restartCalls = 0;
                const restartPracticeFrame = () => { restartCalls += 1; };
                let pendingPracticeLaunch = null;
                eval(fnSource);
                const launched = await launch(1);
                return {
                  launched,
                  confirmCalls,
                  restartCalls,
                  pendingPracticeLaunch,
                  practiceLoaded: bankState.practiceLoaded,
                  practiceStartIndex: bankState.practiceStartIndex,
                  selectedId: bankState.selectedId,
                  practiceActiveId: bankState.practiceActiveId,
                  error: bankState.error,
                };
              },
            };
            (async () => {
              const results = {};
              for (const [name, check] of Object.entries(contractChecks)) {
                results[name] = await check();
              }
              process.stdout.write(JSON.stringify(results));
            })().catch((error) => {
              console.error(error);
              process.exit(1);
            });
            """
        ).replace('__QUESTION_BANK_SOURCE__', json.dumps(question_bank_js()))
        return json.loads(self.run_node(script))


    def test_index_page_smoke_has_core_navigation_and_question_panel(self):
        self.assertIn('id="calendarPageLink"', index_html())
        self.assertIn('id="wikiHomeLink"', index_html())
        self.assertIn('id="questionBankPageLink"', index_html())
        self.assertIn('class="question-panel"', index_html())
        self.assertIn('id="questionBankBrowser"', index_html())

    def test_question_bank_page_smoke_has_filter_table_and_practice_shell(self):
        self.assertIn('id="bankPageToggleFiltersBtn"', question_bank_html())
        self.assertIn('id="bankPageList"', question_bank_html())
        self.assertIn('<input id="bankPageTopicInput"', question_bank_html())
        self.assertIn('id="bankPageTopicOptions"', question_bank_html())
        self.assertIn('<select id="bankPageAttemptStatusSelect"', question_bank_html())
        self.assertIn('<select id="bankPageFieldInput"', question_bank_html())
        self.assertIn('<select id="bankPageCategoryInput"', question_bank_html())
        self.assertIn('<select id="bankPageIssuerInput"', question_bank_html())

        self.assertIn('문제 풀이 · 문제은행', question_bank_html())
        self.assertIn('id="bankPageTogglePracticeBtn"', question_bank_html())
        self.assertIn('id="bankPageHeaderSummary"', question_bank_html())
        self.assertIn('id="bankPageOverviewCards"', question_bank_html())
        self.assertIn('id="bankPageReviewSummary"', question_bank_html())
        self.assertIn('id="bankPageToggleReviewBtn"', question_bank_html())
        self.assertIn('id="bankPageReviewBody"', question_bank_html())
        self.assertIn('id="bankPageReviewStats"', question_bank_html())
        self.assertIn('id="bankPageReviewFilters"', question_bank_html())
        self.assertIn('id="bankPageReviewList"', question_bank_html())
        self.assertIn('id="bankPageResetFiltersBtn"', question_bank_html())
        self.assertIn('id="bankPageSelectionSummary"', question_bank_html())
        self.assertIn('id="bankPagePracticeStatus"', question_bank_html())
        self.assertIn('question-bank-table-selection', question_bank_html())
        self.assertIn('id="bankPageCategoryGuideBtn"', question_bank_html())
        self.assertIn('id="bankPageCategoryGuideDialog"', question_bank_html())
        self.assertIn('bankPageHeaderPracticeToggle', question_bank_js())
        self.assertNotIn('bankPageOpenPracticeTab', question_bank_html())
        self.assertIn('/api/question-bank', question_bank_js())
        self.assertIn('QUESTION_BANK_LAUNCH_KEY', question_bank_js())
        self.assertIn('QUESTION_BANK_PRACTICE_COLLAPSED_KEY', question_bank_js())
        self.assertIn('function populateTopicOptions(', question_bank_js())
        self.assertIn('function populateFieldNameOptions(', question_bank_js())
        self.assertIn('function populateIssuerOptions(', question_bank_js())
        self.assertIn('function populateCategoryOptions(', question_bank_js())
        self.assertIn('available_topics', question_bank_js())
        self.assertIn('available_field_names', question_bank_js())
        self.assertIn('available_issuers', question_bank_js())
        self.assertIn('available_categories', question_bank_js())
        self.assertIn('question-keyword-link', question_bank_js())
        self.assertIn('card_query=', question_bank_js())
        self.assertIn('cs-flashcards-question-bank-updated', question_bank_js())
        self.assertIn("window.addEventListener('message'", question_bank_js())
        self.assertIn('function renderHeader()', question_bank_js())
        self.assertIn('function renderOverviewCards()', question_bank_js())
        self.assertIn('function renderCategoryGuideDialog()', question_bank_js())
        self.assertIn('function openCategoryGuideDialog()', question_bank_js())
        self.assertIn('function closeCategoryGuideDialog(', question_bank_js())
        self.assertIn('function questionBankItemMatchesAttemptStatusFilter(item, attemptStatus = filterValues().attempt_status)', question_bank_js())
        self.assertIn("if (!questionBankItemMatchesAttemptStatusFilter(nextItem))", question_bank_js())
        self.assertIn('function renderActiveFilters()', question_bank_js())
        self.assertIn('function renderSelectionSummary()', question_bank_js())
        self.assertIn('function resetFilters()', question_bank_js())
        self.assertIn('function bindHeaderChipActions()', question_bank_js())
        self.assertIn('function ensureSelectedRowVisible()', question_bank_js())
        self.assertIn('function scheduleLoad()', question_bank_js())
        self.assertIn('id="bankPagePracticeFrame"', question_bank_html())
        self.assertIn('id="bankPagePracticePlaceholder"', question_bank_html())
        self.assertIn('function practiceFrameUrl()', question_bank_js())
        self.assertIn('function setPracticeCollapsed(', question_bank_js())
        self.assertIn('function embeddedPracticeHasUnsavedState()', question_bank_js())
        self.assertIn('onRowActivate: (_row, index) => {', question_bank_js())
        self.assertIn('launch(index);', question_bank_js())
        self.assertIn('function ensureQuestionBankReviewLoaded(', question_bank_js())
        self.assertIn('question-bank-embed=1', question_bank_js())
        self.assertIn("get('question-bank-embed') === '1'", app_js())
        self.assertIn('function restartPracticeFrame(startIndex, sessionState = bankState.practiceSessionState)', question_bank_js())
        self.assertIn('function practiceLaunchPayload(startIndex, sessionState = bankState.practiceSessionState)', question_bank_js())
        self.assertIn("if (sessionState && typeof sessionState === 'object') payload.sessionState = sessionState;", question_bank_js())
        self.assertIn('function confirmPracticeRestart(startIndex)', question_bank_js())
        self.assertIn('if (bankState.practiceLoaded && embeddedPracticeHasUnsavedState() && !confirmPracticeRestart(safeStart)) {', question_bank_js())
        self.assertIn('restartPracticeFrame(safeStart, null);', question_bank_js())

    def test_calendar_page_smoke_has_tabs_and_detail_drawer(self):
        self.assertIn('id="mainTabCalendarBtn"', calendar_html())
        self.assertIn('id="mainTabListBtn"', calendar_html())
        self.assertIn('id="calendarDetailDrawer"', calendar_html())
        self.assertIn('id="calendarDetailCloseBtn"', calendar_html())

    def test_wiki_page_smoke_has_sidebar_search_and_status_region(self):
        self.assertIn('id="wikiSearchToggleBtn"', wiki_html())
        self.assertIn('id="wikiSearch"', wiki_html())
        self.assertIn('id="wikiSidebarToggleBtn"', wiki_html())
        self.assertIn('id="wikiSidebar"', wiki_html())
        self.assertIn('id="wikiSearchToggleBtn"', wiki_html())
        self.assertIn('id="wikiStatus"', wiki_html())

    def test_app_js_smoke_keeps_embedded_question_bank_browser_hooks(self):
        self.assertIn('function renderQuestionBankBrowser()', app_js())
        self.assertIn('function loadQuestionBankBrowser()', app_js())
        self.assertIn('function openQuestionBankSession(startIndex = 0)', app_js())
        self.assertIn('questionBankToggleBtn', app_js())

    def test_question_bank_js_smoke_keeps_load_launch_and_persistence_hooks(self):
        self.assertIn("const QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';", question_bank_js())
        self.assertIn('function loadQuestionBankPage()', question_bank_js())
        self.assertIn('function launch(startIndex = 0, {reveal = true} = {})', question_bank_js())
        self.assertIn('window.sessionStorage.setItem(QUESTION_BANK_LAUNCH_KEY', question_bank_js())
        self.assertIn('question-bank-filters-collapsed', question_bank_js())
        self.assertIn('let restorePracticePaneOnReload = isReloadNavigation() && Boolean(restoredPracticeState?.loaded) && !persistedPracticeCollapsed();', question_bank_js())
        self.assertIn('loaded: bankState.practiceLoaded,', question_bank_js())
    def test_calendar_js_smoke_keeps_tab_and_drawer_focus_handlers(self):
        self.assertIn('function setMainTab(tabId)', calendar_js())
        self.assertIn('function openDetailDrawer()', calendar_js())
        self.assertIn('function closeDetailDrawer({ restoreFocus = true } = {})', calendar_js())
        self.assertIn("if (event.key === 'Escape' && calendarState.detailOpen)", calendar_js())

    def test_wiki_js_smoke_keeps_sidebar_persistence_and_status_updates(self):
        self.assertIn("const WIKI_SIDEBAR_STATE_KEY = 'csFlashcardsWikiSidebar:v1';", wiki_js())
        self.assertIn('function toggleWikiSidebar(force = !wikiState.sidebarOpen)', wiki_js())
        self.assertIn('function wikiStatus(text, isError = false)', wiki_js())
        self.assertIn('wikiStatus(`검색 결과 ${matches.length}건`);', wiki_js())

    def test_css_smoke_keeps_question_and_table_shell_visibility_rules(self):
        self.assertIn('.question-panel[hidden]', style_css())
        self.assertIn('display: none !important', style_css())
    def test_free_tts_naturalness_controls_are_present(self):
        self.assertIn('id="speechVoice"', index_html())
        self.assertIn('한국어 고품질/Siri/Google/Microsoft 음성', index_html())
        self.assertIn('function populateSpeechVoiceSelect()', app_js())
        self.assertIn('function splitSpeechText(text)', app_js())
        self.assertIn('function expandSpeechItemForPauses(item)', app_js())
        self.assertIn('isPause: true', app_js())
        self.assertIn('window.speechSynthesis.onvoiceschanged = populateSpeechVoiceSelect', app_js())


    def test_question_practice_controls_are_present(self):
        self.assertIn('.question-panel[hidden]', style_css())
        self.assertIn('display: none !important', style_css())
        self.assertNotIn('id="questionModeBtn"', index_html())
        self.assertNotIn('id="questionPracticeBtn"', index_html())
        for snippet in [
            'id="questionPanel"',
            'id="questionSessionModeSelect"',
            'id="questionSessionReview"',
            'id="questionTypeShort"',
            'id="questionTypeSubjective"',
            'id="questionTypeMultipleChoice"',
            'id="questionTypeEssay"',
            'id="questionCountSelect"',
            'id="questionTimeLimitSelect"',
            'id="generateQuestionsBtn"',
            'id="openQuestionImportBtn"',
            'id="questionBankToggleBtn"',
            'id="questionBankBrowser"',
            'id="questionBankQueryInput"',
            'id="questionBankAttemptStatusSelect"',
            'id="questionBankTopicInput"',
            '<input id="questionBankTopicInput"',
            'id="questionBankTopicOptions"',
            'id="questionBankFieldInput"',
            '<select id="questionBankFieldInput"',
            'id="questionBankCategoryInput"',
            '<select id="questionBankCategoryInput"',
            'id="questionBankIssuerInput"',
            '<select id="questionBankIssuerInput"',
            '<th scope="col">키워드</th>',

            'id="questionBankSourceInput"',
            'id="questionBankDifficultySelect"',
            'id="questionBankTypeSelect"',
            'id="questionBankSectionInput"',
            'id="questionBankList"',
            'id="questionBankLoadBtn"',
            'id="questionBankCloseBtn"',
            'class="question-bank-table"',

            'id="finishQuestionSessionBtn"',
            'id="openAiQuizSearchBtn"',
            'id="questionHistoryBtn"',
            'id="revealAnswerBtn"',
            'id="openQuestionCardBtn"',

        ]:
            self.assertIn(snippet, index_html())
        for snippet in [
            'questionMode: false',
            'questionSessionId:',
            'questionSessionTitle:',
            "questionSessionMode: 'practice'",
            'QUESTION_SESSION_MODE_LABELS',
            'BOK_MOCK_CONFIG',
            'function applyQuestionSessionModePreset(',
            'function questionRevealLocked(',
            'function generateBokExamQuestions(',
            'function populateQuestionBankIssuerOptions(',
            'function findCardByKeyword(',
            'function renderQuestionKeywordLinks(',
            'function goToQuestionKeyword(',
            'function renderQuestionSessionReview(',
            'function generateQuestionsFromCurrentFilter()',
            '/api/questions/generate',
            '/api/question-bank',
            'function fetchQuestionBankEntries()',
            'function renderQuestionBankBrowser()',
            'function questionBankItemMatchesAttemptStatusFilter(item, attemptStatus = questionBankFilterValues().attempt_status)',
            'if (reloadOnFilterMismatch && !nextBankItem)',
            'function syncQuestionBankAttemptState(question, {reloadOnFilterMismatch = true} = {})',
            'loadQuestionBankBrowser().catch(() => {});',
            "cache: 'no-store'",
            "params.set('__ts', String(Date.now()))",
            'function openQuestionBankSession(startIndex = 0)',
            'function consumePendingQuestionBankLaunch()',
            'PENDING_QUESTION_BANK_LAUNCH_KEY',
            'function renderQuestionMarkdown(source)',
            'question-md-image',
            'question-bank-item',
            'function renderQuestionPanel()',
            'function revealQuestionAnswer()',
            'function openQuestionSourceCard()',
            'question-answer-meta',
            'data-question-open-card="1"',
            'question-keyword-link',
            'function openQuestionPracticeFromMenu()',
            'toggleQuestionMode(true)',
            'function openQuestionImportDialog()',
            'function importQuestionsFromText()',
            'function importedQuestionSetPayload(rawText)',
            "sessionMode: normalizeQuestionSessionMode(parsed.session_mode ?? parsed.exam_mode ?? parsed.mode ?? 'practice')",
            'function buildImportedQuestions(rawQuestions)',
            'expected_time_minutes',
            'answer_guide',
            'function resolveImportedCard(rawQuestion, index)',
            'questionImportInput',
            'openQuestionImportBtn',
            'questionImportApplyBtn',
            'function aiQuizSearchPrompt()',
            'function openAiQuizSearch(event = null)',
            '자체 퀴즈생성 기능을 활용해줘',
            'AI_QUIZ_PROMPT_TYPE_ORDER',
            'googleAiSearchUrl(aiQuizSearchPrompt())',
            'question-mode-active',
            '/api/questions/attempt',
            'responseErrorText(res)',
            'function saveQuestionAttempt(question, {quiet = false} = {})',
            'function setQuestionJudgment(judgment)',
            'syncQuestionBankAttemptState(current);',
            "syncQuestionBankAttemptState(current, {reloadOnFilterMismatch: index === state.questionIndex});",
            'function finishQuestionSession()',
            'function questionHasSubmittedAnswer(question)',
            'function markUnansweredQuestionWrong(question, answeredAt = new Date().toISOString())',
            'function finalizeQuestionJudgment(question, answeredAt = new Date().toISOString())',
            'function questionSessionScoreSummary(questions = state.questions)',
            'strong>${escapeHtml(sessionSummary.scoreLabel)}</strong>',
            "summary: questionSessionScoreSummary(),",
            "finalizeQuestionJudgment(question, finishedAt);",
            'function saveCurrentWrongNote()',
            'question-answer-input',
            'question-wrong-note',
            'question-session-lock',
            'question-session-summary',
            '정답 잠금',
            'questionTimeLimitSelect',
            'finishQuestionSessionBtn',
            'new URLSearchParams(window.location.search)',
            '/api/questions/attempts',
            'function openQuestionHistory()',
            'function loadQuestionHistory()',
            'function setQuestionHistoryFilter(filter)',
            'questionHistoryBtn',
            'data-question-history-filter',
            'function markQuestionSourceCard(status)',
            'data-question-mark',
            'data-question-judgment',
            'data-question-edit="1"',
            'questionBankEditDialog',
            'questionBankEditPromptInput',
            'function openQuestionBankEditDialog()',
            'function saveCurrentQuestionBankEdit()',
            '/api/question-bank/',
            'data-question-answer-refine',
            'questionAnswerRefineInstruction',
            'function refineCurrentQuestionAnswer()',
            '/ai-refine-answer',
            'data-question-finish-session',
            '제출하고 정답 보기',
            'question-embed-topbar',
            'data-question-nav="prev"',
            'data-question-reveal="1"',
            'question-judgment-badge',
            'is-judged-wrong',
            '틀림 표시됨',
            "${isWrongSelection ? ' wrong selected-wrong' : ''}",
            'question-choice-badges',
            'question-choice-badge answer',
            'question-choice-badge wrong',
            'question-session-score-grid',
            'question-session-missed-chip',
            '총괄 채점',
            '빨간 표시 문제',
            '채점 완료 · ${sessionSummary.scorePercent}점',
            "questionBankIds: items.map((item) => String(item?.questionBankId || '').trim()).filter(Boolean)",
            'question-review-box',
            'question-review-actions',
            "markQuestionSourceCard('O')",
            "markQuestionSourceCard('X')",
            'const reviewCard = currentQuestionCard();',
            'question-history-field',
            'question-session-meta',
            'question-history-session-meta',
        ]:
            'function questionMarkdownListMatch(line)',
            'function renderQuestionMarkdownListLevel(lines, startIndex, indent, ordered)',

            self.assertIn(snippet, app_js())
        self.assertIn('id="questionHistoryDialog"', index_html())
        self.assertIn('id="questionHistoryBody"', index_html())
        self.assertIn('id="questionImportDialog"', index_html())
        self.assertIn('id="questionImportInput"', index_html())
        self.assertIn('id="questionImportApplyBtn"', index_html())
        self.assertIn('id="questionBankEditDialog"', index_html())
        self.assertIn('id="questionBankEditPromptInput"', index_html())
        self.assertIn('data-question-history-filter="ambiguous"', index_html())
        self.assertIn('data-question-history-filter="unknown"', index_html())
        self.assertIn('.question-history-filter-row', style_css())
        self.assertIn('.question-history-item', style_css())
        self.assertIn('.question-session-meta', style_css())
        self.assertIn('.question-session-lock', style_css())
        self.assertIn('.question-session-summary', style_css())
        self.assertIn('.question-session-review', style_css())
        self.assertIn('.question-history-session-meta', style_css())
        self.assertIn('.question-import-body', style_css())
        self.assertIn('.question-import-input', style_css())
        self.assertIn('.question-bank-edit-body', style_css())
        self.assertIn('.question-inline-toolbar', style_css())
        self.assertIn('question-toolbar-button', index_html())
        self.assertIn('question-toolbar-eyebrow', index_html())
        self.assertIn('question-stage', index_html())
        self.assertIn('.question-toolbar-button', style_css())
        self.assertIn('.question-toolbar-eyebrow', style_css())
        self.assertIn('.question-card-shell', style_css())
        self.assertIn('.question-card-progress', style_css())
        self.assertIn('.question-card-grid', style_css())
        self.assertIn('.question-bank-browser', style_css())
        self.assertIn('.question-bank-table', style_css())
        self.assertIn('.question-bank-row-trigger', style_css())
        self.assertIn('.question-bank-list', style_css())
        self.assertIn('.question-markdown', style_css())
        self.assertIn('.question-md-image', style_css())
        self.assertIn('.question-answer-meta', style_css())
        self.assertIn('.question-answer-meta-card-button', style_css())
        self.assertIn('.question-markdown ul ul', style_css())
        self.assertIn('.question-markdown ol ol', style_css())
        self.assertIn('question-bank-shell-topbar', question_bank_html())
        self.assertIn('.question-bank-shell', style_css())
        self.assertIn('.question-bank-shell-topbar', style_css())
        self.assertIn('.question-bank-embed .topbar', style_css())
        self.assertIn('body.question-bank-embed #questionBankToggleBtn', style_css())
        self.assertIn('if (index < 0) {', question_bank_js())
        self.assertIn('body.question-bank-embed #questionBankBrowser', style_css())
        self.assertIn('body.question-bank-embed {', style_css())
        self.assertIn('.question-bank-practice-collapsed', table_shell_css())
        self.assertIn('.question-bank-practice-placeholder[hidden]', table_shell_css())
        self.assertIn('.question-bank-overview-grid', table_shell_css())
        self.assertIn('.question-bank-review-body[hidden]', table_shell_css())
        self.assertIn('.question-bank-review-stats', table_shell_css())
        self.assertIn('.question-bank-review-item', table_shell_css())
        self.assertIn('.question-bank-review-list', table_shell_css())
        self.assertIn('.question-bank-selection-summary', table_shell_css())
        self.assertIn('.question-bank-practice-status', table_shell_css())
        self.assertIn('.question-bank-header-chip', table_shell_css())
        self.assertIn('.question-bank-filter-chip', table_shell_css())
        self.assertIn('.question-choice-badges', style_css())
        self.assertIn('.question-choice-badge.answer', style_css())
        self.assertIn('.question-choice.selected-wrong', style_css())
        self.assertIn('.question-session-summary.is-finished', style_css())
        self.assertIn('.question-session-score-grid', style_css())
        self.assertIn('.question-session-missed-chip', style_css())
        self.assertIn('.question-side-note.is-score', style_css())
        self.assertIn('.question-card-shell.is-session-finished', style_css())
        self.assertIn('.question-embed-topbar.is-finished', style_css())
        self.assertIn('.question-embed-topbar-status.finished', style_css())
        self.assertIn('.question-bank-header-chip-button', table_shell_css())
        self.assertIn('.question-bank-table-selection', table_shell_css())
        self.assertIn('.question-bank-shell-header-chips', table_shell_css())
        self.assertIn('.question-bank-guide-table', table_shell_css())
        self.assertIn('.question-bank-metric-card.score', table_shell_css())
        self.assertIn('.question-bank-summary-pill.attempt-wrong', table_shell_css())
        self.assertIn('function questionBankSliceMatchesPracticeSummary(summary = bankState.practiceSummary)', question_bank_js())
        self.assertIn('if (bankState.practiceSummary && !questionBankSliceMatchesPracticeSummary(bankState.practiceSummary)) {', question_bank_js())
        self.assertIn('.question-bank-row-number.is-wrong::after', table_shell_css())
        self.assertIn('.question-choice.wrong', style_css())

    def test_concept_html_widgets_use_trusted_iframe_boundary(self):
        self.assertIn("const TRUSTED_CONCEPT_WIDGET_HTML_KIND = 'concept-widget';", app_js())
        self.assertIn('function trustedConceptWidgetHtml(payload)', app_js())
        self.assertIn('function isTrustedConceptWidgetHtml(value)', app_js())
        self.assertIn("if (!isTrustedConceptWidgetHtml(payload)) throw new Error('Trusted concept HTML payload required.');", app_js())
        self.assertIn("frame.srcdoc = conceptMediaIframeSrcdoc(payload, alt);", app_js())
        self.assertIn('sandbox iframe 전용', app_js())
        self.assertIn('Sandbox HTML 위젯', index_html())
        self.assertIn('카드 뒷면의 sandbox iframe 안에서만 렌더링되는 HTML 위젯', index_html())
        self.assertNotIn("frame.srcdoc = conceptMediaIframeSrcdoc(String(payload || ''), alt);", app_js())

    def test_wiki_html_uses_trusted_render_boundary(self):
        self.assertIn("const WIKI_TRUSTED_RENDERED_HTML_KIND = 'wiki-rendered';", wiki_js())
        self.assertIn('function wikiTrustedRenderedHtml(html)', wiki_js())
        self.assertIn('function wikiApplyTrustedHtml(element, trustedHtml', wiki_js())
        self.assertIn("wikiApplyTrustedHtml(wiki$('wikiArticle'), wikiTrustedRenderedHtml(page?.html || ''), {emptyText: '문서가 비어 있습니다.'});", wiki_js())
        self.assertIn("wikiApplyTrustedHtml(preview, wikiTrustedRenderedHtml(data?.html || ''), {emptyText: '미리보기 결과가 비어 있습니다.'});", wiki_js())
        self.assertNotIn("wiki$('wikiArticle').innerHTML = page?.html || '<p class=\"muted\">문서가 비어 있습니다.</p>';", wiki_js())
        self.assertNotIn("preview.innerHTML = data?.html || '<p class=\"muted\">미리보기 결과가 비어 있습니다.</p>';", wiki_js())
    def test_question_bank_node_contracts(self):
        self.assertNotIn(
            "if (bankState.items.length && shouldRefreshPracticeSession()) await launch(selectedIndex(bankState.practiceStartIndex), {reveal: false});",
            question_bank_js(),
        )
        results = self.run_question_bank_contract_batch()

        with self.subTest(contract='filter_refresh'):
            self.assertEqual(
                results['filterRefresh'],
                {
                    'launchCalls': 0,
                    'reviewCalls': 0,
                    'loading': False,
                    'selectedId': 'beta',
                    'practiceStartIndex': 1,
                    'itemCount': 2,
                    'reviewLoading': False,
                },
            )

        with self.subTest(contract='review_toggle'):
            self.assertEqual(
                results['reviewToggle'],
                {
                    'collapsed': False,
                    'loadCalls': 1,
                    'renderCalls': 0,
                    'buttonText': '리뷰 숨기기',
                    'expanded': 'true',
                    'hidden': False,
                },
            )

        with self.subTest(contract='explicit_launch'):
            self.assertEqual(
                results['explicitLaunch'],
                {
                    'launched': False,
                    'confirmCalls': 1,
                    'restartCalls': 0,
                    'pendingPracticeLaunch': None,
                    'practiceLoaded': True,
                    'practiceStartIndex': 0,
                    'selectedId': 'alpha',
                    'practiceActiveId': 'alpha',
                    'error': '현재 풀이 세트를 유지했습니다. 다시 시작하려면 선택한 행을 다시 누르세요.',
                },
            )

if __name__ == '__main__':
    unittest.main()
