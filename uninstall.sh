#!/bin/sh
# MobileSignal Sunucu Monitörü — kaldırma
# Kullanım: sudo sh uninstall.sh            (config/log korunur)
#          sudo sh uninstall.sh --purge     (her şeyi siler)
set -eu
if [ "$(id -u)" -ne 0 ]; then echo "HATA: sudo ile çalıştır." >&2; exit 1; fi

if command -v pkill >/dev/null 2>&1; then
  pkill -f "ms-monitor" 2>/dev/null || true
else
  for p in $(ps -eo pid,args 2>/dev/null | grep "[m]s-monitor" | awk '{print $1}'); do
    kill "$p" 2>/dev/null || true
  done
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now ms-monitor 2>/dev/null || true
  rm -f /etc/systemd/system/ms-monitor.service
  systemctl daemon-reload 2>/dev/null || true
fi
if [ -f /etc/init.d/ms-monitor ]; then
  /etc/init.d/ms-monitor stop 2>/dev/null || true
  if command -v update-rc.d >/dev/null 2>&1; then update-rc.d -f ms-monitor remove; fi
  if command -v chkconfig >/dev/null 2>&1; then chkconfig --del ms-monitor 2>/dev/null || true; fi
  rm -f /etc/init.d/ms-monitor
fi
if command -v rc-update >/dev/null 2>&1; then
  rc-service ms-monitor stop 2>/dev/null || true
  rc-update del ms-monitor default 2>/dev/null || true
  rm -f /etc/init.d/ms-monitor
fi
if command -v crontab >/dev/null 2>&1; then
  (crontab -l 2>/dev/null | grep -v ms-monitor || true) | crontab - 2>/dev/null || true
fi

rm -f /usr/local/bin/ms-monitor

if [ "${1:-}" = "--purge" ]; then
  rm -rf /etc/mobilesignal /var/lib/mobilesignal /var/log/mobilesignal-monitor.log
  echo "Tamamen silindi (config + log + durum dahil)."
else
  echo "Servis kaldırıldı. Config korundu: /etc/mobilesignal/monitor.conf"
  echo "(Her şeyi silmek için: sudo sh uninstall.sh --purge)"
fi
