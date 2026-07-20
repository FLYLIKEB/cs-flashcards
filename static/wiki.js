const WIKI_SIDEBAR_STATE_KEY = 'csFlashcardsWikiSidebar:v1';

const wikiState = {
  index: null,
  page: null,
  currentSlug: '',
  query: '',
  sidebarOpen: true,
  searchOpen: false,
  expandedToc: {},
  editorOpen: false,
  editorLoading: false,
  editorSaving: false,
  editorAiLoading: false,
  editorAiStatus: '',
  editorAiStatusError: false,
  editorAiTemplates: [],
  editorAiSelectedTemplateId: '',
  editorAiTemplateEditorOpen: false,
  editorSourcePath: '',
  editorOriginalContent: '',
};

const wiki$ = (id) => document.getElementById(id);
const wikiAiTools = window.CsAiTools || null;
let wikiMarkdownEditor = null;
let wikiMarkdownPreviewSideBySide = false;
let wikiPreviewRequestToken = 0;

const WIKI_AI_TEMPLATE_STORAGE_KEY = 'csFlashcardsWikiAiPromptTemplates:v1';
const WIKI_AI_PROMPT_TEMPLATES = Object.freeze([
  {
    id: 'easy',
    label: '쉽게',
    instruction: '아주 길고 상세하고 이해하기 쉽게 다시 써줘. 빠진 개념 없이 핵심 정의, 배경, 동작 원리, 예시, 주의점, 관련 개념까지 전부 포함해줘. Markdown 제목/목록/표/인용/코드블록을 적절히 활용하고, 기존 내부 링크·외부 링크·표·체크리스트는 최대한 유지해줘.',
  },
  {
    id: 'compact',
    label: '압축',
    instruction: '중복을 줄이고 핵심만 빠르게 복습할 수 있게 다시 정리해줘. 정의, 차이점, 암기 포인트 위주로 짧고 밀도 높게 정리하고 기존 링크와 표는 유지해줘.',
  },
  {
    id: 'interview',
    label: '면접형',
    instruction: '기술면접 답변용으로 다시 써줘. 한 줄 정의 → 왜 중요한지 → 동작 원리 → 장단점/트레이드오프 → 꼬리질문 포인트 순서로 정리하고, 기존 링크와 표는 유지해줘.',
  },
  {
    id: 'structured',
    label: '구조화',
    instruction: '문단 구조를 더 읽기 쉽게 재배치해줘. 제목 계층, 요약, 비교표, 체크리스트를 활용하고 내용 누락 없이 기존 링크와 표를 유지해줘.',
  },
]);
const wikiAiTemplateManager = wikiAiTools?.createPromptTemplateManager
  ? wikiAiTools.createPromptTemplateManager({
      storageKey: WIKI_AI_TEMPLATE_STORAGE_KEY,
      defaults: WIKI_AI_PROMPT_TEMPLATES,
    })
  : null;

function wikiEscapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
}

function wikiPageUrl(slug) {
  const normalized = String(slug || '').trim().replace(/^\/+|\/+$/g, '');
  if (!normalized) return '/wiki';
  return `/wiki/page/${encodeURIComponent(normalized).replace(/%2F/g, '/')}`;
}

function wikiApiUrl(path) {
  return new window.URL(String(path || '/'), window.location.origin).toString();
}

function wikiCurrentSlug() {
  const prefix = '/wiki/page/';
  if (window.location.pathname.startsWith(prefix)) {
    return decodeURIComponent(window.location.pathname.slice(prefix.length)).replace(/^\/+|\/+$/g, '');
  }
  return '';
}

function wikiDefaultSidebarOpen() {
  return window.matchMedia('(min-width: 721px)').matches;
}

function readSavedWikiSidebarState() {
  if (wikiDefaultSidebarOpen()) return true;
  try {
    const saved = window.localStorage.getItem(WIKI_SIDEBAR_STATE_KEY);
    if (saved === 'open') return true;
    if (saved === 'closed') return false;
  } catch (_error) {
    // Ignore storage failures and fall back to mobile default.
  }
  return false;
}

function saveWikiSidebarState() {
  try {
    window.localStorage.setItem(WIKI_SIDEBAR_STATE_KEY, wikiState.sidebarOpen ? 'open' : 'closed');
  } catch (_error) {
    // Ignore storage failures.
  }
}

function applyWikiSidebarState({persist = true} = {}) {
  document.body.classList.toggle('wiki-sidebar-collapsed', !wikiState.sidebarOpen);
  wiki$('wikiSidebar')?.setAttribute('aria-hidden', String(!wikiState.sidebarOpen));
  const toggleBtn = wiki$('wikiSidebarToggleBtn');
  if (toggleBtn) {
    toggleBtn.textContent = '목차';
    toggleBtn.setAttribute('aria-expanded', String(wikiState.sidebarOpen));
    toggleBtn.setAttribute('aria-label', wikiState.sidebarOpen ? '목차 숨기기' : '목차 보기');
    toggleBtn.setAttribute('title', wikiState.sidebarOpen ? '목차 숨기기' : '목차 보기');
  }
  if (persist) saveWikiSidebarState();
}

function toggleWikiSidebar(force = !wikiState.sidebarOpen) {
  wikiState.sidebarOpen = Boolean(force);
  applyWikiSidebarState();
}

function closeWikiSidebarOnMobile() {
  if (!window.matchMedia('(max-width: 720px)').matches) return;
  if (!wikiState.sidebarOpen) return;
  toggleWikiSidebar(false);
}

