# DOORS Numarasına Bağlı Jira Bug Takibi

## TL;DR

> **Quick Summary**: Her test senaryosunun DOORS Absolute Number'ını kullanarak Jira bug'larını takip eden sistem. Aynı DOORS numarası için mükerrer bug açmayı engeller, eski bug'ları eşler, web arayüzde durumunu gösterir.
>
> **Deliverables**:
> - `bug-tracker.json` dosya tabanlı eşleme deposu
> - DOORS numarasına göre Jira bug sorgulama
> - Web arayüzde bug durumu göstergesi (yeni / mevcut / kapalı)
> - Mükerrer bug engelleme
>
> **Estimated Effort**: Short (~1 gün)
> **Parallel Execution**: 3 task paralel çalışabilir

---

## 1. Vizyon

Mevcut sistemde Jira bug'ları her seferinde yeni açılıyor. DOORS Absolute Number'ları (örn: `DOORS-12345`) kalıcı kimlik olarak kullanıp:

```
Test koştu → senaryo fail etti → DOORS-12345
    │
    ├─ bug-tracker.json'da DOORS-12345 var mı?
    │   ├─ EVET → mevcut Jira key'ini göster (PROJ-456)
    │   │         → Jira'da issue'nun hâlâ açık mı kapalı mı olduğunu kontrol et
    │   │         → Web UI'da durumu göster: "🔁 Daha önce açılmış: PROJ-456 (Open)"
    │   │
    │   └─ HAYIR → "Create Jira Bug" butonu aktif
    │              → Mühendis tıklar → yeni bug açılır
    │              → DOORS-12345 → PROJ-789 eşlemesi kaydedilir
    │
    └─ DOORS DXl: "Test Sonucu XX" attribute'u güncellenir
```

---

## 2. Teknik Tasarım

### Bug Tracker JSON Şeması

```json
{
  "version": "1.0",
  "mappings": {
    "DOORS-12345": {
      "jiraKey": "PROJ-456",
      "status": "OPEN",
      "firstSeen": "2026-04-20T10:30:00Z",
      "lastSeen": "2026-04-26T17:00:00Z",
      "scenarioName": "Hatalı giriş",
      "runIds": ["20260420-001", "20260426-test-001"],
      "resolution": null
    },
    "DOORS-67890": {
      "jiraKey": "PROJ-789",
      "status": "CLOSED",
      "firstSeen": "2026-04-15T09:00:00Z",
      "lastSeen": "2026-04-20T12:00:00Z",
      "scenarioName": "Ödeme hatası",
      "runIds": ["20260415-001"],
      "resolution": "Fixed in v2.3.1"
    }
  }
}
```

### Veri Akışı

```
┌──────────────┐     ┌────────────────┐     ┌─────────────┐
│  Web UI      │────▶│  FastAPI       │────▶│ bug-tracker │
│  Triage      │     │  /api/v1/bugs  │     │  .json      │
│  Sayfası     │◀────│  GET/POST      │◀────│             │
└──────────────┘     └───────┬────────┘     └─────────────┘
                             │
                             ▼
                      ┌─────────────┐
                      │  Jira API   │
                      │ (isteğe     │
                      │  bağlı)     │
                      └─────────────┘
```

### Yeni API Endpoint'leri

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| `GET` | `/api/v1/bugs` | Tüm bug eşleşmelerini listele |
| `GET` | `/api/v1/bugs/{doorsNumber}` | DOORS numarasına göre bug durumu |
| `POST` | `/api/v1/bugs/{doorsNumber}/create` | Yeni Jira bug aç + eşlemeyi kaydet |
| `POST` | `/api/v1/bugs/{doorsNumber}/refresh` | Jira'dan güncel durumu çek |

---

## 3. İş Paketleri

### Task 1: Bug Tracker Service (Java — report-model modülü)

**Süre**: ~3 saat

- [x] `BugTracker.java`: JSON dosya oku/yaz, thread-safe
- [x] `BugMapping.java`: DTO (doorsNumber, jiraKey, status, timestamps)
- [x] `BugTrackerService.java`: 
  - `getMapping(doorsNumber)` → Optional<BugMapping>
  - `registerMapping(doorsNumber, jiraKey, scenarioName, runId)` → void
  - `updateStatus(doorsNumber, newStatus)` → void
  - `getAllMappings()` → List<BugMapping>
- [x] `BugTrackerServiceTest.java`: unit testler
- [x] `mvn -q -pl report-model test` → all pass

### Task 2: FastAPI Bug Endpoint'leri (Python)

**Süre**: ~2 saat

- [x] `server.py`'ye yeni endpoint'ler:
  - `GET /api/v1/bugs` → `bug-tracker.json` oku, tüm mapping'leri dön
  - `GET /api/v1/bugs/{doorsNumber}` → tek mapping dön (200) veya 404
  - `POST /api/v1/bugs/{doorsNumber}/create` → Jira bug aç + mapping kaydet
- [x] `BugTrackerStore` sınıfı: JSON okuma/yazma (thread-safe file lock)
- [x] `pytest tests/test_bugs.py -v` → en az 4 test

### Task 3: Web UI Güncelleme (Triage Sayfası)

**Süre**: ~2 saat

- [x] `triage.html` güncelleme:
  - Her hata kartında bug durumu göstergesi:
    - 🟢 "Yeni hata — bug açılmadı" → "Create Jira Bug" butonu aktif
    - 🟡 "PROJ-456 (Open) — 🔁 Daha önce açılmış" → buton pasif, Jira linki
    - 🔴 "PROJ-789 (Closed) — ✅ Kapatılmış" → yeniden açma opsiyonu
  - DOORS numarası her kartta görünür
  - "Tüm bug'ları gör" linki
- [x] JavaScript (`static/triage.js`): sayfa yüklemede bug durumlarını API'den çek
- [x] `data-testid="bug-status"`, `data-testid="jira-link"`
- [x] pytest: triage sayfası bug durumlarını doğru gösteriyor

---

## 4. Test Stratejisi

| Task | Test Türü | Araç |
|------|----------|------|
| Task 1 | Unit test | JUnit 5 |
| Task 2 | API test | FastAPI TestClient |
| Task 3 | UI test | FastAPI TestClient (HTML assertion) |

---

## 5. Commit Planı

```
feat(bug-tracker): add BugTrackerService with file-based DOORS→Jira mapping
feat(fastapi): add /api/v1/bugs endpoints for bug mapping CRUD
feat(web): show bug status on triage page — new/existing/closed indicators
```

---

## 6. Kabul Kriterleri

- [x] Aynı DOORS numarasıyla ikinci kez bug açılamaz
- [x] Web UI'da her hata kartında bug durumu görünür
- [x] `bug-tracker.json` dosyası proje kökünde, insan-okunabilir
- [x] Mevcut tüm testler bozulmaz (`mvn test` + `pytest`)
- [x] DOORS numarası olmayan senaryolarda sistem çökmez (graceful)
- [x] `bug-tracker.json` bozuk/eksik olsa bile sistem açılır (boş mapping ile başlar)
