# P2 API Contract

## 1. Amaç

Bu belge Flutter istemci ile FastAPI backend arasındaki sözleşme ilkelerini, endpoint gruplarını, hata modelini, pagination, idempotency ve sürümleme kurallarını tanımlar.

## 2. Genel ilkeler

- Base path: `/api/v1`
- JSON UTF-8
- ISO-8601 UTC timestamps
- UUID/opaque string kimlikler
- Bearer access token
- Workspace/tenant bağlamı token ve server-side üyelikten belirlenir
- Case erişimi ayrıca doğrulanır
- OpenAPI tek kaynak sözleşmedir
- Breaking değişiklik yeni API versiyonu gerektirir

## 3. Ortak header'lar

İstek:

- `Authorization: Bearer <token>`
- `X-Request-ID`
- `Idempotency-Key` yazma komutlarında
- `If-Match` optimistic locking gereken güncellemelerde

Yanıt:

- `X-Request-ID`
- `ETag`
- `Retry-After` rate limit/retry durumunda

## 4. Hata modeli

```json
{
  "error": {
    "code": "CASE_VERSION_CONFLICT",
    "message": "Dosya başka bir işlem tarafından güncellendi.",
    "request_id": "req_123",
    "details": {
      "current_version": 8
    },
    "retryable": false
  }
}
```

Ham stack trace istemciye dönmez.

## 5. Pagination

Cursor modeli:

```json
{
  "items": [],
  "page": {
    "next_cursor": "opaque",
    "has_more": true
  }
}
```

Offset pagination yalnız küçük admin listelerinde kullanılabilir.

## 6. Kimlik ve oturum

- POST `/auth/login`
- POST `/auth/refresh`
- POST `/auth/logout`
- GET `/auth/sessions`
- DELETE `/auth/sessions/{session_id}`
- POST `/auth/email/verify`
- POST `/auth/password/reset-request`
- POST `/auth/password/reset`

Token response access token süresi ve refresh davranışını içerir; refresh token güvenli depoda tutulur.

## 7. Workspace ve kullanıcı

- GET `/workspaces`
- GET `/workspaces/{workspace_id}`
- GET `/workspaces/{workspace_id}/members`
- POST `/workspaces/{workspace_id}/members`
- PATCH `/workspaces/{workspace_id}/members/{member_id}`
- DELETE `/workspaces/{workspace_id}/members/{member_id}`
- GET `/me`
- PATCH `/me/preferences`

## 8. Cases

- POST `/cases`
- GET `/cases`
- GET `/cases/{case_id}`
- PATCH `/cases/{case_id}`
- POST `/cases/{case_id}/archive`
- POST `/cases/{case_id}/restore`
- DELETE `/cases/{case_id}`
- GET `/cases/{case_id}/summary`
- GET `/cases/{case_id}/activity`

Create case request:

```json
{
  "title": null,
  "legal_domain": "consumer",
  "initial_narrative": "...",
  "client_request_id": "mobile_uuid"
}
```

## 9. Conversations ve messages

- POST `/cases/{case_id}/conversations`
- GET `/cases/{case_id}/conversations`
- GET `/conversations/{conversation_id}/messages`
- POST `/conversations/{conversation_id}/messages`
- POST `/messages/{message_id}/retry`
- POST `/messages/{message_id}/feedback`

Mesaj response durumları:

- accepted
- processing
- completed
- failed

Streaming sonraki aşamada SSE veya WebSocket ile eklenebilir; ilk sözleşme polling uyumlu olmalıdır.

## 10. Case memory

- GET `/cases/{case_id}/memory`
- GET `/cases/{case_id}/facts`
- PATCH `/cases/{case_id}/facts/{fact_id}`
- POST `/cases/{case_id}/facts/{fact_id}/confirm`
- POST `/cases/{case_id}/facts/{fact_id}/reject`
- GET `/cases/{case_id}/timeline`
- GET `/cases/{case_id}/missing-information`
- GET `/cases/{case_id}/contradictions`
- POST `/cases/{case_id}/contradictions/{id}/resolve`
- GET `/cases/{case_id}/risks`
- GET `/cases/{case_id}/deadlines`
- POST `/cases/{case_id}/deadlines/{id}/confirm`

## 11. Documents

