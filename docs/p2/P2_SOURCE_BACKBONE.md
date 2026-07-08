# P2 Trusted Source Backbone

## 1. Amaç

Kaynak omurgası, Emsalist'in kullandığı mevzuat, içtihat, Resmî Gazete ve doktrin kayıtlarının kökenini, sürümünü, doğrulama durumunu ve kullanım izini yönetir. Bu katman tamamlanmadan semantik hukuk araması veya kaynak bağlantılı dilekçe nihai kabul alamaz.

## 2. Kaynak öncelik sırası

1. Resmî mevzuat ve Resmî Gazete
2. Resmî mahkeme/kurum karar veri tabanı
3. Kurum tarafından yayımlanan doğrulanmış metin
4. Güvenilir ikincil hukuk kaynağı
5. Editör incelemesinden geçmiş doktrin
6. Kullanıcı yüklemesi
7. Doğrulanmamış dış kaynak

Sıralama, otomatik olarak hukuki bağlayıcılık anlamına gelmez; doğrulama ve kaynak kalitesini gösterir.

## 3. Kaynak türleri

- legislation
- regulation
- communiqué
- circular
- presidential_decree
- official_gazette_issue
- supreme_court_decision
- council_of_state_decision
- constitutional_court_decision
- court_of_jurisdictional_disputes_decision
- regional_court_decision
- first_instance_decision
- doctrine_article
- doctrine_book
- institutional_guidance
- user_uploaded_source

## 4. Temel veri modeli

### 4.1 SourceRecord

Kaynağın canonical kimliğidir.

Alanlar:

- id
- source_type
- canonical_key
- title
- issuing_authority
- court
- chamber
- case_number
- decision_number
- decision_date
- publication_date
- effective_date
- repeal_date
- official_url
- language
- jurisdiction
- verification_status
- temporal_status
- current_version_id
- created_at
- updated_at

### 4.2 SourceVersion

Kaynağın belirli metin sürümüdür.

Alanlar:

- id
- source_record_id
- version_label
- content_hash
- raw_document_hash
- retrieved_at
- valid_from
- valid_to
- supersedes_version_id
- retrieval_method
- parser_version
- normalized_text
- metadata_json
- status

### 4.3 SourceParagraph

Kaynağın atıf yapılabilir bölümü.

Alanlar:

- id
- source_version_id
- paragraph_index
- heading_path
- text
- text_hash
- page
- article_number
- locator_json
- embedding_status

### 4.4 SourceVerification

Doğrulama olayını tutar.

Alanlar:

- id
- source_record_id
- source_version_id
- verification_method
- verifier_type: automated, editor, official_match
- verifier_user_id
- evidence_url
- evidence_hash
- result
- notes
- verified_at

### 4.5 SourceRelationship

Kaynaklar arası ilişkiyi tutar.

İlişki türleri:

- amends
- repeals
- supersedes
- cites
- interprets
- conflicts_with
- similar_to
- derived_from
- consolidated_into

### 4.6 SourceUsage

Kaynağın dosya, mesele, iddia veya taslakta kullanım izidir.

Alanlar:

- id
- tenant_id
- case_id
- source_record_id
- source_version_id
- source_paragraph_id
- usage_type
- target_type
- target_id
- relevance_score
- reason
- selected_by
- used_in_final_draft
- created_at

## 5. Canonical key kuralları

### 5.1 İçtihat

Önerilen canonical key:

`court|chamber|case_number|decision_number|decision_date`

Normalize işlemleri:

- Türkçe karakter normalizasyonu
- boşluk/noktalama temizliği
- esas ve karar numarası format standardı
- daire adının controlled vocabulary ile eşlenmesi

### 5.2 Mevzuat

Önerilen canonical key:

`authority|legislation_type|number|publication_date`

Madde düzeyindeki değişiklikler ayrı SourceVersion üretir.

## 6. Doğrulama statüleri

- `verified_official`
- `verified_secondary`
- `editor_verified`
- `needs_review`
- `conflicting`
- `outdated`
- `superseded`
- `repealed`
- `unavailable`
- `quarantined`

Geçiş kuralları:

- Resmî URL ve hash eşleşmesi → verified_official
- İki güvenilir ikincil kaynak eşleşmesi → verified_secondary
- İnsan editör onayı → editor_verified
- Metin veya metadata çelişkisi → conflicting
- Yeni sürüm bulunduğunda eski sürüm → superseded/outdated

## 7. Güncellik ve temporal validity

Her mevzuat kaydı için:

- yürürlük başlangıcı
- yürürlük sonu
- değişiklik tarihi
- konsolide sürüm
- geçmiş sürüm

