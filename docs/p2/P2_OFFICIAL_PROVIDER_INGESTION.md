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
| Yargıtay | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | `requires_browser=True`; canlı browser discovery P2.6D'ye ertelendi ve P2.6C'de `browser_discovery_unavailable` ile fail-closed kalır. |
| Danıştay | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | `requires_browser=True`; canlı browser discovery P2.6D'ye ertelendi. Board/daire bilgisi numbered chamber'a indirgenmez. |
| AYM | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | `requires_browser=True`; Norm Denetimi ve Bireysel Başvuru browser discovery P2.6D'ye ertelendi. Eksik canonical karar numarası uydurulmaz. |
| Uyuşmazlık Mah. | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Kabul edilen mevcut capability `requires_browser=True`; P2.6C non-browser live smoke için `not_eligible`/`not_attempted`. Güncel discovery-surface doğrulaması P2.6D'ye ertelendi. |
| Mevzuat | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Mevzuat Bilgi Sistemi. Madde/Ek Madde/Geçici Madde/Mükerrer Madde alt türü ve citable locator provenance korunur. Navigasyon/kurabiye kromu kanonik içeriğe karışmaz. |
| Resmî Gazete | fixture-tested | fixture-tested | fixture-tested | fixture-tested | not_supported | Gazete sayısı vs yayımlanmış enstrüman ayırımı. Enstrüman segmentasyonu belirsiz ise uydurulmaz; `manual_review_required`. |

Resmî Gazete kanonik kimliği yalnız exact fetch içeriğinden türetilir. Kontrollü
`h1`/`h2` başlığı belge tipini; exact gövdedeki tipe özgü, satır-başına bağlı
etiketler sayı/numarayı belirler. Discovery adayındaki `source_type`, `kind`,
`instrument_type` ve `external_id` yalnız untrusted routing/observability
ipuçlarıdır; kanonik tip veya numara fallback'i değildir. Belirsiz başlık,
eksik tipe özgü numara ya da gövde içinde sıradan bir mevzuat atfı
`manual_review_required` ile fail-closed kalır.

## Ingestion run modeli

- `source_ingestion_runs` — sağlayıcı, tür, durum, sayaçlar, safe error code.
- `source_ingestion_items` — aday başına izlenebilirlik; sadece hash/kod depolar (ham kaynak metni veya sorgu bilgisi İÇERMEZ).

Run türleri: `discover_only`, `fetch_and_ingest`, `exact_source`, `bounded_window`.
Run statüleri: `queued`, `running`, `completed`, `completed_with_errors`, `failed`, `cancelled`.

API endpoint'leri çalışmayı `queued` oluşturur (202). Gerçek yürütme CLI / worker
seam üzerinden yapılır. Otomatik/worker canlı HTTP taşıyıcısı fail-closed kalır
ve yalnızca `OFFICIAL_PROVIDER_LIVE_SMOKE=1` ile yapılandırılır. Operatör
CLI'sinde `--enable-live` açık opt-in sınırıdır ve SSRF-korumalı gerçek
taşıyıcıyı kurar.

Queued API run kontratı ham `query` kabul etmez (`extra="forbid"`); kalıcı
`cursor_json` parametreleri yalnız `from_date`, `to_date`, `max_items` ve
`external_id` alanlarıdır. Forged/legacy bir queued run içinde `query` anahtarı
bulunursa yürütme provider discovery veya transport çağırmadan
`persisted_query_not_supported` ile fail-closed olur. Ham sorgu run/item
depolamasına, safe yanıtlara, log veya metrik etiketlerine yazılmaz.

## CLI

```bash
python -m app.official_source_ingestion --provider yargitay \
  --mode bounded_window --from-date 2026-07-01 --max-items 100
```

Servis katmanıyla aynı kodu kullanır; ikinci bir CLI-only ingestion motoru yoktur.
Doğrudan CLI `--query` girdisi yalnız o proses içindeki `provider.discover`
çağrısına iletilir; `SourceIngestionRun.cursor_json` veya item satırlarında
saklanmaz ve queued worker tarafından replay edilmez.
`--run-id` kullanıldığında kuyrukta saklanan `cursor_json.max_items` yetkilidir;
CLI `--max-items` değeri kuyruktaki parametreyi sessizce ezmez. `--enable-live`
verilmezse taşıyıcı `None` kalır ve gerçek ağ erişimi yapılmaz. `--enable-live`
verilirse `create_real_transport()` kullanılır ve oluşturulan taşıyıcı kapanışta
`close()` edilir.

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

Provider liste/detay yanıtı yalnız güvenli operasyonel alanları döndürür:
`status`, `last_run_at`, `last_success_at`, `last_run_status`,
`last_safe_error_code`. Ham URL, cursor, sorgu, external id, HTML, header,
stack trace veya exception metni dönmez.