- POST `/cases/{case_id}/documents/uploads`
- POST `/documents/{document_id}/parts`
- POST `/documents/{document_id}/complete-upload`
- GET `/cases/{case_id}/documents`
- GET `/documents/{document_id}`
- GET `/documents/{document_id}/analysis-runs`
- POST `/documents/{document_id}/reprocess`
- POST `/document-findings/{finding_id}/confirm`
- POST `/document-findings/{finding_id}/reject`
- DELETE `/documents/{document_id}`

Upload session response signed target veya API upload URL'si döndürür.

### 11.1 P2.5 uygulanan endpoint'ler (case-scoped, authenticated)

İlk sürümde tek-atışlık multipart upload uygulanmıştır (chunked/parts ve
analysis-runs ileri sürüm). Tümü tenant + case-owner scoped; foreign/unknown
kaynak `404` döner:

- `POST /api/v1/cases/{case_id}/documents` (multipart/form-data, alan `file`, opsiyonel `document_type`) → 201; aynı hash aynı case'de → `409` (`X-Duplicate-Document-Id`)
- `GET /api/v1/cases/{case_id}/documents`
- `GET /api/v1/cases/{case_id}/documents/{document_id}`
- `DELETE /api/v1/cases/{case_id}/documents/{document_id}` (soft delete, 204)
- `GET /api/v1/cases/{case_id}/documents/{document_id}/content` (authenticated download)
- `POST /api/v1/cases/{case_id}/documents/{document_id}/retry`
- `GET /api/v1/cases/{case_id}/documents/{document_id}/pages`
- `GET /api/v1/cases/{case_id}/documents/{document_id}/analysis`
- `POST /api/v1/cases/{case_id}/documents/{document_id}/type`
- `POST /api/v1/cases/{case_id}/documents/{document_id}/extractions/{extraction_id}/confirm`
- `POST /api/v1/cases/{case_id}/documents/{document_id}/extractions/{extraction_id}/reject`

## 12. Legal sources ve search

- POST `/search/legal`
- POST `/search/similar`
- POST `/search/opposing`
- GET `/legal-sources/{source_id}`
- GET `/legal-sources/{source_id}/versions`
- GET `/legal-sources/{source_id}/paragraphs`
- GET `/cases/{case_id}/sources`
- POST `/cases/{case_id}/sources`
- DELETE `/cases/{case_id}/sources/{usage_id}`
- POST `/search/results/{result_id}/feedback`

## 13. Legal issues

- GET `/cases/{case_id}/legal-issues`
- POST `/cases/{case_id}/legal-issues/rebuild`
- PATCH `/legal-issues/{issue_id}`
- POST `/legal-issues/{issue_id}/merge`
- POST `/legal-issues/{issue_id}/reject`
- GET `/legal-issues/{issue_id}/graph`

## 14. Drafts

- POST `/cases/{case_id}/drafts`
- GET `/cases/{case_id}/drafts`
- GET `/drafts/{draft_id}`
- POST `/drafts/{draft_id}/readiness-check`
- POST `/drafts/{draft_id}/plan`
- POST `/drafts/{draft_id}/generate`
- PATCH `/drafts/{draft_id}/paragraphs/{paragraph_id}`
- POST `/drafts/{draft_id}/validate`
- POST `/drafts/{draft_id}/submit-review`
- POST `/drafts/{draft_id}/approve`
- POST `/drafts/{draft_id}/export`
- GET `/drafts/{draft_id}/revisions`

## 15. UYAP

- GET `/uyap/status`
- POST `/uyap/connect`
- POST `/uyap/disconnect`
- POST `/uyap/sync`
- GET `/uyap/movements`
- POST `/uyap/movements/{movement_id}/match-case`
- POST `/uyap/movements/{movement_id}/mark-read`
- POST `/uyap/movements/{movement_id}/extract-deadline`

## 16. Notifications

- GET `/notifications`
- POST `/notifications/{notification_id}/mark-read`
- POST `/notifications/mark-all-read`
- GET `/notification-preferences`
- PATCH `/notification-preferences`
- POST `/devices/push-tokens`
- DELETE `/devices/push-tokens/{token_id}`

## 17. Background jobs

Uzun işlemler job resource döndürür:

```json
{
  "job_id": "job_123",
  "status": "queued",
  "poll_url": "/api/v1/jobs/job_123"
}
```

- GET `/jobs/{job_id}`
- POST `/jobs/{job_id}/cancel`

Job response progress percent yerine güvenilir stage kullanabilir.

## 18. Idempotency

Zorunlu işlemler:

- case create
- message send
- upload complete
- document reprocess
- UYAP sync
- draft generation
- export

Aynı key ve aynı request hash aynı sonucu döndürür. Aynı key farklı payload ile conflict üretir.

## 19. Optimistic locking

PATCH request:

- `If-Match: "version-8"`

Conflict:

- HTTP 412 veya 409
- mevcut version bilgisi
- istemci merge/reload seçeneği

## 20. HTTP durumları

- 200 başarı
- 201 oluşturuldu
- 202 asenkron kabul
- 204 içerik yok
- 400 doğrulama
- 401 oturum yok/geçersiz
- 403 yetki yok
- 404 bulunamadı veya erişim gizleme
- 409 idempotency/iş kuralı conflict
- 412 version conflict
- 413 dosya büyük
- 415 format desteklenmiyor
- 422 semantic validation
- 429 rate limit
- 503 bağımlı servis geçici unavailable

## 21. Mobil cache ve sync

List response'ları `updated_at`, `version` ve tombstone bilgisi taşır. Mobil delta sync için ileride:

- GET `/sync/changes?cursor=`

endpoint'i eklenebilir.

## 22. Güvenlik

- Object-level authorization her endpoint'te
- Tenant ID request body'den güvenilir kabul edilmez
- Signed URL kısa süreli ve tek belgeye bağlı
- Hassas alanlar response modelinde explicit inclusion ile döner
- Admin endpoint'leri ayrı scope ister

## 23. OpenAPI kapısı

CI şunları doğrular:

- schema üretimi deterministic
- security scheme mevcut
- response/error modelleri belgeli
- istemci codegen breaking diff kontrolü
- docs ve kod endpoint isimleri uyumlu

## 24. Kapanış kriterleri

- Endpoint grupları ürün aşamalarıyla eşleşir.
- Idempotency ve optimistic locking tanımlıdır.
- Tenant/case authorization body parametresine dayanmaz.
- Uzun işlemler job modeli kullanır.
- Ortak hata modeli mobilde güvenli gösterilebilir.
- OpenAPI sözleşmesi Flutter istemci üretimine uygundur.

## 25. Mevcut backend davranışı (P2.2A gerçek durum)

Bu bölüm, bu belgenin geri kalanının tanımladığı **hedef** sözleşmeden farklı
olarak, P2.2A sırasında mobil istemcinin bağlandığı **gerçek** backend
davranışını kaydeder. Kaynak: `backend/app` ve `docs/api/openapi-v1.json`.

- Canonical base path: `/api/v1`. Legacy flat alias'lar (prefix'siz) mevcut ama
  OpenAPI şemasına dahil değildir (`include_in_schema=false`).
- Correlation header: istek ve yanıt `X-Correlation-ID` kullanır.
- Hata zarfı gerçek alanı: `correlation_id` (bkz. aşağıdaki delta).
- `request_id` yalnızca ileriye dönük uyumluluk için okunur (fallback); gerçek
  backend şu an bunu döndürmez.
- Varsayılan auth modu `local`'dir; bu modda token gerekmez. `jwt` modu
  `Authorization: Bearer` ile HS256 kullanır (P2.2B1 kapsamı).
- CORS yalnız `GET`, `POST`, `DELETE` metotlarına izin verir; izinli header'lar
  `Content-Type`, `Authorization`, `X-Correlation-ID`. Native mobil istemcide
  CORS uygulanmaz; bu not webview/tarayıcı akışları içindir.
