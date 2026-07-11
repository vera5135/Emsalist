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

## 18. P2.6 uygulanan davranış (implemented)

Bu bölüm gerçekte kodlanan davranışı kaydeder. Belirtilmeyen tasarım maddeleri
(embedding üretimi, semantic ranking, gerçek Playwright canlı fetch entegrasyonu,
konsolide sürüm otomasyonu, destructive admin merge) ileri sürümlere bırakılmıştır.

### 18.1 Canonical model kararı

Net-new DB tabloları: `source_records`, `source_versions`, `source_paragraphs`,
`source_verifications`, `source_relationships`, `source_usages`. Mevcut
`Precedent`/`LegalGroundOrm`/`LegalIssueNode` case-scoped türetilmiş
snapshot'lardır ve dokunulmadı (farklı mimari katman, çakışma yok). Vector/Chroma
katmanı türetilmiştir; P2.6 yalnız P2.7'nin tüketeceği
`source_index_eligibility` seam'ini sağlar, embedding üretmez.

### 18.2 Provider / kaynak destek matrisi (gerçek)

| Provider / Source type | Gerçek fetch | Parse metadata | Text | Paragraph provenance | Verification evidence |
|---|---|---|---|---|---|
| Mevzuat (legislation) | Seam (fixture/editor submit) | ✅ canonical key | ✅ normalize | ✅ madde no bazlı | ✅ resmi domain+hash |
| Yargıtay kararı (supreme_court_decision) | Seam (fixture/editor submit; canlı Playwright scraper ayrı/dormant) | ✅ canonical key | ✅ normalize | ✅ bölüm bazlı (sahte sayfa yok) | ✅ resmi domain+hash |
| Diğer resmi türler | Seam | ✅ | ✅ | ✅ | koşullu |
| Doktrin / user_uploaded | Seam | title-hash key | ✅ | bölüm bazlı | needs_review |

Not: P2.6 canlı dış network fetch'i CI için zorunlu değildir. Secure fetcher
(`source_fetcher`) tam SSRF korumasıyla hazırdır ve enjekte edilebilir resolver/
transport ile deterministik test edilir; gerçek Yargıtay Playwright scraper'ı
mevcut ancak bu dilimin canonical hattına bağlanmadı. Fixture'lar production
source olduğunu iddia etmez.

### 18.3 Canonical key

Deterministic, merkezi (`source_canonical_key`). İçtihat:
`type|court|chamber|case_no|decision_no|date`; mevzuat:
`type|authority|number|date`. Türkçe NFKC/casefold + E./K. + tarih normalizasyonu.
Eşdeğer varyantlar (Yargıtay 13.HD E.2020/123 K.2021/456 vs YARGITAY 13 HD
2020-123 2021-456) aynı key'e gider; gerçekten farklı numara/tarih birleşmez.

### 18.4 Versiyonlama

Aynı canonical key + aynı content_hash → idempotent (yeni sürüm yok). Aynı key +
farklı content → yeni SourceVersion, eski `superseded` işaretlenir ama silinmez.
Aynı key + kritik metadata çelişkisi → `conflicting`, sessiz merge yok.

### 18.5 Doğrulama state machine

`verified_official` yalnız resmi allowlisted URL + başarılı retrieval + content
hash ile verilir (URL'de 'gov' geçmesi yeterli değil). `quarantined →
verified_official` doğrudan geçiş yok. `conflicting` yalnız review ile çözülür.
Normal lawyer tenant kullanıcısı global source'u verify/quarantine edemez
(`require_editor` seam; jwt modunda editor/admin rolü zorunlu, local modda mevcut
kod tabanıyla uyumlu bypass).

### 18.6 Temporal validity

`evaluate_source_validity(...)` → valid | not_yet_effective | expired | repealed
| superseded | unknown. Tarih bilinmiyorsa `valid` uydurulmaz.

### 18.7 SSRF / ingestion güvenliği

`source_fetcher.validate_url` yalnız http/https; credentials reddi; domain
allowlist; localhost/loopback/private/link-local/reserved (IPv4+IPv6); metadata
endpoint; IP literal fail-closed; DNS çözümündeki her IP doğrulanır (rebinding);
her redirect hop'unda yeniden doğrulama; redirect loop/max hop; response size +
content-type allowlist. 'Başarıyla indirildi' ≠ 'doğrulandı'.

### 18.8 SourceUsage traceability

Tenant+case-owner scoped; foreign case/usage → 404; source/version ve
version/paragraph bütünlüğü doğrulanır; conflicting/quarantined kaynak normal
kullanıcı tarafından trusted usage olarak eklenemez; `used_in_final_draft` P2.9
gelene kadar sahte true yapılmaz; `relevance_score` fabricate edilmez; yeni
sürüm eski usage'ı silmez (izlenebilirlik korunur).

### 18.9 Bilinen eksikler / rollback

- Embedding/semantic index üretilmez (P2.7).
- Canlı resmi fetch bu hattın parçası değil (seam + dormant scraper).
- Destructive admin merge yok; yalnız review/conflict seam.
- Editor/admin mobil review ekranı P2.6'da yok; backend/API + testler yeterli
  (final raporda belirtildi).
- Rollback: migration `ce94808703a4` tek adımda `downgrade -1`; router mount
  kaldırılarak yeni endpoint'ler devre dışı bırakılabilir; eski legacy source
  yolları etkilenmez.
