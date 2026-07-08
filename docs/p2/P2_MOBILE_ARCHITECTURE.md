# P2 Mobile Architecture

## 1. Amaç

Bu belge `/mobile` altında kurulacak Flutter uygulamasının paket yapısını, state yönetimi, API erişimi, güvenli depolama, offline davranış ve test sınırlarını tanımlar.

## 2. Proje konumu

```text
/mobile
  /lib
  /test
  /integration_test
  /ios
  /android
```

Android dizini Flutter gereği bulunabilir; P2'nin birincil yayın hedefi iOS'tur.

## 3. Flavor'lar

- development
- staging
- production

Her flavor ayrı:

- bundle identifier
- API base URL
- push environment
- analytics/crash environment
- app display suffix

taşır.

## 4. Mimari yaklaşım

Feature-first, katmanlı yapı:

```text
lib/
  app/
  core/
  design_system/
  features/
    auth/
    workspace/
    cases/
    chat/
    case_memory/
    documents/
    sources/
    search/
    drafts/
    uyap/
    notifications/
    settings/
```

Her feature:

- presentation
- application/state
- domain
- data/repository

sınırlarına ayrılır. Küçük feature'larda gereksiz dosya çoğaltılmaz; ancak UI doğrudan HTTP client çağırmaz.

## 5. State yönetimi

Karar:

- predictable, test edilebilir provider/state container yaklaşımı
- async loading/data/error durumları ortak model
- navigation ve session state ayrıştırılır
- case-scoped state aktif case değişiminde invalidate edilir

Kesin kütüphane P2.1 ADR'sinde seçilir; Riverpod önerilen başlangıçtır.

## 6. API erişimi

- OpenAPI generated DTO/client
- Generated client doğrudan widget'ta kullanılmaz
- Repository adapter domain model dönüşümü yapar
- Ortak auth, request ID, retry ve error mapping interceptor'ları
- Idempotency key istemci tarafından üretilir

## 7. Navigation

- Typed routes
- Auth guard
- Workspace guard
- Case deep link guard
- Notification deep link
- Yetkisiz hedefte güvenli geri dönüş

Ana shell:

- Asistan
- Dosyalar
- Kaynaklar
- Taslaklar

## 8. Güvenli depolama

Secure storage:

- refresh token
- device/session identifier
- gerektiğinde encryption key reference

Normal preferences:

- theme mode
- non-sensitive UI preferences
- onboarding status

## 9. Yerel veri

Şifreli cache:

- son 20 case metadata
- case başına son 200 mesaj
- gönderilmemiş metin queue
- kaynak/draft özetleri sınırlı

Varsayılan olarak saklanmaz:

- belge bytes
- UYAP evrak bytes
- tam export artifacts
- credential

## 10. Offline queue

Queue item:

- client_request_id
- operation type
- case/conversation ID
- safe payload reference
- created_at
- retry count
- status

Sadece güvenli ve idempotent işlemler queue'ya alınır. Belge upload ayrı resumable upload durumuyla yönetilir.

## 11. Tema ve design system

- ThemeMode.system default
- Light/dark tokens
- Semantic colors
- Renk dışında ikon/metin durumu
- Dynamic Type
- Safe area
- Minimum touch target
- VoiceOver labels

## 12. Chat rendering

Mesaj listesi:

- virtualized/lazy
- stable message keys
- pagination upward
- composer keyboard-safe
- async message status
- card type registry

Kart tipleri domain-specific widget'lara ayrılır.

## 13. Error mapping

Backend error code → kullanıcı mesajı → retry policy.

UI stack trace veya raw response göstermez. Request ID destek için görünür olabilir.

## 14. Push notification

- Device token registration
- Token refresh
- Environment ayrımı
- Hassas body yok
- Deep link authorization
- Foreground/in-app notification handling

## 15. Crash ve analytics

- İçeriksiz crash metadata
- User/workspace hash
- Case text veya belge adı gönderilmez
- Screen/flow events allowlist
- Development debug logs production'da kapalı

## 16. Build ve CI

P2.1 CI:

- flutter format
- flutter analyze
- unit/widget tests
- golden tests
- iOS simulator build
- generated client drift check

Production signing secrets CI secret store'da olur.

## 17. Test edilebilirlik

- Repository interface mock
- Fake clock
- Fake connectivity
- Fake secure storage
- Deterministic theme/golden
- Integration environment config

## 18. Kabul kriterleri

- `/mobile` backend'den bağımsız build edilir.
- UI doğrudan HTTP çağırmaz.
- Token secure storage'dadır.
- Aktif case değişiminde eski case state'i görünmez.
- Offline retry duplicate mesaj üretmez.
- Küçük iPhone, dark mode ve Dynamic Type testleri geçer.
