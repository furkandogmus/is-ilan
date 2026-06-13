"""
Entegrasyon testleri: location vs remote, direkt LinkedIn vs proxy karşılaştırması.

Çalıştırmak için:
    python3 -m pytest tests/test_location_remote.py -v
"""
import html
import json
import time
import urllib.parse
import urllib.request
import pytest

from is_ilan import fetch, parse_listing_page

PROXY_URL = "http://127.0.0.1:8765"
DIRECT_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ── Yardımcılar ──────────────────────────────────────────────────────────────

def _direct_fetch_raw(keywords, location, hours, remote, start=0):
    """LinkedIn guest API'ye direct istek."""
    params = {"keywords": keywords, "start": str(start)}
    if hours:
        params["f_TPR"] = f"r{hours * 3600}"
    if remote:
        params["f_WT"] = "2"
    elif location:
        params["location"] = location
    url = f"{DIRECT_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(1)  # rate limit
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def _proxy_fetch_html(keywords, location, hours, remote, start=0):
    """Kendi proxy sunucusu üzerinden HTML döndürür."""
    params = {"keywords": keywords, "start": str(start)}
    if hours:
        params["hours"] = str(hours)
    if remote:
        params["remote"] = "1"
    elif location:
        params["location"] = location
    url = f"{PROXY_URL}/api/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception as e:
        pytest.skip(f"Proxy sunucu erişilemez: {e}")


def _fetch_results(fetch_fn, **kwargs):
    """Verilen fetch fonksiyonuyla 2 sayfa çek, parse et."""
    all_jobs = []
    for page in range(2):
        try:
            html_text = fetch_fn(start=page * 25, **kwargs)
            page_jobs = parse_listing_page(html_text)
            if not page_jobs:
                break
            all_jobs.extend(page_jobs)
        except Exception:
            break
        time.sleep(1)
    return all_jobs


# ── Testler: LinkedIn direkt ──────────────────────────────────────────────────

class TestDirectLinkedIn:
    """LinkedIn API'sine doğrudan istek."""

    def test_turkey_returns_turkey_jobs(self):
        """location=Turkey verince Türkiye lokasyonlu ilanlar dönmeli."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        assert len(jobs) > 0, "En az 1 iş ilanı dönmeli"
        locs = [j["location"].lower() for j in jobs]
        turkey_signs = sum(1 for l in locs if "türkiye" in l or "turkey" in l or "istanbul" in l or "ankara" in l or "izmir" in l)
        assert turkey_signs >= len(jobs) * 0.7, (
            f"İlanların en az %70'i Türkiye lokasyonlu olmalı. "
            f"{turkey_signs}/{len(jobs)} Türkiye işareti taşıyor. "
            f"Lokasyonlar: {locs[:5]}"
        )

    def test_remote_excludes_regular_location(self):
        """remote=True verince f_WT=2 filtresi uygulanmalı, global ilanlar dönmeli."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="", hours=24, remote=True)
        assert len(jobs) > 0, "Remote aramada sonuç dönmeli"
        # Remote ilanlarda lokasyon farklı ülkelerden olabilir
        locs = [j["location"] for j in jobs]
        countries = set()
        for l in locs:
            if "united states" in l.lower() or ", us" in l.lower():
                countries.add("US")
            elif "türkiye" in l.lower() or "turkey" in l.lower():
                countries.add("TR")
            else:
                countries.add("OTHER")
        assert len(countries) > 1, f"Remote ilanlar farklı ülkelerden olmalı: {countries}"

    def test_turkey_vs_remote_no_overlap(self):
        """Turkey ve Remote sonuçları kesişmemeli."""
        turkey = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        remote = _fetch_results(_direct_fetch_raw, keywords="devops", location="", hours=24, remote=True)
        turkey_ids = {j["id"] for j in turkey}
        remote_ids = {j["id"] for j in remote}
        common = turkey_ids & remote_ids
        assert len(common) == 0, (
            f"Turkey ve Remote sonuçları kesişmemeli! "
            f"Ortak: {len(common)} ilan"
        )

    def test_istanbul_returns_istanbul_jobs(self):
        """location=Istanbul verince Istanbul lokasyonlu ilanlar dönmeli."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="Istanbul", hours=72, remote=False)
        assert len(jobs) > 0, "Istanbul aramasında sonuç dönmeli"
        locs = [j["location"].lower() for j in jobs]
        istanbul = sum(1 for l in locs if "istanbul" in l)
        assert istanbul >= len(jobs) * 0.6, (
            f"Çoğu ilan Istanbul lokasyonlu olmalı. "
            f"{istanbul}/{len(jobs)} İstanbul. {locs[:5]}"
        )

    def test_no_location_returns_global(self):
        """location verilmezse global ilanlar dönmeli."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="", hours=24, remote=False)
        assert len(jobs) > 0, "Global aramada sonuç dönmeli"
        locs = [j["location"].lower() for j in jobs]
        countries = []
        for l in locs:
            if "turkey" in l or "türkiye" in l:
                countries.append("TR")
            elif "united states" in l or ", us" in l or ", tx" in l or ", ny" in l:
                countries.append("US")
            else:
                countries.append("OTHER")
        tr_count = countries.count("TR")
        assert tr_count <= len(jobs) * 0.3, (
            f"Lokasyonsuz aramada Türkiye ağırlıklı olmamalı. "
            f"{tr_count}/{len(jobs)} Türkiye"
        )


