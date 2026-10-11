#!/bin/sh
# MobileSignal Sunucu Monitörü — kolay kurulum
# Tüm dağıtımlar: Debian/Ubuntu, RHEL/CentOS/Alma/Rocky, Arch, openSUSE, Alpine
# Kullanım:  sudo sh install.sh   (aynı klasörde ms-monitor.py olmalı)
#            sudo API_URL=https://mobilesignal.tr API_KEY=xxx sh install.sh
set -eu

BIN="/usr/local/bin/ms-monitor"
CONF_DIR="/etc/mobilesignal"
CONF="$CONF_DIR/monitor.conf"
STATE_DIR="/var/lib/mobilesignal"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

say() { printf '%s\n' "$*"; }
err() { printf 'HATA: %s\n' "$*" >&2; }

# --- root kontrolü
if [ "$(id -u)" -ne 0 ]; then
  err "root (sudo) ile çalıştır:  sudo sh install.sh"
  exit 1
fi

# --- python3 bul
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
done
if [ -z "$PY" ]; then
  err "python3 bulunamadı. Önce kur: apt install python3 / yum install python3 / apk add python3"
  exit 1
fi
say "Python: $PY ($("$PY" --version 2>&1))"

# --- dosyaları yerleştir
if [ ! -f "$SRC_DIR/ms-monitor.py" ]; then
  err "ms-monitor.py aynı klasörde bulunamadı."
  exit 1
fi
mkdir -p "$CONF_DIR" "$STATE_DIR"
cp "$SRC_DIR/ms-monitor.py" "$BIN"
chmod 755 "$BIN"
chmod 755 "$STATE_DIR"

if [ ! -f "$CONF" ]; then
  cp "$SRC_DIR/ms-monitor.conf.example" "$CONF"
  chmod 600 "$CONF"
  say "Örnek config yazıldı: $CONF"
else
  say "Mevcut config korunuyor: $CONF"
fi

# --- env ile verilen API bilgisini config'e işle
set_val() { # key value
  if grep -q "^$1=" "$CONF" 2>/dev/null; then
    sed -i "s|^$1=.*|$1=$2|" "$CONF"
  else
    printf '%s=%s\n' "$1" "$2" >> "$CONF"
  fi
}
[ -n "${API_URL:-}" ] && set_val API_URL "$API_URL"
[ -n "${API_KEY:-}" ] && set_val API_KEY "$API_KEY"
[ -n "${SITE_AD:-}" ] && set_val SITE_AD "$SITE_AD"
[ -n "${WEBHOOK_SECRET:-}" ] && set_val WEBHOOK_SECRET "$WEBHOOK_SECRET"

# --- interaktif sor (yoksa)
need() { # key label
  v="$(grep -E "^$1=" "$CONF" | cut -d= -f2- || true)"
  case "$v" in ""|BURAYA*|*ÖRNEK*|*ornek*) : ;; *) return 0 ;; esac
  printf '%s: ' "$2"
  read -r ans || ans=""
  [ -n "$ans" ] && set_val "$1" "$ans"
}
need API_URL "MobileSignal adresi [https://mobilesignal.tr]"
need API_KEY "Panelden aldığın API anahtarı"
if grep -q "^WEBHOOK_SECRET=BURAYA" "$CONF" 2>/dev/null; then
  RND="$(tr -dc 'a-zA-Z0-9' < /dev/urandom 2>/dev/null | head -c 24 || echo "degistir-bunu-123")"
  set_val WEBHOOK_SECRET "$RND"
  say "WEBHOOK_SECRET üretildi (config içinde görebilirsin)."
fi

# --- servis kur: systemd > openrc > cron+nohup
started=""
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  cat > /etc/systemd/system/ms-monitor.service <<EOF
[Unit]
Description=MobileSignal Sunucu Monitoru
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$PY $BIN
Restart=always
RestartSec=10
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now ms-monitor
  systemctl --no-pager --full status ms-monitor || true
  started="systemd"
elif command -v rc-update >/dev/null 2>&1; then
  cat > /etc/init.d/ms-monitor <<EOF
#!/sbin/openrc-run
name="ms-monitor"
command="$PY"
command_args="$BIN"
command_background="yes"
pidfile="/run/ms-monitor.pid"
depend() { need net; }
EOF
  chmod +x /etc/init.d/ms-monitor
  rc-update add ms-monitor default
  rc-service ms-monitor restart
  started="openrc"
elif [ -d /etc/init.d ]; then
  cat > /etc/init.d/ms-monitor <<EOF
#!/bin/sh
### BEGIN INIT INFO
# Provides:          ms-monitor
# Required-Start:    \$network
# Default-Start:     2 3 4 5
# Short-Description: MobileSignal Sunucu Monitoru
### END INIT INFO
case "\$1" in
  start) nohup $PY $BIN >/var/log/mobilesignal-monitor.log 2>&1 & echo \$! > /var/run/ms-monitor.pid ;;
  stop) kill "\$(cat /var/run/ms-monitor.pid 2>/dev/null)" 2>/dev/null || true ;;
  restart) \$0 stop; sleep 2; \$0 start ;;
  *) echo "kullanim: \$0 {start|stop|restart}"; exit 1 ;;
esac
exit 0
EOF
  chmod +x /etc/init.d/ms-monitor
  if command -v update-rc.d >/dev/null 2>&1; then update-rc.d ms-monitor defaults; fi
  if command -v chkconfig >/dev/null 2>&1; then chkconfig --add ms-monitor; chkconfig ms-monitor on; fi
  /etc/init.d/ms-monitor restart || /etc/init.d/ms-monitor start
  started="sysv"
else
  # son çare: cron @reboot + hemen nohup
  pkill -f "ms-monitor.py" 2>/dev/null || true
  nohup "$PY" "$BIN" >/var/log/mobilesignal-monitor.log 2>&1 &
  (crontab -l 2>/dev/null | grep -v ms-monitor; echo "@reboot $PY $BIN") | crontab -
  started="cron+nohup (pid $!)"
fi

say ""
say "Kurulum tamam ($started)."
say "Config : $CONF"
say "Log    : /var/log/mobilesignal-monitor.log"
say ""
say "Test et:  $PY $BIN --test"
"$PY" "$BIN" --test || {
  err "Test bildirimi GÖNDERİLEMEDİ — API_URL/API_KEY'yi kontrol et: $CONF"
  exit 2
}
say ""
PORT="$(grep -E '^WEBHOOK_PORT=' "$CONF" | cut -d= -f2)"
SECRET="$(grep -E '^WEBHOOK_SECRET=' "$CONF" | cut -d= -f2)"
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
say "Buton için (Panel → Eylem Butonları → Yeni, tip=webhook):"
say "  http://${IP:-SUNUCU_IP}:${PORT:-9273}/load?key=${SECRET:-GIZLI}"
say "(Güvenlik grubunda ${PORT:-9273}/tcp portunu açmayı unutma.)"