function applyWikiSearchState({focus = false} = {}) {
  const searchWrap = wiki$('wikiSearch');
  const searchInput = wiki$('wikiSearchInput');
  const toggleBtn = wiki$('wikiSearchToggleBtn');
  if (searchWrap) {
    searchWrap.hidden = !wikiState.searchOpen;
    searchWrap.setAttribute('aria-hidden', String(!wikiState.searchOpen));
  }
  if (toggleBtn) {
    toggleBtn.setAttribute('aria-expanded', String(wikiState.searchOpen));
    toggleBtn.setAttribute('aria-label', wikiState.searchOpen ? '검색 닫기' : '검색 열기');
    toggleBtn.setAttribute('title', wikiState.searchOpen ? '검색 닫기' : '검색');
  }
  if (searchInput) {
    searchInput.tabIndex = wikiState.searchOpen ? 0 : -1;
    if (!wikiState.searchOpen) {
      searchInput.blur();
    } else if (focus) {
      searchInput.focus({preventScroll: true});
      searchInput.select();
    }
  }
}

function toggleWikiSearch(force = !wikiState.searchOpen, {focus = true} = {}) {
  wikiState.searchOpen = Boolean(force);
  applyWikiSearchState({focus: wikiState.searchOpen && focus});
}

function closeWikiSearch() {
  if (!wikiState.searchOpen) return;
  toggleWikiSearch(false, {focus: false});
}

function wikiShowSearchResults() {
  if (!wikiState.sidebarOpen) toggleWikiSidebar(true);
  const matches = Array.from(document.querySelectorAll('#wikiToc .wiki-toc-link'));
  if (!matches.length) {
    wikiStatus('일치하는 문서가 없습니다.');
    return;
  }
  closeWikiSearch();
  matches[0].focus({preventScroll: true});
  matches[0].scrollIntoView({block: 'nearest'});
  wikiStatus(`검색 결과 ${matches.length}건`);
}

function wikiStatus(text, isError = false) {
  const el = wiki$('wikiStatus');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('error-text', Boolean(isError));
}

function wikiFilteredTree(items, query) {
  const normalized = String(query || '').trim().toLowerCase();
  if (!normalized) return items;
  return items.reduce((acc, item) => {
    const children = wikiFilteredTree(item.children || [], normalized);
    if (String(item.title || '').toLowerCase().includes(normalized) || children.length) {
      acc.push({...item, children});
    }
    return acc;
  }, []);
}

function wikiActiveTrailSlugs() {
  const crumbs = wikiState.index?.breadcrumbs?.[wikiState.currentSlug] || [];
  return new Set(crumbs.map((crumb) => String(crumb?.slug || '').trim()).filter(Boolean));
}

function wikiTocBranchExpanded(item, activeTrail = wikiActiveTrailSlugs()) {
  if (!item.children?.length) return false;
  if (wikiState.query) return true;
  if (Object.prototype.hasOwnProperty.call(wikiState.expandedToc, item.slug)) {
    return Boolean(wikiState.expandedToc[item.slug]);
  }
  return activeTrail.has(item.slug);
}

function toggleWikiTocBranch(slug) {
  const normalized = String(slug || '').trim();
  if (!normalized) return;
  wikiState.expandedToc[normalized] = !Boolean(wikiState.expandedToc[normalized]);
  wikiRenderToc();
}

function wikiRenderTocItems(items, activeTrail = wikiActiveTrailSlugs()) {
  if (!items.length) return '<p class="small muted">일치하는 문서가 없습니다.</p>';
  return `<ul>${items.map((item) => {
    const active = item.slug === wikiState.currentSlug;
    const hasChildren = Boolean(item.children?.length);
    const expanded = wikiTocBranchExpanded(item, activeTrail);
    const children = hasChildren && expanded ? wikiRenderTocItems(item.children, activeTrail) : '';
    const toggle = hasChildren
      ? `<button class="wiki-toc-toggle" type="button" data-wiki-toc-toggle="${wikiEscapeHtml(item.slug)}" aria-expanded="${expanded}" aria-label="${expanded ? '하위 목차 접기' : '하위 목차 펼치기'}">▸</button>`
      : '<span class="wiki-toc-spacer" aria-hidden="true"></span>';
    return `<li class="wiki-toc-item${hasChildren ? ' has-children' : ''}${expanded ? ' open' : ''}"><div class="wiki-toc-row">${toggle}<a class="wiki-toc-link${active ? ' active' : ''}" href="${wikiPageUrl(item.slug)}" data-wiki-nav="1"${active ? ' aria-current="page"' : ''}>${wikiEscapeHtml(item.title)}</a></div>${children}</li>`;
  }).join('')}</ul>`;
}

function wikiRenderToc() {
  const toc = wiki$('wikiToc');
  if (!toc || !wikiState.index) return;
  const filtered = wikiFilteredTree(wikiState.index.tree || [], wikiState.query);
  toc.innerHTML = wikiRenderTocItems(filtered);
}

function wikiRenderBreadcrumbs(page) {
  const el = wiki$('wikiBreadcrumbs');
  if (!el) return;
  const crumbs = Array.isArray(page?.breadcrumbs) ? page.breadcrumbs : [];
  el.innerHTML = crumbs.map((crumb) => `<a href="${wikiPageUrl(crumb.slug)}" data-wiki-nav="1">${wikiEscapeHtml(crumb.title)}</a>`).join(' <span>›</span> ');
}

function wikiNavigationItems() {
  const items = [];
  const seen = new Set();
  const book = wikiState.index?.book;
  if (book?.available !== false) {
    const bookSlug = String(book?.slug || '_book').trim() || '_book';
    items.push({
      title: book?.title || '책 소개',
      slug: bookSlug,
      url: wikiPageUrl(bookSlug),
    });
    seen.add(bookSlug);
  }
  for (const item of Array.isArray(wikiState.index?.flat) ? wikiState.index.flat : []) {
    const slug = String(item?.slug || '').trim();
    if (!slug || seen.has(slug)) continue;
    items.push({
      title: item?.title || slug,
      slug,
      url: wikiPageUrl(slug),
    });
    seen.add(slug);
  }
  return items;
}

