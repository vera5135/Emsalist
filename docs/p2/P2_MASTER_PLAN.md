# Emsalist P2 Master Plan

## 1. Amaç

P2, Emsalist'i mevcut backend temeli üzerinde çalışan iOS-first bir hukuk çalışma alanına dönüştürür. Ürün; dosya hafızası, belge analizi, güvenilir hukuk kaynakları, hibrit arama, hukuki mesele grafiği, kaynak bağlantılı dilekçe üretimi ve kontrollü UYAP entegrasyonunu tek mobil deneyimde birleştirir.

## 2. Başarı tanımı

P2 başarılı sayılabilmek için kullanıcı şu uçtan uca akışı güvenli ve izlenebilir biçimde tamamlayabilmelidir:

1. Yeni dosya açar.
2. Olayı doğal dille anlatır.
3. Belge yükler.
4. Sistem yapılandırılmış olay, tarih, taraf, talep, delil, eksik ve çelişki çıkarır.
5. Kullanıcı kritik bilgileri doğrular veya düzeltir.
6. Sistem güvenilir mevzuat ve içtihat arar.
7. Kaynakları hukuki mesele, iddia ve delillerle eşleştirir.
8. Kaynak bağlantılı dilekçe taslağı oluşturur.
9. Kullanıcı her paragrafın dayanağını inceler.
10. Taslağı DOCX/PDF olarak dışa aktarır.
11. UYAP hareketlerini ilgili dosyayla eşleştirir.

## 3. Sabit ürün kararları

- Birincil dağıtım kanalı iOS App Store'dur.
- Mobil istemci Flutter ile geliştirilecektir.
- Backend FastAPI ve PostgreSQL üzerinde devam eder.
- Ana deneyim chat-first olacaktır.
- Varsayılan tema `ThemeMode.system`; manuel açık/koyu geçişi ayarlarda bulunur.
- Üst çubukta kalıcı güneş/ay simgesi bulunmaz.
- UYAP durumu kompakt bir ikonla gösterilir; yeni hareketler rozetle işaretlenir.
- İlk uçtan uca pilot `ayıplı araç / tüketici hukuku` dosyasıdır.
- Android ana yayın hedefi P2 beta sonrasıdır.
- P2.0 yalnızca planlama ve sözleşme aşamasıdır.

## 4. Mimari sıralama ilkesi

Aşamalar şu bağımlılık sırasıyla uygulanır:

1. Mobil kabuk ve istemci mimarisi
2. Kimlik, oturum ve yetki
3. Dosya ve konuşma modeli
4. Yapılandırılmış dosya hafızası
5. Belge işleme hattı
6. Güvenilir hukuk kaynağı omurgası
7. Hibrit arama
8. Hukuki mesele ve delil grafiği
9. Kaynak bağlantılı dilekçe üretimi
10. UYAP Bridge
11. Bildirimler, beta ve App Store hazırlığı

Semantik arama, otomasyon veya UYAP genişletmesi; kaynak doğrulama ve dosya izolasyonu tamamlanmadan öne alınamaz.

## 5. P2 aşamaları

### P2.0 — Ürün ve mimari planlama

Çıktılar:

- ürün kapsamı
- kullanıcı ve dosya akışları
- mobil bilgi mimarisi
- konuşma tasarımı
- veri modeli
- API sözleşmesi
- güvenlik/KVKK modeli
- test stratejisi
- kabul matrisi
- risk kaydı
- backlog ve bağımlılık haritası

Kapanış kapısı:

- açık kritik ürün kararı kalmaması
- kapsam içi/dışı maddelerin onaylanması
- pilot senaryonun ölçülebilir kabul kriterlerinin yazılması
- Flutter ve backend sorumluluk sınırlarının belirlenmesi

### P2.1 — Mobil uygulama kabuğu

Kapsam:

- Flutter proje başlangıcı
- iOS-first tasarım sistemi
- otomatik/açık/koyu tema
- ana sohbet ekranı
- dosya drawer'ı
- alt mesaj oluşturucu
- UYAP durum ikonu
- ayarlar ve görünüm menüsü
- bağlantı, boş durum ve hata ekranları

Kapanış kapısı:

- küçük iPhone ekranında taşma olmaması
- klavye ve safe-area davranışının doğru olması
- tema geçişlerinin test edilmesi
- erişilebilir etiketlerin bulunması
- mock veriyle temel navigasyonun çalışması

