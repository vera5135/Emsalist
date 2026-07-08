# P2 UYAP Bridge

## 1. Amaç

UYAP Bridge, kullanıcıya ait UYAP dosya hareketlerini Emsalist dosyalarıyla kontrollü biçimde eşleştirir. İlk sürüm okuma, eşleştirme, evrak ekleme ve bildirim odaklıdır; kullanıcı adına evrak göndermez.

## 2. İlk sürüm kapsamı

- bağlantı durumu
- son başarılı kontrol zamanı
- dosya numarası eşleştirme
- yeni hareket listesi
- manuel UYAP evrakı ekleme
- evrakı Emsalist case ile ilişkilendirme
- yeni hareket rozeti
- okundu/işlendi durumu
- süre adayı çıkarma
- bağlantıyı kaldırma

## 3. Kapsam dışı

- otomatik dava açma
- otomatik evrak gönderme
- e-imza
- kullanıcı adına nihai işlem
- yetki kapsamını gizli biçimde genişletme

## 4. UI durumları

- connected
- disconnected
- connecting
- authentication_required
- degraded
- error
- disabled

Üst çubuk ikonu renk yanında erişilebilir metin ve şekil değişikliği taşır.

## 5. UYAP hareket modeli

Alanlar:

- id
- tenant_id
- user_id
- uyap_connection_id
- uyap_file_reference
- matched_case_id
- movement_type
- movement_date
- title
- safe_summary
- document_reference
- source_hash
- read_at
- processed_at
- sync_run_id
- created_at

## 6. Dosya eşleştirme

Sinyaller:

- mahkeme adı
- esas/dosya numarası
- taraf isimleri
- kullanıcı manuel seçimi

Confidence düşükse otomatik eşleştirme yapılmaz.

## 7. Kimlik bilgileri

- Parola düz metin saklanmaz.
- Token/oturum verisi platform güvenli deposu veya şifreli server secret store içinde tutulur.
- Loglarda parola, token, cookie ve evrak tam metni bulunmaz.
- Bağlantı kaldırıldığında token iptal/silme süreci çalışır.

## 8. Senkronizasyon

- idempotent sync run
- kaynak hareket hash'i ile duplicate önleme
- retry yalnız transient hatalarda
- backoff ve rate limit
- son başarılı cursor/checkpoint
- kullanıcı tetiklemeli manuel yenileme

## 9. Evrak akışı

1. Hareket alınır.
2. Metadata kaydedilir.
3. Evrak indirilebiliyorsa güvenli belge hattına gönderilir.
4. Document source_type `uyap_document` olur.
5. Kullanıcı case eşleşmesini doğrular.
6. Belge analizi normal pipeline üzerinden çalışır.
7. Süre adayı kullanıcıya sunulur.

## 10. Süre çıkarımı

- trigger event UYAP movement veya evrak olabilir.
- hesaplama dayanak ve varsayımlarını gösterir.
- kullanıcı doğrulaması olmadan confirmed olmaz.
- kritik belirsizlik varsa bildirim engelleyici uyarı taşır.

## 11. Bildirimler

- yeni hareket
- yeni evrak
- authentication required
- sync error
- olası süre

Bildirim payload'ı hassas belge içeriği taşımaz; deep link hedefi taşır.

## 12. Feature flag

UYAP modülü:

- global
- tenant
- user

seviyelerinde kapatılabilir. Kapalıyken mevcut veriler erişim politikasına göre korunur, yeni sync yapılmaz.

## 13. API özeti

- GET `/uyap/status`
- POST `/uyap/connect`
- POST `/uyap/disconnect`
- POST `/uyap/sync`
- GET `/uyap/movements`
- POST `/uyap/movements/{movement_id}/match-case`
- POST `/uyap/movements/{movement_id}/mark-read`
- POST `/uyap/movements/{movement_id}/extract-deadline`

## 14. Audit

Kaydedilir:

- connection created/removed
- sync started/completed/failed
- movement matched
- document imported
- deadline confirmed

Kaydedilmez:

- parola
- token
- belge tam metni
- hassas cookie

## 15. Hata davranışı

- UYAP erişilemiyorsa Emsalist case kullanımı devam eder.
- Hata büyük kalıcı banner yerine ikon ve açıklayıcı bottom sheet ile gösterilir.
- Son başarılı kontrol zamanı korunur.
- Kullanıcıya verinin güncel olmayabileceği açıkça belirtilir.

## 16. Kabul kriterleri

- Yeni hareket duplicate oluşmadan alınır.
- Yanlış case otomatik eşleştirilmez.
- Token/parola loglara sızmaz.
- Modül kapatılabilir.
- Evrak belge pipeline'ına kaynak etiketiyle girer.
- Süre kullanıcı doğrulaması olmadan kesinleşmez.
- İlk sürümde outbound UYAP işlemi yoktur.