function wikiPageNavLink(item, direction) {
  if (!item) return '<span class="wiki-page-nav-link is-empty" aria-hidden="true"></span>';
  const label = direction === 'next' ? '다음 글' : '이전 글';
  const rel = direction === 'next' ? 'next' : 'prev';
  return `
    <a class="wiki-page-nav-link ${direction}" href="${wikiPageUrl(item.slug)}" data-wiki-nav="1" rel="${rel}">
      <span class="wiki-page-nav-kicker">${label}</span>
      <strong>${wikiEscapeHtml(item.title)}</strong>
    </a>`;
}

function wikiRenderPageNav(page) {
  const el = wiki$('wikiPageNav');
  if (!el) return;
  const items = wikiNavigationItems();
  const currentSlug = String(page?.slug || wikiState.currentSlug || '').trim();
  const currentIndex = items.findIndex((item) => item.slug === currentSlug);
  if (currentIndex < 0) {
    el.hidden = true;
    el.innerHTML = '';
    return;
  }
  const previous = currentIndex > 0 ? items[currentIndex - 1] : null;
  const next = currentIndex < items.length - 1 ? items[currentIndex + 1] : null;
  if (!previous && !next) {
    el.hidden = true;
    el.innerHTML = '';
    return;
  }
  el.hidden = false;
  el.innerHTML = `${wikiPageNavLink(previous, 'prev')}${wikiPageNavLink(next, 'next')}`;
}

function wikiRenderLinkedCards(page) {
  const linkedCards = Array.isArray(page?.linked_cards) ? page.linked_cards : [];
  const flashcardLink = wiki$('wikiFlashcardLink');
  if (flashcardLink) {
    const primary = page?.primary_card || null;
    flashcardLink.hidden = !primary?.card_url;
    flashcardLink.href = primary?.card_url || '/';
    flashcardLink.textContent = primary?.term ? `${primary.term} 카드` : '대표 카드';
    flashcardLink.title = primary?.term ? `${primary.term} 카드 열기` : '대표 카드 열기';
  }
  const box = wiki$('wikiLinkedCards');
  if (!box) return;
  if (!linkedCards.length) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  box.hidden = false;
  box.innerHTML = `
    <strong>연결된 플래시카드 ${linkedCards.length}개</strong>
    <p>문서 제목이나 출처 파일과 연결된 카드입니다.</p>
    <div class="wiki-linked-card-list">
      ${linkedCards.map((card) => {
        const meta = [card.category || '', Number(card.question_wrong_count || 0) > 0 ? `오답 ${card.question_wrong_count}` : ''].filter(Boolean).join(' · ');
        return `<a class="wiki-linked-card-link" href="${wikiEscapeHtml(card.card_url || '/')}" target="_blank" rel="noopener noreferrer"><span>${wikiEscapeHtml(card.term || card.id || '카드')}</span>${meta ? `<span class="wiki-linked-card-meta">${wikiEscapeHtml(meta)}</span>` : ''}</a>`;
      }).join('')}
    </div>`;
}

function wikiEditablePage(page = wikiState.page) {
  return Boolean(page?.source_path && page?.raw_url);
}

function wikiEditorInstance() {
  return wikiMarkdownEditor;
}

function wikiEditorValue() {
  const editor = wikiEditorInstance();
  return editor ? editor.value() : (wiki$('wikiEditorTextarea')?.value || '');
}

function wikiSetEditorValue(value, {clearHistory = false} = {}) {
  const nextValue = String(value || '');
  const editor = wikiEditorInstance();
  if (editor?.codemirror) {
    editor.value(nextValue);
    if (clearHistory) editor.codemirror.clearHistory();
    return;
  }
  const textarea = wiki$('wikiEditorTextarea');
  if (textarea) textarea.value = nextValue;
}

function wikiFocusEditor() {
  const editor = wikiEditorInstance();
  if (editor?.codemirror) {
    editor.codemirror.refresh();
    editor.codemirror.focus();
    return;
  }
  wiki$('wikiEditorTextarea')?.focus({preventScroll: true});
}

function wikiEditorPreviewPlaceholder(text = '미리보기를 불러오는 중입니다.') {
  return `<p class="wiki-editor-preview-loading">${wikiEscapeHtml(text)}</p>`;
}

function wikiEditorPreviewSourcePath() {
  return String(wikiState.editorSourcePath || wikiState.page?.source_path || '').trim();
}

async function wikiRenderPreviewMarkdown(sourcePath, content) {
  if (wikiAiTools?.postJson) {
    return wikiAiTools.postJson(wikiApiUrl('/api/wiki/render-preview'), {
      source_path: sourcePath,
      content,
    });
  }
  return wikiFetchJson(wikiApiUrl('/api/wiki/render-preview'), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      source_path: sourcePath,
      content,
    }),
  });
}