- P2.2A'nın entegre ettiği read-only endpoint'ler:
  - `GET /api/v1/meta/version` → `{application, version, api_version, commit, build_timestamp, environment}`
  - `GET /health` → `{status: healthy|unhealthy|degraded, service, checks, components}` (unhealthy'de HTTP 503)

### 25.1 Hedef sözleşme ile mevcut backend farkları (delta)

| Konu | Hedef sözleşme (bu belge) | Mevcut backend (P2.2A) |
| --- | --- | --- |
| Correlation header | `X-Request-ID` | `X-Correlation-ID` |
| Hata alanı | `error.request_id`, `error.retryable`, `error.details` | `error.correlation_id` (retryable/details yok) |
| Auth | her istek `Bearer` | varsayılan `local` (tokensiz), opsiyonel `jwt` |
| Cases | `POST/GET /cases`, `GET /cases/{id}` | yok; `GET /case/current`, `GET /case/state?case_id=` var |
| Pagination | cursor (`page.next_cursor`) | ilgili read-only endpoint'lerde yok |
| Idempotency-Key / If-Match | zorunlu (yazma) | uygulanmıyor |
| HTTP metotları | PATCH/PUT dahil | CORS yalnız GET/POST/DELETE |

## 26. P2.2B1 Auth contract stabilization

P2.2B1, login/refresh/change-password auth endpoint'lerini stabilize eder ve
aşağıdaki değişiklikleri getirir:

### Login response (`POST /api/v1/auth/login`)

`LoginResponse` artık aşağıdaki alanları içerir:

```json
{
  "access_token": "<JWT>",
  "refresh_token": "<64-char-hex>",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_expires_in": 604800,
  "user": { "id": "...", "tenant": "...", "role": "..." }
}
```

- `refresh_token` gerçek backend refresh token'dır (64 hex karakter).
- `refresh_expires_in` 7 gün (604800 saniye) olarak döner.

### Refresh request (`POST /api/v1/auth/refresh`)

Artık JSON body kabul eder:

```json
{ "refresh_token": "<64-char-hex>" }
```

Response aynı modelde döner:

```json
{
  "access_token": "<new-JWT>",
  "refresh_token": "<new-64-char-hex>",
  "token_type": "bearer",
  "expires_in": 1800,
  "refresh_expires_in": 604800
}
```

- Her refresh yeni bir `refresh_token` döndürür (rotation).
- Eski refresh token yeniden kullanılırsa tüm token family revoke edilir.

### Change password (`POST /api/v1/auth/change-password`)

Artık çalışır (HTTP 501 kaldırıldı). Token version'ı artırır ve tüm refresh
session'ları revoke eder. İstemci yeniden login olmak zorundadır.

### Rate limiting

Login endpoint'ine in-memory rate limiter bağlanmıştır: `AUTH_MODE=jwt` modunda
5 başarısız denemeden sonra 15 dakika bloke. DB-level locking de korunur.

### Production safety

Production ortamında `AUTH_MODE=local` ile başlatma engellenir (mevcut
`validate_production_config` ile).

### Auth edpoint listesi

| Method | Path | Auth | Response model |
|--------|------|------|----------------|
| `POST` | `/api/v1/auth/login` | none | `LoginResponse` |
| `POST` | `/api/v1/auth/refresh` | none (body token) | `TokenRefreshResponse` |
| `GET` | `/api/v1/auth/me` | Bearer | `MeResponse` |
| `POST` | `/api/v1/auth/logout` | Bearer | `MessageResponse` |
| `POST` | `/api/v1/auth/logout-all` | Bearer | `MessageResponse` |
| `POST` | `/api/v1/auth/change-password` | Bearer | `MessageResponse` |

Bu bölüm, bu belgenin geri kalanının tanımladığı **hedef** sözleşmeden farklı
olarak, P2.2A sırasında mobil istemcinin bağlandığı **gerçek** backend
davranışını kaydeder. Kaynak: `backend/app` ve `docs/api/openapi-v1.json`.

- Canonical base path: `/api/v1`. Legacy flat alias'lar (prefix'siz) mevcut ama
  OpenAPI şemasına dahil değildir (`include_in_schema=false`).
- Correlation header: istek ve yanıt `X-Correlation-ID` kullanır.
- Hata zarfı gerçek alanı: `correlation_id` (bkz. aşağıdaki delta).
- `request_id` yalnızca ileriye dönük uyumluluk için okunur (fallback); gerçek
  backend şu an bunu döndürmez.
- Varsayılan auth modu `local`'dir; bu modda token gerekmez. `jwt` modu
  `Authorization: Bearer` ile HS256 kullanır (P2.2B kapsamı).
