# Dış Servis Entegrasyon Rehberi

Bu rehber, `java_reports` test raporlama sistemini Jira, DOORS ve e posta servislerine bağlamak için kullanılır. FastAPI tarafı canlı web arayüzünü ve API çağrılarını yönetir. Java modülleri ise pipeline içinde rapor üretimi, Jira kaydı, DOORS güncellemesi ve e posta gönderimi için çalışır.

İlgili ana yollar:

* `/home/ol_ta/projects/java_reports/fastapi-server/server.py`
* `/home/ol_ta/projects/java_reports/fastapi-server/jira_client.py`
* `/home/ol_ta/projects/java_reports/fastapi-server/bug_tracker.py`
* `/home/ol_ta/projects/java_reports/jira-service/`
* `/home/ol_ta/projects/java_reports/doors-service/`
* `/home/ol_ta/projects/java_reports/email-service/`
* `/home/ol_ta/projects/java_reports/orchestrator/`
* `/home/ol_ta/projects/java_reports/bug-tracker.json`
* `/home/ol_ta/projects/java_reports/mock-email.json`

## Section 1: Jira Entegrasyonu

### Nasıl çalışır

Jira entegrasyonu iki yerde bulunur:

* FastAPI tarafı: `fastapi-server/server.py` ve `fastapi-server/jira_client.py`
* Java pipeline tarafı: `jira-service/` ve `orchestrator/src/main/java/com/testreports/orchestrator/JiraCreateStage.java`

FastAPI tarafında `server.py`, uygulama açılırken `JiraClient()` oluşturur. Bu sınıf `fastapi-server/jira_client.py` içindedir ve Jira ayarlarını ortam değişkenlerinden okur. Bir kullanıcı web arayüzünden veya API üzerinden başarısız bir senaryo için Jira bug oluşturmak istediğinde şu endpoint çalışır:

```http
POST /api/v1/runs/{runId}/scenarios/{scenarioId}/jira
```

Endpoint akışı şöyledir:

1. `server.py`, `MANIFESTS_DIR` altındaki run manifest dosyalarını okur.
2. `{runId}` değerine göre ilgili test koşumunu bulur.
3. `{scenarioId}` değerine göre senaryoyu bulur.
4. `JIRA_BASE_URL`, `JIRA_PAT` ve `JIRA_PROJECT` ayarları dolu değilse `503 Service Unavailable` döner.
5. Senaryo adından Jira summary üretir.
6. Senaryo adımlarını wiki renderer formatında description alanına yazar.
7. `jira_client.create_issue()` ile Jira REST API v2 çağrısı yapar.
8. Başarılıysa `201 Created` ve `jiraKey`, `jiraUrl` döner.

Python client şu adrese istek atar:

```text
{JIRA_BASE_URL}/rest/api/2/issue
```

Yetkilendirme header değeri:

```http
Authorization: Bearer {JIRA_PAT}
```

Java tarafında `jira-service/src/main/java/com/testreports/jira/JiraClient.java`, Jira REST API v2 için ayrı bir client sağlar. `JiraCreateStage`, pipeline çalışırken manifest içindeki `failed` senaryoları gezer ve her başarısız senaryo için Jira issue açar. Bu stage kritik değildir. Jira ayarı yoksa pipeline test raporlamasını durdurmadan Jira adımını atlar.

### Gerekli ortam değişkenleri

FastAPI Jira endpointleri için:

```dotenv
JIRA_BASE_URL=https://jira.firma.local
JIRA_PAT=gercek_personal_access_token_degeri
JIRA_PROJECT=TEST
JIRA_ISSUE_TYPE=Bug
JIRA_SSL_VERIFY=true
```

Değerleri nasıl alırsınız:

