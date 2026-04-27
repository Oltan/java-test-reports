interface BugInfo {
  jiraKey: string
  status: string
  firstSeen: string
  lastSeen: string
  runIds: string[]
  scenarioName: string
}

interface JiraResponse {
  jiraKey: string
  jiraUrl?: string
}

const JIRA_BASE_URL = (document.querySelector('meta[name="jira-base-url"]') as HTMLMetaElement)?.content ?? ''
const RUN_ID = (document.querySelector('meta[name="run-id"]') as HTMLMetaElement)?.content ?? ''

function getToken(): string {
  return localStorage.getItem('jwt_token') ?? ''
}

function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

function jiraLink(key: string, url?: string): string {
  const href = url ?? (JIRA_BASE_URL ? `${JIRA_BASE_URL}/browse/${key}` : '#')
  return `<a class="jira-anchor" href="${href}" target="_blank" rel="noopener">${key} ↗</a>`
}

// ── Toast ──────────────────────────────────────────────────────────
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

// ── Bug statuses ───────────────────────────────────────────────────
async function loadBugStatuses(): Promise<void> {
  const cards = document.querySelectorAll<HTMLElement>('[data-doors-number]')
  await Promise.allSettled(
    Array.from(cards).map(async card => {
      const doorsNum = card.dataset.doorsNumber
      if (!doorsNum) return
      const statusEl = card.querySelector<HTMLElement>('[data-bug-status]')!
      const btn = card.querySelector<HTMLButtonElement>('[data-create-jira]')

      try {
        const res = await fetch(`/api/v1/bugs/${doorsNum}`, { headers: authHeaders() })
        if (res.ok) {
          const bug: BugInfo = await res.json()
          statusEl.innerHTML = `
            <span class="bug-pill bug-pill--open">
              <span class="bug-dot"></span>
              ${jiraLink(bug.jiraKey)}
              <span class="bug-label">${bug.status}</span>
            </span>`
          if (btn) { btn.disabled = true; btn.textContent = 'Already Reported' }
        } else if (res.status === 404) {
          statusEl.innerHTML = '<span class="bug-pill bug-pill--new">New — not yet reported</span>'
        } else {
          statusEl.innerHTML = '<span class="bug-pill bug-pill--unknown">Status unknown</span>'
        }
      } catch {
        statusEl.innerHTML = '<span class="bug-pill bug-pill--unknown">Status unknown</span>'
      }
    })
  )
}

// ── Create Jira bug ────────────────────────────────────────────────
async function createJira(btn: HTMLButtonElement): Promise<void> {
  const card = btn.closest<HTMLElement>('[data-scenario-id]')!
  const scenarioId = card.dataset.scenarioId!
  const statusEl = card.querySelector<HTMLElement>('[data-bug-status]')!
  const keyEl = card.querySelector<HTMLElement>('[data-jira-key]')!

  btn.disabled = true
  btn.textContent = 'Creating…'

  try {
    const res = await fetch(`/api/v1/runs/${RUN_ID}/scenarios/${scenarioId}/jira`, {
      method: 'POST',
      headers: authHeaders(),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }))
      throw new Error(err.detail ?? `HTTP ${res.status}`)
    }

    const data: JiraResponse = await res.json()
    keyEl.innerHTML = jiraLink(data.jiraKey, data.jiraUrl)
    keyEl.style.display = 'inline-flex'
    btn.textContent = 'Bug Created'
    btn.classList.add('btn--done')

    statusEl.innerHTML = `
      <span class="bug-pill bug-pill--open">
        <span class="bug-dot"></span>
        ${jiraLink(data.jiraKey, data.jiraUrl)}
        <span class="bug-label">OPEN</span>
      </span>`

    toast(`Jira bug oluşturuldu: ${data.jiraKey}`, 'success')
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error'
    btn.textContent = 'Hata — Tekrar Dene'
    btn.disabled = false
    toast(`Bug oluşturulamadı: ${msg}`, 'error')
  }
}

// ── Filter ─────────────────────────────────────────────────────────
function setupFilter(): void {
  const inp = document.getElementById('filter-input') as HTMLInputElement | null
  const countEl = document.getElementById('visible-count')
  const cards = document.querySelectorAll<HTMLElement>('[data-scenario-id]')

  inp?.addEventListener('input', () => {
    const q = inp.value.toLowerCase()
    let visible = 0
    cards.forEach(card => {
      const match = (card.querySelector('.card-title')?.textContent ?? '').toLowerCase().includes(q)
      card.style.display = match ? '' : 'none'
      if (match) visible++
    })
    if (countEl) countEl.textContent = String(visible)
  })
}

// ── Wire buttons ───────────────────────────────────────────────────
function setupButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('[data-create-jira]').forEach(btn => {
    btn.addEventListener('click', () => createJira(btn))
  })
}

// ── Copy error ─────────────────────────────────────────────────────
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

document.addEventListener('DOMContentLoaded', () => {
  loadBugStatuses()
  setupFilter()
  setupButtons()
  setupCopyButtons()
})
