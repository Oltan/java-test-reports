# RUNBOOK — Test Reports Automation Sunucusu

Bu doküman `fastapi-server`'ın operasyonel işletimini anlatır: kurulum, ortam
değişkenleri, dev/prod çalıştırma, kullanıcı yönetimi, koşum yaşam döngüsü ve
sorun giderme. Kurulum adımlarının genişletilmiş hali için
[KURULUM.md](KURULUM.md), günlük kullanım için [CALISTIRMA.md](CALISTIRMA.md).
Yapay zeka ajanları için makine-okunur API referansı: [API.md](API.md).

## 1. Genel Bakış

`fastapi-server`, Java/Cucumber test koşumlarını (`test-core` Maven modülü)
tetikleyen, sonuçları DuckDB'ye yazan ve WebSocket üzerinden canlı ilerleme
yayınlayan tek bir FastAPI sürecidir. Üç bileşen aynı process içinde
paylaşılan durumu tutar:

- `running_tests` (bellek içi dict) — o an çalışan Maven süreçlerinin PID'leri
- `ws_manager` (WebSocket `ConnectionManager`, `websocket_handler.py`) —
  run_id'ye göre gruplanmış canlı bağlantılar ve son mesaj önbelleği
- DuckDB dosyası (`REPORTS_DUCKDB_PATH`) — run/job/worker/kullanıcı/senaryo
  kayıtları (`runs`, `jobs`, `worker_runs`, `users`, `scenario_results`, ...)

## 2. Tek Worker Kısıtı (ÖNEMLİ)

**Sunucu MUTLAKA `--workers 1` ile çalıştırılmalıdır.** Birden fazla uvicorn
worker süreci başlatmak veri kaybına ve tutarsız davranışa yol açar, çünkü:

- `running_tests` ve WebSocket bağlantı tablosu her worker'da ayrı bellekte
  tutulur — bir worker'ın başlattığı koşumu diğer worker göremez, iptal
  isteği yanlış worker'a düşebilir.
- DuckDB dosyası tek yazarlı bir gömülü veritabanıdır; aynı `.duckdb`
  dosyasını birden fazla süreç eşzamanlı açmaya çalışırsa kilitlenme veya
  hata alınır.

