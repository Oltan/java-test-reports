# Allure + ExtentReports Birleştirme Planı

## TL;DR

> **Quick Summary**: surefirePlugin'ün retry, @id/@dep bağımlılık, tag-bazlı koşum özelliklerini mevcut Allure tabanlı sisteme taşı. Windows-native çalışacak şekilde düzenle. Hybrid raporlama (Allure ana + ExtentReports opsiyonel).
>
> **Deliverables**:
> - Retry mekanizması (file-based state, konfigure edilebilir retry count)
> - @id/@dep senaryo bağımlılık yönetimi
> - Tag bazlı koşum script'i (Windows .bat + PowerShell)
> - Failure location capture (feature:line)
> - Windows-native kurulum (WSL gerekmez)
> - Kapsamlı geçiş rehberi
>
> **Estimated Effort**: Medium (~3 gün)
> **Parallel Execution**: YES — 3 waves, 4-5 task/wave

---

## 1. Vizyon

İki sistemin en iyi özelliklerini birleştirip Windows'ta tek komutla çalışan entegre bir sistem:

```
Cucumber Feature Dosyaları
    │
    ├── @id:Login @dep:Setup  (senaryo bağımlılığı)
    │
    ▼
CucumberRetryRunner (retry + dependency graph)
    │
    ├── Attempt 1 → FAIL
    ├── Attempt 2 → FAIL  
    ├── Attempt 3 → PASS ✅
    │
    ▼
Allure Results (JSON) + ExtentReports (HTML, opsiyonel)
    │
    ▼
FastAPI Dashboard → Jira Bug → DOORS DXL → Email
```

## 2. Teknik Kararlar

| Karar | Seçim | Gerekçe |
|-------|-------|---------|
| **Ana rapor** | Allure | Daha modern UI, Cucumber adapter, CI-friendly |
| **Retry** | surefirePlugin'ten taşı | File-based state, battle-tested |
| **Bağımlılık** | @id/@dep sistemi | Topolojik sıralama, sağlam |
| **Video** | opsiyonel (ffmpeg varsa) | Disk tasarrufu, graceful skip |
| **Windows** | Python embeddable + .bat | WSL gerekmez, tek tıkla |
| **ExtentReports** | Opsiyonel plugin olarak kalır | Geçiş süreci için hybrid |
| **Build** | Maven (değişmedi) | Mevcut altyapı |

## 3. İş Paketleri

### Wave 1: Retry + Bağımlılık (Java, paralel 3 task)

#### Task 1.1: RetryRunner — test-core'a taşı

surefirePlugin'teki `CucumberRetryRunnerTest.java`'i al, `test-core/` modülüne `RetryTestRunner.java` olarak taşı.

- [ ] `com.testreports.runner.RetryTestRunner.java`
- [ ] Retry mekanizması: `--retry-count N` parametresi
- [ ] File-based state: `target/retry-state/` altında senaryo durumu
- [ ] RetryDemoSteps benzeri test adımları
- [ ] pytest: retry logic testleri

**Süre**: 3 saat  
**Bağımlılık**: Yok

#### Task 1.2: DependencyGraph — @id/@dep sistemi

surefirePlugin'teki dependency graph + toposort'u `test-core/` modülüne taşı.

