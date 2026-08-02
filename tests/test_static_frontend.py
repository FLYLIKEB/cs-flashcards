import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
WIKI_HTML = (ROOT / 'static' / 'wiki.html').read_text(encoding='utf-8')
QUESTION_BANK_HTML = (ROOT / 'static' / 'question-bank.html').read_text(encoding='utf-8')
WIKI_JS = (ROOT / 'static' / 'wiki.js').read_text(encoding='utf-8')
QUESTION_BANK_JS = (ROOT / 'static' / 'question-bank.js').read_text(encoding='utf-8')
STYLE_CSS = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')
TABLE_SHELL_CSS = (ROOT / 'static' / 'table-shell.css').read_text(encoding='utf-8')
CALENDAR_HTML = (ROOT / 'static' / 'calendar.html').read_text(encoding='utf-8')
CALENDAR_JS = (ROOT / 'static' / 'calendar.js').read_text(encoding='utf-8')


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

    def test_index_page_smoke_has_core_navigation_and_question_panel(self):
        self.assertIn('id="calendarPageLink"', INDEX_HTML)
        self.assertIn('id="wikiHomeLink"', INDEX_HTML)
        self.assertIn('id="questionBankPageLink"', INDEX_HTML)
        self.assertIn('class="question-panel"', INDEX_HTML)
        self.assertIn('id="questionBankBrowser"', INDEX_HTML)

    def test_question_bank_page_smoke_has_filter_table_and_practice_shell(self):
        self.assertIn('id="bankPageToggleFiltersBtn"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageList"', QUESTION_BANK_HTML)
        self.assertIn('<input id="bankPageTopicInput"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageTopicOptions"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageAttemptStatusSelect"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageFieldInput"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageCategoryInput"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageIssuerInput"', QUESTION_BANK_HTML)

        self.assertIn('문제 풀이 · 문제은행', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageTogglePracticeBtn"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageHeaderSummary"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageOverviewCards"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewSummary"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewStats"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewFilters"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageReviewList"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageResetFiltersBtn"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageSelectionSummary"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPagePracticeStatus"', QUESTION_BANK_HTML)
        self.assertIn('question-bank-table-selection', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageCategoryGuideBtn"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageCategoryGuideDialog"', QUESTION_BANK_HTML)
        self.assertIn('bankPageHeaderPracticeToggle', QUESTION_BANK_JS)
        self.assertNotIn('bankPageOpenPracticeTab', QUESTION_BANK_HTML)
        self.assertIn('/api/question-bank', QUESTION_BANK_JS)
        self.assertIn('QUESTION_BANK_LAUNCH_KEY', QUESTION_BANK_JS)
        self.assertIn('QUESTION_BANK_PRACTICE_COLLAPSED_KEY', QUESTION_BANK_JS)
        self.assertIn('function populateTopicOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateFieldNameOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateIssuerOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateCategoryOptions(', QUESTION_BANK_JS)
        self.assertIn('available_topics', QUESTION_BANK_JS)
        self.assertIn('available_field_names', QUESTION_BANK_JS)
        self.assertIn('available_issuers', QUESTION_BANK_JS)
        self.assertIn('available_categories', QUESTION_BANK_JS)
        self.assertIn('question-keyword-link', QUESTION_BANK_JS)
        self.assertIn('card_query=', QUESTION_BANK_JS)
        self.assertIn('cs-flashcards-question-bank-updated', QUESTION_BANK_JS)
        self.assertIn("window.addEventListener('message'", QUESTION_BANK_JS)
        self.assertIn('function renderHeader()', QUESTION_BANK_JS)
        self.assertIn('function renderOverviewCards()', QUESTION_BANK_JS)
        self.assertIn('function renderCategoryGuideDialog()', QUESTION_BANK_JS)
        self.assertIn('function openCategoryGuideDialog()', QUESTION_BANK_JS)
        self.assertIn('function closeCategoryGuideDialog(', QUESTION_BANK_JS)
        self.assertIn('function questionBankItemMatchesAttemptStatusFilter(item, attemptStatus = filterValues().attempt_status)', QUESTION_BANK_JS)
        self.assertIn("if (!questionBankItemMatchesAttemptStatusFilter(nextItem))", QUESTION_BANK_JS)
        self.assertIn('function renderActiveFilters()', QUESTION_BANK_JS)
        self.assertIn('function renderSelectionSummary()', QUESTION_BANK_JS)
        self.assertIn('function resetFilters()', QUESTION_BANK_JS)
        self.assertIn('function bindHeaderChipActions()', QUESTION_BANK_JS)
        self.assertIn('function ensureSelectedRowVisible()', QUESTION_BANK_JS)
        self.assertIn('function scheduleLoad()', QUESTION_BANK_JS)
        self.assertIn('id="bankPagePracticeFrame"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPagePracticePlaceholder"', QUESTION_BANK_HTML)
        self.assertIn('function practiceFrameUrl()', QUESTION_BANK_JS)
        self.assertIn('function setPracticeCollapsed(', QUESTION_BANK_JS)
        self.assertIn('function shouldRefreshPracticeSession()', QUESTION_BANK_JS)
        self.assertIn('if (shouldRefreshPracticeSession()) launch(index);', QUESTION_BANK_JS)
        self.assertIn('await loadQuestionBankReview();', QUESTION_BANK_JS)
        self.assertIn('question-bank-embed=1', QUESTION_BANK_JS)
        self.assertIn("get('question-bank-embed') === '1'", APP_JS)
        self.assertIn("const QUESTION_BANK_SESSION_SYNC_REQUEST = 'cs-flashcards-question-bank-session-sync-request';", QUESTION_BANK_JS)
        self.assertIn("const QUESTION_BANK_SESSION_SYNC_RESPONSE = 'cs-flashcards-question-bank-session-sync-response';", QUESTION_BANK_JS)
        self.assertIn('function syncEmbeddedPracticeSession(startIndex)', QUESTION_BANK_JS)
        self.assertIn('function restartPracticeFrame(startIndex, sessionState = bankState.practiceSessionState)', QUESTION_BANK_JS)
        self.assertIn('function practiceLaunchPayload(startIndex, sessionState = bankState.practiceSessionState)', QUESTION_BANK_JS)
        self.assertIn("if (sessionState && typeof sessionState === 'object') payload.sessionState = sessionState;", QUESTION_BANK_JS)
        self.assertIn('bankState.practiceSessionState = syncResult?.sessionState && typeof syncResult.sessionState === \'object\' ? syncResult.sessionState : null;', QUESTION_BANK_JS)
        self.assertIn('restartPracticeFrame(safeStart, syncResult?.sessionState || bankState.practiceSessionState);', QUESTION_BANK_JS)
        self.assertIn('function confirmPracticeRestart(startIndex)', QUESTION_BANK_JS)
        self.assertIn('const syncResult = await syncEmbeddedPracticeSession(safeStart);', QUESTION_BANK_JS)
        self.assertIn('if (syncResult?.preserved) {', QUESTION_BANK_JS)
        self.assertIn('if (syncResult?.requiresReload && syncResult?.hasInProgress && !confirmPracticeRestart(safeStart)) {', QUESTION_BANK_JS)

    def test_calendar_page_smoke_has_tabs_and_detail_drawer(self):
        self.assertIn('id="mainTabCalendarBtn"', CALENDAR_HTML)
        self.assertIn('id="mainTabListBtn"', CALENDAR_HTML)
        self.assertIn('id="calendarDetailDrawer"', CALENDAR_HTML)
        self.assertIn('id="calendarDetailCloseBtn"', CALENDAR_HTML)

    def test_wiki_page_smoke_has_sidebar_search_and_status_region(self):
        self.assertIn('id="wikiSearchToggleBtn"', WIKI_HTML)
        self.assertIn('id="wikiSearch"', WIKI_HTML)
        self.assertIn('id="wikiSidebarToggleBtn"', WIKI_HTML)
        self.assertIn('id="wikiSidebar"', WIKI_HTML)
        self.assertIn('id="wikiSearchToggleBtn"', WIKI_HTML)
        self.assertIn('id="wikiStatus"', WIKI_HTML)

    def test_app_js_smoke_keeps_embedded_question_bank_browser_hooks(self):
        self.assertIn('function renderQuestionBankBrowser()', APP_JS)
        self.assertIn('function loadQuestionBankBrowser()', APP_JS)
        self.assertIn('function openQuestionBankSession(startIndex = 0)', APP_JS)
        self.assertIn('questionBankToggleBtn', APP_JS)

    def test_question_bank_js_smoke_keeps_load_launch_and_persistence_hooks(self):
        self.assertIn("const QUESTION_BANK_LAUNCH_KEY = 'csPendingQuestionBankLaunch:v1';", QUESTION_BANK_JS)
        self.assertIn('function loadQuestionBankPage()', QUESTION_BANK_JS)
        self.assertIn('function launch(startIndex = 0, {reveal = true} = {})', QUESTION_BANK_JS)
        self.assertIn('window.sessionStorage.setItem(QUESTION_BANK_LAUNCH_KEY', QUESTION_BANK_JS)
        self.assertIn('question-bank-filters-collapsed', QUESTION_BANK_JS)
        self.assertIn('let restorePracticePaneOnReload = isReloadNavigation() && Boolean(restoredPracticeState?.loaded) && !persistedPracticeCollapsed();', QUESTION_BANK_JS)
        self.assertIn('loaded: bankState.practiceLoaded,', QUESTION_BANK_JS)
    def test_calendar_js_smoke_keeps_tab_and_drawer_focus_handlers(self):
        self.assertIn('function setMainTab(tabId)', CALENDAR_JS)
        self.assertIn('function openDetailDrawer()', CALENDAR_JS)
        self.assertIn('function closeDetailDrawer({ restoreFocus = true } = {})', CALENDAR_JS)
        self.assertIn("if (event.key === 'Escape' && calendarState.detailOpen)", CALENDAR_JS)

    def test_wiki_js_smoke_keeps_sidebar_persistence_and_status_updates(self):
        self.assertIn("const WIKI_SIDEBAR_STATE_KEY = 'csFlashcardsWikiSidebar:v1';", WIKI_JS)
        self.assertIn('function toggleWikiSidebar(force = !wikiState.sidebarOpen)', WIKI_JS)
        self.assertIn('function wikiStatus(text, isError = false)', WIKI_JS)
        self.assertIn('wikiStatus(`검색 결과 ${matches.length}건`);', WIKI_JS)

    def test_css_smoke_keeps_question_and_table_shell_visibility_rules(self):
        self.assertIn('.question-panel[hidden]', STYLE_CSS)
        self.assertIn('display: none !important', STYLE_CSS)
    def test_free_tts_naturalness_controls_are_present(self):
        self.assertIn('id="speechVoice"', INDEX_HTML)
        self.assertIn('한국어 고품질/Siri/Google/Microsoft 음성', INDEX_HTML)
        self.assertIn('function populateSpeechVoiceSelect()', APP_JS)
        self.assertIn('function splitSpeechText(text)', APP_JS)
        self.assertIn('function expandSpeechItemForPauses(item)', APP_JS)
        self.assertIn('isPause: true', APP_JS)
        self.assertIn('window.speechSynthesis.onvoiceschanged = populateSpeechVoiceSelect', APP_JS)


    def test_question_practice_controls_are_present(self):
        self.assertIn('.question-panel[hidden]', (ROOT / 'static' / 'style.css').read_text(encoding='utf-8'))
        self.assertIn('display: none !important', (ROOT / 'static' / 'style.css').read_text(encoding='utf-8'))
        self.assertNotIn('id="questionModeBtn"', INDEX_HTML)
        self.assertNotIn('id="questionPracticeBtn"', INDEX_HTML)
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
            self.assertIn(snippet, INDEX_HTML)
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

            self.assertIn(snippet, APP_JS)
        self.assertIn('id="questionHistoryDialog"', INDEX_HTML)
        self.assertIn('id="questionHistoryBody"', INDEX_HTML)
        self.assertIn('id="questionImportDialog"', INDEX_HTML)
        self.assertIn('id="questionImportInput"', INDEX_HTML)
        self.assertIn('id="questionImportApplyBtn"', INDEX_HTML)
        self.assertIn('id="questionBankEditDialog"', INDEX_HTML)
        self.assertIn('id="questionBankEditPromptInput"', INDEX_HTML)
        self.assertIn('data-question-history-filter="ambiguous"', INDEX_HTML)
        self.assertIn('data-question-history-filter="unknown"', INDEX_HTML)
        self.assertIn('.question-history-filter-row', STYLE_CSS)
        self.assertIn('.question-history-item', STYLE_CSS)
        self.assertIn('.question-session-meta', STYLE_CSS)
        self.assertIn('.question-session-lock', STYLE_CSS)
        self.assertIn('.question-session-summary', STYLE_CSS)
        self.assertIn('.question-session-review', STYLE_CSS)
        self.assertIn('.question-history-session-meta', STYLE_CSS)
        self.assertIn('.question-import-body', STYLE_CSS)
        self.assertIn('.question-import-input', STYLE_CSS)
        self.assertIn('.question-bank-edit-body', STYLE_CSS)
        self.assertIn('.question-inline-toolbar', STYLE_CSS)
        self.assertIn('question-toolbar-button', INDEX_HTML)
        self.assertIn('question-toolbar-eyebrow', INDEX_HTML)
        self.assertIn('question-stage', INDEX_HTML)
        self.assertIn('.question-toolbar-button', STYLE_CSS)
        self.assertIn('.question-toolbar-eyebrow', STYLE_CSS)
        self.assertIn('.question-card-shell', STYLE_CSS)
        self.assertIn('.question-card-progress', STYLE_CSS)
        self.assertIn('.question-card-grid', STYLE_CSS)
        self.assertIn('.question-bank-browser', STYLE_CSS)
        self.assertIn('.question-bank-table', STYLE_CSS)
        self.assertIn('.question-bank-row-trigger', STYLE_CSS)
        self.assertIn('.question-bank-list', STYLE_CSS)
        self.assertIn('.question-markdown', STYLE_CSS)
        self.assertIn('.question-md-image', STYLE_CSS)
        self.assertIn('.question-answer-meta', STYLE_CSS)
        self.assertIn('.question-answer-meta-card-button', STYLE_CSS)
        self.assertIn('.question-markdown ul ul', STYLE_CSS)
        self.assertIn('.question-markdown ol ol', STYLE_CSS)
        self.assertIn('question-bank-shell-topbar', QUESTION_BANK_HTML)
        self.assertIn('.question-bank-shell', STYLE_CSS)
        self.assertIn('.question-bank-shell-topbar', STYLE_CSS)
        self.assertIn('.question-bank-embed .topbar', STYLE_CSS)
        self.assertIn('body.question-bank-embed #questionBankToggleBtn', STYLE_CSS)
        self.assertIn('if (index < 0) {', QUESTION_BANK_JS)
        self.assertIn('body.question-bank-embed #questionBankBrowser', STYLE_CSS)
        self.assertIn('body.question-bank-embed {', STYLE_CSS)
        self.assertIn('.question-bank-practice-collapsed', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-practice-placeholder[hidden]', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-overview-grid', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-review-stats', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-review-list', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-review-item', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-selection-summary', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-practice-status', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-header-chip', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-filter-chip', TABLE_SHELL_CSS)
        self.assertIn('.question-choice-badges', STYLE_CSS)
        self.assertIn('.question-choice-badge.answer', STYLE_CSS)
        self.assertIn('.question-choice.selected-wrong', STYLE_CSS)
        self.assertIn('.question-session-summary.is-finished', STYLE_CSS)
        self.assertIn('.question-session-score-grid', STYLE_CSS)
        self.assertIn('.question-session-missed-chip', STYLE_CSS)
        self.assertIn('.question-side-note.is-score', STYLE_CSS)
        self.assertIn('.question-card-shell.is-session-finished', STYLE_CSS)
        self.assertIn('.question-embed-topbar.is-finished', STYLE_CSS)
        self.assertIn('.question-embed-topbar-status.finished', STYLE_CSS)
        self.assertIn('.question-bank-header-chip-button', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-table-selection', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-shell-header-chips', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-guide-table', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-metric-card.score', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-summary-pill.attempt-wrong', TABLE_SHELL_CSS)
        self.assertIn('function questionBankSliceMatchesPracticeSummary(summary = bankState.practiceSummary)', QUESTION_BANK_JS)
        self.assertIn('if (bankState.practiceSummary && !questionBankSliceMatchesPracticeSummary(bankState.practiceSummary)) {', QUESTION_BANK_JS)
        self.assertIn('.question-bank-row-number.is-wrong::after', TABLE_SHELL_CSS)
        self.assertIn('.question-choice.wrong', STYLE_CSS)

    def test_concept_html_widgets_use_trusted_iframe_boundary(self):
        self.assertIn("const TRUSTED_CONCEPT_WIDGET_HTML_KIND = 'concept-widget';", APP_JS)
        self.assertIn('function trustedConceptWidgetHtml(payload)', APP_JS)
        self.assertIn('function isTrustedConceptWidgetHtml(value)', APP_JS)
        self.assertIn("if (!isTrustedConceptWidgetHtml(payload)) throw new Error('Trusted concept HTML payload required.');", APP_JS)
        self.assertIn("frame.srcdoc = conceptMediaIframeSrcdoc(payload, alt);", APP_JS)
        self.assertIn('sandbox iframe 전용', APP_JS)
        self.assertIn('Sandbox HTML 위젯', INDEX_HTML)
        self.assertIn('카드 뒷면의 sandbox iframe 안에서만 렌더링되는 HTML 위젯', INDEX_HTML)
        self.assertNotIn("frame.srcdoc = conceptMediaIframeSrcdoc(String(payload || ''), alt);", APP_JS)

    def test_wiki_html_uses_trusted_render_boundary(self):
        self.assertIn("const WIKI_TRUSTED_RENDERED_HTML_KIND = 'wiki-rendered';", WIKI_JS)
        self.assertIn('function wikiTrustedRenderedHtml(html)', WIKI_JS)
        self.assertIn('function wikiApplyTrustedHtml(element, trustedHtml', WIKI_JS)
        self.assertIn("wikiApplyTrustedHtml(wiki$('wikiArticle'), wikiTrustedRenderedHtml(page?.html || ''), {emptyText: '문서가 비어 있습니다.'});", WIKI_JS)
        self.assertIn("wikiApplyTrustedHtml(preview, wikiTrustedRenderedHtml(data?.html || ''), {emptyText: '미리보기 결과가 비어 있습니다.'});", WIKI_JS)
        self.assertNotIn("wiki$('wikiArticle').innerHTML = page?.html || '<p class=\"muted\">문서가 비어 있습니다.</p>';", WIKI_JS)
        self.assertNotIn("preview.innerHTML = data?.html || '<p class=\"muted\">미리보기 결과가 비어 있습니다.</p>';", WIKI_JS)
    def test_question_bank_filter_refresh_does_not_auto_launch_practice(self):
        self.assertNotIn(
            "if (bankState.items.length && shouldRefreshPracticeSession()) await launch(selectedIndex(bankState.practiceStartIndex), {reveal: false});",
            QUESTION_BANK_JS,
        )
        result = self.run_node(textwrap.dedent(
            """
            const fs = require('fs');
            const source = fs.readFileSync('static/question-bank.js', 'utf8');
            const start = source.indexOf('async function loadQuestionBankPage() {');
            const end = source.indexOf('\\nrestoreFilterState();', start);
            if (start < 0 || end < 0) throw new Error('loadQuestionBankPage not found');
            const fnSource = source.slice(start, end);
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
            const filterValues = () => ({topic: '', field_name: '', issuer: '', category: ''});
            const populateTopicOptions = () => {};
            const populateFieldNameOptions = () => {};
            const populateIssuerOptions = () => {};
            const populateCategoryOptions = () => {};
            const persistFilterState = () => {};
            const applyPracticeLaunch = () => {};
            let launchCalls = 0;
            let reviewCalls = 0;
            const loadQuestionBankReview = async () => { reviewCalls += 1; bankState.reviewLoading = false; };
            const launch = async () => { launchCalls += 1; };
            const fetchEntries = async () => ({
              items: [
                {question_bank_id: 'alpha'},
                {question_bank_id: 'beta'},
              ],
              summary: {total: 2, returned: 2},
            });
            eval(fnSource);
            loadQuestionBankPage().then(() => {
              process.stdout.write(JSON.stringify({
                launchCalls,
                reviewCalls,
                loading: bankState.loading,
                selectedId: bankState.selectedId,
                practiceStartIndex: bankState.practiceStartIndex,
                itemCount: bankState.items.length,
                reviewLoading: bankState.reviewLoading,
              }));
            }).catch((error) => {
              console.error(error);
              process.exit(1);
            });
            """
        ))
        self.assertEqual(
            result,
            '{"launchCalls":0,"reviewCalls":1,"loading":false,"selectedId":"beta","practiceStartIndex":1,"itemCount":2,"reviewLoading":false}',
        )

    def test_question_bank_explicit_launch_keeps_restart_confirm_contract(self):
        result = self.run_node(textwrap.dedent(
            """
            const fs = require('fs');
            const source = fs.readFileSync('static/question-bank.js', 'utf8');
            const start = source.indexOf('async function launch(startIndex = 0, {reveal = true} = {}) {');
            const end = source.indexOf('\\nasync function loadQuestionBankPage() {', start);
            if (start < 0 || end < 0) throw new Error('launch not found');
            const fnSource = source.slice(start, end);
            const bankState = {
              items: [
                {question_bank_id: 'alpha'},
                {question_bank_id: 'beta'},
              ],
              error: '',
              practiceLoaded: false,
              practiceCollapsed: true,
              practiceStartIndex: 0,
              practiceSessionState: null,
              selectedId: '',
            };
            const selectedIndex = (fallback = 0) => fallback;
            const setPracticeCollapsed = () => {};
            const persistFilterState = () => {};
            const questionBankResultSetKey = () => 'alpha\u001fbeta';
            const renderTable = () => {};
            const renderPracticePane = () => {};
            const ensureSelectedRowVisible = () => {};
            let syncCalls = 0;
            const syncEmbeddedPracticeSession = async () => {
              syncCalls += 1;
              return {requiresReload: true, hasInProgress: true, sessionState: {draft: 'keep'}};
            };
            let confirmCalls = 0;
            const confirmPracticeRestart = () => {
              confirmCalls += 1;
              return false;
            };
            let restartCalls = 0;
            const restartPracticeFrame = () => { restartCalls += 1; };
            eval(fnSource);
            launch(1).then((launched) => {
              process.stdout.write(JSON.stringify({
                launched,
                syncCalls,
                confirmCalls,
                restartCalls,
                practiceLoaded: bankState.practiceLoaded,
                practiceStartIndex: bankState.practiceStartIndex,
                selectedId: bankState.selectedId,
                error: bankState.error,
              }));
            }).catch((error) => {
              console.error(error);
              process.exit(1);
            });
            """
        ))
        self.assertEqual(
            result,
            '{"launched":false,"syncCalls":1,"confirmCalls":1,"restartCalls":0,"practiceLoaded":true,"practiceStartIndex":1,"selectedId":"beta","error":"현재 풀이 세트를 유지했습니다. 다시 시작하려면 선택한 행을 다시 누르세요."}',
        )

if __name__ == '__main__':
    unittest.main()
