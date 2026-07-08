# P2 Case Memory Model

## 1. Amaç

Dosya hafızası, sohbet özetinden bağımsız, kaynak bağlantılı, sürümlü ve kullanıcı tarafından düzeltilebilir bir hukuk dosyası modeli sağlar. Amaç; dosyadaki olayları, tarihleri, tarafları, talepleri, delilleri, eksikleri, çelişkileri, riskleri ve kaynakları izlenebilir biçimde saklamaktır.

## 2. Temel ilkeler

1. Her kayıt `tenant_id` ve `case_id` taşır.
2. Her somut bilgi bir `source_type` ve `source_id` ile ilişkilidir.
3. Kullanıcı beyanı, belge çıkarımı, UYAP verisi ve sistem çıkarımı ayrı kaynak türleridir.
4. Çelişkili değerler otomatik birleştirilmez.
5. Silinen veya düzeltilen değerler geçmişten tamamen kaybolmaz; sürüm zincirinde tutulur.
6. Yapay zekâ önerisi, doğrulanmış gerçek statüsünü kendiliğinden alamaz.
7. Her kritik değişiklik audit olayı üretir.
8. Dosya hafızası farklı dosyalar arasında paylaşılmaz.

## 3. Çekirdek varlıklar

### 3.1 Case

Dosyanın ana kaydıdır.

Alanlar:

- `id`
- `tenant_id`
- `owner_user_id`
- `title`
- `legal_domain`
- `case_type`
- `status`
- `summary_text`
- `court_name`
- `court_file_number`
- `uyap_file_key`
- `risk_level`
- `created_at`
- `updated_at`
- `archived_at`
- `deleted_at`
- `version`

### 3.2 CaseParty

Taraf veya ilgili kişiyi temsil eder.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `party_type`: person, company, public_body, unknown
- `role`: client, plaintiff, defendant, creditor, debtor, witness, expert, other
- `display_name`
- `normalized_name`
- `identity_reference_encrypted`
- `contact_reference_encrypted`
- `verification_status`
- `source_type`
- `source_id`
- `created_at`
- `updated_at`
- `version`

### 3.3 CaseFact

Somut bilgi veya dosya alanıdır.

Örnek fact türleri:

- purchase_date
- sale_amount
- vehicle_plate
- vehicle_vin
- defect_discovery_date
- notice_date
- report_number
- report_date

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `fact_type`
- `value_json`
- `normalized_value_json`
- `unit`
- `source_type`
- `source_id`
- `source_locator`
- `confidence`
- `verification_status`
- `valid_from`
- `valid_to`
- `supersedes_fact_id`
- `created_by`
- `created_at`
- `updated_at`
- `version`

### 3.4 TimelineEvent

Dosya kronolojisindeki olaydır.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `event_type`
- `title`
- `description`
- `occurred_at`
- `occurred_at_precision`: exact, day, month, year, approximate, unknown
- `end_at`
- `party_ids`
- `source_type`
- `source_id`
- `source_locator`
- `legal_significance`
- `verification_status`
- `contradiction_status`
- `created_at`
- `updated_at`
- `version`

### 3.5 Claim

Dosyadaki hukuki iddia veya talebi temsil eder.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `claim_type`
- `title`
- `statement`
- `requested_relief`
- `amount`
- `currency`
- `status`
- `asserted_by_party_id`
- `source_type`
- `source_id`
- `verification_status`
- `created_at`
- `updated_at`
- `version`

### 3.6 Defense

Karşı iddia veya savunmadır.

Alanlar Claim ile benzerdir; ayrıca `responds_to_claim_id` taşır.

### 3.7 Evidence

Bir iddia veya olayla bağlantılı delildir.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `evidence_type`
- `title`
- `description`
- `document_id`
- `source_locator`
- `supports_claim_ids`
- `supports_event_ids`
- `reliability_status`
- `admissibility_status`
- `verification_status`
- `created_at`
- `updated_at`

### 3.8 MissingInformation

Eksik somut bilgi kaydıdır.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `field_key`
- `display_name`
- `required_value_type`
- `reason_required`
- `importance`: critical, high, medium, low
- `related_issue_ids`
- `related_claim_ids`
- `can_extract_from_document`
- `completion_rule_json`
- `status`: open, requested, supplied, verified, waived
- `resolved_by_fact_id`
- `created_at`
- `resolved_at`

Kural:

Kategori veya alanın varlığı tamamlanma değildir. `completion_rule_json` somut değeri doğrular.

### 3.9 Contradiction

Birbiriyle uyumsuz kayıtları temsil eder.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `contradiction_type`
- `subject_key`
- `fact_ids`
- `source_refs`
- `severity`
- `legal_impact`
- `status`: open, resolved, accepted_difference, dismissed
- `resolution_fact_id`
- `resolution_note`
- `resolved_by`
- `created_at`
- `resolved_at`

### 3.10 Risk

Dosyadaki hukuki veya operasyonel risktir.

Risk türleri:

- limitation
- deadline
- jurisdiction
- venue
- burden_of_proof
- evidence
- contradiction
- source_quality
- enforceability
- collection
- procedural

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `risk_type`
- `severity`
- `title`
- `reason`
- `impact`
- `mitigation`
- `related_fact_ids`
- `related_issue_ids`
- `related_claim_ids`
- `source_refs`
- `status`
- `calculated_at`
- `accepted_by_user_id`

