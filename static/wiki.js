const wikiState = {
  index: null,
  currentSlug: '',
  query: '',
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

function wikiCurrentSlug() {
  const prefix = '/wiki/page/';
  if (window.location.pathname.startsWith(prefix)) {
    return decodeURIComponent(window.location.pathname.slice(prefix.length)).replace(/^\/+|\/+$/g, '');
  }
  return '';
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

function wikiRenderTocItems(items) {
  if (!items.length) return '<p class="small muted">일치하는 문서가 없습니다.</p>';
  return `<ul>${items.map((item) => {
    const active = item.slug === wikiState.currentSlug ? ' active' : '';
    const children = item.children?.length ? wikiRenderTocItems(item.children) : '';
    return `<li><a class="wiki-toc-link${active}" href="${wikiPageUrl(item.slug)}" data-wiki-nav="1">${wikiEscapeHtml(item.title)}</a>${children}</li>`;
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
  el.innerHTML = crumbs.map((crumb) => `<a href="${wikiPageUrl(crumb.slug)}" data-wiki-nav="1">${wikiEscapeHtml(crumb.title)}</a>`).join(' <span>/</span> ');
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
  const page = await wikiFetchJson(`/api/wiki/page/${encodeURIComponent(normalized).replace(/%2F/g, '/')}`);
  if (push && window.location.pathname !== wikiPageUrl(page.slug)) {
    window.history.pushState({}, '', wikiPageUrl(page.slug));
  }
  wikiApplyPage(page);
}

async function wikiInit() {
  try {
    wikiState.index = await wikiFetchJson('/api/wiki/index');
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
  event.preventDefault();
  const slug = decodeURIComponent(href.replace('/wiki/page/', '')).replace(/^\/+|\/+$/g, '');
  wikiLoadPage(slug, {push: true}).catch((error) => {
    wikiStatus(`문서 이동 실패: ${error.message || error}`, true);
  });
});

wikiInit();
