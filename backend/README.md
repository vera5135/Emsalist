# Emsalist Backend

Emsalist'in ilk aşama FastAPI backend'idir. Olay özetini kural tabanlı olarak
analiz eder, Yargıtay karar araması için sorgular üretir ve istemcinin sağladığı
mock kararları metin benzerliğine göre sıralar. Ayrıca Playwright üzerinden
Yargıtay'ın kamuya açık karar arama sayfasına bağlanır. LLM çağrısı yapmaz.

## Kurulum ve çalıştırma

Python 3.11 veya daha yeni bir sürüm önerilir.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m uvicorn app.main:app --reload
```

Playwright Python paketi ile Chromium tarayıcısı ayrı kurulur; bu nedenle
`python -m playwright install chromium` adımı gereklidir.

API dokümantasyonu servis başladıktan sonra `http://127.0.0.1:8000/docs`, sağlık
kontrolü ise `http://127.0.0.1:8000/health` adresindedir.

## Örnek akış

### 1. Olayı analiz et

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/case/analyze `
  -ContentType 'application/json' `
  -Body '{"case_text":"Boşanma sonrası davalı lehine yoksulluk nafakasına hükmedildi. Davalı daha sonra işe girdi ve düzenli maaş almaya başladı. Müvekkilin geliri ise azaldı ve nafakanın kaldırılması, mümkün değilse indirilmesi isteniyor."}'
```

### 2. Arama sorguları üret

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/search/build `
  -ContentType 'application/json' `
  -Body '{"case_text":"Nafaka alacaklısı işe girdi, yükümlünün geliri azaldı.","legal_topic":"Nafakanın kaldırılması veya indirilmesi","legal_keywords":["yoksulluk nafakası","ekonomik durum değişikliği","TMK 176"]}'
```

### 3. Mock kararları sırala

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/decisions/rank `
  -ContentType 'application/json' `
  -Body '{"case_text":"Nafaka alacaklısı işe girdi ve düzenli maaş almaya başladı. Nafaka yükümlüsünün geliri azaldı.","decisions":[{"source":"mock","court":"Yargıtay 2. Hukuk Dairesi","esas_no":"2023/100","karar_no":"2024/200","date":"15.02.2024","raw_text":"Yoksulluk nafakası alan tarafın işe girdiği ve düzenli gelir elde ettiği anlaşılmıştır. Tarafların ekonomik durumundaki değişiklik nedeniyle nafakanın hakkaniyete uygun biçimde indirilmesi gerekir."}]}'
```

### 4. Yargıtay'da gerçek karar araması yap

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/yargitay/search `
  -ContentType 'application/json' `
  -Body '{"queries":["+\"yoksulluk nafakası\" +\"nafakanın kaldırılması\"","+\"nafaka indirimi\" +\"ekonomik durum\""],"max_results":20}'
```

Endpoint Yargıtay karar arama sayfasını gerçek bir Chromium oturumunda kullanır.
Site CAPTCHA gösterirse doğrulamayı aşmaya çalışmaz; eldeki sonuçlarla birlikte
açıklayıcı mesajı `errors` alanında döndürür. Yargıtay'ın HTML yapısı değişirse
`app/services/yargitay_scraper.py` dosyasının başındaki seçiciler güncellenebilir.

### 5. Dilekçe stratejisi oluştur

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/petition/strategy `
  -ContentType 'application/json' `
  -Body '{"case_text":"Müvekkil emekli maaşı ile geçinmekte, kira ödemekte ve yeni evliliğinden çocuğu bulunmaktadır. Yoksulluk nafakasının kaldırılması, aksi halde indirilmesi istenmektedir.","top_decisions":[{"similarity_score":90,"usefulness_score":"Yüksek","court":"3. Hukuk Dairesi","esas_no":"2012/15632","karar_no":"2012/21942","date":"18.10.2012","short_summary":"Nafaka koşullarının değerlendirilmesine ilişkin karar.","legal_principle":"Tarafların sosyal ve ekonomik durumları birlikte değerlendirilmelidir.","why_relevant":"Somut olayla ekonomik durum ve nafaka kaldırma talebi bakımından ilgilidir.","lehe_aleyhe":"Lehe","petition_paragraph":"Yargıtay içtihatlarında tarafların sosyal ve ekonomik durumlarındaki değişikliklerin dikkate alınması gerektiği kabul edilmektedir."}]}'
```

### 6. Dilekçe taslağı oluştur

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/petition/draft `
  -ContentType 'application/json' `
  -Body '{"case_text":"Müvekkil emekli maaşı ile geçinmekte, kira ödemekte ve yeni evliliğinden çocuğu bulunmaktadır.","answers":{"nafaka_amount":"17500 TL","retirement_salary":"22000 TL","rent_amount":"19000 TL","child_info":"Yeni evlilikten bir çocuk vardır.","opponent_income_evidence":"Davalının çalıştığına ilişkin SGK kaydı talep edilecektir."},"selected_decisions":[{"court":"3. Hukuk Dairesi","esas_no":"2012/15632","karar_no":"2012/21942","date":"18.10.2012","petition_paragraph":"Yargıtay içtihatlarında sosyal ve ekonomik durum değişikliklerinin nafaka değerlendirmesinde dikkate alınması gerektiği kabul edilmektedir."}],"tone":"Ölçülü ve ikna edici","request_type":"Öncelikle nafakanın kaldırılması, aksi halde indirilmesi"}'
```

