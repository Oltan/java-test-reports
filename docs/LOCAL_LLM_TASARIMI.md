# Local / Custom LLM Entegrasyon Tasarımı

**Amaç:** Test koşumu doğru ve güvenilir biçimde çalıştıktan sonra aynı hata bağlamını
LLM'e verip iki işi kontrollü şekilde otomatikleştirmek:

1. **Repair:** Düşen Cucumber/Selenium testini analiz edip güvenli test-kodu yaması önermek.
2. **Triage/Jira:** Gerçek ürün hatası mı, test/infra hatası mı, duplicate mı kararına yardımcı olmak.

Bu doküman yavaş ama istek limiti yüksek local/custom LLM endpoint'i için önerilen tasarımı
özetler.

## 1. Mevcut durum

Kodda L2 repair altyapısı zaten vardır:

- `POST /api/repair/{run_id}/propose`: failed/broken senaryo bağlamını toplar,
  OpenAI-compatible chat-completions endpoint'ine yollar ve JSON yama önerisi bekler.
- `POST /api/repair/{run_id}/apply`: öneriyi `test-core/src/test/**` altında uygular ve
  istenirse aynı tag'lerle yeniden koşar.
- Konfigürasyon `.env` üzerinden yapılır:
  - `OPENAI_BASE_URL`
  - `OPENAI_API_KEY`
  - `OPENAI_MODEL`
  - `OPENAI_TIMEOUT`

Eğer custom endpoint **OpenAI-compatible** ise ilk entegrasyon için ekstra kod gerekmez;
sadece `.env` değerleri değiştirilir.

## 2. Önerilen LLM sağlayıcı katmanı

Local LLM yavaş çalışacağı için tek bir request/response çağrısı yeterli olsa bile bunu
provider katmanı gibi düşünmek doğru olur:

```text
/api/repair/propose
  -> context collector
  -> prompt builder
  -> LLM provider adapter
       - openai-compatible adapter
       - custom-json adapter (gerekiyorsa)
       - mock adapter (test)
  -> response parser / validator
  -> human approval / apply
```

### OpenAI-compatible ise

Beklenen endpoint biçimi:

```http
POST {OPENAI_BASE_URL}/chat/completions
Authorization: Bearer {OPENAI_API_KEY}
Content-Type: application/json

{
  "model": "...",
  "messages": [...],
  "temperature": 0
}
```

Bu biçime uyuyorsa mevcut `services/repair.py::OpenAIClient` kullanılabilir.

### OpenAI-compatible değilse

Yeni adapter eklenmeli:

```text
LLM_PROVIDER=openai_compatible | custom_http
CUSTOM_LLM_URL=http://localhost:1234/generate
CUSTOM_LLM_API_KEY=...
CUSTOM_LLM_TIMEOUT=900
```

Adapter'ın tek görevi `messages -> raw_text` dönüşümü yapmak olmalı. Repair parser ve güvenlik
kuralları provider'dan bağımsız kalmalıdır.

## 3. Yavaş local LLM için çalışma modeli

Yavaş model için HTTP request'i senkron bekletmek yerine job mantığı daha sağlıklı olur.

### Faz 1 — Basit kullanım

İlk aşamada mevcut `/api/repair/{run_id}/propose` yeterlidir. Sadece timeout artırılır:

```env
OPENAI_BASE_URL=http://localhost:8080/v1
OPENAI_API_KEY=local-secret
OPENAI_MODEL=local-repair-model
OPENAI_TIMEOUT=900
```

### Faz 2 — Kuyruklu LLM işleri

Model dakikalarca sürebiliyorsa repair çağrısı ayrı job olarak tutulmalıdır:

```text
POST /api/repair/{run_id}/jobs      -> job_id döner
GET  /api/repair/jobs/{job_id}      -> queued/running/done/failed
GET  /api/repair/jobs/{job_id}/log  -> LLM ara logları / denemeler
POST /api/repair/jobs/{job_id}/apply
```

