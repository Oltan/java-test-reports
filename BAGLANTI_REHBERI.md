# Bağlantı Rehberi

Bu rehber, kendi sistemlerinizi (Jira, test altyapısı, CI/CD) bu raporlama platformuna bağlamak için gereken tüm adımları içerir.

---

## 1. Hızlı başlangıç

```bash
cd /home/ol_ta/projects/java_reports/fastapi-server

# Bağımlılıkları kur
pip install -r requirements.txt

# .env dosyası oluştur (aşağıdaki bölümlere göre doldur)
cp .env.example .env   # yoksa aşağıdaki şablonu kullan

# Sunucuyu başlat
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Tarayıcıdan aç: `http://localhost:8000`

---

## 2. Ortam değişkenleri (`.env` şablonu)

`fastapi-server/.env` dosyasına aşağıdaki değerleri yazın. Dosya `.gitignore`'dadır, repoya gitmez.

```env
# ── Sunucu kimlik doğrulama ──────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=güçlü_bir_şifre_seçin
JWT_SECRET=rastgele_uzun_bir_string_buraya

# ── Jira bağlantısı ──────────────────────────────────────────────
JIRA_URL=https://jira.sirketiniz.local
JIRA_PAT=kişisel_erişim_tokenınız
JIRA_PROJECT_KEY=PROJ
JIRA_ISSUE_TYPE=Bug
JIRA_RETRY_COUNT=3

# ── Jira dry-run (gerçek Jira yokken test için) ──────────────────
# JIRA_DRY_RUN=true

# ── Test sonuçları dizini ─────────────────────────────────────────
MANIFESTS_DIR=/home/ol_ta/projects/java_reports/manifests

# ── Veritabanı ───────────────────────────────────────────────────
REPORTS_DUCKDB_PATH=reports.duckdb
```

---

## 3. Jira bağlantısı

### 3.1 Personal Access Token (PAT) oluşturma

**Jira Server / Data Center:**
1. Jira → Profil → `Personal Access Tokens` → `Create token`
2. Token'a şu izinler gerekir: `Create Issues`, `Add Comments`, `Add Attachments`, `Browse Projects`, `Transition Issues`

**Jira Cloud:**
Cloud, PAT yerine API Token kullanır. `JIRA_PAT` değerine API Token değerini yazın.  
URL formatı Cloud için: `https://siznin-alan.atlassian.net`

### 3.2 `DOORS Number` custom field

`search_by_doors_number()` ve auto-match için Jira'da `DOORS Number` adında custom field tanımlı olmalıdır. Jira yöneticinizden alan adını ve field ID'sini alın; gerekirse `jira_client.py:101` satırındaki JQL sorgusunu güncelleyin:

```python
# jira_client.py:101
jql = f'project = {self.project_key} AND "DOORS Number" ~ "{doors_number}"'
```

Alan adınız farklıysa (örn. `customfield_10100`) JQL'i ve `fields["DOORS Number"]` satırını değiştirin.

### 3.3 Bağlantıyı test etme

Sunucu çalışırken:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"şifreniz"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# Jira konfigürasyon durumu
curl -s http://localhost:8000/api/v1/jira/status \
  -H "Authorization: Bearer $TOKEN"
```

### 3.4 Dry-run modu (Jira yokken)

Gerçek Jira olmadan tüm triage akışını test etmek için:

```env
JIRA_DRY_RUN=true
JIRA_PROJECT_KEY=BUG
```

`fastapi-server/mock_jira.json` dosyasına sahte issue'ları ekleyin:

```json
{
  "BUG-001": {"key": "BUG-001", "status": "Open",        "doors_number": "DOORS-12345"},
  "BUG-002": {"key": "BUG-002", "status": "In Progress", "doors_number": "REQ-LOGIN-001"},
  "BUG-003": {"key": "BUG-003", "status": "Closed",      "doors_number": "DOORS-12345"}
}
```

`Closed` statüsündeki issue'lar auto-match'e dahil edilmez (sadece `Open` ve `In Progress` gibi aktif statüler eşleşir).

---

## 4. Jira auto-match akışı

Triage sayfası açıldığında sistem otomatik olarak şunu yapar:

1. Run'daki tüm `FAILED` / `BROKEN` senaryoları tarar
2. Her senaryonun DOORS numarasıyla Jira'da arama yapar  
3. Aktif issue'ları (Done/Closed/Resolved/Cancelled olmayanları) senaryoya bağlar
4. Birden fazla aktif issue varsa **hepsini** bağlar

Manuel işlem gerektirmez. Zaten manuel triage kararı verilmiş senaryolar atlanır.

**Aktif / Pasif statü tanımı** (`server.py` içinde):

```python
INACTIVE_STATUSES = {"done", "closed", "resolved", "cancelled",
                     "wont fix", "won't fix", "duplicate", "rejected"}
```

Jira'nızdaki statü adları farklıysa bu sete ekleyin.

---

## 5. Test sonuçlarını bağlama

### 5.1 Allure sonuçları → manifest → dashboard

Test koşusu `target/allure-results` üretir. FastAPI bu sonuçları `MANIFESTS_DIR` dizinindeki JSON manifestler üzerinden okur.

Mevcut Python manifest üretici:

```bash
# Allure sonuçlarından manifest üret
python3 fastapi-server/allure_to_manifest.py \
  test-core/target/allure-results \
  manifests/
```

Veya doğrudan API'ye yükleyin (sunucu çalışırken):

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@manifests/run-20260503.json"
```

### 5.2 DOORS numarası formatı

Feature dosyasında her senaryoya DOORS etiketi ekleyin:

```gherkin
@DOORS-12345
Scenario: Ödeme başarısız olur
  Given kullanıcı ödeme sayfasındadır
  When geçersiz kart bilgisi girilir
  Then hata mesajı görünür
```