* `JIRA_BASE_URL`: Jira ana adresi. Tarayıcıda Jira açtığınız kök adresi yazın. Örnek: `https://jira.firma.local`.
* `JIRA_PAT`: Jira profilinizden oluşturulan Personal Access Token değeridir. Token ekranda yalnızca bir kez gösterilir, güvenli bir parola kasasına kaydedin.
* `JIRA_PROJECT`: Bug açılacak Jira projesinin key değeri. Jira issue anahtarındaki ilk kısımdır. Örnek: `TEST-123` için proje key `TEST`.
* `JIRA_ISSUE_TYPE`: Jira issue tipi. Varsayılan değer `Bug`.
* `JIRA_SSL_VERIFY`: Kurumsal sertifika sorunu varsa geçici test için `false` yapılabilir. Kalıcı çözüm doğru CA sertifikasını sisteme eklemektir.

Java orchestrator için aynı değerlerin `ORCHESTRATOR_` prefixli halleri de kullanılabilir:

```dotenv
ORCHESTRATOR_JIRA_BASE_URL=https://jira.firma.local
ORCHESTRATOR_JIRA_PAT=gercek_personal_access_token_degeri
ORCHESTRATOR_JIRA_PROJECT=TEST
ORCHESTRATOR_JIRA_ISSUE_TYPE=Bug
```

Not: Projedeki mevcut `.env.example` dosyasında bazı eski isimler de bulunabilir: `JIRA_URL`, `JIRA_PROJECT_KEY`, `SMTP_USER`, `SMTP_PASS`. FastAPI Jira kodu `JIRA_BASE_URL`, `JIRA_PAT`, `JIRA_PROJECT` adlarını okur. Orchestrator ise `ORCHESTRATOR_JIRA_BASE_URL`, `ORCHESTRATOR_JIRA_PAT`, `ORCHESTRATOR_JIRA_PROJECT` adlarını okur.

### Jira Personal Access Token nasıl alınır

Jira Server veya Jira Data Center için genel akış:

1. Jira web arayüzünde kendi profilinizi açın.
2. `Personal Access Tokens` sayfasına gidin. Bazı kurulumlarda yol `Profile`, sonra `Personal Access Tokens` şeklindedir.
3. `Create token` seçin.
4. Token için anlaşılır bir ad verin. Örnek: `java_reports_fastapi`.
5. Süre sonu politikanız varsa uygun bitiş tarihi seçin.
6. Token oluşturulduğunda değeri hemen kopyalayın. Bu değer daha sonra tekrar gösterilmez.
7. `.env` dosyasındaki `JIRA_PAT` alanına bu gerçek değeri yazın.

Token sahibinin ilgili projede en az şu yetkilere sahip olması gerekir:

* Issue görüntüleme
* Issue oluşturma
* Gerekliyse attachment ekleme
* Proje alanlarını okuma

Jira Cloud kullanıyorsanız şirketinizin güvenlik politikasına göre API token ve email tabanlı Basic Auth gerekebilir. Bu projedeki Python client Bearer PAT bekler. Jira Cloud bağlantısı için önce kurumunuzun desteklediği auth tipini doğrulayın.

### Başarısız senaryodan Jira bug oluşturma örneği

Önce FastAPI server çalıştırılır:

```bash
cd /home/ol_ta/projects/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Sonra var olan run değerleri listelenir:

```bash
curl -s http://localhost:8000/api/v1/runs
```

Belirli bir run içindeki başarısız senaryolar alınır:

```bash
curl -s http://localhost:8000/api/v1/runs/20260425-1500-auto-690/failures
```

Bir başarısız senaryo için Jira bug oluşturulur:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/runs/20260425-1500-auto-690/scenarios/login-timeout/jira
```

Başarılı cevap örneği:

```json
{
  "jiraKey": "TEST-1241",
  "jiraUrl": "https://jira.firma.local/browse/TEST-1241"
}
```

Jira issue içeriği şu mantıkla oluşur:

```text
Summary: Automated test failed: Login timeout

Description:
h2. Automated Test Failure

*Run ID:* 20260425-1500-auto-690
*Scenario:* Login timeout
*Duration:* 2430

h3. Steps
{noformat}
  [pass] Kullanıcı giriş sayfasını açar
  [FAIL] Kullanıcı doğru şifreyle giriş yapar
{noformat}
```

