# Çalıştırma Rehberi

Testleri koşma, FastAPI sunucusunu başlatma ve web arayüzünü kullanma. Kurulum için: [KURULUM.md](KURULUM.md)

## 1. Hızlı başlangıç

```bash
# 1) Testleri koş (depo kökünde, mvn PATH'te olmalı)
mvn test

# 2) Allure raporu üret (opsiyonel)
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report
python3 -m http.server 8080 -d test-core/target/allure-report   # raporu görüntüle

# 3) Dashboard sunucusunu başlat
bash start.sh          # = cd fastapi-server && python3 -m uvicorn server:app --host 0.0.0.0 --port 8000

# 4) Python testleri
cd fastapi-server && python3 -m pytest tests/ -v
```

## 2. Maven ile test koşma

```bash
# Tüm testler
mvn -pl test-core test

# Tag filtresiyle
mvn -pl test-core test -Dcucumber.filter.tags="@smoke"
mvn -pl test-core test -Dcucumber.filter.tags="@smoke and @login"
mvn -pl test-core test -Dcucumber.filter.tags="@smoke or @regression"
mvn -pl test-core test -Dcucumber.filter.tags="not @wip"

# Retry ile (başarısızları N kez yeniden dener, bkz. ENTEGRASYON.md §8)
mvn -pl test-core test -Dcucumber.filter.tags="@Flaky" -Dretry.count=2
```

Örnek tag'ler bu depoda: `@smoke`, `@sample-fail`, `@Flaky`, `@RetryDemo`, `@DependencyDemo` (bkz. `scripts/features.txt`).

Sonuç dizini: `test-core/target/allure-results/` — boşsa test koşmamış veya Allure plugin aktif değil demektir.

Windows'ta tag listesini sırayla koşturmak için: `scripts\run-by-tag.bat` (`-f dosya`, `--retry-count N`, `--continue-on-fail`, `--dry-run` seçenekleri vardır).

## 3. FastAPI sunucusunu başlatma

| Yöntem | Komut |
|---|---|
| Linux/WSL | `bash start.sh` veya `bash scripts/start-servers.sh` (arka planda başlatır) |
| Windows | `scripts\start-server.bat` (çift tıkla) |
| Elle | `cd fastapi-server && python3 -m uvicorn server:app --host 0.0.0.0 --port 8000` |

Terminal açık kalmalıdır; sunucu durursa dashboard, triage ve public rapor sayfaları da kapanır.

Varsayılan giriş bilgileri `admin / admin123`'tür (`ADMIN_USERNAME` / `ADMIN_PASSWORD` ile değiştirin — üretimde mutlaka değiştirin).

### Adresler

| URL | Auth | Açıklama |
|---|---|---|
| `http://localhost:8000/` | — | Ana sayfa + giriş |
| `http://localhost:8000/docs` | — | Swagger API dokümantasyonu |
| `http://localhost:8000/dashboard` | Mühendis | Koşu özeti, grafikler, trendler |
| `http://localhost:8000/admin` | Mühendis | Test başlatma, canlı log |
| `http://localhost:8000/reports/merge` | Mühendis | Run birleştirme + paylaşım bağlantısı |
| `http://localhost:8000/reports/{run_id}` | Mühendis | Run detayı |
| `http://localhost:8000/reports/{run_id}/triage` | Mühendis | Hata kartları / triage |
| `http://localhost:8000/public/reports` | — | Paylaşılmış public raporlar |

### WSL'de çalışıp Windows tarayıcısından erişme

Windows, WSL portlarını otomatik yönlendirir; `http://localhost:8000` çoğu zaman doğrudan açılır. Açılmıyorsa WSL IP'sini alın ve onu kullanın:

```bash
wsl hostname -I    # örn. 172.x.x.x → http://172.x.x.x:8000
```

## 4. Web arayüzü ile mühendis akışı

