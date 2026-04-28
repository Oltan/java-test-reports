import { Chart, registerables } from 'chart.js'
Chart.register(...registerables)

interface ScenarioInfo {
  attempts?: { status: string }[]
  dependencies?: string[]
}

interface Run {
  runId: string
  timestamp: string
  totalScenarios: number
  passed: number
  failed: number
  skipped: number
  duration: string
  scenarios?: ScenarioInfo[]
}

const TOKEN_KEY = 'jwt_token'

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t)
}
function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

function el<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T
}

async function apiFetch<T>(url: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> ?? {}),
  }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(url, { ...init, headers })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<T>
}

// ── Login ──────────────────────────────────────────────────────────
async function handleLogin(e: Event): Promise<void> {
  e.preventDefault()
  const form = e.target as HTMLFormElement
  const username = (form.querySelector('#username') as HTMLInputElement).value
  const password = (form.querySelector('#password') as HTMLInputElement).value
  const errEl = el('login-error')
  const btn = form.querySelector('button[type="submit"]') as HTMLButtonElement

  errEl.textContent = ''
  btn.disabled = true
  btn.textContent = 'Giriş yapılıyor…'

  try {
    const data = await apiFetch<{ token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
    setToken(data.token)
    showDashboard()
  } catch {
    errEl.textContent = 'Geçersiz kullanıcı adı veya şifre'
  } finally {
    btn.disabled = false
    btn.textContent = 'Giriş Yap'
  }
}

function logout(): void {
  clearToken()
  location.reload()
}

function showDashboard(): void {
  el('login-section').style.display = 'none'
  el('dashboard-content').style.display = 'block'
  loadData()
}

// ── Animated counter ───────────────────────────────────────────────
function animateCount(target: HTMLElement, value: number, suffix = ''): void {
  const dur = 700
  const t0 = Date.now()
  const tick = (): void => {
    const p = Math.min((Date.now() - t0) / dur, 1)
    const ease = 1 - Math.pow(1 - p, 3)
    target.textContent = Math.round(ease * value) + suffix
    if (p < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

// ── Charts ─────────────────────────────────────────────────────────
let charts: Chart[] = []

function destroyCharts(): void {
  charts.forEach(c => c.destroy())
  charts = []
}

function renderPieChart(run: Run): void {
  const ctx = (el('pieChart') as HTMLCanvasElement).getContext('2d')!
  const total = run.totalScenarios || 1
  charts.push(
    new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['Passed', 'Failed', 'Skipped'],
        datasets: [{
          data: [run.passed, run.failed, run.skipped],
          backgroundColor: ['#22c55e', '#ef4444', '#64748b'],
          borderColor: '#1e293b',
          borderWidth: 3,
          hoverOffset: 10,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '74%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#94a3b8', padding: 20, font: { size: 13 } },
          },
          tooltip: {
            callbacks: {
              label: ctx => ` ${ctx.label}: ${ctx.parsed} (${Math.round(ctx.parsed / total * 100)}%)`,
            },
          },
        },
      },
    })
  )
}

function renderBarChart(runs: Run[]): void {
  const slice = [...runs].reverse().slice(-12)
  const ctx = (el('barChart') as HTMLCanvasElement).getContext('2d')!
  charts.push(
    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: slice.map(r => r.runId.slice(-6)),
        datasets: [
          { label: 'Passed',  data: slice.map(r => r.passed),  backgroundColor: 'rgba(34,197,94,0.85)',  borderRadius: 4, borderSkipped: false },
          { label: 'Failed',  data: slice.map(r => r.failed),  backgroundColor: 'rgba(239,68,68,0.85)',  borderRadius: 4, borderSkipped: false },
          { label: 'Skipped', data: slice.map(r => r.skipped), backgroundColor: 'rgba(100,116,139,0.6)', borderRadius: 4, borderSkipped: false },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#94a3b8', font: { size: 12 } } },
        },
        scales: {
          x: { stacked: true, ticks: { color: '#64748b', font: { size: 11 } }, grid: { display: false } },
          y: { stacked: true, ticks: { color: '#64748b' }, grid: { color: 'rgba(51,65,85,0.5)' }, border: { display: false } },
        },
      },
    })
  )
}