### Java pipeline ile Jira oluşturma

Orchestrator, `JiraCreateStage` içinde manifestteki her `failed` senaryo için issue açar. Çalıştırmadan önce ortam değişkenlerini verin:

```bash
export ORCHESTRATOR_JIRA_BASE_URL="https://jira.firma.local"
export ORCHESTRATOR_JIRA_PAT="gercek_personal_access_token_degeri"
export ORCHESTRATOR_JIRA_PROJECT="TEST"
export ORCHESTRATOR_JIRA_ISSUE_TYPE="Bug"

java -jar /home/ol_ta/projects/java_reports/orchestrator/target/orchestrator.jar --run-id=auto
```

Dry run için Java tarafında system property kullanılabilir:

```bash
java -Djira.dry-run=true \
  -jar /home/ol_ta/projects/java_reports/orchestrator/target/orchestrator.jar --run-id=auto
```

### Jira sorun giderme

| Belirti | Olası neden | Çözüm |
| --- | --- | --- |
| `503 Service Unavailable` | Jira FastAPI tarafında yapılandırılmamış | `JIRA_BASE_URL`, `JIRA_PAT`, `JIRA_PROJECT` değerlerini `.env` içine ekleyin ve serverı yeniden başlatın. |
| `502 Bad Gateway`, `Jira API error 401` | PAT yanlış, süresi dolmuş veya auth tipi uyumsuz | Yeni PAT oluşturun. Jira Server veya Data Center üzerinde Bearer PAT desteğini doğrulayın. |
| `502 Bad Gateway`, `403` | Token sahibinin proje yetkisi yok | Jira proje izinlerinde issue create yetkisini verin. |
| `404 Run not found` | `{runId}` için manifest yok | `MANIFESTS_DIR` değerini ve manifest dosyasının adını kontrol edin. |
| `404 Scenario not found` | `{scenarioId}` manifestte yok | `/api/v1/runs/{runId}/failures` ile gerçek scenario id değerini alın. |
| SSL hatası | Kurumsal CA tanınmıyor | CA sertifikasını sisteme ekleyin. Geçici test için `JIRA_SSL_VERIFY=false` kullanın. |

## Section 2: DOORS Entegrasyonu

### Nasıl çalışır

DOORS entegrasyonu iki katmandan oluşur:

* Java DOORS batch DXL wrapper: `doors-service/`
* FastAPI bug eşleme servisi: `fastapi-server/bug_tracker.py` ve `bug-tracker.json`

Java tarafında `doors-service/src/main/java/com/testreports/doors/DoorsClient.java`, IBM DOORS istemcisini batch modda çalıştırır. `DoorsClient`, manifest içindeki senaryoları gezer ve `doorsAbsNumber` alanı olan kayıtları DXL payload içine ekler. Sonra geçici bir JSON parametre dosyası üretir ve DOORS executable ile DXL scripti çağırır.

Çalıştırılan komut mantığı:

```text
doors.exe -b DoorsDxlScript.dxl -paramFile doors-run.json -W
```

DXL script yolu runtime sırasında resource içinden geçici dosyaya kopyalanır. Kaynak dosya:

```text
/home/ol_ta/projects/java_reports/doors-service/src/main/resources/DoorsDxlScript.dxl
```

Orchestrator tarafında `DoorsUpdateStage`, `ORCHESTRATOR_DOORS_EXE` ayarı varsa `DoorsClient` oluşturur. Ayar yoksa DOORS adımı atlanır. Linux üzerinde gerçek DOORS client olmadığı için stage uyarı yazar ve batch DXL çalıştırmaz. Bu normaldir.

### DOORS Windows gereksinimi

DOORS entegrasyonu Windows gerektirir. DXL batch çalıştırması IBM DOORS client kurulumuna bağlıdır. WSL veya Linux ortamında gerçek `doors.exe` bulunmadığı için Java client güncellemeyi atlar.

