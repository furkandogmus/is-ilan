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
import os
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"


class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SCRIPT_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/search":
            self._proxy_search(parsed.query)
            return

        if parsed.path == "/" or parsed.path == "":
            self.path = "/index.html"

        return super().do_GET()

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
        elif "location" in params:
            linkedin_params["location"] = params["location"][0]

        url = f"{API}?{urllib.parse.urlencode(linkedin_params)}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(f"Proxy error: {e}".encode())

    def log_message(self, format, *args):
        print(f"  {args[0]}")


def main():
    ap = argparse.ArgumentParser(description="is-ilan web sunucusu")
    ap.add_argument("--port", "-p", type=int, default=8080, help="Port (varsayılan: 8080)")
    args = ap.parse_args()

    addr = ("0.0.0.0", args.port)
    server = http.server.HTTPServer(addr, ProxyHandler)

    print(f"""
  ╭──────────────────────────────────────────╮
  │     is-ilan web arayüzü                  │
  │                                          │
  │     http://localhost:{args.port:<5}              │
  │                                          │
  │     Çıkmak için Ctrl+C                   │
  ╰──────────────────────────────────────────╯
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSunucu durduruldu.")
        server.server_close()


if __name__ == "__main__":
    main()