function wikiEnsureMarkdownEditor() {
  if (wikiMarkdownEditor) return wikiMarkdownEditor;
  if (typeof window.EasyMDE !== 'function') return null;
  const textarea = wiki$('wikiEditorTextarea');
  if (!textarea) return null;
  wikiMarkdownEditor = new window.EasyMDE({
    element: textarea,
    autoDownloadFontAwesome: false,
    autofocus: false,
    autoRefresh: {delay: 120},
    forceSync: true,
    inputStyle: 'textarea',
    lineNumbers: true,
    minHeight: '420px',
    nativeSpellcheck: false,
    placeholder: 'Markdown 원문을 입력하세요.',
    previewClass: ['wiki-article', 'wiki-editor-preview'],
    previewRender: (plainText, previewEl) => {
      const preview = previewEl || null;
      const sourcePath = wikiEditorPreviewSourcePath();
      const token = ++wikiPreviewRequestToken;
      const loadingHtml = wikiEditorPreviewPlaceholder();
      if (!preview) return loadingHtml;
      preview.innerHTML = loadingHtml;
      if (!sourcePath) {
        preview.innerHTML = wikiEditorPreviewPlaceholder('미리보기에 필요한 원본 경로를 찾지 못했습니다.');
        return loadingHtml;
      }
      wikiRenderPreviewMarkdown(sourcePath, plainText).then((data) => {
        if (token !== wikiPreviewRequestToken || !preview.isConnected) return;
        preview.innerHTML = data?.html || '<p class="muted">미리보기 결과가 비어 있습니다.</p>';
      }).catch((error) => {
        if (token !== wikiPreviewRequestToken || !preview.isConnected) return;
        preview.innerHTML = `<p class="error-text">${wikiEscapeHtml(error.message || error)}</p>`;
      });
      return loadingHtml;
    },
    sideBySideFullscreen: false,
    spellChecker: false,
    status: false,
    syncSideBySidePreviewScroll: true,
    toolbar: [
      'bold',
      'italic',
      'heading',
      '|',
      'quote',
      'unordered-list',
      'ordered-list',
      '|',
      'link',
      'table',
      'code',
      '|',
      'preview',
      'side-by-side',
      '|',
      'guide',
    ],
  });
  if (!wikiMarkdownPreviewSideBySide && typeof wikiMarkdownEditor.toggleSideBySide === 'function') {
    wikiMarkdownEditor.toggleSideBySide();
    wikiMarkdownPreviewSideBySide = true;
  }
  wikiMarkdownEditor.codemirror.on('change', () => {
    if (!wikiState.editorOpen) return;
    if (wikiState.editorAiStatus && !wikiState.editorAiStatusError) {
      wikiState.editorAiStatus = '';
      wikiApplyEditorState();
    }
  });
  return wikiMarkdownEditor;
}

function wikiEditorHasUnsavedChanges() {
  return wikiState.editorOpen && wikiEditorValue() !== wikiState.editorOriginalContent;
}

function wikiEditorSyncHint() {
  return wikiEditorInstance() || typeof window.EasyMDE === 'function'
    ? 'Markdown 편집기와 실시간 미리보기로 문서를 수정합니다.'
    : 'Markdown 원문을 직접 수정합니다. 편집기 플러그인을 불러오지 못했습니다.';
}

function wikiEditorAiStatusText() {
  if (wikiState.editorAiLoading) return 'AI가 현재 문서 초안을 생성하는 중입니다.';
  return wikiState.editorAiStatus || '현재 Markdown과 지시문을 기준으로 AI 초안을 편집기에 반영합니다.';
}

function wikiDefaultAiTemplates() {
  return WIKI_AI_PROMPT_TEMPLATES.map((template) => ({...template}));
}

function wikiAiTemplates() {
  if (!Array.isArray(wikiState.editorAiTemplates) || !wikiState.editorAiTemplates.length) {
    wikiState.editorAiTemplates = wikiAiTemplateManager?.getTemplates?.() || wikiDefaultAiTemplates();
  }
  return wikiState.editorAiTemplates;
}

function wikiAiTemplateButtonLabel(template, index) {
  return String(template?.label || '').trim() || `템플릿 ${index + 1}`;
}

function wikiUpdateAiTemplate(id, patch = {}) {
  const templateId = String(id || '').trim();
  const nextTemplates = wikiAiTemplateManager?.updateTemplate?.(templateId, patch)
    || wikiAiTemplates().map((template) => (
      template.id === templateId ? {...template, ...patch, id: template.id} : {...template}
    ));
  wikiState.editorAiTemplates = Array.isArray(nextTemplates) && nextTemplates.length ? nextTemplates : wikiDefaultAiTemplates();
  return wikiState.editorAiTemplates;
}

function wikiRenderAiTemplateUi() {
  const templates = wikiAiTemplates();
  const selectedId = String(wikiState.editorAiSelectedTemplateId || '').trim();
  const buttons = wiki$('wikiEditorAiTemplates');
  const list = wiki$('wikiEditorAiTemplateList');
  const toggle = wiki$('wikiEditorAiTemplateToggle');
  const editor = wiki$('wikiEditorAiTemplateEditor');
  if (buttons) {
    buttons.innerHTML = templates.map((template, index) => {
      const active = template.id === selectedId ? ' is-active' : '';
      return `<button type="button" class="wiki-editor-ai-template-btn${active}" data-wiki-ai-template-id="${wikiEscapeHtml(template.id || '')}">${wikiEscapeHtml(wikiAiTemplateButtonLabel(template, index))}</button>`;
    }).join('');
  }
  if (list) {
    list.innerHTML = templates.map((template, index) => {
      const templateId = wikiEscapeHtml(template.id || '');
      return `<section class="wiki-editor-ai-template-card"><div class="wiki-editor-ai-template-row"><label class="wiki-editor-ai-template-field-label" for="wikiEditorAiTemplateLabel-${index + 1}">버튼 이름</label><input id="wikiEditorAiTemplateLabel-${index + 1}" class="wiki-editor-ai-template-field" type="text" maxlength="40" value="${wikiEscapeHtml(template.label || '')}" data-wiki-ai-template-id="${templateId}" data-wiki-ai-template-field="label" /></div><div class="wiki-editor-ai-template-row"><label class="wiki-editor-ai-template-field-label" for="wikiEditorAiTemplateInstruction-${index + 1}">지시문</label><textarea id="wikiEditorAiTemplateInstruction-${index + 1}" class="wiki-editor-ai-template-field wiki-editor-ai-template-textarea" rows="4" maxlength="4000" data-wiki-ai-template-id="${templateId}" data-wiki-ai-template-field="instruction">${wikiEscapeHtml(template.instruction || '')}</textarea></div></section>`;
    }).join('');
  }
  if (toggle) {
    toggle.textContent = wikiState.editorAiTemplateEditorOpen ? '템플릿 접기' : '템플릿 수정';
  }
  if (editor) {
    const showEditor = wikiState.editorOpen && wikiState.editorAiTemplateEditorOpen;
    editor.hidden = !showEditor;
    editor.setAttribute('aria-hidden', String(!showEditor));
  }
}