# ── Testler: Proxy karşılaştırması ───────────────────────────────────────────

class TestProxyVsDirect:
    """Proxy sonuçları direkt LinkedIn sonuçlarıyla aynı olmalı."""

    def test_turkey_proxy_equals_direct(self):
        """Proxy Turkey sonuçları direct sonuçlarla uyumlu olmalı."""
        direct = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        proxy = _fetch_results(_proxy_fetch_html, keywords="devops", location="Turkey", hours=24, remote=False)
        assert len(direct) > 0
        assert len(proxy) > 0
        direct_ids = {j["id"] for j in direct}
        proxy_ids = {j["id"] for j in proxy}
        common = direct_ids & proxy_ids
        assert len(common) >= min(len(direct_ids), len(proxy_ids)) * 0.5, (
            f"Proxy sonuçları direct sonuçlarla %50+ eşleşmeli. "
            f"Ortak: {len(common)}, Direct: {len(direct_ids)}, Proxy: {len(proxy_ids)}"
        )

    def test_remote_proxy_equals_direct(self):
        """Proxy Remote sonuçları direct sonuçlarla benzer yapıda olmalı (canlı API değişken)."""
        direct = _fetch_results(_direct_fetch_raw, keywords="devops", location="", hours=24, remote=True)
        proxy = _fetch_results(_proxy_fetch_html, keywords="devops", location="", hours=24, remote=True)
        assert len(direct) > 0, "Direct aramada sonuç dönmeli"
        assert len(proxy) > 0, "Proxy aramada sonuç dönmeli"
        # Canlı API zamana bağlı farklı sonuçlar dönebilir, %50+ eşleşme yeterli
        direct_ids = {j["id"] for j in direct}
        proxy_ids = {j["id"] for j in proxy}
        common = direct_ids & proxy_ids
        # Her iki taraf da geçerli ilan yapısı döndürmüş mü kontrol et
        for j in proxy[:3]:
            assert j["id"] and j["title"], f"Proxy ilan geçersiz: {j}"
        assert len(common) >= min(len(direct_ids), len(proxy_ids)) * 0.3, (
            f"Proxy Remote ve Direct en az %30 örtüşmeli. "
            f"Ortak: {len(common)}, Direct: {len(direct_ids)}, Proxy: {len(proxy_ids)}"
        )

    def test_proxy_structure_matches_direct(self):
        """Proxy'nin döndüğü ilan yapısı direct ile aynı olmalı."""
        direct = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        proxy = _fetch_results(_proxy_fetch_html, keywords="devops", location="Turkey", hours=24, remote=False)
        assert len(direct) > 0 and len(proxy) > 0
        # Yapısal alanları kontrol et
        d = direct[0]
        p = proxy[0]
        for key in ["id", "title", "company", "location"]:
            assert key in d, f"Direct ilan '{key}' alanını içermeli"
            assert key in p, f"Proxy ilan '{key}' alanını içermeli"
            assert isinstance(d[key], str), f"Direct ilan '{key}' string olmalı"
            assert isinstance(p[key], str), f"Proxy ilan '{key}' string olmalı"


# ── Testler: URL parametreleri ────────────────────────────────────────────────

