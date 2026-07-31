const CALENDAR_API_PATH = '/api/calendar/recruitment';

const calendarState = {
  payload: null,
  calendar: null,
  selectedInstitutions: new Set(),
  selectedEventTypes: new Set(),
  selectedStatuses: new Set(),
  hideApproximate: false,
  selectedEventId: '',
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

function matchesFilters(event) {
  if (!calendarState.selectedInstitutions.has(event.institution.id)) return false;
  if (!calendarState.selectedEventTypes.has(event.event_type)) return false;
  if (!calendarState.selectedStatuses.has(event.status)) return false;
  if (calendarState.hideApproximate && event.is_approximate) return false;
  return true;
}

function filteredEvents() {
  return (calendarState.payload?.events || []).filter(matchesFilters);
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

function renderFilterChips(containerId, items, selectedSet, key, labelKey, colorKey = '') {
  const container = $(containerId);
  if (!container) return;
  container.innerHTML = items.map((item) => {
    const value = item[key];
    const active = selectedSet.has(value);
    const style = colorKey && item[colorKey] ? ` style="border-color:${escapeHtml(item[colorKey])};${active ? `background:${escapeHtml(item[colorKey])};color:#fff;` : ''}"` : '';
    return `<button class="filter-chip${active ? ' active' : ''}" type="button" data-filter-value="${escapeHtml(value)}"${style}>${escapeHtml(item[labelKey])}</button>`;
  }).join('');
}

function renderCounts() {
  const counts = calendarState.payload?.counts;
  const container = $('calendarCounts');
  if (!counts || !container) return;
  const items = [
    ['전체 일정', counts.total_events],
    ['진행 중', counts.open_events],
    ['정확한 날짜', counts.exact_events],
    ['미확인 기관', counts.watch_only_institutions],
  ];
  container.innerHTML = items.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('');
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
      <h4>${escapeHtml(item.institution.name)}</h4>
      <p><strong>${escapeHtml(item.status)}</strong></p>
      <p>${escapeHtml(item.schedule_summary || item.note || '')}</p>
      <div class="dashboard-links">
        ${(item.links || []).map((link) => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)}</a>`).join('')}
      </div>
      ${item.note ? `<p class="event-source">${escapeHtml(item.note)}</p>` : ''}
    </article>
  `).join('');
}

function renderEventList() {
  const events = filteredEvents();
  const container = $('eventList');
  const count = $('eventListCount');
  if (count) count.textContent = `${events.length}건`;
  if (!container) return;
  if (!events.length) {
    container.innerHTML = '<p class="event-detail-empty">현재 필터에 맞는 일정이 없다.</p>';
    return;
  }
  container.innerHTML = events.map((event) => `
    <article class="event-card" data-event-id="${escapeHtml(event.id)}">
      <h3>${escapeHtml(event.title)}</h3>
      <p>${escapeHtml(event.summary || event.description || '')}</p>
      <p class="event-meta">
        <span>${escapeHtml(event.date_display)}</span>
        <span>${escapeHtml(event.event_type_label)}</span>
        <span>${escapeHtml(event.status_label)}</span>
      </p>
    </article>
  `).join('');
  container.querySelectorAll('[data-event-id]').forEach((element) => {
    element.addEventListener('click', () => selectEvent(element.dataset.eventId || ''));
  });
}

function renderSelectedEvent(event) {
  const detail = $('selectedEventDetail');
  const badge = $('selectedEventBadge');
  if (!detail || !badge) return;
  if (!event) {
    badge.hidden = true;
    detail.className = 'event-detail-empty';
    detail.textContent = '달력이나 목록에서 일정을 누르면 상세와 공고 링크를 보여준다.';
    return;
  }
  badge.hidden = false;
  badge.textContent = event.institution.short_name;
  badge.style.background = `${event.institution.color}22`;
  badge.style.color = event.institution.color;
  detail.className = '';
  detail.innerHTML = `
    <h3>${escapeHtml(event.title)}</h3>
    <p>${escapeHtml(event.summary || '')}</p>
    <ul>
      <li>일정: ${escapeHtml(event.date_display)}</li>
      <li>유형: ${escapeHtml(event.event_type_label)}</li>
      <li>상태: ${escapeHtml(event.status_label)}</li>
      ${event.source_label ? `<li>출처: ${escapeHtml(event.source_label)}</li>` : ''}
    </ul>
    ${event.description ? `<p>${escapeHtml(event.description)}</p>` : ''}
    <div class="event-actions">
      ${event.url ? `<a class="primary-link" href="${escapeHtml(event.url)}" target="_blank" rel="noopener noreferrer">공고 열기</a>` : ''}
      <a href="${escapeHtml(event.google_calendar_url)}" target="_blank" rel="noopener noreferrer">Google Calendar에 추가</a>
    </div>
  `;
}

function selectEvent(eventId) {
  calendarState.selectedEventId = eventId;
  const event = filteredEvents().find((item) => item.id === eventId) || null;
  renderSelectedEvent(event);
}

function rerenderCalendar() {
  if (calendarState.calendar) {
    calendarState.calendar.removeAllEvents();
    calendarState.calendar.addEventSource(filteredEvents());
  }
  renderEventList();
  const nextSelected = filteredEvents().find((item) => item.id === calendarState.selectedEventId) || filteredEvents()[0] || null;
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
  renderFilterChips('institutionFilters', payload.institutions, calendarState.selectedInstitutions, 'id', 'short_name', 'color');
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

function initializeCalendar() {
  const element = $('calendar');
  if (!element || !calendarState.payload) return;
  calendarState.calendar = new window.FullCalendar.Calendar(element, {
    locale: 'ko',
    initialView: 'dayGridMonth',
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
      selectEvent(info.event.id);
    },
  });
  calendarState.calendar.render();
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

  renderCounts();
  renderDashboardList('dashboardOpen', payload.dashboard.open, '현재 공개된 일정이 없다.');
  renderDashboardList('dashboardWatch', payload.dashboard.watch, '미확인 기관이 없다.');
  initializeFilterChips();
  initializeCalendar();
  rerenderCalendar();
}

$('copyIcsLinkBtn')?.addEventListener('click', copyIcsLink);
$('hideApproximateToggle')?.addEventListener('change', (event) => {
  calendarState.hideApproximate = Boolean(event.target.checked);
  rerenderCalendar();
});
bindFilterGroup('institutionFilters', calendarState.selectedInstitutions, () => (calendarState.payload?.institutions || []).map((item) => item.id));
bindFilterGroup('eventTypeFilters', calendarState.selectedEventTypes, () => uniqueValues(calendarState.payload?.events || [], 'event_type'));
bindFilterGroup('statusFilters', calendarState.selectedStatuses, () => uniqueValues(calendarState.payload?.events || [], 'status'));

loadCalendar().catch((error) => {
  $('calendarIntro').textContent = error instanceof Error ? error.message : '캘린더를 불러오지 못했다.';
});
