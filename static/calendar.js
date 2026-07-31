const CALENDAR_API_PATH = '/api/calendar/recruitment';
const COMPACT_CALENDAR_MEDIA = '(max-width: 760px)';
const EMPTY_SELECTION_TEXT = '달력이나 목록에서 일정을 누르면 상세와 공고 링크를 보여준다.';
const CALENDAR_SIDEBAR_STATE_KEY = 'csFlashcardsCalendarSidebar:v1';
const CALENDAR_LAST_PANEL_KEY = 'csFlashcardsCalendarLastPanel:v1';

const PANEL_TITLES = {
  overview: '포커스',
  summary: '요약',
  timeline: '타임라인',
  events: '일정 목록',
  subscribe: '캘린더 구독',
  priorities: '우선순위',
  filters: '필터',
  watch: '기관 현황',
};

const calendarState = {
  payload: null,
  calendar: null,
  selectedInstitutions: new Set(),
  selectedEventTypes: new Set(),
  selectedStatuses: new Set(),
  hideApproximate: false,
  selectedEventId: '',
  selectedDateKey: '',
  sidebarOpen: false,
  sidebarMenuOpen: false,
  detailOpen: false,
  activeSidebarPanel: 'overview',
  lastUtilityPanel: 'overview',
  eventListMode: 'selected',
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function uniqueValues(items, key) {
  return [...new Set((items || []).map((item) => item[key]).filter(Boolean))];
}

function compactCalendarView() {
  return window.matchMedia ? window.matchMedia(COMPACT_CALENDAR_MEDIA).matches : window.innerWidth <= 760;
}

function preferredCalendarView() {
  return compactCalendarView() ? 'listMonth' : 'dayGridMonth';
}

function defaultCalendarSidebarOpen() {
  return false;
}

function readSavedCalendarSidebarState() {
  try {
    const saved = window.localStorage.getItem(CALENDAR_SIDEBAR_STATE_KEY);
    if (saved === 'open') return true;
    if (saved === 'closed') return false;
  } catch (_error) {
    // Ignore storage failures and use the default collapsed state.
  }
  return defaultCalendarSidebarOpen();
}

function saveCalendarSidebarState() {
  try {
    window.localStorage.setItem(CALENDAR_SIDEBAR_STATE_KEY, calendarState.sidebarOpen ? 'open' : 'closed');
  } catch (_error) {
    // Ignore storage failures.
  }
}

function readSavedLastUtilityPanel() {
  try {
    const saved = window.localStorage.getItem(CALENDAR_LAST_PANEL_KEY);
    if (saved && PANEL_TITLES[saved]) return saved;
  } catch (_error) {
    // Ignore storage failures.
  }
  return 'overview';
}

function saveLastUtilityPanel() {
  try {
    window.localStorage.setItem(CALENDAR_LAST_PANEL_KEY, calendarState.lastUtilityPanel);
  } catch (_error) {
    // Ignore storage failures.
  }
}

function syncBackdrop() {
  const visible = calendarState.sidebarOpen || calendarState.detailOpen;
  $('calendarDrawerBackdrop').hidden = !visible;
  document.body.classList.toggle('calendar-overlay-open', visible);
}

function applyCalendarSidebarState({ persist = true } = {}) {
  const sidebar = $('calendarSidebar');
  document.body.classList.toggle('calendar-sidebar-collapsed', !calendarState.sidebarOpen);
  if (sidebar) {
    sidebar.hidden = !calendarState.sidebarOpen;
    sidebar.setAttribute('aria-hidden', String(!calendarState.sidebarOpen));
  }
  if (!calendarState.sidebarOpen) {
    toggleCalendarSidebarMenu(false);
  }
  syncBackdrop();
  if (persist) saveCalendarSidebarState();
}

function toggleCalendarSidebar(force = !calendarState.sidebarOpen) {
  calendarState.sidebarOpen = Boolean(force);
  applyCalendarSidebarState();
}

function applyCalendarSidebarMenuState() {
  const menu = $('calendarSidebarMenu');
  const featureBtn = $('calendarFeatureMenuBtn');
  if (menu) menu.hidden = !calendarState.sidebarMenuOpen;
  if (featureBtn) featureBtn.setAttribute('aria-expanded', String(calendarState.sidebarMenuOpen));
}

function toggleCalendarSidebarMenu(force = !calendarState.sidebarMenuOpen) {
  calendarState.sidebarMenuOpen = Boolean(force);
  applyCalendarSidebarMenuState();
}

function renderSidebarTitle() {
  const title = $('calendarSidebarTitle');
  if (title) title.textContent = PANEL_TITLES[calendarState.activeSidebarPanel] || '보조 패널';
}

function applyActiveSidebarPanel() {
  document.querySelectorAll('[data-sidebar-panel]').forEach((element) => {
    const active = element.dataset.sidebarPanel === calendarState.activeSidebarPanel;
    element.hidden = !active;
    element.classList.toggle('is-active', active);
  });
  document.querySelectorAll('[data-sidebar-panel-target]').forEach((button) => {
    button.classList.toggle('active', button.dataset.sidebarPanelTarget === calendarState.activeSidebarPanel);
  });
  document.querySelectorAll('[data-quick-panel]').forEach((button) => {
    button.classList.toggle('active', button.dataset.quickPanel === calendarState.activeSidebarPanel);
  });
  renderSidebarTitle();
}

function setActiveSidebarPanel(panelId, { openSidebar = true, closeMenu = true, scroll = false } = {}) {
  if (!PANEL_TITLES[panelId]) return;
  calendarState.activeSidebarPanel = panelId;
  calendarState.lastUtilityPanel = panelId;
  saveLastUtilityPanel();
  applyActiveSidebarPanel();
  if (openSidebar && !calendarState.sidebarOpen) {
    toggleCalendarSidebar(true);
  }
  if (closeMenu) {
    toggleCalendarSidebarMenu(false);
  }
  if (panelId === 'events') {
    renderEventList();
  }
  if (scroll) {
    const panel = document.querySelector(`[data-sidebar-panel="${panelId}"]`);
    panel?.scrollIntoView({ block: 'nearest' });
  }
}

function openLastUtilityPanel() {
  if (calendarState.sidebarOpen) {
    toggleCalendarSidebar(false);
    return;
  }
  setActiveSidebarPanel(calendarState.lastUtilityPanel || 'overview', { openSidebar: true, closeMenu: true, scroll: false });
}

function closeDetailDrawer() {
  calendarState.detailOpen = false;
  const detailDrawer = $('calendarDetailDrawer');
  if (detailDrawer) {
    detailDrawer.hidden = true;
    detailDrawer.setAttribute('aria-hidden', 'true');
  }
  syncBackdrop();
}

function openDetailDrawer() {
  calendarState.detailOpen = true;
  const detailDrawer = $('calendarDetailDrawer');
  if (detailDrawer) {
    detailDrawer.hidden = false;
    detailDrawer.setAttribute('aria-hidden', 'false');
  }
  syncBackdrop();
}

function openSidebarPanelFromMenu(panelId) {
  if (panelId === 'close') {
    toggleCalendarSidebar(false);
    toggleCalendarSidebarMenu(false);
    return;
  }
  if (panelId === 'detail') {
    toggleCalendarSidebarMenu(false);
    openDetailDrawerFromSelection();
    return;
  }
  setActiveSidebarPanel(panelId, { openSidebar: true, closeMenu: true, scroll: true });
}

function eventTimestamp(event, field = 'start') {
  const value = field === 'end' ? (event.end || event.end_inclusive || event.start) : (event.start || event.start_inclusive);
  return Date.parse(value || '') || 0;
}

function sortEventsByStart(items) {
  return [...(items || [])].sort((left, right) => {
    const delta = eventTimestamp(left) - eventTimestamp(right);
    if (delta) return delta;
    return String(left.list_title || left.title || '').localeCompare(String(right.list_title || right.title || ''), 'ko');
  });
}

function priorityLabel(item) {
  return String(item?.institution_name || item?.institution_group || '').trim();
}

function hexToRgb(value) {
  const normalized = String(value || '').trim().replace('#', '');
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) return null;
  return {
    r: Number.parseInt(normalized.slice(0, 2), 16),
    g: Number.parseInt(normalized.slice(2, 4), 16),
    b: Number.parseInt(normalized.slice(4, 6), 16),
  };
}

