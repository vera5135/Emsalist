# P2 Document Pipeline

## 1. Amaç

Belge hattı; mobil yüklemeden güvenli depolamaya, metin çıkarmadan kullanıcı doğrulamasına kadar bütün belge yaşam döngüsünü tanımlar. Hedef, dosyadan çıkarılan her bilginin belge konumuna ve analiz sürümüne bağlanmasıdır.

## 2. Desteklenen formatlar

İlk sürüm:

- PDF
- UDF
- DOCX
- TXT
- JPG
- JPEG
- PNG

Sonraki sürüm değerlendirmesi:

- TIFF
- HEIC
- XLSX
- EML
- ZIP içindeki kontrollü evrak paketleri

## 3. Belge yaşam döngüsü

Durumlar:

- `selected`
- `uploading`
- `uploaded`
- `security_scanning`
- `quarantined`
- `queued`
- `extracting`
- `classifying`
- `analyzing`
- `awaiting_user_review`
- `completed`
- `failed`
- `unsupported`
- `deleted`

Durum geçişleri audit kaydı üretir.

## 4. Uçtan uca akış

1. Mobil istemci belge metadata'sını alır.
2. Backend upload session oluşturur.
3. Boyut, uzantı ve izin kontrolleri yapılır.
4. İstemci belgeyi doğrudan veya parçalı yükler.
5. Sunucu gerçek MIME türünü magic-byte ile doğrular.
6. SHA-256 hash hesaplanır.
7. Tenant/case içinde duplicate kontrolü yapılır.
8. Zararlı içerik ve arşiv bombası kontrolü uygulanır.
9. Belge güvenli, private object storage'a taşınır.
10. Document kaydı ve processing job atomik oluşturulur.
11. Format özel metin çıkarımı yapılır.
12. Sayfa, paragraf ve koordinat bilgileri oluşturulur.
13. Belge türü sınıflandırılır.
14. Fact, taraf, tarih, tutar, talep ve kaynak adayları çıkarılır.
15. Prompt injection ve şüpheli talimatlar veri olarak işaretlenir.
16. Kullanıcıya kritik doğrulama kartları gösterilir.
17. Onaylanan bilgiler case memory'ye yazılır.
18. Analiz sürümü ve model/çıkarıcı bilgisi kaydedilir.

## 5. Yükleme politikası

### 5.1 Boyut

P2 ilk beta:

- tek belge üst sınırı: 25 MB
- fotoğraf üst sınırı: 15 MB
- toplam eş zamanlı yükleme: 3

Sonraki genişleme:

- parçalı yükleme ile 100 MB

### 5.2 İsim ve yol güvenliği

- Kullanıcı dosya adı yalnız display metadata olarak saklanır.
- Storage key sunucu tarafından üretilir.
- `../`, null byte ve unicode path confusion temizlenir.
- Aynı isim mevcut dosyanın üzerine yazmaz.

### 5.3 MIME doğrulama

Uzantı tek başına yeterli değildir. Gerçek MIME ile izin verilen format eşleşmelidir.

### 5.4 Duplicate davranışı

Aynı case içinde aynı hash bulunursa:

- kullanıcıya mevcut belge gösterilir
- varsayılan olarak ikinci fiziksel kopya oluşturulmaz
- kullanıcı farklı bir belge olduğunu iddia ederse manuel inceleme kaydı açılır

Farklı tenant'lar arasında hash eşleşmesi kullanıcıya gösterilmez.

## 6. Güvenlik taraması

Kontroller:

- zararlı yazılım
- makro ve embedded object
- PDF JavaScript
- arşiv bombası
- aşırı sayfa/nesne sayısı
- bozuk dosya yapısı
- şifreli dosya
- uzantı/MIME uyuşmazlığı

Karantina davranışı:

- dosya analiz edilmez
- normal indirme bağlantısı verilmez
- kullanıcıya teknik olmayan açıklama gösterilir
- admin erişimi ayrı ve audit'li olur

## 7. Format özel çıkarım

### 7.1 PDF

- önce text layer
- gerekirse sayfa bazlı OCR
- tablo ve imza alanı işaretleme
- sayfa koordinatı korunması

### 7.2 UDF

- yalnız backend tarafında ayrıştırılır
- UYAP/UDF parser sandbox içinde çalışır
- ham UDF istemcide açılmaz
- parser başarısızsa orijinal belge korunur

### 7.3 DOCX

- paragraf, tablo, header/footer ve dipnot çıkarılır
- track changes ve yorumlar ayrı metadata olarak tutulur
- embedded media varsayılan olarak analiz edilmez

### 7.4 Görseller

