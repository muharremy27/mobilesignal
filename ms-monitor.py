#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MobileSignal Sunucu Monitörü — tek dosya, stdlib only.
- Tüm Linux dağıtımlarında çalışır (systemd şart değil).
- CPU / RAM / Disk / Load kritik değerde ms_notify ile telefona uyarı atar.
- Apache + LiteSpeed fark etmez: en çok CPU/RAM yiyen process + URL/file raporlar.
- Dahili mini HTTP sunucusu: telefondaki "Eylem Butonu" (webhook) ile anlık load sorgulanır.

Kullanım:
  ms-monitor --test        bağlantı + eşik testi (ozel olayı gönderir)
  ms-monitor --once        tek tur kontrol yap, çık
  ms-monitor --status      anlık özeti stdout'a bas, çık
  ms-monitor               sonsuz döngü (servis bunu çalıştırır)

Config: /etc/mobilesignal/monitor.conf  (KEY=değer, # yorum)
Ortama göre de override: MS_API_KEY, MS_API_URL ...
Sadece Python3 stdlib kullanır — pip paketi gerekmez.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

VERSION = "1.0.1"
CONF_PATH = os.environ.get("MS_CONF", "/etc/mobilesignal/monitor.conf")
STATE_PATH = "/var/lib/mobilesignal/state.json"
LOG_PATH = "/var/log/mobilesignal-monitor.log"

DEFAULTS = {
    "API_URL": "https://mobilesignal.tr",   # sonuna /site_ajax.php otomatik eklenir
    "API_KEY": "",                           # panelden alınan anahtar (zorunlu)
    "SITE_AD": "",                           # boşsa hostname kullanılır
    "CHECK_INTERVAL": "60",                  # saniye
    "CPU_CRIT": "85",                        # % (0=kapalı)
    "RAM_CRIT": "85",                        # % (0=kapalı)
    "DISK_CRIT": "90",                       # % (0=kapalı)
    "LOAD_CRIT": "0",                        # 5-dk load eşiği; 0=otomatik (cpu*2)
    "PROC_CPU_CRIT": "50",                   # tek process %cpu eşiği (0=kapalı)
    "PROC_RAM_CRIT": "20",                   # tek process %mem eşiği (0=kapalı)
    "TOP_N": "5",                            # raporda kaç process/url gösterilsin
    "ALERT_COOLDOWN_DK": "15",               # aynı uyarı en fazla X dk'da bir
    "WEBHOOK_PORT": "9273",                  # butonla sorgu portu (0=kapalı)
    "WEBHOOK_SECRET": "",                    # boşsa ?key kontrolü yok (önerilmez)
    "LOG_TAIL": "2000",                      # access log'dan kaç satır analiz edilsin
}

# Bilinen access-log yolları (Apache + LiteSpeed + varyantlar)
LOG_GLOBS = [
    "/var/log/apache2/access.log",
    "/var/log/apache2/other_vhosts_access.log",
    "/var/log/httpd/access_log",
    "/var/log/httpd/access.log",
    "/usr/local/apache/logs/access_log",
    "/usr/local/apache/logs/access.log",
    "/usr/local/lsws/logs/access.log",
    "/var/log/lsws/access.log",
    "/var/log/nginx/access.log",
]

WEB_KEYWORDS = ("apache2", "httpd", "lshttpd", "litespeed", "lsws",
                "lsphp", "php", "php-fpm", "nginx", "node", "python")


# ---------------------------------------------------------------- config

def load_conf(path=CONF_PATH):
    cfg = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip().upper()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    # env override
    for k in list(cfg.keys()):
        ev = os.environ.get("MS_" + k)
        if ev is not None and ev != "":
            cfg[k] = ev
    return cfg


def fnum(cfg, key, default=0.0):
    try:
        return float(str(cfg.get(key, default)).replace(",", "."))
    except (ValueError, TypeError):
        return float(default)


def inum(cfg, key, default=0):
    try:
        return int(float(str(cfg.get(key, default)).replace(",", ".")))
    except (ValueError, TypeError):
        return default


def site_ad(cfg):
    s = (cfg.get("SITE_AD") or "").strip()
    return s if s else socket.gethostname()


def log_line(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s" % (ts, msg)
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- metrikler

def cpu_count():
    try:
        n = os.cpu_count() or 1
    except Exception:
        n = 1
    return max(1, n)


def _proc_stat_cpu():
    """(total, idle) döner."""
    try:
        with open("/proc/stat", encoding="utf-8") as f:
            p = f.readline().split()
        vals = list(map(int, p[1:8]))
        total = sum(vals)
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        return total, idle
    except (OSError, ValueError, IndexError):
        return None


def cpu_percent():
    a = _proc_stat_cpu()
    if not a:
        return 0.0
    time.sleep(1)
    b = _proc_stat_cpu()
    if not b:
        return 0.0
    dt, di = b[0] - a[0], b[1] - a[1]
    if dt <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (dt - di) * 100.0 / dt)), 1)


