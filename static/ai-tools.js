(function initCsAiTools() {
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

  window.CsAiTools = {
    postJson,
    responseErrorText,
    setButtonBusy,
    setStatus,
  };
})();