Bu nedenle hem geliştirme hem üretim komutlarında `--workers 1` sabittir
(varsayılan zaten 1'dir, fakat açıkça belirtin). Yatay ölçek gerekiyorsa
ayrı port/DB ile ayrı bir süreç çalıştırın — aynı DuckDB dosyasını paylaşmayın.

Eşzamanlı test koşumu ihtiyacı `TEST_MAX_CONCURRENCY` ile *tek süreç
içinde* kuyruklama olarak çözülür (bkz. §6), worker sayısı artırılarak değil.

## 3. Kurulum

```bash
cd fastapi-server
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
# .env dosyasını düzenleyin: en azından JWT_SECRET ve ADMIN_PASSWORD

python3 -m pytest tests/ -v   # doğrulama
```

Java/Maven tarafı kurulumu için [KURULUM.md](KURULUM.md) §1-2'ye bakın.

## 4. Ortam Değişkenleri

Kaynak: `fastapi-server/.env.example` (bu dosyayla senkron tutulmalıdır).
`.env` dosyası `fastapi-server/` içinde olmalı ve git'e girmemelidir.

| Değişken | Varsayılan | Açıklama | Prod'da zorunlu mu? |
|---|---|---|---|
| `ENV` | `development` | `production` olduğunda varsayılan `JWT_SECRET` ile açılışı reddeder | Önerilir |
| `JWT_SECRET` | `dev-secret-change-me` | Token imzalama anahtarı (hem login hem `/api/admin/service-tokens` tokenları) | **Evet** — `openssl rand -hex 32` ile üretin |
| `JWT_EXPIRATION_HOURS` | `24` | Normal login token'ının geçerlilik süresi (saat) | Hayır |
| `ADMIN_USERNAME` | `admin` | Login fallback kullanıcı adı (`users` tablosunda eşleşme yoksa) | Önerilir |
| `ADMIN_PASSWORD` | `admin123` | Login fallback parolası | **Evet** |
| `SERVICE_TOKEN_DAYS` | `365` | `/api/admin/service-tokens` isteğinde `days` verilmezse kullanılan varsayılan geçerlilik (gün) | Hayır |
| `TEST_MAX_CONCURRENCY` | `1` | Aynı anda Maven adımı çalıştırabilecek iş (job) sayısı; fazlası `queued` bekler | Hayır |
| `RUN_HARD_TIMEOUT` | `3600` | Bir koşumu toplam bu kadar saniye sonra zorla sonlandır (`0` = kapalı) | Hayır |
| `RUN_STALL_TIMEOUT` | `900` | Çıktı üretmeden bu kadar saniye geçerse koşumu "takıldı" sayıp sonlandır (`0` = kapalı) | Hayır |
| `RUN_RECOVERY_ON_STARTUP` | `1` | Açılışta önceki süreçten kalan `running`/`queued` satırları `interrupted` işaretle | Hayır |
| `RUN_RETENTION_DAYS` | `30` | Bu kadar günden eski (terminal durumdaki) koşumların ağır artifact'ları silinir: `target/allure-results-{run_id}/` + `manifests/{run_id}/` ek dosyaları. Manifest JSON'ları ve DuckDB satırları KALIR (geçmiş/dashboard bozulmaz; eski ekran görüntüsü/videolar 404 olur). `0` = yaş kuralı kapalı | Hayır |
| `RUN_RETENTION_MAX_RUNS` | `0` | Ek üst sınır: en yeni N koşum dışındakilerin artifact'ları silinir. `0` = sınırsız | Hayır |
| `REPORTS_DUCKDB_PATH` | `reports.duckdb` | DuckDB dosya yolu (göreli ise çalışma dizinine göredir) | Önerilir (mutlak yol verin) |
| `MANIFESTS_DIR` | `<repo_kökü>/manifests` | Run manifest JSON'larının okunduğu/yazıldığı dizin | Hayır |
| `JAVA_PROJECT_ROOT` | `<repo_kökü>` | Maven parent `pom.xml` dizini | Hayır |
| `MAVEN_MODULE` | `test-core` | `mvn -pl <MODUL>` argümanı | Hayır |
| `MAVEN_CMD` | *(PATH'ten `mvn`)* | `mvn` çalıştırılabilir dosyasının tam yolu | Hayır |
| `ALLURE_RESULTS_DIR` | `<JAVA_PROJECT_ROOT>/<MAVEN_MODULE>/target/allure-results` | Per-run dizin bulunamazsa kullanılan yedek Allure sonuç dizini | Hayır |

> Jira/SMTP/DOORS/Allure-CLI gibi entegrasyon değişkenleri (`JIRA_URL`,
> `SMTP_HOST`, `DOORS_PATH`, ...) bu listede yok; bkz. repo kökü
> `.env.example` ve [ENTEGRASYON.md](ENTEGRASYON.md).

## 5. Çalıştırma

### 5.1 Geliştirme (dev)

```bash
cd fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
# veya kısayol:
bash ../start.sh
```

`http://localhost:8000` açılıyorsa sunucu ayaktadır. Terminal kapanırsa
sunucu da durur.

### 5.2 Üretim (systemd)

Örnek unit dosyası: `scripts/test-reports.service`. Kurulum:

```bash
# 1) Dosyayı düzenleyin: WorkingDirectory, EnvironmentFile, ExecStart python
#    yolu ve User/Group placeholder'larını gerçek dağıtım yolunuzla değiştirin.
sudo cp scripts/test-reports.service /etc/systemd/system/test-reports.service
sudo systemctl daemon-reload

# 2) Etkinleştir + başlat
sudo systemctl enable --now test-reports

# 3) Durum kontrolü
sudo systemctl status test-reports

# 4) Canlı log
journalctl -u test-reports -f
```

Unit dosyası zaten `--workers 1` ile gelir (bkz. §2) ve `Restart=on-failure`
+ `RestartSec=5` ile çöküş sonrası otomatik yeniden başlar. Yeniden başlatma
davranışı için §7'ye bakın — takılı kalan koşumlar güvenle temizlenir.

Servis yönetimi: `systemctl {start|stop|restart|status} test-reports`.

## 6. Kullanıcı Yönetimi ve Roller

Kullanıcılar DuckDB `users` tablosunda pbkdf2 ile hash'lenmiş parolalarla
tutulur. Login önce `users` tablosunda eşleşme arar; bulamazsa
`ADMIN_USERNAME`/`ADMIN_PASSWORD` ortam değişkenlerine fallback yapar (rol:
`admin`). Token payload'ında bir `role` alanı taşınır:

| Rol | Nasıl elde edilir | Yetkiler |
|---|---|---|
| `admin` | env fallback ile giriş, veya `/api/admin/users` ile `role:"admin"` oluşturulmuş kullanıcı | her şey + `/api/admin/*` uçları |
| `runner` | `/api/admin/users` ile `role:"runner"` (varsayılan) oluşturulmuş kullanıcı | test başlat/izle/iptal et, koşumları görüntüle — admin uçları hariç |
| `agent` | `/api/admin/service-tokens` ile üretilen servis token'ı | `runner` ile aynı erişim; AI-agent/otomasyon istemcileri için |

`/api/admin/*` uçları `require_role("admin")` ile korunur; yetkisiz rol
`403 {"detail": "Requires role in [...]"}` alır.

### 6.1 Giriş (token alma)

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
```

Sunucu ayrıca tarayıcı oturumları için `HttpOnly` bir `access_token` cookie'si
set eder (`samesite=lax`); API/agent istemcileri cookie'yi yok sayıp `token`
alanını Bearer olarak kullanmalıdır.

### 6.2 Kullanıcı listeleme (admin)

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/admin/users
```

### 6.3 Kullanıcı ekleme (admin)

```bash
curl -X POST http://localhost:8000/api/admin/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"username":"yeni_muhendis","password":"guclu_bir_parola","role":"runner"}'
```

`201` döner; kullanıcı adı zaten varsa `409`, kullanıcı adı/parola boşsa
`422`.

### 6.4 Kullanıcı silme (admin)

```bash
curl -X DELETE http://localhost:8000/api/admin/users/yeni_muhendis \
  -H "Authorization: Bearer $TOKEN"
```

Kendi hesabınızı silmeye çalışırsanız `400`; kullanıcı yoksa `404`.

### 6.5 Servis token'ı üretme (admin, AI-agent/otomasyon için)

```bash
curl -X POST http://localhost:8000/api/admin/service-tokens \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"name": "ci-agent", "days": 365}'
```

Üretilen token `sub: "svc:ci-agent"`, `role: "agent"` ile stateless bir
JWT'dir — sunucu tarafında iptal/geçersizleştirme mekanizması yoktur, yalnız
imza ve `exp` ile geçerlidir (`JWT_SECRET` rotasyonu tüm token'ları geçersiz
kılar). Detaylar için [API.md §2.4](API.md#24-service-tokens-for-ai-agents--automation).

## 7. Koşum Yaşam Döngüsü

Bir test işi (`job`) şu durum makinesinden geçer:

```
queued → running → completed
                 → failed
                 → cancelled    (iptal ÖNCE DB'ye yazılır)
                 → interrupted  (restart recovery)
```

- **queued**: `POST /api/tests/start` çağrısı işi kuyruğa alır (`TEST_MAX_CONCURRENCY`
  doluysa). `worker_runs` satırları da `queued` ile oluşturulur.
- **running**: Bir slot boşaldığında iş kuyruktan çekilir; bu işin worker'ları
  `mvn ... test` ile başlar.
- **completed / failed**: Worker'ın Maven süreci bitince sonuç DuckDB'ye
  yazılır; hata varsa `failed`, yoksa `completed`. Bir job'ın kendi durumu
  ancak **tüm** worker'ları bitince `completed`/`failed` olur.
- **cancelled**: `POST /api/tests/{run_id}/cancel` (o run'ın ait olduğu tüm
  job'ı iptal eder) veya `POST /api/tests/job/{job_id}/cancel` ile tetiklenir.
  İptal durumu önce veritabanına yazılır, sonra süreç grubuna `SIGTERM`
  gönderilir (`_terminate_proc`); böylece yarışan bir "final status" yazımı
  `cancelled`'ı ezmez (final yazımlar `WHERE status = 'running'`/`!= 'cancelled'`
  koşulludur). `queued` durumundaki job'lar da iptal edilebilir — hiç
  başlamadan kuyruktan düşerler.
- **interrupted**: Sunucu yeniden başladığında (`RUN_RECOVERY_ON_STARTUP=1`
  ise, lifespan içinde) hâlâ `running`/`queued` görünen worker'lar bulunur,
  hayattaysa süreç gruplarına `SIGTERM` gönderilir ve hem `worker_runs` hem
  `jobs` satırları `interrupted` olarak işaretlenir.
- **Stall/hard timeout watchdog**: Her worker için bir arka plan görevi
  `RUN_STALL_TIMEOUT` (çıktı sessizliği) ve `RUN_HARD_TIMEOUT` (toplam süre)
  limitlerini izler; aşılırsa süreç grubu sonlandırılır (aynı `_terminate_proc`
  yolu, orphan `java`/`chromedriver` bırakmaz).

### Koşum modları (`TestRunOptions.mode`)

`POST /api/tests/start` gövdesinde `mode` alanı `single` (varsayılan),
`matrix` veya `shard` olabilir:

- **single**: tek `tags` + `parallel` (N kopya worker, hepsi aynı tag).
- **matrix**: `workers: [{tags, browser?, environment?}]` — her worker kendi
  tag/browser/environment'ını taşır; `workers` boşsa `422`.
- **shard**: `features` alanıyla (veya `GET /api/tests/discovery?tags=&shards=`
  önizlemesiyle) feature dosyaları worker'lar arasında bölünür; `shard` +
  `retry_count > 0` kombinasyonu `422` döner (validator kısıtı).

### Kuyruk ve limit

`TEST_MAX_CONCURRENCY` (varsayılan `1`) aynı anda `running` olabilecek job
sayısını sınırlar. Limit doluyken yeni işler `queued` durumunda kuyrukta
bekler; bir job bitince `_dispatch_queued` bir sonraki kuyruktaki işi başlatır.

### Duplicate koruması (409) ve `force`

Aynı `tags` + `environment` kombinasyonuyla zaten `queued`/`running` bir iş
varsa `POST /api/tests/start` **409** döner. **`force` bu branch'te bir sorgu
parametresi DEĞİL, istek gövdesinin (`TestRunOptions`) bir alanıdır**
(`fastapi-server/models.py`: `force: bool = False`):

```bash
curl -X POST "http://localhost:8000/api/tests/start" \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
  -d '{"tags":"@smoke","environment":"staging","force":true}'
```

## 8. Sorun Giderme

| Belirti | Açıklama / Çözüm |
|---|---|
| Bir koşum kalıcı olarak `running` görünüyor | Sunucu beklenmedik şekilde kapanmış olabilir. Sunucuyu yeniden başlatın (`systemctl restart test-reports` veya `bash start.sh`); açılışta (varsayılan `RUN_RECOVERY_ON_STARTUP=1`) bu koşum otomatik `interrupted` olarak işaretlenir ve varsa artık süreç grubuna `SIGTERM` gönderilir. Yani yeniden başlatmak **güvenlidir**, koşum ortasında yapılsa bile. |
| Yetim `java`/`chromedriver`/`chrome` süreçleri kaldı | `pgrep -f test-core` ile kontrol edin; sunucu her Maven sürecini kendi süreç grubunda başlatır (`start_new_session=True`) ve iptal/kurtarma/watchdog sırasında `killpg` ile tüm grubu sonlandırmayı dener. Restart sonrası hâlâ süreç varsa manuel `kill` gerekebilir. |
| `fastapi-server/reports.duckdb` diye başıboş bir dosya var | Testler veya lokal denemeler sırasında oluşmuş olabilir; `REPORTS_DUCKDB_PATH` göreli olduğu için çalışma dizinine göre yazılır. Sunucu kapalıyken güvenle silinebilir — açılışta `init_schema` şemayı yeniden kurar (kullanıcılar dahil tüm tablolar sıfırlanır). Üretimde karışıklığı önlemek için `REPORTS_DUCKDB_PATH`'i mutlak bir yola ayarlayın. |
| Koşum `RUN_STALL_TIMEOUT`/`RUN_HARD_TIMEOUT` ile sonlandırıldı | Beklenen davranış — çıktı üretmeden çok uzun süre geçti veya toplam süre limiti aşıldı. Gerekiyorsa `.env`'de bu değerleri artırın (`0` = watchdog kapalı). |
| `401 Unauthorized` | Token eksik/süresi dolmuş (`JWT_EXPIRATION_HOURS`) — `POST /api/v1/auth/login` ile yeniden giriş yapın. |
| `403 Forbidden` bir `/api/admin/*` çağrısında | Token'ın rolü `admin` değil (`runner`/`agent`). O kullanıcıya admin rolü atamak için mevcut bir admin ile `/api/admin/users` kullanın. |
| Sunucu prod'da açılmıyor, log'da JWT_SECRET hatası | `ENV=production` iken varsayılan `JWT_SECRET` (`dev-secret-change-me`) ile açılış reddedilir. `.env` içine gerçek bir `JWT_SECRET` (`openssl rand -hex 32`) yazın. |
| Aynı `tags`+`environment` ile başlatma 409 veriyor | Beklenen davranış — zaten kuyrukta/çalışan aynı iş var. Kasıtlıysa istek gövdesine `"force": true` ekleyin (§7 — sorgu parametresi değil). |
| Loglar nerede? | stdout/stderr'e yazılır. systemd altında `journalctl -u test-reports -f` ile izlenir; elle çalıştırıldığında doğrudan terminalde görünür. |

Genel kurulum sorunları için [KURULUM.md §5](KURULUM.md#5-sık-karşılaşılan-kurulum-sorunları),
günlük kullanım sorunları için [CALISTIRMA.md §6](CALISTIRMA.md#6-sorun-giderme).
