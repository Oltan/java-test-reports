# Windows Kurulum Rehberi

Bu rehber, raporlama platformunu Windows PC'ye production olarak kurar. Sonunda sistem Windows başladığında otomatik açılır, tarayıcıdan erişilebilir olur.

---

## 1. Gerekli yazılımlar

Sırasıyla kurun. Her birinde kurulum tamamlandıktan sonra yeni bir terminal açın (PATH güncellenir).

### 1.1 Python 3.12

1. https://www.python.org/downloads/ → "Download Python 3.12.x"
2. Kurulum sırasında **"Add Python to PATH"** kutusunu işaretleyin
3. Kontrol:
```
python --version
pip --version
```

### 1.2 Git

1. https://git-scm.com/download/win → "64-bit Git for Windows"
2. Kurulum sırasında tüm seçenekleri varsayılan bırakın
3. Kontrol:
```
git --version
```

### 1.3 Java JDK 21 (test çalıştırmak için)

1. https://adoptium.net/ → "Latest LTS: JDK 21" → Windows x64 MSI
2. Kurulum sırasında **"Set JAVA_HOME"** seçeneğini açın
3. Kontrol:
```
java -version
```

### 1.4 Apache Maven (test çalıştırmak için)

1. https://maven.apache.org/download.cgi → "Binary zip archive" indir
2. Örneğin `C:\tools\apache-maven-3.9.9\` klasörüne çıkar
3. Sistem ortam değişkenlerine ekle:
   - `MAVEN_HOME` = `C:\tools\apache-maven-3.9.9`
   - `PATH`'e ekle: `C:\tools\apache-maven-3.9.9\bin`
4. Kontrol:
```
mvn -version
```

### 1.5 NSSM (Windows Servis Yöneticisi)

Uygulamayı Windows servisi olarak çalıştırmak için kullanılır.

1. https://nssm.cc/download → "nssm 2.24 (2014-08-31)" → zip indir
2. `C:\tools\nssm\` klasörüne çıkar
3. `C:\tools\nssm\win64\` yolunu PATH'e ekle
4. Kontrol:
```
nssm version
```

---

## 2. Projeyi indirme

PowerShell veya Komut İstemi'ni **Yönetici olarak** açın:

```powershell
# İstediğiniz dizine gidin, örneğin:
cd C:\

# Repoyu klonla
git clone https://github.com/Oltan/java-test-reports.git
cd java-test-reports
```

---

## 3. Python bağımlılıklarını kurma

```powershell
cd C:\java-test-reports\fastapi-server

# Sanal ortam oluştur (production için önerilen)
python -m venv venv

# Sanal ortamı aktifleştir
venv\Scripts\activate

# Bağımlılıkları kur
pip install -r requirements.txt
```

---

## 4. Ortam değişkenlerini ayarlama (.env)

`C:\java-test-reports\fastapi-server\.env` dosyasını oluşturun:

```env
# ── Kimlik doğrulama ──────────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=GüçlüBirŞifre123!
JWT_SECRET=bu_en_az_32_karakter_uzun_rastgele_bir_string_olmali

# ── Dizinler ─────────────────────────────────────────────────
MANIFESTS_DIR=C:\java-test-reports\manifests
REPORTS_DUCKDB_PATH=C:\java-test-reports\fastapi-server\reports.duckdb

# ── Jira (gerçek Jira varsa) ─────────────────────────────────
JIRA_URL=https://jira.sirketiniz.local
JIRA_PAT=jira_personal_access_token
JIRA_PROJECT_KEY=PROJ
JIRA_ISSUE_TYPE=Bug

# ── Jira yoksa dry-run modda çalış ───────────────────────────
# JIRA_DRY_RUN=true

# ── Maven yolu (PATH'te değilse) ─────────────────────────────
# MAVEN_CMD=C:\tools\apache-maven-3.9.9\bin\mvn.cmd
```

> **Önemli:** `.env` dosyasını Git'e commit etmeyin. `.gitignore`'da zaten var.

---

## 5. İlk çalıştırma testi

Servise kaydetmeden önce çalıştığını doğrulayın:

```powershell
cd C:\java-test-reports\fastapi-server
venv\Scripts\activate

# Sunucuyu başlat
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Tarayıcıdan açın: `http://localhost:8000`

Dashboard görünüyorsa Ctrl+C ile durdurun ve servis kurulumuna geçin.

---

## 6. Windows servisi olarak kurma (NSSM)

**Yönetici olarak açılmış** PowerShell'de:

```powershell
# Servis kur
nssm install TestRaporlama

# Açılan GUI'de şunları doldurun:
#   Path:     C:\java-test-reports\fastapi-server\venv\Scripts\python.exe
#   Startup directory: C:\java-test-reports\fastapi-server
#   Arguments: -m uvicorn server:app --host 0.0.0.0 --port 8000

# Veya GUI yerine komutla:
nssm set TestRaporlama Application "C:\java-test-reports\fastapi-server\venv\Scripts\python.exe"
nssm set TestRaporlama AppDirectory "C:\java-test-reports\fastapi-server"
nssm set TestRaporlama AppParameters "-m uvicorn server:app --host 0.0.0.0 --port 8000"

# .env dosyasını servis ortamına tanıt
nssm set TestRaporlama AppEnvironmentExtra "DOTENV_PATH=C:\java-test-reports\fastapi-server\.env"

# Log dosyaları
nssm set TestRaporlama AppStdout "C:\java-test-reports\logs\server.log"
nssm set TestRaporlama AppStderr "C:\java-test-reports\logs\error.log"
nssm set TestRaporlama AppRotateFiles 1
nssm set TestRaporlama AppRotateBytes 10485760

# Crash'te otomatik yeniden başlat
nssm set TestRaporlama AppExit Default Restart
nssm set TestRaporlama AppRestartDelay 3000

# Servisi başlat
nssm start TestRaporlama
```

