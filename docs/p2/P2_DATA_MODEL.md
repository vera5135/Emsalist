# P2 Data Model

## 1. Amaç

Bu belge P2 domain varlıklarını, ana ilişkileri, tenant/case izolasyonunu, sürümleme ve silme kurallarını tanımlar. Fiziksel PostgreSQL şeması uygulama aşamasında migration'larla kesinleşir.

## 2. Domain sınırları

- Identity & Workspace
- Case & Collaboration
- Conversation
- Case Memory
- Document Processing
- Legal Sources
- Search
- Legal Issue Graph
- Drafting
- UYAP
- Notification
- Audit & Retention

## 3. Identity & Workspace

### Workspace

- id
- type: personal, office
- name
- status
- data_region
- retention_policy_id
- created_at

### User

- id
- email_normalized
- display_name
- status
- created_at

### WorkspaceMember

- id
- workspace_id
- user_id
- role
- permissions_json
- status
- joined_at

### DeviceSession

- id
- user_id
- workspace_id
- refresh_token_hash
- device_name
- platform
- expires_at
- revoked_at

## 4. Case & Collaboration

### Case

Ana tenant alanı `workspace_id` olarak modellenir; backend mevcut `tenant_id` adını kullanmaya devam edebilir. API'de kavram `workspace` olarak sunulur.

### CaseMember

- case_id
- workspace_id
- user_id
- role
- permissions_override
- revoked_at

### CaseActivity

- case_id
- actor_id
- activity_type
- target_type
- target_id
- safe_metadata
- created_at

## 5. Conversation

### Conversation

- id
- workspace_id
- case_id
- title
- status
- created_by
- created_at

### Message

- id
- workspace_id
- case_id
- conversation_id
- role
- content_encrypted_or_private
- content_hash
- status
- parent_message_id
- client_request_id
- model_run_id
- created_at
- completed_at

### MessageAttachment

- message_id
- document_id
- relation_type

## 6. Case Memory

Detaylar `P2_CASE_MEMORY_MODEL.md` içindedir.

Ana tablolar:

- case_parties
- case_facts
- timeline_events
- claims
- defenses
- evidence
- missing_information
- contradictions
- risks
- deadlines
- legal_issues
- memory_revisions

## 7. Document Processing

### Document

- id
- workspace_id
- case_id
- original_filename
- storage_key
- mime_type
- size_bytes
- sha256
- document_type
- status
- uploaded_by
- created_at
- deleted_at

### DocumentAnalysisRun

- id
- document_id
- pipeline_version
- status
- input_hash
- output_hash
- model metadata
- timestamps

### DocumentFinding

- id
- analysis_run_id
- document_id
- finding_type
- value_json
- normalized_value_json
- locator_json
- confidence
- verification_status
- linked_memory_record_id

### DocumentArtifact

- id
- document_id
- artifact_type: extracted_text, preview, thumbnail, ocr_json
- storage_key
- hash
- created_at

## 8. Legal Sources

Ana tablolar:

- source_records
- source_versions
- source_paragraphs
- source_verifications
- source_relationships
- source_usages
- source_ingestion_runs

Global kaynak tabloları tenant dışı olabilir; ancak `source_usage` tenant/case bağlıdır.

## 9. Search

### SearchQuery

Hassas sorgu tam metni zorunlu olarak kalıcı tutulmaz.

- id (String(32), PK)
- tenant_id (String(32), FK → tenants.id)
- user_id (String(32), FK → users.id)
- case_id (String(32), FK → cases.id, nullable)
- query_hash (String(64), index): domain-separated HMAC-SHA256 hash. Ham sorgu yerine `tenant_id:positive_clauses` üzerinden hesaplanır. Domain: `"emsalist-query-hash|v1"`.
- safe_query_summary (JSON): yalnız yapısal istatistikler (cümle sayıları, atıf adayı sayıları). Ham metin, operatörler veya normalize edilmiş metin içermez.
- filters_json (JSON): uygulanan filtreler (source_types, date_range, court, official_only)
- index_version (Integer): sorgu anındaki en yeni SourceParagraph.created_at timestamp'i. Cursor binding için kullanılır.
- created_by → User
- created_at

### SearchFeedback

- id (String(32), PK)
- search_query_id (String(32), FK → search_queries.id, index)
- result_id (String(256), index): HMAC-signed result identifier
- source_id (String(32)): kaynak kaydı ID
- feedback_type (String(30)): `relevant`, `not_relevant`, `authoritative`, `outdated`, `incorrect`
- user_id (String(32), FK → users.id)
- created_at

### SourceParagraph embedding alanları (P2.7)

Aşağıdaki alanlar `source_paragraphs` tablosuna P2.7 ile eklenmiştir:

- embedding_status (String(20), default=`"pending"`): `pending` | `indexed` | `failed`
- embedding_model (String(60), nullable): model adı (örn. `gemini-embedding-001`)
- embedding_version (String(40), nullable): versiyon etiketi (örn. `p2.7-embedding-1`)
- embedding_dimension (Integer, nullable): vektör boyutu (örn. 768)
- embedding_vector_json (Text, nullable): JSON float dizisi olarak embedding vektörü. P2.7 pilot sınırı: pgvector native tipi yerine JSON/Text.
- embedding_updated_at (DateTime tz, nullable)

Semantic retrieval yalnızca `embedding_status == "indexed"` olan paragrafları kapsar.

