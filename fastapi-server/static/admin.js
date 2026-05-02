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
  location.reload();
}

function showAdmin() {
  $("auth-gate").style.display = "none";
  $("admin-content").style.display = "block";
  loadRunningTests();
  loadVersions();
  setInterval(loadRunningTests, 5000);
}

function connectTestRunWebSocket(runId) {
  if (!runId) return;
  if (liveProgressSocket) liveProgressSocket.close();

  const progress = $("live-progress");
  const output = $("live-output");
  if (progress) progress.style.display = "block";
  if ($("live-passed")) $("live-passed").textContent = "0";
  if ($("live-failed")) $("live-failed").textContent = "0";
  if ($("live-running")) $("live-running").textContent = "0";
  if ($("live-pct")) $("live-pct").textContent = "0%";
  if (output) output.textContent = "";

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${location.host}/ws/test-status/${runId}`);
  liveProgressSocket = ws;
  ws.onmessage = (e) => {
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
      setTimeout(() => location.reload(), 2000);
    }
  };
  ws.onerror = () => {
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
    msg.textContent = `${data.runs?.length || 0} test başlatıldı`;
    msg.className = "admin-status-msg admin-status--success";
    connectTestRunWebSocket(data.runs?.[0]);
    setTimeout(() => loadRunningTests(), 2000);
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

async function loadRunningTests() {
  const list = $("running-tests-list");
  try {
    const data = await apiFetch("/api/tests/running");
    if (!data.running || data.running.length === 0) {
      list.innerHTML = '<li class="running-tests-empty">Aktif test yok</li>';
      return;
    }
    list.innerHTML = data.running.map(id => `
      <li>
        <span class="running-test-id">${id}</span>
        <button class="cancel-btn" onclick="window.cancelTest('${id}')">İptal</button>
      </li>
    `).join("");
  } catch {
    list.innerHTML = '<li class="running-tests-empty">Yüklenemedi</li>';
  }
}

async function cancelTest(runId) {
  try {
    await apiFetch(`/api/tests/${runId}/cancel`, { method: "POST" });
    loadRunningTests();
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

(function init() {
  $("login-form")?.addEventListener("submit", handleLogin);
  $("logout-btn")?.addEventListener("click", handleLogout);
  $("start-test-btn")?.addEventListener("click", startTestRun);
  $("pipeline-btn")?.addEventListener("click", triggerPipeline);
  initThemeToggle();

  if (getToken()) {
    showAdmin();
  }
})();
