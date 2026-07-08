# P2 Information Architecture

## 1. Amaç

Bu belge mobil uygulamanın ana navigasyonunu, ekran hiyerarşisini, ekranlar arası geçişleri ve görünür bilgi önceliklerini tanımlar.

## 2. Ana navigasyon

Birincil alt navigasyon dört bölümden oluşur:

1. Asistan
2. Dosyalar
3. Kaynaklar
4. Taslaklar

Bildirimler, hesap ve uygulama ayarları profil/üç nokta menüsünde bulunur.

## 3. Uygulama kabuğu

### 3.1 Üst çubuk

Aktif dosya varken:

`☰  Araç Ayıbı Dosyası                 UYAP  ⋯`

Bileşenler:

- Sol menü: dosya drawer'ı
- Başlık: aktif dosya adı
- Alt başlık: dosya numarası veya taraf özeti
- UYAP ikonu: bağlantı ve yeni hareket durumu
- Üç nokta: dosya ve görünüm işlemleri

Aktif dosya yokken:

`☰  Emsalist                           UYAP  ⋯`

### 3.2 Tema

- Varsayılan: sistem teması
- Seçenekler: Otomatik, Açık, Koyu
- Tema ayarı üst çubukta ayrı ikon olarak bulunmaz
- Tercih cihazda saklanır

### 3.3 UYAP durumları

- Bağlı: yeşil ikon + erişilebilir durum etiketi
- Bağlı değil: gri ve bağlantı kesik simgesi
- Bağlanıyor: sarı/progress durumu
- Hata: kırmızı uyarı
- Yeni hareket: mavi nokta veya sayı rozeti

Renk tek başına anlam taşımaz.

## 4. Asistan bölümü

### 4.1 Ana sohbet ekranı

Bölümler:

- Üst çubuk
- Mesaj akışı
- Bağlamsal öneri/quick action alanı
- Composer

Quick action örnekleri:

- İçtihat Ara
- Mevzuat Ara
- Dilekçe Hazırla
- Belge İncele
- Dosya Özeti

### 4.2 Composer

`＋  Mesajınızı yazın…                  Gönder`

Artı menüsü:

- Belge yükle
- Fotoğraf çek
- Galeriden ekle
- UYAP evrakı ekle
- Sesli anlatım
- İçtihat ara
- Mevzuat ara
- Dilekçe incele

### 4.3 Mesaj kartları

- Kullanıcı mesajı
- Asistan mesajı
- Belge kartı
- Kaynak kartı
- Eksik bilgi kartı
- Çelişki kartı
- Risk kartı
- Süre kartı
- Taslak kartı
- UYAP hareket kartı
- Sistem/hata kartı

## 5. Dosya drawer'ı

Sıralama:

1. Yeni dosya
2. Arama
3. Sabitlenen dosyalar
4. Son dosyalar
5. Arşiv
6. Çöp kutusu

Her dosya satırı:

- kısa başlık
- taraf veya dosya numarası
- durum
- son güncelleme
- kritik uyarı sayısı

Drawer, ana sohbeti tamamen değiştirmeden dosya seçimini mümkün kılar.

## 6. Dosyalar bölümü

### 6.1 Dosya listesi

Filtreler:

- Aktif
- Bilgi bekliyor
- Belge bekliyor
- Taslak hazırlanıyor
- İncelemede
- Tamamlandı
- Arşivlendi

Sıralama:

- Son güncelleme
- Yaklaşan süre
- Risk seviyesi
- Alfabetik

### 6.2 Dosya detay ekranı

Sekmeler yerine mobil uyumlu bölüm listesi tercih edilir:

- Genel bakış
- Taraflar
- Kronoloji
- Talepler ve savunmalar
- Belgeler ve deliller
- Eksikler
- Çelişkiler
- Riskler
- Süreler
- Hukuki meseleler
- Kaynaklar
- Taslaklar
- UYAP hareketleri
- Aktivite geçmişi

Kritik özet bottom sheet olarak sohbet ekranından da açılabilir.

## 7. Kaynaklar bölümü

### 7.1 Kaynak arama

- Arama alanı
- Dosya bağlamını kullan anahtarı
- Mahkeme/daire/tarih/tür/doğrulama filtreleri
- Benzer/Karşıt sonuç seçimi

