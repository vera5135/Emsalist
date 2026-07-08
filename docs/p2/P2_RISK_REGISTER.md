# P2 Risk Register

## 1. Ölçek

Olasılık ve etki: Low, Medium, High, Critical.

Durum:

- open
- mitigated
- accepted
- monitoring
- closed

## 2. Risk tablosu

| ID | Risk | Olasılık | Etki | Azaltım | Owner/Aşama | Durum |
|---|---|---:|---:|---|---|---|
| R-001 | Yapay zekânın uydurma karar veya mevzuat üretmesi | High | Critical | Source ID zorunluluğu, deterministic citation renderer, validation gate | P2.6–P2.9 | open |
| R-002 | Tenant veya case verisi karışması | Medium | Critical | Object authorization, tenant-scoped repositories, isolation tests | P2.2–P2.4 | open |
| R-003 | Belge prompt injection | High | High | Belgeyi data olarak sınırla, tool allowlist, adversarial tests | P2.5–P2.9 | open |
| R-004 | Kritik tarihin yanlış çıkarılması | Medium | Critical | Locator, confidence, user confirmation, contradiction engine | P2.4–P2.5 | open |
| R-005 | Güncel olmayan mevzuatın kullanılması | Medium | Critical | Source versioning, temporal validity, source tracking | P2.6 | open |
| R-006 | Arama sonuçlarının alakasız veya tek taraflı olması | High | High | Benchmark, opposing decisions, feedback, reranking | P2.7 | open |
| R-007 | UYAP credential sızıntısı | Low | Critical | Secret store, no logging, rotation, security tests | P2.10 | open |
| R-008 | UYAP servis değişikliği/erişilemezliği | High | Medium | Adapter, feature flag, graceful degradation, manual import | P2.10 | open |
| R-009 | Belge parser zararlı içeriği işlemesi | Medium | Critical | Sandbox, AV, MIME, limits, quarantine | P2.5 | open |
| R-010 | Mobil offline cache hassas veri sızıntısı | Medium | High | Encrypted cache, no document bytes, logout wipe | P2.1–P2.3 | open |
| R-011 | Token replay veya cihaz kaybı | Medium | High | Refresh rotation, device sessions, remote revoke | P2.2 | open |
| R-012 | Dilekçe paragrafının kaynağını kaybetmesi | Medium | High | Paragraph metadata, source fingerprint, revalidation | P2.9 | open |
| R-013 | Kullanıcı düzenlemesinin AI tarafından üzerine yazılması | Medium | High | Revision model, merge conflict, user edit protection | P2.9 | open |
| R-014 | Büyük belge ve OCR maliyeti/performansı | High | Medium | Limits, async jobs, page selection, quotas | P2.5 | open |
| R-015 | Model sağlayıcı outage veya fiyat artışı | Medium | High | Provider abstraction, fallback, usage budget | P2.4–P2.9 | open |
| R-016 | Kaynak lisansı veya kullanım hakkı problemi | Medium | High | Provenance, license registry, official-first | P2.6 | open |
| R-017 | Veri yerleşimi/aktarım modelinin uygun olmaması | Medium | Critical | Legal review, region config, DPA/subprocessor list | P2.0–Beta | open |
| R-018 | Yanlış süre bildirimi | Medium | Critical | Assumption display, confirmation, source-linked deadline | P2.4/P2.10 | open |
| R-019 | Kullanıcının AI çıktısını kontrol etmeden kullanması | High | High | Review gates, warnings, approval role, provenance UI | P2.9 | open |
| R-020 | UI'ın küçük ekranda aşırı karmaşık olması | Medium | Medium | Chat-first, bottom sheets, golden/usability tests | P2.1 | open |
| R-021 | PR/aşama kapsamının büyümesi | High | Medium | Stage gates, separate PRs, backlog dependency | All | monitoring |
| R-022 | Migration'ın production verisini kilitlemesi | Low | Critical | Migration review, lock testing, staged backfill | All schema stages | open |
| R-023 | Backup/restore regresyonu | Low | Critical | Existing CI gate, real pg_dump/restore tests | All | monitoring |
| R-024 | Notification içinde hassas veri sızıntısı | Medium | High | Safe payload, deep link only, tests | P2.10–P2.11 | open |
| R-025 | Analytics/loglarda hukuk dosyası içeriği | Medium | Critical | Redaction, schema allowlist, log leakage tests | All | open |
| R-026 | Duplicate kaynakların ranking'i bozması | High | Medium | Canonical key, dedupe, benchmark metric | P2.6–P2.7 | open |
| R-027 | İnsan kaynak inceleme kuyruğunun birikmesi | Medium | Medium | Priority queue, official auto-verify, SLA | P2.6 | open |
| R-028 | Beta kullanıcılarının onboarding'i tamamlayamaması | Medium | High | Guided first case, pilot template, telemetry | P2.11 | open |
| R-029 | App Store inceleme veya privacy metadata gecikmesi | Medium | Medium | Early checklist, privacy manifest, staged TestFlight | P2.11 | open |
| R-030 | Ücretlendirme maliyetleri karşılamaması | Medium | High | Free beta, usage measurement, cost model | Post-beta | accepted |

## 3. Kritik go/no-go riskleri

Aşağıdakiler açıkken beta yayınlanmaz:

- R-001 kaynak uydurma blocker
- R-002 tenant/case sızıntısı
- R-007 credential sızıntısı
- R-009 zararlı belge işleme açığı
- R-017 veri işleme/yerleşim hukuki incelemesi tamamlanmaması
- R-018 doğrulanmamış kritik sürelerin kesin bildirilmesi
- R-025 log/analytics içerik sızıntısı

## 4. Risk review sıklığı

- Her P2 PR'ında etkilenen riskler
- Her milestone sonunda tam review
- Beta döneminde haftalık
- Security incident sonrası anlık

## 5. Risk kabul kuralı

Critical risk ürün sahibi ve güvenlik/hukuk değerlendirmesi olmadan accepted olamaz. Risk kabulü süreli, gerekçeli ve yeniden değerlendirme tarihli olur.

## 6. Kanıtlar

Her mitigation şu kanıtlardan en az birine bağlanır:

- test
- CI report
- threat model
- benchmark
- legal review
- runbook
- monitoring dashboard
- beta report
