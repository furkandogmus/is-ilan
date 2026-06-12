#!/usr/bin/env python3
"""
LinkedIn İş İlanı Arama Aracı
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

LinkedIn'in giriş gerektirmeyen guest (misafir) API'sini kullanarak
iş ilanlarını terminalden arar, filtreler ve macOS bildirimi gönderir.

Kullanım örnekleri:
    python3 is_ilan.py python --hours 48
    python3 is_ilan.py "data engineer" --remote
    python3 is_ilan.py devops --location "Istanbul"
    python3 is_ilan.py react --title-filter "senior|lead"
    python3 is_ilan.py java --json | jq '.'
    python3 is_ilan.py --reset
"""

import argparse
import html
import json
import os
import random
import re
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

# ── Sabitler ────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, ".is_jobs_seen.json")
API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"
    " (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0)"
    " Gecko/20100101 Firefox/121.0",
]

MAX_RETRIES = 3
RETRY_DELAY = 3

# ── Terminal renkleri (TrueColor / ANSI) ───────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[38;2;111;154;114m"
BLUE = "\033[38;2;90;138;158m"
CYAN = "\033[38;2;152;196;218m"
YELLOW = "\033[38;2;201;148;48m"
MAGENTA = "\033[38;2;200;170;150m"
RED = "\033[38;2;201;106;106m"
CORAL = RED
PURPLE = BLUE
RESET = "\033[0m"
SPINNER = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]


def color_supported():
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def c(code, text):
    """Render *text* with ANSI *code* only if stdout is a TTY."""
    if not color_supported():
        return text
    return f"{code}{text}{RESET}"


# ── LinkedIn API ────────────────────────────────────────────────────────────

def is_blocked(html_text):
    blocks = [
        "challenge-platform", "captcha", "please verify you're not a robot",
        "too many requests", "limit exceeded", "blocked",
    ]
    return any(b in html_text.lower() for b in blocks)


def fetch(keywords, location, hours, remote, start=0):
    """LinkedIn guest job-search API'sine istek atar, HTML döndürür."""
    params = {"keywords": keywords, "start": str(start)}
    if hours:
        params["f_TPR"] = f"r{hours * 3600}"
    if remote:
        params["f_WT"] = "2"
    elif location:
        params["location"] = location
    url = f"{API}?{urllib.parse.urlencode(params)}"

    for attempt in range(MAX_RETRIES):
        ua = random.choice(USER_AGENTS)
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8", "replace")
            if is_blocked(body):
                raise RuntimeError("LinkedIn isteği engelledi (rate limit / captcha)")
            return body
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (2 ** attempt)
                time.sleep(wait)
                continue
            raise


def parse_listing_page(html_text):
    """Bir HTML sayfasındaki tüm ilan kartlarını parse eder."""
    jobs = []
    for block in re.split(r'data-entity-urn="urn:li:jobPosting:', html_text)[1:]:
        m_id = re.match(r"(\d+)", block)
        job_id = m_id.group(1) if m_id else None

        def grab(pattern):
            m = re.search(pattern, block, re.DOTALL)
            return html.unescape(m.group(1).strip()) if m else ""

        title = grab(r'base-search-card__title">\s*(.*?)\s*</h3>')
        title = re.sub(r"\s+", " ", title)

        # Şirket: önce subtitle bölümünü ayır, içinde <a> ara
        sub = re.search(r'base-search-card__subtitle">\s*(.*?)\s*</h4>', block, re.DOTALL)
        if sub:
            sub_block = sub.group(1)
            a_m = re.search(r'<a[^>]*>\s*(.*?)\s*</a>', sub_block, re.DOTALL)
            if a_m:
                company = html.unescape(a_m.group(1).strip())
            else:
                company = re.sub(r'<[^>]+>', '', sub_block).strip()
            company = re.sub(r"\s+", " ", company)
        else:
            company = ""

        location = grab(r'job-search-card__location">\s*(.*?)\s*</span>')
        location = re.sub(r"\s+", " ", location)
        listed = grab(r'<time[^>]*datetime="([^"]+)"')
        url = grab(r'href="(https://[^"]*?/jobs/view/[^"]*?)"')
        url = url.split("?")[0] if url else ""

        # 2. parse yöntemi: bazen time etiketi farklı olabiliyor
        if not listed:
            listed = grab(r'job-search-card__listdate[^>]*datetime="([^"]+)"')

        if job_id and title:
            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "listed": listed,
                "url": url,
            })
    return jobs


