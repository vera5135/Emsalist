# P2 Decision Register

Bu belge P2 boyunca alınan ürün ve mimari kararlarının kayıt defteridir. Her karar `Accepted`, `Proposed`, `Deferred` veya `Rejected` durumlarından biriyle tutulur.

## Karar tablosu

| ID | Konu | Karar | Durum | Gerekçe | Yeniden değerlendirme |
|---|---|---|---|---|---|
| P2-D001 | Birincil platform | iOS-first | Accepted | Ana kullanıcı kitlesi avukatlar; iPhone öncelikli dağıtım hedefi App Store | P2 beta sonrası Android |
| P2-D002 | Mobil teknoloji | Flutter | Accepted | Tek kod tabanı, iOS-first geliştirme ve sonraki Android seçeneği | P2.1 başlangıcı |
| P2-D003 | Ana kullanıcı deneyimi | Chat-first | Accepted | Form yükünü azaltmak, doğal hukuk dosyası anlatımı sağlamak | Kullanılabilirlik testleri |
| P2-D004 | Tema | Sistem teması varsayılan; açık/koyu manuel seçenek | Accepted | Mobil platform davranışıyla uyum ve sade üst çubuk | P2.1 |
| P2-D005 | Üst çubuk tema ikonu | Kalıcı güneş/ay ikonu yok | Accepted | Alanı korumak ve gereksiz kontrolü kaldırmak | P2.1 beta |
| P2-D006 | UYAP göstergesi | Kompakt ikon + durum + rozet | Accepted | Büyük kalıcı kapsül yerine sade görünüm | P2.10 |
| P2-D007 | İlk pilot | Ayıplı araç/tüketici hukuku | Accepted | Tarih, tutar, belge, ihbar, ayıp ve seçimlik hak ilişkilerini birlikte test eder | Pilot kapanışı |
| P2-D008 | Backend | FastAPI + PostgreSQL devam | Accepted | P1 kabul edilmiş altyapı korunur | Büyük ölçek gereksinimi doğarsa |
| P2-D009 | Kaynak sırası | Güvenilir kaynak omurgası aramadan önce | Accepted | Uydurma ve güncellik riskini azaltır | Değişmez mimari ilke |
| P2-D010 | Semantik katman | Kaynak ve dosya omurgasından sonra | Accepted | Semantik sonuçların izlenebilir ve doğrulanabilir olması gerekir | Değişmez mimari ilke |
| P2-D011 | UYAP ilk sürüm | Okuma/eşleştirme ağırlıklı, otomatik gönderim yok | Accepted | Güvenlik ve hukuki riskleri sınırlamak | Teknik/hukuki fizibilite sonrası |
| P2-D012 | P2.0 kapsamı | Dokümantasyon ve sözleşme; ürün kodu yok | Accepted | Yeniden iş riskini azaltmak | P2.0 kapanışı |
| P2-D013 | Asistan soru biçimi | Bir seferde en kritik tek soru | Accepted | Kullanıcı yükünü ve bilişsel karmaşayı azaltmak | Konuşma tasarımı testleri |
| P2-D014 | Dosya hafızası | Yapılandırılmış, kaynak bağlantılı ve sürümlü | Accepted | Sohbet özeti tek başına yeterli değildir | Veri modeli incelemesi |
| P2-D015 | Belge çıkarımı | Doğrulama statülü; otomatik kesinleştirme yok | Accepted | Belge okuma hatalarının hukuk dosyasını bozmasını önlemek | P2.5 |

## Açık kararlar

### P2-O001 — Flutter proje dizini

Seçenekler:

- `/mobile`
- `/apps/mobile`
- ayrı repository

Öneri: mevcut backend ve dokümantasyonla aynı repository içinde `/mobile`.

Kabul ölçütleri:

- CI ayrımı kolay olmalı
- backend kodundan bağımsız build edilebilmeli
- gelecekte Android eklenebilmelidir

### P2-O002 — Bundle identifier

Öneri:

- production: `com.emsalist.app`
- staging: `com.emsalist.app.staging`
- development: `com.emsalist.app.dev`

App Store hesabı ve marka sahipliği doğrulanmadan kesinleştirilmez.

### P2-O003 — Hesap modeli

Seçenekler:

- yalnız bireysel avukat
- bireysel + büro workspace
- yalnız büro workspace

Öneri: kullanıcı her zaman bir tenant/workspace içinde çalışır; bireysel avukat için kişisel workspace otomatik oluşturulur.

### P2-O004 — İlk giriş yöntemi

Öneri sırası:

1. e-posta + parola
2. e-posta doğrulama
3. Apple ile giriş
4. isteğe bağlı MFA

Apple ile giriş, başka sosyal giriş sunulursa App Store kuralları nedeniyle değerlendirilmelidir.

### P2-O005 — Offline kapsamı

Öneri:

- son dosya listesi
- son konuşmaların şifreli yerel cache'i
- gönderilemeyen metin mesajlarının retry kuyruğu
- belgelerin varsayılan olarak kalıcı offline saklanmaması

### P2-O006 — Dosya silme geri alma süresi

Öneri: 30 gün soft-delete; legal hold varsa purge yok.

### P2-O007 — Maksimum belge boyutu

Mevcut backend varsayılanı 15 MB'dir. P2 için öneri:

- standart sınır: 25 MB
- büyük belge: parçalı yükleme ile 100 MB'a kadar
- ilk beta: mevcut 15 MB korunabilir

Nihai karar performans ve depolama testine bağlıdır.

### P2-O008 — UDF çözümleme

Öneri: yalnız backend tarafında; mobil istemci UDF içeriğini yerel olarak ayrıştırmaz.

### P2-O009 — Kaynak insan incelemesi

Öneri: doğrulama kuyruğu ve editör rolü P2.6'da hazırlanır; beta öncesi kritik kaynaklar insan incelemesinden geçer.

### P2-O010 — Bildirim altyapısı

Öneri:

- APNs/FCM soyutlaması
- backend notification outbox
- idempotent delivery
- dosya ve olay bağlantılı payload

### P2-O011 — DOCX şablonları

Öneri:

- sistem şablonu
- büro şablonu
- dosya bazlı seçim
- sürüm ve değişiklik kaydı

### P2-O012 — Yapay zekâ sağlayıcısı

Öneri: provider abstraction zorunlu; Gemini/diğer sağlayıcı iş mantığına gömülmez.

### P2-O013 — Veri barındırma

Karar verilmesi gerekenler:

- Türkiye içi barındırma hedefi
- AB bölgesi alternatifi
- yedek bölgesi
- alt işleyen listesi

### P2-O014 — Beta kapsamı

Öneri:

- 10–20 avukat
- sınırlı hukuk alanı
- davetli kullanım
- gerçek dosya öncesi sentetik test paketi

### P2-O015 — Ücretlendirme

Öneri: P2 kapalı beta sırasında ödeme alınmaz; kullanım ve maliyet verisi toplanır, fiyatlandırma beta sonrasında belirlenir.

## Karar alma kuralı

- Kritik kararlar PR açıklamasında ayrıca listelenir.
- `Accepted` karar değişirse yeni ID ile karar yazılır; eski karar silinmez.
- Güvenlik, KVKK ve hukuk kaynağı doğrulama kararları yalnız UI gerekçesiyle gevşetilemez.
