# P2 Observability

## 1. Amaç

Gözlemlenebilirlik; kullanıcı içeriğini ifşa etmeden sistem sağlığını, gecikmeyi, hata oranını, belge/arama/AI işlerini ve UYAP senkronizasyonunu izlemeyi sağlar.

## 2. Temel ilkeler

- İçerik değil olay ve sonuç metadata'sı
- Request/job correlation
- Tenant ve kullanıcı kimlikleri hash/opaque
- Structured logs
- Metrics, traces ve audit ayrımı
- Production debug log kapalı
- Hassas veri redaction testi

## 3. Correlation kimlikleri

- request_id
- trace_id
- workspace_ref
- case_id opaque
- job_id
- model_run_id
- sync_run_id
- document_analysis_run_id

Mobil istemci request_id üretir veya server değerini saklar.

## 4. Log olayları

Örnekler:

- auth.login.success/failure
- case.created
- message.accepted/completed/failed
- document.uploaded/quarantined/analyzed
- search.completed
- source.verified/outdated
- draft.generated/validated/exported
- uyap.sync.completed/failed
- notification.delivered/failed

## 5. Loglanmayan içerik

- message text
- document text
- draft text
- source full text
- password/token/cookie
- signed URL
- identity/contact data

## 6. Metrics

### API

- request count
- error rate
- p50/p95/p99 latency
- auth failure
- rate limit

### Jobs

- queue depth
- wait duration
- run duration
- retry/dead-letter

### Documents

- upload success
- quarantine rate
- extraction success
- OCR fallback
- analysis duration

### Search

- query latency
- zero result rate
- verified source ratio
- duplicate rate
- feedback rate

### AI

- provider/model
- request success
- latency
- token count
- fallback count
- grounding validation failure

### UYAP

- connection health
- sync latency
- movement count
- auth required
- duplicate suppression

### Mobile

- crash-free sessions
- cold start
- API failure
- offline queue size
- screen performance

## 7. Tracing

Trace span örnekleri:

- HTTP request
- DB query group
- document scan/extract/analyze
- search lexical/semantic/rerank
- model call
- citation validation
- export render
- UYAP sync

Trace attribute'leri içerik taşımaz.

## 8. SLO önerileri

- API availability: %99.9 hedef
- auth availability: %99.95 hedef
- search p95: < 3 s
- message acceptance p95: < 1 s
- critical notification dispatch: tanımlı dakika hedefi
- document analysis success: fixture ve production oranı izlenir

Beta sonrası gerçek kullanım verisiyle SLO kesinleştirilir.

## 9. Alerting

Kritik:

- auth outage
- tenant isolation/security signal
- database unavailable
- backup failure
- source ingestion poisoning
- large error spike
- secret leakage detection

Yüksek:

- search zero-result spike
- document pipeline backlog
- model provider outage
- UYAP auth failure spike

## 10. Dashboard'lar

- Platform health
- Mobile health
- Document pipeline
- Search/source quality
- AI grounding
- UYAP sync
- Security events
- Retention/purge

## 11. Error codes

Kullanıcıya güvenli error code, operasyona ayrıntılı internal cause bağlanır. Aynı request_id ile destek incelemesi yapılır.

## 12. Analytics

Ürün analytics yalnız minimum olayları toplar:

- screen viewed
- flow started/completed
- feature action
- error category

Hukuk dosyası içeriği, arama metni ve kaynak paragrafı analytics'e gönderilmez.

## 13. Retention

- operational logs kısa süreli
- security/audit daha uzun süreli
- traces örneklemeli
- raw model içerik logu kapalı
- retention süresi policy/config ile yönetilir

## 14. Runbook bağlantıları

Her kritik alert:

- owner
- severity
- dashboard
- investigation steps
- mitigation
- rollback
- escalation

bilgisine bağlanır.

## 15. Kapanış kriterleri

- Hassas içerik log testleri geçer.
- Request/job correlation uçtan uca çalışır.
- Kritik servisler metric ve alert taşır.
- Backup, migration ve purge görünürdür.
- AI grounding failure ayrıca ölçülür.
- Mobile crash/performance raporu beta öncesi hazırdır.
