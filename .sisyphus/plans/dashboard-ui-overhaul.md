# Dashboard UI Overhaul + MCP Entegrasyonu

## TL;DR

> **Quick Summary**: Test raporlama dashboard'unu modern chart'larla (pie/bar) yeniden tasarla, MCP araçlarını kur (playwright, chrome-devtools), görsel QA yap, entegrasyon rehberi hazırla.
>
> **Deliverables**:
> - Chart.js tabanlı modern dashboard (pie + bar charts, metric cards, dark theme, 1080p)
> - Playwright MCP kurulumu + screenshot testi
> - Chrome DevTools MCP kurulumu
> - Görsel kendini puanlama (AI model ile)
> - Detaylı entegrasyon rehberi
>
> **Estimated Effort**: Medium (~2 gün)
> **Parallel Execution**: YES — 2 waves, 4-5 task/wave

---

## 1. Vizyon

Mevcut basit dashboard'u, profesyonel test raporlama araçları seviyesinde modern bir arayüze dönüştürmek:

```
┌─────────────────────────────────────────────────────────┐
│  🏠 Test Raporlama Sistemi            🔑 admin         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────┐ │
│  │ ✅ 67%   │ │ 📊 4 Run │ │ ⏱ 8.2s  │ │ 📈 +12%   │ │
│  │ Success  │ │  Total   │ │ Avg      │ │ vs Last   │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────────┘ │
│                                                          │
│  ┌─────────────────────┐  ┌──────────────────────────┐ │
│  │   🍩 Pass/Fail Dağılımı   │  📊 Run Bazında Karşılaştırma   │ │
│  │     (pie chart)     │  │     (bar chart)           │ │
│  │                     │  │  ████████░░ ✅ passed     │ │
│  │    🟩 67% passed    │  │  ███░░░░░░░ ❌ failed     │ │
│  │    🟥 33% failed    │  │  ░░░░░░░░░░ ⏭ skipped    │ │
│  │                     │  │  Run1 Run2 Run3 Run4      │ │
│  └─────────────────────┘  └──────────────────────────┘ │
│                                                          │
│  📋 Son Run'lar                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │ live-demo-001 │ ✅2 ❌1 │ 8.2s │ 30 dk önce       │ │
│  │ 20260426-test │ ✅2 ❌1 │ 8.2s │ 1 saat önce      │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Teknik Tasarım

### Chart Kütüphanesi: Chart.js

- **Neden**: Hafif (60KB gzipped), pie/bar/doughnut desteği, responsive, dark-theme uyumlu
- **Self-hosted**: `fastapi-server/static/chart.min.js` olarak bundle edilecek
- **CDN YOK**: Tamamen offline çalışır
- **Chart tipleri**:
  - `doughnut`: pass/fail/skip oranları (yuvarlak grafik)
  - `bar`: run bazında karşılaştırma (sıralı, yeşil/kırmızı/gri)

### MCP Araçları

| MCP | Komut | Amaç |
|-----|-------|------|
| playwright | `opencode mcp add playwright` | Tarayıcı otomasyonu, screenshot |
| chrome-devtools | `opencode mcp add chrome-devtools` | Chrome DevTools erişimi |

### UI Grid Layout (1080p)

```
1920 x 1080 çözünürlükte:
- Sol kolon (%35): Metric cards + past run listesi
- Sağ kolon (%65): Pie chart (üst) + Bar chart (alt)
- Header: başlık + login/logout
- Her kart: border-radius 12px, box-shadow, hover efekti
- Renk paleti: dark bg (#0f172a), surface (#1e293b), accent (#3b82f6)
```

---

## 3. İş Paketleri

### Wave 1: MCP Kurulumu + Temel Altyapı (Paralel)

#### Task 1: Playwright MCP Kurulumu

- [x] `opencode mcp add playwright` — Playwright MCP server ekle
- [x] Playwright tarayıcıları indir (`npx playwright install chromium`)
- [x] Test: `curl http://localhost:8000/` screenshot'ı al
- [x] Screenshot'ı `.sisyphus/evidence/dashboard-screenshot.png` kaydet
- [x] Görsel kalite puanlaması yap (1-10)

**Süre**: 1 saat  
**Bağımlılık**: Yok  
**QA**: Screenshot dosyası var mı? Bar chart, pie chart görünüyor mu?

#### Task 2: Chrome DevTools MCP Kurulumu

- [x] `opencode mcp add chrome-devtools` — Chrome DevTools MCP ekle
- [x] Test: console.log çıktılarını yakala, performans metriklerini al
- [x] Dashboard yüklenme süresini ölç (< 500ms hedef)

**Süre**: 30 dk  
**Bağımlılık**: Yok  
**QA**: `opencode mcp list` → chrome-devtools RUNNING

#### Task 3: Chart.js Bundle + Static Files

- [x] `chart.min.js` (v4.4.x) indir → `fastapi-server/static/chart.min.js`
- [x] FastAPI'ye `StaticFiles` mount ekle: `app.mount("/static", StaticFiles(directory="static"))`
- [x] Test: `curl http://localhost:8000/static/chart.min.js` → HTTP 200
- [x] CSS değişkenleri dosyası: `static/dashboard.css`

**Süre**: 30 dk  
**Bağımlılık**: Yok  
**QA**: JS ve CSS statik olarak servis ediliyor

---

### Wave 2: Dashboard UI Overhaul (Sıralı)

#### Task 4: Metric Cards Component

- [x] `templates/dashboard.html` yeniden yaz
- [x] 4 metric card: Success Rate, Total Runs, Avg Duration, Trend
- [x] Grid layout (CSS Grid), her kartta ikon + büyük sayı + alt metin
- [x] Responsive: 1080p'de yan yana, mobilde alt alta
- [x] Koyu tema renkleri

**Süre**: 1.5 saat  
**Bağımlılık**: Task 3  
**QA**: Playwright screenshot'ta metric card'lar görünüyor

#### Task 5: Pie Chart (Doughnut) — Pass/Fail/Skip

- [x] `/api/v1/runs/{id}/summary` endpoint'i (pass/fail/skip sayıları)
- [x] Chart.js doughnut chart: 3 segment (green/red/gray)
- [x] Ortada toplam senaryo sayısı
- [x] Legend: passed, failed, skipped + sayılar
- [x] Tooltip: hover'da detay

**Süre**: 1.5 saat  
**Bağımlılık**: Task 3  
**QA**: Chart render ediliyor, segmentler doğru oranlarda

#### Task 6: Bar Chart — Run Bazında Karşılaştırma

- [x] `/api/v1/runs/compare` endpoint'i (son N run'un pass/fail/skip verisi)
- [x] Chart.js stacked bar chart
- [x] Her run bir bar, içinde pass/fail/skip segmentleri
- [x] X ekseni: run ID (kısa), Y ekseni: senaryo sayısı
- [x] Renkler: passed=#16a34a, failed=#dc2626, skipped=#94a3b8
- [x] Sıralı: en yeni run en solda