Windows makinede gerekenler:

* IBM DOORS client kurulu olmalı.
* `doors.exe` veya kurumunuzdaki DOORS batch executable yolu bilinmeli.
* Çalışan kullanıcı DOORS modüllerine yazma yetkisine sahip olmalı.
* VPN, lisans sunucusu ve DOORS veritabanı erişimi açık olmalı.

Örnek ortam değişkeni:

```powershell
$env:ORCHESTRATOR_DOORS_EXE="C:\Program Files\IBM\DOORS\bin\doors.exe"
```

Bazı mevcut örneklerde `DOORS_PATH` adı görülebilir. Orchestrator kodu `doors.exe` config key değerini okur, ortam değişkeni olarak bunun karşılığı `ORCHESTRATOR_DOORS_EXE` olur.

### bug-tracker.json ne işe yarar

`/home/ol_ta/projects/java_reports/bug-tracker.json`, DOORS requirement numarası ile Jira issue anahtarını eşler. FastAPI tarafında `BugTracker`, bu dosyayı thread lock ile okur ve yazar.

Örnek kayıt:

```json
{
  "version": "1.0",
  "mappings": {
    "DOORS-10111": {
      "jiraKey": "PROJ-945",
      "status": "OPEN",
      "firstSeen": "2026-04-18T23:07:13.494328Z",
      "lastSeen": "2026-04-26T23:07:13.494338Z",
      "scenarioName": "Login timeout",
      "runIds": ["20260423-test-003"],
      "resolution": "Fixed in v2.3.1"
    }
  }
}
```

Bu dosya şu amaçlarla kullanılır:

* Aynı DOORS requirement için daha önce Jira kaydı açılmış mı görmek
* Web arayüzünde failed scenario yanında Jira durumunu göstermek
* DOORS numarasından Jira key ve durum bilgisini bulmak
* Aynı hatanın görüldüğü run id değerlerini takip etmek

### DOORS numarası senaryoda nasıl görünür

Manifest içindeki senaryo kaydında `doorsAbsNumber` alanı bulunur. `server.py` bug status endpointi bu alanı okur. `DoorsClient` de aynı alanı batch DXL payload içine yazar.

Örnek senaryo parçası:

```json
{
  "id": "login-timeout",
  "name": "Login timeout",
  "status": "failed",
  "doorsAbsNumber": "DOORS-10111",
  "duration": 2430,
  "steps": [
    {"name": "Giriş sayfası açılır", "status": "passed"},
    {"name": "Kullanıcı giriş yapar", "status": "failed"}
  ]
}
```

### API endpointleri

Bug mapping okumak için:

```http
GET /api/v1/bugs
GET /api/v1/bugs/{doors_number}
```

Yeni mapping oluşturmak için:

```http
POST /api/v1/bugs/{doors_number}/create
```

Bu POST endpoint JWT ister. Önce login olun:

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Token alındıktan sonra mapping oluşturun:

```bash
TOKEN="buraya_login_cevabindaki_token_degerini_yazin"

curl -i -X POST \
  http://localhost:8000/api/v1/bugs/DOORS-10111/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "scenarioName": "Login timeout",
    "runId": "20260425-1500-auto-690"
  }'
```

Başarılı cevap örneği:

```json
{
  "jiraKey": "PROJ-5821",
  "doorsNumber": "DOORS-10111"
}
```

Önemli ayrım: `POST /api/v1/bugs/{doors_number}/create` endpointi gerçek Jira API çağrısı yapmaz. `server.py` içinde deterministic bir `PROJ-xxxx` anahtarı üretir ve `bug-tracker.json` dosyasına yazar. Gerçek Jira issue açmak için Section 1 içindeki Jira endpointini kullanın veya Java `JiraCreateStage` çalıştırın.

Run bazlı bug durumlarını görmek için:

```bash
curl -s http://localhost:8000/api/v1/runs/20260425-1500-auto-690/bug-status
```

