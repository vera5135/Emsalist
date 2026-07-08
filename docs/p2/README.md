# Emsalist P2 Planlama Alanı

Bu dizin, Emsalist P2 ürün, mimari, güvenlik ve kabul kararlarının tek referans alanıdır.

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

## Tamamlanan P2.0 belgeleri

### Ürün ve süreç

- `P2_MASTER_PLAN.md`
- `P2_PRODUCT_SCOPE.md`
- `P2_DECISION_REGISTER.md`
- `P2_ACCEPTANCE_MATRIX.md`
- `P2_USER_FLOWS.md`
- `P2_INFORMATION_ARCHITECTURE.md`
- `P2_CONVERSATION_DESIGN.md`
- `P2_BACKLOG.md`
- `P2_RELEASE_STRATEGY.md`

### Mobil ve API mimarisi

- `P2_MOBILE_ARCHITECTURE.md`
- `P2_API_CONTRACT.md`
- `P2_DATA_MODEL.md`
- `P2_NOTIFICATION_ARCHITECTURE.md`

### Hukuk dosyası, belge ve kaynak

- `P2_CASE_MEMORY_MODEL.md`
- `P2_DOCUMENT_PIPELINE.md`
- `P2_SOURCE_BACKBONE.md`
- `P2_SEARCH_ARCHITECTURE.md`
- `P2_LEGAL_REASONING_MODEL.md`
- `P2_GROUNDED_DRAFTING.md`
- `P2_UYAP_BRIDGE.md`

### Güvenlik ve kalite

- `P2_SECURITY_PRIVACY.md`
- `P2_TEST_STRATEGY.md`
- `P2_OBSERVABILITY.md`
- `P2_RISK_REGISTER.md`

## Kabul edilmiş temel kararlar

- Flutter projesi monorepo içinde `/mobile`
- Production bundle ID hedefi `com.emsalist.app`
- Personal ve office workspace aynı tenant modelinde
- E-posta/parola başlangıç; Apple Sign In beta öncesi
- Şifreli sınırlı offline cache; belge bytes varsayılan olarak offline değil
- 30 gün soft-delete ve legal hold koruması
- İlk beta belge sınırı 25 MB
- UDF yalnız backend sandbox parser
- Notification outbox + APNs/FCM adapter
- Provider-agnostic AI katmanı
- 15 avukatlık ücretsiz kapalı beta
- İlk pilot ayıplı araç/tüketici hukuku

## Geliştirme kapısı

P2.0 PR'ı merge edilmeden Flutter projesi, yeni mobil endpoint veya P2 migration'ı oluşturulmaz. P2.0 merge sonrasında ilk uygulama branch'i:

```text
feat/p2.1-mobile-shell
```

İlk gerçek geliştirme yalnız mobil shell, tema, navigasyon, chat composer, dosya drawer mock'u ve UYAP durum mock'u ile sınırlıdır.