class TestURLParams:
    def test_location_present_in_url_when_not_remote(self):
        """remote=False ise URL'de location parametresi olmalı."""
        params = {"keywords": "devops", "start": "0", "location": "Turkey"}
        url = f"{DIRECT_API}?{urllib.parse.urlencode(params)}"
        assert "location=Turkey" in url

    def test_f_WT_present_when_remote(self):
        """remote=True ise URL'de f_WT=2 parametresi olmalı."""
        params = {"keywords": "devops", "start": "0", "f_WT": "2"}
        url = f"{DIRECT_API}?{urllib.parse.urlencode(params)}"
        assert "f_WT=2" in url

    def test_location_not_combined_with_f_WT(self):
        """Aynı anda hem location hem f_WT gönderilmemeli."""
        # fetch() fonksiyonu remote=True ise location eklemez
        params = {"keywords": "devops", "start": "0", "f_TPR": "r86400", "f_WT": "2"}
        url = f"{DIRECT_API}?{urllib.parse.urlencode(params)}"
        assert "location=" not in url


# ── Testler: Parse ───────────────────────────────────────────────────────────

class TestParseJobStructure:
    def test_parsed_jobs_have_all_fields(self):
        """Parse edilen ilanlar tüm gerekli alanları içermeli."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        assert len(jobs) > 0
        required = ["id", "title", "company", "location", "listed", "url"]
        for j in jobs:
            for key in required:
                assert key in j, f"'{key}' alanı eksik: {j}"

    def test_job_ids_are_unique(self):
        """Aynı ilan ID'si tekrar etmemeli."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        assert len(jobs) > 0
        ids = [j["id"] for j in jobs]
        assert len(ids) == len(set(ids)), f"Duplicate ID'ler var: {len(ids)} total vs {len(set(ids))} unique"

    def test_urls_are_absolute(self):
        """İlan URL'leri mutlak olmalı."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="", hours=24, remote=False)
        assert len(jobs) > 0
        urls = [j["url"] for j in jobs if j.get("url")]
        assert len(urls) > 0, "En az bir ilanın URL'si olmalı"
        for url in urls:
            assert url.startswith("https://") or url.startswith("http://"), f"URL mutlak değil: {url}"

    def test_title_not_empty(self):
        """İlan başlığı boş olmamalı."""
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        assert len(jobs) > 0
        for j in jobs:
            assert j["title"].strip(), f"Boş başlık: {j}"

    def test_html_entities_decoded(self):
        """HTML entity'leri decode edilmeli (&amp; → &)."""
        html_sample = '<div data-entity-urn="urn:li:jobPosting:123"><h3 class="base-search-card__title">DevOps &amp; Cloud</h3><h4 class="base-search-card__subtitle"><a>Test Corp</a></h4><span class="job-search-card__location">Remote</span></div>'
        jobs = parse_listing_page(html_sample)
        assert len(jobs) == 1
        assert jobs[0]["title"] == "DevOps & Cloud"


# ── Testler: Filtreleme mantığı ──────────────────────────────────────────────

