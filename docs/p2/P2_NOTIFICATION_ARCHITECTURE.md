# P2 Notification Architecture

## 1. Amaç

Bildirim sistemi; UYAP hareketleri, süreler, belge analizleri, kaynak güncellemeleri ve taslak incelemelerini güvenli, idempotent ve kullanıcı tercihleriyle uyumlu biçimde iletir.

## 2. Bildirim türleri

- uyap_new_movement
- uyap_auth_required
- deadline_upcoming
- deadline_overdue
- document_analysis_completed
- document_analysis_failed
- critical_contradiction
- missing_document
- source_updated
- draft_review_requested
- draft_changes_requested
- draft_approved

## 3. Öncelikler

- critical
- high
- normal
- informational

Critical bildirimler de hassas belge içeriği taşımaz.

## 4. Mimari

```text
Domain Event
  → Notification Outbox
  → Preference/Policy Filter
  → Channel Adapter
  → APNs / In-app
  → Delivery Receipt
```

FCM adapter Android aşamasında aynı interface ile eklenir.

## 5. Notification outbox

Alanlar:

- id
- workspace_id
- user_id
- case_id nullable
- event_type
- priority
- safe_payload_json
- target_type
- target_id
- idempotency_key
- scheduled_at
- status
- attempts
- created_at

DB transaction ile domain olayı ve outbox kaydı birlikte oluşturulur.

## 6. Güvenli payload

Push body örneği:

`Bir dosyanızda yeni UYAP hareketi var.`

Taşınabilir:

- notification_id
- target_type
- target_id opaque
- category

Taşınmaz:

- müvekkil adı
- belge adı/tam metni
- dosya içeriği
- UYAP credential
- kritik sağlık/ceza ayrıntısı

## 7. Tercihler

Kullanıcı kategori bazında:

- push açık/kapalı
- in-app açık/kapalı
- sessiz saatler
- kritik bildirim istisnası
- dosya bazlı mute

ayarlayabilir.

## 8. Sessiz saatler

- Kullanıcı timezone'u
- Deferred delivery
- Kritik süre politikası
- Aynı olay için bildirim birleştirme

## 9. İdempotency ve duplicate önleme

Key örneği:

`user_id|event_type|target_id|event_version`

Aynı event tekrar işlense bile tek kullanıcı bildirimi oluşur.

## 10. Deep link

Push açıldığında:

1. oturum kontrolü
2. workspace erişimi
3. target object authorization
4. hedef ekran

Yetkisiz veya silinmiş hedefte hassas bilgi gösterilmez.

## 11. Device token

- Token şifreli saklanır.
- Environment ayrılır.
- Token refresh güncellenir.
- Geçersiz token revoke edilir.
- Logout cihaz kaydını pasifleştirir.

## 12. In-app center

- okunmamış sayısı
- kategori filtreleri
- priority
- dosya bağlantısı
- mark read/all read
- retention

## 13. Deadline bildirimi

Yalnız confirmed deadline için kesin bildirim dili kullanılır. Proposed deadline:

`Olası bir süre tespit edildi; doğrulamanız gerekiyor.`

## 14. Source update bildirimi

Yalnız kaynak gerçekten bir case/draft usage kaydına bağlıysa gönderilir. Genel kaynak değişiklikleri kullanıcıyı gereksiz uyarmamalıdır.

## 15. Delivery status

- queued
- filtered
- scheduled
- sent
- delivered
- failed
- expired
- revoked_token

## 16. Retry

- exponential backoff
- max attempts
- permanent error separation
- dead-letter
- alert threshold

## 17. API özeti

- GET `/notifications`
- POST `/notifications/{id}/mark-read`
- POST `/notifications/mark-all-read`
- GET `/notification-preferences`
- PATCH `/notification-preferences`
- POST `/devices/push-tokens`
- DELETE `/devices/push-tokens/{id}`

## 18. Testler

- duplicate domain event
- quiet hours
- muted case
- revoked token
- unauthorized deep link
- safe payload scan
- timezone
- critical/proposed deadline language
- outbox transaction rollback

## 19. Kabul kriterleri

- Hassas içerik push payload'ına girmez.
- Duplicate event tek bildirim üretir.
- Sessiz saatler ve tercihler uygulanır.
- Deep link yeniden authorization yapar.
- Proposed süre kesin deadline gibi sunulmaz.
- Token logout/revoke sonrası kullanılmaz.
