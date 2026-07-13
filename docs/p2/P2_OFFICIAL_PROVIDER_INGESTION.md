# P2.6C — Çoklu Sağlayıcı Resmî Hukuk Kaynağı Ingestion

PR #16 — `feat/p2.6c-official-provider-ingestion`

## Amaç

Altı Türk resmî hukuk kaynağı sağlayıcısını (Yargıtay, Danıştay, AYM, Uyuşmazlık
Mahkemesi, Mevzuat, Resmî Gazete) tamamlanmış P2.6 Güvenilir Hukuk Kaynağı
Omurgası kanonik ingestion hattına bağlar. Sağlayıcı adaptörleri; kamuya açık
resmî arama/yayın yüzeylerinden adayları keşfeder, tam içeriği SSRF-korumalı
P2.6 taşıyıcısı üzerinden çeker ve kanonik `ingest_official_fetch` yoluna
aktarır.

Bu bir arama motoru değildir. Embedding üretmez. LLM hukuki muhakeme içermez.

## Mimari kararlar

1. Kanonik trust `ingest_official_fetch` yoluyla `source_fetcher`'ın çektiği
   tam byte'lardan türetilir. Hiçbir sağlayıcı kodu doğrudan
   SourceRecord/SourceVersion/SourceVerification yazmaz.
2. Tüm ağ erişimleri P2.6 SSRF doğrulama hattından geçer (`source_fetcher`).
   `requests.get(url)` veya `httpx.get(url)` gibi doğrudan HTTP çağrıları
   sağlayıcı kodunda kullanılmaz.
3. Sağlayıcı keşfi/parse verileri resmî kanıt değildir. HTML arama sonucu
   metadata'sı `verified_official` için yeterli değildir.
4. Provider API endpoint'leri `require_editor` sınırıyla korunur. Avukat ve
   `tenant_admin` rolleri 403 alır.

## Sağlayıcı sözleşmesi

`backend/app/services/source_providers/base.py` içinde tanımlanmıştır.
Her sağlayıcı şu kontratı uygular:

- `provider_code` / `provider_name` / `source_types` / `official_domains`
- `capabilities` (discovery, fetch, parse, incremental, bounded_window, requires_browser)
- `request_policy` (min_interval, max_concurrency, timeout, retryable_statuses, max_retries, backoff)
- `discover(query, cursor, limit, from_date, to_date, transport, resolver)` → `ProviderDiscoveryPage`
- `fetch(candidate, transport, resolver)` → SSRF-doğrulanmış `FetchResult`
- `parse(candidate, fetch_result)` → `ParsedOfficialSource`

## Kayıt (registry)

Sabit bir dict üzerinde `backend/app/services/source_providers/registry.py`.
Dinamik import yok. Bilinmeyen sağlayıcı kodları `ProviderError("unknown_provider")`
döndürür. Her sağlayıcı `OFFICIAL_PROVIDER_*_ENABLED` config flag'iyle
açılıp kapatılır; varsayılan kapalıdır.

## Güven kontratı (non-negotiable)

```
Provider keşif/parse                        → UNTRUSTED
P2.6 source_fetcher ile tam çekim           → SSRF-safe bytes
ingest_official_fetch(fetch_result)         → P2.6 verified_official
```

Hiçbir sağlayıcı kodu doğrudan trust üretemez. `record.verification_status = "verified_official"` veya `SourceVerification(...verified_official...)` sadece P2.6 `ingest_official_fetch` motorunda gerçekleşir.

## Sağlayıcı destek matrisi

| Sağlayıcı | Discovery | Fetch | Parse | Kanonik ingestion | Incremental | Known limitation |
|---|---|---|---|---|---|---|
| Yargıtay | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Gerçek Karar Arama JavaScript yüzeyi; browser gerektirir. Gerçek yüzey yapısı kontrol edilene kadar canlı keşif mümkün değildir. |
| Danıştay | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Gerçek yüzey JS yüzeyi; browser gerektirir. Board/daire bilgisi korunur, numbered chamber'a indirgenmez. |
| AYM | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Gerçek yüzey JS yüzeyi. Bireysel başvuru (Başvuru No, karar no olmadan) `manual_review_required` hata koduyla işaretlenir; data uydurulmaz. |
| Uyuşmazlık Mah. | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Halihazırda allowlist'te olan UYAP emsal yüzeyi üzerinden. Görüntü/indirme temsil farklılığında aynı içerik duplicate oluşturmaz. |
| Mevzuat | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Mevzuat Bilgi Sistemi. Madde/Ek Madde/Geçici Madde parsing. Navigasyon/kurabiye kromu kanonik içeriğe karışmaz. |
| Resmî Gazete | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Gazete sayısı vs yayımlanmış enstrüman ayırımı. Enstrüman segmentasyonu belirsiz ise uydurulmaz; `manual_review_required`. |

