const RUN_ID = document.querySelector('meta[name="run-id"]')?.content ?? '';
const JIRA_BASE = document.querySelector('meta[name="jira-base-url"]')?.content ?? '';

function getToken() {
  return localStorage.getItem('jwt_token') ?? '';
}

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

function jiraLink(key, url) {
  const href = url || (JIRA_BASE ? `${JIRA_BASE}/browse/${key}` : '#');
  return `<a class="jira-anchor" href="${href}" target="_blank" rel="noopener">${key} ↗</a>`;
}

function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  requestAnimationFrame(() => {
    el.classList.add('toast--in');
    setTimeout(() => {
      el.classList.remove('toast--in');
      el.addEventListener('transitionend', () => el.remove(), { once: true });
    }, 3200);
  });
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function renderCard(s) {
  const hasDecision = !!s.triage_decision;
  const decisionClass = hasDecision ? ` data-decision="${s.triage_decision}"` : '';
  const isPass = s.triage_decision === 'accepted_pass';
  const isSkip = s.triage_decision === 'accepted_skip';
  const isJira = s.triage_decision === 'jira_created' || s.triage_decision === 'jira_linked';

  let metaTags = '';
  if (s.doors_number) {
    metaTags += `<span class="fcard-meta-tag fcard-meta-tag--doors" data-testid="doors-tag">DOORS ${esc(s.doors_number)}</span>`;
  }
  if (s.is_flaky) {
    metaTags += `<span class="fcard-meta-tag fcard-meta-tag--flaky" data-testid="flaky-tag">⚡ Flaky</span>`;
  }
  if (s.retry_attempt > 1) {
    metaTags += `<span class="fcard-meta-tag fcard-meta-tag--retry" data-testid="retry-tag">Retry #${s.retry_attempt}</span>`;
  }

  let decisionHtml = '';
  if (hasDecision) {
    if (isPass) {
      decisionHtml = `<div class="decision-badge decision-badge--pass" data-testid="decision-badge">✓ Pass olarak işaretlendi</div>`;
    } else if (isSkip) {
      decisionHtml = `<div class="decision-badge decision-badge--skip" data-testid="decision-badge">⊘ Skip olarak işaretlendi</div>`;
    } else if (isJira) {
      decisionHtml = `<div class="decision-badge decision-badge--jira" data-testid="decision-badge">🔗 Jira ${s.triage_decision === 'jira_created' ? 'oluşturuldu' : 'bağlandı'}</div>`;
    }
    if (s.triage_reason) {
      decisionHtml += `<div class="decision-info"><strong>Sebep:</strong> ${esc(s.triage_reason)}</div>`;
    }
    if (s.triage_actor) {
      decisionHtml += `<div class="decision-info"><strong>Karar veren:</strong> ${esc(s.triage_actor)}${s.triage_timestamp ? ' · ' + esc(s.triage_timestamp) : ''}</div>`;
    }
  }

  let jiraDisplay = '';
  if (s.jira_keys && s.jira_keys.length) {
    jiraDisplay = `<span class="jira-key-display" data-testid="jira-key-display" style="display:inline-flex;gap:6px">${s.jira_keys.map(k => jiraLink(k)).join('')}</span>`;
  }

  const stepsHtml = (s.error_message || '').trim()
    ? `<div class="error-box">
        <div class="error-box-header">
          <span class="error-box-label">Error</span>
          <button class="btn-copy" data-copy-error="${esc(s.error_message)}" data-testid="copy-error">Kopyala</button>
        </div>
        <pre class="error-text">${esc(s.error_message)}</pre>
      </div>`
    : '';

  const createDisabled = (s.triage_decision === 'jira_created' || s.triage_decision === 'accepted_pass' || s.triage_decision === 'accepted_skip') ? ' disabled' : '';
  const actionsDisabled = hasDecision ? ' disabled' : '';
  const btnDoneClass = s.triage_decision === 'jira_created' ? ' btn--done' : '';

  return `
  <div class="fcard" data-testid="failure-card"
       data-scenario-id="${esc(s.scenario_uid)}"
       ${s.doors_number ? `data-doors-number="${esc(s.doors_number)}"` : ''}
       ${decisionClass}>
    <div class="fcard-header">
      <div class="fcard-title-group">
        <div class="fcard-title card-title" data-testid="scenario-name">${esc(s.scenario_name)}</div>
        <div class="fcard-id">${esc(s.scenario_uid)}</div>
      </div>
      <span class="badge badge-fail" data-testid="failure-badge">FAILED</span>
    </div>

    ${metaTags ? `<div class="fcard-meta-row">${metaTags}</div>` : ''}

    ${decisionHtml ? `<div data-bug-status data-testid="bug-status">${decisionHtml}</div>` : `
    <div data-bug-status class="bug-status-row" data-testid="bug-status">
      ${s.jira_keys && s.jira_keys.length
        ? s.jira_keys.map(k => `<span class="bug-pill bug-pill--open"><span class="bug-dot"></span>${jiraLink(k)}<span class="bug-label">OPEN</span></span>`).join('')
        : '<span class="bug-pill bug-pill--new">New — not yet reported</span>'}
    </div>`}

    ${stepsHtml}

    <div class="fcard-actions" data-testid="card-actions">
      <div class="triage-actions-group">
        <button class="btn btn-primary${btnDoneClass}" data-create-jira data-testid="create-jira-button"${createDisabled}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>
          Create Jira Bug
        </button>
        <button class="btn btn-ghost btn-sm" data-link-jira-toggle data-testid="link-jira-button"${actionsDisabled}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          Link Jira
        </button>
      </div>
      ${jiraDisplay}
      <div class="triage-actions-divider"></div>
      <div class="triage-actions-group">
        <button class="btn btn-success btn-sm" data-override="accepted_pass" data-testid="override-pass-button"${actionsDisabled}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          Pass olarak işaretle
        </button>
        <button class="btn btn-ghost btn-sm" data-override="accepted_skip" data-testid="override-skip-button"${actionsDisabled}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
          Skip olarak işaretle
        </button>
      </div>
    </div>

    <div class="link-jira-section" data-link-jira-section hidden>
      <label class="override-label">Mevcut Jira Anahtarı</label>
      <div class="link-jira-row">
        <input class="link-jira-input" data-link-jira-input type="text" placeholder="PROJ-1234">
        <button class="btn btn-primary btn-sm" data-link-jira-submit>Bağla</button>
        <button class="btn btn-ghost btn-sm" data-link-jira-cancel>İptal</button>
      </div>
    </div>

    <div class="override-section" data-override-section hidden>
      <label class="override-label" data-override-label></label>
      <textarea class="override-reason" data-override-reason placeholder="Açıklama zorunlu…"></textarea>
      <div class="override-error" data-override-error></div>
      <div class="override-actions">
        <button class="btn btn-primary btn-sm" data-override-submit>Onayla</button>
        <button class="btn btn-ghost btn-sm" data-override-cancel>İptal</button>
      </div>
    </div>
  </div>`;
}

