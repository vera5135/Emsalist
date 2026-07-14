# Emsalist P2 Master Plan

## 1. Amaç

P2, Emsalist'i mevcut backend temeli üzerinde çalışan iOS-first bir hukuk çalışma alanına dönüştürür. Ürün; dosya hafızası, belge analizi, güvenilir hukuk kaynakları, hibrit arama, hukuki mesele grafiği, kaynak bağlantılı dilekçe üretimi ve kontrollü UYAP entegrasyonunu tek mobil deneyimde birleştirir.

## 2. Başarı tanımı

P2 başarılı sayılabilmek için kullanıcı şu uçtan uca akışı güvenli ve izlenebilir biçimde tamamlayabilmelidir:

1. Yeni dosya açar.
2. Olayı doğal dille anlatır.
3. Belge yükler.
4. Sistem yapılandırılmış olay, tarih, taraf, talep, delil, eksik ve çelişki çıkarır.
5. Kullanıcı kritik bilgileri doğrular veya düzeltir.
6. Sistem güvenilir mevzuat ve içtihat arar.
7. Kaynakları hukuki mesele, iddia ve delillerle eşleştirir.
8. Kaynak bağlantılı dilekçe taslağı oluşturur.
9. Kullanıcı her paragrafın dayanağını inceler.
10. Taslağı DOCX/PDF olarak dışa aktarır.
11. UYAP hareketlerini ilgili dosyayla eşleştirir.

## 3. Sabit ürün kararları

- Birincil dağıtım kanalı iOS App Store'dur.
- Mobil istemci Flutter ile, monorepo içindeki `/mobile` dizininde geliştirilecektir.
- Production bundle ID hedefi `com.emsalist.app` olacaktır.
- Backend FastAPI ve PostgreSQL üzerinde devam eder.
- Ana deneyim chat-first olacaktır.
- Varsayılan tema `ThemeMode.system`; manuel açık/koyu geçişi ayarlarda bulunur.
- Üst çubukta kalıcı güneş/ay simgesi bulunmaz.
- UYAP durumu kompakt bir ikonla gösterilir; yeni hareketler rozetle işaretlenir.
- Kullanıcı her zaman bir workspace içinde çalışır; bireysel kullanıcıya personal workspace oluşturulur.
- İlk beta belge sınırı 25 MB, soft-delete süresi 30 gündür.
- UDF yalnız backend sandbox parser ile işlenir.
- İlk uçtan uca pilot `ayıplı araç / tüketici hukuku` dosyasıdır.
- Kapalı beta 15 avukatla ve ücretsiz yürütülür.
- Android ana yayın hedefi P2 beta sonrasıdır.
- P2.0 yalnızca planlama ve sözleşme aşamasıdır.

## 4. Mimari sıralama ilkesi

Aşamalar şu bağımlılık sırasıyla uygulanır:

1. Mobil kabuk ve istemci mimarisi
2. Kimlik, oturum ve yetki
3. Dosya ve konuşma modeli
4. Yapılandırılmış dosya hafızası
5. Belge işleme hattı
6. Güvenilir hukuk kaynağı omurgası
7. Hibrit arama
8. Hukuki mesele ve delil grafiği
9. Kaynak bağlantılı dilekçe üretimi
10. UYAP Bridge ve bildirimler
11. Beta ve App Store hazırlığı

Semantik arama, otomasyon veya UYAP genişletmesi; kaynak doğrulama ve dosya izolasyonu tamamlanmadan öne alınamaz.

## 5. P2 aşamaları

### P2.0 — Ürün ve mimari planlama

Çıktılar:

- ürün kapsamı
- kullanıcı ve dosya akışları
- mobil bilgi mimarisi
- konuşma tasarımı
- mobil mimari
- veri modeli
- API sözleşmesi
- güvenlik ve gizlilik modeli
- case memory ve document pipeline
- source/search/reasoning/drafting mimarisi
- UYAP ve notification sınırları
- test, observability, risk ve release stratejisi
- kabul matrisi
- backlog ve bağımlılık haritası