function wikiToggleAiTemplateEditor(force = !wikiState.editorAiTemplateEditorOpen) {
  wikiState.editorAiTemplateEditorOpen = Boolean(force);
  wikiRenderAiTemplateUi();
  wikiApplyEditorState();
}

function wikiApplyAiTemplate(templateId) {
  if (!wikiState.editorOpen || wikiState.editorLoading || wikiState.editorSaving || wikiState.editorAiLoading) return;
  const targetId = String(templateId || '').trim();
  const template = wikiAiTemplates().find((item) => item.id === targetId);
  const instructionInput = wiki$('wikiEditorAiInstruction');
  if (!template || !instructionInput) return;
  instructionInput.value = String(template.instruction || '');
  wikiState.editorAiSelectedTemplateId = template.id;
  wikiState.editorAiStatus = `${wikiAiTemplateButtonLabel(template, 0)} 템플릿을 지시문에 채웠습니다. 필요하면 바로 수정하세요.`;
  wikiState.editorAiStatusError = false;
  wikiRenderAiTemplateUi();
  wikiApplyEditorState();
  instructionInput.focus();
  instructionInput.setSelectionRange(instructionInput.value.length, instructionInput.value.length);
}

function wikiResetAiTemplates() {
  wikiState.editorAiTemplates = wikiAiTemplateManager?.resetTemplates?.() || wikiDefaultAiTemplates();
  wikiState.editorAiSelectedTemplateId = '';
  wikiState.editorAiStatus = 'AI 템플릿을 기본값으로 되돌렸습니다.';
  wikiState.editorAiStatusError = false;
  wikiRenderAiTemplateUi();
  wikiApplyEditorState();
}

function wikiApplyEditorState() {
  const canEdit = wikiEditablePage();
  const open = canEdit && wikiState.editorOpen;
  const editor = open ? wikiEnsureMarkdownEditor() : wikiEditorInstance();
  const editBtn = wiki$('wikiEditBtn');
  const panel = wiki$('wikiEditorPanel');
  const article = wiki$('wikiArticle');
  const pageNav = wiki$('wikiPageNav');
  const textarea = wiki$('wikiEditorTextarea');
  const aiInstruction = wiki$('wikiEditorAiInstruction');
  const aiButton = wiki$('wikiEditorAiBtn');
  const aiStatus = wiki$('wikiEditorAiStatus');
  const templateToggle = wiki$('wikiEditorAiTemplateToggle');
  const templateEditor = wiki$('wikiEditorAiTemplateEditor');
  const templateResetBtn = wiki$('wikiEditorAiTemplateResetBtn');
  const cancelBtn = wiki$('wikiEditorCancelBtn');
  const saveBtn = wiki$('wikiEditorSaveBtn');
  const source = wiki$('wikiEditorSource');
  const hint = wiki$('wikiEditorHint');
  const editorBusy = wikiState.editorLoading || wikiState.editorSaving || wikiState.editorAiLoading;

  wikiRenderAiTemplateUi();

  if (editBtn) {
    editBtn.hidden = !canEdit || open;
    editBtn.disabled = editorBusy;
  }
  if (panel) {
    panel.hidden = !open;
    panel.setAttribute('aria-hidden', String(!open));
  }
  if (article) {
    article.hidden = open;
  }
  if (pageNav && open) {
    pageNav.hidden = true;
  }
  if (source) {
    source.textContent = open ? (wikiState.editorSourcePath || wikiState.page?.source_path || '') : '';
  }
  if (hint) {
    hint.textContent = wikiState.editorLoading ? '문서 원본을 불러오는 중입니다.' : wikiEditorSyncHint();
  }
  if (editor?.codemirror) {
    editor.codemirror.setOption('readOnly', editorBusy ? 'nocursor' : false);
    if (open) window.requestAnimationFrame(() => editor.codemirror.refresh());
  } else if (textarea) {
    textarea.disabled = editorBusy;
    textarea.placeholder = wikiState.editorLoading ? '문서를 불러오는 중입니다...' : 'Markdown 원문을 입력하세요.';
    if (!open) {
      textarea.value = '';
    }
  }
  if (aiInstruction) {
    aiInstruction.disabled = !open || editorBusy;
    if (!open) {
      aiInstruction.value = '';
    }
  }
  document.querySelectorAll('[data-wiki-ai-template-id]').forEach((button) => {
    button.disabled = !open || editorBusy;
  });
  document.querySelectorAll('#wikiEditorAiTemplateList [data-wiki-ai-template-field]').forEach((field) => {
    field.disabled = !open || editorBusy;
  });
  if (templateToggle) {
    templateToggle.disabled = !open || editorBusy;
    templateToggle.textContent = wikiState.editorAiTemplateEditorOpen ? '템플릿 접기' : '템플릿 수정';
  }
  if (templateEditor) {
    const showEditor = open && wikiState.editorAiTemplateEditorOpen;
    templateEditor.hidden = !showEditor;
    templateEditor.setAttribute('aria-hidden', String(!showEditor));
  }
  if (templateResetBtn) {
    templateResetBtn.disabled = !open || editorBusy;
  }
  if (aiButton) {
    if (wikiAiTools?.setButtonBusy) {
      wikiAiTools.setButtonBusy(aiButton, {
        busy: wikiState.editorAiLoading,
        disabled: !open || editorBusy,
        idleLabel: 'AI',
        busyLabel: '…',
        idleTitle: 'AI로 문서 다듬기',
        busyTitle: 'AI가 문서를 다듬는 중입니다',
        idleTip: '위키 AI',
        busyTip: '변환 중',
      });
    } else {
      aiButton.disabled = !open || editorBusy;
      aiButton.textContent = wikiState.editorAiLoading ? '…' : 'AI';
    }
  }
  if (aiStatus) {
    if (wikiAiTools?.setStatus) {
      wikiAiTools.setStatus(aiStatus, open ? wikiEditorAiStatusText() : '', open && wikiState.editorAiStatusError);
    } else {
      aiStatus.textContent = open ? wikiEditorAiStatusText() : '';
      aiStatus.classList.toggle('error-text', Boolean(open && wikiState.editorAiStatusError));
    }
  }
  if (cancelBtn) {
    cancelBtn.disabled = !open || wikiState.editorSaving || wikiState.editorAiLoading;
  }
  if (saveBtn) {
    saveBtn.disabled = !open || wikiState.editorLoading || wikiState.editorSaving || wikiState.editorAiLoading;
    saveBtn.textContent = wikiState.editorSaving ? '저장 중...' : '저장';
  }
}

