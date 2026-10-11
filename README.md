# MobileSignal — Sunucu & WordPress İzleme Monitörü

[MobileSignal](https://mobilesignal.tr), sunucunuzu ve web sitelerinizi 7/24 izleyerek kritik durumlarda **anında cebinize mobil bildirim** gönderen yeni nesil bir izleme altyapısıdır.

Sunucunuz çöktüğünde ya da siteniz hata verdiğinde terminale veya e-postaya bakmakla vakit kaybetmeyin. İster tek komutla kurulan Linux sunucu ajanıyla, ister hazır WordPress eklentisiyle tüm kontrol parmaklarınızın ucunda.

---

## 🚀 Öne Çıkan Özellikler

- **Linux Sunucu Monitörü:** CPU, RAM, Disk veya Load kritik eşiğe ulaştığında anında uyarı.
- **Suçlu İşlem & URL Tespiti:** Apache / LiteSpeed / nginx fark etmeksizin en çok kaynak tüketen işlem (`PID`, `lsphp`, `php-fpm`) ve en çok vurulan URL raporda listelenir.
- **WordPress Entegrasyonu:** WooCommerce siparişleri, form gönderimleri ve kritik PHP/500 hataları için kod yazmadan anlık mobil bildirim.
- **Eylem Butonları:** Telefondaki tek bir butona basarak sunucunun o anki load/yük durumunu anında sorgulama.
- **Hafif ve Bağımsız:** Harici kütüphane veya `pip` gerektirmez (sadece Python3 standart kütüphanesi).

---

## 🔌 1) WordPress Eklentisi ile Entegrasyon

WordPress ve WooCommerce siteleriniz için sunucuya ajan kurmanıza gerek kalmadan uygulama düzeyinde bildirim alabilirsiniz.

### Neler Bildirilir?
- **WooCommerce Siparişleri:** Yeni sipariş, tutar ve müşteri detayıyla cebinizde.
- **Kritik PHP & Site Hataları:** Fatal error, veritabanı bağlantı kopması veya 500 hataları.
- **Form Bildirimleri:** İletişim formu ve randevu taleplerinde anında tetikleme.

### Kurulum Adımları
1. [MobileSignal Paneli](https://mobilesignal.tr)'ne giriş yapıp **API Anahtarları** bölümünden siteniz için bir API anahtarı alın.
2. WordPress yönetim panelinizden **MobileSignal** eklentisini yükleyip etkinleştirin.
3. Eklenti ayarlarına API anahtarınızı girin ve almak istediğiniz bildirim tiplerini (Siparişler, Hatalar vb.) işaretleyin.

---

## 🖥️ 2) Linux Sunucu Ajanı Kurulumu (Root ile)

Sunucu seviyesinde (CPU, RAM, Disk, Load ve Web sunucusu logları) izleme yapmak için ajanı tek komutla kurabilirsiniz.

### Tek Satırda Kurulum
```sh
sudo API_URL=https://mobilesignal.tr API_KEY=PANELDEKI_ANAHTAR sh install.sh
```

Manuel dosya kurulumu için:
```sh
# Dosyaları sunucuya kopyaladıktan sonra:
sudo sh install.sh
```

Kurulum sonunda test bildirimi otomatik olarak telefonunuza gönderilir. Ulaşmazsa:
```sh
python3 /usr/local/bin/ms-monitor --test
cat /var/log/mobilesignal-monitor.log
nano /etc/mobilesignal/monitor.conf   # API_URL ve API_KEY alanlarını kontrol edin
```

---

## ⚙️ 3) Ajan Ayarları (`/etc/mobilesignal/monitor.conf`)

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `API_URL` | `https://mobilesignal.tr` | [MobileSignal](https://mobilesignal.tr) servis adresi |
| `API_KEY` | *(boş)* | Panel → API Anahtarları sayfasındaki site anahtarınız (**zorunlu**) |
| `SITE_AD` | hostname | Bildirim başlığındaki sunucu/site öneki |
| `CHECK_INTERVAL` | `60` | Kontrol aralığı (saniye, min: 15) |
| `CPU_CRIT` / `RAM_CRIT` / `DISK_CRIT` | `85/85/90` | Yüzdelik kritik eşikler (`0` = devre dışı) |
| `LOAD_CRIT` | `0` | 5 dakikalık load eşiği (`0` = `CPU Çekirdek Sayısı × 2`) |
| `PROC_CPU_CRIT` / `PROC_RAM_CRIT` | `50/20` | Tek bir işlemin aşabileceği maksimum limit |
| `TOP_N` | `5` | Raporda yer alacak en ağır işlem ve URL sayısı |
| `ALERT_COOLDOWN_DK` | `15` | Bildirim sıklığı / spam engelleme (dakika) |
| `WEBHOOK_PORT` | `9273` | Butonla anlık sorgu portu (`0` = kapalı) |
| `WEBHOOK_SECRET` | *(boş)* | Sorgu için güvenlik anahtarı (`?key=`) |

> **Not:** Kritik sunucu uyarıları `site_hatasi` olayıyla iletilir. [MobileSignal Paneli](https://mobilesignal.tr)'nde **Uyarı Kuralları → Site Hatası** seçeneğinin açık olduğundan emin olun.

---

## 📲 4) Butonla Anlık Load Sorgulama (Telefondan)

1. Sunucu güvenlik duvarında webhook portunu açın:
   ```sh
   ufw allow 9273/tcp            # RHEL / CentOS için: firewall-cmd --add-port=9273/tcp --permanent
   ```
2. `monitor.conf` içerisindeki `WEBHOOK_SECRET` değerinizi alın (`install.sh` otomatik oluşturur).
3. [MobileSignal Paneli](https://mobilesignal.tr) üzerinden **Eylem Butonları → Yeni** yolunu izleyin:
   - **Başlık:** `Sunucu Durumu`
   - **Tip:** `webhook` | **Metod:** `GET`
   - **URL:** `http://SUNUCU_IP_ADRESI:9273/load?key=GIZLI_ANAHTAR`
4. Mobil uygulamada **Ekran** sekmesindeki butona bastığınızda sunucunun anlık CPU, RAM, Load ve en çok vuran URL özeti ekranınıza gelir.

---

## 📊 5) Ajan Ne Raporlar?

- **Sistem Kaynakları:** CPU %, RAM % (kullanılan/toplam MB), Load (1/5/15 dk), Disk doluluk yüzdeleri.
- **Ağır İşlemler:** `ps` üzerinden tespit edilen yüksek tüketimli servisler (`apache2`, `httpd`, `lshttpd`, `lsphp`, `php-fpm` vb.).
- **Tetikleyici Dosyalar:** Komut satırından tespit edilen betikler (örn: `/wp-admin/admin-ajax.php`, `/cron.php`).
- **Hedef URL'ler:** Apache, LiteSpeed ve Nginx erişim logları taranarak en çok istek alan URL'ler.

---

## 🛠️ 6) Yönetim Komutları

```sh
systemctl status ms-monitor                  # Servis durumunu kontrol et
journalctl -u ms-monitor -f                  # Canlı logları izle
python3 /usr/local/bin/ms-monitor --status   # Anlık sistem özetini yazdır
python3 /usr/local/bin/ms-monitor --once     # Tek seferlik kontrol çalıştır
sudo sh uninstall.sh                         # Ajanı kaldır (ayarlar korunur)
```

---

## 🔗 Bağlantılar

- **Web Sitesi & Panel:** [mobilesignal.tr](https://mobilesignal.tr)
- **API Dokümantasyonu:** [mobilesignal.tr](https://mobilesignal.tr)
- **Destek & İletişim:** [mobilesignal.tr](https://mobilesignal.tr)

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
