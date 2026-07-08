# P2 Product Scope

## 1. Amaç

Bu belge P2 boyunca geliştirilecek ürün kapsamını, kapsam dışı alanları, kullanıcı değerini ve başarı sınırlarını tanımlar. Kapsam değişikliği yalnızca karar kaydına yeni bir karar eklenerek yapılabilir.

## 2. Ürün tanımı

Emsalist P2, avukatın bir hukuk dosyasını mobil cihazdan doğal dil ile başlatabildiği, belgeleri ve olayları yapılandırabildiği, güvenilir mevzuat ve içtihatlarla çalışabildiği ve kaynak bağlantılı dilekçe üretebildiği iOS-first hukuk çalışma alanıdır.

Ürün bir hukuk danışmanı yerine geçen otonom karar sistemi değildir. Nihai değerlendirme, kaynak seçimi ve dışa aktarılan hukuki metin üzerinde son kontrol avukata aittir.

## 3. Birincil kullanıcı grupları

### 3.1 Bireysel avukat

- Kişisel çalışma alanında dosya açar.
- Belge yükler ve analiz sonuçlarını doğrular.
- İçtihat ve mevzuat arar.
- Taslak üretir ve dışa aktarır.
- Kendi UYAP bağlantısını yönetir.

### 3.2 Büro yöneticisi

- Büro çalışma alanını ve kullanıcı rollerini yönetir.
- Dosya erişimlerini belirler.
- Büro şablonlarını ve kaynak politikalarını yönetir.
- İnceleme ve onay akışlarını izler.

### 3.3 Büro çalışanı

- Yetkili olduğu dosyalarda çalışır.
- Belge ve not ekler.
- Taslak hazırlayabilir.
- Rolüne göre nihai onay veya dışa aktarma yetkisi sınırlanabilir.

### 3.4 Kaynak inceleme editörü

- Hukuk kaynağı doğrulama kuyruğunu yönetir.
- Tekrar kayıtları birleştirir.
- Güncellik ve yürürlük statülerini işaretler.
- Hatalı veya şüpheli kaynakları karantinaya alır.

### 3.5 Sistem yöneticisi

- Teknik sağlık, indeksleme ve iş kuyruğu durumlarını izler.
- Kullanıcı içeriğine varsayılan erişimi yoktur.
- Ayrı yetki ve denetim kaydı olmadan hukuk dosyası içeriğini görüntüleyemez.

## 4. P2 kapsam içi

### 4.1 Mobil istemci

- Flutter tabanlı iOS-first uygulama
- Chat-first ana deneyim
- Sistem/açık/koyu tema
- Dosya drawer'ı ve aktif dosya başlığı
- Kompakt UYAP durum ikonu
- Bildirim merkezi
- Erişilebilirlik ve küçük ekran desteği

### 4.2 Kimlik ve çalışma alanı

- E-posta tabanlı giriş
- Access/refresh token yönetimi
- Oturum yenileme ve iptal
- Kişisel ve büro workspace modeli
- Rol ve dosya bazlı yetkilendirme
- Cihaz oturumu görünürlüğü

### 4.3 Dosya ve konuşma

- Yeni dosya oluşturma
- Doğal dille olay anlatımı
- Dosya listesi, arama, sabitleme ve arşiv
- Dosyaya bağlı konuşma geçmişi
- Mesaj tekrar deneme ve idempotency
- Dosya özeti ve durum göstergesi

### 4.4 Yapılandırılmış dosya hafızası

- Taraflar
- Olaylar ve kronoloji
- İddia ve savunmalar
- Talepler
- Belgeler ve deliller
- Eksik bilgiler
- Çelişkiler
- Riskler
- Süreler
- Hukuki meseleler
- Kaynak ve taslak bağlantıları

### 4.5 Belge işleme

- PDF, UDF, DOCX, TXT, JPG, JPEG, PNG
- Güvenli yükleme
- MIME, boyut, hash ve tekrar kontrolü
- Asenkron analiz
- Sayfa/paragraf konumlandırma
- Belge türü tespiti
- Bilgi çıkarımı
- Kullanıcı doğrulama ve reddetme

### 4.6 Güvenilir hukuk kaynağı omurgası

- Mevzuat
- Resmî Gazete
- Yargıtay
- Danıştay
- Anayasa Mahkemesi
- Uyuşmazlık Mahkemesi
- Doğrulanmış ikincil kaynaklar
- Kontrollü doktrin
- Kaynak sürümü, hash'i, güncellik ve doğrulama durumu

### 4.7 Hibrit hukuk araması

- Anahtar kelime
- Tam metin
- Semantik arama
- Esas/karar numarası
- Mahkeme, daire ve tarih filtreleri
- Benzer karar
- Karşıt karar
- Dosya bağlamlı sıralama
- Kaynak doğrulama filtresi

### 4.8 Hukuki mesele ve delil grafiği