function renderCards(scenarios) {
  const main = document.getElementById('triage-main');
  if (!scenarios.length) {
    main.innerHTML = `<div class="empty-state"><div class="empty-icon">🎉</div><h2>Tüm senaryolar geçti</h2><p>Bu çalıştırmada hiçbir başarısızlık yok.</p></div>`;
    return;
  }
  main.innerHTML = scenarios.map(renderCard).join('');
  bindCardEvents();
}

function bindCardEvents() {
  document.querySelectorAll('[data-create-jira]').forEach(btn => {
    btn.addEventListener('click', () => createJira(btn));
  });

  document.querySelectorAll('[data-link-jira-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('[data-scenario-id]');
      const section = card.querySelector('[data-link-jira-section]');
      section.hidden = !section.hidden;
      card.querySelector('[data-override-section]').hidden = true;
    });
  });

  document.querySelectorAll('[data-link-jira-cancel]').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('[data-link-jira-section]').hidden = true;
    });
  });

  document.querySelectorAll('[data-link-jira-submit]').forEach(btn => {
    btn.addEventListener('click', () => linkJira(btn));
  });

  document.querySelectorAll('[data-override]').forEach(btn => {
    btn.addEventListener('click', () => {
      const card = btn.closest('[data-scenario-id]');
      const section = card.querySelector('[data-override-section]');
      const label = card.querySelector('[data-override-label]');
      const decision = btn.dataset.override;
      label.textContent = decision === 'accepted_pass' ? 'Pass Olarak İşaretleme Sebebi' : 'Skip Olarak İşaretleme Sebebi';
      section.hidden = !section.hidden;
      card.querySelector('[data-link-jira-section]').hidden = true;
      card.querySelector('[data-override-reason]').value = '';
      card.querySelector('[data-override-error]').textContent = '';
      card.querySelector('[data-override-reason]').classList.remove('override-reason--error');
    });
  });

  document.querySelectorAll('[data-override-cancel]').forEach(btn => {
    btn.addEventListener('click', () => {
      btn.closest('[data-override-section]').hidden = true;
    });
  });

  document.querySelectorAll('[data-override-submit]').forEach(btn => {
    btn.addEventListener('click', () => submitOverride(btn));
  });

  document.querySelectorAll('[data-copy-error]').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copyError ?? '';
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Kopyalandı!';
        setTimeout(() => { btn.textContent = orig; }, 1500);
      });
    });
  });
}

