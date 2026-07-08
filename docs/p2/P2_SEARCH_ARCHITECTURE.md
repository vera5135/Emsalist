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
