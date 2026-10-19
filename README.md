<p align="center"><img src="assets/zilli-logo.svg" alt="Zilli" width="240"></p>

# Zilli

Okul zil programı: ders saatlerine göre öğrenci, öğretmen ve teneffüs zillerini çalar; teneffüs müziği ve İstiklal Marşı düğmeleri vardır. Eski bilgisayarlarda da hızlı çalışır.

*School bell software for Turkish schools (Windows 7–11, Linux). The interface is in Turkish.*

## İndir

Hazır paketler [Releases](../../releases) sayfasındadır:

| Paket | Çalıştığı sistemler |
|---|---|
| `Zilli-Kurulum-<sürüm>.exe` | Windows 7 SP1, 8, 8.1, 10, 11 (32 ve 64 bit), ek güncelleme gerekmez |
| `Zilli-x86_64.AppImage` | 2018 sonrası 64 bit Linux dağıtımları (Ubuntu 18.04+, Debian 10+, Pardus 19+, Mint 19+, Fedora...) |
| `zilli_<sürüm>_amd64.deb` | Debian/Ubuntu/Pardus/Mint, Ubuntu 18.04 ve sonrası |

## Özellikler

- **Pano:** büyük saat, günün çizelgesi (dersler, teneffüsler ve "şimdi" çizgisi), sonraki zile geri sayım ve sıradaki üç zil; olay kaydı tek tıkla açılır
- **Zil Saatleri:** Hafta İçi / Cumartesi / Pazar için ayrı, 16 derse kadar; öğrenci zili dersten 15 sn – 3 dk önce, öğretmen zili ders başında, teneffüs zili ders sonunda
- **Melodiler:** öğrenci, öğretmen ve teneffüs zili için ayrı melodi ve ses seviyesi; günün son zili için ayrı "Son Zil" (varsayılan MEB Çıkış Zili); dosya ekleme düğmesi
- Çalan sesin adı, süresi ve ilerleme çubuğu üst bilgide görünür
- **Müzik ve Marşlar:** teneffüste rastgele müzik (sonraki zilden 30 sn önce yavaşça susar), İstiklal Marşı, İstiklal Marşı (Enstrümental), Saygı Duruşu + İstiklal Marşı ve Siren
- **Ayarlar:** üç tema (Açık, Gece, Yüksek kontrast; tüm yazılar WCAG okunurluk oranlarını karşılar), açılışta otomatik başlatma
- **Sistem tepsisi:** pencere kapatılırken küçültme sorulur; küçültülünce görev çubuğunda yer kaplamaz, tepsi simgesinden açılır. Linux'ta StatusNotifierItem (KDE, GNOME AppIndicator, XFCE, Cinnamon), yoksa eski XEmbed tepsisi kullanılır
- Bilgisayar uykudan uyanırsa 1 dakikadan eski zilleri çalmaz; aynı anda iki kopya açılmaz; ayarlar elektrik kesintisinde bozulmaz
- Eksik veya bozuk ses dosyası programı durdurmaz: Melodiler sayfasında "Ses dosyası yok" yazar, elle çalınınca hata penceresi açılır, zamanlı zilde "Son olaylar"a yazılır. Bozuk ayar dosyası `zilli.json.bozuk` olarak kenara alınır, varsayılanlarla açılır