// ── Metrics ────────────────────────────────────────────────────────
function renderMetrics(runs: Run[]): void {
  const latest = runs[0]
  const rate = Math.round((latest.passed / (latest.totalScenarios || 1)) * 100)
  animateCount(el('metric-rate'), rate, '%')
  animateCount(el('metric-total'), runs.length)

  const avg = runs.reduce((s, r) => s + parseFloat(r.duration || '0'), 0) / runs.length
  el('metric-avg').textContent = avg.toFixed(1) + 's'

  const trendEl = el('metric-trend')
  if (runs.length >= 2) {
    const delta =
      (runs[0].passed / (runs[0].totalScenarios || 1) -
        runs[1].passed / (runs[1].totalScenarios || 1)) * 100
    trendEl.textContent = (delta >= 0 ? '▲ +' : '▼ ') + Math.abs(delta).toFixed(1) + '%'
    trendEl.className = 'metric-value ' + (delta >= 0 ? 'trend-up' : 'trend-down')
  } else {
    trendEl.textContent = '—'
  }
}

// ── Run table ──────────────────────────────────────────────────────
function renderTable(runs: Run[]): void {
  const tbody = el('run-tbody')
  tbody.innerHTML = runs.slice(0, 20).map(r => {
    const date = new Date(r.timestamp).toLocaleString('tr-TR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
    const rate = Math.round((r.passed / (r.totalScenarios || 1)) * 100)
    const ok = r.failed === 0
    const retryCount = (r.scenarios ?? []).filter(s => (s.attempts?.length ?? 0) > 1).length
    const hasDeps = (r.scenarios ?? []).some(s => (s.dependencies?.length ?? 0) > 0)
    return `
      <tr>
        <td><a class="run-link" href="/reports/${r.runId}">${r.runId.slice(0, 22)}</a></td>
        <td class="td-muted">${date}</td>
        <td><span class="badge badge-pass">${r.passed}</span></td>
        <td><span class="badge badge-fail">${r.failed}</span></td>
        <td>
          <div class="prog-wrap">
            <div class="prog-bar" style="width:${rate}%"></div>
          </div>
          <span class="prog-label">${rate}%</span>
        </td>
        <td class="td-muted">${parseFloat(r.duration).toFixed(1)}s</td>
        <td>${retryCount > 0 ? `<span class="badge badge-retry">${retryCount} retried</span>` : '<span class="td-muted">—</span>'}</td>
        <td>${hasDeps ? '<span class="badge badge-dep">⛓️ has deps</span>' : '<span class="td-muted">—</span>'}</td>
        <td><span class="status-pill ${ok ? 'pill-pass' : 'pill-fail'}">${ok ? 'PASSED' : 'FAILED'}</span></td>
        <td><a class="action-link" href="/reports/${r.runId}/triage">Triage →</a></td>
      </tr>`
  }).join('')
}

function showEmpty(): void {
  el('dashboard-content').innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📊</div>
      <h2>Henüz test çalıştırılmadı</h2>
      <p>İlk test koşusu tamamlandığında burada görüntülenecek.</p>
    </div>`
}

// ── Load ───────────────────────────────────────────────────────────
async function loadData(): Promise<void> {
  try {
    const runs = await apiFetch<Run[]>('/api/v1/runs')
    if (!runs || runs.length === 0) { showEmpty(); return }
    destroyCharts()
    renderMetrics(runs)
    renderPieChart(runs[0])
    renderBarChart(runs)
    renderTable(runs)
  } catch (e) {
    console.error('Failed to load runs:', e)
  }
}

// ── Table search ───────────────────────────────────────────────────
function setupSearch(): void {
  const inp = document.getElementById('table-search') as HTMLInputElement | null
  inp?.addEventListener('input', () => {
    const q = inp.value.toLowerCase()
    document.querySelectorAll<HTMLTableRowElement>('#run-tbody tr').forEach(row => {
      row.style.display = row.textContent?.toLowerCase().includes(q) ? '' : 'none'
    })
  })
}

// ── Init ───────────────────────────────────────────────────────────
;(function init(): void {
  el('login-form')?.addEventListener('submit', handleLogin)
  el('logout-btn')?.addEventListener('click', logout)
  setupSearch()

  const token = getToken()
  if (token) {
    apiFetch<Run[]>('/api/v1/runs')
      .then(() => showDashboard())
      .catch(() => { clearToken() })
  }
})()