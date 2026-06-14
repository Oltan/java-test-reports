# CLAUDE.md — Test Reports Automation System

Bu dosyayı Claude Code otomatik okur. Projenin mevcut durumu, tamamlanan işler ve devam edilecek dalga planı burada.

## AKTİF BRANCH

```
claude/dreamy-heisenberg-li4yol
```

Tüm geliştirme bu branch'te yapılır. Commit/push'lar bu branch'e gider; main/master'a dokunulmaz.

---

## MEVCUT DURUM

### ✅ Wave 0 — Stabilizasyon (TAMAMLANDI)
- 14 failing pytest testi düzeltildi → **119 passed**
- `WebDriverFactory.java`: hardcoded Chrome yolları kaldırıldı, Selenium Manager kullanıyor
- `VideoHook.java`: hardcoded display/size kaldırıldı, system property'ler kullanıyor (`-Dvideo.display`, `-Dvideo.size`)
- `requirements-dev.txt` eklendi

### ✅ Wave 1 — Sadeleştirme (TAMAMLANDI)
- `create_jira_bug` bug fix: `scenario.errorMessage` (mevcut değildi) → failed step'ten türetiyor
- `RetryTestRunner` Java deduplication: topo-sort DependencyResolver'a devredildi (8/8 test green)
- 14 root `.md` → `docs/` altına konsolide edildi; root'ta sadece `README.md` + `AGENTS.md` + `CLAUDE.md`

### ⏳ Wave 2 — Test Koşum Yönetimi Temeli (SIRADA)
**Bağımsız paketler, aynı anda 3'e kadar paralel agent çalıştır:**

| Paket | Kapsam | Owned Files |
|-------|--------|-------------|
| **RM-1** | test-core izolasyon | `CucumberTestRunner.java`, `cucumber.properties`, `pom.xml` (test-core) |
| **RM-2** | RunManager çekirdeği | `server.py` (run yönetimi bölümü), `models.py`, `db.py` |
| **P4** | CSS design token altyapısı | `static/dashboard.css`, `static/admin.js` |

### ⏳ Wave 3 — Paralel Modlar + UI (RM-1 + RM-2 tamamlanınca)
- RM-3: Matrix paralel modlar (`workers:[{tags, browser?, environment?}]`)
- P5: Scenario detail sayfası
- P6: runDetail.js güncellemeleri
- P7: Dashboard widget'ları + email fix
- RM-4: Admin UI (kuyruk paneli, per-run durdur)

### ⏳ Wave 4 — Taşınabilirlik (W3 sonrası)
- P8 + RM-5: Başka Java projelerine bağlama, env dokümantasyonu

### ⏳ Wave 5 — Agent Zemini (W4 sonrası)
- P9: Failures endpoint + `docs/API.md`

---

## TEKNİK BAĞLAM (W2 için kritik bilgiler)

### Mevcut koşum yönetimi sorunları

**server.py'deki kırık noktalar:**
- `_save_results_to_duckdb` (server.py ~719): HEP global `ALLURE_RESULTS_DIR` okur → paralel worker'lar kendi klasörüne yazar ama ingest yanlış yeri okur
- `cancel_test` (server.py:445): `conn` with-bloğu kapandıktan sonra kullanılıyor (bug)
- `execute_test_run` finali (server.py:599-621): koşulsuz `completed/failed` yazar → `cancelled` durumunu eziyor
- `proc.kill()`: süreç grubu olmadan → yetim java/chromedriver/chrome kalır
- Kuyruk/limit yok, `queued`/`interrupted` durumları yok, restart'ta orphan recovery yok

**models.py:**
- Tags regex `^@[\w,\-]+$` (models.py:96) gerçek Cucumber ifadelerini (`@a and not @b`) reddediyor

**Java engeli:**
- `CucumberTestRunner.java:16`'daki `@ConfigurationParameter(PLUGIN...)` JUnit Platform'da system property'yi eziyor → `-Dcucumber.plugin` override'ı çalışmıyor
- Çözüm: anotasyonu kaldır, default'ları `cucumber.properties`'e taşı