## 10. Legal Issue Graph

### LegalIssue

Case memory içindedir.

### IssueEdge

- id
- workspace_id
- case_id
- from_type
- from_id
- relation_type
- to_type
- to_id
- source
- confidence
- status

Relation örnekleri:

- supported_by
- contradicted_by
- requires
- related_to
- governed_by
- argued_against_by
- drafted_in

## 11. Drafting

### Draft

- id
- workspace_id
- case_id
- draft_type
- title
- status
- current_revision_id
- created_by
- reviewer_id
- approved_by
- created_at
- updated_at

### DraftRevision

- id
- draft_id
- revision_number
- parent_revision_id
- content_hash
- source_fingerprint
- validation_summary_json
- created_by
- created_at

### DraftSection

- id
- draft_revision_id
- section_type
- order_index
- heading

### DraftParagraph

Detaylar grounded drafting belgesindedir.

### DraftComment

- draft_id
- revision_id
- paragraph_id nullable
- author_id
- body
- status
- created_at

### ExportArtifact

- draft_revision_id
- format
- storage_key
- hash
- template_version
- created_at

## 12. UYAP

### UyapConnection

- id
- workspace_id
- user_id
- status
- encrypted_credential_reference
- last_checked_at
- last_success_at
- created_at
- revoked_at

### UyapSyncRun

- id
- connection_id
- status
- cursor
- started_at
- completed_at
- safe_error_code

### UyapMovement

Detaylar UYAP belgesindedir.

### UyapCaseMatch

- movement/file reference
- case_id
- match_method
- confidence
- confirmed_by

## 13. Notification

### Notification

- id
- workspace_id
- user_id
- case_id nullable
- type
- priority
- title
- safe_body
- target_type
- target_id
- read_at
- created_at

### NotificationPreference

- user_id
- workspace_id
- category
- enabled
- quiet_hours

### PushDeviceToken

- user_id
- platform
- token_encrypted
- environment
- revoked_at

## 14. Audit & Retention

Mevcut P1 modelleri korunur ve genişletilir:

- audit_events
- retention_policies
- deletion_requests
- legal_holds
- purge_runs
- purge_items

AuditEvent belge veya dilekçe tam metni taşımaz.

## 15. İlişki özeti

```text
Workspace
 ├─ Members
 ├─ Cases
 │   ├─ CaseMembers
 │   ├─ Conversations ─ Messages
 │   ├─ Documents ─ AnalysisRuns ─ Findings
 │   ├─ CaseMemory records
 │   ├─ LegalIssues ─ IssueEdges
 │   ├─ SourceUsages ─ Global Sources
 │   ├─ Drafts ─ Revisions ─ Paragraphs
 │   ├─ UyapMovements
 │   └─ Notifications
 └─ Retention/Audit
```

## 16. Kimlik ve anahtar stratejisi

- Opaque UUID/ULID benzeri string
- Kullanıcıya sıralı DB ID gösterilmez
- Canonical source key ayrı unique alandır
- Client request ID idempotency için unique scope taşır

## 17. Tenant/case izolasyonu

- Tenant bağlı her tabloda workspace_id/tenant_id bulunur.
- Case child tablolarında case_id yanında tenant doğrulaması yapılır.
- Composite index ve gerektiğinde composite FK değerlendirilir.
- Repository katmanı tenant bağlamı olmadan sorgu kabul etmez.
- Row-level security gelecek savunma katmanı olarak değerlendirilebilir; uygulama yetkilendirmesinin yerine geçmez.

## 18. Sürümleme

Optimistic lock kullanan tablolar:

- cases
- case_facts
- timeline_events
- claims
- legal_issues
- drafts
- draft_paragraphs

Her PATCH beklenen version taşır.

## 19. Soft delete ve purge

- Cases, documents, drafts soft-delete olur.
- Child kayıtlar varsayılan görünümden çıkarılır.
- Legal hold fiziksel purge'ü engeller.
- Purge sırası FK bağımlılığına göre deterministik olur.
- Object storage artifact'leri DB purge ile koordineli silinir.

## 20. Şifreleme sınıfları

Uygulama alan şifrelemesi gerektirebilecek veriler:

- kimlik referansları
- iletişim bilgileri
- credential/token referansları
- push token

Tam belge ve mesaj içeriği private storage/database encryption ile korunur; loglarda yer almaz.

## 21. İndeksleme

Öncelikli indeksler:

- workspace_id + updated_at
- workspace_id + case_id
- case_id + fact_type
- case_id + verification_status
- document_id + analysis_run_id
- source canonical_key
- source verification/temporal status
- deadline due_at + status
- notification user_id + read_at

## 22. Migration ilkeleri

- Her schema değişikliği Alembic migration
- Upgrade/downgrade veya açık irreversible gerekçe
- Büyük backfill ayrı background task
- Lock süresi ölçülür
- Production-only PostgreSQL doğrulaması
- Backup/restore ve migration CI kapısı korunur

## 23. Kapanış kriterleri

- Tüm P2 domain'leri tablo/ilişki düzeyinde tanımlıdır.
- Global kaynak ile tenant kullanım kaydı ayrıdır.
- Mesaj, belge ve draft içerikleri audit log'a taşınmaz.
- Soft delete/legal hold/purge ilişkisi nettir.
- Optimistic locking ve idempotency alanları tanımlıdır.
- Case child kayıtlarının tenant izolasyonu sağlanabilir durumdadır.