LOADING_MSGS = [
    "Rüzgârın sesi dinleniyor", "Tozpembe hayaller aranıyor",
    "Küçük bir tebessüm", "Sessizce taranıyor",
    "Gökyüzüne bakılıyor",
]


def spinner(step, msg=""):
    s = SPINNER[step % len(SPINNER)]
    sys.stderr.write(f"\r  {c(DIM, s)}  {msg}")
    sys.stderr.flush()


def fetch_all_pages(keywords, location, hours, remote, max_pages=5, delay=2):
    all_jobs = []
    msg = random.choice(LOADING_MSGS) if max_pages > 1 else ""
    step = 0
    for page in range(max_pages):
        if max_pages > 1:
            page_msg = f"{msg}  {c(DIM, f'Sayfa {page + 1}/{max_pages}')}"
            spinner(step, page_msg)
            step += 1
        try:
            html_text = fetch(keywords, location, hours, remote, start=page * 25)
        except Exception:
            if max_pages > 1:
                sys.stderr.write("\r\033[K")
                sys.stderr.flush()
            break
        page_jobs = parse_listing_page(html_text)
        if not page_jobs:
            if max_pages > 1:
                sys.stderr.write("\r\033[K")
                sys.stderr.flush()
            break
        all_jobs.extend(page_jobs)
        if page < max_pages - 1:
            time.sleep(delay)
    if max_pages > 1:
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()
    return all_jobs


def fetch_applicant_count(job_id):
    """İlan detay sayfasından başvuru sayısını çeker. Bulamazsa None döner."""
    url = f"https://www.linkedin.com/jobs/view/{job_id}"
    for attempt in range(MAX_RETRIES):
        ua = random.choice(USER_AGENTS)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html_text = resp.read().decode("utf-8", "replace")
            if is_blocked(html_text):
                return None
            m = re.search(r"(\d+)\s*applicants?", html_text, re.IGNORECASE)
            if m:
                return int(m.group(1))
            if "Be the first" in html_text or "İlk başvuran" in html_text:
                return 0
            return None
        except Exception:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (2 ** attempt))
                continue
            return None


# ── Durum (seen) yönetimi ──────────────────────────────────────────────────

def load_seen():
    """(seen_ids, seen_pairs) döndürür. seen_pairs set[(title, company), ...]"""
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data), set()
        if isinstance(data, dict):
            ids = set(data.get("ids", []))
            pairs = {tuple(p) for p in data.get("pairs", [])}
            return ids, pairs
        return set(), set()
    except (FileNotFoundError, json.JSONDecodeError):
        return set(), set()


def save_seen(ids, pairs=None):
    payload = {
        "ids": sorted(ids),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    if pairs is not None:
        payload["pairs"] = [list(p) for p in pairs]
    with open(STATE_FILE, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ── Bildirim (cross‑platform) ───────────────────────────────────────────────

def _notify_macos(title, body):
    script = (
        f'display notification "{body.replace(chr(34), chr(39))}" '
        f'with title "{title.replace(chr(34), chr(39))}" '
        f'sound name "Glass"'
    )
    subprocess.run(["osascript", "-e", script], check=False, timeout=5)


def _notify_linux(title, body):
    subprocess.run(
        ["notify-send", title, body, "--app-name=is-ilan", "-u", "normal"],
        check=False, timeout=5,
    )


def _notify_windows(title, body):
    # PowerShell Toast notification (Windows 10+)
    ps = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $template.GetElementsByTagName('text')
    $texts.Item(0).AppendChild($template.CreateTextNode('{title}')) > $null
    $texts.Item(1).AppendChild($template.CreateTextNode('{body}')) > $null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('is-ilan').Show($toast)
    """
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        check=False, timeout=10, capture_output=True,
    )


def notify(title, body):
    try:
        if sys.platform == "darwin":
            _notify_macos(title, body)
        elif sys.platform == "linux":
            _notify_linux(title, body)
        elif sys.platform == "win32":
            _notify_windows(title, body)
    except Exception:
        pass


# ── Zamanlanmış görev (cross‑platform) ─────────────────────────────────────

SCHEDULER_NAME = "is-ilan-check"


def _scheduler_install_macos(keywords, hours, interval_hours):
    plist_path = os.path.join(
        os.path.expanduser("~"), "Library", "LaunchAgents",
        f"com.{SCHEDULER_NAME}.plist",
    )
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{SCHEDULER_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>{os.path.join(SCRIPT_DIR, 'is_ilan.py')}</string>
        <string>{keywords}</string>
        <string>--hours</string>
        <string>{hours}</string>
        <string>--pages</string>
        <string>1</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_hours * 3600}</integer>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>"""
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    with open(plist_path, "w") as f:
        f.write(plist)
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.{SCHEDULER_NAME}"],
                   check=False, capture_output=True)
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", plist_path],
        check=False, capture_output=True, text=True,
    )
    return result.returncode == 0, result.stderr.strip()