def mem_info():
    info = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"(\w+):\s+(\d+)", line)
                if m:
                    info[m.group(1)] = int(m.group(2))  # kB
    except OSError:
        return {"pct": 0.0, "used_mb": 0, "total_mb": 0}
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(0, total - avail)
    pct = round(used * 100.0 / total, 1) if total else 0.0
    return {"pct": pct, "used_mb": used // 1024, "total_mb": total // 1024}


def disk_usages():
    out = []
    seen = set()
    for mp in ("/", "/var", "/home", "/tmp"):
        try:
            if not os.path.isdir(mp):
                continue
            st = os.stat(mp)
            key = (st.st_dev)
            if key in seen:
                continue
            seen.add(key)
            u = shutil.disk_usage(mp)
            pct = round(u.used * 100.0 / u.total, 1) if u.total else 0.0
            out.append({"mount": mp, "pct": pct,
                        "used_gb": round(u.used / 1e9, 1),
                        "total_gb": round(u.total / 1e9, 1)})
        except OSError:
            continue
    return out


def load_avg():
    try:
        l1, l5, l15 = os.getloadavg()
        return round(l1, 2), round(l5, 2), round(l15, 2)
    except (OSError, AttributeError):
        return 0.0, 0.0, 0.0


def top_processes(n=5):
    """ps ile en çok CPU yiyenler. Yoksa /proc fallback."""
    rows = []
    try:
        p = subprocess.run(
            ["ps", "-eo", "pid,pcpu,pmem,comm,args", "--sort=-pcpu"],
            capture_output=True, text=True, timeout=10)
        lines = (p.stdout or "").splitlines()[1:1 + max(n * 3, 15)]
        for ln in lines:
            m = re.match(r"\s*(\d+)\s+([\d.]+)\s+([\d.]+)\s+(\S+)\s?(.*)", ln)
            if m:
                rows.append({"pid": int(m.group(1)),
                             "cpu": float(m.group(2)),
                             "mem": float(m.group(3)),
                             "comm": m.group(4),
                             "args": (m.group(5) or m.group(4))[:220]})
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    rows.sort(key=lambda r: r["cpu"], reverse=True)
    return rows[:n]


def web_processes(n=5):
    allp = top_processes(max(n * 4, 20))
    web = [r for r in allp
           if any(k in (r["comm"] + " " + r["args"]).lower() for k in WEB_KEYWORDS)]
    return (web or allp)[:n]


def heavy_files_from_procs(procs):
    """Process cmdline içinden .php / site dosyası yakala."""
    found = []
    for r in procs:
        m = re.findall(r"/[\w\-./]+\.(?:php|py|js|html?)", r.get("args", ""))
        for f in m:
            if f not in found:
                found.append(f)
    return found[:8]


LOG_RE = re.compile(r'"[A-Z]+\s+(\S+)\s+HTTP/[^"]*"\s+(\d{3})\s+(\d+|-)')

def top_urls(tail=2000, n=5):
    """Access log'ların son satırlarından en çok vurulan URL'ler."""
    hits, bw = {}, {}
    scanned = 0
    for path in LOG_GLOBS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 200 * 1024))  # son ~200KB yeterli
                chunk = f.read().decode("utf-8", "replace").splitlines()
            for line in chunk[-tail:]:
                m = LOG_RE.search(line)
                if not m:
                    continue
                url = m.group(1).split("?")[0][:160]
                try:
                    b = int(m.group(3)) if m.group(3) != "-" else 0
                except ValueError:
                    b = 0
                hits[url] = hits.get(url, 0) + 1
                bw[url] = bw.get(url, 0) + b
                scanned += 1
                if scanned >= tail * 2:
                    break
        except OSError:
            continue
        if scanned >= tail:
            break
    ranked = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"url": u, "hits": c, "kb": round(bw.get(u, 0) / 1024)} for u, c in ranked]


