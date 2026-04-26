# 🚀 Test Raporlama Sistemi - Windows Erişim Rehberi

## Sistem Nerede Çalışıyor?

Sunucu **WSL (Ubuntu)** içinde, FastAPI ile `localhost:8000` portunda çalışıyor.
Windows, WSL portlarını otomatik yönlendirdiği için **Windows tarayıcısından direkt erişebilirsiniz.**

---

## ⚡ HIZLI BAŞLATMA (3 Yöntem)

### Yöntem 1: Windows Batch Dosyası (En Kolay)

`scripts/start-server.bat` dosyasına **çift tıkla**.

```
java_reports/
└── scripts/
    └── start-server.bat  ← Buna çift tıkla!
```

### Yöntem 2: WSL Terminalinden

```bash
wsl
cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### Yöntem 3: IntelliJ IDEA Terminal

IntelliJ'de Terminal'i aç (View → Tool Windows → Terminal), WSL seçiliyse:

```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

---

## 🌐 Windows Tarayıcısından Erişim

Sunucu başladıktan sonra, **Windows'ta herhangi bir tarayıcıda** şu adresleri açın:

### 1. Ana Dashboard (Login gerektirmez)
```
http://localhost:8000/
```
→ Test run'larını, istatistikleri ve hızlı linkleri gösterir.

### 2. Swagger API Dokümantasyonu
```
http://localhost:8000/docs
```
→ Tüm API endpoint'lerini buradan test edebilirsiniz.
→ Sağ üstteki **"Authorize"** butonuna tıklayıp token girin.

### 3. Test Run'ları (Token gerekir)
```
http://localhost:8000/api/v1/runs
```
→ Header: `Authorization: Bearer TOKEN_BURAYA`

### 4. Triage - Hata Kartları
```
http://localhost:8000/reports/live-demo-001/triage
```

### 5. Bug Durumu
```
http://localhost:8000/api/v1/bugs/DOORS-12345
```

---

## 🔑 Token Nasıl Alınır?

### Postman ile:
```
POST http://localhost:8000/api/v1/auth/login
Body (JSON):
{
    "username": "admin",
    "password": "admin123"
}
```
Cevaptaki `token` değerini kopyalayın.

### Komut Satırından (WSL / PowerShell):
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### Swagger'dan:
1. `http://localhost:8000/docs` açın
2. `POST /api/v1/auth/login` endpoint'ini bulun
3. "Try it out" → body'ye `{"username":"admin","password":"admin123"}` yazın
4. "Execute" → gelen token'ı kopyalayın
5. Sağ üstte "Authorize" → token'ı yapıştırın → "Authorize"
6. Artık tüm endpoint'ler çalışır!

---

## 📊 API Endpoint Özeti

| Method | URL | Auth | Açıklama |
|--------|-----|------|----------|
| `GET` | `/` | ❌ | Ana dashboard sayfası |
| `GET` | `/docs` | ❌ | Swagger dokümantasyonu |
| `POST` | `/api/v1/auth/login` | ❌ | Token al |
| `GET` | `/api/v1/runs` | ✅ | Tüm test run'ları |
| `GET` | `/api/v1/runs/{id}` | ✅ | Tek run detayı |
| `GET` | `/api/v1/runs/{id}/failures` | ✅ | Sadece hatalar |
| `GET` | `/api/v1/bugs` | ✅ | Tüm bug eşleşmeleri |
| `GET` | `/api/v1/bugs/{doors}` | ✅ | DOORS numarasına göre bug |
| `POST` | `/api/v1/bugs/{doors}/create` | ✅ | Yeni Jira bug aç |
| `GET` | `/reports/{id}/triage` | ✅ | Hata kartları sayfası |

---

## 🔧 Sorun Giderme

### "localhost:8000 açılmıyor"
```bash
# WSL'de sunucunun çalıştığını kontrol et:
wsl curl http://localhost:8000/docs
```

### "Connection refused"
Sunucu başlamamış. WSL'de:
```bash
cd /mnt/c/Users/ol_ta/desktop/java_reports/fastapi-server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000
```

### "401 Unauthorized"
Token eksik veya geçersiz. Tekrar login olup yeni token alın.

### "404 Not Found"
Run ID yanlış olabilir. Önce `/api/v1/runs` ile mevcut run'ları listeleyin.