async function createJira(btn) {
  const card = btn.closest('[data-scenario-id]');
  const scenarioId = card.dataset.scenarioId;
  const statusEl = card.querySelector('[data-bug-status]');
  const jiraKeyEl = card.querySelector('[data-jira-key-display]');

  btn.disabled = true;
  btn.textContent = 'Creating…';

  try {
    const res = await fetch(`/api/triage/${RUN_ID}/scenarios/${scenarioId}/jira`, {
      method: 'POST', headers: authHeaders(),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail ?? `HTTP ${res.status}`);
    }
    const data = await res.json();
    statusEl.innerHTML = `<span class="bug-pill bug-pill--open"><span class="bug-dot"></span>${jiraLink(data.jiraKey, data.jiraUrl)}<span class="bug-label">OPEN</span></span>`;
    if (jiraKeyEl) {
      jiraKeyEl.innerHTML = jiraLink(data.jiraKey, data.jiraUrl);
      jiraKeyEl.style.display = 'inline-flex';
    }
    btn.textContent = 'Bug Created';
    btn.classList.add('btn--done');
    markCardDecided(card, 'jira_created');
    toast(`Jira bug oluşturuldu: ${data.jiraKey}`, 'success');
  } catch (e) {
    btn.textContent = 'Hata — Tekrar Dene';
    btn.disabled = false;
    toast(`Bug oluşturulamadı: ${e.message}`, 'error');
  }
}

