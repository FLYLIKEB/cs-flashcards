(function initCsAiTools() {
  function cloneTemplate(template, fallback = {}, index = 0) {
    const fallbackId = fallback?.id || `template-${index + 1}`;
    return {
      id: String(template?.id || fallbackId).trim() || fallbackId,
      label: String(template?.label ?? fallback?.label ?? ''),
      instruction: String(template?.instruction ?? fallback?.instruction ?? ''),
    };
  }

  function cloneTemplates(templates, defaults = []) {
    const fallbackList = Array.isArray(defaults) ? defaults : [];
    const sourceList = Array.isArray(templates) && templates.length ? templates : fallbackList;
    return sourceList.map((template, index) => cloneTemplate(template, fallbackList[index] || {}, index));
  }

  async function responseErrorText(res) {
    const raw = await res.text();
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed?.detail === 'string' && parsed.detail.trim()) return parsed.detail.trim();
    } catch (_error) {
      // Fall back to the raw text body.
    }
    return raw || `${res.status}`;
  }

  async function postJson(url, payload, options = null) {
    const config = options || {};
    const res = await fetch(url, {
      method: config.method || 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(config.headers || {}),
      },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) throw new Error(await responseErrorText(res));
    return res.json();
  }

  function setButtonBusy(button, {
    busy = false,
    disabled = null,
    idleLabel = 'AI',
    busyLabel = '…',
    idleTitle = '',
    busyTitle = '',
    idleTip = '',
    busyTip = '',
  } = {}) {
    if (!button) return;
    button.textContent = busy ? busyLabel : idleLabel;
    if (idleTitle || busyTitle) button.title = busy ? busyTitle : idleTitle;
    if ('tip' in button.dataset && (idleTip || busyTip)) {
      button.dataset.tip = busy ? busyTip : idleTip;
    }
    if (disabled !== null) button.disabled = Boolean(disabled);
  }

  function setStatus(el, text, isError = false) {
    if (!el) return;
    el.textContent = String(text || '');
    el.classList.toggle('error-text', Boolean(isError));
  }

  function createPromptTemplateManager({storageKey = '', defaults = []} = {}) {
    const fallbackTemplates = cloneTemplates(defaults, defaults);
    let templates = fallbackTemplates.map((template) => ({...template}));

    function persist() {
      if (!storageKey) return;
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(templates));
      } catch (_error) {
        // Ignore storage failures and keep the in-memory copy.
      }
    }

    function load() {
      if (!storageKey) {
        templates = fallbackTemplates.map((template) => ({...template}));
        return;
      }
      try {
        const raw = window.localStorage.getItem(storageKey);
        if (!raw) {
          templates = fallbackTemplates.map((template) => ({...template}));
          return;
        }
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed)) {
          templates = fallbackTemplates.map((template) => ({...template}));
          return;
        }
        templates = fallbackTemplates.map((template, index) => {
          const saved = parsed.find((item) => String(item?.id || '').trim() === template.id) || parsed[index] || {};
          return cloneTemplate({...template, ...saved, id: template.id}, template, index);
        });
      } catch (_error) {
        templates = fallbackTemplates.map((template) => ({...template}));
      }
    }

    load();

    return {
      getTemplates() {
        return templates.map((template) => ({...template}));
      },
      updateTemplate(id, patch = {}) {
        const templateId = String(id || '').trim();
        templates = templates.map((template, index) => {
          if (template.id !== templateId) return {...template};
          return cloneTemplate({...template, ...patch, id: template.id}, fallbackTemplates[index] || template, index);
        });
        persist();
        return templates.map((template) => ({...template}));
      },
      resetTemplates() {
        templates = fallbackTemplates.map((template) => ({...template}));
        persist();
        return templates.map((template) => ({...template}));
      },
    };
  }

  window.CsAiTools = {
    postJson,
    responseErrorText,
    setButtonBusy,
    setStatus,
    createPromptTemplateManager,
  };
})();
