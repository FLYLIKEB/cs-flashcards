(function () {
  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function columnKeys(columns) {
    return Array.isArray(columns)
      ? columns.map((column) => String(column?.key || '')).filter(Boolean)
      : [];
  }

  function readColumnOrder(storageKey, fallbackKeys) {
    const fallback = Array.isArray(fallbackKeys) ? [...fallbackKeys] : [];
    if (!storageKey) return fallback;
    try {
      const saved = JSON.parse(window.localStorage.getItem(storageKey) || '[]');
      if (!Array.isArray(saved)) return fallback;
      const filtered = saved.filter((key, index) => fallback.includes(key) && saved.indexOf(key) === index);
      return [...filtered, ...fallback.filter((key) => !filtered.includes(key))];
    } catch (_error) {
      return fallback;
    }
  }

  function saveColumnOrder(storageKey, order) {
    if (!storageKey) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(Array.isArray(order) ? order : []));
    } catch (_error) {}
  }

  function moveColumnOrder(storageKey, fallbackKeys, sourceKey, targetKey) {
    const validKeys = columnKeys((fallbackKeys || []).map((key) => ({key})));
    if (!validKeys.includes(sourceKey) || !validKeys.includes(targetKey) || sourceKey === targetKey) return validKeys;
    const order = readColumnOrder(storageKey, validKeys);
    const fromIndex = order.indexOf(sourceKey);
    const toIndex = order.indexOf(targetKey);
    if (fromIndex < 0 || toIndex < 0) return order;
    order.splice(toIndex, 0, ...order.splice(fromIndex, 1));
    saveColumnOrder(storageKey, order);
    return order;
  }

  function orderedColumns(columns, storageKey) {
    const byKey = new Map((columns || []).map((column) => [String(column.key || ''), column]));
    return readColumnOrder(storageKey, columnKeys(columns)).map((key) => byKey.get(key)).filter(Boolean);
  }

  function tableMarkup(options) {
    const columns = orderedColumns(options.columns || [], options.storageKey || '');
    const rows = Array.isArray(options.rows) ? options.rows : [];
    if (!rows.length) {
      return `<p class="cs-table-empty">${escapeHtml(options.emptyText || '조건에 맞는 항목이 없습니다.')}</p>`;
    }
    const headerHtml = columns.map((column) => {
      const widthAttr = column.width ? ` style="width:${escapeHtml(column.width)}"` : '';
      const classes = ['column-header'];
      if (column.headerClassName) classes.push(column.headerClassName);
      return `<th scope="col" class="${escapeHtml(classes.join(' '))}"${widthAttr} draggable="true" data-column-key="${escapeHtml(column.key)}" title="드래그해서 열 위치 변경">${escapeHtml(column.label || column.key)}</th>`;
    }).join('');
    const rowHtml = rows.map((row, index) => {
      const classes = [];
      if (row.className) classes.push(row.className);
      const attributes = [
        `data-table-row-id="${escapeHtml(row.id || String(index + 1))}"`,
        `data-table-row-index="${index}"`,
        'tabindex="0"',
      ];
      Object.entries(row.attributes || {}).forEach(([key, value]) => {
        if (!key) return;
        attributes.push(`${escapeHtml(key)}="${escapeHtml(value)}"`);
      });
      return `<tr class="${escapeHtml(classes.join(' '))}" ${attributes.join(' ')}>${columns.map((column) => {
        const cellClasses = [];
        if (column.cellClassName) cellClasses.push(column.cellClassName);
        const value = row.cells && Object.prototype.hasOwnProperty.call(row.cells, column.key) ? row.cells[column.key] : '—';
        return `<td${cellClasses.length ? ` class="${escapeHtml(cellClasses.join(' '))}"` : ''}>${value}</td>`;
      }).join('')}</tr>`;
    }).join('');
    const minWidth = escapeHtml(options.tableMinWidth || '960px');
    return `<div class="cs-table-wrap"><table class="cs-table" style="min-width:${minWidth}"><thead><tr>${headerHtml}</tr></thead><tbody>${rowHtml}</tbody></table></div>`;
  }

  function bindInteractions(mount, options) {
    if (mount.__csTableAbortController) mount.__csTableAbortController.abort();
    const controller = new window.AbortController();
    mount.__csTableAbortController = controller;
    const signal = controller.signal;
    const rowSelector = '[data-table-row-id]';
    mount.addEventListener('click', (event) => {
      if (typeof options.onAction === 'function' && options.onAction(event) === true) return;
      if (event.target.closest('button,a,input,select,textarea,label')) return;
      const row = event.target.closest(rowSelector);
      if (!row) return;
      const index = Number.parseInt(row.dataset.tableRowIndex || '', 10);
      if (!Number.isInteger(index)) return;
      options.onRowActivate?.(options.rows[index], index, event);
    }, {signal});
    mount.addEventListener('keydown', (event) => {
      if (event.target.closest('button,a,input,select,textarea,label')) return;
      const row = event.target.closest(rowSelector);
      if (!row || (event.key !== 'Enter' && event.key !== ' ')) return;
      event.preventDefault();
      const index = Number.parseInt(row.dataset.tableRowIndex || '', 10);
      if (!Number.isInteger(index)) return;
      options.onRowActivate?.(options.rows[index], index, event);
    }, {signal});
    const headers = [...mount.querySelectorAll('[data-column-key]')];
    let draggingColumnKey = '';
    headers.forEach((header) => {
      header.addEventListener('dragstart', (event) => {
        draggingColumnKey = header.dataset.columnKey || '';
        header.classList.add('dragging');
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData('text/plain', draggingColumnKey);
        }
      }, {signal});
      header.addEventListener('dragover', (event) => {
        const targetKey = header.dataset.columnKey || '';
        if (!draggingColumnKey || !targetKey || draggingColumnKey === targetKey) return;
        event.preventDefault();
        header.classList.add('drop-target');
        if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
      }, {signal});
      header.addEventListener('dragleave', () => {
        header.classList.remove('drop-target');
      }, {signal});
      header.addEventListener('drop', (event) => {
        event.preventDefault();
        header.classList.remove('drop-target');
        const targetKey = header.dataset.columnKey || '';
        if (!draggingColumnKey || !targetKey || draggingColumnKey === targetKey) return;
        if (typeof options.onColumnMove === 'function') {
          options.onColumnMove(draggingColumnKey, targetKey);
          return;
        }
        if (options.storageKey) {
          moveColumnOrder(options.storageKey, columnKeys(options.columns || []), draggingColumnKey, targetKey);
          renderTable(mount, options);
        }
      }, {signal});
      header.addEventListener('dragend', () => {
        draggingColumnKey = '';
        headers.forEach((item) => item.classList.remove('dragging', 'drop-target'));
      }, {signal});
    });
  }

  function renderTable(mount, options) {
    if (!mount) return;
    mount.innerHTML = tableMarkup(options);
    bindInteractions(mount, options);
  }

  window.CSTableShell = {
    escapeHtml,
    readColumnOrder,
    saveColumnOrder,
    moveColumnOrder,
    renderTable,
  };
}());