def snapshot(cfg):
    n = inum(cfg, "TOP_N", 5)
    tail = inum(cfg, "LOG_TAIL", 2000)
    mem = mem_info()
    disks = disk_usages()
    l1, l5, l15 = load_avg()
    procs = web_processes(n)
    return {
        "host": site_ad(cfg),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "cpu": cpu_percent(),
        "mem_pct": mem["pct"], "mem_used_mb": mem["used_mb"], "mem_total_mb": mem["total_mb"],
        "disks": disks,
        "load1": l1, "load5": l5, "load15": l15, "nproc": cpu_count(),
        "top_proc": procs,
        "heavy_files": heavy_files_from_procs(procs),
        "top_urls": top_urls(tail, n),
    }


def short_summary(s):
    """Buton cevabı: ilk 200 karakter (telefon ekranına sığsın)."""
    dmax = max([d["pct"] for d in s["disks"]] + [0])
    t = "CPU%%%s RAM%%%s Load%s Disk%%%s" % (s["cpu"], s["mem_pct"], s["load5"], dmax)
    if s["top_proc"]:
        p = s["top_proc"][0]
        t += " | Top:%s %s%%" % (p["comm"][:18], p["cpu"])
    return t[:200]


def detail_text(s):
    L = ["[%s] %s" % (s["time"], s["host"]),
         "CPU %%%s | RAM %%%s (%s/%s MB) | Load %s/%s/%s (cpu:%s)" % (
             s["cpu"], s["mem_pct"], s["mem_used_mb"], s["mem_total_mb"],
             s["load1"], s["load5"], s["load15"], s["nproc"])]
    for d in s["disks"]:
        L.append("Disk %s: %%%s (%s/%s GB)" % (d["mount"], d["pct"], d["used_gb"], d["total_gb"]))
    if s["top_proc"]:
        L.append("Islemler:")
        for p in s["top_proc"]:
            L.append("  #%s %s cpu:%s mem:%s %s" % (p["pid"], p["comm"], p["cpu"], p["mem"], p["args"][:100]))
    if s["heavy_files"]:
        L.append("Agir dosyalar: " + ", ".join(s["heavy_files"]))
    if s["top_urls"]:
        L.append("Cok vurulan URL:")
        for u in s["top_urls"]:
            L.append("  %sx %s (%s KB)" % (u["hits"], u["url"], u["kb"]))
    return "\n".join(L)[:2000]


# ---------------------------------------------------------------- notify

def endpoint_of(api_url):
    u = (api_url or "").strip().rstrip("/")
    if not u:
        return ""
    if re.search(r"\.php$", u, re.I):
        return u
    return u + "/site_ajax.php"


def load_state():
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(st):
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except OSError:
        pass


def throttled(key, cooldown_dk):
    if cooldown_dk <= 0:
        return False
    st = load_state()
    last = float(st.get(key, 0))
    if time.time() - last < cooldown_dk * 60:
        return True
    st[key] = time.time()
    save_state(st)
    return False