**Süre**: 1.5 saat  
**Bağımlılık**: Task 3  
**QA**: Bar chart render ediliyor, run'lar kronolojik sıralı

#### Task 7: Son Run'lar Tablosu + Tasarım Final

- [x] Son 10 run'ı listeleyen tablo
- [x] Her satır: run ID, tarih, süre, pass/fail ikonları, link
- [x] Header: logo + başlık + login durumu
- [x] Footer: versiyon + GitHub linki
- [x] Responsive: 1080p optimize, min-width 1024px
- [x] Hover efektleri, geçiş animasyonları

**Süre**: 1.5 saat  
**Bağımlılık**: Task 4  
**QA**: Tam dashboard Playwright screenshot'ta profesyonel görünüyor

---

### Wave 3: QA + Rehber (Paralel)

#### Task 8: Görsel QA — Playwright Screenshot + Puanlama

- [x] Playwright ile `http://localhost:8000/` aç
- [x] Full page screenshot al
- [x] Screenshot'ı multimodal-looker agent'a gönder
- [x] Dashboard'u 1-10 arası puanla
- [x] Kriterler: renk uyumu, okunabilirlik, bilgi yoğunluğu, profesyonellik
- [x] Puan < 7 ise → Task 4-7'ye dön, düzelt

**Süre**: 1 saat  
**Bağımlılık**: Task 7, Task 1  
**QA**: Puanlama sonucu `.sisyphus/evidence/dashboard-score.md`

#### Task 9: Entegrasyon Rehberi

- [x] `ENTEGRASYON_REHBERI.md` oluştur
- [x] İçerik:
  - Proje yapısı ve bağımlılıklar
  - Maven `pom.xml`'e eklenecek dependency'ler
  - Cucumber `cucumber.properties` ayarları
  - Allure entegrasyonu (adım adım)
  - FastAPI sunucu kurulumu
  - CI/CD pipeline'a ekleme
  - DOORS/Jira entegrasyon konfigürasyonu
  - Örnek proje yapısı
  - Sık sorulan sorular

**Süre**: 2 saat  
**Bağımlılık**: Yok  
**QA**: Rehber takip edilerek sıfırdan entegrasyon yapılabiliyor mu?

---

## 4. Bağımlılık Grafiği

```
Wave 1 (Paralel):
  Task 1 (Playwright MCP) ─────────────┐
  Task 2 (Chrome DevTools MCP) ────────┤
  Task 3 (Chart.js + Static) ──────────┤
                                        │
Wave 2 (Sıralı):                       │
  Task 3 ──► Task 4 (Metric Cards) ──► Task 7 (Final) ──┤
  Task 3 ──► Task 5 (Pie Chart) ────────────────────────┤
  Task 3 ──► Task 6 (Bar Chart) ────────────────────────┤
                                                         │
Wave 3 (Paralel):                                        │
  Task 1 + Task 7 ──► Task 8 (QA + Puanlama)            │
  ───────────────► Task 9 (Entegrasyon Rehberi)         │
```

---

## 5. Commit Planı

```
feat(mcp): add Playwright + Chrome DevTools MCP servers
feat(dashboard): add Chart.js static bundle
feat(dashboard): metric cards with dark theme grid layout
feat(dashboard): doughnut pie chart for pass/fail/skip
feat(dashboard): stacked bar chart for run comparison
feat(dashboard): run history table + header/footer polish
qa(dashboard): Playwright screenshot + visual scoring
docs: entegrasyon rehberi — step-by-step integration guide
```

---

## 6. Kabul Kriterleri

- [x] Dashboard `http://localhost:8000/` 1080p'de profesyonel görünüyor
- [x] Pie chart: pass/fail/skip doğru oranlarda
- [x] Bar chart: run'lar kronolojik, segmentli
- [x] Metric card'lar: anlık veri gösteriyor
- [x] Playwright screenshot başarılı
- [x] Görsel puanlama ≥ 7/10
- [x] Entegrasyon rehberi adım adım takip edilebilir
- [x] Mevcut testler bozulmaz
- [x] Chart.js offline çalışır (CDN yok)
