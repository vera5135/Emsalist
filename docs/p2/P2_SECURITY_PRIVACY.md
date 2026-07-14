# P2 Security and Privacy Baseline

## 1. Amaç

Bu belge P2 boyunca uygulanacak güvenlik, gizlilik, veri minimizasyonu, erişim kontrolü ve kayıt politikalarını tanımlar. Ürün; avukat-müvekkil gizliliği, hassas kişisel veri, UYAP verisi ve hukuk dosyası içerikleri taşıyabileceği için varsayılan yaklaşım `private by default` olur.

## 2. Güvenlik hedefleri

- Tenant ve case izolasyonu
- Yetkisiz dosya erişiminin engellenmesi
- Token, parola ve credential sızıntısının önlenmesi
- Belge ve mesaj içeriğinin loglardan uzak tutulması
- Güvenli belge işleme
- Kaynak ve prompt injection savunması
- İzlenebilir fakat içerik-minimum audit
- Güvenli silme ve retention
- Mobil cihaz kaybı senaryosuna dayanıklılık

## 3. Veri sınıfları

### Çok hassas

- UYAP parola/token/cookie
- kimlik numarası ve kimlik belgesi
- sağlık verisi
- ceza dosyası içeriği
- çocuk verisi
- banka/ödeme bilgisi
- ticari sır

### Hassas

- dosya belgeleri
- dilekçe ve mesaj tam metni
- müvekkil iletişim bilgileri
- dosya stratejisi
- iç notlar

### Kontrollü metadata

- tenant/case ID
- işlem türü
- hata kodu
- durum
- süre ve performans
- kaynak ID

## 4. Kimlik doğrulama

İlk sürüm:

- e-posta + parola
- e-posta doğrulama
- access/refresh token
- güvenli parola sıfırlama
- cihaz oturum listesi
- oturum iptali

Beta öncesi:

- Apple ile giriş
- opsiyonel MFA

Parola kuralları server-side uygulanır; parola hiçbir log veya analytics olayına girmez.

## 5. Yetkilendirme

Kontrol katmanları:

1. authenticated user
2. workspace membership
3. workspace role/permission
4. case membership
5. object-level permission
6. action-specific policy

Tenant ID request body'den güvenilir kabul edilmez.

Admin kullanıcıları varsayılan olarak dosya içeriğine erişemez. Break-glass erişim ayrı onay, gerekçe, süre ve audit gerektirir.

## 6. Mobil güvenlik

- Refresh token platform secure storage içinde
- Access token kısa ömürlü
- Hassas token normal preferences içine yazılmaz
- Ekran görüntüsü engelleme yalnız çok hassas ekranlarda değerlendirilir
- Clipboard hassas içerik için süreli temizleme seçeneği
- Jailbreak/root sinyali uyarı ve risk telemetrisi üretir; tek başına veri kaybına yol açmaz
- Yerel cache şifreli olur
- Belge bytes varsayılan kalıcı offline cache'e alınmaz
- Uygulama background snapshot'ında hassas içerik maskelenir

## 7. Ağ güvenliği

- TLS zorunlu
- Sertifika doğrulama
- Production endpoint allowlist
- Debug proxy ayarları production build'de kapalı
- Signed URL kısa süreli
- Upload/download authorization her işlemde

Certificate pinning risk/operasyon maliyeti nedeniyle P2.1'de zorunlu değildir; threat model sonrası değerlendirilir.

## 8. Sunucu ve veri tabanı

- Non-root container
- Read-only filesystem mümkün olan servislerde
- Secret manager
- Şifreli disk/object storage
- DB bağlantı secret'ı repo dışında
- Least privilege DB rolleri
- Backup şifreleme ve restore testleri
- Migration ve backup CI kapıları korunur

## 9. Loglama

Loglanmaz:

- mesaj tam metni
- belge tam metni
- dilekçe tam metni
- parola/token/API key
- TC kimlik numarası
- UYAP credential
- signed URL

Loglanabilir:

- request_id
- hashed user/workspace reference
- case_id opaque reference
- action type
- duration
- result
- safe error code
- model/provider adı
- token count
- source count

## 10. Audit

Audit olayları:

- giriş/çıkış/oturum iptali
- workspace üyelik değişikliği
- case erişimi ve rol değişikliği
- belge upload/delete/export
- fact confirm/reject
- contradiction resolve
- draft approve/export
- UYAP connect/disconnect/sync
- data export/delete request

Audit metadata içerik değil işlem bağlamı taşır.

## 11. Veri minimizasyonu

- Model sağlayıcısına yalnız gerekli case context gönderilir.
- Tam dosya yerine ilgili paragraf/fact seçilir.
- Arama sorgularında gereksiz kimlik verisi kaldırılır.
- Analytics olayları içerik taşımaz.
- Push notification body hassas ayrıntı içermez.

## 12. Yapay zekâ sağlayıcı güvenliği

- Provider abstraction
- Veri kullanım politikası konfigüre edilebilir
- Model çağrısı tenant/case request_id ile izlenir
- Prompt ve response varsayılan olarak full loglanmaz
- Provider timeout, retry ve fail-closed kuralları
- Hassas alan redaction
- Eğitim amacıyla kullanım varsayılan olarak kapalı sözleşme/politika hedefi

## 13. Prompt injection

- Belge ve kaynak metni talimat değil veridir.
- Tool çağrıları allowlist ve schema kontrollüdür.
- Model tenant/case dışı veri isteyemez.
- URL fetch SSRF korumalıdır.
- Citation yalnız source ID üzerinden oluşturulur.
- Belge içindeki komutlar çalıştırılmaz.

## 14. Dosya güvenliği

