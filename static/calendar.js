const CALENDAR_API_PATH = '/api/calendar/recruitment';
const COMPACT_CALENDAR_MEDIA = '(max-width: 760px)';
const EMPTY_SELECTION_TEXT = '달력이나 목록에서 일정을 누르면 상세와 공고 링크를 보여준다.';

const MAIN_TABS = new Set(['calendar', 'list', 'filters', 'institutions']);

const calendarState = {
  payload: null,
  calendar: null,
  activeTab: 'calendar',
  selectedInstitutions: new Set(),
  selectedEventTypes: new Set(),
  selectedStatuses: new Set(),
  hideApproximate: false,
  selectedEventId: '',
  selectedDateKey: '',
  eventListMode: 'all',
  detailOpen: false,
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

function setMainTab(tabId) {
  if (!MAIN_TABS.has(tabId)) return;
  calendarState.activeTab = tabId;
  closeDetailDrawer();
  applyMainTabState();
  if (tabId === 'list') {
    renderEventList();
  }
}


function applyMainTabState() {
  document.querySelectorAll('[data-main-tab]').forEach((button) => {
    const active = button.dataset.mainTab === calendarState.activeTab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-main-panel]').forEach((panel) => {
    const active = panel.dataset.mainPanel === calendarState.activeTab;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
}

function syncBackdrop() {
  $('calendarDrawerBackdrop').hidden = !calendarState.detailOpen;
  document.body.classList.toggle('calendar-overlay-open', calendarState.detailOpen);
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

function eventDateKey(event) {
  return String(event?.start_inclusive || event?.start || '').slice(0, 10);
}

function nextUpcomingEvent(events, { exactOnly = false } = {}) {
  const now = Date.now();
  const sorted = sortEventsByStart(events).filter((event) => !exactOnly || !event.is_approximate);
  return sorted.find((event) => eventTimestamp(event, 'end') >= now) || sorted[0] || null;
}

function urgentDeadlineEvent(events) {
  const now = Date.now();
  const openEvents = sortEventsByStart(events)
    .filter((event) => event.status === 'open' && eventTimestamp(event, 'end') >= now)
    .sort((left, right) => eventTimestamp(left, 'end') - eventTimestamp(right, 'end'));
  return openEvents[0] || null;
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

function allInstitutions() {
  return (calendarState.payload?.institutions || []).map((item) => item.id);
}

function allEventTypes() {
  return uniqueValues(calendarState.payload?.events || [], 'event_type');
}

function allStatuses() {
  return uniqueValues(calendarState.payload?.events || [], 'status');
}

function matchesFilters(event) {
  if (calendarState.selectedInstitutions.size !== allInstitutions().length && !calendarState.selectedInstitutions.has(event.institution.id)) return false;
  if (calendarState.selectedEventTypes.size !== allEventTypes().length && !calendarState.selectedEventTypes.has(event.event_type)) return false;
  if (calendarState.selectedStatuses.size !== allStatuses().length && !calendarState.selectedStatuses.has(event.status)) return false;
  if (calendarState.hideApproximate && event.is_approximate) return false;
  return true;
}


function filteredEvents() {
  return sortEventsByStart((calendarState.payload?.events || []).filter(matchesFilters));
}

function renderFilterOptions(containerId, items, selectedSet, key, labelKey, metaKey = '') {
  const container = $(containerId);
  if (!container) return;
  container.innerHTML = items.map((item) => {
    const value = item[key];
    const checked = selectedSet.has(value);
    const label = String(item[labelKey] || '').trim();
    const meta = metaKey ? String(item[metaKey] || '').trim() : '';
    const showMeta = meta && meta !== label;
    return `
      <label class="filter-option">
        <input type="checkbox" data-filter-value="${escapeHtml(value)}" aria-label="${escapeHtml(label)}" ${checked ? 'checked' : ''} />
        <span>
          <span class="filter-option__label">${escapeHtml(label)}</span>
          ${showMeta ? `<span class="filter-option__meta">${escapeHtml(meta)}</span>` : ''}
        </span>
      </label>
    `;
  }).join('');
}

function resetFilterGroup(group) {
  if (group === 'institution') {
    calendarState.selectedInstitutions = new Set(allInstitutions());
  } else if (group === 'eventType') {
    calendarState.selectedEventTypes = new Set(allEventTypes());
  } else if (group === 'status') {
    calendarState.selectedStatuses = new Set(allStatuses());
  }
  initializeFilterOptions();
  rerenderCalendar();
}

function resetFilters() {
  calendarState.selectedInstitutions = new Set(allInstitutions());
  calendarState.selectedEventTypes = new Set(allEventTypes());
  calendarState.selectedStatuses = new Set(allStatuses());
  calendarState.hideApproximate = false;
  if ($('hideApproximateToggle')) $('hideApproximateToggle').checked = false;
  initializeFilterOptions();
  rerenderCalendar();
}

function renderSummaryBar(events = filteredEvents()) {
  const payload = calendarState.payload;
  if (!payload) return;
  const openEvents = events.filter((event) => event.status === 'open');
  const deadlineEvent = urgentDeadlineEvent(events);
  const topPriority = (payload.dashboard?.priorities || payload.priorities || [])[0] || null;

  $('summaryOpenCount').textContent = `${openEvents.length}건`;
  $('summaryOpenMeta').textContent = openEvents[0] ? `${openEvents[0].institution.short_name} 포함` : '진행 중 일정 없음';

  if (deadlineEvent) {
    $('summaryDeadlineTitle').textContent = `${deadlineEvent.institution.short_name} ${deadlineEvent.display_label}`;
    $('summaryDeadlineMeta').textContent = deadlineEvent.date_display;
  } else {
    $('summaryDeadlineTitle').textContent = '마감 임박 일정 없음';
    $('summaryDeadlineMeta').textContent = '열린 일정이 없거나 모두 종료 직전 아님';
  }

  if (topPriority) {
    $('summaryNextTitle').textContent = priorityLabel(topPriority);
    $('summaryNextMeta').textContent = topPriority.reason || '우선 확인 대상';
  } else {
    $('summaryNextTitle').textContent = '우선 기관 없음';
    $('summaryNextMeta').textContent = '지금 바로 체크할 기관이 없다.';
  }

  const tagCount = [
    calendarState.selectedInstitutions.size !== allInstitutions().length,
    calendarState.selectedEventTypes.size !== allEventTypes().length,
    calendarState.selectedStatuses.size !== allStatuses().length,
    calendarState.hideApproximate,
  ].filter(Boolean).length;
  $('summaryFilterState').textContent = tagCount ? `${tagCount}개 적용` : '전체';
  $('summaryFilterMeta').textContent = `${events.length}건 표시`;
}

function renderOverview(events = filteredEvents()) {
  const payload = calendarState.payload;
  if (!payload) return;
  const openEvents = events.filter((event) => event.status === 'open');
  const nextExactEvent = nextUpcomingEvent(events, { exactOnly: true });
  const topPriority = (payload.dashboard?.priorities || payload.priorities || [])[0] || null;
  const deadlineEvent = urgentDeadlineEvent(events);

  if (deadlineEvent) {
    $('overviewHeadline').textContent = `${deadlineEvent.institution.name} ${deadlineEvent.display_label}`;
    $('overviewFocus').textContent = `${deadlineEvent.date_display} · 마감 전에 공고 확인과 지원 상태 점검이 필요하다.`;
  } else if (nextExactEvent) {
    $('overviewHeadline').textContent = `${nextExactEvent.institution.name} ${nextExactEvent.display_label}`;
    $('overviewFocus').textContent = `${nextExactEvent.date_display} · ${nextExactEvent.summary || nextExactEvent.description || '다음 확정 일정'}`;
  } else {
    $('overviewHeadline').textContent = '지금 대응할 핵심 일정부터 본다.';
    $('overviewFocus').textContent = topPriority ? `${priorityLabel(topPriority)} 우선 · ${topPriority.reason}` : payload.calendar.description || '';
  }

  const rows = [
    ['보이는 일정', `${events.length}건`, calendarState.hideApproximate ? '예정 숨김 적용' : '현재 필터 기준'],
    ['진행 중', `${openEvents.length}건`, openEvents[0] ? openEvents[0].date_display : '열린 일정 없음'],
    ['다음 확정', nextExactEvent ? nextExactEvent.display_label : '대기 중', nextExactEvent ? `${nextExactEvent.institution.short_name} · ${nextExactEvent.date_display}` : '확정 일정 대기'],
    ['1순위', topPriority ? priorityLabel(topPriority) : '없음', topPriority ? topPriority.reason : '우선순위 정보 없음'],
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
    <div class="timeline-list">
      ${timeline.map((item) => `
        <article class="timeline-item">
          <span class="timeline-item__period">${escapeHtml(item.period || '')}</span>
          <div class="timeline-item__content">
            <strong>${escapeHtml(item.headline || '')}</strong>
            <span class="table-note">${escapeHtml(item.focus || '')}</span>
          </div>
        </article>
      `).join('')}
    </div>
  `;
}

function renderCounts() {
  const counts = calendarState.payload?.counts;
  const container = $('calendarCounts');
  if (!counts || !container) return;
  const items = [
    ['전체 일정', counts.total_events, '공고 + 예비공고 + 연간 계획'],
    ['진행 중', counts.open_events, '지금 바로 대응 가능'],
    ['확정 날짜', counts.exact_events, '일 단위가 확정된 일정'],
    ['예정/관측', counts.planned_events, '월 단위·전후 일정 포함'],
    ['체크 대기', counts.watch_only_institutions, '짧게 확인할 기관'],
  ];
  container.innerHTML = `
    <div class="stat-grid">
      ${items.map(([label, value, note]) => `
        <article class="stat-card">
          <span class="stat-card__label">${escapeHtml(label)}</span>
          <strong class="stat-card__value">${escapeHtml(value)}</strong>
          <span class="stat-card__meta">${escapeHtml(note)}</span>
        </article>
      `).join('')}
    </div>
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
    <ol class="priority-cards">
      ${priorities.map((item) => `
        <li class="priority-card">
          <span class="priority-card__rank">${escapeHtml(item.rank)}</span>
          <div class="priority-card__body">
            <strong>${escapeHtml(priorityLabel(item))}</strong>
            <span class="table-note">${escapeHtml(item.reason || '')}</span>
          </div>
        </li>
      `).join('')}
    </ol>
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
    <div class="institution-cards">
      ${items.map((item) => `
        <article class="institution-card">
          <div class="institution-card__head">
            <strong>${escapeHtml(item.institution.short_name || item.institution.name)}</strong>
            <span class="institution-card__status">${escapeHtml(item.status)}</span>
          </div>
          <p class="institution-card__summary">${escapeHtml(item.schedule_summary || item.note || '')}</p>
          ${item.note && item.schedule_summary ? `<span class="table-note">${escapeHtml(item.note)}</span>` : ''}
          ${(item.links || []).length ? `<span class="table-links">${(item.links || []).map((link) => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)}</a>`).join('')}</span>` : ''}
        </article>
      `).join('')}
    </div>
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
    <div class="event-row-list">
      ${listEvents.map((event) => `
        <button class="event-row-button${event.id === calendarState.selectedEventId ? ' is-selected' : ''}" type="button" data-event-id="${escapeHtml(event.id)}">
          <span class="event-row-button__date">${escapeHtml(event.date_display)}</span>
          <span class="event-row-button__content">
            <strong>${escapeHtml(event.list_title || event.title)}</strong>
            <span class="table-note">${escapeHtml(event.institution.short_name)} · ${escapeHtml(event.event_type_label)}${event.summary ? ` · ${escapeHtml(event.summary)}` : ''}</span>
          </span>
          <span class="event-row-button__status">${escapeHtml(event.status_label)}${event.is_approximate ? ' · 예정' : ''}</span>
        </button>
      `).join('')}
    </div>
  `;

  container.querySelectorAll('[data-event-id]').forEach((element) => {
    element.addEventListener('click', () => selectEvent(element.dataset.eventId || '', { openDetail: true }));
  });
}

function renderSelectedEventPeek(event) {
  const peek = $('selectedEventPeek');
  const openButton = $('selectedEventOpenBtn');
  if (!peek) return;
  if (openButton) openButton.disabled = !event;
  if (!event) {
    peek.className = 'selected-event-peek event-detail-empty';
    peek.textContent = '달력이나 목록에서 일정을 누르면 핵심 정보와 바로가기 링크를 보여준다.';
    return;
  }
  peek.className = 'selected-event-peek';
  peek.innerHTML = `
    <div class="selected-event-peek__head">
      <span class="event-pill">${escapeHtml(event.institution.short_name)}</span>
      <strong class="selected-event-peek__title">${escapeHtml(event.list_title || event.title)}</strong>
    </div>
    <div class="selected-event-peek__facts">
      <span>${escapeHtml(event.date_display)}</span>
      <span>${escapeHtml(event.event_type_label)}</span>
      <span>${escapeHtml(event.status_label)}${event.is_approximate ? ' · 예정' : ''}</span>
    </div>
    <p class="selected-event-peek__summary">${escapeHtml(event.summary || event.description || '공고 핵심 내용을 바로 확인한다.')}</p>
    <div class="event-actions">
      ${event.url ? `<a class="primary-link" href="${escapeHtml(event.url)}" target="_blank" rel="noopener noreferrer">공고 열기</a>` : ''}
      <a href="${escapeHtml(event.google_calendar_url)}" target="_blank" rel="noopener noreferrer">Google Calendar에 추가</a>
    </div>
  `;
}

function renderSelectedEvent(event) {
  const detail = $('selectedEventDetail');
  const badge = $('selectedEventBadge');
  if (!detail || !badge) return;
  renderSelectedEventPeek(event);
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

function renderActiveFilterSummary(events = filteredEvents()) {
  const tags = [];
  if (calendarState.selectedInstitutions.size !== allInstitutions().length) tags.push(`기관 ${calendarState.selectedInstitutions.size}개`);
  if (calendarState.selectedEventTypes.size !== allEventTypes().length) tags.push(`유형 ${calendarState.selectedEventTypes.size}개`);
  if (calendarState.selectedStatuses.size !== allStatuses().length) tags.push(`상태 ${calendarState.selectedStatuses.size}개`);
  if (calendarState.hideApproximate) tags.push('예정 숨김');
  $('activeFilterSummary').textContent = tags.length ? `필터 적용 중 · ${events.length}건 표시` : '전체 보기';
  $('activeFilterTags').innerHTML = (tags.length ? tags : ['전체']).map((label) => `<span class="filter-tag">${escapeHtml(label)}</span>`).join('');
  $('filterResultCount').textContent = `${events.length}건 표시`;
}

function bindFilterGroup(containerId, getSelectedSet) {
  $(containerId)?.addEventListener('change', () => {
    const selectedSet = getSelectedSet();
    selectedSet.clear();
    $(containerId).querySelectorAll('input[data-filter-value]:checked').forEach((checkbox) => {
      selectedSet.add(checkbox.dataset.filterValue || '');
    });
    rerenderCalendar();
  });
}


function initializeFilterOptions() {
  const payload = calendarState.payload;
  if (!payload) return;
  renderFilterOptions('institutionFilters', payload.institutions, calendarState.selectedInstitutions, 'id', 'short_name', 'name');
  renderFilterOptions(
    'eventTypeFilters',
    uniqueValues(payload.events, 'event_type').map((eventType) => ({ event_type: eventType, event_type_label: payload.events.find((item) => item.event_type === eventType)?.event_type_label || eventType })),
    calendarState.selectedEventTypes,
    'event_type',
    'event_type_label',
  );
  renderFilterOptions(
    'statusFilters',
    uniqueValues(payload.events, 'status').map((status) => ({ status, status_label: payload.events.find((item) => item.status === status)?.status_label || status })),
    calendarState.selectedStatuses,
    'status',
    'status_label',
  );
  renderActiveFilterSummary(filteredEvents());
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

function rerenderCalendar() {
  const events = filteredEvents();
  if (calendarState.calendar) {
    calendarState.calendar.removeAllEvents();
    calendarState.calendar.addEventSource(events);
  }
  renderActiveFilterSummary(events);
  renderSummaryBar(events);
  renderOverview(events);
  renderTimeline();
  renderCounts();
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

  calendarState.selectedInstitutions = new Set(allInstitutions());
  calendarState.selectedEventTypes = new Set(allEventTypes());
  calendarState.selectedStatuses = new Set(allStatuses());

  $('calendarUpdatedAt').textContent = `마지막 업데이트 ${payload.calendar.last_updated} · 총 ${payload.counts.total_events}개 일정`;
  $('calendarIntro').textContent = payload.calendar.intro || payload.calendar.description || '';
  $('icsFeedLink').href = payload.calendar.ics_url;
  $('icsSubscribeLink').href = payload.calendar.ics_url;
  const notes = $('calendarNotes');
  if (notes) {
    notes.innerHTML = (payload.calendar.notes || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('');
  }

  initializeFilterOptions();
  initializeCalendar();
  rerenderCalendar();
  applyMainTabState();
}

document.querySelectorAll('[data-main-tab]').forEach((button) => {
  button.addEventListener('click', () => setMainTab(button.dataset.mainTab || 'calendar'));
});
$('summaryDeadlineBtn')?.addEventListener('click', () => {
  const event = urgentDeadlineEvent(filteredEvents());
  if (event) selectEvent(event.id, { openDetail: true });
});
$('summaryOpenBtn')?.addEventListener('click', () => {
  calendarState.selectedStatuses = new Set(['open']);
  initializeFilterOptions();
  calendarState.eventListMode = 'all';
  setMainTab('list');
  rerenderCalendar();
});
$('summaryNextBtn')?.addEventListener('click', () => setMainTab('institutions'));
$('summaryFilterBtn')?.addEventListener('click', () => setMainTab('filters'));
$('selectedEventOpenBtn')?.addEventListener('click', () => {
  if (calendarState.selectedEventId) {
    selectEvent(calendarState.selectedEventId, { openDetail: true });
  }
});
$('calendarDetailCloseBtn')?.addEventListener('click', closeDetailDrawer);
$('calendarDrawerBackdrop')?.addEventListener('click', closeDetailDrawer);
$('copyIcsLinkBtn')?.addEventListener('click', copyIcsLink);
$('resetFiltersBtn')?.addEventListener('click', resetFilters);
$('resetInstitutionFiltersBtn')?.addEventListener('click', () => resetFilterGroup('institution'));
$('resetEventTypeFiltersBtn')?.addEventListener('click', () => resetFilterGroup('eventType'));
$('resetStatusFiltersBtn')?.addEventListener('click', () => resetFilterGroup('status'));
$('filterGoCalendarBtn')?.addEventListener('click', () => setMainTab('calendar'));
$('filterGoListBtn')?.addEventListener('click', () => setMainTab('list'));
$('eventListModeSelectedBtn')?.addEventListener('click', () => setEventListMode('selected'));
$('eventListModeAllBtn')?.addEventListener('click', () => setEventListMode('all'));
$('hideApproximateToggle')?.addEventListener('change', (event) => {
  calendarState.hideApproximate = Boolean(event.target.checked);
  rerenderCalendar();
});
window.matchMedia?.(COMPACT_CALENDAR_MEDIA).addEventListener?.('change', () => applyResponsiveCalendarView());
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeDetailDrawer();
  }
});
bindFilterGroup('institutionFilters', () => calendarState.selectedInstitutions);
bindFilterGroup('eventTypeFilters', () => calendarState.selectedEventTypes);
bindFilterGroup('statusFilters', () => calendarState.selectedStatuses);

loadCalendar().catch((error) => {
  $('calendarIntro').textContent = error instanceof Error ? error.message : '캘린더를 불러오지 못했다.';
  $('overviewHeadline').textContent = '일정을 불러오지 못했다.';
  $('overviewFocus').textContent = '잠시 후 다시 시도해 달라.';
});