Parser `@DOORS-` ile başlayan etiketi arar. Büyük/küçük harf fark etmez. Birden fazla DOORS etiketi konulabilir ama auto-match ilk bulunan numara için çalışır.

### 5.3 Screenshot ve video

Allure hook'ları `scenario_results` tablosuna `screenshot_path` ve `video_path` yazar. Bug oluştururken sistem bu dosyaları otomatik olarak Jira issue'suna ekler.

Hook sınıfları:

```
test-core/src/test/java/com/testreports/allure/ScreenshotHook.java
test-core/src/test/java/com/testreports/allure/VideoHook.java
test-core/src/test/java/com/testreports/allure/WebDriverHolder.java
```

Step sınıfınızda driver bağlantısı:

```java
WebDriver driver = new ChromeDriver();
WebDriverHolder.setDriver(driver);   // ← zorunlu, hook bunu okur
```

Test sonunda:

```java
driver.quit();
WebDriverHolder.removeDriver();
```

Video için `ffmpeg` sisteminizde kurulu olmalıdır. Kurulu değilse hook sessizce atlar, test akışı durmaz.

---

## 6. Kimlik doğrulama

### 6.1 Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"şifreniz"}'
```

Yanıt:

```json
{"token": "eyJhbGci..."}
```

### 6.2 Token kullanımı

Tüm `/api/` endpoint'lerine şu header ile erişin:

```
Authorization: Bearer eyJhbGci...
```

Token süresi varsayılan 24 saattir. Değiştirmek için:

```env
JWT_EXPIRATION_HOURS=8
```

### 6.3 Public raporlar

`/public/reports` sayfası token gerektirmez. Sadece `visibility = 'public'` olan run'lar görünür. Run'ı public yapmak için dashboard'dan görünürlük ayarını değiştirin.

---

## 7. CI/CD entegrasyonu

### 7.1 Ortam değişkenleri (CI'da secret olarak tanımlayın)

```
JIRA_URL
JIRA_PAT
JIRA_PROJECT_KEY
ADMIN_PASSWORD
JWT_SECRET
```

CI'da repoya `JIRA_PAT` veya `ADMIN_PASSWORD` **yazmayın**. Secret store veya vault kullanın.

### 7.2 GitHub Actions örneği

```yaml
- name: Run tests
  run: mvn -B test

- name: Start report server
  env:
    JIRA_URL:         ${{ secrets.JIRA_URL }}
    JIRA_PAT:         ${{ secrets.JIRA_PAT }}
    JIRA_PROJECT_KEY: ${{ secrets.JIRA_PROJECT_KEY }}
    ADMIN_PASSWORD:   ${{ secrets.ADMIN_PASSWORD }}
    JWT_SECRET:       ${{ secrets.JWT_SECRET }}
  run: |
    pip install -r fastapi-server/requirements.txt
    python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 &
    sleep 3

- name: Upload manifests
  run: |
    TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
      -H 'Content-Type: application/json' \
      -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" \
      | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
    # Sonuçlar MANIFESTS_DIR'a otomatik yüklenir
```

### 7.3 Jenkins örneği

```groovy
environment {
    JIRA_URL         = credentials('jira-url')
    JIRA_PAT         = credentials('jira-pat')
    JIRA_PROJECT_KEY = 'PROJ'
    ADMIN_PASSWORD   = credentials('report-admin-password')
    JWT_SECRET       = credentials('report-jwt-secret')
}
steps {
    sh 'pip install -r fastapi-server/requirements.txt'
    sh 'python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 &'
}
```

---

## 8. Triage API referansı

| Endpoint | Metod | Açıklama |
|---|---|---|
| `/api/triage/{run_id}` | GET | Run'ın triage durumu |
| `/api/triage/{run_id}/auto-match-jira` | POST | DOORS numarasıyla otomatik Jira eşleştir |
| `/api/triage/{run_id}/scenarios/{id}/jira` | POST | Yeni Jira bug oluştur |
| `/api/triage/{run_id}/scenarios/{id}/link-jira` | POST | Mevcut Jira'yı bağla (`{"jira_key":"PROJ-123"}`) |
| `/api/triage/{run_id}/scenarios/{id}/override` | POST | Pass/skip kararı (`{"decision":"accepted_pass","reason":"..."}`) |

---

## 9. Sorun giderme

| Belirti | Olası neden | Çözüm |
|---|---|---|
| Run-detail sayfası "Yükleniyor" kalıyor | `bug-tracker.json` bozuk | Dosyayı `{"version":"1.0","mappings":{}}` içeriğiyle sıfırlayın |
| Auto-match `matched: 0` döndürüyor | Tüm Jira issue'ları kapalı ya da DOORS numarası eşleşmiyor | `mock_jira.json` veya Jira'daki `DOORS Number` alanını kontrol edin |
| Jira bug oluşturulamıyor (503) | `JIRA_URL` veya `JIRA_PAT` eksik | `.env` dosyasını kontrol edin, dry-run ile test edin |
| Jira bug oluşturulamıyor (502) | Ağ erişimi veya token yetersiz izin | `JIRA_PAT` yetkilerini, URL'yi ve proxy ayarlarını kontrol edin |
| Screenshot Jira'ya eklenmiyor | `screenshot_path` NULL | `WebDriverHolder.setDriver(driver)` çağrıldığını doğrulayın |
| DOORS numarası triage'da boş | Etiket formatı yanlış | `@DOORS-12345` formatını kullanın (rakam zorunlu) |
| 401 Unauthorized | Token süresi dolmuş | Yeniden login olun |
| `mappings` KeyError | `bug-tracker.json` yanlış format | Yukarıdaki JSON şablonuyla dosyayı yeniden oluşturun |