function tintColor(value, alpha) {
  const rgb = hexToRgb(value);
  if (!rgb) return '';
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`;
}

function applyCalendarEventTone(info) {
  const color = info.event.backgroundColor || info.event.borderColor || '';
  const tint = tintColor(color, 0.14);
  const border = tintColor(color, 0.28);
  if (!tint || !border) return;
  info.el.style.setProperty('--event-tint', tint);
  info.el.style.setProperty('--event-border', border);
  info.el.style.setProperty('--event-solid', color);
  info.el.classList.add('fc-event-toned');
  if (info.view.type.startsWith('list')) {
    info.el.classList.add('fc-list-event-toned');
  }
}

function matchesFilters(event) {
  if (!calendarState.selectedInstitutions.has(event.institution.id)) return false;
  if (!calendarState.selectedEventTypes.has(event.event_type)) return false;
  if (!calendarState.selectedStatuses.has(event.status)) return false;
  if (calendarState.hideApproximate && event.is_approximate) return false;
  return true;
}

function filteredEvents() {
  return sortEventsByStart((calendarState.payload?.events || []).filter(matchesFilters));
}

function eventDateKey(event) {
  return String(event?.start_inclusive || event?.start || '').slice(0, 10);
}

function nextUpcomingEvent(events, { exactOnly = false } = {}) {
  const now = Date.now();
  const sorted = sortEventsByStart(events).filter((event) => !exactOnly || !event.is_approximate);
  return sorted.find((event) => eventTimestamp(event, 'end') >= now) || sorted[0] || null;
}

function toggleSetValue(targetSet, value, fallbackValues) {
  if (targetSet.has(value)) {
    targetSet.delete(value);
  } else {
    targetSet.add(value);
  }
  const fallbackItems = typeof fallbackValues === 'function' ? fallbackValues() : fallbackValues;
  if (!targetSet.size) {
    (fallbackItems || []).forEach((item) => targetSet.add(item));
  }
}

function renderFilterChips(containerId, items, selectedSet, key, labelKey) {
  const container = $(containerId);
  if (!container) return;
  container.innerHTML = items.map((item) => {
    const value = item[key];
    const active = selectedSet.has(value);
    return `<button class="filter-chip${active ? ' active' : ''}" type="button" data-filter-value="${escapeHtml(value)}">${escapeHtml(item[labelKey])}</button>`;
  }).join('');
}

function allInstitutions() {
  return (calendarState.payload?.institutions || []).map((item) => item.id);
}

function allEventTypes() {
  return uniqueValues(calendarState.payload?.events || [], 'event_type');
}

function allStatuses() {
  return uniqueValues(calendarState.payload?.events || [], 'status');
}

function resetFilters() {
  calendarState.selectedInstitutions = new Set(allInstitutions());
  calendarState.selectedEventTypes = new Set(allEventTypes());
  calendarState.selectedStatuses = new Set(allStatuses());
  calendarState.hideApproximate = false;
  if ($('hideApproximateToggle')) $('hideApproximateToggle').checked = false;
  initializeFilterChips();
  rerenderCalendar();
}

function renderQuickBar(events = filteredEvents()) {
  const payload = calendarState.payload;
  if (!payload) return;
  const openEvents = events.filter((event) => event.status === 'open');
  const nextExactEvent = nextUpcomingEvent(events, { exactOnly: true });
  const restrictedGroups = [
    calendarState.selectedInstitutions.size !== allInstitutions().length,
    calendarState.selectedEventTypes.size !== allEventTypes().length,
    calendarState.selectedStatuses.size !== allStatuses().length,
    calendarState.hideApproximate,
  ].filter(Boolean).length;

  $('quickOpenCount').textContent = `${openEvents.length}건`;
  $('quickWatchCount').textContent = `${payload.dashboard.watch.length}곳`;
  $('quickFilterState').textContent = restrictedGroups ? `${restrictedGroups}개 조건` : '전체';

  const title = $('quickNextEventTitle');
  const meta = $('quickNextEventMeta');
  if (nextExactEvent) {
    title.textContent = `${nextExactEvent.institution.short_name} ${nextExactEvent.display_label}`;
    meta.textContent = nextExactEvent.date_display;
  } else {
    title.textContent = '확정 일정 없음';
    meta.textContent = '예정 일정만 남아 있다.';
  }
}

function renderOverview(events = filteredEvents()) {
  const payload = calendarState.payload;
  if (!payload) return;
  const openEvents = events.filter((event) => event.status === 'open');
  const nextExactEvent = nextUpcomingEvent(events, { exactOnly: true });
  const timelineLead = payload.timeline?.[0] || null;
  const priorities = payload.dashboard?.priorities || payload.priorities || [];
  const topPriority = priorities[0] || null;

  let headline = timelineLead?.headline || '지금 봐야 할 채용 일정만 압축했다.';
  let focus = timelineLead?.focus || payload.calendar.description || '';

  if (openEvents.length) {
    const leadOpen = openEvents[0];
    headline = `${leadOpen.institution.name} ${leadOpen.display_label} 진행 중`;
    focus = `${leadOpen.date_display} · ${leadOpen.summary || leadOpen.description || '지금 바로 대응해야 하는 일정'}`;
  } else if (nextExactEvent) {
    headline = `${nextExactEvent.institution.name} ${nextExactEvent.display_label}`;
    focus = `${nextExactEvent.date_display} · ${nextExactEvent.summary || nextExactEvent.description || '다음 확정 일정'}`;
  } else if (topPriority) {
    focus = `${priorityLabel(topPriority)} 우선 · ${topPriority.reason}`;
  }

  $('overviewHeadline').textContent = headline;
  $('overviewFocus').textContent = focus || '업데이트된 일정과 우선순위를 한 화면에 보여준다.';

  const rows = [
    ['현재 보이는 일정', `${events.length}건`, calendarState.hideApproximate ? '예정 월/전후 숨김 적용' : '필터 기준으로 계산'],
    ['진행 중', `${openEvents.length}건`, openEvents[0] ? openEvents[0].date_display : '열린 접수 일정 없음'],
    ['다음 확정 일정', nextExactEvent ? nextExactEvent.display_label : '대기 중', nextExactEvent ? `${nextExactEvent.institution.short_name} · ${nextExactEvent.date_display}` : '확정 일정이 더 필요함'],
    ['체크 대기 기관', `${payload.dashboard.watch.length}곳`, topPriority ? `${priorityLabel(topPriority)}부터 확인` : '링크만 짧게 확인'],
  ];

  $('overviewHighlights').innerHTML = `
    <table class="compact-table compact-table--summary">
      <tbody>
        ${rows.map(([label, value, note]) => `
          <tr>
            <th scope="row">${escapeHtml(label)}</th>
            <td>
              <strong>${escapeHtml(value)}</strong>
              <span class="table-note">${escapeHtml(note)}</span>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderTimeline() {
  const container = $('timelineHighlights');
  const timeline = calendarState.payload?.timeline || [];
  if (!container) return;
  if (!timeline.length) {
    container.innerHTML = '<p class="event-detail-empty">표시할 타임라인이 없다.</p>';
    return;
  }
  container.innerHTML = `
    <table class="compact-table">
      <thead>
        <tr><th>시기</th><th>핵심</th></tr>
      </thead>
      <tbody>
        ${timeline.map((item) => `
          <tr>
            <td>${escapeHtml(item.period || '')}</td>
            <td>
              <strong>${escapeHtml(item.headline || '')}</strong>
              <span class="table-note">${escapeHtml(item.focus || '')}</span>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderPriorityList() {
  const container = $('priorityList');
  const priorities = calendarState.payload?.dashboard?.priorities || calendarState.payload?.priorities || [];
  if (!container) return;
  if (!priorities.length) {
    container.innerHTML = '<p class="event-detail-empty">표시할 우선순위가 없다.</p>';
    return;
  }
  container.innerHTML = `
    <table class="compact-table">
      <thead>
        <tr><th>우선</th><th>대상</th><th>이유</th></tr>
      </thead>
      <tbody>
        ${priorities.map((item) => `
          <tr>
            <td>${escapeHtml(item.rank)}</td>
            <td>${escapeHtml(priorityLabel(item))}</td>
            <td>${escapeHtml(item.reason || '')}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderCounts() {
  const counts = calendarState.payload?.counts;
  const container = $('calendarCounts');
  if (!counts || !container) return;
  const items = [
    ['전체 일정', counts.total_events, '공고 + 예비공고 + 연간 계획'],
    ['진행 중', counts.open_events, '지금 바로 대응 가능한 일정'],
    ['확정 날짜', counts.exact_events, '일 단위가 확정된 일정'],
    ['예정/관측', counts.planned_events, '월 단위·전후 일정 포함'],
    ['체크 대기 기관', counts.watch_only_institutions, '짧게 확인만 해도 되는 곳'],
  ];
  container.innerHTML = `
    <table class="compact-table compact-table--summary">
      <tbody>
        ${items.map(([label, value, note]) => `
          <tr>
            <th scope="row">${escapeHtml(label)}</th>
            <td>
              <strong>${escapeHtml(value)}</strong>
              <span class="table-note">${escapeHtml(note)}</span>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function renderDashboardList(containerId, items, emptyText) {
  const container = $(containerId);
  if (!container) return;
  if (!items.length) {
    container.innerHTML = `<p class="event-detail-empty">${escapeHtml(emptyText)}</p>`;
    return;
  }
  container.innerHTML = `
    <table class="compact-table">
      <thead>
        <tr><th>기관</th><th>상태</th><th>요약</th></tr>
      </thead>
      <tbody>
        ${items.map((item) => `
          <tr>
            <td>${escapeHtml(item.institution.short_name || item.institution.name)}</td>
            <td>${escapeHtml(item.status)}</td>
            <td>
              <strong>${escapeHtml(item.schedule_summary || item.note || '')}</strong>
              ${(item.links || []).length ? `<span class="table-links">${(item.links || []).map((link) => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)}</a>`).join('')}</span>` : ''}
              ${item.note && item.schedule_summary ? `<span class="table-note">${escapeHtml(item.note)}</span>` : ''}
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

function selectedDateEvents(events) {
  const source = sortEventsByStart(events);
  if (!source.length) return [];
  const activeDateKey = calendarState.selectedDateKey || eventDateKey(nextUpcomingEvent(source) || source[0]);
  calendarState.selectedDateKey = activeDateKey;
  return source.filter((event) => eventDateKey(event) === activeDateKey);
}

function renderEventListModeButtons() {
  $('eventListModeSelectedBtn')?.classList.toggle('active', calendarState.eventListMode === 'selected');
  $('eventListModeAllBtn')?.classList.toggle('active', calendarState.eventListMode === 'all');
}

function setEventListMode(mode) {
  calendarState.eventListMode = mode === 'all' ? 'all' : 'selected';
  renderEventList();
}

function renderEventList(events = filteredEvents()) {
  const container = $('eventList');
  const count = $('eventListCount');
  if (!container) return;

  let listEvents = sortEventsByStart(events);
  let contextText = '필터 기준 전체 일정';

  if (calendarState.eventListMode === 'selected') {
    listEvents = selectedDateEvents(events);
    const lead = listEvents[0] || null;
    contextText = lead ? `${lead.date_display} 일정만 표시` : '선택한 날짜 일정이 없다.';
  }

  renderEventListModeButtons();
  if (count) count.textContent = `${listEvents.length}건`;
  $('eventListContext').textContent = contextText;

  if (!listEvents.length) {
    container.innerHTML = '<p class="event-detail-empty">현재 조건에 맞는 일정이 없다.</p>';
    return;
  }

  container.innerHTML = `
    <table class="compact-table compact-table--events">
      <thead>
        <tr><th>날짜</th><th>일정</th><th>상태</th></tr>
      </thead>
      <tbody>
        ${listEvents.map((event) => `
          <tr>
            <td>${escapeHtml(event.date_display)}</td>
            <td>
              <button class="table-row-button${event.id === calendarState.selectedEventId ? ' is-selected' : ''}" type="button" data-event-id="${escapeHtml(event.id)}">${escapeHtml(event.list_title || event.title)}</button>
              <span class="table-note">${escapeHtml(event.institution.short_name)} · ${escapeHtml(event.event_type_label)}${event.summary ? ` · ${escapeHtml(event.summary)}` : ''}</span>
            </td>
            <td>${escapeHtml(event.status_label)}${event.is_approximate ? ' · 예정' : ''}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;

  container.querySelectorAll('[data-event-id]').forEach((element) => {
    element.addEventListener('click', () => selectEvent(element.dataset.eventId || '', { openDetail: true }));
  });
}

function renderSelectedEvent(event) {
  const detail = $('selectedEventDetail');
  const badge = $('selectedEventBadge');
  if (!detail || !badge) return;
  if (!event) {
    badge.hidden = true;
    detail.className = 'event-detail-empty';
    detail.textContent = EMPTY_SELECTION_TEXT;
    return;
  }
  badge.hidden = false;
  badge.textContent = event.institution.short_name;
  detail.className = '';
  detail.innerHTML = `
    <h3>${escapeHtml(event.list_title || event.title)}</h3>
    <p>${escapeHtml(event.summary || event.description || '')}</p>
    <dl class="detail-grid">
      <div>
        <dt>기관</dt>
        <dd>${escapeHtml(event.institution.name)}</dd>
      </div>
      <div>
        <dt>일정</dt>
        <dd>${escapeHtml(event.date_display)}</dd>
      </div>
      <div>
        <dt>유형</dt>
        <dd>${escapeHtml(event.event_type_label)}</dd>
      </div>
      <div>
        <dt>상태</dt>
        <dd>${escapeHtml(event.status_label)}</dd>
      </div>
    </dl>
    ${event.description ? `<p>${escapeHtml(event.description)}</p>` : ''}
    <ul>
      ${event.source_label ? `<li>출처: ${escapeHtml(event.source_label)}</li>` : ''}
      ${event.details ? `<li>${escapeHtml(event.details)}</li>` : ''}
    </ul>
    <div class="event-actions">
      ${event.url ? `<a class="primary-link" href="${escapeHtml(event.url)}" target="_blank" rel="noopener noreferrer">공고 열기</a>` : ''}
      <a href="${escapeHtml(event.google_calendar_url)}" target="_blank" rel="noopener noreferrer">Google Calendar에 추가</a>
    </div>
  `;
}

function syncSelectedEventCard() {
  $('eventList')?.querySelectorAll('[data-event-id]').forEach((element) => {
    element.classList.toggle('is-selected', element.dataset.eventId === calendarState.selectedEventId);
  });
}

function selectEvent(eventId, { openDetail = false } = {}) {
  calendarState.selectedEventId = eventId;
  const event = filteredEvents().find((item) => item.id === eventId) || null;
  if (!event) {
    renderSelectedEvent(null);
    syncSelectedEventCard();
    closeDetailDrawer();
    return;
  }
  calendarState.selectedDateKey = eventDateKey(event);
  renderSelectedEvent(event);
  renderEventList();
  syncSelectedEventCard();
  if (openDetail) {
    openDetailDrawer();
  }
}

function openDetailDrawerFromSelection() {
  const events = filteredEvents();
  const selected = events.find((item) => item.id === calendarState.selectedEventId) || events[0] || null;
  if (!selected) {
    renderSelectedEvent(null);
    return;
  }
  selectEvent(selected.id, { openDetail: true });
}

function rerenderCalendar() {
  const events = filteredEvents();
  if (calendarState.calendar) {
    calendarState.calendar.removeAllEvents();
    calendarState.calendar.addEventSource(events);
  }
  renderQuickBar(events);
  renderOverview(events);
  renderCounts();
  renderTimeline();
  renderPriorityList();
  renderDashboardList('dashboardOpen', calendarState.payload?.dashboard?.open || [], '현재 공개된 일정이 없다.');
  renderDashboardList('dashboardWatch', calendarState.payload?.dashboard?.watch || [], '미확인 기관이 없다.');
  renderEventList(events);

  const nextSelected = events.find((item) => item.id === calendarState.selectedEventId) || events[0] || null;
  if (nextSelected) {
    selectEvent(nextSelected.id);
  } else {
    calendarState.selectedEventId = '';
    renderSelectedEvent(null);
    syncSelectedEventCard();
    closeDetailDrawer();
  }
}

function renderActiveFilterSummary() {
  const parts = [];
  if (calendarState.selectedInstitutions.size !== allInstitutions().length) parts.push(`기관 ${calendarState.selectedInstitutions.size}`);
  if (calendarState.selectedEventTypes.size !== allEventTypes().length) parts.push(`유형 ${calendarState.selectedEventTypes.size}`);
  if (calendarState.selectedStatuses.size !== allStatuses().length) parts.push(`상태 ${calendarState.selectedStatuses.size}`);
  if (calendarState.hideApproximate) parts.push('예정 숨김');
  $('activeFilterSummary').textContent = parts.length ? parts.join(' · ') : '전체 보기';
}

function bindFilterGroup(containerId, selectedSet, allValues) {
  $(containerId)?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-filter-value]');
    if (!button) return;
    toggleSetValue(selectedSet, button.dataset.filterValue || '', allValues);
    initializeFilterChips();
    rerenderCalendar();
  });
}

function initializeFilterChips() {
  const payload = calendarState.payload;
  if (!payload) return;
  renderFilterChips('institutionFilters', payload.institutions, calendarState.selectedInstitutions, 'id', 'short_name');
  renderFilterChips(
    'eventTypeFilters',
    uniqueValues(payload.events, 'event_type').map((eventType) => ({ event_type: eventType, event_type_label: payload.events.find((item) => item.event_type === eventType)?.event_type_label || eventType })),
    calendarState.selectedEventTypes,
    'event_type',
    'event_type_label',
  );
  renderFilterChips(
    'statusFilters',
    uniqueValues(payload.events, 'status').map((status) => ({ status, status_label: payload.events.find((item) => item.status === status)?.status_label || status })),
    calendarState.selectedStatuses,
    'status',
    'status_label',
  );
  renderActiveFilterSummary();
}

function initializeCalendar() {
  const element = $('calendar');
  if (!element || !calendarState.payload) return;
  calendarState.calendar = new window.FullCalendar.Calendar(element, {
    locale: 'ko',
    initialView: preferredCalendarView(),
    height: 'auto',
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,listMonth',
    },
    buttonText: {
      today: '오늘',
      month: '월',
      list: '목록',
    },
    events: filteredEvents(),
    eventClick(info) {
      info.jsEvent.preventDefault();
      selectEvent(info.event.id, { openDetail: true });
    },
    eventDidMount(info) {
      applyCalendarEventTone(info);
    },
  });
  calendarState.calendar.render();
  applyResponsiveCalendarView(true);
}

function applyResponsiveCalendarView(force = false) {
  if (!calendarState.calendar) return;
  const targetView = preferredCalendarView();
  if (force || calendarState.calendar.view.type !== targetView) {
    calendarState.calendar.changeView(targetView);
  }
}

async function copyIcsLink() {
  const link = $('icsSubscribeLink')?.href || '';
  if (!link) return;
  try {
    await navigator.clipboard.writeText(link);
    $('copyIcsLinkBtn').textContent = '복사됨';
    window.setTimeout(() => {
      $('copyIcsLinkBtn').textContent = 'ICS 링크 복사';
    }, 1500);
  } catch (_error) {
    window.prompt('이 링크를 복사해서 Google Calendar의 URL로 추가에 넣으면 된다.', link);
  }
}

async function loadCalendar() {
  const response = await fetch(CALENDAR_API_PATH, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error('캘린더 데이터를 불러오지 못했다.');
  calendarState.payload = await response.json();
  const payload = calendarState.payload;

  payload.institutions.forEach((item) => calendarState.selectedInstitutions.add(item.id));
  allEventTypes().forEach((item) => calendarState.selectedEventTypes.add(item));
  allStatuses().forEach((item) => calendarState.selectedStatuses.add(item));

  $('calendarUpdatedAt').textContent = `마지막 업데이트 ${payload.calendar.last_updated} · 총 ${payload.counts.total_events}개 일정`;
  $('calendarIntro').textContent = payload.calendar.intro || payload.calendar.description || '';
  $('icsFeedLink').href = payload.calendar.ics_url;
  $('icsSubscribeLink').href = payload.calendar.ics_url;
  const notes = $('calendarNotes');
  if (notes) {
    notes.innerHTML = (payload.calendar.notes || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  }

  initializeFilterChips();
  initializeCalendar();
  rerenderCalendar();
  applyActiveSidebarPanel();
}

calendarState.sidebarOpen = readSavedCalendarSidebarState();
calendarState.lastUtilityPanel = readSavedLastUtilityPanel();
calendarState.activeSidebarPanel = calendarState.lastUtilityPanel;
applyCalendarSidebarState({ persist: false });
applyCalendarSidebarMenuState();
applyActiveSidebarPanel();

$('calendarSidebarToggleBtn')?.addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  openLastUtilityPanel();
});
$('calendarFeatureMenuBtn')?.addEventListener('click', (event) => {
  event.preventDefault();
  event.stopPropagation();
  toggleCalendarSidebarMenu();
});
document.querySelectorAll('[data-sidebar-panel-target]').forEach((button) => {
  button.addEventListener('click', () => openSidebarPanelFromMenu(button.dataset.sidebarPanelTarget || ''));
});
$('calendarSidebarCloseBtn')?.addEventListener('click', () => toggleCalendarSidebar(false));
$('calendarDetailCloseBtn')?.addEventListener('click', closeDetailDrawer);
$('calendarDrawerBackdrop')?.addEventListener('click', () => {
  toggleCalendarSidebar(false);
  closeDetailDrawer();
});
$('copyIcsLinkBtn')?.addEventListener('click', copyIcsLink);
$('resetFiltersBtn')?.addEventListener('click', resetFilters);
$('quickFilterBtn')?.addEventListener('click', () => setActiveSidebarPanel('filters', { openSidebar: true, closeMenu: true, scroll: false }));
$('quickListBtn')?.addEventListener('click', () => setActiveSidebarPanel('events', { openSidebar: true, closeMenu: true, scroll: false }));
document.querySelectorAll('[data-quick-panel]').forEach((button) => {
  button.addEventListener('click', () => {
    const panelId = button.dataset.quickPanel || 'overview';
    if (calendarState.sidebarOpen && calendarState.activeSidebarPanel === panelId) {
      toggleCalendarSidebar(false);
      return;
    }
    setActiveSidebarPanel(panelId, { openSidebar: true, closeMenu: true, scroll: false });
  });
});
$('quickNextEventBtn')?.addEventListener('click', () => {
  const nextExactEvent = nextUpcomingEvent(filteredEvents(), { exactOnly: true });
  if (nextExactEvent) {
    selectEvent(nextExactEvent.id, { openDetail: true });
  }
});
$('eventListModeSelectedBtn')?.addEventListener('click', () => setEventListMode('selected'));
$('eventListModeAllBtn')?.addEventListener('click', () => setEventListMode('all'));
$('hideApproximateToggle')?.addEventListener('change', (event) => {
  calendarState.hideApproximate = Boolean(event.target.checked);
  rerenderCalendar();
});
window.matchMedia?.(COMPACT_CALENDAR_MEDIA).addEventListener?.('change', () => applyResponsiveCalendarView());
document.addEventListener('click', (event) => {
  if (calendarState.sidebarMenuOpen && !event.target.closest('.calendar-feature-menu-wrap')) {
    toggleCalendarSidebarMenu(false);
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    toggleCalendarSidebarMenu(false);
    closeDetailDrawer();
    toggleCalendarSidebar(false);
  }
});
bindFilterGroup('institutionFilters', calendarState.selectedInstitutions, () => allInstitutions());
bindFilterGroup('eventTypeFilters', calendarState.selectedEventTypes, () => allEventTypes());
bindFilterGroup('statusFilters', calendarState.selectedStatuses, () => allStatuses());

loadCalendar().catch((error) => {
  $('calendarIntro').textContent = error instanceof Error ? error.message : '캘린더를 불러오지 못했다.';
  $('overviewHeadline').textContent = '일정을 불러오지 못했다.';
  $('overviewFocus').textContent = '잠시 후 다시 시도해 달라.';
});
