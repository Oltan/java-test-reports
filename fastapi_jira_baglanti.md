# FastAPI Jira Bağlantı Rehberi

## 1. Mimari Özet

FastAPI sunucusu, test otomasyon sisteminde başarısız senaryolar için Jira issue oluşturmak amacıyla Jira Server/DC (Data Center) veya Jira Cloud ile entegre çalışır. Bağlantı, `atlassian-python-api` kütüphanesi üzerinden **PAT (Personal Access Token)** ile yapılır.

```
FastAPI Server → jira_client.py → atlassian.Jira → Jira REST API v2
                                    (PAT ile auth)
```

---

## 2. Konfigürasyon (.env)

Aşağıdaki ortam değişkenleri `fastapi-server/.env` dosyasında tanımlanmalıdır:

```bash
# Zorunlu
JIRA_URL=https://jira.sirket.local          # Jira Server/DC base URL
JIRA_PAT=your_personal_access_token_here     # Jira Personal Access Token
JIRA_PROJECT_KEY=TEST                        # Jira proje anahtarı

# Opsiyonel
JIRA_ISSUE_TYPE=Bug                          # Oluşturulacak issue tipi (default: Bug)
JIRA_RETRY_COUNT=3                           # API hatası durumunda retry sayısı
JIRA_DRY_RUN=false                           # Dry-run modu (gerçek Jira'ya yazmadan simüle et)
```

### Alternatif Değişken İsimleri

`jira_client.py` aşağıdaki aliasları da destekler:

| Birincil | Alternatif |
|----------|-----------|
| `JIRA_URL` | `JIRA_BASE_URL` |
| `JIRA_PROJECT_KEY` | `JIRA_PROJECT` |

---

## 3. Jira Client (`jira_client.py`)

### 3.1 Bağlantı Oluşturma

```python
from jira_client import JiraClient

# Ortam değişkenlerinden otomatik okur
client = JiraClient()

# Veya manuel parametrelerle
client = JiraClient(
    base_url="https://jira.sirket.local",
    pat="your_pat_here",
    project="TEST",
    issue_type="Bug",
    retry_count=3,
)
```

### 3.2 Temel Metodlar

| Metod | Amaç |
|-------|------|
| `is_configured()` | Jira bağlantısı yapılandırılmış mı? |
| `create_issue(summary, description, doors_number)` | Yeni bug oluşturur |
| `search_by_doors_number(doors_number)` | DOORS numarasına göre issue ara |
| `get_issue_status(issue_key)` | Issue durumunu getir |
| `add_comment(issue_key, comment)` | Issue'a yorum ekle |
| `attach_screenshot(issue_key, filepath)` | Ekran görüntüsü ekle |
| `issue_url(key)` | Issue URL'si üret |

### 3.3 Retry Mekanizması

Tüm Jira API çağrıları otomatik retry ile çalışır:
- Varsayılan: **3 deneme**
- Backoff: `0.5s, 1s, 2s` (exponential)
- Son denemede hata verilir

### 3.4 Dry-Run Modu

Gerçek Jira'ya yazmadan test etmek için:

```bash
export JIRA_DRY_RUN=true
# veya
export DRY_RUN=true
```

Dry-run modunda:
- Issue key: `DRY-{hash[:8]}` formatında üretilir
- URL: `https://dry-run.local/browse/DRY-abc12345`
- `JIRA_DRY_RUN_RESULT=failure` ile hata simülasyonu yapılabilir

---

## 4. FastAPI Endpoint'leri

### 4.1 Triage Ekranından Jira Oluşturma

```
POST /api/triage/{run_id}/scenarios/{scenario_id}/jira
Authorization: Bearer <token>
```

**Akış:**
1. Senaryo bilgilerini `scenario_results` tablosundan çek
2. Mevcut Jira mapping'i kontrol et (`jira_mappings` tablosu)
3. Jira'ya issue oluştur:
   - Summary: `Automated test failed: {scenario_name}`
   - Description: Wiki renderer formatında (hata mesajı, run_id, DOORS numarası)
4. `jira_mappings` tablosuna kaydet
5. `triage_decisions` tablosuna `jira_created` kararı ekle
6. `scenario_history` tablosuna explanation olarak Jira key yaz

### 4.2 Mevcut Jira'yı Senaryoya Bağlama

```
POST /api/triage/{run_id}/scenarios/{scenario_id}/link-jira
Body: {"jira_key": "JIRA-1234"}
Authorization: Bearer <token>
```

**Akış:**
1. `jira_mappings` tablosuna `(scenario_uid, jira_key)` ekle
2. `triage_decisions` tablosuna `jira_linked` kararı ekle
3. `scenario_history` explanation'ı güncelle

