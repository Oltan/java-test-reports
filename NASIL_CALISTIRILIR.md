# 🚀 Test Raporlama Sistemi — Windows Erişim Rehberi

## ⚡ TEK ADIMDA BAŞLAT

**Windows PowerShell veya CMD'yi aç, şunu yaz:**

```bash
wsl bash /mnt/c/Users/ol_ta/desktop/java_reports/start.sh
```

Ya da WSL terminalinde:
```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports && bash start.sh
```

Terminali **kapatma**, sunucu çalıştığı sürece açık kalsın.

---

## 🌐 TARAYICIDA AÇ

Sunucu başladıktan sonra, Windows'ta tarayıcını aç:

| Adres | İçerik |
|-------|--------|
| **http://localhost:8000** | Ana dashboard |
| http://localhost:8000/docs | API dökümanı (Swagger) |
| http://localhost:8000/reports/live-demo-001/triage | Hata kartları |

**localhost çalışmazsa WSL IP dene:**
```bash
# PowerShell'de WSL IP'yi bul:
wsl hostname -I
# Çıkan IP'yi kullan: http://172.XX.XX.XX:8000
```

---

## 🔑 Login

Dashboard sayfasında form var:
- Username: `admin`
- Password: `admin123`

Token'ı aldıktan sonra tüm endpoint'ler çalışır.

---

## 🧪 Testleri Koş

```bash
wsl
cd /mnt/c/Users/ol_ta/desktop/java_reports
export PATH="/home/ol_ta/tools/apache-maven-3.9.9/bin:$PATH"
mvn -pl test-core test  # Cucumber testleri
```

---

## 📊 Ekran Görüntüsü

Sunucu çalışırken terminal şöyle görünür:
```
INFO:     Started server process [XXXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

Tarayıcıda dashboard:
```
╔══════════════════════════════╗
║   Test Raporlama Sistemi    ║
║                             ║
║   📊 4 Test Run             ║
║   🟩 6 passed  🟥 3 failed  ║
║                             ║
║   🔗 Hızlı Linkler          ║
║   🔑 Giriş Yap              ║
╚══════════════════════════════╝
```
