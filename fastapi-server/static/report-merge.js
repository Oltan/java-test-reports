import { C as Chart, r as registerables } from "./vendor.js";
Chart.register(...registerables);

const STATUS_COLORS = {
  passed: "#00c853",
  failed: "#ff1744",
  skipped: "#ffc107",
  broken: "#9e9e9e",
};

const TOKEN_KEY = "jwt_token";
function getToken() { return localStorage.getItem(TOKEN_KEY); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }
function $(id) { return document.getElementById(id); }

function showNavLinks() {
  const navLinks = $("nav-links");
  const logoutBtn = $("logout-btn");
  if (navLinks) navLinks.style.display = "";
  if (logoutBtn) logoutBtn.style.display = "";
}

function hideNavLinks() {
  const navLinks = $("nav-links");
  const logoutBtn = $("logout-btn");
  if (navLinks) navLinks.style.display = "none";
  if (logoutBtn) logoutBtn.style.display = "none";
}

function handleLogout() {
  clearToken();
  hideNavLinks();
  location.reload();
}

async function apiFetch(url, opts = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...opts.headers ?? {} };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { ...opts, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw { status: res.status, body };
  }
  return res.json();
}

let allJobs = [];
let selectedJobIds = new Set();
let allScenarios = [];
let selectedScenarioUids = new Set();
let triageCache = {};
let currentFilter = "all";
let charts = [];

function destroyCharts() {
  charts.forEach(c => c.destroy());
  charts = [];
}

