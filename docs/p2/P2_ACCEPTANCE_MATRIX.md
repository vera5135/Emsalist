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

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Desteklenen formatlar doğrulanıyor | Kritik | upload tests |
| Boyut, MIME, hash ve path traversal kontrolleri var | Kritik | security tests |
| Tekrar belge tespit ediliyor | Yüksek | dedupe test |
| Analiz asenkron ve durum izlenebilir | Kritik | job integration |
| Çıkarılan her bilgi sayfa/paragraf konumuna bağlı | Kritik | extraction test |
| Kullanıcı doğrulama/reddetme yapabiliyor | Kritik | API/mobile test |
| Okunamayan/eksik sayfa açıkça işaretleniyor | Yüksek | fixture test |

## P2.6 — Kaynak omurgası

| Kriter | Öncelik | Kanıt |
|---|---:|---|
| Resmî kaynak metadata modeli tamam | Kritik | DB/API schema |
| İçerik hash ve retrieval zamanı tutuluyor | Kritik | ingestion test |
| Doğrulama/güncellik statüsü mevcut | Kritik | API test |
| Tekrar kararlar canonical key ile birleştiriliyor | Kritik | dedupe test |
| Eski/yürürlükten kalkmış kaynak işaretleniyor | Kritik | version test |
| Kaynak kullanım izi dosya ve dilekçeye bağlanıyor | Kritik | traceability test |
| Doğrulanmamış kaynak doğrulanmış etiketi alamıyor | Kritik | rule test |

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