function wikiResetEditorState() {
  wikiState.editorOpen = false;
  wikiState.editorLoading = false;
  wikiState.editorSaving = false;
  wikiState.editorAiLoading = false;
  wikiState.editorAiStatus = '';
  wikiState.editorAiStatusError = false;
  wikiState.editorAiSelectedTemplateId = '';
  wikiState.editorSourcePath = '';
  wikiState.editorOriginalContent = '';
}

function wikiCloseEditor({force = false} = {}) {
  if (!force && wikiEditorHasUnsavedChanges() && !window.confirm('저장하지 않은 변경사항을 버릴까요?')) {
    return false;
  }
  wikiResetEditorState();
  wikiApplyEditorState();
  return true;
}

function wikiConfirmEditorNavigation() {
  if (wikiState.editorAiLoading) {
    wikiStatus('AI 초안 생성이 끝난 뒤 이동하세요.', true);
    return false;
  }
  if (!wikiEditorHasUnsavedChanges()) return true;
  return window.confirm('저장하지 않은 변경사항을 버리고 이동할까요?');
}

function wikiSyncStatusLabel(syncTarget) {
  return syncTarget === 'github' ? 'GitHub 반영 완료' : '로컬 저장 완료';
}

function wikiApplyPage(page) {
  wikiState.page = page || null;
  wikiState.currentSlug = page?.slug || '';
  wiki$('wikiArticle').innerHTML = page?.html || '<p class="muted">문서가 비어 있습니다.</p>';
  wiki$('wikiRawLink').href = page?.raw_url || '#';
  document.title = `${page?.title || '문서'} · ${wikiState.index?.book?.title || 'CS 학습 위키'}`;
  wikiRenderBreadcrumbs(page);
  wikiRenderLinkedCards(page);
  wikiRenderPageNav(page);
  wikiRenderToc();
  wikiApplyEditorState();
  wikiStatus(`${page?.title || '문서'} 열람 중`);
}

async function wikiResponseError(res) {
  if (wikiAiTools?.responseErrorText) return wikiAiTools.responseErrorText(res);
  const raw = await res.text();
  let message = raw || `${res.status}`;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === 'string' && parsed.detail.trim()) {
      message = parsed.detail.trim();
    }
  } catch (_error) {
    // Fall back to the raw text body.
  }
  return message;
}

async function wikiFetchJson(url, options = null) {
  const res = await fetch(url, options || undefined);
  if (!res.ok) {
    throw new Error(await wikiResponseError(res));
  }
  return res.json();
}

async function wikiFetchText(url, options = null) {
  const res = await fetch(url, options || undefined);
  if (!res.ok) {
    throw new Error(await wikiResponseError(res));
  }
  return res.text();
}

async function wikiLoadPage(slug, {push = false} = {}) {
  const normalized = String(slug || wikiState.index?.default_page_slug || '').trim() || '_book';
  const page = await wikiFetchJson(wikiApiUrl(`/api/wiki/page/${encodeURIComponent(normalized).replace(/%2F/g, '/')}`));
  if (push && window.location.pathname !== wikiPageUrl(page.slug)) {
    window.history.pushState({}, '', wikiPageUrl(page.slug));
  }
  wikiApplyPage(page);
}

async function wikiStartEdit() {
  const page = wikiState.page;
  if (!wikiEditablePage(page) || wikiState.editorLoading || wikiState.editorSaving || wikiState.editorAiLoading) return;
  if (wikiState.editorOpen) {
    wikiFocusEditor();
    return;
  }
  wikiState.editorOpen = true;
  wikiState.editorLoading = true;
  wikiState.editorAiLoading = false;
  wikiState.editorAiStatus = '';
  wikiState.editorAiStatusError = false;
  wikiState.editorSourcePath = page?.source_path || '';
  wikiState.editorOriginalContent = '';
  wikiApplyEditorState();
  try {
    const text = await wikiFetchText(wikiApiUrl(page?.raw_url || '#'));
    if (!wikiState.editorOpen || wikiState.editorSourcePath !== (page?.source_path || '')) return;
    wikiState.editorOriginalContent = text;
    wikiSetEditorValue(text, {clearHistory: true});
    wikiStatus(`${page?.title || '문서'} 원본을 불러왔습니다.`);
  } catch (error) {
    wikiStatus(`문서 원본 불러오기 실패: ${error.message || error}`, true);
    wikiCloseEditor({force: true});
    return;
  } finally {
    wikiState.editorLoading = false;
    wikiApplyEditorState();
  }
  wikiFocusEditor();
}

