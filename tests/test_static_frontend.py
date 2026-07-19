import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / 'static' / 'app.js').read_text(encoding='utf-8')
INDEX_HTML = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
WIKI_HTML = (ROOT / 'static' / 'wiki.html').read_text(encoding='utf-8')
WIKI_JS = (ROOT / 'static' / 'wiki.js').read_text(encoding='utf-8')
STYLE_CSS = (ROOT / 'static' / 'style.css').read_text(encoding='utf-8')



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
            'bookmarkFilter',
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
            'id="bookmarkListBtn"',
            'id="bookmarkFilterBtn"',
            'id="bookmarkListDialog"',
            'id="bookmarkListBody"',
            'id="definitionAiBtn"',
            'id="detailAiBtn"',
            'id="examAiBtn"',
            'id="conceptImageGenerateBtn"',

            'id="backConceptImagePlaceholder"',
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
            'function renderBookmarkList()',
            'function toggleBookmarkFilter()',
            'function jumpToBookmarkCard(cardId)',
            'state.bookmarkFilter',
            'bookmarkOk',
            'const AI_REWRITE_FIELD_CONFIG = {',
            'function aiRewriteDisplayText(card, field)',
            'function renderAiRewriteControls(card)',
            'async function previewAiRewrite(field)',
            '/ai-rewrite/preview',
            '/ai-rewrite/apply',
            'AI 변환 중',
            'function conceptImagePreviewActive(card)',
            'function bindConceptImageLoadState()',
            "hasImage: Boolean(url)",
            'async function previewConceptImage()',
            '/ai-image/preview',
            '/ai-image/apply',
            '/ai-image/discard',
            'AI 이미지 생성 중',
        ]:
            self.assertIn(snippet, APP_JS)
        for snippet in [
            '.section-title-row',
            '.inline-ai-actions',
            '.inline-ai-btn',
            '.inline-ai-btn.save',
            '.concept-image-actions',
            '.concept-image-action',
            '.concept-image-placeholder',
            '.concept-image-wrap.is-empty',
        ]:
            self.assertIn(snippet, STYLE_CSS)

    def test_wiki_ui_and_flashcard_links_are_present(self):
        self.assertIn('id="wikiHomeLink"', INDEX_HTML)
        self.assertIn('href="/wiki"', INDEX_HTML)
        self.assertIn('target="_blank"', INDEX_HTML)
        menu_popover = INDEX_HTML.split('id="menuPopover"', 1)[1].split('</div>', 1)[0]
        self.assertIn('id="wikiHomeLink"', menu_popover)
        self.assertIn('function renderSourceLinks(sourceFiles)', APP_JS)
        self.assertIn("$('sources').innerHTML = renderSourceLinks(c.source_files);", APP_JS)
        self.assertIn('/wiki/page/', APP_JS)
        self.assertIn('id="frontWikiLink"', INDEX_HTML)
        self.assertIn('id="backWikiLink"', INDEX_HTML)
        self.assertIn('id="wikiSearchInput"', WIKI_HTML)
        self.assertIn('id="wikiSearchToggleBtn"', WIKI_HTML)
        self.assertIn('id="wikiSearch"', WIKI_HTML)
        self.assertIn('id="wikiSidebarToggleBtn"', WIKI_HTML)
        self.assertIn('wiki-sidebar-dock', WIKI_HTML)
        self.assertIn('id="wikiSidebar"', WIKI_HTML)
        self.assertIn('id="wikiToc"', WIKI_HTML)
        self.assertIn('id="wikiArticle"', WIKI_HTML)
        self.assertIn('id="wikiFlashcardLink"', WIKI_HTML)
        self.assertIn('id="wikiLinkedCards"', WIKI_HTML)
        self.assertIn('id="wikiPageNav"', WIKI_HTML)
        self.assertIn('pretendard.css', WIKI_HTML)
        self.assertIn('WIKI_SIDEBAR_STATE_KEY', WIKI_JS)
        self.assertIn('function applyWikiSidebarState(', WIKI_JS)
        self.assertIn('function applyWikiSearchState(', WIKI_JS)
        self.assertIn('function toggleWikiSearch(', WIKI_JS)
        self.assertIn("toggleBtn.textContent = '목차'", WIKI_JS)
        self.assertIn('function toggleWikiSidebar(', WIKI_JS)
        self.assertIn('function wikiApiUrl(path)', WIKI_JS)
        self.assertIn('function wikiRenderLinkedCards(page)', WIKI_JS)
        self.assertIn('function wikiNavigationItems()', WIKI_JS)
        self.assertIn('function wikiRenderPageNav(page)', WIKI_JS)
        self.assertIn('wikiRenderPageNav(page);', WIKI_JS)
        self.assertIn('closeWikiSidebarOnMobile()', WIKI_JS)
        self.assertIn('closeWikiSearch()', WIKI_JS)
        self.assertIn('function wikiShowSearchResults()', WIKI_JS)
        self.assertIn("if (event.key !== 'Enter') return;", WIKI_JS)
        self.assertIn("querySelectorAll('#wikiToc .wiki-toc-link')", WIKI_JS)
        self.assertIn('toggleWikiSidebar(true)', WIKI_JS)
        self.assertIn('scrollIntoView({block: \'nearest\'})', WIKI_JS)
        self.assertIn("(min-width: 721px)", WIKI_JS)
        self.assertIn("(max-width: 720px)", WIKI_JS)
        self.assertIn('@media (max-width: 720px)', STYLE_CSS)
        self.assertIn('.wiki-shell', STYLE_CSS)
        self.assertIn('.wiki-topbar-controls', STYLE_CSS)
        self.assertIn('.wiki-search-toggle', STYLE_CSS)
        self.assertIn('.wiki-search[hidden]', STYLE_CSS)
        self.assertIn('.wiki-sidebar-dock', STYLE_CSS)
        self.assertIn('.wiki-sidebar-toggle', STYLE_CSS)
        self.assertIn('body.wiki-sidebar-collapsed .wiki-sidebar', STYLE_CSS)
        self.assertIn('.wiki-table-wrap tbody tr:nth-child(even)', STYLE_CSS)
        self.assertIn('.wiki-sidebar-title-row', STYLE_CSS)
        self.assertIn('.wiki-linked-cards', STYLE_CSS)
        self.assertIn('.wiki-linked-card-link', STYLE_CSS)
        self.assertIn('.wiki-page-nav', STYLE_CSS)
        self.assertIn('.wiki-page-nav-link', STYLE_CSS)
        self.assertIn('.wiki-page-nav-kicker', STYLE_CSS)
        self.assertIn('--wiki-font-family: "Pretendard"', STYLE_CSS)
        self.assertIn('.wiki-page-shell :where(h1, h2, h3, h4, h5, h6, pre, code, kbd, samp)', STYLE_CSS)
        self.assertIn('expandedToc: {}', WIKI_JS)
        self.assertIn('function wikiTocBranchExpanded(', WIKI_JS)
        self.assertIn('function toggleWikiTocBranch(', WIKI_JS)
        self.assertIn('data-wiki-toc-toggle', WIKI_JS)
        self.assertIn("wikiLoadPage(slug, {push: true})", WIKI_JS)
        self.assertIn('.wiki-toc-row', STYLE_CSS)
        self.assertIn('.wiki-toc-toggle', STYLE_CSS)
        self.assertIn('max-height: calc(100vh - 5.3rem)', STYLE_CSS)
        self.assertIn('overscroll-behavior: contain;', STYLE_CSS)
        self.assertIn('overflow: hidden;', STYLE_CSS)
        self.assertIn('font-size: .84rem;', STYLE_CSS)
        self.assertIn('margin-top: .24rem;', STYLE_CSS)
        self.assertIn('padding-top: .24rem;', STYLE_CSS)
        self.assertIn('.wiki-toc-item.open > .wiki-toc-row .wiki-toc-toggle', STYLE_CSS)
        self.assertIn('function wikiToggleChecklist(', WIKI_JS)
        self.assertIn('/api/wiki/checklist', WIKI_JS)
        self.assertIn('data-wiki-task-checkbox="1"', WIKI_JS)
        self.assertIn('.wiki-task-list', STYLE_CSS)
        self.assertIn('.wiki-task-item', STYLE_CSS)
    def test_audio_playback_repeat_and_term_language_controls_are_present(self):
        for snippet in [
            'id="termSpeechMode"',
            'value="ko_en"',
            'id="termRepeatCount"',
            'id="cardRepeatCount"',
            'id="listRepeatCount"',
            'value="infinite"',
            'id="speakDetailMeaning"',
            'id="speakDetailUsage"',
            'id="audioPresetNameInput"',
            'id="audioPresetSaveBtn"',
            'id="audioPresetList"',
        ]:
            self.assertIn(snippet, INDEX_HTML)
        for snippet in [
            'AUDIO_SETTINGS_KEY',
            'function termSpeechMode()',
            'function termRepeatCount()',
            'function cardRepeatCount()',
            'function listRepeatCount()',
            'function selectedDetailSpeechSections()',
            'function shouldSpeakDetailSection(label)',
            'function termSpeechText(card)',
            'function baseSpeechItemsForCard(card)',
            'termRepeatIndex',
            'cardRepeatIndex',
            'audioListRepeatIndex',
            'estimateSpeechSecondsForOneListPass()',
            'shouldSpeakDetailSection(section.label)',
            'hasPlayableSpeechItems()',
            'state.index = 0',
            'restoreAudioSettings()',
            'AUDIO_PRESETS_KEY',
            'function collectAudioSettings()',
            'function applyAudioSettings(settings = {})',
            'function renderAudioPresets()',
            'function nextAudioPresetName(presets)',
            'function saveCurrentAudioPreset()',
            'function applyAudioPreset(presetId)',
            'function deleteAudioPreset(presetId)',
            'renderAudioPresets();',
            "$('audioPresetSaveBtn')?.addEventListener('click', saveCurrentAudioPreset)",
            "$('audioPresetNameInput')?.addEventListener('keydown'",
            "$('audioPresetList')?.addEventListener('click'",
        ]:
            self.assertIn(snippet, APP_JS)

    def test_bookmark_buttons_are_card_top_actions_not_bottom_mark_row(self):
        self.assertIn('class="card-quick-actions"', INDEX_HTML)
        quick_actions = INDEX_HTML.split('class="card-quick-actions"', 1)[1].split('</div>', 1)[0]
        self.assertIn('id="bookmarkBtn"', quick_actions)
        self.assertIn('id="copyBookmarksBtn"', quick_actions)
        mark_row = INDEX_HTML.split('class="mark-row"', 1)[1].split('</div>', 1)[0]
        self.assertNotIn('id="bookmarkBtn"', mark_row)
        self.assertNotIn('id="copyBookmarksBtn"', mark_row)

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
        for snippet in [
            'id="questionPracticeBtn"',
            'id="questionPanel"',
            'id="questionTypeShort"',
            'id="questionTypeSubjective"',
            'id="questionTypeMultipleChoice"',
            'id="questionTypeEssay"',
            'id="generateQuestionsBtn"',
            'id="openAiQuizSearchBtn"',
            'id="questionHistoryBtn"',
            'id="revealAnswerBtn"',
            'id="openQuestionCardBtn"',
        ]:
            self.assertIn(snippet, INDEX_HTML)
        for snippet in [
            'questionMode: false',
            'function generateQuestionsFromCurrentFilter()',
            '/api/questions/generate',
            'function renderQuestionPanel()',
            'function revealQuestionAnswer()',
            'function openQuestionSourceCard()',
            'function openQuestionPracticeFromMenu()',
            'toggleQuestionMode(true)',
            'function aiQuizSearchPrompt()',
            'function openAiQuizSearch(event = null)',
            '자체 퀴즈생성 기능을 활용해줘',
            'AI_QUIZ_PROMPT_TYPE_ORDER',
            'googleAiSearchUrl(aiQuizSearchPrompt())',
            'question-mode-active',
            '/api/questions/attempt',
            'function saveQuestionAttempt(question)',
            'function markCurrentQuestion(correct)',
            'function saveCurrentWrongNote()',
            'question-answer-input',
            'question-wrong-note',
            'new URLSearchParams(window.location.search)',
            '/api/questions/attempts',
            'function openQuestionHistory()',
            'function loadQuestionHistory()',
            'function setQuestionHistoryFilter(filter)',
            'questionHistoryBtn',
            'data-question-history-filter',
            'function markQuestionSourceCard(status)',
            'data-question-mark',
            'question-review-box',
            'question-review-actions',
            "markQuestionSourceCard('O')",
            "markQuestionSourceCard('X')",
            'const reviewCard = currentQuestionCard();',
            'question-history-field',
        ]:
            self.assertIn(snippet, APP_JS)
        self.assertIn('id="questionHistoryDialog"', INDEX_HTML)
        self.assertIn('id="questionHistoryBody"', INDEX_HTML)
        self.assertIn('.question-history-filter-row', STYLE_CSS)
        self.assertIn('.question-history-item', STYLE_CSS)
        self.assertIn('question-toolbar-button', INDEX_HTML)
        self.assertIn('.question-toolbar-button', STYLE_CSS)


if __name__ == '__main__':
    unittest.main()