- EXIF hassas metadata temizlenir veya ayrı korunur
- orientation normalize edilir
- OCR sonucu bounding box taşır
- düşük kalite sayfa uyarısı oluşturulur

## 8. Belge sınıfları

- petition
- response_petition
- appeal_petition
- court_decision
- expert_report
- contract
- invoice
- notice
- notary_notice
- service_record
- accident_report
- uyap_document
- notification
- receipt
- identity_document
- photo_evidence
- other

Sınıflandırma confidence düşükse kullanıcı seçimi istenir.

## 9. Çıkarım çıktıları

- belge özeti
- taraf adayları
- tarihler
- tutarlar ve para birimi
- araç/taşınmaz/iş ilişkisi gibi konu alanları
- talepler
- savunmalar
- deliller
- hukuki atıflar
- esas/karar numaraları
- dosya numaraları
- kritik paragraflar
- imza veya ek eksikliği
- çelişki adayları
- okunamayan alanlar

Her çıktı:

- document_id
- analysis_run_id
- page
- paragraph
- bounding_box
- text_hash
- confidence
- verification_status

taşır.

## 10. Analiz sürümü

`DocumentAnalysisRun` alanları:

- id
- tenant_id
- case_id
- document_id
- pipeline_version
- extractor_version
- model_provider
- model_name
- prompt_version
- started_at
- completed_at
- status
- error_code
- input_hash
- output_hash
- token_usage_safe

Aynı belge yeniden analiz edilirse önceki sonuçlar silinmez; yeni run oluşturulur.

## 11. Kullanıcı doğrulama

Kullanıcı:

- tek bir çıkarımı doğrulayabilir
- düzeltebilir
- reddedebilir
- toplu onay verebilir
- belgeyi kaynak olarak dışlayabilir

Toplu onay kritik alanlarda varsayılan değildir.

Kritik alanlar:

- tarih
- tutar
- kimlik
- plaka/şasi
- rapor numarası
- tebligat tarihi
- ihbar tarihi
- mahkeme/dosya numarası

## 12. İş kuyruğu

Job türleri:

- document_security_scan
- document_text_extract
- document_classify
- document_fact_extract
- document_source_detect
- document_reprocess

Kurallar:

- idempotency key: document_id + input_hash + pipeline_version
- retry yalnız transient hatalarda
- poison job dead-letter kuyruğuna
- kullanıcıya ilerleme aşaması gösterilir
- job payload hassas metin içermez

## 13. Hata kodları

- DOC-UPLOAD-01: upload interrupted
- DOC-TYPE-02: unsupported format
- DOC-SIZE-03: size limit exceeded
- DOC-SECURITY-04: quarantined
- DOC-PASSWORD-05: password protected
- DOC-EXTRACT-06: text extraction failed
- DOC-OCR-07: low quality OCR
- DOC-ANALYSIS-08: analysis failed
- DOC-DUPLICATE-09: duplicate document

Hata mesajı verinin kaybolup kaybolmadığını açıklar.

## 14. Depolama

- Private object storage
- Server-side encryption
- Tenant/case namespaced key
- Signed URL kısa süreli
- Download authorization her istekte
- Original ve derived artifact ayrımı
- Preview dosyası original yerine kullanılabilir

## 15. Silme ve saklama

- Soft-delete Document kaydını görünmez yapar.
- Legal hold varsa fiziksel silme engellenir.
- Derived text, thumbnail ve OCR çıktıları original ile birlikte purge edilir.
- Yedek saklama politikası ayrıca izlenir.
- Audit kaydı belge içeriğini değil işlem metadata'sını içerir.

## 16. Prompt injection savunması

Belge metni talimat değil veridir.

- Sistem prompt'ları belge içeriğiyle değişmez.
- Belge içindeki URL veya komut otomatik çalıştırılmaz.
- Kaynak doğrulama kapısı belge talimatıyla atlanmaz.
- Çıkarım prompt'u açık data delimiter kullanır.
- Şüpheli talimat span'leri işaretlenir.

## 17. API özeti

- POST `/cases/{case_id}/documents/uploads`
- POST `/documents/{document_id}/parts`
- POST `/documents/{document_id}/complete-upload`
- GET `/documents/{document_id}`
- GET `/documents/{document_id}/analysis-runs`
- POST `/documents/{document_id}/reprocess`
- POST `/document-findings/{finding_id}/confirm`
- POST `/document-findings/{finding_id}/reject`
- DELETE `/documents/{document_id}`

## 18. Kabul kriterleri