Log dizinini oluşturun:
```powershell
mkdir C:\java-test-reports\logs
```

Servis durumunu kontrol edin:
```powershell
nssm status TestRaporlama
# Beklenen çıktı: SERVICE_RUNNING
```

---

## 7. Windows Güvenlik Duvarı

8000 portuna dışarıdan erişim için:

```powershell
# 8000 portunu aç
netsh advfirewall firewall add rule `
  name="Test Raporlama" `
  dir=in `
  action=allow `
  protocol=TCP `
  localport=8000
```

Ağdaki başka bilgisayarlardan erişim: `http://BILGISAYAR_ADI:8000` veya `http://IP_ADRESI:8000`

IP adresini öğrenmek için:
```powershell
ipconfig | findstr "IPv4"
```

---

## 8. Nginx ile HTTPS (opsiyonel ama önerilen)

Şirket sertifikası veya self-signed sertifika varsa HTTPS ekleyin.

### 8.1 Nginx kurulumu

1. https://nginx.org/en/download.html → "Stable version" → Windows zip
2. `C:\tools\nginx\` klasörüne çıkar

### 8.2 Nginx konfigürasyonu

`C:\tools\nginx\conf\nginx.conf` dosyasını düzenleyin:

```nginx
worker_processes 1;

events {
    worker_connections 1024;
}

http {
    # HTTP → HTTPS yönlendirme
    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    # HTTPS
    server {
        listen 443 ssl;
        server_name raporlama.sirketiniz.local;

        ssl_certificate     C:/tools/nginx/ssl/sertifika.crt;
        ssl_certificate_key C:/tools/nginx/ssl/sertifika.key;
        ssl_protocols       TLSv1.2 TLSv1.3;

        client_max_body_size 100M;

        location / {
            proxy_pass         http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header   Upgrade $http_upgrade;
            proxy_set_header   Connection "upgrade";
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_read_timeout 300s;
        }
    }
}
```

### 8.3 Nginx'i servis olarak kur

```powershell
nssm install Nginx "C:\tools\nginx\nginx.exe"
nssm set Nginx AppDirectory "C:\tools\nginx"
nssm start Nginx
```

---

## 9. Güncellemeler

Yeni sürüm geldiğinde:

```powershell
# Servisi durdur
nssm stop TestRaporlama

# Kodu güncelle
cd C:\java-test-reports
git pull origin master

# Bağımlılıkları güncelle
cd fastapi-server
venv\Scripts\activate
pip install -r requirements.txt

# Servisi başlat
nssm start TestRaporlama
```

---

## 10. Servis yönetimi

```powershell
nssm start   TestRaporlama   # başlat
nssm stop    TestRaporlama   # durdur
nssm restart TestRaporlama   # yeniden başlat
nssm status  TestRaporlama   # durum
nssm remove  TestRaporlama   # servisi kaldır
```

Logları takip etmek için:

```powershell
Get-Content C:\java-test-reports\logs\server.log -Wait -Tail 50
```

---

## 11. Sorun giderme

### Servis başlamıyor

```powershell
# Hata loguna bak
Get-Content C:\java-test-reports\logs\error.log -Tail 30

# Elle çalıştırarak hatayı gör
cd C:\java-test-reports\fastapi-server
venv\Scripts\activate
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### 8000 portu meşgul

```powershell
netstat -ano | findstr :8000
# PID'i bulup:
taskkill /PID <pid> /F
```

### .env okunmuyor

`server.py` başında `python-dotenv` ile `.env` otomatik yüklenir. Elle kontrol:

```powershell
cd C:\java-test-reports\fastapi-server
venv\Scripts\activate
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('ADMIN_PASSWORD'))"
```

### DuckDB kilitleniyor

Aynı anda iki process aynı `.duckdb` dosyasını açamaz. Servisi durdurup tekrar başlatın:

```powershell
nssm stop TestRaporlama
nssm start TestRaporlama
```

### Manifests bulunamıyor

`.env` dosyasında `MANIFESTS_DIR` yolunun var olduğunu kontrol edin:

```powershell
Test-Path "C:\java-test-reports\manifests"
# False döndürürse:
mkdir C:\java-test-reports\manifests
```

---

## Özet — Kurulum sonrası kontrol listesi

- [ ] `http://localhost:8000` açılıyor
- [ ] Admin girişi çalışıyor
- [ ] `nssm status TestRaporlama` → `SERVICE_RUNNING`
- [ ] Bilgisayar yeniden başlatıldıktan sonra servis otomatik açılıyor
- [ ] Güvenlik duvarı kuralı eklendi, ağdan erişilebiliyor
- [ ] `.env` dosyasında gerçek şifre ve JWT_SECRET var (varsayılan değil)
