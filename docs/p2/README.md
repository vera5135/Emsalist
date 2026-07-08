# Emsalist P2 Planlama Alanı

Bu dizin, Emsalist P2 ürün ve mimari kararlarının tek referans alanıdır.

## P2 amacı

P2 sonunda Emsalist; iOS öncelikli, chat-first çalışan, her konuşmayı bir hukuk dosyasına bağlayan, belge ve kaynak izlenebilirliği sağlayan, doğrulanabilir içtihat/mevzuat kullanan ve kaynak bağlantılı dilekçe üreten bir mobil hukuk çalışma alanına dönüşecektir.

## Değişmeyen ürün ilkeleri

1. Önce güvenilir dosya ve kaynak omurgası, sonra arama, sonra semantik hukuk katmanı, en son otomasyon ve UYAP.
2. Yapay zekâ kaynaksız kesin hukuk hükmü üretmez.
3. Doğrulanmamış kaynak, doğrulanmış gibi sunulmaz.
4. Dosyalar tenant, kullanıcı ve yetki düzeyinde birbirinden izole edilir.
5. Belgeden çıkarılan bilgiler kullanıcı onayı veya doğrulama statüsü olmadan kesin gerçek sayılmaz.
6. Mobil arayüz form ağırlıklı değil, konuşma ve bağlamsal kart ağırlıklı olur.
7. Asistan aynı anda uzun soru listeleri yerine en kritik tek soruyu sorar.
8. UYAP entegrasyonu bağımsız, kapatılabilir ve güvenlik sınırları belirlenmiş bir modül olur.
9. iPhone birincil istemcidir; Android P2 beta sonrasına bırakılır.
10. P2.0 aşamasında ürün kodu yazılmaz; kapsam, sözleşmeler ve kabul kriterleri kilitlenir.

## Planlanan dokümanlar

- `P2_MASTER_PLAN.md`: ürün hedefi, aşamalar, bağımlılıklar ve kapanış kapıları
- `P2_DECISION_REGISTER.md`: kesinleşen ve açık ürün/mimari kararları
- `P2_ACCEPTANCE_MATRIX.md`: her P2 aşaması için ölçülebilir kabul kriterleri
- `P2_PRODUCT_SCOPE.md`: kapsam içi ve kapsam dışı maddeler
- `P2_USER_FLOWS.md`: uçtan uca kullanıcı akışları
- `P2_INFORMATION_ARCHITECTURE.md`: mobil bilgi mimarisi ve ekran haritası
- `P2_CONVERSATION_DESIGN.md`: asistan davranışı ve mesaj/kart tipleri
- `P2_CASE_MEMORY_MODEL.md`: yapılandırılmış dosya hafızası
- `P2_DOCUMENT_PIPELINE.md`: belge yükleme, çıkarım ve doğrulama süreci
- `P2_SOURCE_BACKBONE.md`: güvenilir hukuk kaynağı omurgası
- `P2_SEARCH_ARCHITECTURE.md`: hibrit arama ve kalite ölçümü
- `P2_GROUNDED_DRAFTING.md`: kaynak bağlantılı dilekçe üretimi
- `P2_UYAP_BRIDGE.md`: UYAP kapsamı ve güvenlik sınırları
- `P2_API_CONTRACT.md`: mobil-backend API sözleşmesi
- `P2_DATA_MODEL.md`: veri modeli ve ilişki sınırları
- `P2_SECURITY_PRIVACY.md`: KVKK, gizlilik ve erişim kontrolleri
- `P2_TEST_STRATEGY.md`: backend, mobil, güvenlik ve benchmark testleri
- `P2_RISK_REGISTER.md`: ürün, hukuk, veri, güvenlik ve operasyon riskleri
- `P2_BACKLOG.md`: uygulanabilir iş paketleri ve bağımlılıkları

## Geliştirme kapısı

`chore/p2.0-planning-baseline` PR'ı onaylanmadan Flutter projesi, yeni mobil endpoint veya P2 veri tabanı migration'ı oluşturulmaz.
