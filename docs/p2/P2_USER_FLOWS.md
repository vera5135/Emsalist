# P2 User Flows

## 1. Amaç

Bu belge P2'nin ana kullanıcı akışlarını, sistem durumlarını, hata yollarını ve kabul noktalarını tanımlar. Akışlar mobil istemci, backend, belge hattı ve hukuk kaynağı katmanlarının sorumluluklarını görünür kılar.

## 2. Akış ilkeleri

- Kullanıcı bir dosyaya yalnızca birkaç temel bilgiyle başlayabilir.
- Sistem uzun formlar yerine sohbet ve bağlamsal kartlar kullanır.
- Her kritik veri kaynağıyla birlikte saklanır.
- Belgeden çıkarılan bilgi kullanıcı onayı olmadan kesinleştirilmez.
- Aynı anda en kritik tek soru sorulur.
- Hata, bekleme ve yeniden deneme durumları açıkça gösterilir.
- Her işlem aktif tenant ve aktif case bağlamında yürütülür.

## 3. UF-01 — İlk açılış ve giriş

### Ön koşul

Kullanıcı uygulamayı ilk kez açar.

### Ana akış

1. Açılış ekranı gösterilir.
2. Uygulama tema tercihini sistemden alır.
3. Kullanıcı e-posta ve parola ile giriş yapar.
4. Backend access ve refresh token döndürür.
5. Token güvenli cihaz deposuna yazılır.
6. Kullanıcının erişebildiği workspace listesi alınır.
7. Tek workspace varsa otomatik seçilir.
8. Birden fazla workspace varsa seçim ekranı gösterilir.
9. Son aktif dosya varsa açılır; yoksa boş Asistan ekranı gösterilir.

### Hata yolları

- Geçersiz kimlik bilgisi: genel ve güvenli hata mesajı
- Ağ yok: tekrar dene ve çevrimdışı görünüm
- Workspace erişimi yok: destek/çıkış seçenekleri
- Refresh token geçersiz: güvenli çıkış

### Kabul noktası

Kullanıcı yetkili workspace içinde ana ekrana ulaşır; token veya parola loglanmaz.

## 4. UF-02 — Yeni dosya oluşturma

### Ana akış

1. Kullanıcı `Yeni Dosya` seçer.
2. Sistem iki başlangıç seçeneği sunar:
   - Olayı anlat
   - Temel bilgileri gir
3. Kullanıcı yalnızca olay anlatımıyla başlayabilir.
4. Backend yeni case ve ilk conversation kaydını atomik oluşturur.
5. Sistem anlatımdan geçici dosya adı ve hukuk alanı önerir.
6. Kullanıcı öneriyi kabul eder veya değiştirir.
7. Asistan ilk kritik soruyu sorar.
8. Dosya durumu `Bilgi toplanıyor` olur.

### Hata yolları

- Aynı istemci isteği tekrar gönderirse idempotency ile ikinci dosya oluşmaz.
- Backend başarısızsa yerel taslak korunur.
- Kullanıcı ekranı kapatırsa yarım giriş kaybolmaz.

### Kabul noktası

Tek case, tek başlangıç conversation ve kaynaklı ilk kullanıcı mesajı oluşturulur.

## 5. UF-03 — Doğal dille dosya bilgisi toplama

### Ana akış

1. Kullanıcı olayı anlatır.
2. Sistem mesajı kaydeder.
3. Bilgi çıkarım katmanı taraf, tarih, tutar, olay ve talep adaylarını üretir.
4. Adaylar `önerildi` veya `tespit edildi` statüsüyle hafızaya yazılır.
5. Çelişki ve eksik bilgi motoru çalışır.
6. Asistan dosya stratejisi açısından en kritik tek soruyu seçer.
7. Kullanıcı cevap verir.
8. Doğrudan kullanıcı beyanı `kullanıcı doğruladı` statüsüyle kaydedilir.
9. Dosya özeti sessizce güncellenir.

### Örnek

- Asistan: `Aracı hangi tarihte satın aldınız?`
- Kullanıcı: `12 Mart 2026.`
- Sistem: satın alma tarihini kaynak mesajıyla kaydeder.
- Asistan: `Satış bedeli ne kadardı?`

### Hata yolları

- Kullanıcı önceki bilgisini düzeltirse eski değer silinmez; superseded olur.
- Belirsiz cevapta tarih/tutar tahmin edilmez.
- Aynı mesaj yeniden işlenirse duplicate fact oluşmaz.

### Kabul noktası

Her bilgi source_id, doğrulama statüsü ve değişiklik geçmişi taşır.

