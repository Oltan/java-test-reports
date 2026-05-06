# Windows — Nginx + HTTPS Kurulum Rehberi

Bu rehber `WINDOWS_KURULUM.md` ile birlikte kullanılır. FastAPI uygulamasının önüne Nginx reverse proxy ve HTTPS ekler.

---

## Sertifika seçeneğini belirleyin

| Durum | Seçenek |
|---|---|
| Şirket IT'den sertifika alabiliyorsunuz | **A — Şirket sertifikası** |
| Domain/IP ile self-signed yeterli | **B — Self-signed** (en yaygın) |
| İnternete açık public domain var | **C — Let's Encrypt** |

Şirket içi kullanım için **Seçenek B** yeterlidir. Adım 2'yi atlayıp IT'den aldığınız `.crt` ve `.key` dosyalarını `C:\java-test-reports\ssl\` klasörüne koyarsanız **Adım 3'ten** devam edin.

---

## Adım 1 — OpenSSL kur

```powershell
# Windows 11 / güncel Windows 10 — winget ile
winget install ShiningLight.OpenSSL

# Veya manuel:
# https://slproweb.com/products/Win32OpenSSL.html
# → "Win64 OpenSSL v3.x.x Light" indir ve kur
```

Kontrol:
```powershell
openssl version
# OpenSSL 3.x.x ... gibi çıktı gelmeli
```

---

## Adım 2 — Self-signed sertifika üret

```powershell
# SSL klasörü oluştur
mkdir C:\java-test-reports\ssl
cd C:\java-test-reports\ssl

# Önce PC'nin IP adresini öğrenin
ipconfig | findstr "IPv4"
# Örneğin: 192.168.1.100
```

Sertifikayı üretin (IP adresini kendinizinkiyle değiştirin):

```powershell
openssl req -x509 -newkey rsa:4096 -sha256 -days 1825 -nodes `
  -keyout sertifika.key `
  -out    sertifika.crt `
  -subj   "/CN=raporlama" `
  -addext "subjectAltName=IP:192.168.1.100,DNS:raporlama.local"
```

Parametreler:
- `-days 1825` → 5 yıl geçerli
- `IP:192.168.1.100` → PC'nin ağ IP'si (ağdaki herkes bu IP ile erişir)
- `DNS:raporlama.local` → Opsiyonel, hosts dosyasına ekleyerek isimle erişmek isterseniz

Oluşan dosyalar:
```
C:\java-test-reports\ssl\sertifika.key   ← özel anahtar (kimseye vermeyin)
C:\java-test-reports\ssl\sertifika.crt   ← sertifika (tarayıcılara dağıtın)
```

---

## Adım 3 — Nginx indir

```powershell
# İndirme klasörüne gid
cd C:\Users\$env:USERNAME\Downloads

# Nginx stable sürümünü indir
Invoke-WebRequest `
  -Uri "https://nginx.org/download/nginx-1.26.2.zip" `
  -OutFile "nginx.zip"

# C:\tools\ altına çıkar ve klasörü yeniden adlandır
Expand-Archive nginx.zip -DestinationPath C:\tools\
Rename-Item C:\tools\nginx-1.26.2 C:\tools\nginx
```

Kontrol:
```powershell
C:\tools\nginx\nginx.exe -v
# nginx version: nginx/1.26.x
```

---

## Adım 4 — Nginx yapılandır

`C:\tools\nginx\conf\nginx.conf` dosyasını açın (Notepad veya VS Code ile) ve içeriğini **tamamen** aşağıdakiyle değiştirin.

> `192.168.1.100` satırını kendi IP adresinizle değiştirin.

```nginx
worker_processes 1;

events {
    worker_connections 1024;
}

http {
    include       mime.types;
    default_type  application/octet-stream;
    sendfile      on;
    keepalive_timeout 65;

    # ── HTTP → HTTPS yönlendirme ────────────────────────────────
    server {
        listen 80;
        server_name _;
        return 301 https://$host$request_uri;
    }

    # ── HTTPS ───────────────────────────────────────────────────
    server {
        listen 443 ssl;
        server_name 192.168.1.100 raporlama.local;   # ← kendi IP'niz

        ssl_certificate     C:/java-test-reports/ssl/sertifika.crt;
        ssl_certificate_key C:/java-test-reports/ssl/sertifika.key;
        ssl_protocols       TLSv1.2 TLSv1.3;
        ssl_ciphers         HIGH:!aNULL:!MD5;
        ssl_session_cache   shared:SSL:10m;
        ssl_session_timeout 10m;

        # Allure sonuç zip'leri için büyük yükleme limiti
        client_max_body_size 200M;

        # FastAPI'ye ilet
        location / {
            proxy_pass         http://127.0.0.1:8000;
            proxy_http_version 1.1;

            # WebSocket desteği (admin paneli canlı log için)
            proxy_set_header   Upgrade    $http_upgrade;
            proxy_set_header   Connection "upgrade";

            proxy_set_header   Host              $host;
            proxy_set_header   X-Real-IP         $remote_addr;
            proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;

            proxy_connect_timeout 60s;
            proxy_read_timeout    300s;
            proxy_send_timeout    300s;
        }
    }
}
```

Konfigürasyonu test edin (hata varsa burada görünür):
```powershell
C:\tools\nginx\nginx.exe -t
# nginx: configuration file ... syntax is ok
# nginx: configuration file ... test is successful
```

---

## Adım 5 — Nginx'i Windows servisi yap

**Yönetici olarak açılmış** PowerShell'de:

```powershell
# Log klasörünü oluştur (yoksa)
mkdir C:\java-test-reports\logs -ErrorAction SilentlyContinue

