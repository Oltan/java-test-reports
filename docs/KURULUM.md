# Kurulum Rehberi (Linux + Windows)

Bu rehber, test raporlama sistemini sıfırdan kurar. Sistem iki bileşenden oluşur:

- `test-core` — Java/Cucumber/Selenium testleri (Maven modülü)
- `fastapi-server` — Python FastAPI dashboard ve API

## 1. Gereksinimler

| Araç | Sürüm | Zorunlu mu? | Kontrol |
|---|---|---|---|
| Java JDK | 21 | Evet | `java -version` |
| Apache Maven | 3.9+ | Evet | `mvn -version` |
| Python | 3.11+ | Evet (fastapi-server için) | `python3 --version` |
| Allure CLI | 2.x | Hayır (HTML rapor üretimi için) | `allure --version` |
| ffmpeg | Güncel | Hayır (video kaydı; yoksa hook sessizce atlar) | `ffmpeg -version` |
| Google Chrome + ChromeDriver | Eşleşen sürümler | Selenium testleri için | `google-chrome --version` |

---

## 2. Linux kurulumu

### 2.1 Java 21 ve Maven

```bash
# Debian/Ubuntu örneği
sudo apt install -y openjdk-21-jdk   # veya Adoptium Temurin 21

# Maven (paket yöneticisinden veya binary zip ile)
sudo apt install -y maven
mvn -version   # 3.9+ olmalı
```

Maven'i binary arşivden kurduysanız `bin/` dizinini `PATH`'e ekleyin (örn. `~/.bashrc` içine):

```bash
export PATH="$HOME/tools/apache-maven-3.9.9/bin:$PATH"
```

### 2.2 Allure CLI (opsiyonel)

```bash
curl -LO https://github.com/allure-framework/allure2/releases/download/2.33.0/allure-2.33.0.tgz
mkdir -p ~/tools && tar -xzf allure-2.33.0.tgz -C ~/tools/
export PATH="$PATH:$HOME/tools/allure-2.33.0/bin"
allure --version
```

### 2.3 ffmpeg (opsiyonel, video kaydı)

```bash
sudo apt install -y ffmpeg
```

ffmpeg yoksa testler yine çalışır; `VideoHook` video kaydını atlar.

### 2.4 Python bağımlılıkları

```bash
cd fastapi-server
pip install -r requirements.txt -r requirements-dev.txt
```

### 2.5 Doğrulama

```bash
mvn validate                                  # Maven projesi geçerli mi?
mvn test                                      # Cucumber testleri koşar
cd fastapi-server && python3 -m pytest tests/ -v   # Python testleri
```

---

## 3. `.env` temelleri

Depo kökünde örnek dosya var:

```bash
cp .env.example .env
```

Sunucunun okuduğu en önemli değişkenler (`fastapi-server/.env` veya ortamdan):

```env
# Kimlik doğrulama (varsayılanlar: admin / admin123 — üretimde mutlaka değiştirin)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=güçlü_bir_şifre
JWT_SECRET=uzun_rastgele_bir_string
JWT_EXPIRATION_HOURS=24

# Dizinler
MANIFESTS_DIR=/path/to/repo/manifests        # varsayılan: <repo>/manifests
REPORTS_DUCKDB_PATH=reports.duckdb
# ALLURE_RESULTS_DIR=                         # varsayılan: <repo>/test-core/target/allure-results

# Jira (yoksa dry-run kullanın)
JIRA_URL=https://jira.sirketiniz.local
JIRA_PAT=personal_access_token
JIRA_PROJECT_KEY=PROJ
# JIRA_DRY_RUN=true
```

`.env` dosyası `.gitignore` içindedir, repoya gitmez. Tüm değişkenlerin listesi için [ENTEGRASYON.md](ENTEGRASYON.md) dosyasına bakın.

---

## 4. Windows kurulumu

### 4.1 Yazılımlar

Her kurulumdan sonra yeni bir terminal açın (PATH güncellenir).

1. **Python 3.11+** — https://www.python.org/downloads/ → kurulumda **"Add Python to PATH"** işaretleyin.
2. **Git** — https://git-scm.com/download/win → varsayılan seçeneklerle kurun.
3. **Java JDK 21** — https://adoptium.net/ → Windows x64 MSI, kurulumda **"Set JAVA_HOME"** açın.
4. **Apache Maven** — https://maven.apache.org/download.cgi → binary zip'i örn. `C:\tools\apache-maven-3.9.9\` dizinine çıkarın; `MAVEN_HOME` tanımlayın ve `C:\tools\apache-maven-3.9.9\bin`'i `PATH`'e ekleyin.
5. **NSSM** (servis olarak çalıştırmak için, opsiyonel) — https://nssm.cc/download → `C:\tools\nssm\win64\` yolunu PATH'e ekleyin.