### P2.2 — Kimlik, oturum ve büro bağlamı

Kapsam:

- giriş/çıkış
- access/refresh token yaşam döngüsü
- güvenli cihaz depolaması
- oturum yenileme
- oturum iptali
- kullanıcı ve büro seçimi
- yetki hatalarının kullanıcıya açıklanması

Kapanış kapısı:

- token sızıntısı olmaması
- süresi dolan oturumun kontrollü yenilenmesi
- yetkisiz dosya erişiminin engellenmesi

### P2.3 — Dosya ve konuşma

Kapsam:

- dosya oluşturma, listeleme, arşivleme ve silme talebi
- aktif dosya seçimi
- konuşma ve mesaj kalıcılığı
- mesaj durumları: gönderiliyor, gönderildi, işleniyor, tamamlandı, başarısız
- tekrar deneme ve idempotency

Kapanış kapısı:

- dosyalar arası veri karışmaması
- mesaj tekrar denemesinde çift kayıt oluşmaması
- ağ kesintisinde kullanıcıya açık durum gösterilmesi

### P2.4 — Yapılandırılmış dosya hafızası

Temel varlıklar:

- CaseParty
- CaseFact
- TimelineEvent
- Claim
- Defense
- Evidence
- MissingInformation
- Contradiction
- Risk
- Deadline
- LegalIssue

Her kayıt için:

- kaynak türü ve kaynak kimliği
- güven skoru
- doğrulama statüsü
- değişiklik geçmişi
- oluşturan/değiştiren kullanıcı

Kapanış kapısı:

- kullanıcı beyanı, belge ve UYAP kaynağının ayrıştırılması
- çelişkili değerlerin kesin bilgiye dönüşmemesi
- kritik eksikler tamamlanmadan genel riskin düşük gösterilmemesi

### P2.5 — Belge işleme hattı

Formatlar:

- PDF, UDF, DOCX, TXT, JPG, JPEG, PNG

Akış:

- tür ve boyut kontrolü
- zararlı içerik kontrolü
- hash ve tekrar belge kontrolü
- güvenli depolama
- metin çıkarma
- sayfa/paragraf konumlandırma
- belge türü tespiti
- bilgi çıkarımı
- kullanıcı onayı

Kapanış kapısı:

- çıkarılan her bilginin belge konumuna bağlanması
- okunamayan ve eksik sayfaların işaretlenmesi
- aynı belgenin tekrar yüklenmesinin yönetilmesi

### P2.6 — Güvenilir hukuk kaynağı omurgası

Kaynaklar:

- mevzuat
- Resmî Gazete
- Yargıtay
- Danıştay
- Anayasa Mahkemesi
- Uyuşmazlık Mahkemesi
- doğrulanmış ikincil kaynaklar
- kontrollü doktrin

Zorunlu metadata:

- kurum/mahkeme/daire
- esas ve karar numarası
- karar/yayım/yürürlük tarihi
- resmî URL
- içerik hash'i
- alınma zamanı
- doğrulama ve güncellik durumu
- önceki/sonraki sürüm ilişkisi

Kapanış kapısı:

- doğrulanmamış kaynağın doğrulanmış görünmemesi
- tekrar kararların birleştirilmesi
- kullanılan kaynağın dosya ve dilekçe bağlamında izlenmesi

### P2.7 — Hibrit hukuk araması

Arama sinyalleri:

- anahtar kelime
- tam metin
- semantik benzerlik
- mahkeme otoritesi
- karar tarihi
- doğrulama statüsü
- dosya olayına uyum
- hukuki mesele uyumu
- sonuç yönü
- tekrar kayıt cezası

Kapanış kapısı:

- benchmark setinde ilk 3 ve ilk 10 başarı oranlarının ölçülmesi
- karşıt kararların ayrı işaretlenmesi
- alakasız teknik kaynakların normal kullanıcıya gösterilmemesi

### P2.8 — Hukuki mesele ve delil grafiği

Bağlantılar:

- mesele ↔ olay
- mesele ↔ delil
- mesele ↔ eksik bilgi
- mesele ↔ risk
- mesele ↔ mevzuat/içtihat
- mesele ↔ karşı argüman
- mesele ↔ dilekçe paragrafı

Kapanış kapısı:

- her ana iddianın delil ve kaynak durumunun görülebilmesi
- ispat yükü ve karşı argümanın kayıt altına alınması

### P2.9 — Kaynak bağlantılı dilekçe