async function wikiRunAiRewrite() {
  if (!wikiState.editorOpen || wikiState.editorLoading || wikiState.editorSaving || wikiState.editorAiLoading) return;
  const sourcePath = wikiEditorPreviewSourcePath();
  const instructionInput = wiki$('wikiEditorAiInstruction');
  const content = wikiEditorValue();
  if (!sourcePath) {
    wikiState.editorAiStatus = 'AI 수정 실패: 원본 경로를 찾지 못했습니다.';
    wikiState.editorAiStatusError = true;
    wikiApplyEditorState();
    return;
  }
  wikiState.editorAiLoading = true;
  wikiState.editorAiStatus = 'AI가 Markdown 초안을 생성하는 중입니다.';
  wikiState.editorAiStatusError = false;
  wikiApplyEditorState();
  try {
    const response = wikiAiTools?.postJson
      ? await wikiAiTools.postJson(wikiApiUrl('/api/wiki/ai-rewrite/preview'), {
          source_path: sourcePath,
          content,
          instruction: instructionInput?.value || '',
        })
      : await wikiFetchJson(wikiApiUrl('/api/wiki/ai-rewrite/preview'), {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            source_path: sourcePath,
            content,
            instruction: instructionInput?.value || '',
          }),
        });
    if (!wikiState.editorOpen || wikiEditorPreviewSourcePath() !== sourcePath) return;
    const nextContent = String(response?.proposal?.content ?? '');
    wikiSetEditorValue(nextContent);
    wikiState.editorAiStatus = `${response?.title || wikiState.page?.title || '문서'} AI 초안을 편집기에 반영했습니다. 검토 후 저장하세요.`;
    wikiState.editorAiStatusError = false;
    wikiStatus(`${response?.title || wikiState.page?.title || '문서'} AI 초안 반영 완료`);
    wikiFocusEditor();
  } catch (error) {
    wikiState.editorAiStatus = `AI 수정 실패: ${error.message || error}`;
    wikiState.editorAiStatusError = true;
    wikiStatus(`AI 수정 실패: ${error.message || error}`, true);
  } finally {
    wikiState.editorAiLoading = false;
    wikiApplyEditorState();
  }
}

async function wikiSaveEditor() {
  if (!wikiState.editorOpen || wikiState.editorLoading || wikiState.editorSaving || wikiState.editorAiLoading) return;
  const sourcePath = String(wikiState.editorSourcePath || wikiState.page?.source_path || '').trim();
  if (!sourcePath) {
    wikiStatus('문서 저장 실패: 원본 경로를 찾지 못했습니다.', true);
    return;
  }
  wikiState.editorSaving = true;
  wikiApplyEditorState();
  try {
    const response = await wikiFetchJson(wikiApiUrl('/api/wiki/page'), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        source_path: sourcePath,
        content: wikiEditorValue(),
        previous_content: wikiState.editorOriginalContent,
      }),
    });
    wikiResetEditorState();
    if (response?.page) {
      wikiApplyPage(response.page);
    } else {
      wikiApplyEditorState();
    }
    wikiStatus(`${response?.page?.title || '문서'} 저장됨 · ${wikiSyncStatusLabel(response?.updated?.sync_target)}`);
  } catch (error) {
    wikiState.editorSaving = false;
    wikiApplyEditorState();
    wikiStatus(`문서 저장 실패: ${error.message || error}`, true);
  }
}

async function wikiToggleChecklist(checkbox) {
  if (!checkbox || checkbox.dataset.wikiTaskPending === '1') return;
  const sourcePath = String(checkbox.dataset.wikiTaskSource || '').trim();
  const lineNumber = Number.parseInt(checkbox.dataset.wikiTaskLine || '', 10);
  if (!sourcePath || !Number.isInteger(lineNumber) || lineNumber < 1) {
    checkbox.checked = !checkbox.checked;
    wikiStatus('체크 저장 실패: 체크리스트 위치 정보를 찾지 못했습니다.', true);
    return;
  }
  const nextChecked = checkbox.checked;
  checkbox.dataset.wikiTaskPending = '1';
  checkbox.disabled = true;
  try {
    const response = await wikiFetchJson(wikiApiUrl('/api/wiki/checklist'), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        source_path: sourcePath,
        line_number: lineNumber,
        checked: nextChecked,
      }),
    });
    if (response?.page) {
      wikiApplyPage(response.page);
    }
    wikiStatus(`${response?.page?.title || '문서'} 체크 저장됨 · ${wikiSyncStatusLabel(response?.updated?.sync_target)}`);
  } catch (error) {
    checkbox.checked = !nextChecked;
    checkbox.disabled = false;
    delete checkbox.dataset.wikiTaskPending;
    wikiStatus(`체크 저장 실패: ${error.message || error}`, true);
  }
}

async function wikiInit() {
  wikiState.sidebarOpen = readSavedWikiSidebarState();
  applyWikiSidebarState({persist: false});
  applyWikiSearchState({focus: false});
  wikiApplyEditorState();
  try {
    wikiState.index = await wikiFetchJson(wikiApiUrl('/api/wiki/index'));
    wiki$('wikiBookTitle').textContent = wikiState.index.book?.title || 'CS 학습 위키';
    wiki$('wikiBookIntroLink').href = wikiPageUrl(wikiState.index.book?.slug || '_book');
    wikiRenderToc();
    await wikiLoadPage(wikiCurrentSlug() || wikiState.index.default_page_slug || wikiState.index.book?.slug || '_book');
  } catch (error) {
    wikiStatus(`위키 로딩 실패: ${error.message || error}`, true);
    wiki$('wikiArticle').innerHTML = `<p class="error-text">${wikiEscapeHtml(error.message || error)}</p>`;
  }
}