- MIME/magic byte kontrolü
- antivirus/malware scan
- PDF active content kontrolü
- sandbox parser
- path traversal engeli
- size/page/object limit
- quarantine
- duplicate hash

## 15. KVKK ve gizlilik operasyonu

Teknik tasarım şu kabiliyetleri destekler:

- aydınlatma ve açık rıza/işleme dayanağı kayıtları gerektiğinde
- kullanıcı veri erişim/export talebi
- düzeltme talebi
- hesap kapatma
- silme talebi
- retention ve legal hold
- alt işleyen/provider kaydı
- veri ihlali müdahale süreci

Hukuki metinler beta öncesi uzman incelemesinden geçirilir.

## 16. Veri yerleşimi kararı

P2 başlangıç kararı:

- primary workload: AB/AEA bölgesinde kontrollü cloud
- production beta öncesi Türkiye içi barındırma seçeneği ve veri aktarım analizi tamamlanır
- backup bölgesi primary ile aynı hukuk/kontrat politikasına tabi olur
- region bilgisi Workspace metadata'sında tutulur

## 17. Retention

Önerilen varsayılanlar:

- soft delete: 30 gün
- audit: uzun süreli, içeriksiz
- operational logs: kısa süreli
- export artifacts: kullanıcı ayarlı veya sınırlı süre
- failed upload temp files: saatler içinde purge
- legal hold: purge engeli

Kesin süreler hukuk ve sözleşme incelemesiyle onaylanır.

## 18. Olay müdahalesi

- incident severity
- containment
- credential rotation
- affected tenant determination
- audit preservation
- user/legal notification decision
- postmortem
- regression test

Runbook beta öncesi hazırlanır.

## 19. Güvenlik testleri

- IDOR/object authorization
- tenant leakage
- role escalation
- token replay
- refresh rotation
- path traversal
- malicious file
- zip bomb
- SSRF
- prompt injection
- source poisoning
- log leakage
- signed URL abuse
- rate limit
- deletion/legal hold bypass

## 20. P2.7 Arama gizliliği

### 20.1 Sorgu hash

- `query_hash` = HMAC-SHA256(domain_separator=`"emsalist-query-hash|v1"`, message=`"tenant_id:space_separated_positive_clauses"`)
- Domain separation, farklı HMAC kullanım alanları arasında çakışmayı önler
- Düz SHA-256 kullanılmaz; hmac modülü ve sabit zamanlı `compare_digest` kullanılır
- `query_hash` yalnız `SearchQuery` tablosunda saklanır; çıkarıma dayanıklıdır (ham metin geri elde edilemez)

### 20.2 Ham sorgu saklanmaz

- `SearchQuery.raw_query_transient` yalnız geçici `SearchQueryPlan` nesnesinde bulunur; DB'ye yazılmaz
- `SearchQuery` tablosunda: `query_hash` + `safe_query_summary` + `filters_json` + `index_version` dışında sorguya dair hiçbir alan yoktur
- `safe_query_summary` = `SearchQueryPlan.safe_summary()` → yalnız yapısal sayılar (optional_clause_count, required_clause_count, excluded_clause_count, exact_citation_candidates count, article_candidates count). Operatör metni veya normalize edilmiş sorgu metni içermez.

### 20.3 Hassas sorgu koruması

`is_sensitive_query()` aşağıdaki desenleri ilk 200 karakterde tarar:
- TC kimlik numarası (11 haneli)
- IBAN (TR ile başlayan)
- E-posta adresi
- Türkiye telefon numarası
- 32+ karakter alfanumerik token

Hassas sorgu tespit edilirse:
- Semantik retrieval (embedding API çağrısı) atlanır
- `degraded_mode=true` dönülür
- Lexical-only sonuçlar döner
- Sorgu metni hiçbir harici servise gönderilmez

### 20.4 Cursor ve result ID güvenliği

- Cursor payload'ı: `query_id`, `query_hash_binding`, `filter_hash`, `index_version`, `last_sort_key`. Ham sorgu metni içermez.
- Cursor imzası: HMAC-SHA256(domain=`"emsalist-cursor|v1"`, payload), base64url
- Result ID payload'ı: `qid`, `sid`, `svid`, `pid`, `iv`. Ham sorgu metni içermez.
- Result ID imzası: HMAC-SHA256(domain=`"emsalist-result-id|v1"`, payload), base64url
- Her iki imza da istek anında `verify_cursor` / `verify_result_id` ile doğrulanır
- `query_hash_binding`: cursor yalnızca aynı sorgu hash'i ile kullanılabilir
- Feedback endpoint'i result ID imzasını doğrular; imzasız veya yanlış imzalı ID reddedilir (422)

### 20.5 Embedding çağrı gizliliği

- Embedding yalnızca global `SourceParagraph.text` üzerinden üretilir (case belgeleri, mesajlar, dilekçeler üzerinde değil)
- Gemini embedding API çağrılarında ham kaynak metni veya sorgu metni günlüğe yazılmaz
- Embedding hataları `try/except` ile yakalanır; hata mesajında ham metin istemciye veya log'a dönmez
- Kaynak embedding batch'i `RETRIEVAL_DOCUMENT`, sorgu embedding'i `RETRIEVAL_QUERY` task_type'ı ile gönderilir

## 21. Kapanış kriterleri

- Threat model her P2 aşamasında güncellenir.
- Hassas içerik loglanmaz.
- Tenant/case object authorization testlidir.
- Mobil token secure storage kullanır.
- Belge parser sandbox/limit ile çalışır.
- Model ve source pipeline prompt injection savunmasına sahiptir.
- Data export/delete/legal hold akışları test edilebilir durumdadır.