## Ingestion run modeli

- `source_ingestion_runs` — sağlayıcı, tür, durum, sayaçlar, safe error code.
- `source_ingestion_items` — aday başına izlenebilirlik; sadece hash/kod depolar (ham kaynak metni veya sorgu bilgisi İÇERMEZ).

Run türleri: `discover_only`, `fetch_and_ingest`, `exact_source`, `bounded_window`.
Run statüleri: `queued`, `running`, `completed`, `completed_with_errors`, `failed`, `cancelled`.

API endpoint'leri çalışmayı `queued` oluşturur (202). Gerçek yürütme CLI / worker
seam üzerinden yapılır. Doğrudan canlı HTTP taşıyıcı yapılandırması production
dağıtımına bırakılmıştır.

## CLI

```bash
python -m app.official_source_ingestion --provider yargitay \
  --mode bounded_window --from-date 2026-07-01 --max-items 100
```

Servis katmanıyla aynı kodu kullanır; ikinci bir CLI-only ingestion motoru yoktur.

## API endpoint'leri

| Method | Path | Auth | Açıklama |
|---|---|---|---|
| GET | `/api/v1/official-source-providers` | editor/admin | Tüm sağlayıcıların metadata/kabiliyet/durum listesi |
| GET | `/api/v1/official-source-providers/{code}` | editor/admin | Tek sağlayıcı detayı |
| POST | `/api/v1/official-source-providers/{code}/runs` | editor/admin | Çalışma kuyruğa al (202) |
| GET | `/api/v1/official-source-ingestion-runs` | editor/admin | Çalışma listesi |
| GET | `/api/v1/official-source-ingestion-runs/{id}` | editor/admin | Çalışma detayı |
| POST | `/api/v1/official-source-ingestion-runs/{id}/cancel` | editor/admin | Çalışma iptali |

Hiçbir endpoint keyfî URL fetch, ham provider HTML, stack trace veya secret
döndürmez.

## Gözlemlenebilirlik

Metrikler (Prometheus formatı, `GET /metrics`) — güvenli etiketlerle:

- `emsalist_official_source_provider_run_total` (provider_code, run_type, status)
- `emsalist_official_source_provider_run_duration_seconds` (provider_code, run_type)
- `emsalist_official_source_provider_discovered_total` (provider_code)
- `emsalist_official_source_provider_fetched_total` (provider_code)
- `emsalist_official_source_provider_ingested_total` (provider_code)
- `emsalist_official_source_provider_duplicate_total` (provider_code)
- `emsalist_official_source_provider_new_version_total` (provider_code)
- `emsalist_official_source_provider_conflict_total` (provider_code)
- `emsalist_official_source_provider_error_total` (provider_code, safe_error_code)

Hiçbir metrik etiketi ham URL, karar başlığı, E/K numarası veya sorgu içeriği
taşımaz.

## Sağlayıcı politika (rate-limit, politeness)

Tüm sağlayıcılar düşük eşzamanlılıkla varsayılan olarak yapılandırılmıştır
(max_concurrency=1, min_interval≥2s, max_retries≤2). 429 Retry-After'a saygı
duyulur; 403 agresif retry yapılmaz. CAPTCHA / challenge tespit edilirse
çalışma durdurulur.

## Resmî site değişikliği tespiti

Her sağlayıcı parser'ı kendi yapısal değişmezlerini tanımlar. Beklenen DOM
yapısı değişirse `provider_structure_changed` safe error code döner.
`body.text` alıp tüm siteyi yutma fallback'i YOKTUR.

## İdempotency

- Aynı sağlayıcı kodu + `external_id` / `detail_url_hash` → keşif deduplikasyonu
- Aynı kanonik key + aynı `content_hash` → P2.6 `duplicate_verified` (versiyon çoğaltma YOK)
- Değişen resmî içerik → yeni `SourceVersion`, eski versiyon korunur

## Kapsam dışı

- Canlı zamanlanmış periodic provider ingestion (cron/scheduler integration yok — schedule-ready tasarım)
- Gerçek üretim HTTP taşıyıcı bağlama (yapılandırma seami mevcut; production deployer'a bırakılmış)
- Mobil sağlayıcı yönetim UI (editor/admin backend altyapısı)
- Authentication/CAPTCHA gerektiren sağlayıcı yüzeylerinin bypass edilmesi
- OCR, UDF parser, dosya tabanlı ingestion (P2.5 kapsamı)
- Embedding/semantik index/arama (P2.7)
- Hukuki mesele grafiği (P2.8)
- Kaynaklı dilekçe (P2.9)