async function linkJira(btn) {
  const card = btn.closest('[data-scenario-id]');
  const scenarioId = card.dataset.scenarioId;
  const section = card.querySelector('[data-link-jira-section]');
  const input = card.querySelector('[data-link-jira-input]');
  const jiraKey = input.value.trim();

  if (!jiraKey) {
    toast('Jira anahtarı zorunlu', 'error');
    return;
  }

  btn.disabled = true;

  try {
    const res = await fetch(`/api/triage/${RUN_ID}/scenarios/${scenarioId}/link-jira`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ jira_key: jiraKey }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail ?? `HTTP ${res.status}`);
    }
    const data = await res.json();
    const statusEl = card.querySelector('[data-bug-status]');
    statusEl.innerHTML = `<span class="bug-pill bug-pill--open"><span class="bug-dot"></span>${jiraLink(data.jiraKey, data.jiraUrl)}<span class="bug-label">LINKED</span></span>`;
    section.hidden = true;
    markCardDecided(card, 'jira_linked');
    toast(`Jira bağlandı: ${data.jiraKey}`, 'success');
  } catch (e) {
    toast(`Jira bağlanamadı: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
}

function submitOverride(btn) {
  const card = btn.closest('[data-scenario-id]');
  const section = card.querySelector('[data-override-section]');
  const textarea = card.querySelector('[data-override-reason]');
  const errorEl = card.querySelector('[data-override-error]');
  const reason = textarea.value.trim();

  if (!reason) {
    errorEl.textContent = 'Açıklama zorunlu';
    textarea.classList.add('override-reason--error');
    textarea.focus();
    return;
  }

  textarea.classList.remove('override-reason--error');
  errorEl.textContent = '';

  const decision = card.querySelector('[data-override]').dataset.override;
  const scenarioId = card.dataset.scenarioId;

  btn.disabled = true;

  fetch(`/api/triage/${RUN_ID}/scenarios/${scenarioId}/override`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ decision, reason }),
  })
  .then(res => {
    if (!res.ok) return res.json().then(err => { throw new Error(err.detail ?? `HTTP ${res.status}`); });
    return res.json();
  })
  .then(() => {
    section.hidden = true;
    const label = decision === 'accepted_pass' ? 'Pass olarak işaretlendi' : 'Skip olarak işaretlendi';
    const badgeClass = decision === 'accepted_pass' ? 'decision-badge--pass' : 'decision-badge--skip';
    const icon = decision === 'accepted_pass' ? '✓' : '⊘';
    const statusEl = card.querySelector('[data-bug-status]');
    statusEl.innerHTML = `<div class="decision-badge ${badgeClass}">${icon} ${label}</div><div class="decision-info"><strong>Sebep:</strong> ${esc(reason)}</div>`;
    markCardDecided(card, decision);
    toast(label, 'success');
  })
  .catch(e => {
    toast(`Hata: ${e.message}`, 'error');
  })
  .finally(() => { btn.disabled = false; });
}

function markCardDecided(card, decision) {
  card.dataset.decision = decision;
  card.querySelectorAll('[data-create-jira], [data-link-jira-toggle], [data-override]').forEach(btn => {
    btn.disabled = true;
  });
}

function setupFilter() {
  const input = document.getElementById('filter-input');
  const count = document.getElementById('visible-count');
  const cards = document.querySelectorAll('[data-scenario-id]');

  input?.addEventListener('input', () => {
    const q = input.value.toLowerCase();
    let n = 0;
    cards.forEach(c => {
      const name = (c.querySelector('.card-title')?.textContent ?? '').toLowerCase();
      const show = name.includes(q);
      c.style.display = show ? '' : 'none';
      if (show) n++;
    });
    count.textContent = String(n);
  });
}

async function init() {
  const token = getToken();
  if (!token) {
    document.getElementById('triage-auth').style.display = '';
    return;
  }

  document.getElementById('triage-auth').style.display = 'none';
  document.getElementById('triage-loading').style.display = '';

  try {
    const res = await fetch(`/api/triage/${RUN_ID}`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) {
      localStorage.removeItem('jwt_token');
      document.getElementById('triage-auth').style.display = '';
      document.getElementById('triage-loading').style.display = 'none';
      document.getElementById('triage-auth-error').textContent = 'Oturum süresi dolmuş. Tekrar giriş yapın.';
      return;
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
      throw new Error(err.detail ?? `HTTP ${res.status}`);
    }

    // Auto-match Jira issues by DOORS number (silent — ignore errors)
    try {
      await fetch(`/api/triage/${RUN_ID}/auto-match-jira`, {
        method: 'POST', headers: authHeaders(),
      });
    } catch { /* Jira not configured or unavailable */ }

    // Re-fetch triage data after auto-match so newly linked issues appear
    const finalRes = await fetch(`/api/triage/${RUN_ID}`, { headers: authHeaders() });
    const data = finalRes.ok ? await finalRes.json() : await res.json();

    document.getElementById('triage-loading').style.display = 'none';
    document.getElementById('triage-header').style.display = '';
    document.getElementById('triage-filter').style.display = '';
    document.getElementById('triage-main').style.display = '';
    document.getElementById('triage-footer').style.display = '';

    document.getElementById('triage-sub').textContent = `${data.total_failed} başarısız senaryo`;

    const statsEl = document.getElementById('triage-stats');
    statsEl.innerHTML = `
      <div class="tstat tstat--fail">
        <span class="tstat-num">${data.total_failed}</span>
        <span class="tstat-label">Failed</span>
      </div>`;

    document.getElementById('visible-count').textContent = String(data.scenarios.length);
    renderCards(data.scenarios);
    setupFilter();
  } catch (e) {
    document.getElementById('triage-loading').style.display = 'none';
    document.getElementById('triage-main').style.display = '';
    document.getElementById('triage-main').innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><h2>Hata</h2><p>${esc(e.message)}</p></div>`;
  }
}

document.getElementById('triage-login-form')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const username = document.getElementById('triage-username').value;
  const password = document.getElementById('triage-password').value;
  const errorEl = document.getElementById('triage-auth-error');
  errorEl.textContent = '';

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Giriş başarısız' }));
      throw new Error(err.detail ?? 'Giriş başarısız');
    }
    const data = await res.json();
    if (data.access_token) {
      localStorage.setItem('jwt_token', data.access_token);
      document.getElementById('triage-auth').style.display = 'none';
      init();
    } else {
      throw new Error('Token alınamadı');
    }
  } catch (e) {
    errorEl.textContent = e.message;
  }
});

document.addEventListener('DOMContentLoaded', init);