def _scheduler_uninstall_macos():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/com.{SCHEDULER_NAME}"],
                   check=False, capture_output=True)
    plist_path = os.path.join(
        os.path.expanduser("~"), "Library", "LaunchAgents",
        f"com.{SCHEDULER_NAME}.plist",
    )
    try:
        os.remove(plist_path)
        return True
    except FileNotFoundError:
        return False


def _scheduler_install_linux(keywords, hours, interval_hours):
    # systemd user timer
    unit_dir = os.path.join(os.path.expanduser("~"), ".config", "systemd", "user")
    os.makedirs(unit_dir, exist_ok=True)

    script_path = os.path.join(SCRIPT_DIR, "is_ilan.py")
    service = f"""[Unit]
Description=is-ilan job check

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {script_path} {keywords} --hours {hours} --pages 1
"""
    timer = f"""[Unit]
Description=is-ilan periodic check

[Timer]
OnUnitActiveSec={interval_hours}h

[Install]
WantedBy=timers.target
"""

    svc_path = os.path.join(unit_dir, f"{SCHEDULER_NAME}.service")
    tim_path = os.path.join(unit_dir, f"{SCHEDULER_NAME}.timer")

    with open(svc_path, "w") as f:
        f.write(service)
    with open(tim_path, "w") as f:
        f.write(timer)

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{SCHEDULER_NAME}.timer"],
                   check=False, capture_output=True)
    return True, ""


def _scheduler_uninstall_linux():
    subprocess.run(["systemctl", "--user", "disable", "--now", f"{SCHEDULER_NAME}.timer"],
                   check=False, capture_output=True)
    unit_dir = os.path.join(os.path.expanduser("~"), ".config", "systemd", "user")
    for fname in [f"{SCHEDULER_NAME}.service", f"{SCHEDULER_NAME}.timer"]:
        try:
            os.remove(os.path.join(unit_dir, fname))
        except FileNotFoundError:
            pass
    return True


def _scheduler_install_windows(keywords, hours, interval_hours):
    script_path = os.path.join(SCRIPT_DIR, "is_ilan.py")
    cmd = (
        f'schtasks /create /tn "{SCHEDULER_NAME}" /tr '
        f'"python {script_path} {keywords} --hours {hours} --pages 1" '
        f'/sc hourly /mo {interval_hours} /f'
    )
    result = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
    return result.returncode == 0, result.stderr.strip()


def _scheduler_uninstall_windows():
    result = subprocess.run(
        f'schtasks /delete /tn "{SCHEDULER_NAME}" /f',
        shell=True, check=False, capture_output=True,
    )
    return result.returncode == 0


def scheduler_install(keywords, hours, interval_hours):
    if sys.platform == "darwin":
        ok, err = _scheduler_install_macos(keywords, hours, interval_hours)
        method = "LaunchAgent"
    elif sys.platform == "linux":
        ok, err = _scheduler_install_linux(keywords, hours, interval_hours)
        method = "systemd timer"
    elif sys.platform == "win32":
        ok, err = _scheduler_install_windows(keywords, hours, interval_hours)
        method = "Task Scheduler"
    else:
        print(c(RED, "✗") + " Bu platform desteklenmiyor.")
        return

    if ok:
        msg = f" Zamanlanmış görev kuruldu ({method}): her {interval_hours} saatte bir '{keywords}' aranacak."
        print(c(GREEN, "✓") + msg)
        if sys.platform != "win32":
            print(f"  Günlük: /tmp/{SCHEDULER_NAME}.log")
            print("  Kaldırmak için: python3 is_ilan.py --uninstall-scheduler")
    else:
        print(c(RED, "✗") + f" Kurulum başarısız: {err}")


