# P2 Backlog

## 1. Amaç

Bu backlog, P2'yi aşama ve bağımlılık bazında uygulanabilir iş paketlerine böler. Her iş paketi ayrı issue veya PR'a dönüşebilir.

## 2. Öncelik

- P0: aşama kapatıcı / güvenlik / veri bütünlüğü
- P1: ana kullanıcı değeri
- P2: kalite ve kullanılabilirlik
- P3: sonraki iterasyon

## 3. P2.0 — Planning baseline

- [x] P0 Master plan
- [x] P0 Decision register
- [x] P0 Acceptance matrix
- [x] P0 Product scope
- [x] P0 User flows
- [x] P0 Information architecture
- [x] P0 Conversation design
- [x] P0 Case memory model
- [x] P0 Document pipeline
- [x] P0 Trusted source backbone
- [x] P0 Search architecture
- [x] P0 Grounded drafting
- [x] P0 UYAP scope
- [x] P0 API contract
- [x] P0 Data model
- [x] P0 Security/privacy
- [x] P0 Test strategy
- [x] P1 Observability
- [x] P0 Risk register
- [x] P1 Release strategy
- [ ] P0 Final consistency review
- [ ] P0 Resolve/accept remaining decisions
- [ ] P0 Mark PR ready and merge

## 4. P2.1 — Mobile shell

### Repository and tooling

- [ ] P0 Create `/mobile` Flutter project
- [ ] P0 Configure dev/staging/prod flavors
- [ ] P0 Add iOS bundle identifiers
- [ ] P0 Add Flutter lint, format, analyze, test CI
- [ ] P1 Add generated API client placeholder

### Design system

- [ ] P0 ThemeMode.system
- [ ] P1 Light/dark palettes
- [ ] P1 Typography and spacing tokens
- [ ] P1 Accessible semantic labels
- [ ] P1 Loading/error/empty components

### Shell

- [ ] P0 Chat screen shell
- [ ] P0 Composer and keyboard behavior
- [ ] P0 Case drawer mock
- [ ] P1 Case summary bottom sheet mock
- [ ] P1 UYAP status icon and sheet mock
- [ ] P1 Appearance settings
- [ ] P1 Offline banner

### Tests

- [ ] P0 Small iPhone overflow tests
- [ ] P1 Golden light/dark
- [ ] P1 Dynamic Type
- [ ] P1 VoiceOver labels

## 5. P2.2 — Auth and workspace

- [ ] P0 Login API/mobile
- [ ] P0 Secure token storage
- [ ] P0 Refresh rotation
- [ ] P0 Logout/revoke
- [ ] P0 Workspace list/select
- [ ] P0 Personal workspace auto-create
- [ ] P1 Device session list
- [ ] P1 Password reset/email verification
- [ ] P1 Apple Sign In
- [ ] P2 MFA
- [ ] P0 Authorization/isolation tests

## 6. P2.3 — Case and chat

- [ ] P0 Case create/list/detail/update
- [ ] P0 Case membership policies
- [ ] P0 Conversation/message persistence
- [ ] P0 Message idempotency
- [ ] P0 Async response status
- [ ] P1 Retry and offline queue
- [ ] P1 Drawer real data
- [ ] P1 Case archive/restore
- [ ] P1 Activity history
- [ ] P0 Cross-case leakage tests

## 7. P2.4 — Case memory

- [ ] P0 Alembic models/migrations
- [ ] P0 Fact source and verification model
- [ ] P0 Timeline
- [ ] P0 Missing information engine
- [ ] P0 Contradiction engine
- [ ] P0 Risk rules
- [ ] P0 Deadline proposal/confirmation
- [ ] P0 Memory revision/idempotency
- [ ] P1 Case summary UI
- [ ] P1 Fact edit/confirm/reject UI
- [ ] P0 Ayıplı araç field profile

## 8. P2.5 — Document pipeline

