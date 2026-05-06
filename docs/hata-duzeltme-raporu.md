# Test Raporlama Sistemi — Hata Düzeltme Raporu

**Tarih:** 2026-05-06
**Sorun:** Admin panelde test başlatılamıyor, "Aktif Testler" kısmı takılı kalıyor, WebSocket bağlantı hatası

---

## 1. Cookie Path Eksikliği — Login Refresh Sonrası Sıfırlanıyordu

### Sorun
Kullanıcı login olduktan sonra sayfayı refresh edince tekrar login ekranı geliyordu.

### Nedeni
`server.py` satır 898'de `set_cookie` çağrısında `path` parametresi belirtilmemişti:

```python
# HATALI
response.set_cookie(key="access_token", value=token, httponly=False, max_age=..., samesite="lax")
```

Cookie default olarak isteğin path'ine (`/api/v1/auth/`) göre ayarlanıyordu. `/admin` ve `/dashboard` isteklerinde cookie gönderilmiyordu.

### Çözüm
`path="/"` eklendi:

```python
# DOĞRU
response.set_cookie(
    key="access_token", value=token, httponly=False,
    max_age=JWT_EXPIRATION_HOURS * 3600, samesite="lax", path="/"
)
```

---

## 2. Pydantic Status Validation — "broken" Durumu Reddediliyordu

### Sorun
`manifests/` klasöründeki bazı JSON dosyalarında `"status": "broken"` vardı. Pydantic model sadece `passed|failed|skipped` kabul ediyordu. `load_manifests()` çağrıldığında `ValidationError` fırlatıyordu → HTTP 500 → frontend token'ı siliyordu → login ekranı.

### Çözüm
`fastapi-server/models.py` satır 19 ve 27'de pattern'e `broken` eklendi:

```python
# HATALI
status: str = Field(pattern=r"^(passed|failed|skipped)$")

# DOĞRU
status: str = Field(pattern=r"^(passed|failed|skipped|broken)$")
```

---

## 3. WebSocket Endpoint Eksikliği

### Sorun
Admin paneli `/ws/test-status/{runId}` adresine WebSocket bağlantısı kurmaya çalışıyordu ama bu endpoint sunucuda yoktu. Dashboard ise `/ws/test-status/live` kullanıyordu (tek endpoint vardı).

### Çözüm
İki ayrı endpoint eklendi:

1. **Dashboard için:** `@app.websocket("/ws/test-status/live")` — global canlı durum
2. **Admin için:** `@app.websocket("/ws/test-status/{run_id}")` — spesifik test takibi

Ayrıca `admin.js`'e token query parametresi eklendi:

```javascript
const ws = new WebSocket(
  `${protocol}://${location.host}/ws/test-status/${runId}?token=${encodeURIComponent(token)}`
);
```

---

## 4. Zombie Test İşleri — DB'de "running" Kalıyordu

### Sorun
Test başlatıldığında `jobs` ve `worker_runs` tablolarına "running" kaydı atılıyordu. Test tamamlandığında ise:

1. **Exception'lar kayboluyordu** — `asyncio.create_task()` ile başlatılan background task'ların exception'ları hiçbir zaman loglanmıyordu
2. **DB update hatası** — DuckDB'nin Foreign Key kısıtlaması nedeniyle `UPDATE jobs SET status='completed'` çalışmıyordu

### Nedeni

**4a. Exception Logging Eksikliği**
```python
# HATALI — exception kayboluyor
task = asyncio.create_task(execute_test_run(run_id, options))
task.add_done_callback(test_tasks.discard)
```

**4b. DuckDB Foreign Key Kısıtlaması**
`worker_runs` tablosu:
```sql
-- HATALI — DuckDB UPDATE sırasında parent tabloya dokunulamıyor
job_id TEXT REFERENCES jobs(job_id),
run_id TEXT REFERENCES runs(id),
```

`worker_runs` INSERT'ünde `run_id` eksikti (FK'yi ihlal etmiyordu ama admin panel run_id alamıyordu).

### Çözüm

**4a. Exception Handler Eklendi**
```python
def _log_task_exception(task: asyncio.Task) -> None:
    if task.done() and not task.cancelled():
        exc = task.exception()
        if exc is not None:
            import traceback
            print(f"[ERROR] Background task failed: {exc}")
            traceback.print_exception(type(exc), exc, exc.__traceback__)