def scheduler_uninstall():
    if sys.platform == "darwin":
        ok = _scheduler_uninstall_macos()
    elif sys.platform == "linux":
        ok = _scheduler_uninstall_linux()
    elif sys.platform == "win32":
        ok = _scheduler_uninstall_windows()
    else:
        print(c(RED, "✗") + " Bu platform desteklenmiyor.")
        return

    if ok:
        print(c(GREEN, "✓") + " Zamanlanmış görev kaldırıldı.")
    else:
        print(c(DIM, "  Zamanlanmış görev zaten kurulu değil."))


def scheduler_status():
    if sys.platform == "darwin":
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/com.{SCHEDULER_NAME}"],
            check=False, capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(c(GREEN, "✓") + " Zamanlanmış görev aktif (LaunchAgent).")
            for line in result.stdout.splitlines():
                line = line.strip()
                if "interval" in line.lower():
                    print(f"  {line}")
        else:
            print(c(DIM, "  Zamanlanmış görev kurulu değil."))
            print("  Kurmak için: python3 is_ilan.py --install-scheduler")
    elif sys.platform == "linux":
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", f"{SCHEDULER_NAME}.timer"],
            check=False, capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(c(GREEN, "✓") + " Zamanlanmış görev aktif (systemd timer).")
        else:
            print(c(DIM, "  Zamanlanmış görev kurulu değil."))
            print("  Kurmak için: python3 is_ilan.py --install-scheduler")
    elif sys.platform == "win32":
        result = subprocess.run(
            f'schtasks /query /tn "{SCHEDULER_NAME}"',
            shell=True, check=False, capture_output=True,
        )
        if result.returncode == 0:
            print(c(GREEN, "✓") + " Zamanlanmış görev aktif (Task Scheduler).")
        else:
            print(c(DIM, "  Zamanlanmış görev kurulu değil."))
            print("  Kurmak için: python3 is_ilan.py --install-scheduler")
    else:
        print(c(RED, "✗") + " Bu platform desteklenmiyor.")


# ── Biçimlendirme / Çıktı ──────────────────────────────────────────────────

