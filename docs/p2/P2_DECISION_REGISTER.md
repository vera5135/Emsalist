# P2 Decision Register

Bu belge P2 boyunca alınan ürün ve mimari kararlarının kayıt defteridir. Her karar `Accepted`, `Deferred`, `Rejected` veya `Superseded` durumlarından biriyle tutulur. Kabul edilmiş karar değiştirilirse eski kayıt silinmez; yeni karar eski kaydı supersede eder.

## Kabul edilmiş kararlar

| ID | Konu | Karar | Durum | Gerekçe | Yeniden değerlendirme |
|---|---|---|---|---|---|
| P2-D001 | Birincil platform | iOS-first | Accepted | Ana kullanıcı kitlesi avukatlar; birincil dağıtım App Store | P2 beta sonrası Android |
| P2-D002 | Mobil teknoloji | Flutter | Accepted | Tek kod tabanı ve sonraki Android seçeneği | P2.1 başlangıcı |
| P2-D003 | Ana kullanıcı deneyimi | Chat-first | Accepted | Form yükünü azaltmak ve doğal dosya anlatımı | Kullanılabilirlik testleri |
| P2-D004 | Tema | Sistem teması varsayılan; açık/koyu manuel seçenek | Accepted | Platform davranışıyla uyum | P2.1 |
| P2-D005 | Üst çubuk tema ikonu | Kalıcı güneş/ay ikonu yok | Accepted | Alanı ve sadeliği korumak | P2.1 beta |
| P2-D006 | UYAP göstergesi | Kompakt ikon + durum + rozet | Accepted | Büyük kalıcı kapsül yerine sade görünüm | P2.10 |
| P2-D007 | İlk pilot | Ayıplı araç/tüketici hukuku | Accepted | Tarih, tutar, belge, ihbar ve kaynak ilişkilerini birlikte test eder | Pilot kapanışı |
| P2-D008 | Backend | FastAPI + PostgreSQL devam | Accepted | P1 kabul edilmiş altyapı korunur | Ölçek ihtiyacı doğarsa |
| P2-D009 | Kaynak sırası | Güvenilir kaynak omurgası aramadan önce | Accepted | Uydurma ve güncellik riskini azaltır | Değişmez ilke |
| P2-D010 | Semantik katman | Kaynak ve dosya omurgasından sonra | Accepted | Sonuçların izlenebilir olması gerekir | Değişmez ilke |
| P2-D011 | UYAP ilk sürüm | Okuma/eşleştirme ağırlıklı; otomatik gönderim yok | Accepted | Güvenlik ve hukuki riski sınırlar | Ayrı fizibilite sonrası |
| P2-D012 | P2.0 kapsamı | Dokümantasyon ve sözleşme; ürün kodu yok | Accepted | Yeniden iş riskini azaltır | P2.0 kapanışı |
| P2-D013 | Asistan soru biçimi | Bir seferde en kritik tek soru | Accepted | Kullanıcı yükünü azaltır | Konuşma testleri |
| P2-D014 | Dosya hafızası | Yapılandırılmış, kaynak bağlantılı ve sürümlü | Accepted | Sohbet özeti tek başına yeterli değildir | Veri modeli review |
| P2-D015 | Belge çıkarımı | Doğrulama statülü; otomatik kesinleştirme yok | Accepted | Çıkarım hatalarının dosyayı bozmaması | P2.5 |
| P2-D016 | Flutter dizini | Monorepo içinde `/mobile` | Accepted | CI ayrımı ve backend'den bağımsız build | P2.1 |
| P2-D017 | Bundle identifiers | prod `com.emsalist.app`, staging `.staging`, dev `.dev` | Accepted | Ortam ayrımı | Signing öncesi sahiplik kontrolü |
| P2-D018 | Hesap modeli | Her kullanıcı workspace içinde; bireysel kullanıcıya personal workspace | Accepted | Bireysel ve büro modelini tek altyapıda birleştirir | Beta geri bildirimi |
| P2-D019 | İlk giriş yöntemi | E-posta/parola + doğrulama; Apple Sign In beta öncesi | Accepted | Basit ilk kurulum ve iOS uyumu | P2.2 |
| P2-D020 | MFA | İlk kapalı betada opsiyonel, production öncesi yüksek riskli hesaplarda sunulur | Accepted | Güvenlik/kullanılabilirlik dengesi | Security review |
| P2-D021 | Offline kapsamı | Şifreli son dosya/mesaj cache'i ve metin retry kuyruğu; belge bytes yok | Accepted | Minimum çevrimdışı fayda ve veri riski | P2.3 beta |
| P2-D022 | Offline cache sınırı | Son 20 dosya ve dosya başına son 200 mesaj; kullanıcı logout'unda temizleme | Accepted | Cihaz depolama ve gizlilik sınırı | Telemetry sonrası |
| P2-D023 | Silme geri alma | 30 gün soft-delete; legal hold purge'ü engeller | Accepted | Geri alma ve hukuki saklama dengesi | Hukuki inceleme |
| P2-D024 | Belge boyutu | İlk beta 25 MB; parçalı yükleme sonrası 100 MB | Accepted | Kullanılabilirlik ve maliyet dengesi | P2.5 performans |
| P2-D025 | UDF çözümleme | Yalnız backend ve sandbox parser | Accepted | Mobil güvenlik ve bakım kolaylığı | Parser fizibilitesi |
| P2-D026 | Kaynak insan incelemesi | Kritik/çelişkili kaynaklar editör kuyruğuna | Accepted | Nihai dilekçe kaynak kalitesini korur | P2.6 SLA |
| P2-D027 | Bildirim mimarisi | Backend outbox + idempotent APNs/FCM adapter | Accepted | Teslimat güvenilirliği ve platform bağımsızlığı | P2.10 |
| P2-D028 | DOCX şablonları | Sistem + büro + taslak override; şablon sürümlü | Accepted | Büro standardı ve izlenebilirlik | P2.9 |
| P2-D029 | AI sağlayıcısı | Provider abstraction zorunlu; iş mantığı sağlayıcıya gömülmez | Accepted | Outage, maliyet ve sağlayıcı değişimi | Her model değişimi |
| P2-D030 | Veri yerleşimi | Başlangıçta AB/AEA bölgesi; beta öncesi Türkiye seçeneği ve aktarım incelemesi | Accepted | Hızlı teknik başlangıç ve ayrı hukuk kapısı | Beta go/no-go |
| P2-D031 | Backup bölgesi | Primary ile aynı hukuk/kontrat politikasına tabi ayrı zone/region | Accepted | Dayanıklılık ve veri politikası uyumu | Infrastructure review |
| P2-D032 | Beta kapsamı | 15 avukat, davetli ve ücretsiz; tüketici pilotu öncelikli | Accepted | Yönetilebilir kapalı beta | P2.11 |
| P2-D033 | Ücretlendirme | Kapalı betada ödeme yok; fiyat beta maliyet/kullanım verisi sonrası | Accepted | Erken fiyat hatasını önlemek | Beta kapanışı |
| P2-D034 | Search baseline | PostgreSQL lexical/full-text + ayrı semantic adapter | Accepted | Mevcut altyapıyı korurken sağlayıcı esnekliği | P2.7 spike |
| P2-D035 | Mobil durum yönetimi | Feature-first repository/state katmanı; UI doğrudan HTTP çağırmaz | Accepted | Test edilebilirlik ve offline davranış | P2.1 ADR |
| P2-D036 | API istemcisi | OpenAPI tabanlı generated client + elle yazılmış repository adapter | Accepted | Sözleşme tutarlılığı | P2.1/P2.2 |
| P2-D037 | Uzun işlem modeli | Async job + polling baseline; streaming sonradan | Accepted | İlk sürüm sadeliği ve güvenilir retry | UX ölçümü sonrası |
| P2-D038 | Source citation | Citation deterministik renderer ile; model serbest citation üretemez | Accepted | Uydurma karar riskini azaltır | Değişmez güvenlik kuralı |
| P2-D039 | P2 branch stratejisi | Her milestone ayrı PR; main'e doğrudan push yok | Accepted | İzlenebilirlik ve rollback | Değişmez süreç kuralı |

## Deferred kararlar

| ID | Konu | Karar | Durum | Açılma koşulu |
|---|---|---|---|---|
| P2-D040 | Android production | P2 kapalı beta sonrasına ertelendi | Deferred | iOS beta hedefleri karşılanınca |
| P2-D041 | UYAP outbound işlem | Otomatik gönderim/e-imza ertelendi | Deferred | Ayrı hukuk, güvenlik ve teknik fizibilite |
| P2-D042 | Tam offline belge erişimi | İlk sürümde yok | Deferred | Cihaz şifreleme ve iş ihtiyacı kanıtı |
| P2-D043 | Gelişmiş CRM/muhasebe | P2 kapsam dışı | Deferred | Ana hukuk çalışma akışı tamamlanınca |

## Karar alma kuralı

- Kritik kararlar PR açıklamasında listelenir.
- Kabul edilmiş karar değişirse yeni ID ile kayıt açılır.
- Güvenlik, gizlilik, tenant izolasyonu ve kaynak doğrulama kararları yalnız UI veya hız gerekçesiyle gevşetilemez.
- `Deferred` kararlar backlog'a otomatik dahil edilmez.
- Hukuki inceleme gerektiren uygulama metinleri beta go/no-go kapısında ayrıca onaylanır.
