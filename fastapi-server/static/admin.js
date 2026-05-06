import { C as Chart, r as registerables } from "./vendor.js";
Chart.register(...registerables);

const TOKEN_KEY = "jwt_token";
let liveProgressSocket = null;

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
    document.cookie = `access_token=${data.token}; path=/; SameSite=Lax`;
    showAdmin();
  } catch {
    errorEl.textContent = "Geçersiz kullanıcı adı veya şifre";
  } finally {
    btn.disabled = false;
    btn.textContent = "Giriş Yap";
  }
}

function handleLogout() {
  clearToken();
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

function showAdmin() {
  $("auth-gate").style.display = "none";
  $("admin-content").style.display = "block";
  showNavLinks();
  loadRunningTests();
  loadJobHistory();
  loadVersions();
  setInterval(loadRunningTests, 5000);
  setInterval(loadJobHistory, 15000);
}

function connectTestRunWebSocket(runId) {
  // Connect WebSocket for live test progress
  if (!runId) { console.log("[WS] runId empty, returning"); return; }
  if (liveProgressSocket) { console.log("[WS] closing old socket"); liveProgressSocket.close(); }

  const progress = $("live-progress");
  const output = $("live-output");
  if (progress) progress.style.display = "block";
  if ($("live-passed")) $("live-passed").textContent = "0";
  if ($("live-failed")) $("live-failed").textContent = "0";
  if ($("live-running")) $("live-running").textContent = "0";
  if ($("live-pct")) $("live-pct").textContent = "0%";
  if (output) output.textContent = "";

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const token = getToken();
  const wsUrl = `${protocol}://${location.host}/ws/test-status/${runId}?token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(wsUrl);
  liveProgressSocket = ws;
  ws.onopen = () => {};
  ws.onerror = () => {};
  ws.onclose = () => {};
  ws.onmessage = (e) => {
    try {
      const raw = JSON.parse(e.data);
      const d = raw.data || raw;
      if (raw.type === "progress" || d.type === "progress" || raw.type === "update") {
        if ($("live-passed")) $("live-passed").textContent = d.passed ?? 0;
        if ($("live-failed")) $("live-failed").textContent = d.failed ?? 0;
        if ($("live-running")) $("live-running").textContent = d.running ?? 0;
        if ($("live-pct")) $("live-pct").textContent = `${d.pct ?? 0}%`;
        if (output) {
          output.textContent = (d.output || []).slice(-50).join("\n");
          output.scrollTop = output.scrollHeight;
        }
      } else if (raw.type === "complete" || d.type === "complete") {
        if ($("live-pct")) $("live-pct").textContent = "100% - Tamamlandı!";
        if (output && d.output) output.textContent = d.output.slice(-50).join("\n");
        setTimeout(() => {
          loadRunningTests();
          loadJobHistory();
        }, 1500);
      }
    } catch (err) {
      console.error("[WS] onmessage error:", err);
    }
  };
  ws.onerror = (e) => {
    console.log("[WS] Connection error:", e);
    if ($("test-status-msg")) {
      $("test-status-msg").textContent = "WebSocket bağlantısı kurulamadı";
      $("test-status-msg").className = "admin-status-msg admin-status--error";
    }
  };
}

async function startTestRun() {
  const tags = $("test-tags")?.value || "@smoke";
  const retry = parseInt($("test-retry")?.value || "0");
  const parallel = parseInt($("test-parallel")?.value || "1");
  const environment = $("test-env")?.value || "staging";
  const version = $("test-version")?.value || undefined;
  const msg = $("test-status-msg");
  try {
    msg.textContent = "Başlatılıyor…";
    msg.className = "admin-status-msg admin-status--pending";
    const body = { tags, retry_count: retry, parallel, environment };
    if (version) body.version = version;
    const data = await apiFetch("/api/tests/start", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const workerCount = data.workers?.length || data.runs?.length || 1;
    const modeLabel = data.mode === "serialized_safe" ? "seri-güvenli" : data.mode || "paralel";
    msg.textContent = `İş başlatıldı — ${data.job_id} · ${workerCount} worker · ${modeLabel}`;
    msg.className = "admin-status-msg admin-status--success";
    const firstRunId = data.workers?.[0]?.run_id || data.runs?.[0];
    connectTestRunWebSocket(firstRunId);
    setTimeout(() => { loadRunningTests(); loadJobHistory(); }, 2000);
  } catch (e) {
    msg.textContent = `Hata: ${e.message}`;
    msg.className = "admin-status-msg admin-status--error";
  }
}

async function triggerPipeline() {
  const msg = $("pipeline-status-msg");
  const statusDiv = $("pipeline-status");
  try {
    msg.textContent = "Pipeline başlatılıyor…";
    msg.className = "admin-status-msg admin-status--pending";
    const data = await apiFetch("/api/pipeline/run", { method: "POST" });
    msg.textContent = "Pipeline başlatıldı";
    msg.className = "admin-status-msg admin-status--success";
    statusDiv.innerHTML = `<div class="admin-pipeline-result-inner">
      Pipeline çalışıyor — Run ID: <strong>${data.run_id}</strong>
    </div>`;
  } catch (e) {
    msg.textContent = `Hata: ${e.message}`;
    msg.className = "admin-status-msg admin-status--error";
  }
}

function renderWorkerStatusBadge(status) {
  const map = {
    running: { label: "çalışıyor", cls: "worker-badge--running" },
    completed: { label: "tamamlandı", cls: "worker-badge--completed" },
    cancelled: { label: "iptal", cls: "worker-badge--cancelled" },
    failed: { label: "başarısız", cls: "worker-badge--failed" },
  };
  const info = map[status] || { label: status, cls: "worker-badge--unknown" };
  return `<span class="worker-badge ${info.cls}">${info.label}</span>`;
}

function renderJobCard(job, showCancel = false) {
  const tags = job.tags || "";
  const retry = job.retry_count ?? 0;
  const parallel = job.parallel ?? 1;
  const env = job.environment || "";
  const version = job.version || "";
  const status = job.status || "unknown";
  const startedAt = job.started_at ? new Date(job.started_at).toLocaleString("tr-TR") : "";

  const statusMap = {
    running: { label: "Çalışıyor", cls: "job-status--running" },
    completed: { label: "Tamamlandı", cls: "job-status--completed" },
    cancelled: { label: "İptal Edildi", cls: "job-status--cancelled" },
  };
  const statusInfo = statusMap[status] || { label: status, cls: "job-status--unknown" };

  let workersHtml = "";
  if (job.workers && job.workers.length > 0) {
    workersHtml = `<div class="job-workers">
      ${job.workers.map(w => `
        <div class="job-worker-row">
          <span class="worker-shard">Shard ${w.shard}</span>
          <span class="worker-run-id">${w.run_id}</span>
          ${renderWorkerStatusBadge(w.status)}
        </div>
      `).join("")}
    </div>`;
  }

  const cancelBtn = showCancel && status === "running"
    ? `<button class="cancel-btn" onclick="window.cancelJob('${job.job_id}')">İptal</button>`
    : "";

  const flakyInfo = status === "completed" && job.flaky_count !== undefined
    ? `<div class="job-summary-stats">
        ${job.flaky_count > 0 ? `<span class="stat-flaky">Flaky: ${job.flaky_count}</span>` : ""}
        ${job.retry_total > 0 ? `<span class="stat-retry">Retry: ${job.retry_total}</span>` : ""}
        ${job.flaky_count === 0 && job.retry_total === 0 ? `<span class="stat-stable">✓ Stabil</span>` : ""}
      </div>`
    : "";

  return `
    <div class="job-card ${status === "running" ? "job-card--active" : ""}">
      <div class="job-card-header">
        <div class="job-card-meta">
          <span class="job-id">${job.job_id}</span>
          <span class="job-status-badge ${statusInfo.cls}">${statusInfo.label}</span>
        </div>
        ${cancelBtn}
      </div>
      <div class="job-card-details">
        ${tags ? `<span class="job-tag">${tags}</span>` : ""}
        ${retry > 0 ? `<span class="job-detail">Retry: ${retry}</span>` : ""}
        <span class="job-detail">Paralel: ${parallel}</span>
        ${env ? `<span class="job-detail">${env}</span>` : ""}
        ${version ? `<span class="job-detail">${version}</span>` : ""}
        ${startedAt ? `<span class="job-detail job-detail--time">${startedAt}</span>` : ""}
      </div>
      ${workersHtml}
      ${flakyInfo}
    </div>
  `;
}

async function loadRunningTests() {
  const container = $("running-tests-list");
  try {
    const data = await apiFetch("/api/tests/running");
    if (!data.jobs || data.jobs.length === 0) {
      container.innerHTML = '<div class="running-tests-empty">Aktif test yok</div>';
      return;
    }
    container.innerHTML = data.jobs.map(job => renderJobCard(job, true)).join("");
  } catch {
    container.innerHTML = '<div class="running-tests-empty">Yüklenemedi</div>';
  }
}

async function loadJobHistory() {
  const container = $("job-history-list");
  try {
    const data = await apiFetch("/api/tests/jobs");
    if (!data.jobs || data.jobs.length === 0) {
      container.innerHTML = '<div class="running-tests-empty">Henüz iş yok</div>';
      return;
    }
    const completedJobs = data.jobs.filter(j => j.status !== "running");
    if (completedJobs.length === 0) {
      container.innerHTML = '<div class="running-tests-empty">Tamamlanmış iş yok</div>';
      return;
    }
    container.innerHTML = completedJobs.map(job => renderJobCard(job, false)).join("");
  } catch {
    container.innerHTML = '<div class="running-tests-empty">Yüklenemedi</div>';
  }
}

async function cancelJob(jobId) {
  try {
    await apiFetch(`/api/tests/job/${jobId}/cancel`, { method: "POST" });
    loadRunningTests();
    loadJobHistory();
  } catch (e) {
    console.error("Cancel failed:", e);
  }
}

async function cancelTest(runId) {
  try {
    await apiFetch(`/api/tests/${runId}/cancel`, { method: "POST" });
    loadRunningTests();
    loadJobHistory();
  } catch (e) {
    console.error("Cancel failed:", e);
  }
}

async function loadVersions() {
  const list = $("version-list");
  try {
    const data = await apiFetch("/api/versions");
    if (!data.versions || data.versions.length === 0) {
      list.innerHTML = '<li style="color:var(--text-muted);">Versiyon bulunamadı</li>';
      return;
    }
    list.innerHTML = data.versions.map(v => `
      <li>
        <span>${v}</span>
        <span class="version-count">mevcut</span>
      </li>
    `).join("");
  } catch {
    list.innerHTML = '<li style="color:var(--text-muted);">Yüklenemedi</li>';
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
  });
}

window.cancelTest = cancelTest;
window.cancelJob = cancelJob;

(async function init() {
  $("login-form")?.addEventListener("submit", handleLogin);
  $("logout-btn")?.addEventListener("click", handleLogout);
  $("start-test-btn")?.addEventListener("click", startTestRun);
  $("pipeline-btn")?.addEventListener("click", triggerPipeline);
  initThemeToggle();

  const token = getToken();
  if (token) {
    try {
      await apiFetch("/api/v1/runs", { method: "GET" });
      showAdmin();
    } catch (err) {
      clearToken();
      hideNavLinks();
    }
  } else {
    hideNavLinks();
  }
})();