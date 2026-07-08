# P2 Grounded Drafting

## 1. Amaç

Kaynak bağlantılı dilekçe sistemi, dosya olayı, delil, hukuki mesele ve doğrulanmış hukuk kaynağını aynı izlenebilir zincirde birleştirir. Sistem tek komutla kontrolsüz nihai metin üretmez; aşamalı, sürümlü ve avukat onaylı çalışır.

## 2. Temel zincir

`Case Fact → Timeline/Event → Claim/Defense → Evidence → Legal Issue → Source Paragraph → Draft Paragraph`

Her önemli paragraf en az bir dosya dayanağı veya açık bir `unsupported` uyarısı taşır.

## 3. Taslak yaşam döngüsü

- `new`
- `readiness_check`
- `planning`
- `generating`
- `source_validation`
- `consistency_review`
- `awaiting_lawyer_review`
- `changes_requested`
- `approved`
- `exported`
- `archived`

## 4. Taslak öncesi yeterlilik kontrolü

Kontroller:

- aktif case ve yetki
- dilekçe türü
- mahkeme/merci
- taraf bilgileri
- talepler
- kritik tarihler
- kritik tutarlar
- çözümlenmemiş çelişkiler
- ana iddiaların delil durumu
- kullanılabilir doğrulanmış kaynaklar
- süre/görev/yetki riskleri

Sonuç:

- ready
- ready_with_warnings
- blocked

`blocked` örnekleri:

- mahkeme/merci bilinmiyor
- ana talep seçilmemiş
- kritik çelişki çözülmemiş
- doğrulanmamış karar numarası zorunlu kaynak olarak seçilmiş

## 5. Taslak türleri

- dava dilekçesi
- cevap dilekçesi
- cevaba cevap
- ikinci cevap
- istinaf
- temyiz
- ihtiyati tedbir/haciz talebi
- itiraz
- beyan
- delil listesi
- ihtarname
- arabuluculuk başvurusu/son tutanak destek metni

Her türün required section ve validation profili bulunur.

## 6. Planlama aşaması

Sistem önce bölüm planı üretir:

- merci
- taraflar
- konu
- kısa özet
- olaylar
- hukuki değerlendirme
- deliller
- hukuki nedenler
- sonuç ve talep
- ekler

Kullanıcı bölüm ekleyebilir, silebilir veya sıralayabilir.

## 7. Paragraf modeli

`DraftParagraph` alanları:

- id
- tenant_id
- case_id
- draft_id
- section_id
- order_index
- paragraph_type
- text
- status
- generated_by
- edited_by
- fact_refs
- event_refs
- claim_refs
- evidence_refs
- issue_refs
- source_paragraph_refs
- unsupported_reason
- confidence
- created_at
- updated_at
- version

## 8. Kaynak seçimi

Kaynak seçimi iki aşamalıdır:

1. Sistem aday kaynakları sıralar.
2. Kullanıcı veya doğrulama politikası kaynağı seçer.

Kaynak kullanımı:

- selected
- used
- not_used
- rejected
- needs_review

Kullanılmama gerekçeleri:

- alakasız
- karşıt
- güncel değil
- doğrulanmamış
- aynı argümanı tekrar ediyor
- dosya olayına uymuyor

## 9. Üretim kuralları

- Model yalnız sağlanan source_id ve source paragraph içeriklerini kullanır.
- Citation metni deterministik renderer tarafından oluşturulur.
- Model karar numarası, tarih veya mahkeme adı icat edemez.
- Doğrulanmamış fact açıkça belirtilmeden kesin cümleye dönüşmez.
- Kullanıcı beyanı delil olarak etiketlenmez.
- Karşıt kaynak varsa sistem bunu gizlemez.
- Hukuki sonuç cümlesi kaynak veya açık analiz etiketi taşır.

## 10. Tutarlılık kontrolleri

- taraf adları tutarlı mı
- tarih sırası doğru mu
- tutarlar ve para birimleri uyumlu mu
- talep ile sonuç bölümü uyumlu mu
- metinde geçen belge delil listesinde var mı
- kullanılan kaynağın temporal validity durumu uygun mu
- karar numarası SourceRecord ile eşleşiyor mu
- aynı olay farklı tarihlerle yazılmış mı
- desteklenmeyen iddia var mı
- karşıt kaynak atlandı mı

## 11. Hukuki citation renderer

Renderer girdisi:

- source_record_id
- source_version_id
- paragraph_id
- citation style

Çıktı örneği:

- mahkeme/daire
- esas/karar numarası
- karar tarihi
- ilgili paragraf veya madde

Renderer veri tabanı dışı serbest metin kabul etmez.

## 12. Kullanıcı düzenlemeleri

- Kullanıcı metni doğrudan düzenleyebilir.
- AI düzenlemesi yeni revision üretir.
- Kullanıcı düzenlemesi üzerine otomatik overwrite yapılmaz.
- Kaynak bağlantısı metin değişiminden sonra yeniden doğrulanır.
- Büyük değişikliklerde paragraph grounding status `needs_review` olur.

## 13. Sürümleme

`DraftRevision`:

- id
- draft_id
- revision_number
- parent_revision_id
- created_by
- creation_reason
- content_hash
- source_fingerprint
- validation_summary
- created_at

Nihai export belirli revision'a bağlanır.

## 14. İnceleme akışı

Roller:

- author
- reviewer
- approver

Aksiyonlar:

- incelemeye gönder
- yorum ekle
- değişiklik iste
- onayla
- onayı geri çek

Onay, kaynak veya fact değiştiğinde invalid olabilir.

## 15. Dışa aktarma

Formatlar:

- DOCX
- PDF
- düz metin

Export içeriği:

- seçili şablon
- paragraf düzeni
- dipnot/citation stili
- ek listesi
- export metadata

DOCX şablon katmanları:

1. sistem şablonu
2. büro şablonu
3. taslak özel ayarı

## 16. Hassas veri ve loglama

- Dilekçe tam metni application log'a yazılmaz.
- Model request/response logları varsayılan olarak kapalı veya redacted olur.
- Export URL kısa süreli signed URL'dir.
- Draft erişimi case membership gerektirir.

## 17. API özeti

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

## 18. Pilot acceptance

Ayıplı araç pilotunda taslak:

- satın alma ve ayıp kronolojisini doğru taşır
- satış bedeli ve araç bilgilerini verified fact'ten alır
- ayıp ihbarı eksikse uyarı verir
- mevzuat ve en az bir doğrulanmış karar kullanır
- kullanılan kaynağın paragrafını gösterir
- karşıt karar varsa listeler
- sonuç ve talebi seçilen seçimlik hakla uyumlu tutar
- DOCX olarak dışa aktarılır

## 19. Kapanış kriterleri

- Doğrulanmamış citation nihai export'a giremez.
- Her önemli paragraf grounding metadata taşır.
- Kullanıcı düzenlemeleri sürüm geçmişinde korunur.
- Source veya fact değişikliği validasyonu yeniden tetikler.
- Dilekçe metni loglara sızmaz.
- Export belirli revision ve source fingerprint'e bağlanır.