Kapanış kapısı:

- açık kritik ürün kararı kalmaması
- kapsam içi/dışı maddelerin onaylanması
- pilot senaryonun ölçülebilir kabul kriterlerinin yazılması
- Flutter ve backend sorumluluk sınırlarının belirlenmesi
- final consistency review tamamlanması

### P2.1 — Mobil uygulama kabuğu

Kapsam:

- `/mobile` Flutter proje başlangıcı
- development/staging/production flavor temeli
- iOS-first tasarım sistemi
- otomatik/açık/koyu tema
- ana sohbet ekranı
- dosya drawer'ı
- alt mesaj oluşturucu
- UYAP durum ikonu ve mock bottom sheet
- ayarlar ve görünüm menüsü
- bağlantı, boş durum ve hata ekranları
- mobil CI ve widget/golden test altyapısı

Kapanış kapısı:

- küçük iPhone ekranında taşma olmaması
- klavye ve safe-area davranışının doğru olması
- tema geçişlerinin test edilmesi
- erişilebilir etiketlerin bulunması
- mock veriyle temel navigasyonun çalışması
- iOS simulator build'in CI'da geçmesi

### P2.2 — Mobil API temeli, kimlik, oturum ve büro bağlamı

P2.2 iki alt dilime ayrılır. P2.2A önce uygulanır ve P2.2B'yi etkinleştiren
altyapıyı sağlar. Faz numaralandırması değişmez; her alt dilim ayrı PR ve ayrı
kabul kapısına sahiptir.

#### P2.2A — Mobil API temeli

Kapsam:

- flavor'a duyarlı API yapılandırması (development/staging/production)
- ortam ve base URL için dart-define (`APP_ENVIRONMENT`, `API_BASE_URL`)
- production-grade Dio API client (timeout, interceptor'lar)
- `X-Correlation-ID` üretimi ve backend `correlation_id` okuma
- merkezî, typed hata eşleme (backend error envelope → domain exception)
- yalnız GET için dayanıklı retry politikası (max 2, sınırlı statü kümesi)
- güvenli loglama (production'da gövde yok; hassas header'lar hiçbir ortamda loglanmaz)
- DTO serialization (json_serializable) — yalnız seçili sistem endpoint'leri
- repository katmanı; UI doğrudan HTTP çağırmaz
- en az bir gerçek read-only endpoint entegrasyonu: `GET /api/v1/meta/version`, `GET /health`
- Sistem Durumu UI (app bar overflow menüsünden; kalıcı badge yok)
- yalnız development flavor için localhost cleartext yapılandırması

Kapsam dışı (P2.2B'ye bırakılır):

- kimlik/giriş, token yaşam döngüsü, güvenli depolama, workspace, oturumlar
- case/message/UYAP mock akışlarının gerçek backend'e bağlanması
- tam OpenAPI mobile client codegen

Kapanış kapısı:

- staging/production'da `API_BASE_URL` yoksa network çağrısı yapılmaz (fail-closed)
- token/PII/hassas header hiçbir ortamda loglanmaz
- yazma işlemleri otomatik retry edilmez
- mevcut P2.1 mock akışları ve testleri bozulmaz
- generated DTO drift'i CI'da yakalanır

#### P2.2B — Kimlik, oturum ve büro bağlamı

P2.2B iki alt dilime ayrılır. P2.2B1 backend auth contract stabilizasyonunu
sağlar; P2.2B2 mobil auth, session ve workspace UI'ını getirir.

##### P2.2B1 — Backend Auth Contract Stabilization

Kapsam:

- User ORM model senkronizasyonu (password_hash, failed_login_count,
  locked_until, token_version, last_login_at, password_changed_at)
- Alembic migration (missing auth columns)
- Login response'da refresh_token dönüşü (gerçek token, `refresh_expires_in`)
- Refresh request body modeli (body'den okuma, cookie fallback)
- Refresh rotation sonrası yeni refresh token dönüşü
- Change-password implementasyonu (501 kaldır, token_version artır)
- Login rate limiter bağlantısı
- Production AUTH_MODE=jwt zorunluluğu
- Auth enpoint'lerinde güvenli loglama (password/token redaction)
- Backend auth testleri (unit, PostgreSQL integration, contract, migration)
- OpenAPI snapshot güncellemesi

Kapanış kapısı:

- refresh token body'den okunur, cookie fallback uyumlu
- eski refresh token reuse'u tüm token family'yi revoke eder
- login rate limit ve account lock çalışır
- change-password eski token'ları geçersiz kılar
- production AUTH_MODE=jwt olmadan başlamaz
- password/token hiçbir log'da görünmez

##### P2.2B2 — Mobile Auth & Session

P2.2B2 üç alt dilime ayrılır:

- **P2.2B2A — Apple Auth Backend & Account Linking** (backend-only)
- **P2.2B2B-A — Mobile auth foundation & secure session** (mobil auth altyapısı,
  secure storage, refresh rotation, router guard, login/link UI, Apple provider
  soyutlaması)
- **P2.2B2B-B — Native Apple Sign-In activation** (concrete native binding, iOS
  capability ve gerçek Apple yapılandırması)

###### P2.2B2A — Apple Auth Backend & Account Linking

Durum: ✅ Completed — PR #10 `main`'e merge edildi (merge commit `87e07ed`).

Kapsam (yalnız backend):

- Ürün kararı: kullanıcıdan **büro kodu / tenant / tenant_slug / workspace
  alınmaz.** Ana yöntem Apple ile Devam Et; yedek e-posta + şifre.
- Apple authorization-code exchange (ES256 client secret), Apple ID token +
  nonce doğrulama (RS256, JWKS cache, unknown-kid refresh).
- Apple `sub` gizliliği: HMAC-SHA256(pepper, "apple|aud|sub") hex digest.
- E-posta + şifre ile **mevcut** hesabı bağlama; Apple link request yalnız
  `link_ticket + email + password` içerir; tenant `User.tenant_id` üzerinden
  backend tarafından çözülür.
- **Email-only account resolution**: tenant_slug gönderilmezse aktif kullanıcı
  araması; duplicate e-postada **otomatik seçim yapılmaz** → generic
  `invalid_credentials`. `tenant_slug` yalnız geriye uyumlu, opsiyonel backend
  alanıdır; mobil UI göndermez.
- Canonical `tenant.id` düzeltmesi (slug hiçbir zaman tenant ID gibi
  kullanılmaz).
- AuthIdentity + AuthLinkTicket tabloları ve tek Alembic revision.
- Standart access/refresh session issuance ortak helper ile yeniden kullanılır;
  refresh rotation + reuse detection + token_version korunur.
- Endpoint'ler: `/auth/apple/login`, `/auth/apple/link`, `/auth/apple/status`,
  `/auth/apple/unlink`. `APPLE_SIGN_IN_ENABLED=false` iken 503
  `apple_sign_in_unavailable`.
- Audit + redaction, migration, test, OpenAPI, dokümantasyon.

Kapsam dışı (P2.2B2B'ye bırakılır): mobil ekranlar, `sign_in_with_apple`, Apple
native butonu, cihazda nonce üretimi, flutter_secure_storage, access token
memory store, refresh token Keychain, AuthInterceptor, single-flight refresh
interceptor, Riverpod AuthStateNotifier, startup session restore, GoRouter auth
redirect, giriş/ilk bağlama/oturum sona erdi/Hesap ekranları, iOS entitlement ve
Xcode capability, gerçek Apple Developer yapılandırması, cihaz/TestFlight E2E.

###### P2.2B2B-A — Mobile auth foundation & secure session

Durum: ✅ Completed — PR #11 (`feat/p2.2-apple-auth-mobile`) `main`'e merge edildi
(merge commit `07da93f`). Bu dilim mobil auth altyapısını ve güvenli oturumu
tamamlar; native Apple aktivasyonu **P2.2B2B-B** olarak ayrı izlenir. Production
uygulamada Apple butonu, concrete native provider gelene kadar gizlidir; bu
dilim P2.2B2B'nin tamamını kapatmaz.

Tamamlanan kapsam:

- Secure token storage (flutter_secure_storage / iOS Keychain; SharedPreferences
  kullanılmaz)
- App startup session restore
- Refresh-token rotation (yeni refresh token eski değerin yerine atomik yazılır)
- Single-flight refresh (paralel 401'ler tek rotasyonda birleşir)
- Authenticated request retry (401 → refresh → tek retry, döngü yok)
- Refresh failure logout (başarısız refresh tüm oturumu temizler → login)
- Auth state management (Riverpod `AuthController` / `StateNotifier`)
- GoRouter auth guards (redirect + refreshListenable; splash/login/shell)
- Email/password login akışı
- Apple login/link DTO, repository ve state seam'leri (discriminated union:
  authenticated / link_required)
- Hesap bağlama (account link) UI (email + mevcut şifre; büro kodu yok)
- Apple status/unlink UI ve repository desteği (parola doğrulamalı, idempotent)
- Token redaction (token'lar loglanmaz; `AuthSession.toString` ve
  Authorization header redaksiyonu)
- Otomatik testler (session manager, refresh interceptor, repository, controller,
  router guard, secure store, nonce, redaction) ve mevcut testlerin korunması

Kapanış kapısı:

- token flutter_secure_storage'da saklanır, loglanmaz
- 401 → single-flight refresh → retry, döngü oluşmaz
- refresh başarısızsa atomik temizlik + login sayfası
- UI doğrudan Dio / secure storage kullanmaz
- mevcut mobile testleri korunur
- flutter analyze/test, dart format, build_runner drift ve iOS simulator build
  yeşil

###### P2.2B2B-B — Native Apple Sign-In activation

Durum: ⏳ Not started — ayrı izlenen uygulama dilimi.

Kalan kapsam:

- `sign_in_with_apple` package entegrasyonu
- Concrete `AppleCredentialProvider` implementasyonu (raw nonce → SHA-256 → Apple
  credential)
- Xcode Signing & Capabilities wiring (Sign in with Apple capability)
- `Runner.pbxproj` entitlement ilişkilendirmesi
  (`CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements`)
- Apple Developer App ID capability (3 flavor App ID'si)
- Bundle ID, Team ID ve Service ID/Key yapılandırması
- Fiziksel cihazda Apple login
- Cancelled / authorized / error native credential testleri
- TestFlight uçtan uca doğrulama
- Apple butonunun etkinleştirilmesi (provider available olduğunda görünür)

Kapanış kapısı:

- gerçek cihazda Apple ile giriş, ilk bağlama, oturum geri yükleme ve unlink
  çalışır
- native cancel/authorized/error yolları test edilir
- Apple butonu production yapılandırmada etkinleşir

#### P2.2C — Case & Chat (formerly P2.3)

### P2.3 — Dosya ve konuşma

Durum: ✅ Completed — PR #12 `main`'e merge edildi (merge commit `eed3cd2`).
Backend case CRUD + arşiv/geri yükleme + soft delete ve conversation/message
kalıcılığı (idempotent mesaj, tenant/owner izolasyonu, IDOR koruması) ile mobil
dosya listesi ve dosya-bazlı sohbet ekranları tamamlandı.

Kapsam:

- dosya oluşturma, listeleme, arşivleme ve silme talebi
- aktif dosya seçimi
- konuşma ve mesaj kalıcılığı
- mesaj durumları
- tekrar deneme ve idempotency
- sınırlı şifreli offline cache

Kapanış kapısı:

- dosyalar arası veri karışmaması
- mesaj tekrar denemesinde çift kayıt oluşmaması
- ağ kesintisinde kullanıcıya açık durum gösterilmesi

### P2.4 — Yapılandırılmış dosya hafızası

Durum: ✅ Completed — PR #13 `main`'e merge edildi (merge commit `abae18d`).
DB-backed CaseFact, TimelineEvent, MissingInformation, Contradiction, Risk
(+ Claim/Defense/Evidence/Deadline tabloları) doğrulama statüleri, deterministic
çelişki tespiti, somut-değer bazlı eksik-bilgi tamamlama, risk kuralları,
optimistic locking (version/409) ve mobil dosya hafızası ekranı ile tamamlandı.

Ertelenen kapsam (deferred): **Claim, Defense, Evidence ve Deadline** veri
modeli + ORM tabloları + migration olarak hazırdır; ancak bunlara ait
**dedicated CRUD endpoint'leri ve mobil kullanıcı akışları bu dilimde yer
almaz** ve bilinçli olarak sonraki dilime bırakılmıştır (şema hazır, kırıcı
migration gerektirmez). Fact, timeline, missing-information, contradiction ve
risk tam olarak (API + mobil) uygulanmıştır.

Temel varlıklar:

- CaseParty
- CaseFact
- TimelineEvent
- Claim
- Defense
- Evidence
- MissingInformation
- Contradiction
- Risk
- Deadline
- LegalIssue

Kapanış kapısı:

- kullanıcı beyanı, belge ve UYAP kaynağının ayrıştırılması
- çelişkili değerlerin kesin bilgiye dönüşmemesi
- kritik eksikler tamamlanmadan genel riskin düşük gösterilmemesi

### P2.5 — Belge işleme hattı

Durum: ✅ Completed — PR #14 `main`'e merge edildi (merge commit `b86bf18`).
Canonical DB Document + DocumentPage + DocumentExtraction; güvenli upload
(magic-byte/MIME doğrulama, path traversal koruması, server-generated storage
key), SHA-256 duplicate (aynı case 409, cross-tenant non-disclosure), durum
makinesi, gerçek parser tabanlı metin/sayfa çıkarımı, deterministic extraction
provenance ve P2.4 memory entegrasyonu (confirm → document_verified CaseFact +
çelişki motoru) ile tamamlandı.

Bilinen kapsam sınırları (kabul bloğu değil):

- **Native mobile file picker yok**: mobil upload akışı şimdilik in-app metin
  belgesi ile uçtan uca çalışır; gerçek PDF/DOCX/UDF/görsel seçimi bir seam
  üzerinden sonraki dilime bırakılmıştır (deferred mobil entegrasyon borcu).
- **OCR yok**: JPG/JPEG/PNG `upload_only`; görsel belgeler OCR yapılmış gibi
  gösterilmez.
- **Senkron analiz**: metin çıkarımı upload isteği içinde yürütülür; arka plan
  job kuyruğu ileri sürümdedir.
- **UDF yalnız okunabilir-XML arşivi**: gerçek ikili UDF `unsupported` döner;
  içerik uydurulmaz.
- Chunked upload, virüs tarayıcı, signed-URL object storage ve
  DocumentAnalysisRun sürümleme kapsam dışıdır.
  Gerçek format destek matrisi ve rollback: `P2_DOCUMENT_PIPELINE.md §19`.

Formatlar:

- PDF, UDF, DOCX, TXT, JPG, JPEG, PNG

Akış:

- tür ve boyut kontrolü
- zararlı içerik kontrolü
- hash ve tekrar belge kontrolü
- güvenli depolama
- metin çıkarma
- sayfa/paragraf konumlandırma
- belge türü tespiti
- bilgi çıkarımı
- kullanıcı onayı

Kapanış kapısı:

- çıkarılan her bilginin belge konumuna bağlanması
- okunamayan ve eksik sayfaların işaretlenmesi
- aynı belgenin tekrar yüklenmesinin yönetilmesi

### P2.6 — Güvenilir hukuk kaynağı omurgası

Durum: ✅ Completed — PR #15 `main`'e merge edildi (merge commit `523cb66`).

Canonical, DB-backed güvenilir hukuk kaynağı omurgası uygulandı. P2.6; embedding
üretimi, semantik sıralama veya arama motoru **içermez** — yalnız P2.7'nin
tüketeceği bir index-eligibility policy seam sağlar.

Uygulanan davranış:

- canonical `SourceRecord` / `SourceVersion` / `SourceParagraph` modeli
- `SourceVerification` / `SourceRelationship` / `SourceUsage` modeli
- deterministic canonical key engine (Türkçe-duyarlı NFKC/casefold + E./K. +
  tarih normalizasyonu)
- source version korunması (eski sürüm `superseded` ama silinmez)
- `editor_submit` her zaman `needs_review` başlar
- resmî URL tek başına kanıt değildir
- `verified_official` yalnız o `SourceVersion`'a bağlı `official_fetch_match`
  kanıtıyla verilir
- resmî güven yalnız sunucunun kendi fetch ettiği byte'lardan türetilir
- `evidence_hash` = `SourceVersion.content_hash`
- değişen sürüm eski sürümün güvenini miras almaz
- aynı-hash resmî fetch mevcut sürümü `duplicate_verified` ile doğrular; yeni
  `SourceVersion` yaratmaz
- effective current-version trust resolver
- `SourceUsage` kesin `source_version_id` provenance'ı
- `SourceUsage` için paragraf opsiyoneldir
- effective trust `SourceRecord` / Official Tracking / Source Review üzerinde
  tutarlı gösterilir
- global source mutation editor/admin sınırı (`require_editor`)
- `tenant_admin` hariç tutulur (global source editor değildir)
- JWT 4-rol × 4-aksiyon request-level authorization matrix (gerçek seed'lenmiş
  DB kimlikleriyle)
- PostgreSQL audit FK integrity (`audit_events_tenant_id_fkey` korunur)
- SSRF-fail-closed güvenli source fetcher
- P2.7-tüketilebilir `index_eligibility` saf policy seam

Kaynaklar:

- mevzuat
- Resmî Gazete
- Yargıtay
- Danıştay
- Anayasa Mahkemesi
- Uyuşmazlık Mahkemesi
- doğrulanmış ikincil kaynaklar
- kontrollü doktrin

Bilinen sınırlar / ertelenen kapsam (kabul bloğu değil):

- canlı zamanlanmış sağlayıcı ingestion'ı henüz canonical ingestion'a bağlı
  değildir; güvenli fetch / resmî ingestion servis seam'i mevcuttur
- mobil editor/review UI uygulanmadı (backend API only)
- semantik arama / embedding / ranking P2.7'dir
- hukuki mesele grafiği P2.8'dir
- kaynaklı dilekçe üretimi P2.9'dur
- `affected_draft_count`, dilekçe üretimi var olana kadar unsupported kalır
- native mobil dosya seçici borcu P2.5/mobil entegrasyona aittir, P2.6'ya değil

Kapanış kanıtı:

- Feature acceptance head: `521481f` (aşağıdaki CI kanıtları bu head'te alındı)
- Post-merge main closure: PR #15 normal merge commit `523cb66` (`main`)
- Migration: `ce94808703a4`, tek head, zero drift, downgrade/upgrade round-trip temiz
- Backend PostgreSQL: 1270 passed, 0 skipped, 0 failed
- Source backbone: 30 service testi, 38 route testi
- OpenAPI: drift temiz, 159 benzersiz v1 operation ID
- Mobil: kaynağa özel 14 test yeşil; Mobile CI yeşil
- Feature acceptance head `521481f` gerekli CI:
  - Security Scanning — run `29207647138` — completed / success
  - Config and Migration Audit — run `29207647082` — completed / success
  - Mobile CI — run `29207647044` — completed / success
  - P1.14 Final Acceptance — run `29207647050` — completed / success

Kapanış kapısı:

- doğrulanmamış / editor-submitted içerik `verified_official` görünemez
- tekrar canonical kaynak/sürüm davranışı deterministic'tir (silent overwrite yok)
- kesin source version ve paragraf provenance'ı korunur
- tarihsel `SourceUsage` güveni güncel `SourceRecord` güvenini miras alamaz
- effective current-version trust tutarlı gösterilir
- JWT modda global source mutation'ları editor/admin ile sınırlıdır
- PostgreSQL-backed final acceptance yeşildir

### P2.6C — Çoklu sağlayıcı resmî hukuk kaynağı ingestion

Durum: ⏳ Draft PR — bağımsız sağlayıcı adaptörleri, ingestion run modeli, editor/admin
API ve CLI tamamlandı. P2.7'den önce merge edilmesi gerekir.

Altı resmî Türk hukuk kaynağı sağlayıcısını (Yargıtay, Danıştay, AYM, Uyuşmazlık
Mahkemesi, Mevzuat, Resmî Gazete) P2.6 kanonik ingestion hattına bağlar.
Sağlayıcı adaptörleri asla doğrudan canonical yazma veya trust üretimi yapmaz;
tüm kanonik ingestion `ingest_official_fetch` üzerinden ve SSRF-doğrulanmış
taşıyıcı ile gerçekleşir.

Ayrıntılı sağlayıcı destek matrisi ve tasarım:
`docs/p2/P2_OFFICIAL_PROVIDER_INGESTION.md`.

### P2.7 — Hibrit hukuk araması

Arama sinyalleri:

- anahtar kelime
- tam metin
- semantik benzerlik
- mahkeme otoritesi
- karar tarihi
- doğrulama statüsü
- dosya olayına uyum
- hukuki mesele uyumu
- sonuç yönü
- tekrar kayıt cezası

Kapanış kapısı:

- benchmark setinde ilk 3 ve ilk 10 başarı oranlarının ölçülmesi
- karşıt kararların ayrı işaretlenmesi
- alakasız teknik kaynakların normal kullanıcıya gösterilmemesi

### P2.8 — Hukuki mesele ve delil grafiği

Bağlantılar:

- mesele ↔ olay
- mesele ↔ delil
- mesele ↔ eksik bilgi
- mesele ↔ risk
- mesele ↔ mevzuat/içtihat
- mesele ↔ karşı argüman
- mesele ↔ dilekçe paragrafı

Kapanış kapısı:

- her ana iddianın delil ve kaynak durumunun görülebilmesi
- ispat yükü ve karşı argümanın kayıt altına alınması

### P2.9 — Kaynak bağlantılı dilekçe

Akış:

- dosya yeterlilik kontrolü
- eksik ve çelişki kontrolü
- hukuki mesele ve talep seçimi
- kaynak ve delil eşleştirme
- taslak planı
- bölüm/paragraf üretimi
- kaynak doğrulama
- avukat incelemesi
- DOCX/PDF dışa aktarma

Kapanış kapısı:

- her önemli paragrafın olay, delil ve kaynak metadata'sına bağlanması
- doğrulanmamış emsal numarası bulunmaması
- sonuç/talep ile açıklamalar arasında tutarlılık kontrolü

### P2.10 — UYAP Bridge ve bildirimler

İlk sürüm kapsamı:

- bağlantı durumu
- son kontrol zamanı
- dosya numarası eşleştirme
- manuel evrak ekleme
- yeni hareket rozeti
- hareket kartı
- evrakı dosyaya bağlama
- notification outbox ve güvenli push payload

İlk sürüm kapsam dışı:

- kullanıcı adına otomatik evrak gönderme
- e-imza
- otomatik dava açma

Kapanış kapısı:

- UYAP parolası veya token'ının loglanmaması
- entegrasyonun kapatılabilir olması
- bağlantı durumunun renk dışında ikon/metinle açıklanması
- bildirim payload'ında hassas içerik bulunmaması

### P2.11 — Beta ve App Store hazırlığı

Kapsam:

- 15 avukatlık kapalı beta
- crash/performance takibi
- gerçek dosya ve büyük belge testleri
- gizlilik metinleri
- hesap ve veri silme akışları
- App Store metadata ve ekran görüntüleri

Kapanış kapısı:

- kritik güvenlik açığı olmaması
- kaynak uydurma testlerinin geçmesi
- veri silme ve hesap kapatma sürecinin doğrulanması
- pilot dosya akışının uçtan uca tamamlanması
- veri bölgesi/aktarım hukuk incelemesinin tamamlanması

## 6. Pilot: Ayıplı araç dosyası

Pilot veri alanları:

- satın alma tarihi
- satış bedeli
- satıcı ve alıcı
- marka/model/plaka/şasi
- ayıp türü ve ilk görülme tarihi
- servis kayıtları
- bilirkişi/ekspertiz raporu
- TRAMER bilgisi
- ayıp ihbarı ve noter ihtarı
- seçimlik hak
- zarar kalemleri
- görev/yetki ve süre riskleri

Pilot başarı kriteri:

- eksik alanların somut değer bazında tespit edilmesi
- iki kaynak arasındaki tarih/tutar/araç bilgisi çelişkisinin gösterilmesi
- en az bir doğrulanmış mevzuat ve bir doğrulanmış içtihat kaynağının ilgili iddiaya bağlanması
- kaynaklı taslağın DOCX olarak dışa aktarılması

## 7. Branch ve PR stratejisi

- `chore/p2.0-planning-baseline`
- `feat/p2.1-mobile-shell`
- `feat/p2.2-api-foundation` (P2.2A)
- `feat/p2.2-auth-backend` (P2.2B1)
- `feat/p2.2-apple-auth-backend` (P2.2B2A)
- `feat/p2.2-apple-auth-mobile` (P2.2B2B-A)
- `feat/p2.2-apple-native` (P2.2B2B-B)
- `feat/p2.2c-case-chat` (P2.2C)
- `feat/p2.4-case-memory`
- `feat/p2.5-document-pipeline`
- `feat/p2.6-source-backbone`
- `feat/p2.6c-official-provider-ingestion`
- `feat/p2.7-hybrid-search`
- `feat/p2.8-legal-issue-graph`
- `feat/p2.9-grounded-drafting`
- `feat/p2.10-uyap-bridge`

Her aşama ayrı PR ve ayrı kabul kapısına sahiptir. `main` dalına doğrudan push yapılmaz.

## 8. Definition of Done

Bir P2 PR'ı ancak aşağıdakiler tamamlandığında kapanabilir:

- kapsam ve kabul kriteri karşılandı
- unit/integration/widget testleri geçti
- API ve veri modeli dokümanı güncel
- migration doğrulandı
- OpenAPI drift yok
- güvenlik ve tenant izolasyonu kontrolleri geçti
- hata/boş/yükleniyor durumları işlendi
- erişilebilirlik kontrolü yapıldı
- bilinen risk ve rollback yöntemi yazıldı
- main CI tamamen yeşil

## 9. P2.0 karar durumu

Kritik başlangıç kararları `P2_DECISION_REGISTER.md` içinde kabul edilmiştir. P2.1'e bırakılan state management, router, local encrypted database, crash analytics ve sağlayıcı seçimleri uygulama düzeyi ADR/spike konularıdır; P2.0 kapsam eksikliği değildir.

## 10. P2.0 kapanış çıktısı

P2.0 paketi; bütün plan belgelerini, karar kaydını, kabul matrisini, risk kaydını, final consistency review ve uygulanabilir backlog'u içerir. PR onaylanıp merge edilmeden ürün kodu geliştirmesi başlamaz.