Kontrol: `python --version`, `git --version`, `java -version`, `mvn -version`.

### 4.2 Projeyi indirme ve hızlı kurulum

```powershell
cd C:\
git clone https://github.com/Oltan/java-test-reports.git
cd java-test-reports

# Otomatik kontrol + paket kurulumu + .env oluşturma:
setup.bat
```

`setup.bat` Java/Python kontrolü yapar, `fastapi-server\requirements.txt` paketlerini kurar ve `.env.example`'dan `.env` üretir. Dev/test paketleri için ek olarak:

```powershell
cd fastapi-server
pip install -r requirements.txt -r requirements-dev.txt
```

### 4.3 İlk çalıştırma testi

```powershell
cd C:\java-test-reports\fastapi-server
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Tarayıcıdan `http://localhost:8000` açılıyorsa kurulum tamamdır. Gündelik başlatma için `scripts\start-server.bat` dosyasına çift tıklamak yeterlidir.

### 4.4 Windows servisi olarak kurma (NSSM, opsiyonel)

Yönetici PowerShell'de:

```powershell
nssm install TestRaporlama
nssm set TestRaporlama Application "C:\java-test-reports\fastapi-server\venv\Scripts\python.exe"
nssm set TestRaporlama AppDirectory "C:\java-test-reports\fastapi-server"
nssm set TestRaporlama AppParameters "-m uvicorn server:app --host 0.0.0.0 --port 8000"
nssm set TestRaporlama AppStdout "C:\java-test-reports\logs\server.log"
nssm set TestRaporlama AppStderr "C:\java-test-reports\logs\error.log"
nssm set TestRaporlama AppRotateFiles 1
nssm set TestRaporlama AppExit Default Restart
mkdir C:\java-test-reports\logs
nssm start TestRaporlama
nssm status TestRaporlama   # SERVICE_RUNNING beklenir
```

> Sanal ortam kullanmıyorsanız `Application` değerini sistem Python'una (`python.exe` tam yolu) çevirin. Sanal ortam için önce `python -m venv venv` ve `venv\Scripts\activate` ile paketleri kurun.

Servis yönetimi: `nssm start|stop|restart|status|remove TestRaporlama`.

### 4.5 Güvenlik duvarı (ağdan erişim)

```powershell
netsh advfirewall firewall add rule name="Test Raporlama" dir=in action=allow protocol=TCP localport=8000
```

Ağdaki diğer makinelerden erişim: `http://IP_ADRESI:8000` (`ipconfig | findstr "IPv4"`).

### 4.6 HTTPS / Nginx

Sistemin önüne reverse proxy ve HTTPS koymak için: [NGINX_HTTPS.md](NGINX_HTTPS.md)

### 4.7 Güncelleme

```powershell
nssm stop TestRaporlama
cd C:\java-test-reports
git pull origin master
cd fastapi-server
pip install -r requirements.txt -r requirements-dev.txt
nssm start TestRaporlama
```

---

## 5. Sık karşılaşılan kurulum sorunları

| Belirti | Çözüm |
|---|---|
| `mvn` bulunamıyor | Maven `bin/` dizinini PATH'e ekleyin; sunucu için alternatif olarak `MAVEN_CMD` ortam değişkenine mvn'in tam yolunu verin |
| `allure` bulunamıyor | Allure CLI `bin/` dizinini PATH'e ekleyin veya `ALLURE_BIN` ile tam yol verin |
| 8000 portu meşgul | `netstat -ano \| findstr :8000` (Windows) / `lsof -i :8000` (Linux) ile süreci bulup kapatın |
| DuckDB kilitleniyor | Aynı `.duckdb` dosyasını iki süreç açamaz; sunucuyu tek kopya çalıştırın |
| `.env` okunmuyor | Dosyanın `fastapi-server/` içinde olduğundan emin olun (`python-dotenv` otomatik yükler) |
| Video kaydı yok | `ffmpeg` kurulu mu? CI'da sanal ekran (Xvfb) gerekir; yoksa hook atlanır |

Sonraki adımlar: testleri çalıştırma için [CALISTIRMA.md](CALISTIRMA.md), başka bir Java projesini bağlama için [ENTEGRASYON.md](ENTEGRASYON.md).
