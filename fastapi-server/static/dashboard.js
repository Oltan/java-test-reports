import { C as Chart, r as registerables } from "./vendor.js";
Chart.register(...registerables);

const TOKEN_KEY = "jwt_token";

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function setToken(t) { localStorage.setItem(TOKEN_KEY, t); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }
function $(id) { return document.getElementById(id); }

async function apiFetch(url, opts = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...opts.headers ?? {} };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, { ...opts, headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function handleLogin(e) {
  e.preventDefault();
  const form = e.target;
  const username = form.querySelector("#username").value;
  const password = form.querySelector("#password").value;
  const errorEl = $("login-error");
  const btn = form.querySelector('button[type="submit"]');
  errorEl.textContent = "";
  btn.disabled = true;
  btn.textContent = "Giriş yapılıyor…";
  try {
    const data = await apiFetch("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    setToken(data.token);
    document.cookie = `access_token=${data.token}; path=/; SameSite=Lax; max-age=${24 * 3600}`;
    showDashboard();
  } catch {
    errorEl.textContent = "Geçersiz kullanıcı adı veya şifre";
  } finally {
    btn.disabled = false;
    btn.textContent = "Giriş Yap";
  }
}

function handleLogout() {
  clearToken();
  document.cookie = "access_token=; Max-Age=0; path=/";
  hideNavLinks();
  location.reload();
}

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

async function showDashboard() {
  $("login-section").style.display = "none";
  $("dashboard-content").style.display = "block";
  showNavLinks();
  await loadDashboard();
}

function animateValue(el, target, suffix = "") {
  const start = Date.now();
  const tick = () => {
    const progress = Math.min((Date.now() - start) / 700, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(eased * target) + suffix;
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

let charts = [];

function destroyCharts() {
  charts.forEach(c => c.destroy());
  charts = [];
}

function renderPieChart(metrics) {
  const ctx = $("pieChart").getContext("2d");
  const total = metrics.passed + metrics.failed + metrics.skipped || 1;
  charts.push(new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Passed", "Failed", "Skipped"],
      datasets: [{
        data: [metrics.passed, metrics.failed, metrics.skipped],
        backgroundColor: ["#34d399", "#f87171", "#94a3b8"],
        borderColor: getComputedStyle(document.documentElement).getPropertyValue("--surface").trim(),
        borderWidth: 3,
        hoverOffset: 10,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "74%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#8b95a8", padding: 20, font: { size: 13, family: "'DM Sans', sans-serif" } },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.label}: ${ctx.parsed} (${Math.round(ctx.parsed / total * 100)}%)`,
          },
        },
      },
    },
  }));
}

function renderBarChart(versionBreakdown) {
  const ctx = $("barChart").getContext("2d");
  const labels = versionBreakdown.map(v => v.version);
  const passed = versionBreakdown.map(v => v.passed);
  const failed = versionBreakdown.map(v => v.failed);
  const skipped = versionBreakdown.map(v => v.skipped);

  charts.push(new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Passed", data: passed, backgroundColor: "#34d399", borderRadius: 4 },
        { label: "Failed", data: failed, backgroundColor: "#f87171", borderRadius: 4 },
        { label: "Skipped", data: skipped, backgroundColor: "#94a3b8", borderRadius: 4 },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#8b95a8", padding: 16, font: { size: 12, family: "'DM Sans', sans-serif" } },
        },
      },
      scales: {
        x: {
          stacked: true,
          grid: { color: "rgba(148,163,184,.1)" },
          ticks: { color: "#8b95a8" },
        },
        y: {
          stacked: true,
          grid: { display: false },
          ticks: { color: "#8b95a8" },
        },
      },
    },
  }));
}

function renderMetrics(metrics) {
  animateValue($("metric-rate"), metrics.success_rate, "%");
  animateValue($("metric-total"), metrics.total_runs);
  animateValue($("metric-avg"), metrics.avg_duration, "s");
  animateValue($("metric-flaky"), metrics.flaky_count);
}

function updateHeatMap(metrics) {
  const passRate = metrics.total_runs > 0 ? metrics.success_rate : 100;
  const warmth = 100 - passRate;
  const hue = 160 - (warmth * 1.6);
  const root = document.documentElement;
  root.style.setProperty('--warmth', warmth);
  root.style.setProperty('--heat-hue', hue);
  root.style.setProperty('--heat-glow', `0 0 40px hsla(${hue}, 80%, 50%, ${0.15 + warmth * 0.003})`);
  root.style.setProperty('--heat-accent', `hsl(${hue}, 70%, 50%)`);
  root.style.setProperty('--heat-accent-muted', `hsla(${hue}, 70%, 50%, 0.12)`);
  root.style.setProperty('--accent', `hsl(${hue}, 70%, 50%)`);
  root.style.setProperty('--accent-hover', `hsl(${hue}, 80%, 60%)`);
  root.style.setProperty('--accent-muted', `hsla(${hue}, 70%, 50%, 0.12)`);
  root.style.setProperty('--accent-glow', `hsla(${hue}, 70%, 50%, 0.25)`);
}

function renderTable(runs) {
  const tbody = $("run-tbody");
  if (!runs || runs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted)">Veri bulunamadı</td></tr>';
    return;
  }
  tbody.innerHTML = runs.map(run => {
    const date = run.timestamp ? new Date(run.timestamp).toLocaleDateString("tr-TR") : "—";
    const total = run.totalScenarios || 0;
    const pct = total > 0 ? Math.round((run.passed / total) * 100) : 0;
    const hasRetries = run.scenarios?.some(s => s.attempts?.length > 1);
    const hasDeps = run.scenarios?.some(s => s.dependencies?.length > 0);
    const skipped = run.skipped || 0;
    const isPass = run.failed === 0 && skipped === 0;
    const isSkipped = run.failed === 0 && skipped > 0;
    const rowStatus = isPass ? "passed" : isSkipped ? "skipped" : "failed";
    const rowClass = isPass ? "" : isSkipped ? "tr-skip" : "tr-fail";
    const pillClass = isPass ? "pill-pass" : isSkipped ? "pill-skip" : "pill-fail";
    const pillLabel = isPass ? "PASSED" : isSkipped ? "SKIPPED" : "FAILED";
    const allTags = [...new Set((run.scenarios || []).flatMap(s => s.tags || []))];
    const tagBadges = allTags.slice(0, 4).map(t => `<span class="run-tag">${t}</span>`).join("");
    const moreTag = allTags.length > 4 ? `<span class="run-tag run-tag-more">+${allTags.length - 4}</span>` : "";
    const verBadge = run.version ? `<span class="run-ver">${run.version}</span>` : "";
    return `<tr data-status="${rowStatus}" class="${rowClass}">
      <td>
        <a class="run-link" href="/reports/${run.runId}">${run.runId.slice(0, 22)}</a>
        <div class="run-meta">${verBadge}${tagBadges}${moreTag}</div>
      </td>
      <td class="td-muted">${date}</td>
      <td><span class="badge badge-pass">${run.passed}</span></td>
      <td><span class="badge badge-fail">${run.failed}</span></td>
      <td><span class="badge badge-skip">${skipped}</span></td>
      <td>
        <div class="prog-wrap"><div class="prog-bar" style="width:${pct}%"></div></div>
        <span class="prog-label">${pct}%</span>
      </td>
      <td class="td-muted">${parseFloat(run.duration).toFixed(1)}s</td>
      <td>${hasRetries ? '<span class="badge badge-retry">retried</span>' : '<span class="td-muted">—</span>'}</td>
      <td>${hasDeps ? '<span class="badge badge-dep">⛓️ deps</span>' : '<span class="td-muted">—</span>'}</td>
      <td><span class="status-pill ${pillClass}">${pillLabel}</span></td>
      <td><a class="action-link" href="/reports/${run.runId}/triage">Triage →</a></td>
    </tr>`;
  }).join("");
}

function showEmpty() {
  const tbody = $("run-tbody");
  if (tbody) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;color:var(--text-muted)">Henüz test çalıştırılmadı</td></tr>';
  }
}

async function loadDashboard() {
  let runs = [];
  let metrics = null;

  try {
    runs = await apiFetch("/api/v1/runs");
    console.log("[dashboard] runs loaded:", runs.length);
  } catch (err) {
    console.error("[dashboard] Failed to load runs:", err);
  }

  try {
    metrics = await apiFetch("/api/dashboard/metrics");
    console.log("[dashboard] metrics loaded:", metrics);
  } catch (err) {
    console.error("[dashboard] Failed to load metrics:", err);
  }

  destroyCharts();

  if (metrics) {
    renderMetrics(metrics);
    updateHeatMap(metrics);
    if (metrics.version_breakdown?.length > 0) {
      renderBarChart(metrics.version_breakdown);
    }
  }

  if (runs && runs.length > 0) {
    if (metrics) {
      renderPieChart(metrics);
    }
    renderTable(runs);
  } else {
    showEmpty();
  }
}

async function loadVersions() {
  try {
    const data = await apiFetch("/api/versions");
    const select = $("version-select");
    if (!select) return;
    const currentVal = select.value;
    select.innerHTML = '<option value="">Tümü</option>';
    data.versions.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    });
    if (currentVal && data.versions.includes(currentVal)) {
      select.value = currentVal;
    }
  } catch { /* versions endpoint may fail if no data */ }
}

function getFilterParams() {
  const version = $("version-select")?.value || "";
  const dateRange = $("date-range")?.value || "";
  const params = new URLSearchParams();
  if (version) params.set("version", version);
  if (dateRange) {
    const parts = dateRange.split(" to ");
    if (parts[0]) params.set("start", new Date(parts[0]).toISOString());
    if (parts[1]) params.set("end", new Date(parts[1]).toISOString());
  }
  return params.toString();
}

async function handleGenerate() {
  const params = getFilterParams();
  const query = params ? `?${params}` : "";
  let runs = [];
  let metrics = null;

  try {
    runs = await apiFetch(`/api/v1/runs${query}`);
  } catch (err) {
    console.error("Failed to load runs:", err);
  }

  try {
    metrics = await apiFetch(`/api/dashboard/metrics${query}`);
  } catch (err) {
    console.error("Failed to load metrics:", err);
  }

  destroyCharts();

  if (metrics) {
    renderMetrics(metrics);
    updateHeatMap(metrics);
    if (metrics.version_breakdown?.length > 0) {
      renderBarChart(metrics.version_breakdown);
    }
  }

  if (runs && runs.length > 0) {
    if (metrics) {
      renderPieChart(metrics);
    }
    renderTable(runs);
  } else {
    showEmpty();
  }
}

function initThemeToggle() {
  const saved = localStorage.getItem("theme") || "dark";
  document.documentElement.setAttribute("data-theme", saved);
  const btn = $("theme-toggle");
  btn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    destroyCharts();
    loadDashboard();
  });
}

function initDatePicker() {
  const el = $("date-range");
  if (typeof flatpickr === "undefined") return;
  flatpickr(el, {
    mode: "range",
    enableTime: true,
    dateFormat: "Y-m-d H:i",
    locale: typeof flatpickr.l10ns?.tr !== "undefined" ? flatpickr.l10ns.tr : {},
    time_24hr: true,
    theme: "dark",
  });
}

function initWebSocket() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const token = getToken();
  if (!token) return;
  const ws = new WebSocket(`${protocol}//${location.host}/ws/test-status/live?token=${encodeURIComponent(token)}`);
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.progress !== undefined) {
        $("progress-section").style.display = "block";
        $("progress-bar").style.width = `${data.progress}%`;
        $("progress-pct").textContent = `${Math.round(data.progress)}%`;
        if (data.status) $("progress-label").textContent = data.status;
        if (data.progress >= 100) {
          setTimeout(() => {
            $("progress-section").style.display = "none";
            loadDashboard();
          }, 2000);
        }
      }
    } catch { /* ignore non-JSON messages */ }
  };
  ws.onclose = () => { /* auto-reconnect handled by browser */ };
}

function applyTableFilters() {
  const q = ($("table-search")?.value || "").toLowerCase();
  const status = $("status-filter")?.value || "";
  document.querySelectorAll("#run-tbody tr").forEach(tr => {
    const textMatch = !q || tr.textContent?.toLowerCase().includes(q);
    const statusMatch = !status || tr.dataset.status === status;
    tr.style.display = textMatch && statusMatch ? "" : "none";
  });
}

function initTableSearch() {
  $("table-search")?.addEventListener("input", applyTableFilters);
  $("status-filter")?.addEventListener("change", applyTableFilters);
}

(async function init() {
  $("login-form")?.addEventListener("submit", handleLogin);
  $("logout-btn")?.addEventListener("click", handleLogout);
  $("generate-btn")?.addEventListener("click", handleGenerate);
  initThemeToggle();
  initTableSearch();

  const token = getToken();
  if (token) {
    try {
      await apiFetch("/api/v1/runs", { method: "GET" });
      await showDashboard();
      loadVersions();
      initDatePicker();
      initWebSocket();
    } catch (err) {
      clearToken();
      hideNavLinks();
    }
  } else {
    hideNavLinks();
  }
})();