### 7.2 Sonuç kartı

- Başlık
- Mahkeme/daire
- Tarih
- Esas/karar numarası
- Doğrulama rozeti
- İlgili paragraf
- Dosyayla ilgisi
- Kullanılabilir argüman
- Karşı tarafın kullanabileceği yön
- Kaynağı aç
- Dosyaya ekle
- Dilekçede kullan

### 7.3 Kaynak detay

- Resmî metin veya kontrollü içerik
- Metadata
- Sürüm/güncellik
- İlgili paragraflar
- Dosyalarda kullanım
- Taslaklarda kullanım
- Önceki/sonraki sürüm ilişkisi

### 7.4 Resmî kaynak takibi

- Son kontrol
- Güncellik
- Yeni sürüm
- Değişiklik özeti
- Etkilenen dosya ve taslaklar
- İnceleme gereken kayıtlar

## 8. Taslaklar bölümü

### 8.1 Taslak listesi

Durumlar:

- Taslak
- Eksik bilgi var
- Kaynak kontrolü gerekli
- İncelemede
- Değişiklik istendi
- Onaylandı
- Dışa aktarıldı

### 8.2 Taslak editörü

- Bölüm navigasyonu
- Metin editörü
- Kaynak/delil paneli veya bottom sheet
- Tutarlılık uyarıları
- Sürüm geçmişi
- İncelemeye gönder
- DOCX/PDF dışa aktar

Mobilde sürekli sağ panel yerine bağlamsal bottom sheet kullanılır.

## 9. Bildirim merkezi

Gruplar:

- Kritik süreler
- UYAP hareketleri
- Belge analizleri
- Çelişkiler ve eksikler
- Kaynak güncellemeleri
- Taslak incelemeleri

Her bildirim:

- ilgili dosya
- olay/tarih
- kaynak
- öncelik
- okundu durumu
- doğrudan aksiyon

bilgilerini taşır.

## 10. Ayarlar

### 10.1 Görünüm

- Otomatik
- Açık
- Koyu
- Metin boyutu sistem ayarına uyum

### 10.2 Hesap ve güvenlik

- Profil
- Workspace
- Cihaz oturumları
- Parola değiştir
- MFA
- Çıkış

### 10.3 Bildirimler

- UYAP
- Süre
- Belge
- Kaynak
- Taslak
- Sessiz saatler

### 10.4 Veri ve gizlilik

- Veri dışa aktarma
- Hesap kapatma
- Dosya silme politikası
- Gizlilik metni
- Model sağlayıcısı veri kullanımı açıklaması

### 10.5 UYAP

- Bağlantı durumu
- Son bağlantı
- Yeniden bağlan
- Yetki kapsamı
- Bağlantıyı kaldır

## 11. Ekran durumları

Her veri ekranı aşağıdaki durumları tanımlamalıdır:

- İlk yükleniyor
- İçerik var
- Boş
- Kısmi veri
- Çevrimdışı cache
- Yetkisiz
- Hata
- Yeniden deneme
- Silinmiş/arşivlenmiş

## 12. Mobil davranış kuralları

- Kritik aksiyonlar tek elle erişilebilir bölgede olmalıdır.
- Silme ve nihai dışa aktarma onay ister.
- Modal üstüne modal açılmaz.
- Uzun hukuki metinlerde okuma konumu korunur.
- Klavye composer'ı kapatmaz.
- Bottom sheet yüksekliği içerik ve erişilebilirlik ayarına uyar.
- Gesture-only işlem bulunmaz; görünür alternatif sunulur.

## 13. Derin bağlantılar

Desteklenmesi planlanan hedefler:

- dosya
- mesaj
- belge
- kaynak
- taslak
- UYAP hareketi
- süre

Bildirimden açılan deep link önce workspace ve yetki kontrolü yapar.

## 14. İlk P2.1 ekran seti

P2.1 yalnız şu ekranları gerçek UI olarak oluşturur:

1. Splash/loading
2. Ana chat shell
3. Dosya drawer mock
4. Dosya özeti bottom sheet mock
5. UYAP durum bottom sheet mock
6. Görünüm ayarı
7. Boş, hata ve çevrimdışı durumları

Gerçek auth, dosya ve mesaj API entegrasyonu sonraki aşamalardadır.