### RM-1 hedef davranış
Per-run izole edilecek çıktılar:
- `allure-results` → `-Dallure.results.directory=target/allure-results-{run_id}`
- `cucumber-report.json` → `-Dcucumber.plugin` tam liste (Allure + plugin kompozisyonu)
- `videos` → `-Dvideo.dir=target/videos-{run_id}` (VideoHook.java yeni prop)
- `retry-state` → `-Dretry.state.dir=target/retry-state-{run_id}` (zaten var)

### RM-2 durum makinesi
```
queued → running → completed
                 → failed
                 → cancelled    (iptal ÖNCE DB'ye yazılır, final yazım WHERE status='running' koşullu)
                 → interrupted  (restart recovery)
```

DuckDB schema eklentileri (`ADD COLUMN IF NOT EXISTS` ile ucuz migration):
- `pid INTEGER`, `last_output_at TIMESTAMP`, `exit_code INTEGER`, `per_worker_tags TEXT`

### Riskli kararlar (üç seçenek analiz edildi)
- **R1** Eşzamanlı mvn: varsayılan `TEST_MAX_CONCURRENCY=1`; etkinleşince global kilitle bir kez `test-compile`, sonra `surefire:test`
- **R2** Per-run Allure dizini: mekanizma kanıtlı, RM-1 kabul testi en önce koşulmalı
- **R3** Çapraz platform durdurma: POSIX `start_new_session`+`killpg` SIGTERM→SIGKILL; Windows `CREATE_NEW_PROCESS_GROUP`+`taskkill /T /F`

---

## DALGA KAPISI KURALLARI (Orkestratör = Sen)

Her dalgadan sonra:
```bash
# 1. Python testleri
cd fastapi-server && python3 -m pytest tests/ -v
# Beklenti: 119 passed (veya daha fazla, 0 fail)

# 2. Java derleme
mvn clean compile

# 3. (test-core'a dokunan dalgalar) smoke testi
mvn test -Dcucumber.filter.tags="@smoke"

# 4. Boot smoke
cd fastapi-server && timeout 5 python3 -c "from server import app; print('OK')"

# Geçerse:
git add -A && git commit -m "Wave N: ..." && git push -u origin claude/dreamy-heisenberg-li4yol
```

**Alt agent kuralları:**
- Alt agent'lar ASLA commit/push yapmaz — sadece dosya değiştirir, sonucu raporlar
- Her agent'ın owned files kümesi ayrık (çakışma yasak)
- `models.py` ve `db.py` dalga başına tek sahip
- Agent brief'i kendi kendine yeterli: hedef + owned/forbidden files + kabul komutları + `STATUS: DONE|BLOCKED` final format
- Hata: BLOCKED → brief'i zenginleştir → 1 retry → böl → orkestratör kendisi yapar

---

## KABUL KRİTERLERİ (Proje tamamlandığında)

- [ ] Farklı tag'li iki eşzamanlı koşu DuckDB'de çakışmasız tamamlanır
- [ ] Durdurulan koşum: yetim süreç kalmaz (`pgrep -f test-core` boş), kardeş etkilenmez
- [ ] Restart sonrası takılı `running` kalmaz (→ `interrupted`)
- [ ] Kuyruk: limit doluyken `queued` görünür, sıra gelince başlar; duplicate 409 → `force` ile geçilir
- [ ] Admin UI'da per-run durdurma ve kuyruk paneli çalışır
- [ ] `python3 -m pytest tests/ -v` → 0 fail
- [ ] `mvn clean compile` → BUILD SUCCESS

---

## HIZLI BAŞLANGIÇ

```bash
# Branch'e geç
git checkout claude/dreamy-heisenberg-li4yol

# Python bağımlılıkları
pip install -r fastapi-server/requirements.txt -r fastapi-server/requirements-dev.txt

# Testleri doğrula
cd fastapi-server && python3 -m pytest tests/ --tb=short

# Sunucuyu başlat
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
# → http://localhost:8000
```

API geri-uyum çapası dosyaları (değiştirme):
- `fastapi-server/tests/test_auth_boundaries.py`
- `fastapi-server/tests/test_integration_workflow.py` (satır 217-248: job_id, /api/tests/jobs şekli)
