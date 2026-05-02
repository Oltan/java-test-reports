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
function $(id) { return document.getElementById(id); }

async function apiFetch(url, opts = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...opts.headers ?? {} };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { ...opts, headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

let allRuns = [];
let selectedRunIds = new Set();
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

async function loadRuns() {
  const container = $("run-checkboxes");
  try {
    allRuns = await apiFetch("/api/v1/runs");
    if (!allRuns || allRuns.length === 0) {
      container.innerHTML = '<div class="rpt-loading">Henüz çalıştırma yok</div>';
      return;
    }
    renderRunCheckboxes();
  } catch (e) {
    container.innerHTML = `<div class="rpt-loading rpt-loading--error">Yüklenemedi: ${e.message}</div>`;
  }
}

function renderRunCheckboxes() {
  const container = $("run-checkboxes");
  container.innerHTML = allRuns.map(run => {
    const date = run.timestamp ? new Date(run.timestamp).toLocaleDateString("tr-TR") : "—";
    const total = run.totalScenarios || 0;
    const pct = total > 0 ? Math.round((run.passed / total) * 100) : 0;
    const isSelected = selectedRunIds.has(run.runId);
    return `
      <label class="run-checkbox-card ${isSelected ? 'selected' : ''}" data-run-id="${run.runId}">
        <input type="checkbox" ${isSelected ? 'checked' : ''} value="${run.runId}" class="run-checkbox">
        <div class="run-checkbox-info">
          <div class="run-checkbox-id">${run.runId.slice(0, 24)}</div>
          <div class="run-checkbox-meta">${date} · ${run.passed}/${run.failed}/${run.skipped} · ${pct}%</div>
        </div>
      </label>
    `;
  }).join("");

  container.querySelectorAll(".run-checkbox").forEach(cb => {
    cb.addEventListener("change", (e) => {
      const runId = e.target.value;
      if (e.target.checked) {
        selectedRunIds.add(runId);
      } else {
        selectedRunIds.delete(runId);
      }
      updateCheckboxStyles();
      updateSelectedCount();
      loadMergedData();
    });
  });
}

function updateCheckboxStyles() {
  document.querySelectorAll(".run-checkbox-card").forEach(card => {
    const runId = card.dataset.runId;
    if (selectedRunIds.has(runId)) {
      card.classList.add("selected");
    } else {
      card.classList.remove("selected");
    }
  });
}

function updateSelectedCount() {
  $("selected-count").textContent = `${selectedRunIds.size} seçili`;
}

async function loadMergedData() {
  if (selectedRunIds.size === 0) {
    $("rpt-stats-bar").style.display = "none";
    $("rpt-chart-section").style.display = "none";
    $("scenario-cards").innerHTML = `
      <div class="rpt-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--text-muted);"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        <h2>Çalıştırma seçin</h2>
        <p>Yukarıdaki listeden en az bir çalıştırma seçerek rapor detaylarını görüntüleyin.</p>
      </div>`;
    return;
  }

  try {
    const ids = Array.from(selectedRunIds).join(",");
    const data = await apiFetch(`/api/reports/merge-data?run_ids=${encodeURIComponent(ids)}`);
    renderStats(data.summary);
    renderCharts(data.summary, data.runs);
    renderScenarioCards(data.scenarios);
  } catch (e) {
    console.error("Failed to load merged data:", e);
  }
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

function renderScenarioCards(scenarios) {
  const container = $("scenario-cards");
  if (!scenarios || scenarios.length === 0) {
    container.innerHTML = `
      <div class="rpt-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--text-muted);"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <h2>Senaryo bulunamadı</h2>
        <p>Seçilen çalıştırmalarda senaryo verisi yok.</p>
      </div>`;
    return;
  }

  const statusOrder = { failed: 0, skipped: 1, passed: 2 };
  const sorted = [...scenarios].sort((a, b) => statusOrder[a.status] - statusOrder[b.status]);

  container.innerHTML = sorted.map(s => {
    const statusClass = `rpt-card--${s.status}`;
    const statusLabel = s.status === "passed" ? "PASSED" : s.status === "failed" ? "FAILED" : "SKIPPED";

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
        <div class="rpt-error-header" onclick="window.toggleError('${s.id}')">
          <span>Hata Detayı</span>
          <svg class="rpt-error-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
        </div>
        <div class="rpt-error-body" id="error-${s.id}">${escapeHtml(s.errorMessage)}</div>
      </div>`;
    }

    let tagsHtml = "";
    if (s.tags && s.tags.length > 0) {
      tagsHtml = `<div class="rpt-tags">${s.tags.map(t => `<span class="rpt-tag">${escapeHtml(t)}</span>`).join("")}</div>`;
    }

    const featurePath = s.tags && s.tags.length > 0 ? s.tags.find(t => t.startsWith("@"))?.replace("@", "") : "";

    return `
      <div class="rpt-card ${statusClass}" data-scenario-id="${s.id}">
        <div class="rpt-card-header" onclick="window.toggleScenario('${s.id}')">
          <div class="rpt-card-left">
            <span class="rpt-status-dot"></span>
            <span class="rpt-card-name">${escapeHtml(s.name)}</span>
          </div>
          <div class="rpt-card-right">
            ${featurePath ? `<span class="rpt-card-feature">${escapeHtml(featurePath)}</span>` : ""}
            <span class="rpt-card-duration">${escapeHtml(s.duration)}</span>
            <span class="rpt-card-badge">${statusLabel}</span>
            <svg class="rpt-card-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
          </div>
        </div>
        <div class="rpt-card-body" id="body-${s.id}">
          ${stepsHtml}
          ${errorHtml}
          ${tagsHtml}
          <div class="rpt-card-meta">Run: <span class="rpt-card-runid">${escapeHtml(s.runId)}</span></div>
        </div>
      </div>
    `;
  }).join("");
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
    if (selectedRunIds.size > 0) {
      destroyCharts();
      loadMergedData();
    }
  });
}

(function init() {
  $("select-all-btn")?.addEventListener("click", () => {
    allRuns.forEach(r => selectedRunIds.add(r.runId));
    renderRunCheckboxes();
    updateSelectedCount();
    loadMergedData();
  });
  $("deselect-all-btn")?.addEventListener("click", () => {
    selectedRunIds.clear();
    renderRunCheckboxes();
    updateSelectedCount();
    loadMergedData();
  });
  initThemeToggle();
  updateDateTime();
  loadRuns();
})();