# P2 Acceptance Matrix

Bu matris her P2 aşamasının ölçülebilir kapanış kriterlerini tanımlar. Bir aşama, kritik kriterlerden biri karşılanmıyorsa tamamlanmış sayılmaz.

## P2.0 — Planlama ve mimari temel

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Ürün kapsamı ve kapsam dışı maddeler yazılı | Kritik | `P2_PRODUCT_SCOPE.md` |
| Kullanıcı akışları ve ekran haritası yazılı | Kritik | `P2_USER_FLOWS.md`, `P2_INFORMATION_ARCHITECTURE.md` |
| Mobil-backend sorumluluk sınırı belirli | Kritik | `P2_API_CONTRACT.md`, `P2_DATA_MODEL.md` |
| Güvenlik/KVKK modeli yazılı | Kritik | `P2_SECURITY_PRIVACY.md` |
| Test ve benchmark stratejisi yazılı | Kritik | `P2_TEST_STRATEGY.md` |
| Açık kritik karar kalmaması | Kritik | `P2_DECISION_REGISTER.md` |
| Aşamalı backlog ve bağımlılık haritası mevcut | Yüksek | `P2_BACKLOG.md` |
| P2.0 PR yalnız dokümantasyon içeriyor | Kritik | PR diff |

## P2.1 — Mobil kabuk

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Flutter proje yapısı bağımsız build ediliyor | Kritik | CI build |
| iOS simülatöründe açılıyor | Kritik | CI/demo |
| Sistem/açık/koyu tema çalışıyor | Yüksek | widget/golden test |
| Küçük iPhone ekranında overflow yok | Kritik | golden test |
| Klavye açıldığında composer görünür | Kritik | widget test |
| Safe-area ve Dynamic Type destekleniyor | Yüksek | accessibility test |
| Ana chat, drawer, UYAP ikonu, ayarlar navigasyonu çalışıyor | Kritik | widget/integration test |
| Yükleniyor, boş ve hata durumları tanımlı | Yüksek | ekran görüntüsü/test |

## P2.2 — Kimlik ve oturum

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Giriş, token yenileme ve çıkış çalışıyor | Kritik | integration test |
| Token güvenli cihaz deposunda | Kritik | code review/security test |
| Süresi dolmuş refresh token reddediliyor | Kritik | API test |
| Oturum iptali diğer cihazı etkiliyor | Yüksek | integration test |
| Yetkisiz tenant/dosya erişimi 403/404 | Kritik | isolation test |
| Hassas auth verisi loglarda yok | Kritik | log scan |

## P2.3 — Dosya ve konuşma

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Dosya oluşturma/listeleme/güncelleme/arşivleme çalışıyor | Kritik | API + mobile integration |
| Aktif dosya değiştiğinde konuşma bağlamı doğru değişiyor | Kritik | E2E test |
| Mesaj kalıcılığı ve sıralaması doğru | Kritik | DB/API test |
| Idempotency çift mesajı önlüyor | Kritik | retry test |
| Ağ kesintisinde başarısız mesaj görünür ve tekrar denenebilir | Yüksek | mobile integration |
| Dosyalar arası mesaj sızıntısı yok | Kritik | tenant/case isolation test |

## P2.4 — Dosya hafızası

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Taraf, olay, tarih, talep, delil, eksik, çelişki ve risk modeli mevcut | Kritik | migration/model/API |
| Her bilgi kaynak türü ve source_id taşıyor | Kritik | schema test |
| Doğrulama statüsü ve sürüm geçmişi tutuluyor | Kritik | integration test |
| Çelişkili bilgi otomatik kesinleşmiyor | Kritik | regression test |
| Kritik değer eksikken kategori tamamlandı görünmüyor | Kritik | acceptance test |
| Kritik eksikler varken genel risk düşük olamıyor | Kritik | rule test |

## P2.5 — Belge hattı

Durum: ✅ Uygulandı (P2.5). Kanıtlar `backend/tests/test_document_pipeline_routes.py`
(23 test) ve mobil `document_repository_test.dart` / `documents_screen_test.dart`
(13 test). Gerçek format matrisi ve kapsam dışı için `P2_DOCUMENT_PIPELINE.md §19`.

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Desteklenen formatlar doğrulanıyor (gerçek parser bazında) | Kritik | test_document_pipeline_routes: pdf/txt/docx/udf/image |
| Boyut, MIME magic-byte, hash ve path traversal kontrolleri var | Kritik | mime_spoof / zero_byte / path_traversal / unsupported_extension testleri |
| Tekrar belge tespit ediliyor (aynı case, 409); farklı tenant sızıntısı yok | Yüksek | duplicate_same_case / same_hash_different_case testleri |
| Analiz durumu izlenebilir (state machine); geçersiz geçiş engellenir | Kritik | retry / state transitions |
| Çıkarılan her bilgi sayfa konumuna bağlı (PDF gerçek sayfa) | Kritik | extraction_provenance testi |
| Kullanıcı doğrulama/reddetme yapabiliyor → P2.4 document_verified fact | Kritik | confirm/reject → CaseFact + contradiction testleri |
| Okunamayan/görsel belge açıkça işaretleniyor (uydurma yok) | Yüksek | image upload_only / udf binary unsupported |