- [ ] `com.testreports.runner.DependencyResolver.java`
- [ ] `@id:` ve `@dep:` tag parser
- [ ] Topolojik sıralama (Kahn's algorithm)
- [ ] Bağımlılık PASS değilse SKIP
- [ ] Test feature dosyasında örnek `@id:` / `@dep:` kullanımı

**Süre**: 3 saat  
**Bağımlılık**: Yok

#### Task 1.3: FailureCapture — feature:line konum yakalama

surefirePlugin'teki `FailureCapturePlugin.java`'i `allure-integration/` modülüne taşı.

- [ ] `com.testreports.allure.FailureLocationCapture.java`
- [ ] Fail olan her senaryo için `feature:line` kaydı
- [ ] Allure JSON'a label olarak ekleme
- [ ] Dashboard'da "Kaynak: login.feature:42" şeklinde gösterim

**Süre**: 2 saat  
**Bağımlılık**: Yok

---

### Wave 2: Script + Dashboard (paralel 3 task)

#### Task 2.1: Tag Runner Script (Windows)

surefirePlugin'teki `run-by-tag.sh`'i Windows'a uyarla.

- [ ] `scripts/run-by-tag.bat` (Windows batch)
- [ ] `scripts/run-by-tag.ps1` (PowerShell)
- [ ] `features.txt` formatı aynı
- [ ] `--retry-count`, `--continue-on-fail`, `--dry-run` flag'leri
- [ ] Her tag için ayrı timing + özet

**Süre**: 2 saat  
**Bağımlılık**: Task 1.1

#### Task 2.2: Dashboard — retry + dependency gösterimi

FastAPI dashboard'una retry ve dependency bilgilerini ekle.

- [ ] `templates/scenario-detail.html`: retry count, attempt history
- [ ] `templates/dashboard.html`: dependency graph görselleştirme (opsiyonel)
- [ ] API: `GET /api/v1/runs/{id}/dependencies` endpoint
- [ ] Test: pytest ile yeni endpoint'ler

**Süre**: 3 saat  
**Bağımlılık**: Task 1.1, 1.2

#### Task 2.3: Windows Native Kurulum

WSL gerekmeden Windows'ta çalışacak paket.

- [ ] Python embeddable package (`.zip`, portable)
- [ ] `start-server.bat` güncelleme (Windows path'ler)
- [ ] `.env.example` Windows path formatı
- [ ] Allure CLI Windows path
- [ ] Maven wrapper (`mvnw.bat`) ekleme
- [ ] Tek tıkla kurulum: `setup.bat`

**Süre**: 3 saat  
**Bağımlılık**: Yok

---

### Wave 3: Geçiş Rehberi + Final (paralel 2 task)

#### Task 3.1: Geçiş Rehberi

ExtentReports'tan Allure'a geçiş için kapsamlı rehber.

- [ ] `GECIS_REHBERI.md`:
  - Neden Allure? (karşılaştırma tablosu)
  - Mevcut ExtentReports projesine Allure ekleme (adım adım)
  - surefirePlugin özelliklerini taşıma
  - ExtentReports'u tamamen kaldırma (opsiyonel)
  - Hybrid kullanım (ikisi birden)
  - Sık sorulan sorular
  - Önce/sonra ekran görüntüleri

**Süre**: 2 saat  
**Bağımlılık**: Yok

#### Task 3.2: Final QA + Test

Tüm sistemin Windows'ta uçtan uca testi.

- [ ] `mvn clean test` (tüm modüller)
- [ ] `pytest fastapi-server/tests/ -v`
- [ ] `scripts/run-by-tag.bat` test
- [ ] Dashboard screenshot (Playwright)
- [ ] Performance: dashboard yüklenme < 1s
- [ ] Allure report + ExtentReports report karşılaştırma

**Süre**: 2 saat  
**Bağımlılık**: Tüm Wave 1 + 2

---

## 4. Bağımlılık Grafiği

```
Wave 1 (Paralel):
  Task 1.1 (Retry) ──────────────┐
  Task 1.2 (Dependency) ─────────┤
  Task 1.3 (FailureCapture) ─────┤
                                  │
Wave 2 (Paralel):                 │
  Task 2.1 (Tag Runner) ◄────────┘ (Task 1.1)
  Task 2.2 (Dashboard)  ◄────────┘ (Task 1.1 + 1.2)
  Task 2.3 (Windows) ──────────── (bağımsız)
                                  │
Wave 3 (Paralel):                 │
  Task 3.1 (Rehber) ───────────── (bağımsız)
  Task 3.2 (QA)      ◄───────────┘ (tüm Wave 1 + 2)
```

## 5. Windows Mimarisi

```
C:\test-reports\
├── setup.bat              # Tek tıkla kurulum
├── start-server.bat       # Sunucu başlat
├── run-tests.bat          # Testleri koş
├── python\                # Python embeddable (portable)
├── mvnw.bat               # Maven wrapper
├── java\                  # Java (sistemde varsa gerekmez)
└── ... (proje dosyaları)
```

## 6. Commit Planı

```
feat(retry): port retry runner + file-based state from surefirePlugin
feat(dependency): @id/@dep dependency graph + toposort resolver
feat(failure): FailureCapturePlugin → Allure label integration
feat(scripts): Windows tag-based test runner (.bat + .ps1)
feat(dashboard): retry history + dependency info in scenario detail
feat(windows): portable Python, mvnw, one-click setup.bat
docs: ExtentReports→Allure geçiş rehberi
test(qa): full Windows end-to-end verification
```

## 7. Kabul Kriterleri

- [ ] Retry: `mvn test -Dretry.count=3` ile 3 deneme yapar
- [ ] Dependency: `@id:A @dep:B` ile B PASS değilse A SKIP
- [ ] Failure: Allure JSON'da `feature:line` label'ı var
- [ ] Tag runner: `run-by-tag.bat` Windows'ta çalışır
- [ ] Dashboard: scenario detail'de "Attempt 2/3" gösterir
- [ ] Windows: `setup.bat` ile tek tıkla kurulum
- [ ] Geçiş rehberi: adım adım takip edilebilir
- [ ] Tüm mevcut testler bozulmaz