- Mesele-alt mesele ilişkisi
- Olay, belge, delil, kaynak ve risk bağlantıları
- İspat yükü
- Karşı argüman
- Eksik delil
- Dilekçe paragrafı bağlantısı

### 4.9 Kaynak bağlantılı dilekçe

- Yeterlilik kontrolü
- Talep ve hukuki mesele seçimi
- Delil ve kaynak eşleştirme
- Bölüm ve paragraf bazlı üretim
- Kaynak izlenebilirliği
- Avukat düzenleme ve sürüm geçmişi
- DOCX ve PDF dışa aktarma

### 4.10 UYAP Bridge ilk sürüm

- Bağlantı durumu
- Son kontrol zamanı
- Dosya numarası eşleştirme
- Manuel UYAP evrakı ekleme
- UYAP kaynak etiketi
- Yeni hareket rozeti
- Evrakı dosyaya bağlama
- Süre çıkarma önerisi

### 4.11 Bildirimler

- Yeni UYAP hareketi
- Yeni tebligat
- Yaklaşan süre
- Eksik belge
- Kritik çelişki
- Belge analizi tamamlandı
- Yeni ilgili kaynak
- Taslak inceleme bekliyor

### 4.12 Beta ve App Store hazırlığı

- Kapalı beta
- Crash ve performans izleme
- Hesap kapatma ve veri silme
- Gizlilik ve izin metinleri
- App Store ekranları ve metadata

## 5. P2 kapsam dışı

Aşağıdakiler P2 ilk yayın kapsamına dahil değildir:

- Kullanıcı adına otomatik dava açma
- UYAP üzerinden otomatik evrak gönderme
- Otomatik e-imza
- Mahkeme sisteminde kullanıcı adına işlem yapma
- Avukat onayı olmadan nihai dilekçe gönderme
- Tam teşekküllü hukuk bürosu muhasebesi
- Gelişmiş CRM ve satış hunisi
- Bordro ve personel yönetimi
- Müvekkil portalı
- Genel amaçlı e-posta istemcisi
- Android ana mağaza yayını
- Kamuya açık hukuk arama motoru
- Kullanıcı konuşmalarının model eğitimi amacıyla kullanılması
- Kaynaksız veya doğrulanmamış emsal üretimi

## 6. Hukuki ürün sınırları

Sistem:

- Kaynağı ve belirsizliği açıkça gösterir.
- Doğrulanmamış kararı kesin emsal olarak sunmaz.
- Karar numarası veya belge içeriği tahmin etmez.
- Kullanıcı beyanı ile belge tespitini ayırır.
- Çelişkili bilgiyi kullanıcı onayı olmadan kesinleştirmez.
- Süre hesaplamasını kaynak ve varsayımlarıyla gösterir.
- Nihai hukuki görüşü avukatın kontrolüne bırakır.

## 7. Veri ve gizlilik sınırları

- Her kullanıcı bir workspace/tenant bağlamında çalışır.
- Dosya erişimi ayrıca yetkilendirilir.
- Belge tam metni ve dilekçe metni uygulama loglarına yazılmaz.
- UYAP şifresi kalıcı ve düz metin olarak saklanmaz.
- Silme, legal hold ve yedek saklama süreçleri izlenebilir olur.
- Model sağlayıcısına gönderilen içerik en az veri ilkesiyle sınırlandırılır.

## 8. Pilot kapsamı

İlk uçtan uca pilot ayıplı araç/tüketici hukuku dosyasıdır.

Zorunlu pilot alanları:

- satın alma tarihi
- satış bedeli
- satıcı ve alıcı
- marka/model/plaka/şasi
- ayıbın türü ve ilk görülme tarihi
- servis kayıtları
- ekspertiz/bilirkişi raporu
- TRAMER bilgisi
- ayıp ihbarı ve noter ihtarı
- seçimlik hak
- zarar kalemleri
- görev, yetki ve süre riskleri

Pilot, kategori seçimini değil somut değer tamamlanmasını ölçer.

## 9. Ürün başarı ölçütleri

P2 beta sonunda en az aşağıdakiler ölçülmelidir:

- Yeni dosyadan ilk anlamlı dosya özetine kadar geçen süre
- Kritik eksik bilgi tespit oranı
- Çelişki tespit doğruluğu
- Kaynakların resmî/doğrulanmış oranı
- İlk 3 ve ilk 10 arama başarısı
- Kaynak bağlantılı paragraf oranı
- Yanlış veya uydurma kaynak oranı
- Belge analiz hata oranı
- Mobil crash-free session oranı
- Beta kullanıcılarının uçtan uca pilot tamamlama oranı

## 10. Kapsam değişikliği kuralı

Yeni bir özellik yalnızca şu koşullarda P2 kapsamına alınabilir:

1. Kullanıcı değerini açıkça artırır.
2. Mevcut aşama sırasını bozmaz.
3. Güvenlik veya kaynak doğrulama kapısını gevşetmez.
4. Karar kaydına eklenir.
5. Kabul matrisi ve backlog güncellenir.