Operasyonel durum çözümleme sırası saf ve I/O'suzdur:

1. disabled provider → `disabled`
2. auth gerektiriyorsa → `unsupported_requires_auth`
3. browser gerektiriyor ve browser discovery uygulanmadıysa → `browser_discovery_unavailable`
4. otomatik/live transport yapılandırılmadıysa → `transport_unavailable`
5. son terminal safe error `provider_structure_changed` ise → `provider_changed`
6. son terminal safe error `challenge_detected` veya `manual_review_required` ise → `manual_review_required`
7. başarılı veya kısmi başarılı operasyonel run yoksa → `fixture_tested_only`
8. son terminal run `failed` ise → `degraded`
9. son terminal run `completed_with_errors` ise → `degraded`
10. son terminal run `completed` ise → `available`

Yargıtay, Danıştay, AYM ve Uyuşmazlık için browser discovery/current-surface
doğrulaması P2.6D'ye ertelenmiştir.
Capability bayrağı değiştirilmez ve browser prerequisite karşılanmadan durum
`transport_unavailable`, `fixture_tested_only` veya `available` seviyesine
ilerlemez.

Queued/running run'lar son terminal operasyonel sağlığı silmez. `last_success_at`,
yalnızca gerçek başarılı iş üreten `completed` veya `completed_with_errors`
run'lardan gelir; boş başarı sahte son başarı üretmez.

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
- `emsalist_official_source_provider_retry_total` (provider_code, operation, safe_error_code)

Hiçbir metrik etiketi ham URL, karar başlığı, E/K numarası veya sorgu içeriği
taşımaz.

## Sağlayıcı politika (rate-limit, politeness)

Tüm sağlayıcılar düşük eşzamanlılıkla varsayılan olarak yapılandırılmıştır
(max_concurrency=1, min_interval≥2s, max_retries≤2). `max_retries` ek deneme
sayısıdır; varsayılan 2 değeri en fazla 3 toplam deneme anlamına gelir.
Backoff deterministiktir: `backoff_base_seconds * 2 ** retry_index`,
`backoff_max_seconds` ile sınırlanır ve `min_interval_seconds` altına düşmez.

Tek bir paylaşılan retry executor yalnızca provider ağ operasyonlarına uygulanır:
discovery fetch'i ve detail fetch'i. Parse, canonical ingestion, DB yazımı ve
`ingest_official_fetch` retry edilmez. 429 için güvenli parse edilmiş
`Retry-After` değeri operasyonel sınırlar içindeyse kullanılır; sınırı aşarsa
erken retry yapılmaz ve `rate_limited` ile fail-closed edilir. 403
`access_denied` olarak tek denemede durur. CAPTCHA/challenge, yapı değişimi,
transport yokluğu, access denied ve rate limit provider-wide stop kodlarıdır;
kalan adaylar hammer edilmez.

## Resmî site değişikliği tespiti

Her sağlayıcı parser'ı kendi yapısal değişmezlerini tanımlar. Beklenen DOM
yapısı değişirse `provider_structure_changed` safe error code döner.
`body.text` alıp tüm siteyi yutma fallback'i YOKTUR.

## İdempotency

- Aynı sağlayıcı kodu + `external_id` / `detail_url_hash` → keşif deduplikasyonu
- Aynı kanonik key + aynı `content_hash` → P2.6 `duplicate_verified` (versiyon çoğaltma YOK)
- Değişen resmî içerik → yeni `SourceVersion`, eski versiyon korunur

## Madde alt türü ve citable locator provenance

Madde locator'ının tek kaynağı normalize edilmiş kanonik hukuk metnindeki satır
başına bağlı, deterministik başlıktır. Provider discovery metadata'sı bu karara
girdi değildir. Kapalı vocabulary:

- `regular_article` → `Madde N`
- `additional_article` → `Ek Madde N`
- `provisional_article` → `Geçici Madde N`
- `repeated_article` → `Mükerrer Madde N`

Ekli numaralar boşlukları kaldırılmış ve harf eki kararlı büyük harfe çevrilmiş
biçimde korunur (`1 / a` → `1/A`); baştaki sıfırlar integer dönüşümüyle
silinmez. Gösterim etiketi Türkçedir. Locator key, alt tür ile numarayı birlikte
taşır (`provisional_article:1`), dolayısıyla `Madde 1` ve `Geçici Madde 1`
çakışmaz.

Article-aware yeni `SourceVersion` satırlarında
`metadata_json.paragraph_locator_version = "p2.6c-article-locator-1"` bulunur.
Article-located `SourceParagraph.locator_json` yalnızca kontrollü
`locator_type`, `article_kind`, `article_number`, `article_label`,
`article_locator_key`, `article_locator_method` ve `article_locator_version`
alanlarını taşır. `article_locator_method` değeri `deterministic_heading`'dir.
Bu metadata extraction trust kanıtı değildir ve `verified_official` statüsü
üretemez.

