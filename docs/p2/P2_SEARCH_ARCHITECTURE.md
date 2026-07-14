# P2 Hybrid Search Architecture

## 1. Amaç

Hibrit hukuk araması; anahtar kelime, tam metin, metadata ve semantik benzerlik sinyallerini birleştirerek doğrulanmış ve dosya bağlamına uygun kaynakları sıralar. Arama katmanı güvenilir kaynak omurgasının üzerine kurulur.

## 2. Arama türleri

- anahtar kelime
- tam ifade
- esas numarası
- karar numarası
- mevzuat numarası/madde
- semantik arama
- dosya bağlamlı arama
- benzer karar
- karşıt karar
- ilgili mevzuat
- ilgili doktrin

## 3. Sorgu akışı

1. Kullanıcı sorgusu alınır.
2. Tenant ve case bağlamı doğrulanır.
3. Sorgu niyeti sınıflandırılır.
4. Hukuki alan ve mesele adayları çıkarılır.
5. Filtreler normalize edilir.
6. Lexical ve semantic retrieval paralel çalışır.
7. Sonuçlar canonical source kimliğinde birleştirilir.
8. Kalite, doğrulama ve temporal filtreler uygulanır.
9. Dosya bağlamlı reranking yapılır.
10. Karşıt karar/olumsuz yön tespiti eklenir.
11. Sonuç açıklaması ve ilgili paragraf hazırlanır.

## 4. İndeksler

### 4.1 Lexical index

Alanlar:

- title
- normalized citation
- court/chamber
- case/decision number
- headings
- paragraph text
- legal topic
- keywords

### 4.2 Semantic index

Birim: SourceParagraph.

Metadata:

- source_id
- version_id
- paragraph_id
- source_type
- verification_status
- temporal_status
- court/chamber
- date
- legal topic
- embedding model/version

### 4.3 Metadata index

- exact citation lookup
- date range
- court/chamber
- source type
- verification status
- temporal validity

## 5. Sorgu normalizasyonu

- Türkçe küçük/büyük harf ve karakter normalizasyonu
- `E.`, `K.`, tarih ve daire formatlarının standardizasyonu
- mevzuat madde kalıbı çıkarımı
- hukuki eş anlamlılar
- typo toleransı
- stopword kontrolü

Normalizasyon kullanıcı sorgusunu değiştirmez; ayrı query plan olarak tutulur.

## 6. Hibrit retrieval

Önerilen ilk formül:

- lexical score: %35
- semantic score: %30
- source authority/verification: %15
- temporal relevance: %10
- case context relevance: %10

Ağırlıklar benchmark ile ayarlanır; sabit ürün kuralı değildir.

## 7. Reranking sinyalleri

Pozitif:

- verified_official/editor_verified
- aynı hukuki mesele
- aynı talep veya uyuşmazlık türü
- benzer olay örgüsü
- aynı sonuç yönü
- daha güncel karar
- ilgili paragrafın yüksek lexical eşleşmesi

Negatif:

- duplicate
- outdated/repealed
- düşük doğrulama
- alakasız teknik metin
- yalnız genel kavram eşleşmesi
- farklı hukuk alanı
- kullanıcının alakasız geri bildirimi

## 8. Dosya bağlamı

Dosya bağlamından kullanılabilecek güvenli alanlar:

- legal domain
- legal issue codes
- claim types
- verified facts
- selected remedies
- court/jurisdiction

Kullanılmaması gerekenler:

- doğrulanmamış çelişkili fact
- gereksiz kişisel veri
- belge tam metninin sorguya kontrolsüz eklenmesi

## 9. Benzer ve karşıt karar

Benzer karar:

- olay ve hukuki mesele benzerliği
- aynı/benzer talep
- benzer sonuç

Karşıt karar:

- aynı meselede farklı sonuç
- farklı ispat değerlendirmesi
- süre/ihbar/görev gibi engelleyici yaklaşım

Sonuç kartı karşıt yönü açıkça etiketler.

## 10. Sonuç açıklanabilirliği

Her sonuç için:

- neden bulundu
- hangi sorgu terimi veya mesele eşleşti
- dosyadaki hangi olaya bağlı
- ilgili paragraf
- doğrulama/güncellik
- kullanılabilir argüman
- karşı taraf lehine olası yön

sunulur.

Model yalnız açıklama üretir; source metadata deterministik sistemden gelir.

## 11. Filtreler

- source_type
- court
- chamber
- decision_date range
- case_number
- decision_number
- legal_domain
- legal_issue
- outcome_direction
- verification_status
- temporal_status
- official_only

## 12. Pagination ve kararlılık

- Cursor pagination
- Aynı query snapshot içinde deterministic order
- Index güncellemesi sırasında cursor version taşır
- Duplicate source version tek sonuç altında gruplanır

## 13. Cache

Cache key:

`tenant_scope|query_hash|filter_hash|case_context_version|index_version`

Kişisel case bağlamı içeren sonuçlar ortak cache'e yazılmaz.

## 14. Geri bildirim

Kullanıcı aksiyonları:

- ilgili
- alakasız
- karşıt karar olarak değerli
- yanlış metadata
- tekrar kayıt
- dilekçede kullanıldı

Geri bildirim doğrudan global ranking'i değiştirmez; kontrollü değerlendirme ve offline tuning verisi olur.

## 15. Benchmark

Hukuk alanları:

- tüketici
- kira
- iş
- icra
- aile
- ceza
- ticaret
- idare

Her senaryo:

- sorgu
- beklenen kaynaklar
- kabul edilebilir kaynaklar
- alakasız kaynaklar
- karşıt kaynaklar
- ilk 3 ve ilk 10 hedefi

İlk pilot hedefi:

- Recall@10 ≥ %85
- Precision@5 ≥ %70
- doğrulanmış kaynak oranı ilk 5'te ≥ %80
- duplicate oranı ilk 10'da ≤ %5

Hedefler beta verisiyle yeniden kalibre edilir.

## 16. Güvenlik

- Query logları hassas metin maskelemesi uygular.
- Arama tenant verisini başka tenant sonucuna karıştırmaz.
- Embedding servisinde minimum veri kullanılır.
- Prompt injection içeren kaynak paragrafı talimat sayılmaz.
- Resmî URL fetch işlemi SSRF korumalıdır.

## 17. API özeti

- POST `/search/legal`
- POST `/search/similar`
- POST `/search/opposing`
- GET `/search/suggestions`
- POST `/search/results/{result_id}/feedback`

Yanıt alanları:

- query_id
- index_version
- result_id
- source metadata
- paragraph snippet
- relevance breakdown
- explanation
- verification status
- temporal status

## 18. Kapanış kriterleri

- Exact citation araması deterministic çalışır.
- Hibrit sonuçlar benchmark ile ölçülür.
- Doğrulanmamış kaynak açıkça ayrılır.
- Karşıt kararlar gizlenmez.
- Aynı karar tekrarları bastırılır.
- Dosya bağlamı çelişkili fact'lere dayanmaz.
- Her sonuç kaynak ve paragraf kimliğine bağlıdır.

## 19. P2.7 Uygulanan Mimari

### 19.1 Exact-version trust path

Her adayın güven zinciri deterministik olarak çözülür:

```
resolve_version_verification_status(record_id, version_id, record.verification_status)
  → effective resolved status
    → index_eligibility(resolved_status)
      → IndexEligibility(eligible, weight)
```

Ağırlık skalası:
- `full_weight` → 1.0
- `reduced_weight` → 0.7
- `low_weight` → 0.4
- `historical_only` → 0.2

`eligible=false` olan adaylar sonuç kümesinden çıkarılır. Sağlayıcı kodu hiçbir zaman güven göstergesi olarak kullanılmaz; güven yalnız P2.6 zincirinden türetilir.

### 19.2 Sorgu dilbilgisi (Query Grammar)

Ayrıntılı belge: `P2_SEARCH_QUERY_GRAMMAR.md`.

- Deterministik, LLM tabanlı değil
- Operatörler: `+` (zorunlu), `-` (hariç), `""` (tam ifade)
- Boşluk = OR; hiçbir zaman zorunlu AND değil
- Zorunlu/hariç cümleleri hard constraint, sıralama ipucu değil
- Semantik retrieval hard constraint'leri bypass edemez
- Hatalı sözdizimi 422 semantic validation döner (sessiz fallback yok)
- Uygulama: `backend/app/services/search_query_grammar.py`

### 19.3 Lexical/semantic skorlama ve renormalizasyon

Normal mod (semantik mevcut):

| Sinyal | Ağırlık |
|---|---|
| Lexical | %35 |
| Semantic | %30 |
| Source authority | %15 |
| Temporal relevance | %10 |
| Case context | %10 |

Degraded mod (semantik yok):

| Sinyal | Ağırlık |
|---|---|
| Lexical | %50 |
| Source authority | %22 |
| Temporal relevance | %15 |
| Case context | %13 |
| Semantic | %0 |

Lexical skor: pozitif cümlelerin normalize edilmiş metinde alt-dize eşleşmesi veya token örtüşmesi (0.3 kısmi ağırlık). Tam ifade (`"..."`) alt-dize eşleşmesi ile tam puan alır.

Authority skoru `IndexEligibility.weight` ile eşlenir. Temporal: `current` → 1.0, `expired/repealed/superseded` → 0.1, diğer → 0.5.

### 19.4 Semantik opt-in ve degraded mod

- `search_semantic_enabled=false` → semantik retrieval devre dışı, skor ağırlıkları yeniden normalize
- `GEMINI_API_KEY` yok → `DisabledSearchEmbeddingProvider`, `semantic_available=false`
- Yanıtta `semantic_available` ve `degraded_mode` alanları istemciye bildirilir
- Degraded modda lexical-only sonuçlar döner; kullanıcı deneyimi bozulmaz

### 19.5 Gemini embedding sağlayıcı mimarisi

Soyutlama: `SearchEmbeddingProvider` (ABC).

