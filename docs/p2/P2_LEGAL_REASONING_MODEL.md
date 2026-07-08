# P2 Legal Reasoning Model

## 1. Amaç

Bu belge, Emsalist'in dosyadaki olay, iddia, savunma, delil, hukuki mesele, kaynak ve riskleri nasıl yapılandıracağını tanımlar. Amaç otonom hüküm vermek değil, avukatın analizini açıklanabilir ve kaynak bağlantılı biçimde desteklemektir.

## 2. Temel bileşenler

- Fact
- Timeline Event
- Claim
- Defense
- Evidence
- Legal Issue
- Legal Rule
- Burden of Proof
- Counterargument
- Risk
- Source Paragraph
- Draft Paragraph

## 3. Hukuki mesele ağacı

Örnek ayıplı araç dosyası:

```text
Ayıplı araç uyuşmazlığı
 ├─ Satış ilişkisinin varlığı
 ├─ Ayıbın varlığı
 ├─ Ayıbın gizli/açık olması
 ├─ Teslim tarihinde mevcut olması
 ├─ Süresinde ihbar
 ├─ Seçimlik hakkın koşulları
 ├─ Zarar ve illiyet
 ├─ Görev/yetki
 └─ İspat ve delil yeterliliği
```

Her düğüm ayrı LegalIssue kaydıdır.

## 4. Mesele durumu

- proposed
- accepted
- disputed
- unsupported
- satisfied
- failed
- needs_review

Asistan önerisi `proposed` başlar; kullanıcı veya doğrulama kurallarıyla ilerler.

## 5. İddia değerlendirme yapısı

Her Claim için:

- iddia metni
- ileri süren taraf
- gerekli unsurlar
- destekleyen fact/event
- destekleyen evidence
- karşı delil
- ilgili legal issue
- uygulanabilir kaynak
- ispat yükü
- eksik bilgi
- risk
- değerlendirme statüsü

## 6. Rule application

Hukuki kural uygulaması üç katmanlıdır:

1. Rule: doğrulanmış mevzuat veya içtihat ilkesi
2. Facts: yalnız doğrulanmış veya açıkça statülü dosya bilgisi
3. Analysis: kural ile olgu arasındaki açıklanabilir bağ

Model analysis üretir; rule metadata ve citation deterministik sistemden gelir.

## 7. İspat yükü

Alanlar:

- issue_id
- burden_party_id
- burden_type
- required_standard
- legal_source_refs
- evidence_status
- notes

İspat yükü kaynaksız kesinleştirilmez.

## 8. Delil yeterliliği

Durumlar:

- supported
- partially_supported
- unsupported
- contradicted
- inadmissibility_risk
- authenticity_risk

Sistem delilin hukuki kabul edilebilirliği konusunda kesin karar vermez; risk ve kaynak sunar.

## 9. Karşı argüman

Her ana mesele için en az şu sorular değerlendirilir:

- Karşı taraf bu olguyu nasıl farklı yorumlayabilir?
- Hangi eksik delili kullanabilir?
- Hangi karşıt içtihat mevcut?
- Süre/usul engeli var mı?
- Talebin kapsamı aşırı mı?

Karşı argümanlar kullanıcıdan gizlenmez.

## 10. Confidence ve certainty

Confidence yalnız model teknik güvenidir; hukuki kesinlik değildir.

UI statüleri:

- güçlü destek
- kısmi destek
- belirsiz
- çelişkili
- kaynak eksik

Yüzde tek başına gösterilmez; gerekçe bulunur.

## 11. Reasoning run

`LegalReasoningRun`:

- id
- case_id
- memory_revision_id
- source_fingerprint
- model/provider version
- prompt version
- output hash
- status
- created_at

Yeni fact/source değişiminde reasoning stale olur ve yeniden çalıştırılır.

## 12. Graph edges

- fact_supports_issue
- fact_contradicts_issue
- evidence_supports_claim
- evidence_contradicts_claim
- source_governs_issue
- source_supports_argument
- source_opposes_argument
- issue_requires_issue
- issue_affects_risk
- issue_drafted_in_paragraph

## 13. Güvenlik kuralları

- Çelişkili fact analysis girdisinde açık statü taşır.
- Doğrulanmamış source kesin rule olamaz.
- Model farklı case verisini kullanamaz.
- Kaynak metnindeki talimatlar çalıştırılmaz.
- Reasoning trace kullanıcıya ham chain-of-thought olarak sunulmaz; kısa gerekçe ve dayanak gösterilir.

## 14. Kullanıcı kontrolü

Kullanıcı:

- mesele kabul/reddet
- mesele birleştir/böl
- delil bağlantısı ekle/çıkar
- karşı argüman ekle
- ispat yükü kaydını incele
- analizi yeniden çalıştır

## 15. API özeti

- GET `/cases/{case_id}/legal-issues`
- POST `/cases/{case_id}/legal-issues/rebuild`
- PATCH `/legal-issues/{issue_id}`
- GET `/legal-issues/{issue_id}/graph`
- POST `/legal-issues/{issue_id}/evidence-links`
- POST `/legal-issues/{issue_id}/source-links`
- GET `/cases/{case_id}/reasoning-runs`

## 16. Pilot kabul kriterleri

Ayıplı araç pilotunda:

- ana ve alt meseleler doğru ayrılır
- ihbar/süre meselesi eksik tarihle belirsiz görünür
- ayıp iddiası ekspertiz ve servis kaydıyla bağlanır
- karşıt argüman oluşturulur
- en az bir mevzuat ve içtihat kaynağı issue'ya bağlanır
- unsupported claim açıkça işaretlenir
- draft paragraph issue/fact/evidence/source zincirini taşır