### 4.3 Public API (Eski)

```
POST /api/v1/runs/{run_id}/scenarios/{scenario_id}/jira
```

> Not: Bu endpoint `JiraResponse` döner ama triage kararı oluşturmaz. Yeni kullanım için `/api/triage/...` endpoint'leri tercih edilmeli.

### 4.4 Fake Jira (Dry-Run Test)

```
POST /api/v1/fake-jira
Body: {"scenarioName": "Test", "runId": "run-1"}
```

Sadece `DRY_RUN=true` aktifken çalışır. `bug-tracker.json`'a kayıt atar.

---

## 5. Veritabanı Şeması (İlgili Tablolar)

### `jira_mappings`

| Sütun | Tür | Açıklama |
|-------|-----|----------|
| `scenario_uid` | TEXT | Senaryo UID'si |
| `doors_id` | TEXT | DOORS numarası |
| `jira_key` | TEXT | Jira issue key |
| `created_at` | TIMESTAMP | Oluşturulma zamanı |

**Constraint:** `UNIQUE(scenario_uid, jira_key)`

### `triage_decisions`

| Sütun | Tür | Açıklama |
|-------|-----|----------|
| `scenario_uid` | TEXT (PK) | Senaryo UID'si |
| `run_id` | TEXT | Run ID |
| `decision` | TEXT | `jira_created`, `jira_linked`, `accepted_pass`, `accepted_skip`, `needs_jira` |
| `actor` | TEXT | Kim karar verdi (`engineer`) |
| `reason` | TEXT | Karar gerekçesi |
| `timestamp` | TIMESTAMP | Karar zamanı |

### `scenario_history` (Yeni)

| Sütun | Tür | Açıklama |
|-------|-----|----------|
| `doors_number` | TEXT (PK) | DOORS numarası |
| `run_history` | JSON | `[{"run_id": "...", "status": "...", "explanation": "JIRA-1234"}]` |

---

## 6. Açıklama Formatı

### PASSED Senaryolar

```
v1.2.3 sürümünde test otomasyon ile doğrulanmıştır
```

### FAILED Senaryolar (Jira oluşturulduğunda)

```
JIRA-1234
```

### FAILED Senaryolar (Birden fazla Jira)

```
JIRA-1234, JIRA-5678
```

---

## 7. Hata Yönetimi

| Durum | HTTP Status | Mesaj |
|-------|-------------|-------|
| Jira yapılandırılmamış | 503 | "Jira integration not configured..." |
| Jira API hatası | 502 | "Jira error: {message}" |
| Scenario bulunamadı | 404 | "Scenario '...' not found" |
| Mevcut Jira var | 200 | Mevcut Jira key döner |
| Boş jira_key | 422 | "jira_key is required" |

---

## 8. Örnek Akış

### Senaryo: Başarısız testten Jira oluşturma

```
1. Kullanıcı triage ekranında "Jira Oluştur" butonuna tıklar
   → POST /api/triage/run-123/scenarios/abc123/jira

2. Server scenario_results'tan bilgileri çeker:
   - name_at_run: "Login feature"
   - error_message: "Element not found"
   - doors_number_at_run: "12345"

3. JiraClient.create_issue() çağrılır:
   - Summary: "Automated test failed: Login feature"
   - Description: "h2. Automated Test Failure\n\n*Run ID:* run-123\n*DOORS Number:* 12345\n..."
   - Custom field: DOORS Number = 12345

4. Jira API yanıt verir: {"key": "TEST-456"}

5. Veritabanı güncellenir:
   - jira_mappings: (abc123, 12345, TEST-456)
   - triage_decisions: (abc123, jira_created, engineer)
   - scenario_history.run_history[run-123].explanation = "TEST-456"

6. Yanıt: {"jiraKey": "TEST-456", "jiraUrl": "https://jira.local/browse/TEST-456"}
```

---

## 9. Önemli Notlar

- **Wiki Renderer:** Jira Server/DC için açıklama wiki formatında (`h2.`, `*bold*`, `{noformat}`) gönderilir. Cloud için farklı format gerekir.
- **Custom Field:** `DOORS Number` custom field'ı Jira'da tanımlı olmalıdır. Yoksa `search_by_doors_number()` çalışmaz.
- **PAT Yetkileri:** Token'ın "Create Issues", "Add Comments", "Search Issues" yetkileri olmalı.
- **Tekrar Jira:** Aynı senaryo için zaten Jira varsa, yeni oluşturulmaz — mevcut key döner.