- [ ] P0 Upload session and authorization
- [ ] P0 MIME/hash/size/path controls
- [ ] P0 Private object storage
- [ ] P0 Malware/quarantine integration
- [ ] P0 Async job orchestration
- [ ] P0 PDF/DOCX/TXT extraction
- [ ] P0 UDF backend parser sandbox
- [ ] P1 Image OCR
- [ ] P0 Finding locator and versioning
- [ ] P0 Confirm/reject workflow
- [ ] P1 Mobile upload progress/retry
- [ ] P0 Security fixture suite

## 9. P2.6 — Trusted source backbone

- [ ] P0 SourceRecord/Version/Paragraph schema
- [ ] P0 Canonical key and dedupe
- [ ] P0 Official URL/hash provenance
- [ ] P0 Verification statuses
- [ ] P0 Temporal validity
- [ ] P0 Source usage traceability
- [ ] P1 Ingestion adapter framework
- [ ] P1 Editor review queue
- [ ] P1 Official source tracking
- [ ] P0 Deterministic citation renderer
- [ ] P0 Source poisoning/SSRF tests

## 10. P2.7 — Hybrid search

- [ ] P0 Exact citation lookup
- [ ] P0 PostgreSQL lexical/full-text baseline
- [ ] P0 Vector/semantic index decision and implementation
- [ ] P0 Hybrid fusion
- [ ] P0 Metadata filters
- [ ] P1 Case-context reranking
- [ ] P1 Similar decisions
- [ ] P1 Opposing decisions
- [ ] P0 Search benchmark corpus
- [ ] P0 Recall/precision CI report
- [ ] P1 Result explanation UI

## 11. P2.8 — Legal issue graph

- [ ] P0 LegalIssue and IssueEdge model
- [ ] P0 Issue extraction
- [ ] P0 Claim/evidence/source links
- [ ] P0 Burden of proof
- [ ] P1 Opposing arguments
- [ ] P1 Graph versioning
- [ ] P1 Mobile issue view
- [ ] P0 Unsupported claim detection

## 12. P2.9 — Grounded drafting

- [ ] P0 Draft/readiness schema
- [ ] P0 Draft plan workflow
- [ ] P0 Paragraph grounding metadata
- [ ] P0 Source/fact validation
- [ ] P0 Consistency checks
- [ ] P0 Revision model
- [ ] P1 Review/approval workflow
- [ ] P0 DOCX export
- [ ] P1 PDF export
- [ ] P1 Office templates
- [ ] P0 Hallucinated citation blocker
- [ ] P0 Pilot E2E draft

## 13. P2.10 — UYAP and notifications

- [ ] P0 Adapter/security spike
- [ ] P0 Connection secret storage
- [ ] P0 Status and sync model
- [ ] P0 Movement dedupe/cursor
- [ ] P0 Case matching
- [ ] P0 Document import
- [ ] P0 Feature flag
- [ ] P0 No-secret logging tests
- [ ] P1 Deadline proposal
- [ ] P1 APNs push registration
- [ ] P1 Notification outbox
- [ ] P1 Quiet hours/preferences

## 14. P2.11 — Beta and App Store

- [ ] P0 Security review
- [ ] P0 Data region/privacy legal review
- [ ] P0 Account/data deletion E2E
- [ ] P0 Crash/performance monitoring
- [ ] P0 Full pilot E2E
- [ ] P0 Search/AI evaluation report
- [ ] P1 TestFlight groups
- [ ] P1 Onboarding/tutorial
- [ ] P1 App Store privacy metadata
- [ ] P1 Screenshots/review notes
- [ ] P0 Go/no-go review

## 15. Dependency rules

- P2.4, P2.3 olmadan başlayamaz.
- P2.5, case/document authorization olmadan merge olamaz.
- P2.7, P2.6 canonical/verification olmadan tamamlanamaz.
- P2.8, P2.4 ve P2.6 verilerine bağlıdır.
- P2.9, P2.6–P2.8 kapıları olmadan beta-ready olamaz.
- P2.10 outbound işlem içermez.
- P2.11 kritik riskler açıkken kapanamaz.

## 16. Issue şablonu

Her backlog işi issue'a çevrilirken:

- Problem
- Scope
- Out of scope
- Dependencies
- Acceptance criteria
- Security/privacy impact
- Migration impact
- Test plan
- Rollback
- Documentation

alanlarını taşımalıdır.