def send_notify(cfg, event, title, message, url=""):
    api_key = (cfg.get("API_KEY") or "").strip()
    if not api_key:
        log_line("UYARI: API_KEY bos — bildirim atlaniyor.")
        return False
    ep = endpoint_of(cfg.get("API_URL", ""))
    if not ep:
        log_line("UYARI: API_URL bos — bildirim atlaniyor.")
        return False
    allowed = {"site_hatasi", "iletisim_formu", "urun_satisi",
               "online_satis", "stok_uyarisi", "ozel"}
    if event not in allowed:
        event = "ozel"
    data = urllib.parse.urlencode({
        "action": "ms_notify", "api_key": api_key,
        "event": event, "title": title[:240],
        "message": message[:2000], "url": url[:500],
    }).encode()
    try:
        # NOT: tarayici benzeri UA sart — Python-urllib UA'si
        # Cloudflare Bot Fight / ModSecurity / Imunify360 tarafindan 403 yer.
        req = urllib.request.Request(ep, data=data, method="POST", headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) MobileSignal-Monitor/%s" % VERSION,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded",
        })
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                body = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as he:
            try:
                ebody = he.read().decode("utf-8", "replace")
            except Exception:
                ebody = ""
            snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", ebody)).strip()[:300]
            log_line("notify HATASI: HTTP %s (uc: %s) govde: %s" % (he.code, ep, snippet or "(bos)"))
            return False
        try:
            j = json.loads(body)
            ok = str(j.get("status", "")) in ("success", "True", "1", "onay")
            log_line("notify -> %s (%s)" % (j.get("message", body[:80]), "OK" if ok else "HATA"))
            return ok
        except ValueError:
            log_line("notify -> HTTP cevabi JSON degil: " + body[:100])
            return False
    except Exception as e:
        log_line("notify HATASI: %s" % e)
        return False


def check_and_alert(cfg, snap=None):
    snap = snap or snapshot(cfg)
    host = snap["host"]
    cd = inum(cfg, "ALERT_COOLDOWN_DK", 15)
    alerts = []

    cpu_c, ram_c, disk_c = fnum(cfg, "CPU_CRIT", 85), fnum(cfg, "RAM_CRIT", 85), fnum(cfg, "DISK_CRIT", 90)
    load_c = fnum(cfg, "LOAD_CRIT", 0)
    if load_c <= 0:
        load_c = snap["nproc"] * 2.0
    pcpu_c, pram_c = fnum(cfg, "PROC_CPU_CRIT", 50), fnum(cfg, "PROC_RAM_CRIT", 20)

    if cpu_c > 0 and snap["cpu"] >= cpu_c:
        alerts.append(("cpu", "CPU kritik: %%%s (esik %%%s)" % (snap["cpu"], cpu_c)))
    if ram_c > 0 and snap["mem_pct"] >= ram_c:
        alerts.append(("ram", "RAM kritik: %%%s (esik %%%s)" % (snap["mem_pct"], ram_c)))
    for d in snap["disks"]:
        if disk_c > 0 and d["pct"] >= disk_c:
            alerts.append(("disk" + d["mount"], "Disk kritik %s: %%%s" % (d["mount"], d["pct"])))
    if load_c > 0 and snap["load5"] >= load_c:
        alerts.append(("load", "Load kritik: %s (5dk, esik %s)" % (snap["load5"], load_c)))
    for p in snap["top_proc"]:
        tag = "proc%s" % p["pid"]
        if pcpu_c > 0 and p["cpu"] >= pcpu_c:
            alerts.append((tag, "Islem CPU yiyor: %s (#%s) %s%%" % (p["comm"], p["pid"], p["cpu"])))
            break
    for p in snap["top_proc"]:
        if pram_c > 0 and p["mem"] >= pram_c:
            alerts.append(("mem%s" % p["pid"], "Islem RAM yiyor: %s (#%s) %s%%" % (p["comm"], p["pid"], p["mem"])))
            break

    for key, txt in alerts:
        if throttled("alert:" + key, cd):
            log_line("throttle: " + txt)
            continue
        title = "%s — %s" % (host, txt)
        send_notify(cfg, "site_hatasi", title, detail_text(snap))

    if alerts:
        log_line("KRITIK: %s" % "; ".join(t for _, t in alerts))
    return alerts


