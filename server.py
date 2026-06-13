#!/usr/bin/env python3
"""
is-ilan web sunucusu
~~~~~~~~~~~~~~~~~~~~

index.html'i sunar ve LinkedIn guest API isteklerini proxy'ler
(CORS engelini aşmak için).

Kullanım:
    python3 server.py
    python3 server.py --port 3000
"""

import argparse
import http.server
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
TYPEAHEAD = "https://www.linkedin.com/jobs-guest/api/typeaheadHits"

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

# In-memory cache
_cache = {}
CACHE_TTL = 120  # seconds
_CACHE_CLEANUP_INTERVAL = 600  # cleanup every 10 minutes
_last_cache_cleanup = 0.0


def _cache_cleanup():
    global _last_cache_cleanup
    now = time.time()
    if now - _last_cache_cleanup < _CACHE_CLEANUP_INTERVAL:
        return
    expired = [k for k, v in _cache.items() if now - v["ts"] >= CACHE_TTL]
    for k in expired:
        del _cache[k]
    _last_cache_cleanup = now


def _cached(key, ttl=CACHE_TTL):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            _cache_cleanup()
            now = time.time()
            cache_key = key(*args, **kwargs) if callable(key) else key
            if cache_key in _cache and now - _cache[cache_key]["ts"] < ttl:
                return _cache[cache_key]["data"]
            result = fn(*args, **kwargs)
            _cache[cache_key] = {"data": result, "ts": now}
            return result
        return wrapper
    return decorator


def _is_blocked(html_text):
    blocks = [
        "challenge-platform", "captcha", "please verify you're not a robot",
        "too many requests", "limit exceeded",
    ]
    return any(b in html_text.lower() for b in blocks)


def _fetch_url(url, timeout=20):
    for attempt in range(3):
        ua = random.choice(USER_AGENTS)
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "")
                if resp.status == 200 and "text/html" in content_type:
                    decoded = body.decode("utf-8", "replace")
                    if _is_blocked(decoded):
                        raise RuntimeError("LinkedIn isteği engelledi (rate limit / captcha)")
                return body
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            if attempt < 2:
                time.sleep(3 * (2 ** attempt))
                continue
            raise


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/search":
            self._proxy_search(parsed.query)
            return

        if parsed.path == "/api/applicants":
            self._proxy_applicants(parsed.query)
            return

        if parsed.path == "/api/typeahead":
            self._proxy_typeahead(parsed.query)
            return

        if parsed.path == "/" or parsed.path == "":
            self.path = "/index.html"

        return super().do_GET()

    @_cached(lambda self, url: url)
    def _do_fetch(self, url):
        return _fetch_url(url)

    def _proxy_search(self, query_string):
        params = urllib.parse.parse_qs(query_string)

        linkedin_params = {
            "keywords": params.get("keywords", ["devops"])[0],
            "start": params.get("start", ["0"])[0],
        }

        if "hours" in params:
            linkedin_params["f_TPR"] = f"r{int(params['hours'][0]) * 3600}"
        if "remote" in params:
            linkedin_params["f_WT"] = "2"
        elif "location" in params and params["location"][0].strip():
            linkedin_params["location"] = params["location"][0]

        url = f"{API}?{urllib.parse.urlencode(linkedin_params)}"

        try:
            body = self._do_fetch(url)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", f"max-age={CACHE_TTL}")
            self.end_headers()
            self.wfile.write(body)
        except RuntimeError as e:
            self.send_response(429)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(str(e).encode())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def _proxy_typeahead(self, query_string):
        params = urllib.parse.parse_qs(query_string)
        query = params.get("q", [""])[0].strip()

        if len(query) < 2:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"[]")
            return

        url = f"{TYPEAHEAD}?{urllib.parse.urlencode({'query': query, 'typeaheadType': 'GEO'})}"

        try:
            body = self._do_fetch(url)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", f"max-age={CACHE_TTL}")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        print(f"  {args[0]}")

    def _proxy_applicants(self, query_string):
        params = urllib.parse.parse_qs(query_string)
        raw_ids = params.get("ids", [""])[0]
        job_ids = [jid.strip() for jid in raw_ids.split(",") if jid.strip()]

        if len(job_ids) > 50:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Too many IDs (max 50)"}).encode())
            return

        counts = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self._fetch_applicant_count, jid): jid for jid in job_ids}
            for future in as_completed(futures):
                jid = futures[future]
                try:
                    counts[jid] = future.result()
                except Exception:
                    counts[jid] = None

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(counts, ensure_ascii=False).encode())

    @_cached(lambda self, job_id: f"applicant_count_{job_id}", ttl=CACHE_TTL)
    def _fetch_applicant_count(self, job_id):
        url = f"https://www.linkedin.com/jobs/view/{job_id}"
        for attempt in range(3):
            try:
                body = _fetch_url(url, timeout=15)
                html_text = body.decode("utf-8", "replace")
                m = re.search(r"(\d+)\s*applicants?", html_text, re.IGNORECASE)
                if m:
                    return int(m.group(1))
                if "Be the first" in html_text or "İlk başvuran" in html_text:
                    return 0
                return None
            except Exception:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                return None


def print_banner(port):
    banner = f"""
  ╭{'─' * 50}╮
  │  {'':46} │
  │  ⌖  İlanRotası  v2.0{'':29} │
  │  {'':46} │
  │  ▸  Web:  http://localhost:{port:<4}{'':20} │
  │  ▸  CLI:  python3 is_ilan.py devops{'':21} │
  │  {'':46} │
  │  Çıkmak için Ctrl+C{'':33} │
  │  {'':46} │
  ╰{'─' * 50}╯
"""
    print(banner)


def main():
    ap = argparse.ArgumentParser(description="is-ilan web sunucusu")
    ap.add_argument("--port", "-p", type=int, default=8080, help="Port (varsayılan: 8080)")
    args = ap.parse_args()

    addr = ("127.0.0.1", args.port)
    server = http.server.HTTPServer(addr, ProxyHandler)

    print_banner(args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Sunucu durduruldu.\n")
        server.server_close()


if __name__ == "__main__":
    main()
