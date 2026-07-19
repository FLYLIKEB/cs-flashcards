const WIKI_SIDEBAR_STATE_KEY = 'csFlashcardsWikiSidebar:v1';

const wikiState = {
  index: null,
  currentSlug: '',
  query: '',
  sidebarOpen: true,
  expandedToc: {},
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
    toggleBtn.textContent = wikiState.sidebarOpen ? '목차 숨기기' : '목차 보기';
    toggleBtn.setAttribute('aria-expanded', String(wikiState.sidebarOpen));
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
    return `<li class="wiki-toc-item${hasChildren ? ' has-children' : ''}${expanded ? ' open' : ''}"><div class="wiki-toc-row">${toggle}<a class="wiki-toc-link${active ? ' active' : ''}" href="${wikiPageUrl(item.slug)}" data-wiki-nav="1" data-wiki-slug="${wikiEscapeHtml(item.slug)}" data-wiki-expanded="${expanded ? '1' : '0'}"${hasChildren ? ' data-wiki-has-children="1"' : ''}${active ? ' aria-current="page"' : ''}>${wikiEscapeHtml(item.title)}</a></div>${children}</li>`;
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

function wikiApplyPage(page) {
  wikiState.currentSlug = page.slug || '';
  wiki$('wikiArticle').innerHTML = page.html || '<p class="muted">문서가 비어 있습니다.</p>';
  wiki$('wikiRawLink').href = page.raw_url || '#';
  document.title = `${page.title || '문서'} · ${wikiState.index?.book?.title || 'CS 학습 위키'}`;
  wikiRenderBreadcrumbs(page);
  wikiRenderToc();
  wikiStatus(`${page.title || '문서'} 열람 중`);
}

async function wikiFetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(await res.text() || `${res.status}`);
  }
  return res.json();
}

async function wikiLoadPage(slug, {push = false} = {}) {
  const normalized = String(slug || wikiState.index?.default_page_slug || '').trim() || '_book';
  const page = await wikiFetchJson(wikiApiUrl(`/api/wiki/page/${encodeURIComponent(normalized).replace(/%2F/g, '/')}`));
  if (push && window.location.pathname !== wikiPageUrl(page.slug)) {
    window.history.pushState({}, '', wikiPageUrl(page.slug));
  }
  wikiApplyPage(page);
}

async function wikiInit() {
  wikiState.sidebarOpen = readSavedWikiSidebarState();
  applyWikiSidebarState({persist: false});
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

wiki$('wikiToc')?.addEventListener('click', (event) => {
  const toggle = event.target.closest('[data-wiki-toc-toggle]');
  if (!toggle) return;
  event.preventDefault();
  toggleWikiTocBranch(toggle.dataset.wikiTocToggle || '');
});

wiki$('wikiSidebarToggleBtn')?.addEventListener('click', () => toggleWikiSidebar());

window.addEventListener('popstate', () => {
  if (!wikiState.index) return;
  wikiLoadPage(wikiCurrentSlug() || wikiState.index.default_page_slug || '_book').catch((error) => {
    wikiStatus(`문서 이동 실패: ${error.message || error}`, true);
  });
});

document.addEventListener('click', (event) => {
  const link = event.target.closest('a[data-wiki-nav="1"], .wiki-article a[href^="/wiki/page/"], #wikiBookIntroLink');
  if (!link) return;
  const href = link.getAttribute('href') || '';
  if (!href.startsWith('/wiki/page/')) return;
  const slug = decodeURIComponent(href.replace('/wiki/page/', '')).replace(/^\/+|\/+$/g, '');
  if (link.dataset.wikiHasChildren === '1' && link.dataset.wikiExpanded !== '1' && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
    event.preventDefault();
    toggleWikiTocBranch(link.dataset.wikiSlug || slug);
    return;
  }
  event.preventDefault();
  wikiLoadPage(slug, {push: true}).then(() => {
    closeWikiSidebarOnMobile();
  }).catch((error) => {
    wikiStatus(`문서 이동 실패: ${error.message || error}`, true);
  });
});

wikiInit();