### 3.11 Deadline

Süre veya tarih riskidir.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `deadline_type`
- `trigger_event_id`
- `trigger_date`
- `duration_rule_json`
- `calculated_due_at`
- `jurisdiction_calendar`
- `assumptions_json`
- `legal_source_refs`
- `verification_status`
- `status`: proposed, confirmed, completed, expired, cancelled
- `confirmed_by`
- `created_at`
- `updated_at`

Kural:

Kullanıcı doğrulaması veya yeterli kaynak olmadan `confirmed` olamaz.

### 3.12 LegalIssue

Ana veya alt hukuki meseledir.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `parent_issue_id`
- `issue_code`
- `title`
- `description`
- `burden_of_proof_party_id`
- `status`
- `confidence`
- `source_refs`
- `created_at`
- `updated_at`
- `version`

### 3.13 MemoryRevision

Dosya hafızasındaki değişiklik setidir.

Alanlar:

- `id`
- `tenant_id`
- `case_id`
- `revision_number`
- `trigger_type`: user_message, document_analysis, uyap_sync, manual_edit, system_recompute
- `trigger_id`
- `change_summary_json`
- `created_by`
- `created_at`

## 4. Kaynak türleri

- `user_message`
- `user_manual_entry`
- `document_extraction`
- `uyap_document`
- `uyap_movement`
- `official_legal_source`
- `secondary_legal_source`
- `system_inference`
- `imported_case_data`

## 5. Doğrulama statüleri

- `proposed`
- `detected`
- `user_confirmed`
- `document_confirmed`
- `uyap_confirmed`
- `official_source_confirmed`
- `conflicting`
- `rejected`
- `superseded`
- `invalid`

Geçiş kuralları:

- system_inference → proposed
- document_extraction → detected
- user_manual_entry → user_confirmed
- kullanıcı onayı → user_confirmed
- resmî belge eşleşmesi → document_confirmed veya uyap_confirmed
- çelişki → conflicting
- yeni doğru değer → eski kayıt superseded

## 6. Kaynak konumlandırma

`source_locator` yapısı:

```json
{
  "document_id": "doc_123",
  "page": 2,
  "paragraph": 3,
  "bounding_box": [0.12, 0.24, 0.83, 0.31],
  "text_hash": "sha256:..."
}
```

Mesaj kaynağı için:

```json
{
  "conversation_id": "conv_1",
  "message_id": "msg_123",
  "character_start": 0,
  "character_end": 18
}
```

## 7. Çelişki kuralları

Çelişki adayları:

- aynı fact_type için farklı normalleştirilmiş değer
- aynı olay için farklı tarih
- aynı araç için farklı plaka/şasi
- aynı rapor için farklı tarih/numara
- aynı talep için farklı tutar

Çelişki açılmaması gereken durumlar:

- yaklaşık tarih ile daha kesin tarih uyumluysa
- para birimi dönüşümü açıklanmışsa
- belge farklı dönem veya farklı aracı açıkça gösteriyorsa

## 8. Eksik bilgi tamamlama kuralları

Örnek:

```json
{
  "field_key": "sale_amount",
  "required_value_type": "money",
  "completion_rule": {
    "fact_type": "sale_amount",
    "verification_status_in": ["user_confirmed", "document_confirmed"],
    "value_required": true,
    "currency_required": true
  }
}
```

## 9. Risk seviyesi kuralları

- Kritik süre veya hak düşürücü tarih bilinmiyorsa risk en az `medium`.
- Çözülmemiş kritik çelişki varsa genel dosya riski `low` olamaz.
- Doğrulanmamış kaynağa dayanan tek kritik iddia varsa kaynak riski en az `high`.
- Belge veya delil bulunmayan ana iddia için ispat riski en az `medium`.

## 10. API davranışı

- Hafıza listeleri cursor pagination kullanır.
- Güncelleme optimistic locking ile `version` kontrolü yapar.
- Fact doğrulama ve reddetme ayrı komut endpoint'leri kullanır.
- Silme yerine varsayılan olarak supersede/reject uygulanır.
- Her komut idempotency key kabul eder.

## 11. Veri izolasyonu

- Tüm sorgular tenant filtresi uygular.
- Case üyeliği ayrıca doğrulanır.
- Source ID üzerinden farklı case verisine erişim engellenir.
- Background job payload'ı case ve tenant kimliklerini taşır.
- Cache anahtarları tenant ve case ile namespaced olur.

## 12. Pilot alan haritası

Ayıplı araç pilotunda zorunlu fact türleri:

- purchase_date
- sale_amount
- seller_identity
- buyer_identity
- vehicle_brand
- vehicle_model
- vehicle_plate
- vehicle_vin
- defect_type
- defect_discovery_date
- service_entry_date
- report_date
- report_number
- tramer_summary
- defect_notice_date
- notary_notice_date
- selected_remedy
- claimed_damage_amount

## 13. Kabul kriterleri

- Her kritik fact kaynak bağlantılıdır.
- Çelişkili fact doğrulanmış görünmez.
- Kullanıcı düzeltmesi eski kaydı kaybetmez.
- Eksik kategori değil somut değer bazında hesaplanır.
- Farklı case veya tenant verisi karışmaz.
- Kritik eksik varken dosya riski düşük olamaz.
- Bir hafıza revizyonu aynı input ile yeniden çalıştırıldığında duplicate kayıt oluşturmaz.
