const TOKEN_KEY = 'jwt_token'
const RUN_ID = (document.querySelector('meta[name="run-id"]') as HTMLMetaElement)?.content ?? ''
const JIRA_BASE_URL = (document.querySelector('meta[name="jira-base-url"]') as HTMLMetaElement)?.content ?? ''

function getToken(): string { return localStorage.getItem(TOKEN_KEY) ?? '' }
function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

function jiraLink(key: string, url?: string): string {
  const href = url ?? (JIRA_BASE_URL ? `${JIRA_BASE_URL}/browse/${key}` : '#')
  return `<a class="jira-anchor" href="${href}" target="_blank" rel="noopener">${key} ↗</a>`
}

function toast(msg: string, type: 'success' | 'error'): void {
  const el = document.createElement('div')
  el.className = `toast toast--${type}`
  el.textContent = msg
  document.body.appendChild(el)
  requestAnimationFrame(() => {
    el.classList.add('toast--in')
    setTimeout(() => {
      el.classList.remove('toast--in')
      el.addEventListener('transitionend', () => el.remove(), { once: true })
    }, 3200)
  })
}

// ── Run Rename ──
function setupRename(): void {
  const titleEl = document.getElementById('run-title')!
  const btn = document.getElementById('run-edit-btn')!
  const input = document.getElementById('run-edit-input') as HTMLInputElement

  btn.addEventListener('click', () => {
    titleEl.style.display = 'none'
    btn.style.display = 'none'
    input.style.display = ''
    input.focus()
    input.select()
  })

  async function save(): Promise<void> {
    const newName = input.value.trim()
    if (!newName) { cancel(); return }

    // Token kontrolü — rename için login şart
    if (!getToken()) {
      toast('Rename için önce giriş yapmalısınız', 'error')
      window.location.href = '/'
      return
    }

    try {
      const res = await fetch(`/api/v1/runs/${RUN_ID}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ displayName: newName }),
      })
      if (!res.ok) {
        if (res.status === 401) {
          toast('Oturum süresi doldu. Lütfen tekrar giriş yapın.', 'error')
          window.location.href = '/'
          return
        }
        throw new Error(`HTTP ${res.status}`)
      }
      toast('İsim güncellendi', 'success')
      location.reload()
    } catch (err) {
      toast(`Rename failed: ${err instanceof Error ? err.message : 'Unknown'}`, 'error')
      cancel()
    }
  }

  function cancel(): void {
    input.style.display = 'none'
    titleEl.style.display = ''
    btn.style.display = ''
  }

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') save()
    if (e.key === 'Escape') cancel()
  })
  input.addEventListener('blur', cancel)
}

// ── Bug Status ──
interface BugStatus { scenarioId: string; doorsAbsNumber?: string; jiraKey?: string; jiraUrl?: string; status?: string; isReported: boolean }

async function loadBugStatuses(): Promise<void> {
  const cards = document.querySelectorAll<HTMLElement>('[data-doors-number]')
  if (!cards.length) return
  try {
    const res = await fetch(`/api/v1/runs/${RUN_ID}/bug-status`, { headers: authHeaders() })
    if (!res.ok) return
    const statuses: BugStatus[] = await res.json()
    const map = new Map(statuses.map(s => [s.scenarioId, s]))
    cards.forEach(card => {
      const sid = card.dataset.scenarioId
      const statusEl = card.querySelector<HTMLElement>('[data-bug-status]')!
      const btn = card.querySelector<HTMLButtonElement>('[data-create-jira]')
      const keyEl = card.querySelector<HTMLElement>('[data-jira-key]')
      const info = map.get(sid!)
      if (!info) return
      if (info.isReported && info.jiraKey) {
        statusEl.innerHTML = `<span class="bug-pill bug-pill--open"><span class="bug-dot"></span>${jiraLink(info.jiraKey, info.jiraUrl)}<span class="bug-label">${info.status ?? 'OPEN'}</span></span>`
        if (btn) { btn.disabled = true; btn.textContent = 'Already Reported' }
        if (keyEl) { keyEl.innerHTML = jiraLink(info.jiraKey, info.jiraUrl); keyEl.style.display = 'inline-flex' }
      } else {
        statusEl.innerHTML = '<span class="bug-pill bug-pill--new">New — not yet reported</span>'
      }
    })
  } catch { /* silent */ }
}

// ── Jira Creation ──
async function createJira(btn: HTMLButtonElement): Promise<void> {
  const card = btn.closest<HTMLElement>('[data-scenario-id]')!
  const scenarioId = card.dataset.scenarioId!
  const statusEl = card.querySelector<HTMLElement>('[data-bug-status]')!
  const keyEl = card.querySelector<HTMLElement>('[data-jira-key]')!
  btn.disabled = true
  btn.textContent = 'Creating…'
  try {
    const res = await fetch(`/api/v1/runs/${RUN_ID}/scenarios/${scenarioId}/jira`, { method: 'POST', headers: authHeaders() })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(err.detail ?? `HTTP ${res.status}`)
    }
    const data = await res.json()
    keyEl.innerHTML = jiraLink(data.jiraKey, data.jiraUrl)
    keyEl.style.display = 'inline-flex'
    btn.textContent = 'Bug Created'
    btn.classList.add('btn--done')
    statusEl.innerHTML = `<span class="bug-pill bug-pill--open"><span class="bug-dot"></span>${jiraLink(data.jiraKey, data.jiraUrl)}<span class="bug-label">OPEN</span></span>`
    toast(`Jira bug oluşturuldu: ${data.jiraKey}`, 'success')
  } catch (err) {
    const msg = err instanceof Error ? err.message : 'Unknown error'
    btn.textContent = 'Hata — Tekrar Dene'
    btn.disabled = false
    toast(`Bug oluşturulamadı: ${msg}`, 'error')
  }
}

// ── Filters ──
function setupFilters(): void {
  const tabs = document.querySelectorAll<HTMLButtonElement>('.filter-tab')
  const cards = document.querySelectorAll<HTMLElement>('.scard')
  const countEl = document.getElementById('visible-count')
  const searchInput = document.getElementById('filter-input') as HTMLInputElement
  let currentFilter = 'all'

  function applyFilters(): void {
    const q = searchInput?.value.toLowerCase() ?? ''
    let visible = 0
    cards.forEach(card => {
      const status = card.dataset.status ?? ''
      const name = (card.querySelector('.scard-name')?.textContent ?? '').toLowerCase()
      const matchFilter = currentFilter === 'all' || status === currentFilter
      const matchSearch = !q || name.includes(q)
      const show = matchFilter && matchSearch
      card.style.display = show ? '' : 'none'
      if (show) visible++
    })
    if (countEl) countEl.textContent = String(visible)
  }

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'))
      tab.classList.add('active')
      currentFilter = tab.dataset.filter ?? 'all'
      applyFilters()
    })
  })
  searchInput?.addEventListener('input', applyFilters)
}

// ── Group Collapse ──
function setupGroups(): void {
  document.querySelectorAll<HTMLElement>('.tag-group-header').forEach(header => {
    header.addEventListener('click', () => {
      header.classList.toggle('collapsed')
      const body = header.nextElementSibling as HTMLElement
      if (body) body.style.display = header.classList.contains('collapsed') ? 'none' : ''
    })
  })
}

// ── Copy Error ──
function setupCopyButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('[data-copy-error]').forEach(btn => {
    btn.addEventListener('click', () => {
      const text = btn.dataset.copyError ?? ''
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent
        btn.textContent = 'Kopyalandı!'
        setTimeout(() => { btn.textContent = orig }, 1500)
      })
    })
  })
}

// ── Jira Buttons ──
function setupJiraButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('[data-create-jira]').forEach(btn => {
    btn.addEventListener('click', () => createJira(btn))
  })
}

// ── Retry Toggle ──
function setupRetryToggles(): void {
  document.querySelectorAll<HTMLElement>('[data-retry-toggle]').forEach(toggle => {
    toggle.addEventListener('click', () => {
      const list = toggle.nextElementSibling as HTMLElement
      if (list) list.style.display = list.style.display === 'none' ? '' : 'none'
    })
  })
}

// ── Lightbox ──
function setupLightbox(): void {
  document.querySelectorAll<HTMLImageElement>('.attachment-img').forEach(img => {
    img.addEventListener('click', () => {
      const overlay = document.createElement('div')
      overlay.className = 'lightbox'
      overlay.innerHTML = `<img src="${img.src}" alt="${img.alt}" class="lightbox-img">`
      overlay.addEventListener('click', () => overlay.remove())
      document.body.appendChild(overlay)
    })
  })
}

document.addEventListener('DOMContentLoaded', () => {
  loadBugStatuses()
  setupFilters()
  setupRename()
  setupJiraButtons()
  setupCopyButtons()
  setupGroups()
  setupRetryToggles()
  setupLightbox()
})