# Kullanımı
task = asyncio.create_task(execute_test_run(run_id, options))
task.add_done_callback(lambda t: test_tasks.discard(t))
task.add_done_callback(_log_task_exception)
```

**4b. Foreign Key Kısıtlamaları Kaldırıldı**
`db.py`'de workflow tablolarından FK'ler çıkarıldı:

```sql
-- DOĞRU
CREATE TABLE worker_runs (
  worker_id TEXT PRIMARY KEY,
  job_id TEXT,        -- REFERENCES kaldırıldı
  run_id TEXT,        -- REFERENCES kaldırıldı
  ...
);
```

Benzer şekilde `pipeline_status` ve `triage_decisions` tablolarından da `REFERENCES runs(id)` kaldırıldı.

**4c. `run_id` INSERT'e Eklendi**
`start_tests()` fonksiyonunda `worker_runs` INSERT'ine `run_id` kolonu eklendi:

```python
# HATALI
INSERT INTO worker_runs (worker_id, job_id, shard, status, output_dir, started_at)
VALUES (?, ?, ?, 'running', ?, ?)

# DOĞRU
INSERT INTO worker_runs (worker_id, job_id, run_id, shard, status, output_dir, started_at)
VALUES (?, ?, ?, ?, 'running', ?, ?)
```

**4d. `init_schema` Eksikliği**
`start_tests()` ve `list_running_tests()` fonksiyonlarında `init_schema(conn)` çağrısı eksikti. Yeni DB oluşturulduğunda tablolar yoktu. Her iki fonksiyona da eklendi.

**4e. `execute_test_run` Hata Yönetimi**
`try/finally` yerine `try/except/finally` kullanıldı. Her durumda (başarılı veya hatalı) "complete" broadcast gönderiliyor ve DB güncelleniyor:

```python
try:
    await asyncio.gather(consume_stream(proc.stdout), consume_stream(proc.stderr))
    await proc.wait()
    saved = _save_results_to_duckdb(run_id, options, started_at)
except Exception as e:
    stats["error"] = str(e)
    stats["running"] = 0
finally:
    running_tests.pop(run_id, None)

# Her durumda complete broadcast
await ws_manager.broadcast(run_id, {"type": "complete", ...})

