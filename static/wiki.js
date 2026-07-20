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
  editorSourcePath: '',
  editorOriginalContent: '',
};

const wiki$ = (id) => document.getElementById(id);

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

function wikiEditorValue() {
  return wiki$('wikiEditorTextarea')?.value || '';
}

function wikiEditorHasUnsavedChanges() {
  return wikiState.editorOpen && wikiEditorValue() !== wikiState.editorOriginalContent;
}

function wikiEditorSyncHint() {
  return 'Markdown 원문을 직접 수정합니다.';
}

function wikiApplyEditorState() {
  const canEdit = wikiEditablePage();
  const open = canEdit && wikiState.editorOpen;
  const editBtn = wiki$('wikiEditBtn');
  const panel = wiki$('wikiEditorPanel');
  const article = wiki$('wikiArticle');
  const pageNav = wiki$('wikiPageNav');
  const textarea = wiki$('wikiEditorTextarea');
  const cancelBtn = wiki$('wikiEditorCancelBtn');
  const saveBtn = wiki$('wikiEditorSaveBtn');
  const source = wiki$('wikiEditorSource');
  const hint = wiki$('wikiEditorHint');

  if (editBtn) {
    editBtn.hidden = !canEdit || open;
    editBtn.disabled = wikiState.editorLoading || wikiState.editorSaving;
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
  if (textarea) {
    textarea.disabled = wikiState.editorLoading || wikiState.editorSaving;
    textarea.placeholder = wikiState.editorLoading ? '문서를 불러오는 중입니다...' : 'Markdown 원문을 입력하세요.';
    if (!open) {
      textarea.value = '';
    }
  }
  if (cancelBtn) {
    cancelBtn.disabled = !open || wikiState.editorSaving;
  }
  if (saveBtn) {
    saveBtn.disabled = !open || wikiState.editorLoading || wikiState.editorSaving;
    saveBtn.textContent = wikiState.editorSaving ? '저장 중...' : '저장';
  }
}

function wikiResetEditorState() {
  wikiState.editorOpen = false;
  wikiState.editorLoading = false;
  wikiState.editorSaving = false;
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
  if (!wikiEditablePage(page) || wikiState.editorLoading || wikiState.editorSaving) return;
  if (wikiState.editorOpen) {
    wiki$('wikiEditorTextarea')?.focus({preventScroll: true});
    return;
  }
  wikiState.editorOpen = true;
  wikiState.editorLoading = true;
  wikiState.editorSourcePath = page?.source_path || '';
  wikiState.editorOriginalContent = '';
  wikiApplyEditorState();
  try {
    const text = await wikiFetchText(wikiApiUrl(page?.raw_url || '#'));
    if (!wikiState.editorOpen || wikiState.editorSourcePath !== (page?.source_path || '')) return;
    wikiState.editorOriginalContent = text;
    const textarea = wiki$('wikiEditorTextarea');
    if (textarea) {
      textarea.value = text;
    }
    wikiStatus(`${page?.title || '문서'} 원본을 불러왔습니다.`);
  } catch (error) {
    wikiStatus(`문서 원본 불러오기 실패: ${error.message || error}`, true);
    wikiCloseEditor({force: true});
    return;
  } finally {
    wikiState.editorLoading = false;
    wikiApplyEditorState();
  }
  wiki$('wikiEditorTextarea')?.focus({preventScroll: true});
}

async function wikiSaveEditor() {
  if (!wikiState.editorOpen || wikiState.editorLoading || wikiState.editorSaving) return;
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

document.addEventListener('keydown', (event) => {
  if (!wikiState.editorOpen) return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    wikiSaveEditor();
  }
});

wikiInit();