Böylece browser kapanırsa işlem kaybolmaz, başka bilgisayardan job durumu görülebilir.

## 4. Çok çağrı kullanma stratejisi

İstek hakkı bol olduğu için tek dev prompt yerine aşamalı ve doğrulamalı akış daha güvenli olur:

1. **Classify:** Failure tipi belirle.
   - `PRODUCT_BUG`
   - `TEST_BUG`
   - `INFRA_BROKEN`
   - `FLAKY`
   - `NEEDS_HUMAN`
2. **Context ask:** Model eksik dosya/bağlam var mı söylesin.
3. **Patch propose:** Sadece gerekiyorsa yama önerisi üret.
4. **Self-review:** Aynı modelden veya ikinci küçük prompt'tan öneriyi denetlet.
5. **Validate:** Kod tarafında path, JSON schema, allowed-root, assertion-zayıflatma kontrolleri.
6. **Apply + rerun:** İnsan onayıyla uygula ve aynı tag'lerle yeniden koş.
7. **Triage/Jira:** Rerun sonucu hâlâ assertion failure ise Jira akışına geç.

Bu yaklaşım yavaş modeli daha fazla çağırır ama yanlış otomatik patch riskini azaltır.

## 5. Güvenlik ve sınırlar

LLM'e asla doğrudan repo yazma yetkisi verilmemelidir. Sistem şu guardrail'leri korumalıdır:

- Yazılabilir alan yalnızca `test-core/src/test/**`.
- `pom.xml`, dashboard/server, prod kodu, CI config dosyaları LLM tarafından değiştirilemez.
- Model output'u JSON schema ile parse edilir; serbest metin patch uygulanmaz.
- Her öneri önce diff olarak kullanıcıya gösterilir.
- Apply sonrası otomatik rerun yapılır; rerun başarısızsa değişiklik “başarılı repair” sayılmaz.
- Credential, token, `.env` içeriği prompt'a konmaz.

## 6. Hata açma akışında LLM kullanımı

Jira açmadan önce LLM sadece karar desteği vermelidir; nihai duplicate/bug açma kuralları backend'de
kalmalıdır.

Önerilen akış:

```text
run failed
  -> auto-match existing Jira
  -> if unmatched:
      -> LLM classify failure
      -> if TEST_BUG/INFRA_BROKEN: repair/human handoff
      -> if PRODUCT_BUG: Jira draft summary/description öner
      -> backend duplicate guard
      -> Jira create/link
```

LLM'in Jira için üreteceği alanlar:

- kısa summary
- failure evidence
- reproduction steps
- observed vs expected
- DOORS number / scenario metadata
- confidence + reasoning

Ama Jira key oluşturma, duplicate engelleme ve dry-run kuralları backend'de kalmalıdır.

## 7. Ek yapılması gerekenler

Minimum entegrasyon için:

1. `.env` içine custom endpoint bilgilerini gir.
2. `OPENAI_TIMEOUT` değerini local model süresine göre artır.
3. `/api/repair/{run_id}/propose` ile bir failed run üzerinde dene.
4. Model OpenAI-compatible değilse adapter ekle.

Sağlam production akışı için:

1. Repair job tablosu ve status endpointleri ekle.
2. LLM request/response audit log tut.
3. JSON schema'yı sıkılaştır.
4. Model self-review adımı ekle.
5. Apply öncesi UI diff/onay ekranı ekle.
6. Rerun sonucunu repair kararına bağla.
7. Jira draft endpoint'i ekle; otomatik create yine mevcut duplicate guard'dan geçsin.

## 8. Karar

Yeni repo açmak gerekmez. Doğru yön:

- Test orchestration ve dashboard: mevcut FastAPI sistemi.
- Custom/local LLM: provider/adapter olarak bağlanır.
- OpenCode benzeri araçlar: ana runner yerine repair önerisi üreten yardımcı ajan olarak kullanılabilir.