Bu endpoint her senaryo için `doorsAbsNumber`, `jiraKey`, `jiraUrl`, `status` ve `isReported` alanlarını döner.

### DOORS requirement ile failed scenario bağlama örneği

1. Test manifestte senaryoya DOORS numarası eklenir:

```json
{
  "id": "payment-error",
  "name": "Ödeme sırasında hata mesajı gösterilir",
  "status": "failed",
  "doorsAbsNumber": "DOORS-20442"
}
```

2. FastAPI server çalışır:

```bash
cd /home/ol_ta/projects/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

3. Jira bug gerçek endpoint ile oluşturulur:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/runs/20260425-1500-auto-690/scenarios/payment-error/jira
```

4. DOORS numarası ile Jira anahtarı takip dosyasına kaydedilir:

```bash
TOKEN="buraya_login_cevabindaki_token_degerini_yazin"

curl -i -X POST \
  http://localhost:8000/api/v1/bugs/DOORS-20442/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scenarioName":"Ödeme sırasında hata mesajı gösterilir","runId":"20260425-1500-auto-690"}'
```

5. Windows üzerinde DOORS stage çalıştırılır:

```powershell
$env:ORCHESTRATOR_DOORS_EXE="C:\Program Files\IBM\DOORS\bin\doors.exe"
java -jar C:\path\to\java_reports\orchestrator\target\orchestrator.jar --run-id=auto
```

### DOORS sorun giderme

| Belirti | Olası neden | Çözüm |
| --- | --- | --- |
| `No DOORS executable configured; skipping DOORS update` | `ORCHESTRATOR_DOORS_EXE` verilmemiş | Windows ortamında gerçek `doors.exe` yolunu ayarlayın. |
| `DOORS requires Windows; skipping batch DXL execution` | Linux veya WSL üzerinde çalışıyor | Bu beklenen davranıştır. DOORS güncellemesini Windows client üzerinde çalıştırın. |
| `doors.exe not found` | Yol yanlış veya erişim yok | Dosya yolunu PowerShell ile kontrol edin. Kurulum dizinini doğrulayın. |
| DXL hata verdi | DOORS yetkisi, modül yolu veya DXL script sorunu | `DoorsDxlScript.dxl` içeriğini ve DOORS kullanıcı yetkilerini kontrol edin. |
| `409 Conflict` | Aynı DOORS numarası daha önce kaydedilmiş | `GET /api/v1/bugs/{doors_number}` ile mevcut mapping değerini kullanın. |
| `401 Unauthorized` | Bug create endpointinde JWT yok veya hatalı | `/api/v1/auth/login` ile yeni token alın. |

## Section 3: Email Entegrasyonu

### Nasıl çalışır

E posta entegrasyonu Java tarafındadır:

* Servis kodu: `email-service/src/main/java/com/testreports/email/EmailService.java`
* Rapor özeti modeli: `email-service/src/main/java/com/testreports/email/ReportSummary.java`
* HTML template: `email-service/src/main/resources/templates/report-email.html`
* Pipeline stage: `orchestrator/src/main/java/com/testreports/orchestrator/EmailSendStage.java`
* Test amaçlı mock veri: `/home/ol_ta/projects/java_reports/mock-email.json`

`EmailService`, Simple Java Mail ile SMTP bağlantısı kurar. HTML içerik Thymeleaf ile `report-email.html` templateinden üretilir. Aynı mesaj için plain text özet de oluşturulur.

Pipeline akışı:

1. Testler çalışır ve Allure sonuçları üretilir.
2. Manifest yazılır.
3. Web raporu deploy edilir veya lokal rapor yolu hazırlanır.
4. `EmailSendStage`, manifestten `ReportSummary` oluşturur.
5. `email.recipient` ayarı boş değilse SMTP üzerinden e posta gönderir.
6. Alıcı yoksa `No email recipient configured; skipping email notification` loglanır ve pipeline devam eder.

`EmailSendStage` kritik değildir. E posta hatası rapor üretiminin ana çıktısını engellememelidir, fakat SMTP hataları stage içinde exception üretebilir. CI ortamında bu logları takip edin.