- CORS yalnız `GET`, `POST`, `DELETE` metotlarına izin verir; izinli header'lar
  `Content-Type`, `Authorization`, `X-Correlation-ID`. Native mobil istemcide
  CORS uygulanmaz; bu not webview/tarayıcı akışları içindir.
- P2.2A'nın entegre ettiği read-only endpoint'ler:
  - `GET /api/v1/meta/version` → `{application, version, api_version, commit, build_timestamp, environment}`
  - `GET /health` → `{status: healthy|unhealthy|degraded, service, checks, components}` (unhealthy'de HTTP 503)

### 25.1 Hedef sözleşme ile mevcut backend farkları (delta)

| Konu | Hedef sözleşme (bu belge) | Mevcut backend (P2.2A) |
| --- | --- | --- |
| Correlation header | `X-Request-ID` | `X-Correlation-ID` |
| Hata alanı | `error.request_id`, `error.retryable`, `error.details` | `error.correlation_id` (retryable/details yok) |
| Auth | her istek `Bearer` | varsayılan `local` (tokensiz), opsiyonel `jwt` |
| Cases | `POST/GET /cases`, `GET /cases/{id}` | yok; `GET /case/current`, `GET /case/state?case_id=` var |
| Pagination | cursor (`page.next_cursor`) | ilgili read-only endpoint'lerde yok |
| Idempotency-Key / If-Match | zorunlu (yazma) | uygulanmıyor |
| HTTP metotları | PATCH/PUT dahil | CORS yalnız GET/POST/DELETE |

Mobil istemci P2.2A'da gerçek backend davranışına uyar: `X-Correlation-ID`
gönderir, `correlation_id` okur, `request_id`'yi yalnız fallback olarak dener.
Backend route veya davranışı P2.2A kapsamında değiştirilmez.

### 25.2 OpenAPI mobile client codegen ertelemesi

Tam backend OpenAPI'sinden mobile client codegen, canonical sözleşme (cases,
pagination, idempotency, optimistic locking) stabilize olana kadar **bilinçli
olarak ertelenmiştir**. P2.2A yalnız seçili sistem endpoint'leri için elle
yazılmış DTO (json_serializable) kullanır ve bu endpoint'lerin varlığını
`docs/api/openapi-v1.json` snapshot'ına karşı bir contract test ile doğrular.
Tam codegen drift kapısı sonraki bir faza bırakılmıştır.

## 26. P2.2B2A Apple auth backend & email-only account resolution

Bu bölüm P2.2B2A backend omurgasını sabitler. Mobil UI (P2.2B2B) ayrıdır.

### Ürün kararı

- Kullanıcıya **büro kodu, tenant, tenant_slug, workspace veya çalışma alanı
  sorulmaz.**
- Ana iOS giriş yöntemi: **Apple ile Devam Et.** Yedek yöntem: e-posta + şifre.
- İlk Apple bağlantısında kullanıcıdan yalnız **e-posta + mevcut Emsalist
  şifresi** istenir.
- Apple hesabı otomatik yeni hesap oluşturmaz, Apple e-postasına göre otomatik
  eşleştirilmez; yalnız mevcut ve doğrulanmış bir Emsalist hesabına bağlanır.

### E-posta/şifre login (`POST /api/v1/auth/login`)

`LoginRequest = { email, password, tenant_slug? }`

- `email` ve `password` zorunludur.
- `tenant_slug` yalnız **geriye dönük uyumlu, opsiyonel/deprecated** bir alandır.
  Yeni mobil istemci göndermez ve hiçbir mobil UI'da gösterilmez.
- `tenant_slug` **gönderilmezse**: e-posta trim+casefold ile normalize edilir,
  tüm aktif/silinmemiş kullanıcılar arasında aranır, **tam olarak bir** kullanıcı
  bulunursa canonical `tenant_id` `User.tenant_id` üzerinden alınır ve şifre
  doğrulanır.
- `tenant_slug` **gönderilirse**: `TenantRepository.get_by_slug` ile gerçek
  `Tenant` bulunur, canonical `tenant_id` olarak **`Tenant.id`** kullanılır.
  Slug hiçbir zaman doğrudan tenant ID gibi kullanılmaz.
- Canonical `tenant.id`; User sorgusu, `AuthSession.tenant_id`, JWT `tenant_id`
  claim'i, audit event ve `LoginResponse.user.tenant` alanında kullanılır.
  `LoginResponse.user.tenant` = **canonical tenant ID** (slug değil).

