# Kurulum ve Test Durumu Rehberi

Bu belge başka bir makineye kurarken dikkat edilmesi gereken noktaları ve mevcut yazılımın test durumunu özetler. `NASIL_CALISTIRILIR.md` günlük kullanımı, `ENTEGRASYON_REHBERI.md` entegrasyon ayarlarını anlatır. Bu dosya kurulum öncesi kontrol listesidir.

## 1. Yazılım Durumu (son test koşusu)

| Bileşen | Durum | Not |
|---|---|---|
| Maven build (`mvn clean install -DskipTests`) | BAŞARILI | 3 modül derleniyor |
| `allure-integration` testleri | TAMAMI GEÇTİ | Hook ve adapter testleri yeşil |
| `report-model` testleri | 26 / 27 GEÇTİ | 1 test örnek manifest dosyası bekliyor (`SampleManifestGenerator` önce çalışmalı) |
| `test-core` (Selenium) testleri | BAŞARISIZ | Chrome / ChromeDriver gerektirir, başsız ortamda çalışmaz |
| FastAPI birim testleri | 98 GEÇTİ / 13 BAŞARISIZ / 5 ATLA | Başarısızlar örnek manifest fixture'ı ister |
| FastAPI sunucu açılışı | BAŞARILI | `http://127.0.0.1:8000/` ve `/docs` HTTP 200 döndü |

Özet: Çekirdek (FastAPI sunucu, Allure entegrasyonu, manifest model) çalışır durumda. Kalan testler ortam bağımlı (Chrome, fixture).

## 2. Sistem Önkoşulları

| Araç | Sürüm | Zorunlu mu | Hangi modül için |
|---|---|---|---|
| Java | 21 | Evet | Maven modülleri |
| Maven | 3.9+ | Evet | Build |
| Python | 3.12+ önerilir, 3.11 çalışıyor | Evet | FastAPI sunucu |
| Git | herhangi | Evet | Repo |
| Google Chrome + ChromeDriver | uyumlu çift | Selenium testleri için | `test-core` |
| Allure CLI | 2.33+ | Rapor üretimi için | Allure çıktısı |
| ffmpeg | herhangi | Opsiyonel | Video kaydı (yoksa atlanır) |

## 3. Adım Adım Kurulum

### 3.1 Repoyu klonla
```bash
git clone <repo-url> java-test-reports
cd java-test-reports
```

### 3.2 Java + Maven doğrulama
```bash
java -version    # 21 olmalı
mvn -version     # 3.9+ olmalı
mvn -DskipTests clean install
```

### 3.3 Python sanal ortamı (ZORUNLU)
Sistem genelinde `pip install` yapma. Mevcut `PyJWT` ya da `cryptography` paketleriyle çakışıp `_cffi_backend` ya da `RECORD file not found` hatası verir.

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r fastapi-server/requirements.txt
pip install pytest pytest-asyncio  # test koşmak istersen
```

### 3.4 .env dosyası
```bash
cp .env.example .env
```
Aşağıdaki alanları kendi ortamına göre düzelt:
- `JIRA_URL`, `JIRA_PAT`, `JIRA_PROJECT_KEY`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
- `DOORS_PATH` — Linux/WSL'de Windows yolu çalışmaz, kendi DXL yorumlayıcına göster
- `ALLURE_PATH` — Linux'ta `/usr/local/bin/allure` ya da kurduğun yol
- `JWT_SECRET` — **en az 32 byte** olmalı. Kısa olursa `InsecureKeyLengthWarning` ve token doğrulaması kararsızlaşır. Üretim için: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`

### 3.5 Sunucuyu başlat
```bash
bash start.sh
# ya da
cd fastapi-server && python -m uvicorn server:app --host 0.0.0.0 --port 8000
```
Tarayıcıdan: `http://localhost:8000` ve `http://localhost:8000/docs`.

## 4. Başka Makineye Kurarken Dikkat Edilecek Noktalar

### 4.1 Mutlak yollar
- `start.sh` repo köküne göre çalışır, sorun yok.
- `NASIL_CALISTIRILIR.md` içinde `/mnt/c/Users/ol_ta/desktop/java_reports` yolu yazılı. Başka kullanıcıda WSL yolu farklı olur, yalnızca rehberi güncelle, kod değişmesin.
- `.env.example` içindeki `DOORS_PATH=C:\Program Files\IBM\DOORS\bin\dxl.exe` ve `ALLURE_PATH=C:\tools\allure-2.33.0\bin\allure.bat` Windows için. Linux'ta mutlaka değiştir.
- `test-core` Selenium Manager kullanmaya çalışırken `/tmp/chromedriver-linux64/chromedriver` yoluna düşüyor. Chrome + chromedriver kurulu değilse bu testler beklendiği gibi düşer; CI dışında bunları atlamak için: `mvn -pl allure-integration,report-model test`.