## 6. UF-04 — Belge yükleme ve analiz

### Ana akış

1. Kullanıcı mesaj alanındaki `+` menüsünden belge yükler.
2. İstemci dosya adı, boyut ve türü gösterir.
3. Backend MIME, boyut, hash ve güvenlik kontrollerini yapar.
4. Belge güvenli depoya yazılır.
5. Asenkron analiz işi oluşturulur.
6. Mobil uygulama belge kartında ilerleme gösterir.
7. Metin ve sayfa konumları çıkarılır.
8. Belge türü ve bilgi adayları üretilir.
9. Kullanıcıya doğrulanacak kritik tespitler sunulur.
10. Kullanıcının onayladığı bilgiler dosya hafızasına bağlanır.

### Hata yolları

- Desteklenmeyen format
- Boyut sınırı aşımı
- Zararlı/şüpheli dosya
- Şifreli veya okunamayan PDF
- Eksik sayfa
- Ağ kesintisinde yükleme yeniden deneme
- Aynı hash'e sahip belge tekrar yüklenmesi

### Kabul noktası

Her çıkarım belge ID, sayfa/paragraf konumu, confidence ve statü taşır.

## 7. UF-05 — Çelişki çözme

### Tetikleyici

Aynı fact türü için uyumsuz iki değer bulunur.

### Ana akış

1. Sistem çelişki kaydı oluşturur.
2. Risk seviyesi ve ilgili hukuki mesele belirlenir.
3. Kullanıcıya iki değer ve kaynakları gösterilir.
4. Kullanıcı:
   - bir değeri doğru seçer,
   - ikisini de reddeder,
   - açıklama ekler,
   - daha sonra incelemeyi seçer.
5. Seçilen değer doğrulanır; diğer değer superseded/rejected olur.
6. İlgili risk ve eksik bilgi yeniden hesaplanır.

### Kabul noktası

Çelişkili bilgi çözülmeden kesin gerçek veya dilekçe girdisi olarak kullanılamaz.

## 8. UF-06 — Dosya özeti ve ilerleme

### Ana akış

1. Kullanıcı dosya başlığına dokunur.
2. Bottom sheet veya ayrı sayfa açılır.
3. Bölümler gösterilir:
   - taraflar
   - olay özeti
   - kronoloji
   - talepler
   - belgeler/deliller
   - eksikler
   - çelişkiler
   - riskler
   - süreler
   - meseleler
   - kaynaklar
   - taslaklar
   - UYAP hareketleri
4. Her bölümde tamamlanma değil, somut veri durumu gösterilir.
5. Kullanıcı kayıtları düzeltebilir veya kaynaklarına gidebilir.

### Kabul noktası

Kategori varlığı ile somut değer tamamlanması birbirinden ayrıdır.

## 9. UF-07 — İçtihat ve mevzuat arama

### Ana akış

1. Kullanıcı doğal dil sorusu sorar veya `İçtihat ara` seçer.
2. Sistem aktif dosya bağlamından mesele ve filtre önerir.
3. Kullanıcı kapsamı onaylar veya değiştirir.
4. Hibrit arama çalışır.
5. Sonuçlar doğrulama, otorite, tarih ve dosya ilgisine göre sıralanır.
6. Her kartta ilgili paragraf ve neden bulunduğu gösterilir.
7. Kullanıcı kaynağı:
   - açar,
   - dosyaya ekler,
   - bir meseleye bağlar,
   - dilekçede kullanmak üzere işaretler,
   - alakasız olarak geri bildirim verir.

### Hata yolları

- Resmî kaynağa ulaşılamıyor
- Sonuç yok
- Yalnız doğrulanmamış sonuç var
- Aynı kararın tekrarları
- Karşıt karar bulunması

### Kabul noktası

Kaynak statüsü ve resmî bağlantı açıkça görünür; doğrulanmamış kaynak saklanabilir fakat nihai dilekçe için uyarı üretir.

## 10. UF-08 — Hukuki mesele grafiği oluşturma

### Ana akış

1. Sistem dosya hafızası ve seçili kaynaklardan mesele adayları üretir.
2. Ana ve alt meseleler oluşturulur.
3. Her mesele olay, delil, eksik, risk ve kaynaklarla bağlanır.
4. Kullanıcı meseleleri kabul eder, birleştirir veya reddeder.
5. İspat yükü ve karşı argümanlar kaydedilir.
6. Grafik sürümü oluşturulur.

### Kabul noktası

Her ana iddia için delil ve kaynak durumu görünürdür.

## 11. UF-09 — Kaynak bağlantılı dilekçe oluşturma