Not: Analiz P2.5'te senkron yürütülür (arka plan job kuyruğu ileri sürüm);
gerçek OCR ve chunked upload kapsam dışıdır.

## P2.6 — Kaynak omurgası

Durum: ✅ Uygulandı (P2.6). Kanıtlar `backend/tests/test_source_backbone_services.py`
(26 test) + `test_source_backbone_routes.py` (20 test) ve mobil
`source_repository_test.dart` / `sources_screen_test.dart` (14 test). Gerçek
provider/adapter matrisi, SSRF kontrolleri ve kapsam dışı için
`P2_SOURCE_BACKBONE.md §18`.

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Resmî kaynak metadata modeli tamam (SourceRecord/Version/Paragraph/Verification/Relationship/Usage) | Kritik | migration ce94808703a4 + schema tests |
| İçerik hash ve retrieval zamanı tutuluyor | Kritik | ingestion idempotent/new-version tests |
| Doğrulama/güncellik statüsü + state machine | Kritik | verification SM + temporal tests |
| Tekrar kararlar canonical key ile birleştiriliyor | Kritik | canonical-key equivalent-variant tests |
| Eski/yürürlükten kalkmış kaynak işaretleniyor; olay tarihiyle validity | Kritik | temporal validity tests |
| Kaynak kullanım izi dosya ve paragrafa bağlanıyor; yeni sürümde korunuyor | Kritik | usage traceability tests |
| Doğrulanmamış kaynak verified_official olamıyor; SSRF fail-closed | Kritik | verify-official-requires-evidence + SSRF matrix |
| Çelişkili/karantina kaynak dosyaya trusted eklenemiyor; foreign case/usage 404 | Kritik | usage block + IDOR tests |

Not: Embedding/semantic index (P2.7) ve canlı resmi fetch entegrasyonu bu
dilimin acceptance koşulu değildir; secure fetcher SSRF korumasıyla hazır ve
deterministik test edilir.

## P2.7 — Hibrit arama

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Anahtar kelime ve semantik arama birlikte çalışıyor | Kritik | integration test |
| Mahkeme, daire, tarih ve doğrulama filtreleri çalışıyor | Yüksek | API test |
| Karşıt karar araması destekleniyor | Yüksek | benchmark |
| Tekrar sonuçlar bastırılıyor | Yüksek | dedupe benchmark |
| Dosya bağlamı sıralamaya kontrollü etki ediyor | Kritik | ranking test |
| Pilot benchmark ilk 3/ilk 10 hedefleri tanımlı ve ölçülüyor | Kritik | benchmark report |

## P2.8 — Hukuki mesele grafiği

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Mesele, olay, delil, kaynak ve risk bağlantıları kuruluyor | Kritik | graph integration |
| İspat yükü ve karşı argüman tutuluyor | Yüksek | schema/API test |
| Kaynaksız iddia açıkça işaretleniyor | Kritik | rule test |
| Eksik delil grafikte görünür | Kritik | E2E test |
| Grafik sürümlü ve yeniden üretilebilir | Yüksek | version test |

## P2.9 — Kaynaklı dilekçe

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Yeterlilik kontrolü taslak öncesi çalışıyor | Kritik | workflow test |
| Her önemli paragraf olay/delil/kaynak bağlantısı taşıyor | Kritik | traceability test |
| Doğrulanmamış karar numarası nihai metne giremiyor | Kritik | hallucination test |
| Tarih/tutar/talep tutarlılık kontrolleri çalışıyor | Kritik | validation tests |
| Kullanılan/kullanılmayan kaynak gerekçesi görülebiliyor | Yüksek | UI/API test |
| DOCX ve PDF dışa aktarma çalışıyor | Kritik | artifact test |
| Sürüm geçmişi ve avukat düzenlemeleri korunuyor | Yüksek | revision test |

## P2.10 — UYAP Bridge

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Bağlantı durumu ve son kontrol zamanı gösteriliyor | Kritik | integration/UI test |
| Dosya numarası eşleştirme çalışıyor | Kritik | matching test |
| Manuel evrak ekleme ve etiketleme çalışıyor | Kritik | E2E test |
| Yeni hareket rozeti ve okundu durumu var | Yüksek | mobile test |
| UYAP parolası/token loglarda yok | Kritik | log/security scan |
| Modül kapatılabilir | Kritik | feature flag test |
| İlk sürümde otomatik evrak gönderimi yok | Kritik | scope review |

## P2.11 — Beta ve App Store

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Kapalı beta başarı ölçütleri karşılandı | Kritik | beta report |
| Kritik crash/güvenlik açığı yok | Kritik | crash/security report |
| Hesap kapatma ve veri silme çalışıyor | Kritik | E2E + purge test |
| Gizlilik metinleri ve izin açıklamaları hazır | Kritik | App Store package |
| Pilot dosya uçtan uca tamamlanıyor | Kritik | recorded E2E |
| Kaynak uydurma ve prompt injection testleri geçiyor | Kritik | adversarial report |
| Performans hedefleri karşılanıyor | Yüksek | performance report |

## Genel kapanış kuralı

- Kritik kriterlerden herhangi biri başarısızsa aşama kapatılamaz.
- `continue-on-error`, test skip veya hata gizleme kapanış kanıtı değildir.
- Her aşama için CI çıktısı, test raporu, risk kaydı ve rollback yöntemi bulunmalıdır.