### 4.2 Python paket çakışması
Debian/Ubuntu tabanlı sistemlerde `python3-jwt` ve `python3-cryptography` paketleri sistem APT ile gelir. Sanal ortam dışında pip ile üzerine yazmaya kalkışınca:
- `Cannot uninstall PyJWT 2.7.0, RECORD file not found`
- `ModuleNotFoundError: No module named '_cffi_backend'`
hataları çıkar. Çözüm: her zaman `.venv`. Gerekirse `--ignore-installed` ile zorla, ama venv tercih edilir.

### 4.3 Port çakışması
FastAPI varsayılan portu **8000**. Başka servis (Jenkins, gelen webhook tüneli vb.) aynı portu kullanıyorsa `WEB_SERVER_PORT` değiştir ya da `--port` parametresi ver. Reverse proxy arkasındaysan WebSocket akışı için (`websocket_handler.py`) `Upgrade` ve `Connection` başlıklarını proxy'de aç.

### 4.4 Veri dosyaları ve kalıcı durum
- `*.duckdb` ve `*.duckdb.wal` `.gitignore` içinde. Yeni makinede ilk açılışta DuckDB boş başlar; ihtiyaç varsa `migrate_json_to_duckdb.py` ile veri taşı.
- `manifests/` da yoksayılı; mevcut run kayıtlarını taşıyacaksan ayrıca kopyala.
- `bug-tracker.json` da yoksayılı (`.gitignore`'da). Yeni makinede sıfırdan oluşturulur, üretim verisini ayrıca taşı.

### 4.5 Şifre, anahtar, gizli değer
- `.env` dosyasını **asla commit etme** — `.gitignore` kapsıyor, yine de dikkat.
- Ekran görüntüleri `.sisyphus/evidence/` altında ve `*.png` git'te yoksayılı. Rehbere ekran görüntüsü koyarken parola, token, Jira PAT, DOORS bağlantı bilgisi görünmesin.
- `JWT_SECRET` üretim ortamında her makinede farklı olmalı, geliştirmedeki örnek değer asla canlıya çıkmasın.

### 4.6 Selenium ortamı (test-core)
Headless çalıştırmak için makinede şunlar olmalı:
- `google-chrome` ya da `chromium`
- Eşleşen sürümde `chromedriver` (Selenium 4.21 Selenium Manager ile otomatik indirir, ama internet yoksa elle kur)
- Display gerekiyorsa `xvfb-run` kullan: `xvfb-run mvn -pl test-core test`

### 4.7 Allure rapor üretimi
`mvn allure:generate` çalışsa da statik rapor için CLI önerilir:
```bash
allure generate --clean test-core/target/allure-results -o test-core/target/allure-report
python -m http.server 8080 -d test-core/target/allure-report
```
`allure serve` kullanma — proje politikası statik üretim + dış sunucu.

### 4.8 ffmpeg
Yoksa video kaydı sessizce atlanır, test düşmez. Üretim sunucularında kurulu olması rapor zenginliği için faydalı.

## 5. Kurulum Sonrası Hızlı Sağlık Kontrolü

```bash
# 1) Java derleme
mvn -DskipTests clean install

# 2) Selenium harici testler
mvn -pl allure-integration,report-model test

# 3) Python birim testleri (venv aktif)
cd fastapi-server && python -m pytest tests/ -q

# 4) Sunucu kalkıyor mu
bash start.sh &
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
# 200 görmen lazım
kill %1
```

Bu dört adım yeşilse temel kurulum tamamdır. Selenium ve örnek-fixture bağlı testler ayrı bir konu olarak ele alınır.

## 6. Bilinen Eksikler ve Takip

- `report-model` `ManifestTest.testManifestValidatorValidatesSampleFile` testi `SampleManifestGenerator` önceden çalıştırılmadıkça düşer. Test ön koşulu olarak generator'ı sürefire'a bağlamak gerekir.
- FastAPI test paketinde `test_schema.py` ve bazı `test_server.py`, `test_triage.py` testleri örnek manifest fixture'ı ister. Test verisini üreten yardımcıyı veya fixture'ı conftest'e taşımak çözüm olur.
- `start.sh` portu sabit 8000. `WEB_SERVER_PORT` `.env`'i okuyacak biçimde scriptin güncellenmesi düşünülebilir.
