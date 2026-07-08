import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')


class StaticFrontendTests(unittest.TestCase):
    def test_concept_back_button_is_present(self):
        self.assertIn('id="conceptBackBtn"', INDEX_HTML)
        self.assertIn('이전 개념 카드와 필터로 돌아가기', INDEX_HTML)

    def test_concept_jump_saves_and_restores_full_view_state(self):
        self.assertIn('conceptHistory: []', APP_JS)
        self.assertIn('function currentViewSnapshot()', APP_JS)
        self.assertIn('function restoreViewSnapshot(snapshot)', APP_JS)
        for field in [
            'cardId',
            'backPage',
            'backScrollTop',
            'search',
            'category',
            'importance',
            'difficulty',
            'bok',
            'statusFilter',
        ]:
            self.assertIn(field, APP_JS)
        self.assertIn('state.conceptHistory.push(snapshot)', APP_JS)
        self.assertIn('jumpToCard(card, {rememberCurrent: true})', APP_JS)
        self.assertIn('goBackToPreviousConcept()', APP_JS)

    def test_status_filter_does_not_recount_header_stats_from_status_filtered_rows(self):
        self.assertIn('function cardMatchesCurrentFilters(card, {includeStatus = true} = {})', APP_JS)
        self.assertIn('function rowsForHeaderStats()', APP_JS)
        self.assertIn('cardMatchesCurrentFilters(card, {includeStatus: false})', APP_JS)
        self.assertIn('renderStats(summaryFromRows(rowsForHeaderStats()))', APP_JS)
        self.assertNotIn('renderStats(summaryFromRows(state.filtered))', APP_JS)

    def test_bookmark_and_memo_controls_are_present(self):
        for snippet in [
            'id="bookmarkBtn"',
            'id="copyBookmarksBtn"',
            'id="memoInput"',
            'id="memoSaveBtn"',
            'id="menuBtn"',
            'id="memoListBtn"',
            'id="memoListDialog"',
        ]:
            self.assertIn(snippet, INDEX_HTML)
        for snippet in [
            'function toggleBookmark()',
            '/bookmark',
            'function copyBookmarkedTerms()',
            "join(', ')",
            'function saveMemo()',
            '/memo',
            'function renderMemoList()',
        ]:
            self.assertIn(snippet, APP_JS)


if __name__ == '__main__':
    unittest.main()
