# P2.0 Final Review

## 1. İnceleme kapsamı

P2.0 planlama paketi; ürün kapsamı, kullanıcı akışları, mobil mimari, veri modeli, API, güvenlik, belge hattı, kaynak omurgası, arama, hukuki reasoning, kaynaklı dilekçe, UYAP, bildirim, test, gözlemlenebilirlik, risk ve release stratejisi bakımından çapraz kontrol edilmiştir.

## 2. Sonuç

Engelleyici kapsam veya mimari çelişki tespit edilmemiştir.

Aşağıdaki bağımlılık sırası bütün belgelerde korunmaktadır:

1. Mobil shell ve istemci temeli
2. Kimlik/workspace
3. Case/chat
4. Yapılandırılmış case memory
5. Document pipeline
6. Trusted source backbone
7. Hybrid search
8. Legal issue graph/reasoning
9. Grounded drafting
10. UYAP ve notifications
11. Beta/App Store

## 3. Doğrulanan guardrail'ler

- P2.0 yalnız dokümantasyon içerir.
- P1.14 tag ve release değişmez.
- Main'e doğrudan push yapılmaz.
- Doğrulanmamış kaynak doğrulanmış gibi sunulmaz.
- Citation model tarafından serbest metin olarak üretilmez.
- User, document ve UYAP kaynakları ayrı statü taşır.
- Çelişkili bilgi otomatik kesinleştirilmez.
- Kritik eksikler varken risk low olamaz.
- Tenant/case object authorization bütün katmanlarda zorunludur.
- Belge ve dilekçe tam metni loglanmaz.
- UYAP ilk sürümü outbound işlem içermez.
- Mobile UI doğrudan HTTP client çağırmaz.
- Offline cache belge bytes saklamaz.

## 4. Çapraz belge kontrolleri

### Case memory ↔ Data model ↔ API

Fact, timeline, missing information, contradiction, risk, deadline ve legal issue varlıkları ile bunların API komutları uyumludur.

### Document pipeline ↔ Security ↔ Tests

MIME, hash, size, malware, sandbox, quarantine ve locator kontrolleri güvenlik/test belgelerinde karşılık bulur.

### Source backbone ↔ Search ↔ Drafting

Canonical source, version, paragraph, verification, temporal status ve source usage zinciri arama ve drafting katmanlarında korunur.

### Mobile ↔ API ↔ Offline

OpenAPI generated client, repository adapter, secure token storage, idempotency ve sınırlı encrypted cache kararları uyumludur.

### UYAP ↔ Notification ↔ Privacy

Credential saklama, safe push payload, deep-link authorization ve feature flag kuralları uyumludur.

## 5. Kabul edilmiş başlangıç kararları

- `/mobile` Flutter dizini
- `com.emsalist.app` production bundle hedefi
- Personal + office workspace
- E-posta/parola; Apple Sign In beta öncesi
- 25 MB beta belge sınırı
- 30 gün soft-delete
- Backend UDF sandbox
- Provider-agnostic AI
- Notification outbox
- 15 avukatlık ücretsiz kapalı beta
- AB/AEA teknik başlangıç; beta öncesi veri aktarım/bölge hukuk kapısı

## 6. P2.1'e taşınacak ADR/spike'lar

Bunlar P2.0 eksikliği değil, uygulama düzeyi seçimlerdir:

- Flutter state management kütüphanesi
- Router kütüphanesi
- Local encrypted database kütüphanesi
- Crash/analytics sağlayıcısı
- Semantic vector backend
- Object storage sağlayıcısı

Her biri ilgili feature PR'ında ADR ile kesinleşir.

## 7. P2.0 kapanış önerisi

PR aşağıdaki koşullarda ready/merge olabilir:

- Bütün plan belgeleri repository'de
- Decision register'da kritik açık karar yok
- PR diff yalnız `docs/p2/**`
- Branch main ile conflict taşımıyor
- Gerekli CI kontrolleri success veya docs-only nedeniyle uygulanmıyor

## 8. Sonraki branch

```text
feat/p2.1-mobile-shell
```

P2.1 yalnız Flutter shell, flavor temeli, tema, navigation, chat composer, case drawer mock, UYAP status mock ve mobil test altyapısını içerir. Auth veya gerçek backend feature kapsamına girmez.