Ses biçimleri: mp3, wav, ogg, flac (mid yalnız Windows'ta).

## Kurulum ve otomatik başlatma

- **Windows:** `Zilli-Kurulum-….exe`'yi çalıştırın. Yönetici gerekmez. "Bilgisayar açılınca başlasın" işaretliyse oturum açılınca simge durumunda başlar.
- **.deb:** `sudo apt install ./zilli_1.1.0_amd64.deb` — tüm kullanıcılar için açılışta başlar.
- **AppImage:** dosyaya çalıştırma izni verip (`chmod +x`) bir kez açın; kendini açılışa ekler.

Linux'ta ses dosyaları ve ayarlar `~/Zilli` klasöründedir; Windows'ta programın kurulduğu klasördedir. Ayarlar sayfasında "Veri klasörü → Aç".

Zilli **oturum açıldığında** başlar. Bilgisayar açılıp oturum açılmadan zil çalmaz.

> [!WARNING]
> **Güvenlik uyarısı: otomatik oturum açma önerilmez.** Parolasız oturum açan bir bilgisayarı açan herkes o hesaptaki her şeye (e-posta, kayıtlı tarayıcı şifreleri, e-Okul/MEBBİS oturumları, öğrenci bilgileri, ağ paylaşımları) erişir. Okul bilgisayarlarında bu ciddi bir risktir.
>
> Yine de otomatik oturum açmak zorundaysanız riski azaltın:
> - Yalnızca zil için **ayrı, yönetici olmayan (standart) bir yerel hesap** açın; okulun asıl hesabını kullanmayın.
> - O hesapta e-posta, tarayıcı oturumu, kayıtlı şifre ve kişisel/öğrenci dosyası **bulunmasın**; ağ paylaşımlarına ve yazıcılara erişimi olmasın.
> - Oturum açılınca **ekranı kilitleyin**: Zilli kilit ekranının arkasında çalışmaya ve zil çalmaya devam eder. Windows'ta Görev Zamanlayıcı → "Oturum açıldığında" tetikleyicisiyle `rundll32.exe user32.dll,LockWorkStation` çalıştırılabilir.
> - Uzak masaüstünü kapatın, bilgisayarı ve ses sistemini fiziksel olarak güvenli bir yerde tutun.
>
> Otomatik oturum açmayı açmak: Windows'ta `Win+R` → `netplwiz` → "Kullanıcıların bu bilgisayarı kullanmak için bir kullanıcı adı ve parola girmesi gerekir" işaretini kaldırın; Linux'ta Ayarlar → Kullanıcılar → Otomatik Oturum Aç.

## Geliştirme

```bash
pip install -r requirements.txt   # Python 3.7+ (kod 3.7 uyumlu kalmalı)
python zilli.py
python test_zilli.py
```

Paketler (Linux makinede):

```bash
packaging/linux/build.sh     # AppImage + .deb  (docker gerekir)
packaging/windows/build.sh   # Windows kurulumu (wine gerekir)
```

- Derleme betikleri indirdikleri her dosyayı sha256 ile doğrular; kütüphaneler `packaging/*/requirements.lock` dosyalarından `--require-hashes` ile kurulur. `requirements.txt` değişince `packaging/lock.sh` çalıştırın.
- Linux paketleri Ubuntu 18.04 kapsayıcısında kaynaktan derlenen Python 3.8 + Tk 8.6 (düzgün yazı tipleri için Xft) ile hazırlanır, hedef sistemde Python gerekmez.
- Windows paketi resmi 32 bit Python 3.7.9, PyInstaller 5.13.2 ve Inno Setup 6.2.2 ile hazırlanır. Python 3.8+ Windows 7'de KB2533623 güncellemesi olmadan açılmaz; bu yüzden 3.7.9'da kalın. Microsoft'un Universal C Runtime DLL'leri programın yanına konur, böylece KB2999226 da gerekmez.
- Programla gelen sesler `sounds/` klasöründedir (Melodiler, Marşlar). Program müzik içermez; teneffüs müziğini kullanıcı "Müzik ekle…" ile ekler.
- Simge ve logo `assets/` içindedir (`zilli.svg`, `zilli-logo.svg`); PNG/ICO dosyaları bu SVG'den üretilmiştir.
- Yazı tipi: [Atkinson Hyperlegible Next](https://github.com/googlefonts/atkinson-hyperlegible-next) (Regular ve Bold), `assets/fonts/` içinde programla gelir ve kurulmadan yalnız Zilli için yüklenir; yüklenemezse sistem yazı tipi kullanılır.

## Lisans

Zilli özgür yazılımdır: [GNU Genel Kamu Lisansı v3](LICENSE) (GPL-3.0-or-later) koşullarıyla kullanabilir, değiştirebilir ve dağıtabilirsiniz. Copyright © 2026 Gökay.

Atkinson Hyperlegible Next yazı tipi SIL Open Font License 1.1 ile dağıtılır ([assets/fonts/OFL.txt](assets/fonts/OFL.txt)); Copyright 2020-2024 The Atkinson Hyperlegible Next Project Authors.
