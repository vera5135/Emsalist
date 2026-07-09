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

Kapsam:

- flutter_secure_storage ile token saklama (SharedPreferences kullanılmaz)
- AuthInterceptor (Bearer token inject)
- TokenRefreshInterceptor (single-flight 401 → refresh → retry)
- AuthApi / AuthRepository / SessionRepository
- AuthStateNotifier (Riverpod)
- App startup session restore
- GoRouter redirect guard (unauthorized → login)
- Login screen (email + password)
- Workspace selection screen
- Session expired UI
- Settings'te "Hesap" ekranı / logout
- Mevcut 87 test korunur

Kapanış kapısı:

- token flutter_secure_storage'da saklanır, loglanmaz
- 401 → single-flight refresh → retry, döngü oluşmaz
- refresh başarısızsa atomik temizlik + login sayfası
- UI doğrudan Dio / secure storage kullanmaz
- mevcut mobile testleri korunur

#### P2.2C — Case & Chat (formerly P2.3)

### P2.3 — Dosya ve konuşma

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

Kaynaklar:

- mevzuat
- Resmî Gazete
- Yargıtay
- Danıştay
- Anayasa Mahkemesi
- Uyuşmazlık Mahkemesi
- doğrulanmış ikincil kaynaklar
- kontrollü doktrin

Kapanış kapısı:

- doğrulanmamış kaynağın doğrulanmış görünmemesi
- tekrar kararların canonical key ile birleştirilmesi
- kullanılan kaynağın dosya ve dilekçe bağlamında izlenmesi
- citation'ın deterministic renderer ile üretilmesi

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
- `feat/p2.2-auth-session` (P2.2B2)
- `feat/p2.2c-case-chat` (P2.2C)
- `feat/p2.4-case-memory`
- `feat/p2.5-document-pipeline`
- `feat/p2.6-source-backbone`
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