def relative_time(iso_str):
    """ISO tarih string'ini '2 saat önce' gibi okunaklı hâle getirir."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except ValueError:
        return iso_str
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    minutes = int(diff.total_seconds() / 60)
    if minutes < 1:
        return "az önce"
    if minutes < 60:
        return f"{minutes} dk önce"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} saat önce"
    days = hours // 24
    if days < 7:
        return f"{days} gün önce"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks} hafta önce"
    return dt.strftime("%d.%m.%Y")


def print_jobs(jobs, new_ids):
    if not jobs:
        print(c(DIM, "  (ilan bulunamadı)\n"))
        return

    for j in jobs:
        is_new = j["id"] in new_ids
        flag = c(BLUE, "✦ ") if is_new else c(DIM, "· ")
        title = j["title"]
        company = j["company"]
        loc = j["location"]
        when = relative_time(j["listed"])
        url = j["url"]

        parts = [f"  {flag}{c(BOLD, title)}"]
        meta = []
        if company:
            meta.append(c(BLUE, company))
        if loc:
            meta.append(c(DIM, loc))
        if when:
            meta.append(c(YELLOW, when))
        if meta:
            parts[0] += "  " + c(DIM, "·").join([""] + meta)
        print(parts[0])
        if url:
            print(f"    {c(DIM, url)}")
        print()


def print_summary(total, new_count, keywords, scope, hours, elapsed=None):
    kw = keywords if keywords != "devops" else c(BLUE, keywords)
    elapsed_str = f"  {c(DIM, '⚡')} {elapsed:.1f}sn" if elapsed is not None else ""
    print()
    print(f"  {c(BOLD, '╭─ is-ilan ───────────────────────────────╮')}")
    print(f"  {c(BOLD, '│')}   {c(DIM, '🔍')}  {c(BOLD, kw)}  {c(DIM, '·')}  {scope}  {c(DIM, '·')}  son {hours}s")
    print(f"  {c(BOLD, '│')}  {c(DIM, '─' * 38)}")
    print(f"  {c(BOLD, '│')}   {c(DIM, '📦')}  Toplam {c(BOLD, str(total))}  {c(DIM, '·')}  {c(BLUE, f'{new_count} yeni')}{elapsed_str}")
    print(f"  {c(BOLD, '╰─────────────────────────────────────────╯')}")
    print()


# ── Ana mantık ─────────────────────────────────────────────────────────────

def build_arg_parser():
    ap = argparse.ArgumentParser(
        description="LinkedIn iş ilanı arama aracı (login gerektirmez)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Örnekler:
          %(prog)s python --hours 48
          %(prog)s "data engineer" --remote
          %(prog)s devops --location Istanbul
          %(prog)s react --title-filter "senior|lead|staff"
          %(prog)s java --json
          %(prog)s --reset
        """),
    )

    ap.add_argument(
        "--version", "-V",
        action="version",
        version="is-ilan v2.0",
    )
    ap.add_argument(
        "--coffee",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    # ── Filtreler ──
    flt = ap.add_argument_group("Filtreler")
    flt.add_argument(
        "keywords",
        nargs="?",
        default="devops",
        help='Aranacak anahtar kelime(ler) (örn: "data engineer", python)',
    )
    flt.add_argument(
        "--hours", "-t",
        type=int,
        default=24,
        help="Son kaç saat (varsayılan: 24)",
    )
    flt.add_argument(
        "--location", "-l",
        default="Turkey",
        help="Konum / şehir / ülke (varsayılan: Turkey)",
    )
    flt.add_argument(
        "--remote", "-r",
        action="store_true",
        help="Sadece remote ilanlar",
    )
    flt.add_argument(
        "--title-filter", "-f",
        help="Başlıkta regex filtre (örn: 'senior|lead')",
    )
    flt.add_argument(
        "--no-title-filter",
        action="store_true",
        help="Otomatik başlık filtresini kapat",
    )
    flt.add_argument(
        "--pages", "-p",
        type=int,
        default=1,
        help="Sayfa sayısı (×25 ilan, varsayılan: 1)",
    )
    flt.add_argument(
        "--no-reposts",
        action="store_true",
        help="Repost ilanları gizle",
    )
    flt.add_argument(
        "--max-applicants", "-a",
        type=int,
        default=0,
        help="Maksimum başvuru sayısı (0=sınırsız)",
    )
    flt.add_argument(
        "--all",
        action="store_true",
        help="Görüldü kaydını yoksay (tümünü göster)",
    )

    # ── Çıktı ──
    out = ap.add_argument_group("Çıktı")
    out.add_argument(
        "--json", "-j",
        action="store_true",
        help="JSON formatında çıktı",
    )
    out.add_argument(
        "--url-only",
        action="store_true",
        help="Sadece URL listesi",
    )
    out.add_argument(
        "--stats",
        action="store_true",
        help="Sadece özet göster",
    )
    out.add_argument(
        "--no-notify", "-n",
        action="store_true",
        help="Bildirim gönderme",
    )

    # ── Zamanlanmış görev ──
    sch = ap.add_argument_group("Zamanlanmış Görev")
    sch.add_argument(
        "--install-scheduler",
        metavar="HOURS",
        nargs="?",
        const=6,
        type=int,
        help="Kur: her N saatte bir kontrol (varsayılan: 6)",
    )
    sch.add_argument(
        "--uninstall-scheduler",
        action="store_true",
        help="Zamanlanmış görevi kaldır",
    )
    sch.add_argument(
        "--scheduler-status",
        action="store_true",
        help="Zamanlanmış görev durumu",
    )

    # ── Diğer ──
    misc = ap.add_argument_group("Diğer")
    misc.add_argument(
        "--reset",
        action="store_true",
        help="Görülen ilan kaydını sıfırla",
    )
    return ap


def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    # ── Coffee easter egg ☕ ──
    if args.coffee:
        print(f"""  {c(BLUE, '╭─ ☕  Küçük bir mola ───────────────────╮')}
  {c(BLUE, '│')}                                      {c(BLUE, '│')}
  {c(BLUE, '│')}    Rüzgâr durunca                    {c(BLUE, '│')}
  {c(BLUE, '│')}    bir kahve iyi gider ☕             {c(BLUE, '│')}
  {c(BLUE, '│')}                                      {c(BLUE, '│')}
  {c(BLUE, '╰──────────────────────────────────────────╯')}""")
        return

    # ── Reset ──
    if args.reset:
        save_seen(set(), set())
        print(c(GREEN, "✓") + " Görülen ilan kaydı sıfırlandı.")
        return

    # ── Zamanlanmış görev ──
    if args.uninstall_scheduler:
        scheduler_uninstall()
        return

    if args.scheduler_status:
        scheduler_status()
        return

    if args.install_scheduler is not None:
        scheduler_install(args.keywords, args.hours, args.install_scheduler)
        return

    # ── Sonuçları çek (timer başlat) ──
    t0 = time.time()
    try:
        jobs = fetch_all_pages(
            keywords=args.keywords,
            location=args.location,
            hours=args.hours,
            remote=args.remote,
            max_pages=args.pages,
            delay=2,
        )
    except Exception as e:
        print(f"\n{c(RED, '✗')} Hata: ilanlar alınamadı ({e})", file=sys.stderr)
        sys.exit(1)
    elapsed = time.time() - t0

    # ── Başlık filtresi (regex) ──
    if args.title_filter:
        try:
            pattern = re.compile(args.title_filter, re.IGNORECASE)
        except re.error as e:
            print(f"{c(RED, '✗')} Geçersiz regex: {e}", file=sys.stderr)
            sys.exit(1)
        jobs = [j for j in jobs if pattern.search(j["title"])]
    elif not args.no_title_filter:
        # Otomatik filtre: anahtar kelimedeki her sözcük title'da aranır
        words = [re.escape(w) for w in args.keywords.split() if w]
        if words:
            auto_re = "|".join(words)
            pattern = re.compile(auto_re, re.IGNORECASE)
            jobs = [j for j in jobs if pattern.search(j["title"])]

    # ── Görülen / yeni ayırımı ──
    seen_ids, seen_pairs = load_seen()

    # ── Repost (aynı başlık+şirket) filtresi ──
    if args.no_reposts:
        jobs = [j for j in jobs if (j["title"], j["company"]) not in seen_pairs]

    # ── Maksimum başvuru filtresi ──
    if args.max_applicants > 0:
        # Her ilan için detay sayfasından başvuru sayısını paralel çek
        job_ids = [j["id"] for j in jobs]
        counts = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(fetch_applicant_count, jid): jid for jid in job_ids}
            for future in as_completed(futures):
                jid = futures[future]
                try:
                    counts[jid] = future.result()
                except Exception:
                    counts[jid] = None
        jobs = [j for j in jobs
                if counts.get(j["id"]) is None or counts[j["id"]] <= args.max_applicants]

    if args.all:
        new_ids = {j["id"] for j in jobs}
    else:
        new_ids = {j["id"] for j in jobs if j["id"] not in seen_ids}

    # ── Konum etiketi ──
    scope = "🏠 Remote" if args.remote else args.location

    # ── Kaydedilecek pair'leri güncelle ──
    new_pairs = seen_pairs | {(j["title"], j["company"]) for j in jobs}

    # ── JSON çıktısı ──
    if args.json:
        output = {
            "query": {
                "keywords": args.keywords,
                "location": args.location,
                "hours": args.hours,
                "remote": args.remote,
            },
            "total": len(jobs),
            "new": len(new_ids),
            "elapsed": round(elapsed, 2),
            "jobs": jobs,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        save_seen(seen_ids | {j["id"] for j in jobs}, new_pairs)
        return

    # ── Sadece URL ──
    if args.url_only:
        for j in jobs:
            if j["url"]:
                print(j["url"])
        save_seen(seen_ids | {j["id"] for j in jobs}, new_pairs)
        return

    # ── Sadece istatistik ──
    if args.stats:
        print_summary(len(jobs), len(new_ids), args.keywords, scope, args.hours, elapsed)
        save_seen(seen_ids | {j["id"] for j in jobs}, new_pairs)
        return

    # ── Normal çıktı ──
    print_summary(len(jobs), len(new_ids), args.keywords, scope, args.hours, elapsed)
    print_jobs(jobs, new_ids)

    # ── Bildirim ──
    if new_ids and not args.no_notify:
        new_list = [j for j in jobs if j["id"] in new_ids]
        head = new_list[0]
        extra = f" +{len(new_list) - 1} ilan" if len(new_list) > 1 else ""
        notify(
            f"Yeni ilan: {head['title']}",
            f"{head['company']}{extra}",
        )

    # ── Görülen kaydını güncelle ──
    save_seen(seen_ids | {j["id"] for j in jobs}, new_pairs)


if __name__ == "__main__":
    main()
