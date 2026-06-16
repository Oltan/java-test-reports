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

### ✅ Sadeleştirme S0–S1 (TAMAMLANDI)
- S0: `maven_executable()` → `maven.py` (ol_ta hardcode kaldırıldı, server.py+pipeline.py), `-Dbrowser` wire edildi, `migrate_json_to_duckdb.py` → `docs/arsiv/`
- S1: ortak helper'lar (`services/identifiers.py` DOORS 3→1, `services/csv_export.py` CSV 2→1, `services/jira_helper.py` description 2→1)

### ✅ Wave 2 — Koşum Yönetimi Temeli (TAMAMLANDI — paralel session)
- RM-1: pom.xml `<systemPropertyVariables>` ile `-Dallure.results.directory`/`-Dvideo.dir`/`-Dretry.state.dir`; VideoHook `-Dvideo.dir`
- RM-2: per-run ingest (`allure_dir`), parallel==1 izolasyon, cancel kapalı-conn fix, status-ezme guard (`AND status != 'cancelled'`), `start_new_session`+`killpg`; tags regex gevşetildi; db.py `pid/last_output_at/exit_code` kolonları
- P4: dashboard.css token'ları + admin.js

### ✅ Wave 2-fix #6 — Koşum Yaşam Döngüsü (TAMAMLANDI)
- 6A: pid/exit_code/heartbeat persist (`_persist_worker`)
- 6B: `TEST_MAX_CONCURRENCY` + FIFO kuyruk (`queued`, `_dispatch_queued`, `_spawn_run` seam, jobs.browser)
- 6C: duplicate-run 409 + `force`
- 6D: orphan recovery (`interrupted` + lifespan, PID-reuse korumalı kill, `RUN_RECOVERY_ON_STARTUP`)
- 6E: stall/hard timeout watchdog (`RUN_STALL_TIMEOUT`/`RUN_HARD_TIMEOUT`, `_terminate_proc` dedup)
- 6F: WS `type:"state"` olayları
- 133 pytest passed; yeni testler `tests/test_run_lifecycle.py`

### ✅ Sadeleştirme S2 (TAMAMLANDI)
- `generate_public_share` bölündü: `_share_blockers()` + `_fetch_share_rows()` (iki near-identical SELECT → tek `_SHARE_ROW_SELECT`); ölü `scenario_uids` ve `DEP_TAG_RE` kaldırıldı
- `_save_results_to_duckdb` dekompozisyonu ERTELENDİ: doğrudan test kapsamı yok → önce karakterizasyon testi gerekir