### SMTP yapılandırması

Temel değişkenler:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=qa.reports@firma.com
SMTP_PASSWORD=gercek_smtp_sifresi_veya_app_password
SMTP_FROM=qa.reports@firma.com
EMAIL_RECIPIENT=qa-lideri@firma.com
```

Orchestrator ortam değişkenleri:

```dotenv
ORCHESTRATOR_SMTP_HOST=smtp.gmail.com
ORCHESTRATOR_SMTP_PORT=587
ORCHESTRATOR_SMTP_USERNAME=qa.reports@firma.com
ORCHESTRATOR_SMTP_PASSWORD=gercek_smtp_sifresi_veya_app_password
ORCHESTRATOR_SMTP_FROM=qa.reports@firma.com
ORCHESTRATOR_EMAIL_RECIPIENT=qa-lideri@firma.com
ORCHESTRATOR_REPORT_BASE_URL=http://localhost:8000/reports
```

Değerleri nasıl alırsınız:

* `SMTP_HOST`: Mail sağlayıcınızın SMTP sunucusu. Gmail için `smtp.gmail.com`.
* `SMTP_PORT`: TLS için genelde `587`, SSL için genelde `465`.
* `SMTP_USERNAME`: SMTP hesabının kullanıcı adı. Çoğu sağlayıcıda tam e posta adresidir.
* `SMTP_PASSWORD`: SMTP parolası veya app password. Kurumsal hesaplarda bunu mail yöneticisi verir.
* `SMTP_FROM`: Gönderen adresi. Bazı sağlayıcılarda SMTP hesabı ile aynı olmalıdır.
* `EMAIL_RECIPIENT`: Raporu alacak kişi veya dağıtım listesi.

Mevcut `.env.example` içinde `SMTP_USER` ve `SMTP_PASS` isimleri görülebilir. `EmailSendStage` orchestrator üzerinden `smtp.username` ve `smtp.password` config key değerlerini okur. Ortam değişkeni kullanırken `ORCHESTRATOR_SMTP_USERNAME` ve `ORCHESTRATOR_SMTP_PASSWORD` adlarını verin.

### Thymeleaf template nasıl çalışır

Template dosyası:

```text
/home/ol_ta/projects/java_reports/email-service/src/main/resources/templates/report-email.html
```

`EmailService.sendReport()` şu değişkenleri template context içine koyar:

```text
runId
timestamp
passed
failed
skipped
reportUrl
```

Template bu değerleri HTML içinde `th:text` ve `th:href` ile basar. Örneğin rapor linki şu değişkenden gelir:

```html
<a th:href="${reportUrl}">View Full Report</a>
```

Plain text içerik ayrıca Java kodunda üretilir. Bu sayede HTML göstermeyen mail clientlarda da özet okunabilir.

### mock-email.json ile test

`/home/ol_ta/projects/java_reports/mock-email.json`, gerçek SMTP göndermeden demo veya UI tarafında e posta geçmişi göstermek için kullanılabilecek örnek veridir. İçinde alıcılar, son gönderim zamanı ve son rapor özetleri bulunur.

Örnek alanlar:

```json
{
  "lastEmailSent": "2026-04-26T23:07:13.513316Z",
  "totalEmailsSent": 12,
  "recipients": ["test-muhendisi@firma.com"],
  "recentSummaries": [
    {
      "runId": "20260425-1500-auto-690",
      "subject": "Test Raporu: 10/9 senaryo başarılı",
      "failedScenarios": 2,
      "jiraIssuesCreated": 2,
      "doorsUpdated": 0
    }
  ]
}
```

Bu dosya SMTP bağlantısını doğrulamaz. Gerçek gönderim için orchestrator stage çalışmalıdır veya `email-service` testleri koşulmalıdır.

### Gmail SMTP app password örneği

Gmail normal hesap parolasını çoğu durumda SMTP için kabul etmez. App password gerekir.

Gerçek app password alma adımları:

1. Google hesabında iki adımlı doğrulamayı açın.
2. Google Account sayfasında `Security` bölümüne gidin.
3. `App passwords` sayfasını açın.
4. Uygulama adı olarak `java_reports` yazın.
5. Üretilen 16 karakterli app password değerini kopyalayın.
6. Bu değeri `SMTP_PASSWORD` veya `ORCHESTRATOR_SMTP_PASSWORD` olarak kullanın.

Örnek ayar:

```bash
export ORCHESTRATOR_SMTP_HOST="smtp.gmail.com"
export ORCHESTRATOR_SMTP_PORT="587"
export ORCHESTRATOR_SMTP_USERNAME="qa.reports@gmail.com"
export ORCHESTRATOR_SMTP_PASSWORD="google_app_password_degerini_buraya_yazin"
export ORCHESTRATOR_SMTP_FROM="qa.reports@gmail.com"
export ORCHESTRATOR_EMAIL_RECIPIENT="qa-lideri@firma.com"
export ORCHESTRATOR_REPORT_BASE_URL="http://localhost:8000/reports"

