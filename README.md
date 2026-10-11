# MobileSignal Sunucu Monitörü

Linux sunucunu 7/24 izler, kritik değerde **telefona bildirim** atar.
Apache / LiteSpeed / nginx fark etmez — en çok CPU-RAM yiyen işlem + URL/dosya raporda gelir.
İsteyen, telefondaki **eylem butonuna** basıp anlık load değerini görür.

- Tek dosya: `ms-monitor.py` (sadece Python3 stdlib — `pip` gerekmez)
- Tüm dağıtımlar: Debian/Ubuntu, RHEL/CentOS/Alma/Rocky, Arch, openSUSE, Alpine
- Arka planda çalışır: systemd → OpenRC → SysV → cron+nohup (otomatik sırayla dener)
- Bildirim ucu: `POST {API_URL}/site_ajax.php` → `action=ms_notify`

## 1) Hızlı kurulum (sunucuda, root ile)

```sh
# dosyaları sunucuya at (ör: /root/ms/ içine), sonra:
sudo sh install.sh
```

Tek satırda API ile:

```sh
sudo API_URL=https://mobilesignal.tr API_KEY=PANELDEKI_ANAHTAR sh install.sh
```

Kurulum sonunda otomatik `--test` bildirimi telefona düşer. Düşmezse:

```sh
python3 /usr/local/bin/ms-monitor --test
cat /var/log/mobilesignal-monitor.log
nano /etc/mobilesignal/monitor.conf   # API_URL / API_KEY kontrol
```

## 2) Ayarlar (`/etc/mobilesignal/monitor.conf`)

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `API_URL` | `https://mobilesignal.tr` | Panel adresin (`/site_ajax.php` otomatik eklenir) |
| `API_KEY` | *(boş)* | Panel → API Anahtarları → site anahtarın (**zorunlu**) |
| `SITE_AD` | hostname | Bildirim başlığına prefix |
| `CHECK_INTERVAL` | `60` | Kontrol aralığı sn (min 15) |
| `CPU_CRIT` / `RAM_CRIT` / `DISK_CRIT` | `85/85/90` | % eşik (`0`=kapat) |
| `LOAD_CRIT` | `0` | 5-dk load eşiği; `0`=otomatik (`cpu_sayısı×2`) |
| `PROC_CPU_CRIT` / `PROC_RAM_CRIT` | `50/20` | Tek işlem %eşiği |
| `TOP_N` | `5` | Raporda kaç işlem/URL |
| `ALERT_COOLDOWN_DK` | `15` | Aynı uyarı en fazla bu sıklıkta (spam koruması) |
| `WEBHOOK_PORT` | `9273` | Buton sorgu portu (`0`=kapat) |
| `WEBHOOK_SECRET` | *(boş)* | `?key=` gizli kelimesi — **mutlaka belirle** |

Olay tipi: kritik uyarılar `site_hatasi`, test bildirimi `ozel` olarak gider.
Panelde **Uyarı Kuralları → Site Hatası** açık olmalı.

## 3) Butonla load bakma (telefondan tek dokunuş)

1. Sunucuda güvenlik grubunda `9273/tcp` portunu aç:
   ```sh
   ufw allow 9273/tcp            # veya: firewall-cmd --add-port=9273/tcp --permanent
   ```
2. Config'teki `WEBHOOK_SECRET` değerini not et (`install.sh` otomatik üretir).
3. MobileSignal **Panel → Eylem Butonları → Yeni**:
   - Başlık: `Sunucu Load`
   - Site: ilgili API anahtarı (veya Genel)
   - Tip: **webhook**, Metod: `GET`
   - URL: `http://SUNUCU_IP:9273/load?key=GIZLI_KELIMEN`
4. Telefonda **Ekran** sekmesinde butona bas → sunucu anlık özeti döner
   (`CPU%.. RAM%.. Load..` + işlem/URL detayı), sonuç bildirim olarak da düşer.

## 4) Ne raporlanır?

- `CPU %`, `RAM % (kullanılan/toplam MB)`, `Load 1/5/15 dk`, `Disk % (her mount)`
- En çok yiyen işlemler (`ps` üzerinden: `apache2/httpd/lshttpd/lsphp/php-fpm/...`)
- Cmdline'dan yakalanan ağır dosyalar (`.../wp-admin/admin-ajax.php` gibi `.php` yolları)
- Access-log'dan en çok vurulan URL'ler (Apache + LiteSpeed + nginx bilinen yolları taranır)

## 5) Günlük işlemler

```sh
systemctl status ms-monitor        # durum (systemd)
journalctl -u ms-monitor -f        # canlı log (ek olarak /var/log/mobilesignal-monitor.log)
python3 /usr/local/bin/ms-monitor --status   # anlık özet
python3 /usr/local/bin/ms-monitor --once     # tek tur kontrol
sudo sh uninstall.sh               # kaldır (config korunur)
```

## Dosyalar

| Dosya | Sunucudaki yeri |
|---|---|
| `ms-monitor.py` | `/usr/local/bin/ms-monitor` |
| `ms-monitor.conf.example` | `/etc/mobilesignal/monitor.conf` |
| `install.sh` / `uninstall.sh` | kurulumda bir kez |
| durum (throttle) | `/var/lib/mobilesignal/state.json` |
| log | `/var/log/mobilesignal-monitor.log` |