wiki$('wikiSearchInput')?.addEventListener('input', (event) => {
  wikiState.query = event.target.value || '';
  wikiRenderToc();
});

wiki$('wikiSearchInput')?.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    event.preventDefault();
    closeWikiSearch();
    wiki$('wikiSearchToggleBtn')?.focus({preventScroll: true});
    return;
  }
  if (event.key !== 'Enter') return;
  event.preventDefault();
  wikiShowSearchResults();
});

wiki$('wikiSearchToggleBtn')?.addEventListener('click', () => {
  toggleWikiSearch();
});

wiki$('wikiToc')?.addEventListener('click', (event) => {
  const toggle = event.target.closest('[data-wiki-toc-toggle]');
  if (!toggle) return;
  event.preventDefault();
  toggleWikiTocBranch(toggle.dataset.wikiTocToggle || '');
});

wiki$('wikiSidebarToggleBtn')?.addEventListener('click', () => toggleWikiSidebar());
wiki$('wikiEditBtn')?.addEventListener('click', () => {
  wikiStartEdit();
});
wiki$('wikiEditorCancelBtn')?.addEventListener('click', () => {
  wikiCloseEditor();
});
wiki$('wikiEditorSaveBtn')?.addEventListener('click', () => {
  wikiSaveEditor();
});
wiki$('wikiEditorAiBtn')?.addEventListener('click', () => {
  wikiRunAiRewrite();
});
wiki$('wikiEditorAiTemplateToggle')?.addEventListener('click', () => {
  wikiToggleAiTemplateEditor();
});
wiki$('wikiEditorAiTemplateResetBtn')?.addEventListener('click', () => {
  wikiResetAiTemplates();
});

window.addEventListener('popstate', () => {
  if (!wikiState.index) return;
  if (!wikiConfirmEditorNavigation()) {
    window.history.pushState({}, '', wikiPageUrl(wikiState.currentSlug || wikiState.index.default_page_slug || '_book'));
    return;
  }
  wikiLoadPage(wikiCurrentSlug() || wikiState.index.default_page_slug || '_book').then(() => {
    wikiCloseEditor({force: true});
  }).catch((error) => {
    wikiStatus(`문서 이동 실패: ${error.message || error}`, true);
  });
});

window.addEventListener('beforeunload', (event) => {
  if (!wikiEditorHasUnsavedChanges()) return;
  event.preventDefault();
  event.returnValue = '';
});

document.addEventListener('click', (event) => {
  const insideSearch = event.target.closest('#wikiSearch, #wikiSearchToggleBtn');
  if (!insideSearch) closeWikiSearch();
  const templateButton = event.target.closest('#wikiEditorAiTemplates [data-wiki-ai-template-id]');
  if (templateButton) {
    event.preventDefault();
    wikiApplyAiTemplate(templateButton.dataset.wikiAiTemplateId || '');
    return;
  }
  const link = event.target.closest('a[data-wiki-nav="1"], .wiki-article a[href^="/wiki/page/"], #wikiBookIntroLink');
  if (!link) return;
  const href = link.getAttribute('href') || '';
  if (!href.startsWith('/wiki/page/')) return;
  if (!wikiConfirmEditorNavigation()) {
    event.preventDefault();
    return;
  }
  const slug = decodeURIComponent(href.replace('/wiki/page/', '')).replace(/^\/+|\/+$/g, '');
  event.preventDefault();
  wikiLoadPage(slug, {push: true}).then(() => {
    wikiCloseEditor({force: true});
    closeWikiSidebarOnMobile();
    closeWikiSearch();
  }).catch((error) => {
    wikiStatus(`문서 이동 실패: ${error.message || error}`, true);
  });
});

document.addEventListener('change', (event) => {
  const checkbox = event.target.closest('input[data-wiki-task-checkbox="1"]');
  if (!checkbox) return;
  wikiToggleChecklist(checkbox);
});

document.addEventListener('input', (event) => {
  if (event.target.id === 'wikiEditorAiInstruction') {
    if (!wikiState.editorAiSelectedTemplateId) return;
    wikiState.editorAiSelectedTemplateId = '';
    document.querySelectorAll('#wikiEditorAiTemplates .wiki-editor-ai-template-btn').forEach((button) => {
      button.classList.remove('is-active');
    });
    return;
  }
  const templateField = event.target.closest('#wikiEditorAiTemplateList [data-wiki-ai-template-field]');
  if (!templateField) return;
  const templateId = String(templateField.dataset.wikiAiTemplateId || '').trim();
  const fieldName = String(templateField.dataset.wikiAiTemplateField || '').trim();
  if (!templateId || !fieldName) return;
  wikiUpdateAiTemplate(templateId, {[fieldName]: templateField.value});
  if (fieldName !== 'label') return;
  const updated = wikiAiTemplates().find((template) => template.id === templateId);
  document.querySelectorAll('#wikiEditorAiTemplates [data-wiki-ai-template-id]').forEach((button, index) => {
    if ((button.dataset.wikiAiTemplateId || '') !== templateId) return;
    button.textContent = wikiAiTemplateButtonLabel(updated, index);
  });
});
document.addEventListener('keydown', (event) => {
  if (!wikiState.editorOpen) return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    wikiSaveEditor();
  }
});

wikiInit();
