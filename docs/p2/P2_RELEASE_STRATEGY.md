# P2 Release Strategy

## 1. Amaç

Bu belge P2 branch, PR, milestone, beta ve App Store yayın sürecini tanımlar.

## 2. Branch modeli

- `main`: daima yayınlanabilir ve korumalı
- `chore/p2.0-planning-baseline`
- `feat/p2.1-mobile-shell`
- `feat/p2.2-auth-session`
- `feat/p2.3-case-chat`
- `feat/p2.4-case-memory`
- `feat/p2.5-document-pipeline`
- `feat/p2.6-source-backbone`
- `feat/p2.7-hybrid-search`
- `feat/p2.8-legal-issue-graph`
- `feat/p2.9-grounded-drafting`
- `feat/p2.10-uyap-bridge`
- `release/p2-beta`

Doğrudan `main` push yapılmaz.

## 3. PR kuralları

Her PR:

- tek aşama veya açıkça sınırlı iş paketi
- kabul kriteri
- test kanıtı
- migration etkisi
- güvenlik etkisi
- rollback yöntemi
- ekran görüntüsü/demo gerekiyorsa artifact
- güncel dokümantasyon

Taşınan TODO ve riskler PR açıklamasında listelenir.

## 4. Merge yöntemi

- Küçük, tek amaçlı feature PR: squash merge
- Büyük migration veya audit gerektiren seri: gerekçeli merge commit değerlendirilebilir
- Force push main'e yasak
- CI tamamen yeşil olmadan merge yok

## 5. Milestone tag'leri

Öneri:

- `p2.0-planning-complete`
- `p2.1-mobile-shell-complete`
- `p2.3-case-chat-complete`
- `p2.5-document-pipeline-complete`
- `p2.7-search-complete`
- `p2.9-grounded-drafting-complete`
- `p2-beta.1`

Her küçük PR için tag gerekmez; önemli acceptance kapıları taglenir.

## 6. Ortamlar

- development
- CI ephemeral
- staging
- beta/production

Ayrı:

- bundle ID
- API endpoint
- credentials
- push environment
- object storage namespace
- analytics environment

## 7. Mobil dağıtım

### P2.1–P2.3

- iOS simulator CI
- internal development build

### P2.4–P2.9

- internal TestFlight
- davetli teknik kullanıcılar

### P2.11

- kapalı avukat beta
- staged TestFlight groups
- App Store production candidate

## 8. Feature flags

Zorunlu feature flags:

- AI provider/use
- document analysis
- semantic search
- grounded drafting
- UYAP Bridge
- notifications
- experimental source types

Flag'ler güvenlik kontrolünü bypass etmez.

## 9. Database release

- Expand/contract migration
- Backward-compatible API window
- Büyük backfill ayrı job
- Rollback veya forward-fix planı
- Backup ön kontrolü
- Migration/restore CI

## 10. Release candidate kapıları

- Full backend suite
- Mobile build/widget/golden/integration
- OpenAPI compatibility
- Migration and backup/restore
- Security scans
- Document fixture suite
- Search benchmark
- AI grounding evaluation
- E2E pilot
- Staging smoke
- Privacy/security checklist

## 11. Rollback

Backend:

- önceki image
- migration compatibility plan
- feature flag disable

Mobile:

- server-side feature flag
- minimum supported version policy
- emergency build only when necessary

UYAP/AI/search gibi modüller bağımsız kapatılabilir.

## 12. Beta planı

- 15 avukat
- ücretsiz davetli beta
- tüketici/ayıplı araç pilotu öncelikli
- gerçek dosya kullanımı için açık gizlilik/onboarding
- haftalık geri bildirim
- kritik incident escalation

## 13. Beta çıkış kriterleri

- E2E pilot başarı oranı hedefi
- Kritik security açığı yok
- Kaynak uydurma blocker yok
- Crash-free sessions hedefi
- Arama benchmark kabulü
- Belge analiz başarı oranı
- Destek yükü ve maliyet ölçümü
- Veri silme akışı doğrulandı

## 14. App Store hazırlığı

- Bundle IDs
- signing/certificates
- privacy manifest ve izin açıklamaları
- hesap silme erişimi
- support/privacy URLs
- screenshots
- review notes
- demo account gerekirse
- push notification entitlement

## 15. Release notes

Her release:

- kullanıcı değeri
- teknik değişiklik
- migration
- bilinen sınırlamalar
- güvenlik/gizlilik etkisi
- rollback
- source commit

## 16. Kapanış kriterleri

- Her milestone acceptance kanıtıyla kapanır.
- Main green ve protected kalır.
- P1.14 tag/release değiştirilmez.
- Beta feature flags ile kontrollü açılır.
- Production release geri alınabilir veya modül bazında kapatılabilir.
