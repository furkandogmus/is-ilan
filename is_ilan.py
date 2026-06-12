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
import re
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# ── Sabitler ────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, ".is_jobs_seen.json")
API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

# ── Terminal renkleri (TrueColor / ANSI) ───────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
BLUE = "\033[34m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"
RESET = "\033[0m"


def color_supported():
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def c(code, text):
    """Render *text* with ANSI *code* only if stdout is a TTY."""
    if not color_supported():
        return text
    return f"{code}{text}{RESET}"


def strip_tags(text):
    """Kaba HTML etiket temizliği."""
    return re.sub(r"<[^>]+>", "", text).strip()


# ── LinkedIn API ────────────────────────────────────────────────────────────

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
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


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

        company = grab(r'base-search-card__subtitle">.*?>\s*(.*?)\s*</a>')
        if not company:
            company = grab(r'base-search-card__subtitle">\s*(.*?)\s*</h4>')
        company = re.sub(r"\s+", " ", company)

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


def fetch_all_pages(keywords, location, hours, remote, max_pages=5, delay=2):
    """Birden çok sayfa ilan çeker (pagination)."""
    all_jobs = []
    for page in range(max_pages):
        try:
            html_text = fetch(keywords, location, hours, remote, start=page * 25)
        except Exception:
            break
        page_jobs = parse_listing_page(html_text)
        if not page_jobs:
            break
        all_jobs.extend(page_jobs)
        if page < max_pages - 1:
            time.sleep(delay)
    return all_jobs


# ── Durum (seen) yönetimi ──────────────────────────────────────────────────

def load_seen():
    try:
        with open(STATE_FILE) as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(data)
        if isinstance(data, dict):
            # Yeni format: {"ids": [...], "updated": "ISO-tarih"}
            return set(data.get("ids", []))
        return set()
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(ids):
    payload = {
        "ids": sorted(ids),
        "updated": datetime.now(timezone.utc).isoformat(),
    }
    with open(STATE_FILE, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ── macOS bildirim ─────────────────────────────────────────────────────────

def _as(s):
    """AppleScript string literal yardımcısı."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(title, body):
    script = (
        f'display notification {_as(body)} with title {_as(title)} '
        f'sound name "Glass"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


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


def print_jobs(jobs, new_ids, show_index=False):
    """İlan listesini renkli ve düzenli biçimde terminale basar."""
    if not jobs:
        print(c(DIM, "  (ilan bulunamadı)\n"))
        return

    max_title = max(len(j["title"]) for j in jobs)
    max_company = max(len(j["company"]) for j in jobs)
    width = min(max_title + max_company + 12, 100)

    for idx, j in enumerate(jobs, 1):
        is_new = j["id"] in new_ids
        prefix = f"{idx:2d}. " if show_index else ""
        flag = c(GREEN + BOLD, "★ ") if is_new else "  "

        title = j["title"]
        company = j["company"]
        loc = j["location"]
        when = relative_time(j["listed"])

        line1 = f"{flag}{c(BOLD, title)}"
        print(prefix + line1)

        meta = f"     {c(CYAN, company)}"
        if loc:
            meta += f"  {c(DIM, '·')}  {loc}"
        if when:
            meta += f"  {c(DIM, '·')}  {c(YELLOW, when)}"
        print(meta)

        if j["url"]:
            print(f"     {c(DIM, j['url'])}")
        print()


def print_summary(total, new_count, keywords, scope, hours):
    print()
    header = f"  {c(BOLD, 'İş İlanı Arama')}"
    keywords_display = keywords if keywords != "devops" else c(MAGENTA, keywords)
    print(header)
    print(f"  {'─' * 42}")
    print(f"  Anahtar kelime : {keywords_display}")
    print(f"  Konum          : {scope}")
    print(f"  Zaman aralığı  : son {hours} saat")
    print(f"  Toplam ilan    : {total}")
    print(f"  Yeni ilan      : {c(GREEN + BOLD, str(new_count))}")
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
        "keywords",
        nargs="?",
        default="devops",
        help='Aranacak anahtar kelime(ler) (örn: "data engineer", python)',
    )
    ap.add_argument(
        "--hours", "-t",
        type=int,
        default=24,
        help="Son kaç saat içindeki ilanlar (varsayılan: 24)",
    )
    ap.add_argument(
        "--location", "-l",
        default="Turkey",
        help="Konum / şehir / ülke (varsayılan: Turkey)",
    )
    ap.add_argument(
        "--remote", "-r",
        action="store_true",
        help="Sadece uzaktan (remote) çalışma ilanları",
    )
    ap.add_argument(
        "--title-filter", "-f",
        help="İlan başlığında regex filtre (örn: 'senior|lead')",
    )
    ap.add_argument(
        "--pages", "-p",
        type=int,
        default=1,
        help="Çekilecek sayfa sayısı (her sayfa ~25 ilan, varsayılan: 1)",
    )
    ap.add_argument(
        "--no-notify", "-n",
        action="store_true",
        help="Masaüstü bildirimi gönderme",
    )
    ap.add_argument(
        "--json", "-j",
        action="store_true",
        help="Çıktıyı JSON formatında ver",
    )
    ap.add_argument(
        "--url-only",
        action="store_true",
        help="Sadece ilan URL'lerini listele",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Tüm sonuçları göster (görüldü kaydını yoksay)",
    )
    ap.add_argument(
        "--reset",
        action="store_true",
        help="Görülen ilan kaydını sıfırla ve çık",
    )
    ap.add_argument(
        "--stats",
        action="store_true",
        help="Sadece özet istatistikleri göster",

    )
    return ap


def main():
    ap = build_arg_parser()
    args = ap.parse_args()

    # ── Reset ──
    if args.reset:
        save_seen(set())
        print(c(GREEN, "✓") + " Görülen ilan kaydı sıfırlandı.")
        return

    # ── Sonuçları çek ──
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
        print(f"{c(RED, '✗')} Hata: ilanlar alınamadı ({e})", file=sys.stderr)
        sys.exit(1)

    # ── Başlık filtresi (regex) ──
    if args.title_filter:
        try:
            pattern = re.compile(args.title_filter, re.IGNORECASE)
        except re.error as e:
            print(f"{c(RED, '✗')} Geçersiz regex: {e}", file=sys.stderr)
            sys.exit(1)
        jobs = [j for j in jobs if pattern.search(j["title"])]

    # ── Görülen / yeni ayırımı ──
    seen = load_seen()
    if args.all:
        new_ids = {j["id"] for j in jobs}
    else:
        new_ids = {j["id"] for j in jobs if j["id"] not in seen}

    # ── Konum etiketi ──
    scope = "🌍 Remote" if args.remote else args.location

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
            "jobs": jobs,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        save_seen(seen | {j["id"] for j in jobs})
        return

    # ── Sadece URL ──
    if args.url_only:
        for j in jobs:
            if j["url"]:
                print(j["url"])
        save_seen(seen | {j["id"] for j in jobs})
        return

    # ── Sadece istatistik ──
    if args.stats:
        print_summary(len(jobs), len(new_ids), args.keywords, scope, args.hours)
        save_seen(seen | {j["id"] for j in jobs})
        return

    # ── Normal çıktı ──
    print_summary(len(jobs), len(new_ids), args.keywords, scope, args.hours)
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
    save_seen(seen | {j["id"] for j in jobs})


if __name__ == "__main__":
    main()