# ---------------------------------------------------------------- webhook (buton)

class Handler(BaseHTTPRequestHandler):
    cfg = {}

    def _auth_ok(self, qs):
        secret = (self.cfg.get("WEBHOOK_SECRET") or "").strip()
        if not secret:
            return True
        got = qs.get("key", [""])[0] + qs.get("secret", [""])[0]
        return got == secret

    def _send(self, code, obj, text=None):
        body = (text if text is not None else json.dumps(obj, ensure_ascii=False)).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _status_payload(self):
        s = snapshot(self.cfg)
        return {"status": "success", "ozet": short_summary(s),
                "ayrinti": detail_text(s), "veriler": s}

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        if u.path not in ("/", "/load", "/durum", "/status", "/info"):
            return self._send(404, {"status": "error", "message": "bilinmeyen yol"})
        if not self._auth_ok(qs):
            return self._send(403, {"status": "error", "message": "yetkisiz (key hatali)"})
        try:
            p = self._status_payload()
            # MobileSignal eylem butonu cevabı 200 + kısa metin bekler:
            return self._send(200, p, text=p["ozet"])
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"status": "error", "message": str(e)[:200]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        except Exception:
            raw = ""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        form = urllib.parse.parse_qs(raw)
        if not self._auth_ok({**qs, **{k: v for k, v in form.items()}}):
            return self._send(403, {"status": "error", "message": "yetkisiz (key hatali)"})
        try:
            p = self._status_payload()
            return self._send(200, p, text=p["ozet"])
        except Exception as e:
            return self._send(500, {"status": "error", "message": str(e)[:200]})

    def log_message(self, *a):
        pass


def serve_webhook(cfg):
    port = inum(cfg, "WEBHOOK_PORT", 9273)
    if port <= 0:
        return None
    Handler.cfg = cfg
    try:
        srv = HTTPServer(("0.0.0.0", port), Handler)
    except OSError as e:
        log_line("Webhook portu acilamadi (%s): %s" % (port, e))
        return None
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 1}, daemon=True)
    t.start()
    log_line("Webhook acik: http://0.0.0.0:%s/load  (buton tipi: webhook)" % port)
    return srv


# ---------------------------------------------------------------- main

def cmd_status(cfg):
    s = snapshot(cfg)
    print(detail_text(s))
    print("\nOZET: " + short_summary(s))


def main(argv):
    cfg = load_conf()
    if "--test" in argv:
        s = snapshot(cfg)
        print(detail_text(s))
        ok = send_notify(cfg, "ozel", "%s — baglanti testi" % site_ad(cfg),
                         "MobileSignal sunucu monitoru dogru yapilandirilmis.\n" + detail_text(s))
        print("TEST:", "OK — telefona bildirim dustu" if ok else "BASARISIZ — API_KEY/API_URL'yi kontrol et")
        return 0 if ok else 2
    if "--status" in argv or "--once" in argv:
        if "--once" in argv:
            alerts = check_and_alert(cfg)
            print("Uyari sayisi:", len(alerts))
        else:
            cmd_status(cfg)
        return 0
    if "--version" in argv or "-V" in argv:
        print("ms-monitor " + VERSION)
        return 0

    log_line("ms-monitor %s basladi (host=%s, interval=%ss)" % (VERSION, site_ad(cfg), cfg.get("CHECK_INTERVAL")))
    serve_webhook(cfg)
    interval = max(15, inum(cfg, "CHECK_INTERVAL", 60))
    while True:
        try:
            check_and_alert(cfg)
        except Exception:
            traceback.print_exc()
            log_line("dongu hatasi — 30sn sonra tekrar")
            time.sleep(30)
            continue
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