Uygulamalar:
- `GeminiSearchEmbeddingProvider`: google-genai ile Gemini Embedding API. Model: `gemini-embedding-001`, boyut: 768. `RETRIEVAL_DOCUMENT` (kaynaklar) ve `RETRIEVAL_QUERY` (sorgu) task_type'ları ile.
- `DisabledSearchEmbeddingProvider`: semantik kapalıyken boş vektör döner.

Factory: `create_embedding_provider(settings)` → `search_semantic_enabled` ve `GEMINI_API_KEY` kontrolüne göre ilgili sağlayıcıyı döndürür.

Kaynak embedding'leri:
- `SourceParagraph.embedding_status` = `indexed` | `pending` | `failed`
- `SourceParagraph.embedding_model` / `embedding_version` / `embedding_dimension` / `embedding_vector_json`
- `embedding_vector_json`: JSON float listesi (P2.7 pilot sınırı)
- Semantic retrieval yalnız `embedding_status == "indexed"` olan paragrafları dikkate alır

### 19.6 Sorgu gizliliği (Query privacy)

Uygulama: `backend/app/services/search_privacy.py`.

- `query_hash` = HMAC-SHA256(domain=`"emsalist-query-hash|v1"`, message=`tenant_id:positive_clauses`)
- Ham sorgu metni `SearchQuery` tablosuna yazılmaz; `raw_query_transient` yalnız geçici planda bulunur
- `safe_query_summary` = `SearchQueryPlan.safe_summary()` → yalnız yapısal alanlar (operatör/metin değil): opsiyonel/zorunlu/hariç cümle sayıları, atıf adayı sayıları, madde adayı sayıları
- Hassas sorgu tespiti (`is_sensitive_query`): TC kimlik numarası, IBAN, e-posta, telefon, 32+ karakter token regex eşleşmesi → hassas sorgularda semantik retrieval atlanır
- Hiçbir embedding çağrısında ham sorgu metni veya kaynak metni günlüğe yazılmaz

### 19.7 Cursor/result imzalama

- Cursor: HMAC-SHA256(domain=`"emsalist-cursor|v1"`, payload) ile imzalanmış base64
  - Payload: `query_id`, `query_hash_binding`, `filter_hash`, `index_version`, `last_sort_key`
  - `query_hash_binding` cursor'ı sorguya bağlar; farklı sorguda cursor reddedilir (422)
- Result ID: HMAC-SHA256(domain=`"emsalist-result-id|v1"`, payload) ile imzalanmış base64
  - Payload: `qid`, `sid`, `svid`, `pid`, `iv`
  - Feedback endpoint'inde `verify_result_id` ile doğrulanır
- Cursor ve result ID hiçbir zaman ham sorgu içermez

### 19.8 Benzer arama semantiği

- Referans kaynağın tüm paragrafları birleştirilir (max 5000 karakter)
- Birleşik metin embedding'e gönderilir → `RETRIEVAL_QUERY`
- Tüm `indexed` kaynak paragraflar arasında cosine similarity > 0.4
- Referans kaynağın kendisi hariç tutulur
- Semantik sağlayıcı yoksa metadata benzerliğine düşer (aynı source_type/court)

### 19.9 Karşıt arama kanıt sınırı

- Yalnız `SourceRelationship` tablosundaki `contradicted_by` ve `argued_against_by` ilişkileri kullanılır
- LLM tabanlı karşıt karar üretimi yoktur
- İlişkiler P2.6 kanıt zincirinden gelir; uydurma karşıt karar oluşturulmaz
- Her karşıt sonuç `index_eligibility` filtresinden geçer
- `opposition_basis: "controlled_opposition_evidence"` veya `"no_controlled_opposition"`

### 19.10 Embedding provenance

Her embedding vektörü aşağıdaki metadata ile birlikte saklanır:
- `embedding_model`: model adı (örn. `gemini-embedding-001`)
- `embedding_version`: versiyon etiketi (örn. `p2.7-embedding-1`)
- `embedding_dimension`: vektör boyutu (örn. 768)

Arama sırasında yalnızca eşleşen `embedding_status == "indexed"` paragraflar taranır. Model/versiyon/boyut uyuşmazlığı olan embedding'ler retrieval kapsamına alınmaz.

### 19.11 P2.7 pilot sınırlamaları

- **JSON vektörler**: Embedding vektörleri `TEXT` sütununda JSON float dizisi olarak saklanır. Native pgvector indeksi kullanılmaz.
- **Bounded candidate pool**: Semantik retrieval `MAX_CANDIDATE_POOL` (5000 × 2 = 10000) ile sınırlıdır. Tam veritabanı taraması yerine sınırlı sayıda aday üzerinde cosine similarity hesaplanır. Bu, gerçek pgvector ANN indeksine geçiş öncesi pilot sınırlamasıdır.
- **Exact filtre sonrası**: Tüm filtreler (source_type, court, tarih, official_only) ve hard dilbilgisi kısıtlamaları candidate retrieval sonrası bellekte uygulanır; DB düzeyinde pushdown yoktur.