java -jar /home/ol_ta/projects/java_reports/orchestrator/target/orchestrator.jar --run-id=auto
```

`google_app_password_degerini_buraya_yazin` gerçek bir değer değildir. Google App Password ekranında oluşturulan değeri boşluksuz şekilde yazın.

### Email sorun giderme

| Belirti | Olası neden | Çözüm |
| --- | --- | --- |
| `No email recipient configured` | Alıcı ayarı boş | `ORCHESTRATOR_EMAIL_RECIPIENT` değerini verin. |
| SMTP auth hatası | Kullanıcı adı veya parola yanlış | App password ya da SMTP hesabı parolasını yenileyin. |
| Gmail gönderimi reddediyor | İki adımlı doğrulama veya app password yok | Google Security üzerinden app password üretin. |
| Bağlantı timeout | SMTP host veya port kapalı | Ağ, VPN, firewall ve port değerini kontrol edin. |
| Mail gidiyor ama link çalışmıyor | `report.base.url` boş veya yanlış | `ORCHESTRATOR_REPORT_BASE_URL` değerini FastAPI rapor adresine göre ayarlayın. |
| Gönderen adresi reddediliyor | `SMTP_FROM` SMTP hesabıyla uyumsuz | Sağlayıcının izin verdiği from adresini kullanın. |

## Section 4: Hızlı Başlangıç (Quick Start)

### Önerilen .env formatı

Proje kökünde `.env` oluşturun:

```bash
cd /home/ol_ta/projects/java_reports
cp .env.example .env
```

Sonra aşağıdaki formatı gerçek değerlerle doldurun. Köşeli parantez içindeki açıklamalar değer değildir. İlgili servisten aldığınız gerçek bilgiyi yazın.

```dotenv
# FastAPI admin login
ADMIN_USERNAME=admin
ADMIN_PASSWORD=guclu_bir_admin_sifresi_belirleyin
JWT_SECRET=uzun_rastgele_bir_secret_uret_kullanin
JWT_EXPIRATION_HOURS=24
MANIFESTS_DIR=/home/ol_ta/projects/java_reports/manifests

# Jira, FastAPI endpointleri
JIRA_BASE_URL=https://jira.firma.local
JIRA_PAT=jira_profilinizden_olusturdugunuz_pat_degeri
JIRA_PROJECT=TEST
JIRA_ISSUE_TYPE=Bug
JIRA_SSL_VERIFY=true

# Jira, Java orchestrator
ORCHESTRATOR_JIRA_BASE_URL=https://jira.firma.local
ORCHESTRATOR_JIRA_PAT=jira_profilinizden_olusturdugunuz_pat_degeri
ORCHESTRATOR_JIRA_PROJECT=TEST
ORCHESTRATOR_JIRA_ISSUE_TYPE=Bug

# DOORS, sadece Windows DOORS client üzerinde çalışır
ORCHESTRATOR_DOORS_EXE=C:\Program Files\IBM\DOORS\bin\doors.exe

