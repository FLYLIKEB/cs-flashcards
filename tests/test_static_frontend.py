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
AI_TOOLS_JS = (ROOT / 'static' / 'ai-tools.js').read_text(encoding='utf-8')


class StaticFrontendTests(unittest.TestCase):
    def test_concept_back_button_is_present(self):
        self.assertIn('id="conceptBackBtn"', INDEX_HTML)
        self.assertIn('이전 개념 카드와 필터로 돌아가기', INDEX_HTML)

    def test_frontend_shows_content_db_source(self):
        self.assertIn('id="contentDbPath"', INDEX_HTML)
        self.assertIn("$('contentDbPath').textContent = data.summary.content_db_path;", APP_JS)
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
            'id="flashcardTableBtn"',
            'id="mindMapBtn"',
            'id="definitionAiBtn"',
            'id="detailAiBtn"',
            'id="examAiBtn"',
            'id="conceptImageZoomOutBtn"',
            'id="conceptImageZoomInBtn"',
            'id="conceptMediaEditBtn"',
            'id="conceptImageGenerateBtn"',
            'id="backConceptVideo"',
            'id="backConceptHtmlFrame"',
            'id="backConceptMermaid"',
            'id="backConceptImagePlaceholder"',
            'id="conceptImageDialogStage"',
            'id="conceptMediaDialog"',
            'id="conceptMediaTypeInput"',
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
            'function openFlashcardTableWindow()',
            'function renderFlashcardTableWindow()',
            '__csFlashcardsSelectCardFromTable',
            'function registerFlashcardTableWindow(popupWindow = null)',
            '__csFlashcardsRegisterTableWindow',
            'function bootstrapFlashcardTablePopupWindow()',
            "popupUrl.searchParams.set('popup', 'flashcard-table')",
            'mindMapWindow: null,',
            'function buildMindMapGraphData(cards = state.filtered',
            'function renderMindMapWindow()',
            'function registerMindMapWindow(popupWindow = null)',
            '__csFlashcardsRegisterMindMapWindow',
            '__csFlashcardsSelectCardFromMindMap',
            'function bootstrapMindMapPopupWindow()',
            'function openMindMapWindow()',
            "popupUrl.searchParams.set('popup', 'mind-map')",
            'window.__csFlashcardsMindMapClosed',
            "$('mindMapBtn')?.addEventListener('click', openMindMapWindow);",
            'openerRef.focus?.();',
            'focusAppCard();',
            'renderMindMapWindow();',
            'if (!bootstrapFlashcardTablePopupWindow() && !bootstrapMindMapPopupWindow()) {',
            "window.setTimeout(() => {\n        try {\n          openerRef[callbackName](...args);\n          openerRef.focus?.();\n        } catch (_error) {}\n      }, 0);",
            'function toggleFlashcardBookmarkFromTable(cardId)',
            'function setFlashcardStatusFromTable(cardId, status)',
            '__csFlashcardsToggleBookmarkFromTable',
            '__csFlashcardsSetStatusFromTable',
            'data-bookmark-card-id',
            'data-status-card-id',
            'FLASHCARD_TABLE_COLUMN_ORDER_KEY',
            'function moveFlashcardTableColumn(sourceKey, targetKey)',
            '__csFlashcardsMoveTableColumn',
            'draggable="true"',
            'data-column-key',
            'dragstart',
            'drop-target',
            "get('popup') === 'flashcard-table'",
            'state.bookmarkFilter',
            'bookmarkOk',
            'const AI_REWRITE_FIELD_CONFIG = {',
            'function aiRewriteDisplayText(card, field)',
            'function renderAiRewriteControls(card)',
            'async function previewAiRewrite(field)',
            '/ai-rewrite/preview',
            '/ai-rewrite/apply',
            'AI 변환 중',
            'conceptImageScale: 1,',
            'const CONCEPT_IMAGE_SCALE_MIN = 0.8;',
            'const CONCEPT_MEDIA_TYPES = Object.freeze',
            'function updateConceptImageZoomControls({hasMedia = false} = {})',
            'function stepConceptImageScale(delta)',
            'function conceptImageScalePercent()',
            'function conceptMediaDisplayState(card)',
            'async function previewConceptImage()',
            'async function saveConceptMedia()',
            '/ai-image/preview',
            '/ai-image/apply',
            '/ai-image/discard',
            '/concept-media',
            'function openConceptMediaDialog()',
            'function updateConceptMediaDialogPlaceholder()',
            'function openConceptImageDialog()',
            'function closeConceptImageDialog({restoreFocus = true} = {})',
            "$('conceptMediaEditBtn')?.addEventListener('click'",
            "$('conceptMediaDialogSaveBtn')?.addEventListener('click', saveConceptMedia);",
            "$('conceptImageZoomBtn')?.addEventListener('click'",
            "$('conceptImageZoomOutBtn')?.addEventListener('click'",
            "$('conceptImageZoomInBtn')?.addEventListener('click'",
            'setMessage(`${current.term}: 이미지 크기 ${conceptImageScalePercent()}%`);',
            'openConceptImageDialog();',
            'AI 이미지 생성 중',
        ]:
            self.assertIn(snippet, APP_JS)
        self.assertIn("window.setTimeout(() => {\n        try {\n          openerRef[callbackName](...args);\n          openerRef.focus?.();\n        } catch (_error) {}\n      }, 0);", APP_JS)
        self.assertNotIn("}, 0);\n      }, 0);", APP_JS)
        self.assertNotIn("openerRef.focus?.();\n          window.focus();", APP_JS)
        for snippet in [
            '.section-title-row',
            '.inline-ai-actions',
            '.inline-ai-btn',
            '.inline-ai-btn.save',
            '.concept-image-actions',
            '.concept-image-action',
            '.concept-image-action.zoom',
            '.concept-image-action.zoom-step',
            '.concept-media-stage',
            '.concept-video',
            '.concept-media-iframe',
            '.concept-media-mermaid',
            '.concept-media-editor-modal',
            '.concept-image-placeholder',
            '.concept-image-wrap.is-empty',
            '.concept-image-modal-image',
            '.concept-image-modal-iframe',
        ]:
            self.assertIn(snippet, STYLE_CSS)
        self.assertIn('max-height: calc(clamp(165px, 30vh, 280px) * var(--concept-image-scale, 1));', STYLE_CSS)
        self.assertIn('max-height: calc(205px * var(--concept-image-scale, 1));', STYLE_CSS)
        self.assertIn('id="conceptImageZoomOutBtn"', INDEX_HTML)
        self.assertIn('id="conceptImageZoomInBtn"', INDEX_HTML)
        self.assertIn('id="conceptImageZoomBtn"', INDEX_HTML)
        self.assertIn('id="conceptImageDialog"', INDEX_HTML)

    def test_mind_map_popup_script_contract_is_scoped_and_stable(self):
        popup_block = APP_JS.split('function renderMindMapWindow() {', 1)[1].split('function bootstrapMindMapPopupWindow() {', 1)[0]
        self.assertIn("const invokeOpener = (callbackName, ...args) => {", popup_block)
        self.assertIn("const cardId = trigger.dataset.cardId || decodeURIComponent(href.replace(/^card:/, ''));", popup_block)
        self.assertIn("invokeOpener('__csFlashcardsMindMapClosed');", popup_block)
        self.assertIn('openerRef.focus?.();', popup_block)
        self.assertNotIn('window.focus();', popup_block)
        self.assertEqual(popup_block.count("invokeOpener('__csFlashcardsSelectCardFromMindMap'"), 1)
        self.assertEqual(popup_block.count("invokeOpener('__csFlashcardsMindMapClosed');"), 1)
        self.assertEqual(popup_block.count('window.setTimeout(() => {'), 1)
        self.assertIn('renderMindMapPluginWindow(popup);', APP_JS)
        self.assertIn('function renderMindMapPluginWindow(popupWindow, attempt = 0) {', APP_JS)

    def test_mind_map_popup_bootstrap_and_reopen_contract(self):
        bootstrap_block = APP_JS.split('function bootstrapMindMapPopupWindow() {', 1)[1].split('function openMindMapWindow() {', 1)[0]
        open_block = APP_JS.split('function openMindMapWindow() {', 1)[1].split("function flashcardTablePopupRequested() {", 1)[0]
        self.assertIn('openerRef.__csFlashcardsRegisterMindMapWindow(window);', bootstrap_block)
        self.assertIn("typeof openerRef.__csFlashcardsRegisterMindMapWindow !== 'function'", bootstrap_block)
        self.assertIn('if (state.mindMapWindow && !state.mindMapWindow.closed) {', open_block)
        self.assertIn('renderMindMapWindow();', open_block)
        self.assertIn('state.mindMapWindow.focus();', open_block)
        self.assertIn("const popup = window.open(popupUrl.toString(), 'csFlashcardsMindMapWindow'", open_block)
        self.assertIn('state.mindMapWindow = popup;', open_block)
        self.assertIn('popup.focus();', open_block)

    def test_mind_map_popup_prefers_markmap_plugin_with_tree_fallback(self):
        popup_block = APP_JS.split('function renderMindMapWindow() {', 1)[1].split('function bootstrapMindMapPopupWindow() {', 1)[0]
        for snippet in [
            '플러그인 마인드맵',
            '현재 필터 카드 → 가지형 마인드맵',
            'renderMindMapMarkdown(layout, summaryText)',
            'mindmapPluginShell',
            'mindmapMarkmap',
            'mindmapFallbackTree',
            'renderMindMapPluginWindow(popup);',
            'https://cdn.jsdelivr.net/npm/d3@7',
            'https://cdn.jsdelivr.net/npm/markmap-view@0.18.9',
            'https://cdn.jsdelivr.net/npm/markmap-lib@0.18.9',
            '가장 많이 연결된 대분류부터 정렬하고',
            '연결량이 큰 대분류 → 소분류 → 카드 순서',
            '연결 순위 ${group.connectionRank}위',
            '최상위 허브',
            '소분류 ·',
            "event.target.closest('[data-card-id], a[href^=\"card:\"]')",
        ]:
            self.assertIn(snippet, popup_block)
        self.assertIn('connectionScore = (group.totalConnectionCount * 100)', APP_JS)
        self.assertIn('function renderMindMapPluginWindow(popupWindow, attempt = 0) {', APP_JS)
        self.assertIn('const markmapApi = popupWindow.markmap;', APP_JS)

    def test_wiki_ui_and_flashcard_links_are_present(self):
        self.assertIn('id="wikiHomeLink"', INDEX_HTML)
        self.assertIn('id="questionBankPageLink"', INDEX_HTML)
        self.assertIn('href="/wiki"', INDEX_HTML)
        self.assertIn('href="/question-bank"', INDEX_HTML)
        self.assertIn('문제 풀이 · 문제은행', INDEX_HTML)
        self.assertIn('target="_blank"', INDEX_HTML)
        menu_popover = INDEX_HTML.split('id="menuPopover"', 1)[1].split('</div>', 1)[0]
        self.assertIn('id="wikiHomeLink"', menu_popover)
        self.assertIn('id="questionBankPageLink"', menu_popover)
        self.assertIn('id="mindMapBtn"', menu_popover)
        self.assertNotIn('id="questionPracticeBtn"', menu_popover)
        self.assertIn('function renderSourceLinks(sourceFiles)', APP_JS)
        self.assertIn("$('sources').innerHTML = renderSourceLinks(c.source_files);", APP_JS)
        self.assertIn('/wiki/page/', APP_JS)
        self.assertIn('id="frontWikiLink"', INDEX_HTML)
        self.assertIn('id="backWikiLink"', INDEX_HTML)
        self.assertIn('id="wikiSearchInput"', WIKI_HTML)
        self.assertIn('id="bankPageList"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageCategoryInput"', QUESTION_BANK_HTML)
        self.assertIn('<select id="bankPageIssuerInput"', QUESTION_BANK_HTML)

        self.assertIn('문제 풀이 · 문제은행', QUESTION_BANK_HTML)
        self.assertIn('id="bankPageTogglePracticeBtn"', QUESTION_BANK_HTML)
        self.assertNotIn('bankPageOpenPracticeTab', QUESTION_BANK_HTML)
        self.assertIn('/api/question-bank', QUESTION_BANK_JS)
        self.assertIn('QUESTION_BANK_LAUNCH_KEY', QUESTION_BANK_JS)
        self.assertIn('QUESTION_BANK_PRACTICE_COLLAPSED_KEY', QUESTION_BANK_JS)
        self.assertIn('function populateIssuerOptions(', QUESTION_BANK_JS)
        self.assertIn('function populateCategoryOptions(', QUESTION_BANK_JS)
        self.assertIn('available_issuers', QUESTION_BANK_JS)
        self.assertIn('available_categories', QUESTION_BANK_JS)
        self.assertIn('question-keyword-link', QUESTION_BANK_JS)
        self.assertIn('card_query=', QUESTION_BANK_JS)

        self.assertIn('id="bankPagePracticeFrame"', QUESTION_BANK_HTML)
        self.assertIn('id="bankPagePracticePlaceholder"', QUESTION_BANK_HTML)
        self.assertIn('function practiceFrameUrl()', QUESTION_BANK_JS)
        self.assertIn('function setPracticeCollapsed(', QUESTION_BANK_JS)
        self.assertIn('question-bank-embed=1', QUESTION_BANK_JS)
        self.assertIn("get('question-bank-embed') === '1'", APP_JS)
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
        self.assertIn('id="wikiEditBtn"', WIKI_HTML)
        self.assertIn('id="wikiEditorPanel"', WIKI_HTML)
        self.assertIn('id="wikiEditorTextarea"', WIKI_HTML)
        self.assertIn('id="wikiEditorSaveBtn"', WIKI_HTML)
        self.assertIn('id="wikiEditorCancelBtn"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiBtn"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiInstruction"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiStatus"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiTemplates"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiTemplateToggle"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiTemplateEditor"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiTemplateList"', WIKI_HTML)
        self.assertIn('id="wikiEditorAiTemplateResetBtn"', WIKI_HTML)
        self.assertLess(WIKI_HTML.index('id="wikiPageNav"'), WIKI_HTML.index('id="wikiRawLink"'))
        self.assertLess(WIKI_HTML.index('id="wikiArticle"'), WIKI_HTML.index('id="wikiRawLink"'))
        self.assertIn('pretendard.css', WIKI_HTML)
        self.assertIn('/static/ai-tools.js', INDEX_HTML)
        self.assertIn('/static/ai-tools.js', WIKI_HTML)
        self.assertIn('window.CsAiTools', AI_TOOLS_JS)
        self.assertIn('function setButtonBusy(', AI_TOOLS_JS)
        self.assertIn('function createPromptTemplateManager(', AI_TOOLS_JS)
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
        self.assertIn('function wikiApplyEditorState()', WIKI_JS)
        self.assertIn('function wikiStartEdit()', WIKI_JS)
        self.assertIn('function wikiSaveEditor()', WIKI_JS)
        self.assertIn('function wikiEditorHasUnsavedChanges()', WIKI_JS)
        self.assertIn('function wikiFetchText(', WIKI_JS)
        self.assertIn('/api/wiki/page', WIKI_JS)
        self.assertIn('function wikiRunAiRewrite()', WIKI_JS)
        self.assertIn('/api/wiki/ai-rewrite/preview', WIKI_JS)
        self.assertIn('wikiEditorAiBtn', WIKI_JS)
        self.assertIn('wikiEditorAiInstruction', WIKI_JS)
        self.assertIn('wikiEditorAiStatus', WIKI_JS)
        self.assertIn('WIKI_AI_TEMPLATE_STORAGE_KEY', WIKI_JS)
        self.assertIn('function wikiRenderAiTemplateUi()', WIKI_JS)
        self.assertIn('function wikiApplyAiTemplate(templateId)', WIKI_JS)
        self.assertIn('function wikiResetAiTemplates()', WIKI_JS)
        self.assertIn('wikiEditorAiTemplateToggle', WIKI_JS)
        self.assertIn('wikiEditorAiTemplateResetBtn', WIKI_JS)
        self.assertIn('wikiEditorAiTemplates', WIKI_JS)
        self.assertIn('window.CsAiTools', APP_JS)
        self.assertIn("event.key.toLowerCase() === 's'", WIKI_JS)
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
        self.assertIn('.wiki-page-footer', STYLE_CSS)
        self.assertIn('.wiki-editor', STYLE_CSS)
        self.assertIn('.wiki-editor-textarea', STYLE_CSS)
        self.assertIn('.wiki-editor-actions', STYLE_CSS)
        self.assertIn('.wiki-editor-ai', STYLE_CSS)
        self.assertIn('.wiki-editor-ai-input', STYLE_CSS)
        self.assertIn('.wiki-editor-ai-status', STYLE_CSS)
        self.assertIn('.wiki-editor-ai-template-bar', STYLE_CSS)
        self.assertIn('.wiki-editor-ai-templates', STYLE_CSS)
        self.assertIn('.wiki-editor-ai-template-btn', STYLE_CSS)
        self.assertIn('.wiki-editor-ai-template-editor', STYLE_CSS)
        self.assertIn('.wiki-editor-ai-template-field', STYLE_CSS)
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
        self.assertIn('.wiki-article ul ul', STYLE_CSS)
        self.assertIn('.wiki-article ul ul ul', STYLE_CSS)
        self.assertIn('.wiki-article ol ol', STYLE_CSS)
        self.assertIn('.wiki-article ol ol ol', STYLE_CSS)
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
            'id="questionBankTopicInput"',
            'id="questionBankFieldInput"',
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
            'function openQuestionBankSession(startIndex = 0)',
            'function consumePendingQuestionBankLaunch()',
            'PENDING_QUESTION_BANK_LAUNCH_KEY',
            'function renderQuestionMarkdown(source)',
            'question-md-image',
            'question-bank-item',
            'function renderQuestionPanel()',
            'function revealQuestionAnswer()',
            'function openQuestionSourceCard()',
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
            'function saveQuestionAttempt(question, {quiet = false} = {})',
            'function setQuestionJudgment(judgment)',
            'function finishQuestionSession()',
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
            'question-review-box',
            'question-review-actions',
            "markQuestionSourceCard('O')",
            "markQuestionSourceCard('X')",
            'const reviewCard = currentQuestionCard();',
            'question-history-field',
            'question-session-meta',
            'question-history-session-meta',
        ]:
            self.assertIn(snippet, APP_JS)
        self.assertIn('id="questionHistoryDialog"', INDEX_HTML)
        self.assertIn('id="questionHistoryBody"', INDEX_HTML)
        self.assertIn('id="questionImportDialog"', INDEX_HTML)
        self.assertIn('id="questionImportInput"', INDEX_HTML)
        self.assertIn('id="questionImportApplyBtn"', INDEX_HTML)
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
        self.assertIn('question-bank-shell-topbar', QUESTION_BANK_HTML)
        self.assertIn('.question-bank-shell', STYLE_CSS)
        self.assertIn('.question-bank-shell-topbar', STYLE_CSS)
        self.assertIn('.question-bank-embed .topbar', STYLE_CSS)
        self.assertIn('body.question-bank-embed #questionBankToggleBtn', STYLE_CSS)
        self.assertIn('body.question-bank-embed #questionBankBrowser', STYLE_CSS)
        self.assertIn('body.question-bank-embed {', STYLE_CSS)
        self.assertIn('.question-bank-practice-collapsed', TABLE_SHELL_CSS)
        self.assertIn('.question-bank-practice-placeholder[hidden]', TABLE_SHELL_CSS)


if __name__ == '__main__':
    unittest.main()