**Duplicate e-posta güvenlik davranışı:** dış hata mesajları hiçbir zaman
"e-posta bulunamadı", "birden fazla hesap", "şifre yanlış", "tenant bulunamadı"
veya "hesap pasif" durumlarını ayırt etmez. Genel mesaj: **"Giriş bilgileri
doğrulanamadı."**, machine-readable kod: `invalid_credentials`.

| Aktif kullanıcı | Davranış |
| --- | --- |
| 0 | generic `invalid_credentials` |
| 1 | şifre doğrulamasına devam |
| ≥2 | rastgele hesap seçilmez → generic (audit: `account_resolution_ambiguous`) |

### Apple endpoint sözleşmeleri

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/auth/apple/login` | none | `{ authorization_code, raw_nonce }` | `AppleAuthenticatedResponse` \| `AppleLinkRequiredResponse` |
| `POST` | `/api/v1/auth/apple/link` | none | `{ link_ticket, email, password }` | `LoginResponse` |
| `GET` | `/api/v1/auth/apple/status` | Bearer | – | `{ linked, provider }` |
| `POST` | `/api/v1/auth/apple/unlink` | Bearer | `{ current_password }` | `MessageResponse` |

`/apple/login` yanıtı `state` discriminator'lı ayrık birlik (discriminated
union):

- `state = "authenticated"` → `access_token, refresh_token, token_type,
  expires_in (1800), refresh_expires_in (604800), user{ id, tenant, role }`.
  **`link_ticket` bulunmaz.**
- `state = "link_required"` → `link_ticket, link_expires_in (300)`.
  **`access_token`/`refresh_token` bulunmaz.**

`/apple/link` isteği **yalnız `link_ticket` + `email` + `password`** içerir;
`tenant_slug` veya büro kodu **bulunmaz.** Tenant ilişkisi backend tarafından
`User.tenant_id` üzerinden çözülür. Başarılı yanıt mevcut `LoginResponse` ile
aynıdır. 0 kullanıcı, birden fazla kullanıcı ve yanlış şifre dışarıya aynı
generic `invalid_credentials` hatasını verir; duplicate durumda otomatik seçim
yapılmaz.

`/apple/status` raw Apple subject, Apple e-postası veya audience döndürmez.

`/apple/unlink` mevcut şifreyi doğrular, Apple identity eşlemesini kaldırır,
`token_version`'ı artırır ve kullanıcının tüm session'larını revoke eder
(mevcut oturum geçersiz olur; kullanıcı e-posta/şifreyle tekrar girebilir).
Apple bağlantısı yoksa idempotent başarı: `{ "message": "Apple account is not
linked." }`.

### Apple disabled davranışı

`APPLE_SIGN_IN_ENABLED=false` iken mevcut login/refresh çalışmaya devam eder,
Apple endpoint'leri token üretmez ve dış Apple servisine ağ çağrısı yapılmaz.
HTTP `503 Service Unavailable`, machine-readable kod `apple_sign_in_unavailable`.
Eksik environment değişkenleri yanıtta açıklanmaz.

### Güvenli hata kodları

`apple_sign_in_unavailable`, `apple_authorization_failed`,
`apple_link_ticket_invalid`, `apple_link_ticket_expired`,
`apple_identity_conflict`, `invalid_credentials`, `account_resolution_failed`.
Ham Apple `error_description` client'a dönmez.

### Gizlilik / kalıcılık

- Apple `sub` raw olarak saklanmaz: `HMAC-SHA256(key=APPLE_SUBJECT_PEPPER,
  message="apple|<audience>|<subject>")` hex digest'i `auth_identities`'te
  tutulur.
- Link ticket ≥32 byte CSPRNG ile üretilir; DB'de yalnız SHA-256 hash tutulur;
  raw ticket yalnız oluşturulurken bir kez yanıtta döner; TTL 300 sn; tek
  kullanımlık; tüketim transaction içinde atomiktir (paralel iki istekten yalnız
  biri başarılı).
- Bir Apple kimliği yalnız bir kullanıcıya; bir kullanıcı yalnız bir Apple
  kimliğine bağlanabilir.