# SMTP, Java orchestrator
ORCHESTRATOR_SMTP_HOST=smtp.gmail.com
ORCHESTRATOR_SMTP_PORT=587
ORCHESTRATOR_SMTP_USERNAME=qa.reports@firma.com
ORCHESTRATOR_SMTP_PASSWORD=smtp_saglayicinizdan_aldiginiz_parola_veya_app_password
ORCHESTRATOR_SMTP_FROM=qa.reports@firma.com
ORCHESTRATOR_EMAIL_RECIPIENT=qa-lideri@firma.com
ORCHESTRATOR_REPORT_BASE_URL=http://localhost:8000/reports
```

Güvenli değer üretme örneği:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Bu çıktıyı `JWT_SECRET` için kullanabilirsiniz.

### Her servis için minimal yapılandırma

Jira için minimum:

```dotenv
JIRA_BASE_URL=https://jira.firma.local
JIRA_PAT=jira_pat_degeri
JIRA_PROJECT=TEST
```

DOORS için minimum:

```dotenv
ORCHESTRATOR_DOORS_EXE=C:\Program Files\IBM\DOORS\bin\doors.exe
```

Email için minimum:

```dotenv
ORCHESTRATOR_SMTP_HOST=smtp.gmail.com
ORCHESTRATOR_SMTP_PORT=587
ORCHESTRATOR_SMTP_USERNAME=qa.reports@gmail.com
ORCHESTRATOR_SMTP_PASSWORD=gmail_app_password_degeri
ORCHESTRATOR_EMAIL_RECIPIENT=qa-lideri@firma.com
```

### Test komutları

FastAPI server doğrulama:

```bash
cd /home/ol_ta/projects/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Başka terminalde:

```bash
curl -s http://localhost:8000/api/v1/runs
curl -s http://localhost:8000/api/v1/bugs
```

Jira yapılandırması doğrulama:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/runs/20260425-1500-auto-690/scenarios/login-timeout/jira
```

Beklenenler:

* `201 Created`: Jira issue oluştu.
* `503 Service Unavailable`: `JIRA_BASE_URL`, `JIRA_PAT` veya `JIRA_PROJECT` eksik.
* `404`: Run veya scenario id gerçek manifestte yok.

DOORS bug mapping doğrulama:

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Token değerini aldıktan sonra:

```bash
TOKEN="buraya_login_token_degerini_yazin"

curl -i -X POST \
  http://localhost:8000/api/v1/bugs/DOORS-30001/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scenarioName":"Sepet toplamı yanlış hesaplanır","runId":"manual-check-001"}'

curl -s http://localhost:8000/api/v1/bugs/DOORS-30001
```

Java modüllerini test etme:

```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"

cd /home/ol_ta/projects/java_reports
mvn -pl jira-service test
mvn -pl doors-service test
mvn -pl email-service test
```

Pipeline dry run kontrolleri:

```bash
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
cd /home/ol_ta/projects/java_reports
mvn -pl orchestrator -am package

java -Djira.dry-run=true -Ddoors.dry.run=true \
  -jar orchestrator/target/orchestrator.jar --run-id=auto
```

Canlı pipeline için önce gerçek Jira, DOORS ve SMTP değerlerini verin. DOORS adımını sadece Windows DOORS client üzerinde çalıştırın.

### Genel kontrol listesi

* `.env` dosyası gerçek değerlerle dolduruldu.
* FastAPI server yeniden başlatıldı.
* `MANIFESTS_DIR` altında test run manifest dosyaları var.
* Jira PAT, doğru proje üzerinde issue create yetkisine sahip.
* DOORS güncellemesi Windows üzerinde ve gerçek `doors.exe` yolu ile çalışıyor.
* SMTP hesabı app password veya gerçek SMTP parolası ile doğrulanıyor.
* `bug-tracker.json` yazılabilir durumda.
* Gizli değerler Git commit içine eklenmedi.