- MIME spoofing engellenir.
- Path traversal mümkün değildir.
- Aynı case içinde duplicate belge belirlenir.
- Her çıkarım sayfa/paragraf konumuna bağlıdır.
- Analiz yeniden çalıştırıldığında önceki sürüm korunur.
- Kullanıcı doğrulaması case memory'de kaynaklı fact üretir.
- Karantinadaki belge normal kullanıcı tarafından indirilemez.
- Farklı tenant belgesi hash veya kimlikle keşfedilemez.

## 19. P2.5 uygulanan davranış (implemented)

Bu bölüm, tasarımın hangi kısmının **gerçekten** kodlandığını dürüstçe kaydeder.
Belirtilmeyen tasarım maddeleri (chunked upload, gerçek OCR, virüs tarayıcı,
signed URL object storage, analysis-run sürümleme) ileri sürümlere bırakılmıştır.

### 19.1 Canonical model kararı

DB `documents` tablosu canonical modeldir ve P2.5 alanlarıyla genişletilmiştir
(`safe_filename, extension, document_type_source, analysis_status, support_level,
page_count, extracted_text_available, failure_code, uploaded_by, version`). Yeni
`document_pages` ve `document_extractions` tabloları eklenmiştir. Eski dosya
tabanlı `DocumentIntakeService` + `/documents/upload` rotası dormant bırakılmış,
regresyon önlemek için değiştirilmemiştir. P2.5 rotaları P2.3 sahipli-case
altında çalışır: `/api/v1/cases/{case_id}/documents`.

### 19.2 Gerçek format destek matrisi

| Format | Upload | Text extraction | Page provenance | Analysis (deterministic) |
|--------|--------|-----------------|-----------------|--------------------------|
| PDF | ✅ | ✅ (pypdf, sayfa bazlı) | ✅ gerçek sayfa no | ✅ |
| TXT | ✅ | ✅ (çok-kodlamalı) | tek mantıksal sayfa | ✅ |
| DOCX | ✅ | ✅ (paragraf) | ❌ sahte sayfa üretilmez | ✅ |
| UDF | ✅ | ⚠️ yalnız okunabilir XML/TXT içeren arşivde; aksi halde `unsupported` | tek mantıksal sayfa | ⚠️ |
| JPG/JPEG | ✅ | ❌ OCR yok → `unsupported` (upload_only) | ❌ | ❌ |
| PNG | ✅ | ❌ OCR yok → `unsupported` (upload_only) | ❌ | ❌ |

Support seviyeleri: PDF/DOCX/UDF = `text_extraction_only`, TXT = `fully_supported`,
JPG/JPEG/PNG = `upload_only`. Görsel belgeler için OCR **yapılmış gibi
davranılmaz**; belge kartı oluşur ama `extracted_text_available=false` ve durum
`unsupported` olur.

### 19.3 Durum makinesi (uygulanan)

`uploading → queued → processing → (analyzed | awaiting_confirmation |
unsupported | failed | quarantined)`; `deleted` terminaldir. Geçersiz geçişler
engellenir (ör. `quarantined → analyzed` yok; `deleted` yeniden işlenemez;
`failed → queued` retry ile mümkündür). Geçişler audit üretir.

### 19.4 Çıkarım → case memory (P2.4) entegrasyonu

`document_extractions` kayıtları `detected` olarak üretilir. Kullanıcı onayı:
`document_verified` `verification_status` ile bir `CaseFact` oluşturur ve P2.4
`detect_for_fact_type` çelişki motoru çalışır. Reddetme kaydı `rejected` yapar,
silmez, memory fact üretmez. P2.4 doğrulama/çelişki kuralları bypass edilmez.

### 19.5 Deterministic extractor kapsamı

Yalnız kural tabanlı, yüksek güvenli kalıplar: tarih, tutar+para birimi, plaka,
VIN/şasi, esas/karar numarası. Taraf, talep, savunma ve hukuki sonuç çıkarımı
**yapılmaz** (doğrulanmış analyzer yok). LLM kullanılmaz. Belge içeriği
uydurulmaz.

### 19.6 Bilinen eksikler / rollback

- Gerçek OCR, chundked upload, virüs tarayıcı, signed-URL object storage ve
  DocumentAnalysisRun sürümleme kapsam dışıdır.
- Mobil dosya seçici (native `file_picker`) henüz yok; upload akışı in-app metin
  belgesiyle uçtan uca çalışır ve native picker sonradan seam üzerinden eklenir.
- Rollback: migration `87be64670347` tek adımda `downgrade -1` ile geri alınır;
  yeni rotalar router mount kaldırılarak devre dışı bırakılabilir; eski dosya
  tabanlı `/documents/upload` etkilenmez.