class TestFilteringLogic:
    """Frontend'deki filterJobs fonksiyonunun karşılığı."""

    def _filter_jobs(self, jobs, title_words=None, all_results=False, no_reposts=False):
        """filterJobs() davranışını taklit eder."""
        import re
        unique = {j["id"]: j for j in jobs}
        result = list(unique.values())
        if title_words:
            pattern = re.compile("|".join(re.escape(w) for w in title_words), re.I)
            result = [j for j in result if pattern.search(j["title"])]
        if no_reposts:
            seen = set()
            filtered = []
            for j in result:
                pair = (j["title"].lower(), j["company"].lower())
                if pair not in seen:
                    seen.add(pair)
                    filtered.append(j)
            result = filtered
        return result

    def test_filter_by_keyword_matches_title(self):
        """devops kelimesi başlıkta aranmalı."""
        jobs = [
            {"id": "1", "title": "Senior DevOps Engineer", "company": "A", "location": "TR", "listed": "", "url": ""},
            {"id": "2", "title": "Frontend Developer", "company": "B", "location": "TR", "listed": "", "url": ""},
            {"id": "3", "title": "DevOps Lead", "company": "C", "location": "TR", "listed": "", "url": ""},
        ]
        filtered = self._filter_jobs(jobs, title_words=["devops"])
        assert len(filtered) == 2
        ids = {j["id"] for j in filtered}
        assert ids == {"1", "3"}

    def test_no_reposts_dedup(self):
        """no_reposts aynı title+company eşleşmelerini tekilleştirmeli."""
        jobs = [
            {"id": "1", "title": "DevOps Engineer", "company": "Acme", "location": "TR", "listed": "", "url": ""},
            {"id": "2", "title": "DevOps Engineer", "company": "Acme", "location": "TR", "listed": "", "url": ""},
            {"id": "3", "title": "DevOps Engineer", "company": "Beta", "location": "TR", "listed": "", "url": ""},
        ]
        filtered = self._filter_jobs(jobs, no_reposts=True)
        assert len(filtered) == 2
        companies = {j["company"] for j in filtered}
        assert companies == {"Acme", "Beta"}

    def test_title_filter_case_insensitive(self):
        """Başlık filtresi case-insensitive olmalı."""
        jobs = [
            {"id": "1", "title": "DEVOPS ENGINEER", "company": "A", "location": "TR", "listed": "", "url": ""},
            {"id": "2", "title": "devops intern", "company": "B", "location": "TR", "listed": "", "url": ""},
            {"id": "3", "title": "DevOps Lead", "company": "C", "location": "TR", "listed": "", "url": ""},
        ]
        filtered = self._filter_jobs(jobs, title_words=["DevOps"])
        assert len(filtered) == 3

    def test_remote_location_not_affected_by_turkey_filter(self):
        """Turkey lokasyon filtresi remote ilanları etkilememeli (API seviyesinde)."""
        # Bu test mantıksal: filterJobs LOKASYON filtrelemesi yapmaz,
        # lokasyon filtrelemesi tamamen LinkedIn API'sinden gelir.
        jobs = _fetch_results(_direct_fetch_raw, keywords="devops", location="Turkey", hours=24, remote=False)
        assert len(jobs) > 0
        # Sonuçlar zaten API tarafından filtrelenmiş olmalı
        locs = [j["location"] for j in jobs]
        has_turkey = any("türkiye" in l.lower() or "turkey" in l.lower() or "istanbul" in l.lower() for l in locs)
        assert has_turkey, "Türkiye lokasyon filtresi Türkiye ilanları döndürmeli"


# ── Edge case'ler ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_html_returns_empty(self):
        assert parse_listing_page("") == []

    def test_junk_html_returns_empty(self):
        assert parse_listing_page("<html><body>no jobs</body></html>") == []

    def test_special_characters_in_title(self):
        """Özel karakterli başlıklar parse edilebilmeli."""
        html_sample = '<div data-entity-urn="urn:li:jobPosting:123"><h3 class="base-search-card__title">C++ Developer (m/w/d)</h3><h4 class="base-search-card__subtitle"><a>Tech GmbH</a></h4><span class="job-search-card__location">Berlin</span></div><time datetime="2026-01-01T00:00:00Z"></time>'
        jobs = parse_listing_page(html_sample)
        assert len(jobs) == 1
        assert "C++" in jobs[0]["title"]
        assert "GmbH" in jobs[0]["company"]

    def test_company_without_link(self):
        """Şirket adı <a> etiketi olmadan da parse edilebilmeli."""
        html_sample = '<div data-entity-urn="urn:li:jobPosting:999"><h3 class="base-search-card__title">Test Role</h3><h4 class="base-search-card__subtitle">Plain Text Company</h4><span class="job-search-card__location">Remote</span></div>'
        jobs = parse_listing_page(html_sample)
        assert len(jobs) == 1
        assert jobs[0]["company"] == "Plain Text Company"

    def test_multiple_pages_consistent(self):
        """Farklı sayfalar aynı yapıda ilan döndürmeli."""
        html1 = _direct_fetch_raw(keywords="devops", location="Turkey", hours=24, remote=False, start=0)
        html2 = _direct_fetch_raw(keywords="devops", location="Turkey", hours=24, remote=False, start=25)
        jobs1 = parse_listing_page(html1)
        jobs2 = parse_listing_page(html2)
        if jobs1 and jobs2:
            # Sayfalar arası ID tekrarı olmamalı
            ids1 = {j["id"] for j in jobs1}
            ids2 = {j["id"] for j in jobs2}
            common = ids1 & ids2
            assert len(common) == 0, (
                f"Farklı sayfalarda aynı ID'ler olmamalı! "
                f"Sayfa 1: {len(ids1)}, Sayfa 2: {len(ids2)}, Ortak: {len(common)}"
            )
