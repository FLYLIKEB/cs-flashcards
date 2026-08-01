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
    def test_index_page_smoke_has_core_navigation_and_question_panel(self):
        self.assertIn('id="calendarPageLink"', INDEX_HTML)
        self.assertIn('id="wikiHomeLink"', INDEX_HTML)
        self.assertIn('id="questionBankPageLink"', INDEX_HTML)
        self.assertIn('class="question-panel"', INDEX_HTML)
        self.assertIn('id="questionBankBrowser"', INDEX_HTML)

    def test_question_bank_page_smoke_has_filter_table_and_practice_shell(self):
        self.assertIn('id="bankPageToggleFiltersBtn"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageList"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPagePracticeFrame"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageCategoryGuideDialog"', QUESTION_BANK_HTML)
        self.assertIn('question-bank-shell-topbar', QUESTION_BANK_HTML)

    def test_calendar_page_smoke_has_tabs_and_detail_drawer(self):
        self.assertIn('id="mainTabCalendarBtn"', CALENDAR_HTML)
        self.assertIn('id="mainTabListBtn"', CALENDAR_HTML)
        self.assertIn('id="calendarDetailDrawer"', CALENDAR_HTML)
        self.assertIn('id="calendarDetailCloseBtn"', CALENDAR_HTML)

    def test_wiki_page_smoke_has_sidebar_search_and_status_region(self):
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
        self.assertIn('.question-bank-row-trigger', STYLE_CSS)
        self.assertIn('.question-bank-list', STYLE_CSS)
        self.assertIn('.question-markdown', STYLE_CSS)
        self.assertIn('.question-md-image', STYLE_CSS)
        self.assertIn('.question-answer-meta', STYLE_CSS)
        self.assertIn('.question-answer-meta-card-button', STYLE_CSS)
        self.assertIn('.question-markdown ul ul', STYLE_CSS)
        self.assertIn('.question-markdown ol ol', STYLE_CSS)
        self.assertIn('.question-bank-shell', STYLE_CSS)
        self.assertIn('.question-bank-shell-topbar', STYLE_CSS)
        self.assertIn('.question-bank-embed .topbar', STYLE_CSS)
        self.assertIn('body.question-bank-embed #questionBankToggleBtn', STYLE_CSS)
        self.assertIn('body.question-bank-embed #questionBankBrowser', STYLE_CSS)
        self.assertIn('body.question-bank-embed {', STYLE_CSS)
        self.assertIn('.question-bank-practice-collapsed', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-practice-placeholder[hidden]', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-overview-grid', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-selection-summary', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-practice-status', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-header-chip', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-filter-chip', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-header-chip-button', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-table-selection', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-shell-header-chips', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-guide-table', TABLE_SHELL_CSS)


if __name__ == '__main__':
    unittest.main()
