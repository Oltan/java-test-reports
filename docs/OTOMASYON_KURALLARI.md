# OTOMASYON KURALLARI — Otonom Ajan Kural Kitabı

Bu doküman, test otomasyon sistemini **kendi kendine** işletecek bir ajanın
(Claude veya başka bir otomasyon) uyması gereken kuralları tanımlar. Mekanik
kurallar `fastapi-server/tests/test_feature_conventions.py` lint kapısıyla
otomatik zorlanır; karar kuralları bu dokümanın kendisidir.

> **Bu dokümanı değiştirmek insan onayı gerektirir.** Ajan kural kitabını
> kendisi güncelleyemez; ihtiyaç görürse öneri olarak raporlar.

---

## 1. Senaryo yazım kuralları (lint ile zorlanır)

1. **Her `Scenario` tam bir DOORS/ABS tag'i taşır** (`@DOORS-<sayı>` veya
   `@ABS-<sayı>`). Desenin tek gerçek kaynağı:
   `fastapi-server/services/identifiers.py::DOORS_PATTERN`.
2. **DOORS tag'i senaryo seviyesindedir, feature seviyesinde olamaz**
   (feature seviyesinde olursa tüm senaryolar aynı numarayı miras alır ve
   raporlama/dedup bozulur).
3. **Aynı DOORS numarası iki senaryoda kullanılamaz** (repo genelinde tekil).
   Jira dedup'u ve DOORS CSV'si bu tekilliğin üstüne kuruludur.
4. **`@id:` değerleri repo genelinde tekildir**; **her `@dep:X[,Y]` hedefi
   mevcut bir `@id:`'ye işaret eder**; bağımlılık grafiğinde **döngü yasaktır**
   (Java tarafında `DependencyResolver` koşum sırasını bu grafikten çözer).
5. `@sample-fail` yalnızca **bilerek düşen** demo/kalibrasyon senaryoları
   içindir; triage bu tag'i "beklenen failure" beyanı sayar.
6. Tarayıcı gerektirmeyen senaryolar feature seviyesinde tarayıcısız bir grup
   tag'i taşır (ör. `@UnitDemo`). Bu tag, ajanın Chrome'suz ortamda neyi
   koşabileceğini seçme anahtarıdır.

## 2. Koşum kuralları

- Koşum **her zaman sunucu API'siyle** yapılır: `POST /api/tests/start`
  (kuyruk, izolasyon, iptal, orphan-recovery güvenceleri buradadır). Elle
  `mvn` yalnız teşhis içindir.
- Ortamda Chrome yoksa yalnız tarayıcısız tag'ler koşulur. Selenium
  senaryolarının koşulamaması **BROKEN değil "koşulmadı"dır** — bug açılmaz.
- Kapı komutları (her değişiklik sonrası, sıra önemli):
  ```bash
  cd fastapi-server && python3 -m pytest tests/     # 0 fail
  mvn clean compile                                  # BUILD SUCCESS
  cd fastapi-server && timeout 5 python3 -c "from server import app; print('OK')"
  ```
- Jira varsayılanı **DRY_RUN=true** (mock). `DRY_RUN`'ı kapatmak (gerçek
  Jira'ya yazmak) **insan kararıdır** — bkz. §5.

## 3. Failure karar ağacı (L1 triage algoritması)

Koşum bittiğinde ajan her run için sırasıyla:

1. `GET /api/v1/runs/{run_id}/failures` → failure listesi.
2. Önce **auto-match**: `POST /api/triage/{run_id}/auto-match-jira`.
   Jira'da (description içinde DOORS numarası aranarak) **eski bug** aranır.
   Eşleşme varsa senaryo o bug'a linklenir; **yeni bug açılmaz**.
3. Eşleşme yoksa ve failure **FAILED** (assertion) ise:
   `POST /api/triage/{run_id}/scenarios/{scenario_uid}/jira` ile bug açılır.
   Aynı senaryo için ikinci bug sistemce engellenir (200 + mevcut anahtar döner) —
   ajan 200 gördüğünde "mevcut bug" olarak raporlar, yeni kayıt saymaz.
4. Failure **BROKEN** (infra: driver kurulamadı, timeout, element yok) ise
   **bug açılmaz**; ortam raporu üretilir. L2 açıksa onarım denenir (bkz. §4),
   değilse insana devredilir.
5. `@sample-fail` tag'li failure'lar "beklenen" olarak işaretlenir; bug
   açılmaz, rapora not düşülür.
6. Koşum kapanışı: `GET /api/csv/export?run_id={run_id}` ile DOORS CSV üret,
   run raporunu (`/reports/{run_id}`) paylaş.

## 4. Otonomi seviyeleri

| Seviye | Kapsam | Durum |
|---|---|---|
| **L1** | Koş + triage + bug + rapor/CSV. **Test koduna dokunmaz.** | **AKTİF** |
| **L2** | + BROKEN test onarımı | KAPALI (taslak) |
| **L3** | + DOORS gereksiniminden yeni senaryo yazımı | KAPALI (taslak) |

**L2 taslak kuralları** (etkinleştirilmeden uygulanamaz):
- Yalnız **BROKEN** senaryolara dokunulur; **assertion FAILED'a dokunmak
  yasaktır** (gerçek ürün hatası olabilir — bug akışına gider).
- Değişiklik yalnız `test-core/src/test/**` altında yapılabilir; üretim/sunucu
  koduna dokunulamaz.
- Her onarımdan sonra kapı komutları + aynı tag'in yeniden koşumu zorunludur;
  onarım failure'ı çözmediyse değişiklik geri alınır ve insana devredilir.

**L3 taslak kuralları:**
- Yeni senaryo §1'deki tüm yazım kurallarına uyar (lint kapısı zorlar).
- Yeni senaryo insan review'undan geçmeden `@smoke` setine giremez.

## 5. İnsan onayı gerektiren eylemler

Ajan aşağıdakileri **asla kendi başına yapmaz**; öneri olarak raporlar:

- `DRY_RUN`'ı kapatmak / gerçek Jira'ya bug yazmaya başlamak
- Senaryo veya feature dosyası **silmek**
- `main`/`master` branch'ine dokunmak (geliştirme her zaman aktif çalışma
  branch'indedir)
- Bu kural kitabını değiştirmek
- Çapa test dosyalarını değiştirmek (`tests/test_auth_boundaries.py`,
  `tests/test_integration_workflow.py`)

## 6. Raporlama sözleşmesi

Her otonom seansın sonunda ajan şunları içeren tek bir özet üretir:
koşulan tag'ler ve run_id'ler, geçen/düşen/koşulmayan sayıları,
auto-match ile linklenen eski bug'lar, yeni açılan bug'lar (anahtarlarıyla),
BROKEN/insana-devredilen konular, üretilen CSV/rapor bağlantıları.
"Sessiz başarısızlık" yasaktır: yapılamayan her adım nedeniyle raporlanır.
