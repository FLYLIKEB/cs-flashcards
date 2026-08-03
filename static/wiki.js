const WIKI_SIDEBAR_STATE_KEY = 'csFlashcardsWikiSidebar:v1';
const WIKI_BATCH_AI_MODE_KEY = 'csFlashcardsWikiBatchAiMode:v1';

const wikiState = {
  index: null,
  page: null,
  currentSlug: '',
  query: '',
  sidebarOpen: true,
  batchAiMode: false,
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
  archiveSaving: false,
  imageAiLoadingIndex: -1,
  imageFormatSelections: {},
  imagePromptEditorIndex: -1,
  imagePromptStatus: '',
  imagePromptStatusError: false,
  sectionAiLoadingIndex: -1,
  sectionFormatSelections: {},
  sectionPromptEditorIndex: -1,
  sectionPromptStatus: '',
  sectionPromptStatusError: false,
  tocAiSelections: {},
  pendingAiJobs: {},
  aiJobPollTimer: 0,
  aiNotificationsRequested: false,
};

const wiki$ = (id) => document.getElementById(id);
const wikiAiTools = window.CsAiTools || null;
let wikiMarkdownEditor = null;
let wikiMarkdownPreviewSideBySide = false;
let wikiPreviewRequestToken = 0;
let wikiSidebarReturnFocusEl = null;

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
const WIKI_IMAGE_PROMPT_STORAGE_KEY = 'csFlashcardsWikiImagePromptTemplates:v1';
const WIKI_IMAGE_PROMPT_TEMPLATES = Object.freeze([
  {
    id: 'png',
    label: 'PNG',
    instruction: `Create a clean, minimal educational concept illustration for a Korean CS wiki page.
No text, no letters, no labels, no UI, no watermark, no logo, no border, no collage.
Use a simple single-scene composition with soft modern colors and high clarity.
Primary subject: {{focus_subject}}.
Page title: {{page_title}}.
Section: {{section_title}}.
Image alt: {{alt}}.
Caption: {{caption}}.
Source note: {{source_note}}.
Local content context: {{context_excerpt}}.
Visualize the real mechanism or mental model described by the local content context so a learner can understand it at a glance.
Prefer a neutral academic diagram-like illustration, but rendered as a polished image rather than literal text diagram.`,
  },
  {
    id: 'svg',
    label: 'SVG',
    instruction: `Design a standalone SVG illustration for a Korean CS wiki page.
Use only safe SVG shapes and attributes, and do not include script, foreignObject, iframe, external href, fonts, or any text.
Keep it minimal, academic, and visually clear.
Primary subject: {{focus_subject}}.
Page title: {{page_title}}.
Section: {{section_title}}.
Image alt: {{alt}}.
Caption: {{caption}}.
Source note: {{source_note}}.
Local content context: {{context_excerpt}}.
Reflect the real mechanism or structure described by the local content context rather than a generic tech illustration.`,
  },
  {
    id: 'gif',
    label: 'GIF',
    instruction: `{{focus_subject}}을 설명하는 학습용 GIF를 만들어줘.

요구사항:
- 설명문보다 움직임만 보고 작동 원리가 직관적으로 이해되게 만들어.
- 텍스트/자막은 최소화.
- 한 번 보면 “아, 이렇게 동작하는구나”가 바로 와야 해.
- 정적인 인포그래픽 말고 실제 looping GIF로 만들어.
- 핵심 상태 변화가 분명히 보여야 해. (예: push/pop, enqueue/dequeue, 탐색 순서, split, swap, relax 등)
- 모바일/위키 본문 폭에서도 식별 가능하게 만들어.
- active 요소는 색상/강조로 분명히 보여줘.
- 아래 문맥에 없는 임의의 메커니즘은 만들지 말고, 실제 설명된 단계/상태 변화만 시각화해.

문맥:
- 문서 제목: {{page_title}}
- 섹션: {{section_title}}
- 그림 대체텍스트: {{alt}}
- 그림 설명: {{caption}}
- 인접 본문 요약: {{context_excerpt}}
- 출처 메모: {{source_note}}

의도:
- 시험/면접용 학습 자료라서 긴 설명보다 동작 구조를 한눈에 이해시키는 게 목적이야.
- “설명”이 아니라 “상태 변화 시각화”에 집중해.`,
  },
]);
const wikiImagePromptTemplateManager = wikiAiTools?.createPromptTemplateManager
  ? wikiAiTools.createPromptTemplateManager({
      storageKey: WIKI_IMAGE_PROMPT_STORAGE_KEY,
      defaults: WIKI_IMAGE_PROMPT_TEMPLATES,
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

function wikiIsMobileViewport() {
  return window.matchMedia('(max-width: 720px)').matches;
}

function wikiSidebarToggleButtons() {
  return [wiki$('wikiSidebarToggleBtn'), wiki$('wikiSidebarTopbarBtn')].filter(Boolean);
}

function readSavedWikiSidebarState() {
  try {
    const saved = window.localStorage.getItem(WIKI_SIDEBAR_STATE_KEY);
    if (saved === 'open') return true;
    if (saved === 'closed') return false;
  } catch (_error) {
    // Ignore storage failures and fall back to the viewport default.
  }
  return wikiDefaultSidebarOpen();
}

function saveWikiSidebarState() {
  try {
    window.localStorage.setItem(WIKI_SIDEBAR_STATE_KEY, wikiState.sidebarOpen ? 'open' : 'closed');
  } catch (_error) {
    // Ignore storage failures.
  }
}

function readSavedWikiBatchAiMode() {
  try {
    return window.localStorage.getItem(WIKI_BATCH_AI_MODE_KEY) === 'open';
  } catch (_error) {
    return false;
  }
}

function saveWikiBatchAiMode() {
  try {
    window.localStorage.setItem(WIKI_BATCH_AI_MODE_KEY, wikiState.batchAiMode ? 'open' : 'closed');
  } catch (_error) {
    // Ignore storage failures.
  }
}

function wikiRememberSidebarFocusTarget(element) {
  if (!element || typeof element.focus !== 'function') return;
  wikiSidebarReturnFocusEl = element;
}

function wikiRestoreSidebarFocus() {
  const fallback = wiki$('wikiSidebarTopbarBtn') || wiki$('wikiSidebarToggleBtn');
  const target = wikiSidebarReturnFocusEl || fallback;
  wikiSidebarReturnFocusEl = null;
  target?.focus?.({preventScroll: true});
}

function wikiFocusMobileSidebarCloseButton() {
  if (!wikiIsMobileViewport() || !wikiState.sidebarOpen) return;
  const closeButton = wiki$('wikiSidebarCloseBtn');
  if (!closeButton) return;
  const focus = () => {
    if (!wikiIsMobileViewport() || !wikiState.sidebarOpen) return;
    closeButton.focus({preventScroll: true});
  };
  window.requestAnimationFrame(() => {
    focus();
    window.setTimeout(focus, 0);
  });
}

function wikiApplyMobileSidebarState() {
  const mobileOpen = wikiIsMobileViewport() && wikiState.sidebarOpen;
  document.body.classList.toggle('wiki-mobile-sidebar-open', mobileOpen);
  const backdrop = wiki$('wikiSidebarBackdrop');
  if (backdrop) {
    backdrop.hidden = !mobileOpen;
    backdrop.setAttribute('aria-hidden', String(!mobileOpen));
  }
}

function applyWikiBatchAiMode({persist = true} = {}) {
  document.body.classList.toggle('wiki-batch-ai-mode', wikiState.batchAiMode);
  const panel = wiki$('wikiBatchAiPanel');
  if (panel) {
    panel.hidden = !wikiState.batchAiMode;
    panel.setAttribute('aria-hidden', String(!wikiState.batchAiMode));
  }
  const toggleBtn = wiki$('wikiBatchAiToggleBtn');
  if (toggleBtn) {
    toggleBtn.textContent = wikiState.batchAiMode ? '목차' : 'AI';
    toggleBtn.setAttribute('aria-expanded', String(wikiState.batchAiMode));
    toggleBtn.setAttribute('aria-label', wikiState.batchAiMode ? 'AI 선택 닫기' : 'AI 선택 열기');
    toggleBtn.setAttribute('title', wikiState.batchAiMode ? '일반 목차로 돌아가기' : 'AI 선택 열기');
    toggleBtn.setAttribute('aria-pressed', String(wikiState.batchAiMode));
  }
  if (persist) saveWikiBatchAiMode();
  wikiRenderToc();
}

function applyWikiSidebarState({persist = true} = {}) {
  document.body.classList.toggle('wiki-sidebar-collapsed', !wikiState.sidebarOpen);
  wiki$('wikiSidebar')?.setAttribute('aria-hidden', String(!wikiState.sidebarOpen));
  wikiSidebarToggleButtons().forEach((toggleBtn) => {
    toggleBtn.textContent = '목차';
    toggleBtn.setAttribute('aria-expanded', String(wikiState.sidebarOpen));
    toggleBtn.setAttribute('aria-label', wikiState.sidebarOpen ? '목차 숨기기' : '목차 보기');
    toggleBtn.setAttribute('title', wikiState.sidebarOpen ? '목차 숨기기' : '목차 보기');
  });
  wikiApplyMobileSidebarState();
  if (persist) saveWikiSidebarState();
}

function toggleWikiSidebar(force = !wikiState.sidebarOpen) {
  const nextOpen = Boolean(force);
  if (nextOpen && wikiIsMobileViewport()) closeWikiSearch();
  wikiState.sidebarOpen = nextOpen;
  applyWikiSidebarState();
  if (nextOpen && wikiIsMobileViewport()) {
    wikiFocusMobileSidebarCloseButton();
  }
}

function toggleWikiBatchAiMode(force = !wikiState.batchAiMode) {
  wikiState.batchAiMode = Boolean(force);
  applyWikiBatchAiMode();
}

function closeWikiSidebar({restoreFocus = false} = {}) {
  if (!wikiState.sidebarOpen) return;
  toggleWikiSidebar(false);
  if (restoreFocus) wikiRestoreSidebarFocus();
}

function closeWikiSidebarOnMobile({restoreFocus = false} = {}) {
  if (!wikiIsMobileViewport()) return;
  closeWikiSidebar({restoreFocus});
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
  const nextOpen = Boolean(force);
  if (nextOpen && wikiIsMobileViewport() && wikiState.sidebarOpen) {
    closeWikiSidebarOnMobile();
  }
  wikiState.searchOpen = nextOpen;
  applyWikiSearchState({focus: wikiState.searchOpen && focus});
}

function closeWikiSearch({restoreFocus = false} = {}) {
  if (!wikiState.searchOpen) return;
  toggleWikiSearch(false, {focus: false});
  if (restoreFocus) wiki$('wikiSearchToggleBtn')?.focus({preventScroll: true});
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

function wikiRequestAiNotificationPermission() {
  if (wikiState.aiNotificationsRequested || !('Notification' in window) || window.Notification.permission !== 'default') return;
  wikiState.aiNotificationsRequested = true;
  window.Notification.requestPermission().catch(() => {});
}

function wikiNotifyAiJob(title, body) {
  if (document.visibilityState !== 'hidden' || !('Notification' in window) || window.Notification.permission !== 'granted') return;
  try {
    new window.Notification(title, {body, tag: 'cs-wiki-ai-update'});
  } catch (_error) {}
}

function wikiSelectedBatchSourcePaths() {
  return Object.entries(wikiState.tocAiSelections)
    .filter(([, checked]) => Boolean(checked))
    .map(([sourcePath]) => sourcePath);
}

function wikiBatchPageMetaBySourcePath(sourcePath) {
  const normalized = String(sourcePath || '').trim();
  if (!normalized) return null;
  const items = Array.isArray(wikiState.index?.flat) ? wikiState.index.flat : [];
  return items.find((item) => String(item?.source_path || '').trim() === normalized) || null;
}

async function wikiLoadBatchPageBySourcePath(sourcePath) {
  const normalized = String(sourcePath || '').trim();
  if (!normalized) throw new Error('문서 경로를 찾지 못했습니다.');
  if (normalized === String(wikiState.page?.source_path || '').trim() && wikiState.page) return wikiState.page;
  const pageMeta = wikiBatchPageMetaBySourcePath(normalized);
  const slug = String(pageMeta?.slug || '').trim();
  if (!slug) throw new Error(`문서를 찾지 못했습니다: ${normalized}`);
  return wikiFetchJson(wikiApiUrl(`/api/wiki/page/${encodeURIComponent(slug).replace(/%2F/g, '/')}`));
}

function wikiBatchSectionTargets(page = wikiState.page) {
  const sections = Array.isArray(page?.sections) ? page.sections : [];
  const subheadings = sections.filter((section) => Number(section?.level || 0) >= 2);
  return subheadings.length ? subheadings : sections.filter((section) => Number(section?.level || 0) >= 1);
}

function wikiIsGeneratedSectionImage(image = {}) {
  const href = String(image?.source_href || image?.src || '').trim().toLowerCase();
  return /-section-\d+\.(png|svg|gif)(?:$|[?#])/.test(href);
}

function wikiBatchImageTargets(page = wikiState.page) {
  const images = Array.isArray(page?.images) ? page.images : [];
  return images.filter((image) => !wikiIsGeneratedSectionImage(image));
}

function wikiPageAiJobSpecs(page = wikiState.page, format = 'png', {includeExistingImages = true, includeSections = true} = {}) {
  const normalizedFormat = String(format || 'png').trim().toLowerCase() || 'png';
  const specs = [];
  if (includeSections) {
    for (const section of wikiBatchSectionTargets(page)) {
      const sectionIndex = Number(section?.index);
      if (!Number.isInteger(sectionIndex) || sectionIndex < 0) continue;
      specs.push({
        payload: {
          source_paths: [page.source_path],
          format: normalizedFormat,
          prompt_template: wikiImagePromptFor(page, section, normalizedFormat),
          include_existing_images: false,
          include_sections: true,
          target: 'single_section',
          section_index: sectionIndex,
        },
        label: `${section?.title || page?.title || '섹션'} ${normalizedFormat.toUpperCase()} AI`,
      });
    }
  }
  if (includeExistingImages) {
    for (const image of wikiBatchImageTargets(page)) {
      const imageIndex = Number(image?.index);
      if (!Number.isInteger(imageIndex) || imageIndex < 0) continue;
      specs.push({
        payload: {
          source_paths: [page.source_path],
          format: normalizedFormat,
          prompt_template: wikiImagePromptFor(page, image, normalizedFormat),
          include_existing_images: true,
          include_sections: false,
          target: 'single_image',
          image_index: imageIndex,
        },
        label: `${image?.alt || page?.title || '이미지'} ${normalizedFormat.toUpperCase()} AI`,
      });
    }
  }
  return specs;
}

function wikiUpdateBatchAiHint() {
  const el = wiki$('wikiBatchAiHint');
  if (!el) return;
  const count = wikiSelectedBatchSourcePaths().length;
  el.textContent = count ? `선택 문서 ${count}개` : '선택 문서 0개';
}

async function wikiPollAiJobs() {
  const entries = Object.entries(wikiState.pendingAiJobs);
  if (!entries.length) {
    wikiState.aiJobPollTimer = 0;
    return;
  }
  for (const [jobId, meta] of entries) {
    try {
      const job = await wikiFetchJson(wikiApiUrl(`/api/wiki/ai-jobs/${encodeURIComponent(jobId)}`));
      if (job.status === 'completed' || job.status === 'failed') {
        delete wikiState.pendingAiJobs[jobId];
        const label = meta?.label || job.message || '위키 AI 작업';
        const message = job.status === 'completed'
          ? `${label} 완료`
          : `${label} 실패: ${job.error || job.message || '오류'}`;
        wikiStatus(message, job.status === 'failed');
        wikiNotifyAiJob(job.status === 'completed' ? `위키 AI 완료 · ${label}` : `위키 AI 실패 · ${label}`, job.message || job.error || label);
        if (job.status === 'completed' && Array.isArray(job.source_paths) && job.source_paths.includes(wikiState.page?.source_path) && !wikiState.editorOpen) {
          try {
            await wikiLoadPage(wikiState.currentSlug || job.source_paths[0], {push: false});
          } catch (_reloadError) {}
        }
      } else {
        wikiState.pendingAiJobs[jobId] = {...meta, status: job.status};
      }
    } catch (_error) {}
  }
  wikiState.aiJobPollTimer = window.setTimeout(() => {
    wikiPollAiJobs();
  }, 4000);
}

function wikiTrackAiJob(job, label) {
  const jobId = String(job?.job_id || '').trim();
  if (!jobId) return;
  wikiState.pendingAiJobs[jobId] = {label: String(label || jobId), status: String(job?.status || 'queued')};
  if (!wikiState.aiJobPollTimer) {
    wikiState.aiJobPollTimer = window.setTimeout(() => {
      wikiPollAiJobs();
    }, 4000);
  }
}

async function wikiQueueAiJob(payload, label, {showStatus = true} = {}) {
  wikiRequestAiNotificationPermission();
  const job = wikiAiTools?.postJson
    ? await wikiAiTools.postJson(wikiApiUrl('/api/wiki/ai-jobs'), payload)
    : await wikiFetchJson(wikiApiUrl('/api/wiki/ai-jobs'), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
  wikiTrackAiJob(job, label);
  if (showStatus) wikiStatus(`${label} 요청됨. 백그라운드에서 처리합니다.`);
  return job;
}

async function wikiQueueAiJobs(jobSpecs, label) {
  const specs = Array.isArray(jobSpecs) ? jobSpecs.filter(Boolean) : [];
  if (!specs.length) {
    wikiStatus(`${label} 요청할 이미지가 없습니다.`, true);
    return [];
  }
  const jobs = [];
  const failures = [];
  for (const spec of specs) {
    try {
      jobs.push(await wikiQueueAiJob(spec.payload, spec.label, {showStatus: false}));
    } catch (error) {
      failures.push(`${spec.label}: ${error.message || error}`);
    }
  }
  if (jobs.length && !failures.length) {
    wikiStatus(`${label} ${jobs.length}건 요청됨. 백그라운드에서 처리합니다.`);
  } else if (jobs.length) {
    wikiStatus(`${label} ${jobs.length}건 요청됨, ${failures.length}건 실패: ${failures[0]}`, true);
  } else {
    wikiStatus(`${label} 요청 실패: ${failures[0] || '요청할 항목이 없습니다.'}`, true);
  }
  return jobs;
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
    const checked = Boolean(wikiState.tocAiSelections[item.source_path]);
    const checkbox = wikiState.batchAiMode
      ? `<input class="wiki-toc-ai-checkbox" type="checkbox" data-wiki-ai-source="${wikiEscapeHtml(item.source_path)}" aria-label="${wikiEscapeHtml(item.title)} 선택"${checked ? ' checked' : ''} />`
      : '';
    return `<li class="wiki-toc-item${hasChildren ? ' has-children' : ''}${expanded ? ' open' : ''}"><div class="wiki-toc-row">${checkbox}${toggle}<a class="wiki-toc-link${active ? ' active' : ''}" href="${wikiPageUrl(item.slug)}" data-wiki-nav="1"${active ? ' aria-current="page"' : ''}>${wikiEscapeHtml(item.title)}</a></div>${children}</li>`;
  }).join('')}</ul>`;
}

function wikiRenderToc() {
  const toc = wiki$('wikiToc');
  if (!toc || !wikiState.index) return;
  const filtered = wikiFilteredTree(wikiState.index.tree || [], wikiState.query);
  toc.innerHTML = wikiRenderTocItems(filtered);
  wikiUpdateBatchAiHint();
}

function wikiRenderBreadcrumbs(page) {
  const el = wiki$('wikiBreadcrumbs');
  if (!el) return;
  const crumbs = Array.isArray(page?.breadcrumbs) ? page.breadcrumbs : [];
  el.innerHTML = crumbs.map((crumb) => `<a href="${wikiPageUrl(crumb.slug)}" data-wiki-nav="1">${wikiEscapeHtml(crumb.title)}</a>`).join(' <span>›</span> ');
}

function wikiRenderLastModified(page) {
  const el = wiki$('wikiUpdatedAt');
  if (!el) return;
  const label = String(page?.last_modified_label || '').trim();
  const iso = String(page?.last_modified_at || '').trim();
  el.hidden = !label;
  el.innerHTML = label ? `최종 수정 <time datetime="${wikiEscapeHtml(iso)}">${wikiEscapeHtml(label)}</time>` : '';
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

function wikiArchiveInfo(page = wikiState.page) {
  return page?.archive || wikiState.index?.archive || null;
}

function wikiArchiveEnabled(page = wikiState.page) {
  return Boolean(wikiArchiveInfo(page)?.enabled);
}

function wikiApplyArchiveButtonState() {
  const button = wiki$('wikiGithubArchiveBtn');
  if (!button) return;
  const archive = wikiArchiveInfo();
  const canArchive = wikiEditablePage() && wikiArchiveEnabled();
  const editorBusy = wikiState.editorOpen || wikiState.editorLoading || wikiState.editorSaving || wikiState.editorAiLoading;
  button.hidden = !canArchive;
  button.disabled = !canArchive || editorBusy || wikiState.archiveSaving;
  button.textContent = wikiState.archiveSaving ? '보관 중...' : 'GitHub 보관';
  const repo = String(archive?.repo || '').trim();
  const branch = String(archive?.branch || '').trim() || 'main';
  button.title = repo ? `현재 서버 위키를 ${repo}@${branch} 에 보관` : '현재 서버 위키를 GitHub에 보관';
}

async function wikiArchiveToGithub() {
  if (wikiState.archiveSaving) return;
  if (!wikiArchiveEnabled()) {
    wikiStatus('GitHub 보관 구성이 없습니다.', true);
    return;
  }
  wikiState.archiveSaving = true;
  wikiApplyArchiveButtonState();
  try {
    const response = await wikiFetchJson(wikiApiUrl('/api/wiki/archive/github'), {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        source_path: wikiState.page?.source_path || '',
      }),
    });
    const archive = response?.archive || {};
    const details = [];
    const commit = String(archive?.commit_sha || '').trim();
    if (commit) details.push(`commit ${commit.slice(0, 7)}`);
    if (Number(archive?.changed_file_count || 0) > 0) details.push(`변경 ${Number(archive.changed_file_count)}개`);
    if (Number(archive?.deleted_file_count || 0) > 0) details.push(`삭제 ${Number(archive.deleted_file_count)}개`);
    const summary = archive?.committed ? (details.join(' · ') || '보관 완료') : '변경 없음';
    wikiStatus(`GitHub 보관 완료 · ${summary}`);
  } catch (error) {
    wikiStatus(`GitHub 보관 실패: ${error.message || error}`, true);
  } finally {
    wikiState.archiveSaving = false;
    wikiApplyArchiveButtonState();
  }
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

const WIKI_TRUSTED_RENDERED_HTML_KIND = 'wiki-rendered';

function wikiTrustedRenderedHtml(html) {
  return Object.freeze({
    __csTrustedHtml: true,
    kind: WIKI_TRUSTED_RENDERED_HTML_KIND,
    html: String(html || ''),
  });
}

function isWikiTrustedRenderedHtml(value) {
  return Boolean(value?.__csTrustedHtml) && value.kind === WIKI_TRUSTED_RENDERED_HTML_KIND && typeof value.html === 'string';
}

function wikiRenderMessage(element, text, className = '') {
  if (!element) return;
  const message = document.createElement('p');
  if (className) message.className = className;
  message.textContent = String(text || '');
  element.replaceChildren(message);
}

function wikiApplyTrustedHtml(element, trustedHtml, {emptyText = '', emptyClassName = 'muted'} = {}) {
  if (!element) return;
  if (!isWikiTrustedRenderedHtml(trustedHtml)) throw new Error('Trusted wiki HTML required.');
  if (!trustedHtml.html) {
    if (emptyText) wikiRenderMessage(element, emptyText, emptyClassName);
    else element.replaceChildren();
    return;
  }
  element.innerHTML = trustedHtml.html;
}

function wikiEditorPreviewPlaceholder(text = '미리보기를 불러오는 중입니다.') {
  return String(text || '');
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
      const loadingText = wikiEditorPreviewPlaceholder();
      if (!preview) return loadingText;
      wikiRenderMessage(preview, loadingText, 'wiki-editor-preview-loading');
      if (!sourcePath) {
        wikiRenderMessage(preview, '미리보기에 필요한 원본 경로를 찾지 못했습니다.', 'error-text');
        return loadingText;
      }
      wikiRenderPreviewMarkdown(sourcePath, plainText).then((data) => {
        if (token !== wikiPreviewRequestToken || !preview.isConnected) return;
        wikiApplyTrustedHtml(preview, wikiTrustedRenderedHtml(data?.html || ''), {emptyText: '미리보기 결과가 비어 있습니다.'});
      }).catch((error) => {
        if (token !== wikiPreviewRequestToken || !preview.isConnected) return;
        wikiRenderMessage(preview, error.message || error, 'error-text');
      });
      return loadingText;
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
  wikiApplyArchiveButtonState();
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
  return syncTarget === 'local' ? '로컬 저장 완료' : '저장 완료';
}

function wikiDefaultImagePromptTemplates() {
  return WIKI_IMAGE_PROMPT_TEMPLATES.map((template) => ({...template}));
}

function wikiImagePromptTemplates() {
  return wikiImagePromptTemplateManager?.getTemplates?.() || wikiDefaultImagePromptTemplates();
}

function wikiImagePromptTemplate(format = 'png') {
  const normalized = String(format || 'png').trim().toLowerCase() || 'png';
  return wikiImagePromptTemplates().find((template) => template.id === normalized)
    || wikiDefaultImagePromptTemplates().find((template) => template.id === normalized)
    || wikiDefaultImagePromptTemplates()[0];
}

function wikiUpdateImagePromptTemplate(format, instruction) {
  const normalized = String(format || 'png').trim().toLowerCase() || 'png';
  if (!wikiImagePromptTemplateManager?.updateTemplate) return wikiImagePromptTemplates();
  return wikiImagePromptTemplateManager.updateTemplate(normalized, {instruction: String(instruction || '')});
}

function wikiResetImagePromptTemplate(format) {
  const normalized = String(format || 'png').trim().toLowerCase() || 'png';
  const fallback = WIKI_IMAGE_PROMPT_TEMPLATES.find((template) => template.id === normalized);
  if (!fallback) return wikiImagePromptTemplates();
  if (!wikiImagePromptTemplateManager?.updateTemplate) return wikiDefaultImagePromptTemplates();
  return wikiImagePromptTemplateManager.updateTemplate(normalized, {instruction: fallback.instruction});
}

function wikiImageSelectionKey(page = wikiState.page, imageIndex = -1) {
  return `${page?.source_path || wikiState.currentSlug || 'page'}::image::${imageIndex}`;
}

function wikiSectionSelectionKey(page = wikiState.page, sectionIndex = -1) {
  return `${page?.source_path || wikiState.currentSlug || 'page'}::section::${sectionIndex}`;
}

function wikiSelectedImageFormat(imageIndex, item = null, page = wikiState.page) {
  const saved = wikiState.imageFormatSelections[wikiImageSelectionKey(page, imageIndex)];
  const fallback = String(item?.format || 'png').trim().toLowerCase() || 'png';
  return ['png', 'svg', 'gif'].includes(saved) ? saved : fallback;
}

function wikiSetSelectedImageFormat(imageIndex, format, page = wikiState.page) {
  const normalized = String(format || 'png').trim().toLowerCase() || 'png';
  wikiState.imageFormatSelections = {
    ...wikiState.imageFormatSelections,
    [wikiImageSelectionKey(page, imageIndex)]: normalized,
  };
}

function wikiSelectedSectionFormat(sectionIndex, section = null, page = wikiState.page) {
  const saved = wikiState.sectionFormatSelections[wikiSectionSelectionKey(page, sectionIndex)];
  const fallback = String(section?.format || 'png').trim().toLowerCase() || 'png';
  return ['png', 'svg', 'gif'].includes(saved) ? saved : fallback;
}

function wikiSetSelectedSectionFormat(sectionIndex, format, page = wikiState.page) {
  const normalized = String(format || 'png').trim().toLowerCase() || 'png';
  wikiState.sectionFormatSelections = {
    ...wikiState.sectionFormatSelections,
    [wikiSectionSelectionKey(page, sectionIndex)]: normalized,
  };
}

function wikiImagePromptContext(page = wikiState.page, image = {}) {
  const pageTitle = String(page?.title || '').trim() || '문서';
  const sectionTitle = String(image?.section_title || pageTitle).trim() || pageTitle;
  const alt = String(image?.alt || '').trim() || pageTitle;
  const caption = String(image?.caption || '').trim();
  const sourceNote = String(image?.source_note || '').trim();
  const contextExcerpt = String(image?.context_excerpt || '').trim();
  const focusSubject = String(caption || alt || sectionTitle || pageTitle).trim() || pageTitle;
  return {
    page_title: pageTitle,
    section_title: sectionTitle,
    alt,
    caption,
    source_note: sourceNote,
    context_excerpt: contextExcerpt,
    focus_subject: focusSubject,
  };
}

function wikiRenderImagePromptTemplate(templateText, page = wikiState.page, image = {}) {
  const context = wikiImagePromptContext(page, image);
  return String(templateText || '').replace(/\{\{\s*([a-z_]+)\s*\}\}/gi, (_match, key) => String(context[key] || '').trim());
}

function wikiImagePromptFor(page = wikiState.page, image = {}, format = 'png') {
  return wikiRenderImagePromptTemplate(wikiImagePromptTemplate(format)?.instruction || '', page, image).trim();
}

function wikiToggleImagePromptEditor(imageIndex) {
  wikiState.imagePromptEditorIndex = wikiState.imagePromptEditorIndex === imageIndex ? -1 : imageIndex;
  wikiState.imagePromptStatus = '';
  wikiState.imagePromptStatusError = false;
  wikiEnhanceInlineImages(wikiState.page);
}

function wikiToggleSectionPromptEditor(sectionIndex) {
  wikiState.sectionPromptEditorIndex = wikiState.sectionPromptEditorIndex === sectionIndex ? -1 : sectionIndex;
  wikiState.sectionPromptStatus = '';
  wikiState.sectionPromptStatusError = false;
  wikiEnhanceSectionHeadings(wikiState.page);
}

function wikiEnhanceInlineImages(page = wikiState.page) {
  const article = wiki$('wikiArticle');
  if (!article) return;
  const items = Array.isArray(page?.images) ? page.images : [];
  article.querySelectorAll('img.wiki-inline-image').forEach((image, index) => {
    const item = items[index] || {index, format: 'png', alt: image.getAttribute('alt') || ''};
    let shell = image.parentElement?.classList?.contains('wiki-inline-image-shell') ? image.parentElement : null;
    if (!shell) {
      shell = document.createElement('span');
      shell.className = 'wiki-inline-image-shell';
      image.parentNode?.insertBefore(shell, image);
      shell.appendChild(image);
    }
    shell.querySelector('.wiki-inline-image-ai')?.remove();
    const controls = document.createElement('span');
    controls.className = 'wiki-inline-image-ai';
    const select = document.createElement('select');
    select.className = 'wiki-inline-image-format';
    select.dataset.wikiImageIndex = String(index);
    select.setAttribute('aria-label', `${item?.alt || image.getAttribute('alt') || '위키 이미지'} 파일 포맷`);
    ['png', 'svg', 'gif'].forEach((format) => {
      const option = document.createElement('option');
      option.value = format;
      option.textContent = format;
      select.appendChild(option);
    });
    const currentFormat = wikiSelectedImageFormat(index, item, page);
    select.value = currentFormat;
    const activeBusy = false;
    select.disabled = false;
    select.addEventListener('change', () => {
      wikiSetSelectedImageFormat(index, select.value, page);
      if (wikiState.imagePromptEditorIndex === index) wikiEnhanceInlineImages(page);
    });
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'inline-ai-btn has-tip wiki-inline-image-ai-btn';
    button.dataset.wikiImageIndex = String(index);
    button.dataset.tip = '이미지 AI';
    button.textContent = 'AI';
    button.title = 'AI 이미지 재생성';
    if (wikiAiTools?.setButtonBusy) {
      wikiAiTools.setButtonBusy(button, {
        active: activeBusy,
        idleLabel: 'AI',
        busyLabel: '…',
        idleTitle: 'AI 이미지 재생성',
        busyTitle: 'AI 이미지 생성 중',
      });
    } else {
      button.disabled = activeBusy;
      if (button.disabled) button.textContent = '…';
    }
    button.addEventListener('click', () => {
      wikiRegenerateInlineImage(index);
    });
    const editButton = document.createElement('button');
    editButton.type = 'button';
    editButton.className = 'inline-ai-btn has-tip wiki-inline-image-edit-btn';
    editButton.dataset.tip = '프롬프트 수정';
    editButton.textContent = '✎';
    editButton.title = `${select.value.toUpperCase()} 프롬프트 수정`;
    editButton.disabled = activeBusy;
    editButton.addEventListener('click', () => {
      wikiToggleImagePromptEditor(index);
    });
    controls.append(select, button, editButton);
    shell.appendChild(controls);
    if (wikiState.imagePromptEditorIndex === index) {
      const editor = document.createElement('div');
      editor.className = 'wiki-inline-image-prompt-editor';
      const promptFormat = wikiSelectedImageFormat(index, item, page);
      const template = wikiImagePromptTemplate(promptFormat);
      const label = document.createElement('label');
      label.className = 'wiki-inline-image-prompt-label';
      label.textContent = `${promptFormat.toUpperCase()} 프롬프트`;
      const textarea = document.createElement('textarea');
      textarea.className = 'wiki-inline-image-prompt-textarea';
      textarea.rows = 10;
      textarea.value = String(template?.instruction || '');
      const hint = document.createElement('p');
      hint.className = 'wiki-inline-image-prompt-hint';
      hint.textContent = '사용 가능 변수: {{focus_subject}}, {{page_title}}, {{section_title}}, {{alt}}, {{caption}}, {{context_excerpt}}, {{source_note}}';
      const actions = document.createElement('div');
      actions.className = 'wiki-inline-image-prompt-actions';
      const saveBtn = document.createElement('button');
      saveBtn.type = 'button';
      saveBtn.className = 'header-link';
      saveBtn.textContent = '저장';
      saveBtn.addEventListener('click', () => {
        wikiUpdateImagePromptTemplate(promptFormat, textarea.value);
        wikiState.imagePromptStatus = `${promptFormat.toUpperCase()} 프롬프트 저장 완료`;
        wikiState.imagePromptStatusError = false;
        wikiEnhanceInlineImages(page);
      });
      const resetBtn = document.createElement('button');
      resetBtn.type = 'button';
      resetBtn.className = 'header-link';
      resetBtn.textContent = '기본값';
      resetBtn.addEventListener('click', () => {
        wikiResetImagePromptTemplate(promptFormat);
        wikiState.imagePromptStatus = `${promptFormat.toUpperCase()} 프롬프트 기본값 복원`;
        wikiState.imagePromptStatusError = false;
        wikiEnhanceInlineImages(page);
      });
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'header-link';
      closeBtn.textContent = '닫기';
      closeBtn.addEventListener('click', () => {
        wikiState.imagePromptEditorIndex = -1;
        wikiState.imagePromptStatus = '';
        wikiState.imagePromptStatusError = false;
        wikiEnhanceInlineImages(page);
      });
      actions.append(saveBtn, resetBtn, closeBtn);
      editor.append(label, textarea, hint, actions);
      if (wikiState.imagePromptStatus) {
        const status = document.createElement('p');
        status.className = `wiki-inline-image-prompt-status${wikiState.imagePromptStatusError ? ' error-text' : ''}`;
        status.textContent = wikiState.imagePromptStatus;
        editor.appendChild(status);
      }
      shell.appendChild(editor);
    }
  });
}

async function wikiRegenerateInlineImage(imageIndex) {
  const page = wikiState.page;
  if (!page?.source_path) return;
  const image = Array.isArray(page?.images) ? page.images[imageIndex] : null;
  if (!image) return;
  const format = wikiSelectedImageFormat(imageIndex, image, page);
  const promptOverride = wikiImagePromptFor(page, image, format);
  try {
    await wikiQueueAiJob({
      source_paths: [page.source_path],
      format,
      prompt_template: promptOverride,
      include_existing_images: true,
      include_sections: false,
      target: 'single_image',
      image_index: imageIndex,
    }, `${image?.alt || page?.title || '이미지'} ${format.toUpperCase()} AI`);
  } catch (error) {
    wikiStatus(`AI 이미지 요청 실패: ${error.message || error}`, true);
  }
}

async function wikiQueueCurrentPageAi() {
  const page = wikiState.page;
  if (!page?.source_path) return;
  const format = String(wiki$('wikiBatchAiFormat')?.value || 'png').trim().toLowerCase() || 'png';
  try {
    await wikiQueueAiJobs(
      wikiPageAiJobSpecs(page, format, {includeExistingImages: true, includeSections: true}),
      `${page?.title || '현재 문서'} 일괄 AI`,
    );
  } catch (error) {
    wikiStatus(`현재 문서 AI 요청 실패: ${error.message || error}`, true);
  }
}

async function wikiQueueSelectedDocsAi() {
  const sourcePaths = wikiSelectedBatchSourcePaths();
  if (!sourcePaths.length) {
    wikiStatus('선택한 문서가 없습니다.', true);
    return;
  }
  const format = String(wiki$('wikiBatchAiFormat')?.value || 'png').trim().toLowerCase() || 'png';
  const jobSpecs = [];
  try {
    for (const sourcePath of sourcePaths) {
      const page = await wikiLoadBatchPageBySourcePath(sourcePath);
      jobSpecs.push(...wikiPageAiJobSpecs(page, format, {includeExistingImages: true, includeSections: true}));
    }
    await wikiQueueAiJobs(jobSpecs, `선택 문서 ${sourcePaths.length}개 일괄 AI`);
  } catch (error) {
    wikiStatus(`선택 문서 AI 요청 실패: ${error.message || error}`, true);
  }
}

function wikiEnhanceSectionHeadings(page = wikiState.page) {
  const article = wiki$('wikiArticle');
  if (!article) return;
  article.querySelectorAll('.wiki-section-ai, .wiki-section-prompt-editor').forEach((node) => node.remove());
  const sections = Array.isArray(page?.sections) ? page.sections : [];
  const headings = article.querySelectorAll('h1, h2, h3, h4, h5, h6');
  headings.forEach((heading, index) => {
    const section = sections[index];
    if (!section) return;
    const anyBusy = false;
    const activeBusy = false;
    const controls = document.createElement('span');
    controls.className = 'wiki-section-ai';
    const select = document.createElement('select');
    select.className = 'wiki-inline-image-format wiki-section-format';
    select.dataset.wikiSectionIndex = String(index);
    select.setAttribute('aria-label', `${section?.title || heading.textContent || '섹션'} 파일 포맷`);
    ['png', 'svg', 'gif'].forEach((format) => {
      const option = document.createElement('option');
      option.value = format;
      option.textContent = format;
      select.appendChild(option);
    });
    select.value = wikiSelectedSectionFormat(index, section, page);
    select.disabled = anyBusy;
    select.addEventListener('change', () => {
      wikiSetSelectedSectionFormat(index, select.value, page);
      if (wikiState.sectionPromptEditorIndex === index) wikiEnhanceSectionHeadings(page);
    });
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'inline-ai-btn has-tip wiki-section-ai-btn';
    button.dataset.tip = '섹션 AI';
    button.textContent = 'AI';
    button.title = '섹션 AI 이미지 생성';
    if (wikiAiTools?.setButtonBusy) {
      wikiAiTools.setButtonBusy(button, {
        busy: activeBusy,
        disabled: anyBusy,
        idleLabel: 'AI',
        busyLabel: '…',
        idleTitle: '섹션 AI 이미지 생성',
        busyTitle: 'AI 이미지 생성 중',
      });
    } else {
      button.disabled = anyBusy;
      if (activeBusy) button.textContent = '…';
    }
    button.addEventListener('click', () => {
      wikiGenerateSectionImage(index);
    });
    const editButton = document.createElement('button');
    editButton.type = 'button';
    editButton.className = 'inline-ai-btn has-tip wiki-section-edit-btn';
    editButton.dataset.tip = '프롬프트 수정';
    editButton.textContent = '✎';
    editButton.title = `${select.value.toUpperCase()} 프롬프트 수정`;
    editButton.disabled = anyBusy;
    editButton.addEventListener('click', () => {
      wikiToggleSectionPromptEditor(index);
    });
    controls.append(select, button, editButton);
    heading.appendChild(controls);
    if (wikiState.sectionPromptEditorIndex === index) {
      const editor = document.createElement('div');
      editor.className = 'wiki-inline-image-prompt-editor wiki-section-prompt-editor';
      const promptFormat = wikiSelectedSectionFormat(index, section, page);
      const template = wikiImagePromptTemplate(promptFormat);
      const label = document.createElement('label');
      label.className = 'wiki-inline-image-prompt-label';
      label.textContent = `${promptFormat.toUpperCase()} 프롬프트`;
      const textarea = document.createElement('textarea');
      textarea.className = 'wiki-inline-image-prompt-textarea';
      textarea.rows = 10;
      textarea.value = String(template?.instruction || '');
      const hint = document.createElement('p');
      hint.className = 'wiki-inline-image-prompt-hint';
      hint.textContent = '사용 가능 변수: {{focus_subject}}, {{page_title}}, {{section_title}}, {{alt}}, {{caption}}, {{context_excerpt}}, {{source_note}}';
      const actions = document.createElement('div');
      actions.className = 'wiki-inline-image-prompt-actions';
      const saveBtn = document.createElement('button');
      saveBtn.type = 'button';
      saveBtn.className = 'header-link';
      saveBtn.textContent = '저장';
      saveBtn.addEventListener('click', () => {
        wikiUpdateImagePromptTemplate(promptFormat, textarea.value);
        wikiState.sectionPromptStatus = `${promptFormat.toUpperCase()} 프롬프트 저장 완료`;
        wikiState.sectionPromptStatusError = false;
        wikiEnhanceSectionHeadings(page);
      });
      const resetBtn = document.createElement('button');
      resetBtn.type = 'button';
      resetBtn.className = 'header-link';
      resetBtn.textContent = '기본값';
      resetBtn.addEventListener('click', () => {
        wikiResetImagePromptTemplate(promptFormat);
        wikiState.sectionPromptStatus = `${promptFormat.toUpperCase()} 프롬프트 기본값 복원`;
        wikiState.sectionPromptStatusError = false;
        wikiEnhanceSectionHeadings(page);
      });
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'header-link';
      closeBtn.textContent = '닫기';
      closeBtn.addEventListener('click', () => {
        wikiState.sectionPromptEditorIndex = -1;
        wikiState.sectionPromptStatus = '';
        wikiState.sectionPromptStatusError = false;
        wikiEnhanceSectionHeadings(page);
      });
      actions.append(saveBtn, resetBtn, closeBtn);
      editor.append(label, textarea, hint, actions);
      if (wikiState.sectionPromptStatus) {
        const status = document.createElement('p');
        status.className = `wiki-inline-image-prompt-status${wikiState.sectionPromptStatusError ? ' error-text' : ''}`;
        status.textContent = wikiState.sectionPromptStatus;
        editor.appendChild(status);
      }
      heading.insertAdjacentElement('afterend', editor);
    }
  });
}

async function wikiGenerateSectionImage(sectionIndex) {
  const page = wikiState.page;
  if (!page?.source_path) return;
  const section = Array.isArray(page?.sections) ? page.sections[sectionIndex] : null;
  if (!section) return;
  const format = wikiSelectedSectionFormat(sectionIndex, section, page);
  const promptOverride = wikiImagePromptFor(page, section, format);
  try {
    await wikiQueueAiJob({
      source_paths: [page.source_path],
      format,
      prompt_template: promptOverride,
      include_existing_images: false,
      include_sections: true,
      target: 'single_section',
      section_index: sectionIndex,
    }, `${section?.title || page?.title || '섹션'} ${format.toUpperCase()} AI`);
  } catch (error) {
    wikiStatus(`섹션 AI 요청 실패: ${error.message || error}`, true);
  }
}

function wikiApplyPage(page) {
  wikiState.page = page || null;
  wikiState.currentSlug = page?.slug || '';
  wikiState.imageFormatSelections = {};
  wikiState.imagePromptEditorIndex = -1;
  wikiState.imagePromptStatus = '';
  wikiState.imagePromptStatusError = false;
  wikiState.sectionFormatSelections = {};
  wikiState.sectionPromptEditorIndex = -1;
  wikiState.sectionPromptStatus = '';
  wikiState.sectionPromptStatusError = false;
  wikiApplyTrustedHtml(wiki$('wikiArticle'), wikiTrustedRenderedHtml(page?.html || ''), {emptyText: '문서가 비어 있습니다.'});
  wikiEnhanceInlineImages(page);
  wikiEnhanceSectionHeadings(page);
  wiki$('wikiRawLink').href = page?.raw_url || '#';
  document.title = `${page?.title || '문서'} · ${wikiState.index?.book?.title || 'CS 학습 위키'}`;
  wikiRenderBreadcrumbs(page);
  wikiRenderLastModified(page);
  wikiRenderLinkedCards(page);
  wikiRenderPageNav(page);
  wikiRenderToc();
  wikiApplyEditorState();
  wikiStatus(`${page?.title || '문서'} 열람 중`);
}

function wikiScrollPageToTop() {
  window.requestAnimationFrame(() => {
    window.scrollTo({top: 0, left: 0, behavior: 'auto'});
  });
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

async function wikiLoadPage(slug, {push = false, scrollToTop = false} = {}) {
  const normalized = String(slug || wikiState.index?.default_page_slug || '').trim() || '_book';
  const page = await wikiFetchJson(wikiApiUrl(`/api/wiki/page/${encodeURIComponent(normalized).replace(/%2F/g, '/')}`));
  if (push && window.location.pathname !== wikiPageUrl(page.slug)) {
    window.history.pushState({}, '', wikiPageUrl(page.slug));
  }
  wikiApplyPage(page);
  if (scrollToTop) wikiScrollPageToTop();
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
    wikiApplyArchiveButtonState();
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
    wikiApplyArchiveButtonState();
  } catch (error) {
    checkbox.checked = !nextChecked;
    checkbox.disabled = false;
    delete checkbox.dataset.wikiTaskPending;
    wikiStatus(`체크 저장 실패: ${error.message || error}`, true);
  }
}

async function wikiInit() {
  wikiState.sidebarOpen = readSavedWikiSidebarState();
  wikiState.batchAiMode = readSavedWikiBatchAiMode();
  applyWikiSidebarState({persist: false});
  applyWikiBatchAiMode({persist: false});
  applyWikiSearchState({focus: false});
  wikiApplyEditorState();
  wikiApplyArchiveButtonState();
  try {
    wikiState.index = await wikiFetchJson(wikiApiUrl('/api/wiki/index'));
    wiki$('wikiBookTitle').textContent = wikiState.index.book?.title || 'CS 학습 위키';
    wiki$('wikiBookIntroLink').href = wikiPageUrl(wikiState.index.book?.slug || '_book');
    wikiRenderToc();
    await wikiLoadPage(wikiCurrentSlug() || wikiState.index.default_page_slug || wikiState.index.book?.slug || '_book', {scrollToTop: true});
  } catch (error) {
    wikiStatus(`위키 로딩 실패: ${error.message || error}`, true);
    wikiRenderMessage(wiki$('wikiArticle'), error.message || error, 'error-text');
  }
}

wiki$('wikiSearchInput')?.addEventListener('input', (event) => {
  wikiState.query = event.target.value || '';
  wikiRenderToc();
});

wiki$('wikiSearchInput')?.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    event.preventDefault();
    closeWikiSearch({restoreFocus: true});
    return;
  }
  if (event.key !== 'Enter') return;
  event.preventDefault();
  wikiShowSearchResults();
});

wiki$('wikiSearchToggleBtn')?.addEventListener('click', () => {
  toggleWikiSearch();
});
wiki$('wikiBatchCurrentBtn')?.addEventListener('click', () => {
  wikiQueueCurrentPageAi();
});
wiki$('wikiBatchSelectedBtn')?.addEventListener('click', () => {
  wikiQueueSelectedDocsAi();
});
wiki$('wikiBatchAiToggleBtn')?.addEventListener('click', () => {
  toggleWikiBatchAiMode();
});

wiki$('wikiToc')?.addEventListener('click', (event) => {
  const toggle = event.target.closest('[data-wiki-toc-toggle]');
  if (!toggle) return;
  event.preventDefault();
  toggleWikiTocBranch(toggle.dataset.wikiTocToggle || '');
});

wiki$('wikiSidebarTopbarBtn')?.addEventListener('click', (event) => {
  if (!wikiState.sidebarOpen) wikiRememberSidebarFocusTarget(event.currentTarget);
  toggleWikiSidebar();
});
wiki$('wikiSidebarCloseBtn')?.addEventListener('click', () => {
  closeWikiSidebarOnMobile({restoreFocus: true});
});
wiki$('wikiSidebarBackdrop')?.addEventListener('click', () => {
  closeWikiSidebarOnMobile({restoreFocus: true});
});
wiki$('wikiSidebarToggleBtn')?.addEventListener('click', (event) => {
  if (!wikiState.sidebarOpen) wikiRememberSidebarFocusTarget(event.currentTarget);
  toggleWikiSidebar();
});
wiki$('wikiEditBtn')?.addEventListener('click', () => {
  wikiStartEdit();
});
wiki$('wikiGithubArchiveBtn')?.addEventListener('click', () => {
  wikiArchiveToGithub();
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
  wikiLoadPage(wikiCurrentSlug() || wikiState.index.default_page_slug || '_book', {scrollToTop: true}).then(() => {
    wikiCloseEditor({force: true});
  }).catch((error) => {
    wikiStatus(`문서 이동 실패: ${error.message || error}`, true);
  });
});
window.addEventListener('resize', () => {
  applyWikiSidebarState({persist: false});
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
  wikiLoadPage(slug, {push: true, scrollToTop: true}).then(() => {
    wikiCloseEditor({force: true});
    closeWikiSidebarOnMobile();
    closeWikiSearch();
  }).catch((error) => {
    wikiStatus(`문서 이동 실패: ${error.message || error}`, true);
  });
});

document.addEventListener('change', (event) => {
  const aiCheckbox = event.target.closest('input[data-wiki-ai-source]');
  if (aiCheckbox) {
    const sourcePath = String(aiCheckbox.dataset.wikiAiSource || '').trim();
    if (!sourcePath) return;
    wikiState.tocAiSelections[sourcePath] = aiCheckbox.checked;
    wikiUpdateBatchAiHint();
    return;
  }
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
  if (event.key === 'Escape' && wikiIsMobileViewport() && wikiState.sidebarOpen) {
    event.preventDefault();
    closeWikiSidebarOnMobile({restoreFocus: true});
    return;
  }
  if (!wikiState.editorOpen) return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    wikiSaveEditor();
  }
});

wikiInit();