### ✅ Sadeleştirme S3 — Router split (TAMAMLANDI, `server.*` deseni)
- `server.py` **2804 → 1166 satır**; tüm **51 route** `routes/` paketine taşındı: `bugs, integrations, runs, system, admin, reports, triage, pages, tests` (9 modül).
- **Desen:** her route modülü `import server` + paylaşılan her şeye `server.X` (get_connection, execute_test_run, send_email, _spawn_run, TEST_MAX_CONCURRENCY, tests_lock, running_tests, jira_client, tracker, ws_manager, verify_token, modeller…). server.py app/state/helper/model/lifespan'i tutar, router'ları **dosya sonunda** include eder → import cycle yok, çapa testlerinin `server.X` patch yüzeyi korunur.
- Route sırası: pages catch-all `/reports/{artifact_path:path}` en sonda (specific /reports route'larını gölgelemesin).
- Her grup ayrı commit + green checkpoint; 9 commit imzalı. **143 pytest passed**, çapa (`test_auth_boundaries`, `test_integration_workflow`) + `test_run_lifecycle` router üzerinden yeşil.

### ✅ UI — P5/P6/P7 (TAMAMLANDI)
- P5/P6: run-detail senaryo kartları artık scenario-detail sayfasına linkli (`scard(scenario, run_id)` makro + `/reports/{run_id}/scenario/{id}`)
- P7 email fix: `email_send` hardcoded sıfırlar yerine gerçek metrikleri çekiyor (`_run_email_context`: DB→manifest→sıfır)
- P7 dashboard: version-breakdown bar chart artık `version` filtresine uyuyor
- 135 pytest passed (yeni testler: email gerçek-metrik, dashboard version filtresi)

### ✅ RM-4 — Admin Kuyruk Paneli (TAMAMLANDI)
- `/api/tests/running` artık `queued` job'ları + job `status` alanını da dönüyor (running önce)
- admin.js: queued job'lar "Aktif Testler" panelinde görünür ve **iptal edilebilir** (önce sadece running iptal edilebiliyordu); "Test Geçmişi" yalnız terminal durumları (completed/failed/cancelled/interrupted) gösterir; queued/interrupted rozetleri zaten vardı (P4)
- 136 pytest passed (yeni test: /api/tests/running queued dahil)

### ✅ RM-3 — Matrix Paralel Modlar (TAMAMLANDI)
- `TestRunOptions.mode` (`single`|`matrix`) + `workers:[{tags, browser?, environment?}]` (`WorkerSpec`); matrix workers boşsa 422
- worker_runs'a per-worker `tags`/`browser`/`environment` kolonları → kuyruğa alınan matrix job doğru re-spawn olur
- `_worker_specs()` (single=N kopya, matrix=worker başına) + `_worker_options()`; `start_tests` ve `_dispatch_queued` per-worker config kullanıyor; job satırı temsili `job_tags` ("@a | @b") tutar
- 139 pytest passed (yeni: matrix persist, 422 validation, kuyruk per-worker re-spawn)

### ✅ RM-4 canlı — WS state tüketimi (TAMAMLANDI)
- admin.js `/ws/test-status/live` kanalına abone olup `type:"state"` olaylarında listeyi anında tazeliyor (auto-reconnect); 5sn polling yedek olarak duruyor
- **Bug fix:** `ConnectionManager.broadcast` erken `return` yüzünden per-run abonesi olmayan run'larda "live" mirror'a hiç ulaşmıyordu (live mirror ölü koddu) → düzeltildi; canlı + birim test ile doğrulandı
- 140 pytest passed; canlı uçtan uca smoke (kuyruk/matrix/dispatch/cancel/WS) geçti

### ✅ Admin matrix gönderim UI (TAMAMLANDI)
- admin.html: `test-mode` seçici (single/matrix) + dinamik worker satırları (`matrix-rows`, "Worker ekle"/sil), single alanları (tags/parallel) matrix'te gizleniyor
- admin.js: `addWorkerRow`/`collectWorkers`/`applyMode`; `startTestRun` matrix'te `{mode:"matrix", workers:[{tags, browser?}]}` gönderiyor
- Doğrulama: `node --check` JS syntax OK, admin.html tüm kontrollerle render oluyor; matrix backend'i ayrıca canlı doğrulanmıştı. NOT: form'un tarayıcı-içi tıklama akışı (mod geçişi/satır ekleme) tarayıcısız ortamda otomatik test edilmedi (cache-buster v7)

### ✅ P5 derin — Attachment'lar (TAMAMLANDI)
- `_parse_allure_result` artık attachment'ları (screenshot/video, test+step seviyesi) çıkarıyor + screenshot/video source'ları türetiyor
- `_save_results_to_duckdb`: `_copy_run_attachment` ile dosyaları `MANIFESTS_DIR/{run_id}/`'e kopyalıyor (mevcut `/reports/{path}` route'u sunar), `scenario_results.screenshot_path`/`video_path` dolduruluyor; manifest `attachments` izinli tiplere (image/png, video/mp4, text/plain) filtreli — `load_manifests` validation kırılmıyor
- scenario-detail.html gerçek `/reports/{path}` img/video gösteriyor (placeholder SVG'ler kalktı)
- **Karakterizasyon testleri** eklendi (`tests/test_attachments_ingest.py`) — `_save_results_to_duckdb` artık ilk kez test kapsamında. 143 pytest passed

### ✅ `_save_results_to_duckdb` dekompozisyonu (TAMAMLANDI)
- Persist bloğu (`runs`/`scenario_definitions`/`scenario_results`/history/manifest yazımı) `_persist_run()`'a verbatim çıkarıldı; `_save` artık resolve → aggregate → count → persist akışı. Karakterizasyon testleriyle davranış-koruyan doğrulandı (143 passed)

### ⏳ KALAN (ortam/karar engelli — açıkça)
- **S3 router split**: ÇAPA testleri `server.X`'i monkeypatch'liyor → temiz `deps.py` split onları kırar; sadece `server.*` referans deseniyle (büyük/çirkin diff) yapılabilir. Kullanıcı bunu açıkça ERTELEDİ. İstenirse `server.*` deseniyle yapılır.
- **Shard modu**: `-Dcucumber.execution.dry-run` ile senaryo keşfi + gerçek Maven gerektirir → bu başsız ortamda doğrulanamaz. Maven'lı ortamda yapılmalı.

### ⏳ Wave 4/5 — Taşınabilirlik + Agent zemini
- P8+RM-5: env dokümantasyonu (kısmen `.env.example`'da) · P9: Failures endpoint + `docs/API.md`

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