# DB'yi her durumda güncelle
final_status = "completed" if not stats.get("error") else "failed"
UPDATE jobs SET status = ?, ended_at = ? WHERE job_id = ?
UPDATE worker_runs SET status = ?, ended_at = ? WHERE run_id = ?
```

---

## 5. Test Veri Yolları

### Sorun
`WebDriverFactory.java`'de Chrome ve ChromeDriver yolları WSL ortamına uygun değildi.

### Çözüm
- Chrome binary: `/tmp/chrome-linux64/chrome` → `/usr/bin/google-chrome-stable`
- ChromeDriver: İndirilip `/tmp/chromedriver-linux64/chromedriver`'e kuruldu
- Fazla agresif headless flag'ler (`--single-process`, `--no-zygote`, `--remote-debugging-port`) kaldırıldı

---

## Dosya Değişiklikleri Özeti

| Dosya | Değişiklik |
|-------|-----------|
| `server.py` | Cookie `path="/"`, WebSocket endpoint'leri, `init_schema` çağrıları, exception logging, `try/except/finally` |
| `models.py` | `broken` status pattern'e eklendi |
| `db.py` | `worker_runs`, `pipeline_status`, `triage_decisions` FK kısıtlamaları kaldırıldı |
| `websocket_handler.py` | "live" global broadcast desteği eklendi |
| `admin.js` | WebSocket URL'sine `?token=` eklendi, `onmessage`/`onerror` syntax hatası düzeltildi |
| `WebDriverFactory.java` | Chrome/Chromedriver yolları düzeltildi, flag'ler sadeleştirildi |

---

## 6. WebSocket `onmessage` JavaScript Syntax Hatası

### Sorun
Admin panelde test başlatılıyor, WebSocket bağlantısı kuruluyor, server mesajları gönderiyor ama UI hiç güncellenmiyordu. Browser console'da `Missing catch or finally after try` hatası vardı.

### Nedeni
`admin.js`'de `ws.onmessage` handler'ının içinde `ws.onerror` tanımlanmıştı. `try` bloğu kapanmadan önce `onerror` assignment başlamış, sonra `catch` bloğu yanlış yere yerleştirilmişti. Sonuçta JavaScript parser `try`'yi tamamlanmamış gördü ve tüm `onmessage` handler'ını çalıştırmadı.

```javascript
// HATALI — onerror onmessage içinde, catch yanlış yerde
ws.onmessage = (e) => {
    try {
      ...
    };                           // ← try burada bitiyor gibi görünüyor
    ws.onerror = () => {         // ← ama aslında onmessage içinde!
      ...
    } catch (err) {              // ← catch neye ait? Syntax error!
      ...
    }
  };
};
```

### Çözüm
Handler'lar ayrıldı, `try/catch` düzgün yapılandırıldı:

```javascript
// DOĞRU
ws.onmessage = (e) => {
    try {
      const raw = JSON.parse(e.data);
      const d = raw.data || raw;
      if (raw.type === "progress" || d.type === "progress" || raw.type === "update") {
        ...
      } else if (raw.type === "complete" || d.type === "complete") {
        ...
      }
    } catch (err) {
      console.error("[WS] onmessage error:", err);
    }
  };
  ws.onerror = (e) => {
    console.log("[WS] Connection error:", e);
    ...
  };
};
```

---

## 7. Paylaşım Bağlantısı Görünmüyor — `updateGenerateSection()` Tarafından Gizleniyor

### Sorun
`/reports/merge` sayfasında "Paylaşım Bağlantısı Oluştur" butonuna tıklandığında bağlantı başarılı şekilde oluşturuluyor ama UI'da görünmüyordu.

### Nedeni
`report-merge.js`'de `generateShare()` fonksiyonunun `finally` bloğundan `updateGenerateSection()` çağrılıyordu. Bu fonksiyon `$("share-result").style.display = "none"` yaparak, `try` bloğunda `display = "block"` ile gösterilen paylaşım bağlantısını hemen gizliyordu.

### Çözüm
`finally` bloğundan `updateGenerateSection()` çağrısı kaldırıldı. Buton state'i (`disabled`, `innerHTML`) zaten `finally`'de ayrı ayrı ayarlanıyor.

---

## 8. `/reports/merge` Sayfasına Erişim Hatası (302 Redirect)

### Sorun
Dashboard'da login olduktan sonra `/reports/merge` sayfasına erişim 302 redirect ile login sayfasına yönlendiriliyordu. API çağrıları (`/api/v1/runs`, `/api/dashboard/metrics`) başarılı oluyordu ama page route'ları başarısız oluyordu.

### Nedeni
Dashboard ve Admin JS'lerinde `document.cookie` ile cookie set edilirken `max-age` belirtilmiyordu:

```javascript
// HATALI — max-age yok, session-only cookie
document.cookie = `access_token=${data.token}; path=/; SameSite=Lax`;
```

Sunucu tarafında `set_cookie()` ile `max_age=86400` (24 saat) ile set edilen cookie, JS tarafında `max-age` olmadan tekrar set edildiğinde **session-only cookie** oluyor. Tarayıcı oturumu kapanınca cookie siliniyor. Sonraki sayfa ziyaretinde API çağrıları `Authorization: Bearer` header'ı ile çalışıyordu (localStorage'dan token alıyor) ama page route'ları cookie gerektirdiği için 302 redirect veriyordu.

### Çözüm
JS cookie set etme koduna `max-age` eklendi:

```javascript
// DOĞRU — 24 saat geçerli cookie
document.cookie = `access_token=${data.token}; path=/; SameSite=Lax; max-age=${24 * 3600}`;
```
```

---

## Sonuç

| Test | Durum |
|------|-------|
| Login + Refresh | Token korunuyor, tekrar sormuyor |
| Manifest Yükleme | "broken" status'lu dosyalar hatasız parse ediliyor |
| WebSocket (Admin) | `/ws/test-status/{runId}` bağlanıyor, mesajlar UI'ya yansıyor |
| WebSocket (Dashboard) | `/ws/test-status/live` bağlanıyor |
| Test Başlatma | Maven subprocess çalışıyor, sonuç DB'ye yazılıyor |
| Test Tamamlanma | Job + Worker "completed" olarak işaretleniyor |
| Aktif Testler | Sadece gerçekten çalışan testler görünüyor |