1. **Giriş** — Ana sayfadaki formdan mühendis hesabıyla girin. Test başlatma, triage, Jira, DOORS ve email işlemleri yalnızca giriş yapan kullanıcıya açıktır; public rapor sayfası giriş istemez.
2. **Test çalıştırma** — Admin sayfasında tag, parallel (1-5) ve retry (0-10) değerlerini seçip başlatın. İş bitince Allure sonuçları işlenir, manifest yazılır ve dashboard güncellenir. Parallel değerini makine kapasitesine göre seçin; retry'ı hatayı gizlemek için değil geçici ortam sorunlarını ayıklamak için kullanın.
3. **Triage** — Run detayından triage sayfasını açın: hata mesajı, screenshot, video, Jira durumu ve override kararı bir aradadır. Gerçek ürün hatasıysa Jira kaydı oluşturun veya mevcut kayda bağlayın; test verisi/ortam/otomasyon hatasıysa override ile kısa ve izlenebilir bir not düşün.
4. **Rapor birleştirme ve paylaşım** — `/reports/merge` sayfasında run'ları ve rapora girecek senaryoları seçip oluşturun; üretilen paylaşım bağlantısını kopyalayın.
5. **Public rapor** — Paylaşım bağlantısı salt okunurdur: test başlatamaz, Jira/override/DOORS/email çalıştıramaz. Public sayfada run adı, sayılar, senaryo adı/durumu ve kısa hata özeti görünür; token, parola, Jira anahtarı, SMTP bilgisi ve ham artifact bağlantısı görünmez.
6. **DOORS ve email** — Rapor/pipeline sayfasındaki butonlarla DOORS aktarımı ve email özeti gönderilir (mühendis girişi gerekir). Email metnine gizli değer yazmayın.

## 5. API ile kullanım

### 5.1 Token alma

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
```

Tüm korumalı endpoint'lere `Authorization: Bearer $TOKEN` header'ı ile erişilir. Token süresi varsayılan 24 saattir (`JWT_EXPIRATION_HOURS`).

### 5.2 Test başlatma

```bash
curl -X POST http://localhost:8000/api/tests/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tags": "@smoke",
    "retry_count": 0,
    "browser": "chrome",
    "parallel": 1,
    "environment": "staging",
    "version": "v1.2.3",
    "visibility": "internal"
  }'
```

Alan kuralları (`fastapi-server/models.py` → `TestRunOptions`): `tags` `@` ile başlar (boşluk içeremez), `retry_count` 0-10, `parallel` 1-5, `browser` chrome|firefox|edge, `environment` staging|prod|dev, `visibility` internal|public.

İzleme ve iptal: `GET /api/tests/running`, `GET /api/tests/jobs`, `POST /api/tests/{run_id}/cancel`, `POST /api/tests/job/{job_id}/cancel`.

### 5.3 WebSocket ile canlı izleme

```javascript
const ws = new WebSocket(`ws://localhost:8000/ws/test-status/${runId}?token=${jwtToken}`);
// Dashboard genel akışı için: /ws/test-status/live?token=...
ws.onmessage = (e) => {
  const d = JSON.parse(e.data);   // {run_id, total, passed, failed, skipped, running, pct, type, scenarios:[...]}
};
```

### 5.4 Sorgulama endpoint'leri

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs                    # tüm run'lar
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs/{run_id}           # run detayı
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/runs/{run_id}/failures  # sadece hatalar
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/bugs                    # bug eşleşmeleri
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/scenario-history           # DOORS bazlı geçmiş
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/scenario-matrix            # matris görünümü
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/dashboard/metrics          # dashboard metrikleri
```

Triage ve Jira endpoint'leri için: [ENTEGRASYON.md §11](ENTEGRASYON.md#11-jira-entegrasyonu)

## 6. Sorun giderme

| Belirti | Olası neden / Çözüm |
|---|---|
| `localhost:8000` açılmıyor | Sunucu çalışmıyor — `bash start.sh` ile başlatın; WSL'de `wsl curl http://localhost:8000/docs` ile kontrol edin |
| `Connection refused` | Port veya host yanlış; sunucuyu `--host 0.0.0.0` ile başlatın |
| `401 Unauthorized` | Token eksik/süresi dolmuş — yeniden login olun |
| `404 Not Found` | run_id yanlış — önce `/api/v1/runs` ile listeleyin |
| Run listesi boş | `MANIFESTS_DIR` altında geçerli manifest yok; bir koşu başlatın veya dizini kontrol edin |
| "No tests found" | Surefire include ayarı / runner konumu — [ENTEGRASYON.md §15](ENTEGRASYON.md#15-sık-yapılan-hatalar) |
| Allure sonuçları boş | `cucumber.properties` içinde Allure plugin satırını kontrol edin |
| Test başlatma hatası (sunucudan) | `mvn` PATH'te mi? Değilse `MAVEN_CMD` ortam değişkenine tam yol verin |
| DuckDB kilitleniyor | Aynı `.duckdb` dosyasını iki süreç açamaz; tek sunucu kopyası çalıştırın |