`/petition/draft` yalnızca `selected_decisions` içinde verilen kararları kullanır;
karar seçilmezse uydurma esas/karar numarası üretmez ve emsal karar bölümünü
genel içtihat ilkesi olarak kurar.

### 7. Legal Brain'e kitap yükle

Legal Brain, PDF kitapları ve hukuk kaynaklarını bir kez okuyup kalıcı hafızaya
işlemek için tasarlanmıştır. Yüklenen dosya önce `uploads/` altına alınır; daha
sonra ayrı bir ingest adımıyla sayfa numaraları korunarak chunklara ayrılır ve
indekslenir.

```powershell
$form = @{
  file = Get-Item "C:\kaynaklar\aile-hukuku.pdf"
  title = "Aile Hukuku Şerhi"
  author = "Yazar Adı"
  publisher = "Yayınevi"
  edition = "3. Baskı"
  publication_year = "2024"
  practice_area = "Aile Hukuku"
  topics = "yoksulluk nafakası, nafaka indirimi, TMK 176"
  license_status = "licensed"
  allowed_use = "internal_petition_support"
}
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/legal-brain/books/upload -Form $form
```

### 8. Kitabı Legal Brain hafızasına işle

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/legal-brain/books/ingest `
  -ContentType 'application/json' `
  -Body '{"book_id":"BOOK_ID"}'
```

Bu adım PDF metnini çıkarır, sayfa numaralarını korur, bölüm başlıklarını
yakalamaya çalışır, 700-1200 kelimelik parçalara ayırır ve ChromaDB içine
kaydeder. ChromaDB kullanılamazsa JSONL + SQLite keyword index fallback olarak
devreye girer.

### 9. Doktrin fişleri üret

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/legal-brain/books/create-doctrine-cards `
  -ContentType 'application/json' `
  -Body '{"book_id":"BOOK_ID","practice_area":"Aile Hukuku"}'
```

İlk aşamada LLM kullanılmaz. Sistem “gerekir”, “mümkündür”, “kaldırılır”,
“indirilebilir”, “hakkaniyet”, “ispat” gibi kalıpları ve TMK/HMK/TBK/İİK/TCK/CMK
madde referanslarını yakalayarak kısa doktrin fişleri üretir.

### 10. Legal Brain içinde ara

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/legal-brain/search `
  -ContentType 'application/json' `
  -Body '{"query":"yoksulluk nafakasının kaldırılması emekli maaşı kira ödeme gücü TMK 176","practice_area":"Aile Hukuku","max_results":10}'
```

### 11. Legal Brain debug endpointleri

Yüklenen ve indekslenen kaynakları görmek için:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/legal-brain/documents
```

Belirli bir kitabın gerçekten hangi metinle chunklandığını görmek için:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/legal-brain/books/BOOK_ID/chunks
```

Bu endpoint, her chunk için sayfa aralığını, practice area bilgisini, topicleri
ve ilk 1500 karakterlik metin önizlemesini döndürür. Doctrine card üretimi boş
dönerse ilk bakılacak yer burasıdır.

Kanun kaynakları madde bazlı indekslendiyse belirli bir maddeyi doğrudan görmek için:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/legal-brain/statutes/TMK/articles/176
```

Bu endpoint, örneğin TMK 176 maddesinin indekslenmiş metnini, sayfa bilgisini ve
metadata alanlarını döndürür.

### 12. Olay için Legal Brain kaynaklarını çağır

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/legal-brain/retrieve-for-case `
  -ContentType 'application/json' `
  -Body '{"case_text":"Müvekkil emekli maaşı ile geçinmekte, kira ödemekte ve yeni evliliğinden çocuğu bulunmaktadır. Yoksulluk nafakasının kaldırılması, aksi halde indirilmesi istenmektedir.","practice_area":"Aile Hukuku","max_sources":10}'
```

### 13. Dilekçede Legal Brain kullan

`/petition/strategy` Legal Brain kaynaklarını otomatik çağırır ve strateji özetine
doktrin/mevzuat temelli argümanları ekler. `/petition/draft` içinde Legal Brain
kullanımı için şu alanlar gönderilebilir:

```json
{
  "use_legal_brain": true,
  "legal_language_level": "usta_avukat"
}
```

Bu durumda dilekçe; avukatın olay anlatımı, seçilen Yargıtay kararları, Legal
Brain'den gelen kitap/doktrin fişleri ve mevzuat maddelerini birlikte kullanır.
Kitap kaynağı varsa `citation_label` üzerinden atıf yapar; kaynak yoksa kitap adı
veya sayfa numarası uydurmaz.

## Mimari notlar

- `routes/` yalnızca HTTP sözleşmesini ve bağımlılıkları yönetir.
- `services/` analiz, sorgu üretimi, sıralama, metin temizleme, Yargıtay erişim
  mantığı, Legal Brain kalıcı hukuk hafızası ve kural tabanlı dilekçe
  strateji/taslak üretimini içerir.
- `models/` Pydantic istek/yanıt sözleşmelerini içerir.
- İleride `RuleBasedCaseAnalyzer`, `RuleBasedSearchBuilder` ve
  `MockDecisionRanker` aynı arayüzleri koruyan LLM, scraper ve embedding tabanlı
  servislerle değiştirilebilir.

Sıralama puanları bu aşamada hukuki görüş değildir; yalnızca yerel ve
deterministik mock metin benzerliği sinyalidir.
