# P2 Test Strategy

## 1. Amaç

P2 test stratejisi; backend, mobil, belge hattı, hukuk kaynağı, arama, yapay zekâ, UYAP, güvenlik ve uçtan uca akışları ölçülebilir kalite kapılarıyla doğrular.

## 2. Test piramidi

- Unit tests
- Component/widget tests
- Integration tests
- Contract tests
- Security tests
- Benchmark/evaluation tests
- End-to-end tests
- Beta telemetry validation

Unit test sayısı yüksek, E2E sayısı seçici ve kritik akış odaklı olur.

## 3. Backend testleri

### Unit

- domain rules
- risk calculation
- missing information completion
- contradiction detection
- deadline calculation
- citation rendering
- source canonicalization
- idempotency

### Integration

- PostgreSQL
- Alembic migration
- async jobs
- object storage mock/real integration
- source ingestion
- search index
- export generation

### Authorization

- workspace isolation
- case membership
- role matrix
- object-level access
- break-glass audit

## 4. Mobil testleri

### Unit

- state reducers/providers
- repositories
- DTO mapping
- retry/idempotency behavior
- theme preference

### Widget

- chat shell
- drawer
- composer
- message cards
- bottom sheets
- error/loading/empty states
- accessibility labels

### Golden

Cihaz boyutları:

- küçük iPhone
- standart iPhone
- büyük iPhone

Temalar:

- light
- dark
- system-derived

Dynamic Type seviyeleri de test edilir.

### Integration

- login
- workspace select
- case create
- message send/retry
- document upload
- fact confirm/reject
- search
- draft export
- notification deep link

## 5. API contract testleri

- OpenAPI deterministic generation
- Flutter client generation compatibility
- required/nullable fields
- error schema
- pagination
- auth scopes
- breaking diff

## 6. Belge testleri

Fixture seti:

- text PDF
- scanned PDF
- password-protected PDF
- malformed PDF
- DOCX tables/comments
- UDF sample
- rotated photo
- low-resolution photo
- duplicate document
- malicious/active content sample
- oversized document

Kontroller:

- MIME
- hash
- quarantine
- extraction accuracy
- locator accuracy
- reprocessing versioning
- user confirmation

## 7. Case memory testleri

- source-linked fact creation
- user correction and supersede
- conflicting values
- concrete completion rule
- risk floor with critical missing data
- revision idempotency
- cross-case isolation

## 8. Kaynak omurgası testleri

- canonical key
- duplicate merge
- official hash verification
- version/supersede
- temporal validity
- quarantine
- source usage traceability
- citation rendering

## 9. Search benchmark

Metrics:

- Recall@3/10
- Precision@5
- MRR
- nDCG
- duplicate rate
- verified source rate
- opposing decision recall

Benchmark seti hukuk uzmanı tarafından etiketlenir ve version control altında hassas veri içermeyen fixture olarak tutulur.

## 10. Yapay zekâ evaluation

Senaryolar:

- fact extraction
- single critical question selection
- contradiction handling
- legal issue identification
- source selection
- grounded paragraph generation
- refusal to invent citation
- prompt injection resistance
- cross-case leakage prevention

Sonuçlar deterministic expectation ve rubric scoring ile ölçülür.

## 11. Drafting testleri

- readiness blocked conditions
- source-linked paragraph
- unsupported claim warning
- citation verification
- date/amount consistency
- selected remedy/result alignment
- revision preservation
- DOCX/PDF artifact generation

## 12. UYAP testleri

Gerçek credential CI'da kullanılmaz.

- contract mock
- sync cursor
- duplicate movement
- expired authentication
- uncertain case match
- document import
- feature flag disabled
- secret/log leakage

Gerçek entegrasyon staging ve yetkili test hesabında ayrı kapı olarak yürütülür.

## 13. Güvenlik testleri

- SAST
- dependency audit
- container scan
- secret scan
- IDOR
- tenant leakage
- rate limit
- SSRF
- file upload attacks
- prompt injection
- source poisoning
- signed URL expiry
- token rotation/replay
- log redaction

## 14. Performans hedefleri

İlk beta hedefleri:

- API p95 basit read < 500 ms
- case list p95 < 800 ms
- first message acceptance < 1 s
- document upload progress immediate
- search p95 < 3 s
- mobile cold start hedefi ölçülür ve P2.1'de sabitlenir
- crash-free sessions ≥ %99.5 beta hedefi

Uzun AI işlemleri async job ve ilerleme durumu kullanır.

## 15. E2E pilot

Zorunlu senaryo:

1. Login
2. Personal workspace
3. Ayıplı araç case create
4. Narrative send
5. Satış sözleşmesi upload
6. Ekspertiz raporu upload
7. Fact extraction confirm
8. Tarih contradiction resolve
9. Missing notice date risk
10. Verified source search
11. Legal issue graph
12. Draft readiness
13. Grounded draft generation
14. DOCX export
15. Audit verification

## 16. CI matrisi

Her PR:

- lint/format/type
- unit tests
- affected integration tests
- OpenAPI diff
- security scans
- docs link/lint

Main/nightly:

- full PostgreSQL suite
- migration
- backup/restore
- document fixtures
- search benchmark smoke
- AI evaluation smoke
- mobile golden/integration

Release candidate:

- full E2E
- security regression
- artifact reproducibility
- staging smoke

## 17. Flaky test politikası

- Retry başarının yerine geçmez.
- Flaky test issue ve owner alır.
- Karantinaya alınan test kritik kapıyı kapsamıyorsa süreli olabilir.
- Kritik güvenlik/tenant/source tests skip edilemez.

## 18. Test verisi

- Sentetik
- Kimliksizleştirilmiş
- Gerçek müvekkil verisi CI'da yok
- Fixture provenance belgeli
- Hukuk benchmark verisi lisans/izin kontrollü

## 19. Exit kriterleri

Her aşama:

- kritik testler green
- yeni regression tests
- acceptance matrix kanıtı
- bilinen bug ve risk kaydı
- rollback doğrulaması

P2 beta:

- kritik security açığı yok
- kaynak uydurma blocker yok
- E2E pilot green
- crash/performance hedefleri kabul edilebilir
- data deletion flow green

## 20. Raporlama

CI artifact'leri:

- test results
- coverage
- OpenAPI diff
- security reports
- benchmark summary
- mobile screenshots/golden diff
- E2E evidence

Hassas veri artifact'lerde bulunmaz.