# Nginx'i servis olarak kaydet
nssm install Nginx "C:\tools\nginx\nginx.exe"
nssm set Nginx AppDirectory  "C:\tools\nginx"
nssm set Nginx AppStdout     "C:\java-test-reports\logs\nginx.log"
nssm set Nginx AppStderr     "C:\java-test-reports\logs\nginx-error.log"
nssm set Nginx AppRotateFiles 1
nssm set Nginx AppRotateBytes 10485760
nssm set Nginx AppExit Default Restart
nssm set Nginx AppRestartDelay 3000

# Servisi başlat
nssm start Nginx
```

Durum kontrolü:
```powershell
nssm status Nginx
# SERVICE_RUNNING
```

---

## Adım 6 — Güvenlik duvarı

**Yönetici olarak açılmış** PowerShell'de:

```powershell
# HTTP portu (HTTPS'e yönlendirme için)
netsh advfirewall firewall add rule `
  name="Raporlama HTTP" `
  dir=in action=allow protocol=TCP localport=80

# HTTPS portu (asıl erişim)
netsh advfirewall firewall add rule `
  name="Raporlama HTTPS" `
  dir=in action=allow protocol=TCP localport=443
```

---

## Adım 7 — Sertifikayı tarayıcılara tanıt

Self-signed sertifika kullanıyorsanız tarayıcı "Bağlantınız güvenli değil" uyarısı verir. Bunu kalıcı olarak çözmek için:

### Bu PC'de (bir kez yapın):

```powershell
Import-Certificate `
  -FilePath "C:\java-test-reports\ssl\sertifika.crt" `
  -CertStoreLocation Cert:\LocalMachine\Root
```

### Ağdaki diğer bilgisayarlarda:

1. `C:\java-test-reports\ssl\sertifika.crt` dosyasını USB veya ağ paylaşımıyla gönderin
2. Karşı bilgisayarda dosyaya çift tıklayın
3. **"Sertifikayı Yükle"** → **"Yerel Makine"** → **"Tüm sertifikaları aşağıdaki depoya yerleştir"** → **"Gözat"** → **"Güvenilen Kök Sertifika Yetkilileri"** → Tamam

Bundan sonra o tarayıcıda uyarı çıkmaz.

---

## Test

Tüm adımlar bittikten sonra kontrol listesi:

```powershell
# İki servis de çalışıyor mu?
nssm status TestRaporlama
nssm status Nginx
# Her ikisi de SERVICE_RUNNING olmalı

# Portlar açık mı?
netstat -ano | findstr ":80 \|:443 \|:8000 "

# Nginx log'unda hata var mı?
Get-Content C:\java-test-reports\logs\nginx-error.log -Tail 20
```

Tarayıcıdan erişim:

| URL | Beklenen |
|---|---|
| `http://192.168.1.100` | Otomatik `https://`'e yönlendirilir |
| `https://192.168.1.100` | Dashboard login sayfası açılır |
| `http://localhost:8000` | FastAPI direkt (nginx bypass, sadece bu PC'den) |

---

## Nginx servis yönetimi

```powershell
nssm start   Nginx   # başlat
nssm stop    Nginx   # durdur
nssm restart Nginx   # yeniden başlat (nginx.conf değişikliğinden sonra)
nssm remove  Nginx   # servisi kaldır
```

Konfigürasyon değişikliği sonrası nginx'i yeniden yüklemek için (servisi durdurmadan):
```powershell
C:\tools\nginx\nginx.exe -s reload
```

---

## Sorun giderme

### 443 portu zaten kullanımda

```powershell
netstat -ano | findstr ":443"
# Çıkan PID'i bul, hangi program olduğuna bak:
tasklist | findstr "<PID>"
```

Genellikle IIS veya başka bir web sunucusu işgal eder. IIS'i durdurun:
```powershell
net stop w3svc
Set-Service w3svc -StartupType Disabled
```

### nginx başlamıyor

```powershell
# Hata loguna bak
Get-Content C:\java-test-reports\logs\nginx-error.log -Tail 30

# Konfigürasyonu test et
C:\tools\nginx\nginx.exe -t
```

En yaygın hatalar:
- `sertifika.crt` veya `sertifika.key` yolu yanlış (Linux `/` yerine Windows `/` kullanın — nginx.conf'ta `/` çalışır)
- Port 80 veya 443 başka uygulama tarafından kullanılıyor

### WebSocket bağlantısı kesilıyor

Admin panelindeki canlı log WebSocket kullanır. Nginx timeout değerlerini artırın:
```nginx
proxy_read_timeout 86400s;   # 24 saat
proxy_send_timeout 86400s;
```

### Sertifika süresi doldu

Yeni sertifika üretip servisi yeniden başlatın:
```powershell
cd C:\java-test-reports\ssl

openssl req -x509 -newkey rsa:4096 -sha256 -days 1825 -nodes `
  -keyout sertifika.key `
  -out    sertifika.crt `
  -subj   "/CN=raporlama" `
  -addext "subjectAltName=IP:192.168.1.100,DNS:raporlama.local"

nssm restart Nginx
```
