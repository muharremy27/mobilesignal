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
sudo API_URL=[https://mobilesignal.tr](https://mobilesignal.tr) API_KEY=PANELDEKI_ANAHTAR sh install.sh