tutulur.

Dosya olay tarihi ile kaynak geçerlilik tarihi karşılaştırılır. Olay tarihinde yürürlükte olmayan sürüm uyarı üretir.

## 8. Ingestion hattı

1. Kaynak aday URL'si veya dosyası alınır.
2. Domain ve kurum allowlist kontrolü yapılır.
3. Ham içerik indirilir.
4. Hash hesaplanır.
5. Metadata ayrıştırılır.
6. Canonical key oluşturulur.
7. Duplicate ve sürüm kontrolü yapılır.
8. Metin normalize edilir.
9. Paragraflara bölünür.
10. Otomatik doğrulama çalışır.
11. Gerekirse editör kuyruğuna düşer.
12. Search index'e yalnız izin verilen statüler gönderilir.

## 9. İnsan inceleme akışı

Editör ekranı:

- kaynak metadata karşılaştırması
- resmî/ikincil metin farkı
- duplicate önerisi
- sürüm ilişkisi
- doğrulama kanıtı
- karantina veya onay

Kritik kaynaklar:

- nihai dilekçede kullanılacak doğrulanmamış karar
- metadata çelişkili karar
- yürürlük tarihi belirsiz mevzuat
- kullanıcı tarafından bildirilen hatalı kaynak

insan incelemesine gider.

## 10. Search index politikası

- verified_official: tam ağırlık
- editor_verified: tam ağırlık
- verified_secondary: azaltılmış kalite cezası
- needs_review: aramada gösterilebilir, açık uyarı ve düşük ağırlık
- conflicting/quarantined: normal kullanıcı aramasından çıkarılır
- superseded/outdated: tarih bağlamında gösterilebilir, güncel varsayılan sonuç değildir

## 11. Kaynak kartında zorunlu alanlar

- başlık
- tür
- kurum/mahkeme/daire
- tarih
- esas/karar numarası
- doğrulama statüsü
- temporal status
- ilgili paragraf
- neden bulunduğu
- kullanılabilir argüman
- karşı taraf lehine yön
- resmî bağlantı
- dosyada kullanıldı/kullanılmadı

Normal kullanıcıya parser, embedding veya indeks hatası gösterilmez.

## 12. Resmî kaynak takibi

Takip işi:

- last_checked_at
- last_successful_check_at
- etag/last-modified
- content_hash
- yeni sürüm tespiti
- değişiklik özeti
- etkilenen dosya/taslak listesi

Yeni sürüm, kullanılan bir kaynağı etkiliyorsa ilgili dosyalarda yeniden inceleme görevi oluşturulur.

## 13. Kaynak uydurma savunması

- Modelin döndürdüğü kaynak kimliği veri tabanında bulunmalıdır.
- Esas/karar numarası yalnız SourceRecord'dan alınır.
- Kaynak metni olmayan karar nihai citation olamaz.
- Citation rendering deterministic servis tarafından yapılır.
- Model yalnız source_id seçer; ham citation üretmez.

## 14. API özeti

- GET `/legal-sources`
- GET `/legal-sources/{source_id}`
- GET `/legal-sources/{source_id}/versions`
- GET `/legal-sources/{source_id}/paragraphs`
- POST `/legal-sources/{source_id}/verify`
- POST `/legal-sources/{source_id}/quarantine`
- POST `/cases/{case_id}/sources`
- DELETE `/cases/{case_id}/sources/{usage_id}`
- GET `/official-source-tracking`

## 15. Güvenlik

- Kaynak ingestion dış ağ erişimi allowlist ile sınırlandırılır.
- SSRF savunması zorunludur.
- İndirilen içerik sandbox içinde ayrıştırılır.
- Script ve aktif içerik çalıştırılmaz.
- Editör yetkileri tenant hukuk dosyası yetkilerinden ayrıdır.

## 16. Pilot kabul kriterleri

Ayıplı araç pilotunda:

- en az bir yürürlükte mevzuat kaydı
- en az bir doğrulanmış Yargıtay kararı
- ilgili paragraf bağlantısı
- olay tarihiyle temporal validity kontrolü
- dilekçe paragrafına source usage kaydı
- doğrulanmamış kaynak için açık engel/uyarı

bulunmalıdır.

## 17. Kapanış kriterleri

- Duplicate kararlar canonical key ile birleştirilir.
- Resmî URL ve içerik hash'i saklanır.
- Kaynak sürümleri kaybolmaz.
- Eski mevzuat güncelmiş gibi kullanılmaz.
- Nihai dilekçedeki citation'lar SourceRecord üzerinden üretilir.
- Kaynağın hangi dosya, mesele ve paragrafta kullanıldığı izlenir.