Akış:

- dosya yeterlilik kontrolü
- eksik ve çelişki kontrolü
- hukuki mesele ve talep seçimi
- kaynak ve delil eşleştirme
- taslak planı
- bölüm/paragraf üretimi
- kaynak doğrulama
- avukat incelemesi
- DOCX/PDF dışa aktarma

Kapanış kapısı:

- her önemli paragrafın olay, delil ve kaynak metadata'sına bağlanması
- doğrulanmamış emsal numarası bulunmaması
- sonuç/talep ile açıklamalar arasında tutarlılık kontrolü

### P2.10 — UYAP Bridge

İlk sürüm kapsamı:

- bağlantı durumu
- son kontrol zamanı
- dosya numarası eşleştirme
- manuel evrak ekleme
- yeni hareket rozeti
- hareket kartı
- evrakı dosyaya bağlama

İlk sürüm kapsam dışı:

- kullanıcı adına otomatik evrak gönderme
- e-imza
- otomatik dava açma

Kapanış kapısı:

- UYAP parolası veya token'ının loglanmaması
- entegrasyonun kapatılabilir olması
- bağlantı durumunun renk dışında ikon/metinle de açıklanması

### P2.11 — Beta ve App Store hazırlığı

Kapsam:

- kapalı avukat betası
- crash/performance takibi
- gerçek dosya ve büyük belge testleri
- gizlilik metinleri
- hesap ve veri silme akışları
- App Store metadata ve ekran görüntüleri

Kapanış kapısı:

- kritik güvenlik açığı olmaması
- kaynak uydurma testlerinin geçmesi
- veri silme ve hesap kapatma sürecinin doğrulanması
- pilot dosya akışının uçtan uca tamamlanması

## 6. Pilot: Ayıplı araç dosyası

Pilot veri alanları:

- satın alma tarihi
- satış bedeli
- satıcı ve alıcı
- marka/model/plaka/şasi
- ayıp türü ve ilk görülme tarihi
- servis kayıtları
- bilirkişi/ekspertiz raporu
- TRAMER bilgisi
- ayıp ihbarı ve noter ihtarı
- seçimlik hak
- zarar kalemleri
- görev/yetki ve süre riskleri

Pilot başarı kriteri:

- eksik alanların somut değer bazında tespit edilmesi
- iki kaynak arasındaki tarih/tutar/araç bilgisi çelişkisinin gösterilmesi
- en az bir doğrulanmış mevzuat ve bir doğrulanmış içtihat kaynağının ilgili iddiaya bağlanması
- kaynaklı taslağın DOCX olarak dışa aktarılması

## 7. Branch ve PR stratejisi

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

Her aşama ayrı PR ve ayrı kabul kapısına sahiptir. `main` dalına doğrudan push yapılmaz.

## 8. Definition of Done

Bir P2 PR'ı ancak aşağıdakiler tamamlandığında kapanabilir:

- kapsam ve kabul kriteri karşılandı
- unit/integration/widget testleri geçti
- API ve veri modeli dokümanı güncel
- migration doğrulandı
- OpenAPI drift yok
- güvenlik ve tenant izolasyonu kontrolleri geçti
- hata/boş/yükleniyor durumları işlendi
- erişilebilirlik kontrolü yapıldı
- bilinen risk ve rollback yöntemi yazıldı
- main CI tamamen yeşil

## 9. P2.0 açık kararları

Aşağıdaki kararlar P2.0 kapanmadan kesinleşmelidir:

1. Flutter proje dizini ve monorepo yapısı
2. iOS bundle identifier
3. bireysel avukat ve büro hesabı modeli
4. ilk kimlik doğrulama yöntemi
5. Apple ile giriş kapsamı
6. offline önbellek sınırı
7. silme geri alma süresi
8. belge maksimum boyutu
9. UDF çözümleme yaklaşımı
10. kaynak insan inceleme süreci
11. bildirim altyapısı
12. DOCX şablon sahipliği
13. yapay zekâ sağlayıcı soyutlaması
14. veri barındırma bölgesi
15. beta kullanıcı sayısı ve çıkış kriterleri
16. ücretlendirme kapsamı

## 10. P2.0 kapanış çıktısı

P2.0 PR'ı; bütün plan belgelerini, karar kaydını, kabul matrisini, risk kaydını ve uygulanabilir backlog'u içermelidir. Bu PR onaylanmadan ürün kodu geliştirmesi başlamaz.
