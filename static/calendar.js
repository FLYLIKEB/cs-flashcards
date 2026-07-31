const CALENDAR_API_PATH = '/api/calendar/recruitment';
const COMPACT_CALENDAR_MEDIA = '(max-width: 760px)';
const EMPTY_SELECTION_TEXT = '달력이나 목록에서 일정을 누르면 상세와 공고 링크를 보여준다.';
const CALENDAR_SIDEBAR_STATE_KEY = 'csFlashcardsCalendarSidebar:v1';

const calendarState = {
  payload: null,
  calendar: null,
  selectedInstitutions: new Set(),
  selectedEventTypes: new Set(),
  selectedStatuses: new Set(),
  hideApproximate: false,
  selectedEventId: '',
  sidebarOpen: true,
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
  return window.matchMedia ? window.matchMedia('(min-width: 981px)').matches : window.innerWidth > 980;
}

function readSavedCalendarSidebarState() {
  try {
    const saved = window.localStorage.getItem(CALENDAR_SIDEBAR_STATE_KEY);
    if (saved === 'open') return true;
    if (saved === 'closed') return false;
  } catch (_error) {
    // Ignore storage failures and use the viewport default.
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

function applyCalendarSidebarState({persist = true} = {}) {
  document.body.classList.toggle('calendar-sidebar-collapsed', !calendarState.sidebarOpen);
  $('calendarSidebar')?.setAttribute('aria-hidden', String(!calendarState.sidebarOpen));
  const toggleBtn = $('calendarSidebarToggleBtn');
  if (toggleBtn) {
    toggleBtn.setAttribute('aria-expanded', String(calendarState.sidebarOpen));
    toggleBtn.setAttribute('aria-label', calendarState.sidebarOpen ? '사이드바 숨기기' : '사이드바 보기');
    toggleBtn.setAttribute('title', calendarState.sidebarOpen ? '사이드바 숨기기' : '사이드바 보기');
  }
  if (persist) saveCalendarSidebarState();
}

function toggleCalendarSidebar(force = !calendarState.sidebarOpen) {
  calendarState.sidebarOpen = Boolean(force);
  applyCalendarSidebarState();
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


function nextUpcomingEvent(events, { exactOnly = false } = {}) {
  const now = Date.now();
  const sorted = sortEventsByStart(events).filter((event) => !exactOnly || !event.is_approximate);
  return sorted.find((event) => eventTimestamp(event, 'end') >= now) || sorted[0] || null;
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

  const cards = [
    {
      label: '현재 보이는 일정',
      value: `${events.length}건`,
      note: calendarState.hideApproximate ? '예정 월/전후 숨김 적용' : '필터 기준으로 계산',
    },
    {
      label: '진행 중',
      value: `${openEvents.length}건`,
      note: openEvents[0] ? openEvents[0].date_display : '열린 접수 일정 없음',
    },
    {
      label: '다음 확정 일정',
      value: nextExactEvent ? nextExactEvent.display_label : '대기 중',
      note: nextExactEvent ? `${nextExactEvent.institution.short_name} · ${nextExactEvent.date_display}` : '확정 일정이 더 필요함',
    },
    {
      label: '체크 대기 기관',
      value: `${payload.dashboard.watch.length}곳`,
      note: topPriority ? `${priorityLabel(topPriority)}부터 확인` : '링크만 짧게 확인',
    },
  ];

  $('overviewHighlights').innerHTML = cards.map((item) => `
    <article class="overview-card">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
      <p>${escapeHtml(item.note)}</p>
    </article>
  `).join('');
}

function renderTimeline() {
  const container = $('timelineHighlights');
  const timeline = calendarState.payload?.timeline || [];
  if (!container) return;
  if (!timeline.length) {
    container.innerHTML = '<p class="event-detail-empty">표시할 타임라인이 없다.</p>';
    return;
  }
  container.innerHTML = timeline.map((item) => `
    <article class="timeline-card">
      <p class="timeline-period">${escapeHtml(item.period || '')}</p>
      <h3>${escapeHtml(item.headline || '')}</h3>
      <p>${escapeHtml(item.focus || '')}</p>
    </article>
  `).join('');
}

function renderPriorityList() {
  const container = $('priorityList');
  const priorities = calendarState.payload?.dashboard?.priorities || calendarState.payload?.priorities || [];
  if (!container) return;
  if (!priorities.length) {
    container.innerHTML = '<p class="event-detail-empty">표시할 우선순위가 없다.</p>';
    return;
  }
  container.innerHTML = priorities.map((item) => `
    <article class="priority-item">
      <div class="priority-rank">${escapeHtml(item.rank)}</div>
      <div class="priority-body">
        <span class="priority-rank-label">우선순위 ${escapeHtml(item.rank)}</span>
        <h3>${escapeHtml(priorityLabel(item))}</h3>
        <p>${escapeHtml(item.reason || '')}</p>
      </div>
    </article>
  `).join('');
}

function renderCounts() {
  const counts = calendarState.payload?.counts;
  const container = $('calendarCounts');
  if (!counts || !container) return;
  const items = [
    ['전체 일정', counts.total_events, '공고 + 예비공고 + 연간 계획', ''],
    ['진행 중', counts.open_events, '지금 바로 대응 가능한 일정', 'open'],
    ['확정 날짜', counts.exact_events, '일 단위가 확정된 일정', ''],
    ['예정/관측', counts.planned_events, '월 단위·전후 일정 포함', 'planned'],
    ['체크 대기 기관', counts.watch_only_institutions, '짧게 확인만 해도 되는 곳', 'watch'],
  ];
  container.innerHTML = items.map(([label, value, note, tone]) => `
    <div class="metric-card${tone ? ` metric-card--${tone}` : ''}">
      <dt>${escapeHtml(label)}</dt>
      <dd><strong>${escapeHtml(value)}</strong></dd>
      <p>${escapeHtml(note)}</p>
    </div>
  `).join('');
}

function renderDashboardList(containerId, items, emptyText) {
  const container = $(containerId);
  if (!container) return;
  if (!items.length) {
    container.innerHTML = `<p class="event-detail-empty">${escapeHtml(emptyText)}</p>`;
    return;
  }
  container.innerHTML = items.map((item) => `
    <article class="dashboard-card">
      <div class="event-card__top">
        <h4>${escapeHtml(item.institution.name)}</h4>
        <span class="event-badge">${escapeHtml(item.status)}</span>
      </div>
      <p>${escapeHtml(item.schedule_summary || item.note || '')}</p>
      <div class="dashboard-links">
        ${(item.links || []).map((link) => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)}</a>`).join('')}
      </div>
      ${item.note ? `<p class="event-source">${escapeHtml(item.note)}</p>` : ''}
    </article>
  `).join('');
}

function syncSelectedEventCard() {
  $('eventList')?.querySelectorAll('[data-event-id]').forEach((element) => {
    element.classList.toggle('is-selected', element.dataset.eventId === calendarState.selectedEventId);
  });
}

function renderEventList(events = filteredEvents()) {
  const container = $('eventList');
  const count = $('eventListCount');
  if (count) count.textContent = `${events.length}건`;
  if (!container) return;
  if (!events.length) {
    container.innerHTML = '<p class="event-detail-empty">현재 필터에 맞는 일정이 없다.</p>';
    return;
  }
  container.innerHTML = events.map((event) => `
    <button class="event-card${event.id === calendarState.selectedEventId ? ' is-selected' : ''}" type="button" data-event-id="${escapeHtml(event.id)}">
      <div class="event-card__top">
        <span class="institution-pill">${escapeHtml(event.institution.short_name)}</span>
        <span class="event-badge">${escapeHtml(event.status_label)}</span>
      </div>
      <h3>${escapeHtml(event.list_title || event.title)}</h3>
      <p class="event-card__summary">${escapeHtml(event.summary || event.description || event.display_label || '')}</p>
      <div class="event-badges">
        <span class="event-badge">${escapeHtml(event.date_display)}</span>
        <span class="event-badge">${escapeHtml(event.event_type_label)}</span>
        ${event.is_approximate ? '<span class="event-badge">예정</span>' : ''}
      </div>
    </button>
  `).join('');

  container.querySelectorAll('[data-event-id]').forEach((element) => {
    element.addEventListener('click', () => selectEvent(element.dataset.eventId || '', {revealSidebar: true}));
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
  badge.style.background = '';
  badge.style.color = '';

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

function selectEvent(eventId, {revealSidebar = false} = {}) {
  calendarState.selectedEventId = eventId;
  const event = filteredEvents().find((item) => item.id === eventId) || null;
  if (event && revealSidebar && !calendarState.sidebarOpen) {
    toggleCalendarSidebar(true);
  }
  renderSelectedEvent(event);
  syncSelectedEventCard();
}


function rerenderCalendar() {
  const events = filteredEvents();
  if (calendarState.calendar) {
    calendarState.calendar.removeAllEvents();
    calendarState.calendar.addEventSource(events);
  }
  renderOverview(events);
  renderEventList(events);
  const nextSelected = events.find((item) => item.id === calendarState.selectedEventId) || events[0] || null;
  selectEvent(nextSelected?.id || '');
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
}

function applyResponsiveCalendarView(force = false) {
  if (!calendarState.calendar) return;
  const targetView = preferredCalendarView();
  if (force || calendarState.calendar.view.type !== targetView) {
    calendarState.calendar.changeView(targetView);
  }
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
      selectEvent(info.event.id, {revealSidebar: true});
    },
    eventDidMount(info) {
      applyCalendarEventTone(info);
    },

  });
  calendarState.calendar.render();
  applyResponsiveCalendarView(true);
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
  uniqueValues(payload.events, 'event_type').forEach((item) => calendarState.selectedEventTypes.add(item));
  uniqueValues(payload.events, 'status').forEach((item) => calendarState.selectedStatuses.add(item));

  $('calendarUpdatedAt').textContent = `마지막 업데이트 ${payload.calendar.last_updated} · 총 ${payload.counts.total_events}개 일정`;
  $('calendarIntro').textContent = payload.calendar.intro || payload.calendar.description || '';
  $('icsFeedLink').href = payload.calendar.ics_url;
  $('icsSubscribeLink').href = payload.calendar.ics_url;
  const notes = $('calendarNotes');
  if (notes) {
    notes.innerHTML = (payload.calendar.notes || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  }

  renderTimeline();
  renderPriorityList();
  renderCounts();
  renderDashboardList('dashboardOpen', payload.dashboard.open, '현재 공개된 일정이 없다.');
  renderDashboardList('dashboardWatch', payload.dashboard.watch, '미확인 기관이 없다.');
  initializeFilterChips();
  initializeCalendar();
  rerenderCalendar();
}

calendarState.sidebarOpen = readSavedCalendarSidebarState();
applyCalendarSidebarState({persist: false});

$('calendarSidebarToggleBtn')?.addEventListener('click', () => toggleCalendarSidebar());
$('copyIcsLinkBtn')?.addEventListener('click', copyIcsLink);
$('hideApproximateToggle')?.addEventListener('change', (event) => {
  calendarState.hideApproximate = Boolean(event.target.checked);
  rerenderCalendar();
});
window.matchMedia?.(COMPACT_CALENDAR_MEDIA).addEventListener?.('change', () => applyResponsiveCalendarView());
bindFilterGroup('institutionFilters', calendarState.selectedInstitutions, () => (calendarState.payload?.institutions || []).map((item) => item.id));
bindFilterGroup('eventTypeFilters', calendarState.selectedEventTypes, () => uniqueValues(calendarState.payload?.events || [], 'event_type'));
bindFilterGroup('statusFilters', calendarState.selectedStatuses, () => uniqueValues(calendarState.payload?.events || [], 'status'));

loadCalendar().catch((error) => {
  $('calendarIntro').textContent = error instanceof Error ? error.message : '캘린더를 불러오지 못했다.';
  $('overviewHeadline').textContent = '일정을 불러오지 못했다.';
  $('overviewFocus').textContent = '잠시 후 다시 시도해 달라.';
});