### Ana akış

1. Kullanıcı `Dilekçe hazırla` seçer.
2. Sistem yeterlilik kontrolü çalıştırır.
3. Kritik eksik ve çözülmemiş çelişkiler gösterilir.
4. Kullanıcı taslak türü, mahkeme, talepler ve kapsamı seçer.
5. Sistem dilekçe planı önerir.
6. Kullanıcı planı onaylar.
7. Bölümler oluşturulur.
8. Her paragraf olay, delil ve kaynak metadata'sına bağlanır.
9. Tutarlılık ve kaynak doğrulama kontrolleri çalışır.
10. Kullanıcı metni düzenler.
11. Yeni sürüm kaydedilir.
12. DOCX/PDF dışa aktarılır.

### Engelleyici durumlar

- Doğrulanmamış karar numarası
- Çözülmemiş kritik çelişki
- Mahkeme/talep gibi zorunlu alan eksikliği
- Talep ve sonuç bölümünün uyumsuzluğu

### Kabul noktası

Nihai çıktıda kullanılan önemli iddialar kaynak ve delil bağlantısına sahiptir.

## 12. UF-10 — UYAP hareketi işleme

### Ana akış

1. UYAP ikonu yeni hareket rozeti gösterir.
2. Kullanıcı ikona dokunur.
3. Bağlantı durumu, son kontrol ve hareketler açılır.
4. Kullanıcı hareketi inceler.
5. Evrak aktif dosyayla otomatik veya manuel eşleştirilir.
6. Kullanıcı evrakı dosyaya ekler.
7. Sistem süre adayı çıkarır.
8. Kullanıcı süreyi doğrular.
9. Hareket okundu olarak işaretlenir.

### Hata yolları

- Bağlantı yok
- Kimlik doğrulama süresi dolmuş
- Dosya eşleşmesi belirsiz
- Evrak indirilemiyor

### Kabul noktası

UYAP kaynaklı veri ayrı source_type taşır; şifre ve token loglanmaz.

## 13. UF-11 — Offline ve ağ kesintisi

### Ana akış

1. Ağ kesilir.
2. Kullanıcı son dosya ve mesaj cache'ini görebilir.
3. Yeni metin mesajı `gönderilemedi/kuyrukta` statüsüne alınır.
4. Ağ geldiğinde kullanıcı onayı veya otomatik politika ile yeniden gönderilir.
5. Idempotency çift kayıt oluşmasını engeller.

### Sınırlar

- Yeni hukuk araması offline çalışmaz.
- Belge analiz işi offline başlatılmaz.
- Hassas belgeler varsayılan olarak kalıcı cihaz cache'inde tutulmaz.

## 14. UF-12 — Dosya silme ve geri alma

### Ana akış

1. Kullanıcı dosyayı silmek ister.
2. Etki özeti ve geri alma süresi gösterilir.
3. Kullanıcı doğrular.
4. Dosya soft-delete olur.
5. Çöp kutusunda geri alınabilir.
6. Legal hold varsa kalıcı silme engellenir.
7. Süre sonunda purge işi çalışır.
8. Yedek saklama ve silme izi kaydedilir.

### Kabul noktası

Silme işlemi audit kaydı ve retention politikasıyla izlenebilir.

## 15. UF-13 — Büro içi inceleme

### Ana akış

1. Hazırlayan kullanıcı taslağı incelemeye gönderir.
2. Yetkili avukat bildirim alır.
3. Kaynak, delil ve değişiklik izlerini inceler.
4. Yorum veya düzeltme yapar.
5. Taslak:
   - değişiklik istendi,
   - onaylandı,
   - dışa aktarıldı
   statülerinden birine geçer.

### Kabul noktası

Onay geçmişi, düzenleyen kullanıcı ve sürümler korunur.

## 16. Uçtan uca pilot akışı

1. Ayıplı araç dosyası oluştur.
2. Kullanıcı olay anlatımını girsin.
3. Satış sözleşmesi ve ekspertiz raporu yüklensin.
4. Satış tarihi/tutarı/araç bilgileri çıkarılsın.
5. Çelişkili tarih örneği çözülsün.
6. Eksik ihbar tarihi kritik olarak gösterilsin.
7. Doğrulanmış mevzuat ve içtihat aransın.
8. Kaynaklar hukuki meseleye bağlansın.
9. Dilekçe planı oluşturulsun.
10. Kaynak bağlantılı taslak üretilebilsin.
11. DOCX dışa aktarılsın.

Bu akış P2 beta öncesi zorunlu E2E senaryodur.