Article-aware türler `legislation`, `regulation`, `communique`, `circular` ve
`presidential_decree` ile sınırlıdır. `official_gazette_issue` bir yayın
konteyneridir ve kendi başına madde namespace'i değildir; sayı metninde
`Madde 1` geçse bile issue-level locator üretilmez. Deterministik biçimde ayrı
bir kanonik kayıt olarak segmentlenmiş Resmî Gazete enstrümanı (örneğin
`regulation`) kendi kanonik metninden locator alabilir. Belirsiz enstrüman
segmentasyonu için mevcut `manual_review_required` davranışı korunur.

Geçmiş satırlar backfill edilmez. `article_number` bulunup kontrollü alt tür
provenance'ı bulunmayan paragraph, `regular_article` varsayılmaz; unknown/legacy
olarak ele alınır. Gelecekteki P2.7 tüketicileri de eksik alt türü unknown/legacy
saymalıdır. Aynı hash ile `duplicate_verified` sonucu mevcut immutable version
ve paragraph setini sırf yeni locator metadata'sı eklemek için yeniden yazmaz.

## Kontrollü non-browser live smoke

`python -m app.official_source_ingestion_smoke --confirm-live-smoke` yalnızca
operatör tarafından çalıştırılan, dry/observation amaçlı bounded bir harness'tir.
Çalışması için aynı anda:

- `OFFICIAL_PROVIDER_LIVE_SMOKE=true`
- `--confirm-live-smoke`

gereklidir. Tek guard bile eksikse transport factory çağrılmaz; DNS/TCP oluşmaz.
`--enable-live` tek başına acceptance smoke başlatmaz.

Uygunluk, ayrı bir sağlayıcı listesinden değil kapalı registry'deki capability
kontratından türetilir: discovery+fetch desteklenmeli ve `requires_browser=False`
olmalıdır. Mevcut durumda bu koşulu Mevzuat ve Resmî Gazete karşılar. Uyuşmazlık
dahil browser-required sağlayıcılar otomatik olarak dışlanır.

Her enabled/eligible sağlayıcı için en fazla bir discovery sonucu ve en fazla
bir detail fetch yapılır. Pagination izlenmez ve ikinci bir retry döngüsü yoktur;
mevcut provider retry executor/policy kullanılır. Tüm gerçek ağ erişimi
`create_real_transport()` → provider → destination-pinned `source_fetcher`
yolundadır. Harness canonical ingestion veya veritabanı yazımı yapmaz.

Safe rapor yalnız provider kodu, eligibility/attempt durumu, kapalı outcome,
candidate sayısı, detail-attempt durumu, safe error, güvenli HTTP status,
content type/boyut ve kabul edilen final URL'den çıkarılan hostname'i içerir.
Ham query, external id, başlık, E/K numarası, URL path/query, body, header,
cookie, stack trace ve raw exception içermez.

Browser discovery P2.6D'ye ertelenmiştir. Browser bytes resmî kanıt değildir;
P2.6C non-browser smoke browser detail indirmez. CAPTCHA/access-control bypass,
stealth/evasion ve proxy rotation yasaktır. Fixture smoke testleri controlled
live smoke kanıtı değildir.

Tek kontrollü canlı oturum `2026-07-13T20:16:52.381881+00:00` tarihinde,
`40611aa26ee086407912675cde58d3e89b0c626c` exact SHA üzerinde çalıştırıldı.
Mevzuat ve Resmî Gazete için discovery gerçek pinned transport yolu üzerinden
denendi ve her ikisi de güvenli `fetch_failed` sonucu verdi; aday/detail fetch
ve canonical ingestion oluşmadı. Bu sonuçlar uzaktaki provider'ı başarıya
zorlamak için tekrar çalıştırılmadı. Güvenli evidence:
`docs/p2/P2_6C_CONTROLLED_LIVE_SMOKE.md`.

## Kapsam dışı

- Canlı zamanlanmış periodic provider ingestion (cron/scheduler integration yok — schedule-ready tasarım)
- Browser discovery P2.6D'ye ertelendi; browser gerektiren gerçek yüzeyler P2.6C canlı kabulü değildir.
- Kontrollü live smoke evidence kaydedildi; final PR documentation/acceptance tamamlanmadan P2.6C tamamlanmış sayılmaz.
- Mobil sağlayıcı yönetim UI (editor/admin backend altyapısı)
- Authentication/CAPTCHA gerektiren sağlayıcı yüzeylerinin bypass edilmesi
- OCR, UDF parser, dosya tabanlı ingestion (P2.5 kapsamı)
- Embedding/semantik index/arama (P2.7)
- Hukuki mesele grafiği (P2.8)
- Kaynaklı dilekçe (P2.9)