function updateDateTime() {
  const el = $("rpt-datetime");
  if (el) {
    const now = new Date();
    el.textContent = now.toLocaleDateString("tr-TR", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  }
}

async function loadJobs() {
  const container = $("job-checkboxes");
  try {
    const data = await apiFetch("/api/tests/jobs");
    allJobs = data.jobs || [];
    if (!allJobs || allJobs.length === 0) {
      container.innerHTML = '<div class="rpt-loading">Henüz iş yok</div>';
      return;
    }
    renderJobCheckboxes();
  } catch (e) {
    container.innerHTML = `<div class="rpt-loading rpt-loading--error">Yüklenemedi: ${e.body?.detail || e.message || "HTTP " + e.status}</div>`;
  }
}

function renderJobCheckboxes() {
  const container = $("job-checkboxes");
  container.innerHTML = allJobs.map(job => {
    const isSelected = selectedJobIds.has(job.job_id);
    const workerTags = (job.workers || []).map(w => {
      const statusClass = w.status === "completed" ? "completed" : w.status === "running" ? "running" : w.status === "failed" ? "failed" : "";
      return `<span class="rpt-job-worker-tag ${statusClass ? 'rpt-job-worker-tag--' + statusClass : ''}">${escapeHtml(w.run_id?.slice(0, 16) || w.shard)}</span>`;
    }).join("");
    const startedAt = job.started_at ? new Date(job.started_at).toLocaleDateString("tr-TR") : "—";
    const statusBadge = job.status === "completed" ? "✓" : job.status === "running" ? "⟳" : job.status || "—";
    return `
      <label class="rpt-job-card ${isSelected ? 'selected' : ''}" data-job-id="${escapeHtml(job.job_id)}">
        <input type="checkbox" ${isSelected ? 'checked' : ''} value="${escapeHtml(job.job_id)}" class="job-checkbox">
        <div class="rpt-job-info">
          <div class="rpt-job-id">${escapeHtml(job.job_id.slice(0, 24))} <span style="color:var(--text-muted);font-weight:400;">${statusBadge}</span></div>
          <div class="rpt-job-meta">${startedAt} · ${job.environment || ""} · ${job.version || ""}</div>
          <div class="rpt-job-workers">${workerTags}</div>
        </div>
      </label>
    `;
  }).join("");

  container.querySelectorAll(".job-checkbox").forEach(cb => {
    cb.addEventListener("change", (e) => {
      const jobId = e.target.value;
      if (e.target.checked) {
        selectedJobIds.add(jobId);
      } else {
        selectedJobIds.delete(jobId);
      }
      updateJobCheckboxStyles();
      updateSelectedCount();
      loadScenariosForJobs();
    });
  });
}

function updateJobCheckboxStyles() {
  document.querySelectorAll(".rpt-job-card").forEach(card => {
    const jobId = card.dataset.jobId;
    if (selectedJobIds.has(jobId)) {
      card.classList.add("selected");
    } else {
      card.classList.remove("selected");
    }
  });
}

function updateSelectedCount() {
  $("selected-count").textContent = `${selectedJobIds.size} iş seçili`;
}

async function loadScenariosForJobs() {
  if (selectedJobIds.size === 0) {
    $("scenario-section").style.display = "none";
    $("blocker-banner").style.display = "none";
    allScenarios = [];
    selectedScenarioUids.clear();
    triageCache = {};
    return;
  }

  $("scenario-section").style.display = "block";

  try {
    const allRunIds = [];
    for (const job of allJobs) {
      if (selectedJobIds.has(job.job_id)) {
        for (const w of (job.workers || [])) {
          if (w.run_id) allRunIds.push(w.run_id);
        }
      }
    }

    if (allRunIds.length === 0) {
      $("scenario-cards").innerHTML = emptyState("Senaryo bulunamadı", "Seçilen işlerde çalıştırma verisi yok.");
      $("rpt-stats-bar").style.display = "none";
      $("rpt-chart-section").style.display = "none";
      $("generate-section").style.display = "none";
      return;
    }

    const ids = allRunIds.join(",");
    const data = await apiFetch(`/api/reports/merge-data?run_ids=${encodeURIComponent(ids)}`);
    allScenarios = data.scenarios || [];
    selectedScenarioUids.clear();

    for (const s of allScenarios) {
      if (s.status === "passed") {
        selectedScenarioUids.add(s.id);
      }
    }

    triageCache = {};
    await loadTriageForRuns(allRunIds);

    renderStats(data.summary);
    renderCharts(data.summary, data.runs);
    renderScenarioCards();
    updateGenerateSection();
  } catch (e) {
    $("scenario-cards").innerHTML = `<div class="rpt-loading rpt-loading--error">Yüklenemedi: ${e.body?.detail || e.message || "HTTP " + e.status}</div>`;
  }
}

async function loadTriageForRuns(runIds) {
  const promises = runIds.map(async (runId) => {
    try {
      const data = await apiFetch(`/api/triage/${encodeURIComponent(runId)}`);
      for (const s of (data.scenarios || [])) {
        triageCache[s.scenario_uid] = {
          decision: s.triage_decision,
          jira_key: s.jira_key,
          status: s.status,
          scenario_name: s.scenario_name,
        };
      }
    } catch {
      // triage endpoint may 404 if no failed scenarios — that's fine
    }
  });
  await Promise.all(promises);
}

function getTriageForScenario(scenarioId) {
  return triageCache[scenarioId] || null;
}

function isScenarioBlocked(scenario) {
  if (scenario.status !== "failed") return false;
  const triage = getTriageForScenario(scenario.id);
  if (!triage) return true;
  const allowed = ["jira_linked", "jira_created", "accepted_pass", "accepted_skip"];
  return !allowed.includes(triage.decision);
}

function getBlockerReason(scenario) {
  const triage = getTriageForScenario(scenario.id);
  if (!triage) return "Triaj kararı yok — Jira ile ilişkilendirilmeli veya geçersiz kılınmalı";
  return `Triaj kararı '${triage.decision}' — Jira ile ilişkilendirilmeli veya geçersiz kılınmalı`;
}

function renderStats(summary) {
  $("rpt-stats-bar").style.display = "flex";
  animateValue($("stat-total"), summary.total);
  animateValue($("stat-passed"), summary.passed);
  animateValue($("stat-failed"), summary.failed);
  animateValue($("stat-skipped"), summary.skipped);
}

function animateValue(el, target) {
  const start = Date.now();
  const tick = () => {
    const progress = Math.min((Date.now() - start) / 500, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(eased * target);
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function renderCharts(summary, runs) {
  $("rpt-chart-section").style.display = "grid";
  destroyCharts();

  const isDark = document.documentElement.getAttribute("data-theme") !== "light";
  const surfaceColor = isDark ? "#181d28" : "#ffffff";
  const textColor = isDark ? "#8b95a8" : "#5c6578";

  const pieCtx = $("reportPieChart").getContext("2d");
  const total = summary.passed + summary.failed + summary.skipped || 1;
  charts.push(new Chart(pieCtx, {
    type: "doughnut",
    data: {
      labels: ["Passed", "Failed", "Skipped"],
      datasets: [{
        data: [summary.passed, summary.failed, summary.skipped],
        backgroundColor: [STATUS_COLORS.passed, STATUS_COLORS.failed, STATUS_COLORS.skipped],
        borderColor: surfaceColor,
        borderWidth: 3,
        hoverOffset: 10,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "70%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: textColor, padding: 16, font: { size: 12, family: "'DM Sans', sans-serif" }, usePointStyle: true, pointStyle: "circle" },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.parsed} (${Math.round(ctx.parsed / total * 100)}%)`,
          },
        },
      },
    },
  }));

  if (runs && runs.length > 0) {
    const barCtx = $("reportBarChart").getContext("2d");
    charts.push(new Chart(barCtx, {
      type: "bar",
      data: {
        labels: runs.map(r => r.runId.slice(0, 16)),
        datasets: [
          { label: "Passed", data: runs.map(r => r.passed), backgroundColor: STATUS_COLORS.passed, borderRadius: 4 },
          { label: "Failed", data: runs.map(r => r.failed), backgroundColor: STATUS_COLORS.failed, borderRadius: 4 },
          { label: "Skipped", data: runs.map(r => r.skipped), backgroundColor: STATUS_COLORS.skipped, borderRadius: 4 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: textColor, padding: 16, font: { size: 12, family: "'DM Sans', sans-serif" }, usePointStyle: true, pointStyle: "circle" },
          },
        },
        scales: {
          x: { stacked: true, grid: { color: isDark ? "rgba(148,163,184,.1)" : "rgba(0,0,0,.06)" }, ticks: { color: textColor } },
          y: { stacked: true, grid: { color: isDark ? "rgba(148,163,184,.1)" : "rgba(0,0,0,.06)" }, ticks: { color: textColor } },
        },
      },
    }));
  }
}

function renderScenarioCards() {
  const container = $("scenario-cards");
  const filtered = filterScenarios(allScenarios, currentFilter);

  if (!filtered || filtered.length === 0) {
    container.innerHTML = emptyState("Senaryo bulunamadı", "Seçilen filtrede senaryo verisi yok.");
    $("generate-section").style.display = "none";
    return;
  }

  $("generate-section").style.display = "block";

  const statusOrder = { failed: 0, skipped: 1, passed: 2 };
  const sorted = [...filtered].sort((a, b) => statusOrder[a.status] - statusOrder[b.status]);

  container.innerHTML = sorted.map(s => {
    const statusClass = `rpt-card--${s.status}`;
    const statusLabel = s.status === "passed" ? "PASSED" : s.status === "failed" ? "FAILED" : "SKIPPED";
    const blocked = isScenarioBlocked(s);
    const triage = getTriageForScenario(s.id);
    const selectableClass = "rpt-card--selectable";
    const selectedClass = selectedScenarioUids.has(s.id) ? " rpt-card--selected" : "";
    const blockedClass = blocked ? " rpt-card--blocked" : "";

    let triageBadge = "";
    if (s.status === "failed") {
      if (blocked) {
        triageBadge = `<span class="rpt-card-blocker-badge">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          Triaj Gerekli</span>`;
      } else if (triage) {
        triageBadge = `<span class="rpt-card-triage-ok">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          ${triage.jira_key ? escapeHtml(triage.jira_key) : "Onaylandı"}</span>`;
      }
    }

    let stepsHtml = "";
    if (s.steps && s.steps.length > 0) {
      stepsHtml = `<ul class="rpt-steps">${s.steps.map(step => {
        const stepClass = `rpt-step--${step.status}`;
        return `<li class="rpt-step ${stepClass}">
          <span class="rpt-step-dot"></span>
          <span class="rpt-step-name">${escapeHtml(step.name)}</span>
        </li>`;
      }).join("")}</ul>`;
    }

    let errorHtml = "";
    if (s.errorMessage) {
      errorHtml = `<div class="rpt-error-block">
        <div class="rpt-error-header" onclick="window.toggleError('${escapeHtml(s.id)}')">
          <span>Hata Detayı</span>
          <svg class="rpt-error-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="rpt-error-body" id="error-${escapeHtml(s.id)}">${escapeHtml(s.errorMessage)}</div>
      </div>`;
    }

    let tagsHtml = "";
    if (s.tags && s.tags.length > 0) {
      tagsHtml = `<div class="rpt-tags">${s.tags.map(t => `<span class="rpt-tag">${escapeHtml(t)}</span>`).join("")}</div>`;
    }

    const featurePath = s.tags && s.tags.length > 0 ? s.tags.find(t => t.startsWith("@"))?.replace("@", "") : "";

    return `
      <div class="rpt-card ${statusClass} ${selectableClass}${selectedClass}${blockedClass}" data-scenario-id="${escapeHtml(s.id)}" data-status="${s.status}" data-blocked="${blocked}">
        <input type="checkbox" class="rpt-card-checkbox" ${selectedScenarioUids.has(s.id) ? 'checked' : ''} ${blocked ? 'disabled' : ''} value="${escapeHtml(s.id)}">
        <div class="rpt-card-header" onclick="window.toggleScenario('${escapeHtml(s.id)}')">
          <div class="rpt-card-left">
            <span class="rpt-status-dot"></span>
            <span class="rpt-card-name">${escapeHtml(s.name)}</span>
          </div>
          <div class="rpt-card-right">
            ${featurePath ? `<span class="rpt-card-feature">${escapeHtml(featurePath)}</span>` : ""}
            <span class="rpt-card-duration">${escapeHtml(s.duration)}</span>
            <span class="rpt-card-badge">${statusLabel}</span>
            ${triageBadge}
            <svg class="rpt-card-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
        </div>
        <div class="rpt-card-body" id="body-${escapeHtml(s.id)}">
          ${stepsHtml}
          ${errorHtml}
          ${tagsHtml}
          <div class="rpt-card-meta">Run: <span class="rpt-card-runid">${escapeHtml(s.runId)}</span></div>
        </div>
      </div>
    `;
  }).join("");

  container.querySelectorAll(".rpt-card-checkbox").forEach(cb => {
    cb.addEventListener("change", (e) => {
      e.stopPropagation();
      const scenarioId = e.target.value;
      if (e.target.checked) {
        selectedScenarioUids.add(scenarioId);
      } else {
        selectedScenarioUids.delete(scenarioId);
      }
      updateCardStyles();
      updateGenerateSection();
    });
  });
}

function filterScenarios(scenarios, filter) {
  if (filter === "all") return scenarios;
  return scenarios.filter(s => s.status === filter);
}

function updateCardStyles() {
  document.querySelectorAll(".rpt-card[data-scenario-id]").forEach(card => {
    const id = card.dataset.scenarioId;
    if (selectedScenarioUids.has(id)) {
      card.classList.add("rpt-card--selected");
    } else {
      card.classList.remove("rpt-card--selected");
    }
    const cb = card.querySelector(".rpt-card-checkbox");
    if (cb) cb.checked = selectedScenarioUids.has(id);
  });
}

function updateGenerateSection() {
  const btn = $("generate-share-btn");
  const countEl = $("selected-scenario-count");
  const statusEl = $("generate-status");
  const banner = $("blocker-banner");
  const bannerList = $("blocker-list");

  const selectedScenarios = allScenarios.filter(s => selectedScenarioUids.has(s.id));
  const blockedScenarios = selectedScenarios.filter(s => isScenarioBlocked(s));

  countEl.textContent = `${selectedScenarios.length} senaryo seçili`;

  if (blockedScenarios.length > 0) {
    btn.disabled = true;
    statusEl.textContent = `${blockedScenarios.length} triaj gerektiren senaryo engelleniyor`;
    statusEl.className = "rpt-generate-status rpt-generate-status--error";

    banner.style.display = "flex";
    bannerList.innerHTML = blockedScenarios.map(s => {
      const reason = getBlockerReason(s);
      return `<div class="rpt-blocker-item">
        <span class="rpt-blocker-item-scenario">${escapeHtml(s.name)}</span>
        <span class="rpt-blocker-item-reason">${escapeHtml(reason)}</span>
      </div>`;
    }).join("");
  } else {
    banner.style.display = "none";
    bannerList.innerHTML = "";
    if (selectedScenarios.length === 0) {
      btn.disabled = true;
      statusEl.textContent = "";
      statusEl.className = "rpt-generate-status";
    } else {
      btn.disabled = false;
      statusEl.textContent = "";
      statusEl.className = "rpt-generate-status";
    }
  }

  $("share-result").style.display = "none";
  currentShareId = null;
  $("doors-export-btn").disabled = true;
  $("email-share-btn").disabled = true;
  $("share-action-status").textContent = "";
  $("share-action-status").className = "rpt-share-action-status";
}

let currentShareId = null;

async function generateShare() {
  const btn = $("generate-share-btn");
  const statusEl = $("generate-status");
  const shareResult = $("share-result");
  const shareUrl = $("share-url");

  const selectedIds = Array.from(selectedScenarioUids);
  if (selectedIds.length === 0) return;

  btn.disabled = true;
  btn.innerHTML = `<span class="rpt-spinner"></span> Oluşturuluyor…`;
  statusEl.textContent = "";
  shareResult.style.display = "none";
  currentShareId = null;

  try {
    const result = await apiFetch("/api/reports/generate-share", {
      method: "POST",
      body: JSON.stringify({ scenario_ids: selectedIds, title: "Public Report" }),
    });

    currentShareId = result.share_id;
    const fullUrl = window.location.origin + result.url;
    shareUrl.textContent = fullUrl;
    shareResult.style.display = "block";
    statusEl.textContent = "Bağlantı oluşturuldu!";
    statusEl.className = "rpt-generate-status rpt-generate-status--success";

    $("doors-export-btn").disabled = false;
    $("email-share-btn").disabled = false;
    $("share-action-status").textContent = "";
    $("share-action-status").className = "rpt-share-action-status";
  } catch (e) {
    if (e.status === 409 && e.body?.detail?.blockers) {
      const blockers = e.body.detail.blockers;
      statusEl.textContent = `${blockers.length} triaj gerektiren senaryo engelleniyor`;
      statusEl.className = "rpt-generate-status rpt-generate-status--error";

      const banner = $("blocker-banner");
      const bannerList = $("blocker-list");
      banner.style.display = "flex";
      bannerList.innerHTML = blockers.map(b => {
        return `<div class="rpt-blocker-item">
          <span class="rpt-blocker-item-scenario">${escapeHtml(b.scenario_id)}</span>
          <span class="rpt-blocker-item-reason">${escapeHtml(b.reason)}</span>
        </div>`;
      }).join("");
    } else {
      statusEl.textContent = `Hata: ${e.body?.detail?.message || e.body?.detail || e.message || "Bilinmeyen hata"}`;
      statusEl.className = "rpt-generate-status rpt-generate-status--error";
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Paylaşım Bağlantısı Oluştur`;
    updateGenerateSection();
  }
}

async function shareToDoors(shareId) {
  const btn = $("doors-export-btn");
  const statusEl = $("share-action-status");
  const originalHtml = btn.innerHTML;

  btn.disabled = true;
  btn.innerHTML = `<span class="rpt-spinner"></span> Aktarılıyor…`;
  statusEl.textContent = "";
  statusEl.className = "rpt-share-action-status";

  try {
    const result = await apiFetch(`/api/doors/share/${encodeURIComponent(shareId)}`, { method: "POST" });
    if (result.status === "unavailable") {
      statusEl.textContent = "DOORS bağlantısı mevcut değil";
      statusEl.className = "rpt-share-action-status rpt-share-action-status--error";
    } else if (result.status === "success") {
      statusEl.textContent = "DOORS'a başarıyla aktarıldı";
      statusEl.className = "rpt-share-action-status rpt-share-action-status--success";
    } else {
      statusEl.textContent = `DOORS aktarımı başarısız: ${result.stderr || "Bilinmeyen hata"}`;
      statusEl.className = "rpt-share-action-status rpt-share-action-status--error";
    }
  } catch (e) {
    statusEl.textContent = `DOORS hatası: ${e.body?.detail || e.message || "Bilinmeyen hata"}`;
    statusEl.className = "rpt-share-action-status rpt-share-action-status--error";
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

async function shareViaEmail(shareId) {
  const btn = $("email-share-btn");
  const statusEl = $("share-action-status");
  const originalHtml = btn.innerHTML;

  btn.disabled = true;
  btn.innerHTML = `<span class="rpt-spinner"></span> Gönderiliyor…`;
  statusEl.textContent = "";
  statusEl.className = "rpt-share-action-status";

  try {
    const publicLink = window.location.origin + `/public/reports/${encodeURIComponent(shareId)}`;
    const result = await apiFetch(`/api/email/share/${encodeURIComponent(shareId)}?to=engineer`, { method: "POST" });
    if (result.sent) {
      statusEl.textContent = `E-posta gönderildi — ${publicLink}`;
      statusEl.className = "rpt-share-action-status rpt-share-action-status--success";
    } else {
      statusEl.textContent = `E-posta gönderilemedi: ${result.error || "Bilinmeyen hata"}`;
      statusEl.className = "rpt-share-action-status rpt-share-action-status--error";
    }
  } catch (e) {
    statusEl.textContent = `E-posta hatası: ${e.body?.detail || e.message || "Bilinmeyen hata"}`;
    statusEl.className = "rpt-share-action-status rpt-share-action-status--error";
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

function emptyState(title, message) {
  return `
    <div class="rpt-empty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--text-muted);"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
      <h2>${title}</h2>
      <p>${message}</p>
    </div>`;
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

window.toggleScenario = function(id) {
  const card = document.querySelector(`[data-scenario-id="${id}"]`);
  if (card) card.classList.toggle("expanded");
};

window.toggleError = function(id) {
  const block = document.getElementById(`error-${id}`);
  if (block) block.classList.toggle("expanded");
};

function initThemeToggle() {
  const saved = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  const btn = $("theme-toggle");
  btn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    if (selectedJobIds.size > 0) {
      destroyCharts();
      loadScenariosForJobs();
    }
  });
}

(async function init() {
  $("logout-btn")?.addEventListener("click", handleLogout);

  $("select-all-btn")?.addEventListener("click", () => {
    allJobs.forEach(j => selectedJobIds.add(j.job_id));
    renderJobCheckboxes();
    updateSelectedCount();
    loadScenariosForJobs();
  });

  $("deselect-all-btn")?.addEventListener("click", () => {
    selectedJobIds.clear();
    renderJobCheckboxes();
    updateSelectedCount();
    loadScenariosForJobs();
  });

  $("select-all-scenarios-btn")?.addEventListener("click", () => {
    const filtered = filterScenarios(allScenarios, currentFilter);
    for (const s of filtered) {
      if (!isScenarioBlocked(s)) {
        selectedScenarioUids.add(s.id);
      }
    }
    renderScenarioCards();
    updateGenerateSection();
  });

  $("deselect-all-scenarios-btn")?.addEventListener("click", () => {
    selectedScenarioUids.clear();
    renderScenarioCards();
    updateGenerateSection();
  });

  $("generate-share-btn")?.addEventListener("click", generateShare);

  $("doors-export-btn")?.addEventListener("click", () => {
    if (currentShareId) shareToDoors(currentShareId);
  });

  $("email-share-btn")?.addEventListener("click", () => {
    if (currentShareId) shareViaEmail(currentShareId);
  });

  $("copy-share-btn")?.addEventListener("click", () => {
    const url = $("share-url").textContent;
    navigator.clipboard.writeText(url).then(() => {
      $("copy-share-btn").textContent = "Kopyalandı!";
      setTimeout(() => { $("copy-share-btn").textContent = "Kopyala"; }, 2000);
    });
  });

  document.querySelectorAll("#scenario-filter-tabs .filter-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#scenario-filter-tabs .filter-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentFilter = tab.dataset.filter;
      renderScenarioCards();
    });
  });

  initThemeToggle();
  updateDateTime();

  const token = getToken();
  if (token) {
    try {
      await apiFetch("/api/v1/runs", { method: "GET" });
      showNavLinks();
    } catch {
      clearToken();
      hideNavLinks();
    }
  } else {
    hideNavLinks();
  }

  loadJobs();
})();