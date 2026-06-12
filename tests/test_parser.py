from is_ilan import is_blocked, parse_listing_page, relative_time

SAMPLE_HTML = """<div data-entity-urn="urn:li:jobPosting:1234567890">
  <h3 class="base-search-card__title">Senior Python Developer</h3>
  <h4 class="base-search-card__subtitle">
    <a>Acme Corp</a>
  </h4>
  <span class="job-search-card__location">Istanbul, Turkey</span>
  <time datetime="2026-06-12T10:00:00Z"></time>
  <a href="https://www.linkedin.com/jobs/view/1234567890?ref=xyz">apply</a>
</div>"""

SAMPLE_HTML_NO_LINK = """<div data-entity-urn="urn:li:jobPosting:1234567891">
  <h3 class="base-search-card__title">Junior DevOps Engineer</h3>
  <h4 class="base-search-card__subtitle">
    <a>Startup Inc</a>
  </h4>
  <span class="job-search-card__location">Ankara, Turkey</span>
  <time datetime="2026-06-11T08:00:00Z"></time>
</div>"""


class TestParseListingPage:
    def test_parses_title_company_location(self):
        jobs = parse_listing_page(SAMPLE_HTML)
        assert len(jobs) == 1
        j = jobs[0]
        assert j["id"] == "1234567890"
        assert j["title"] == "Senior Python Developer"
        assert j["company"] == "Acme Corp"
        assert j["location"] == "Istanbul, Turkey"

    def test_parses_listed_datetime(self):
        jobs = parse_listing_page(SAMPLE_HTML)
        assert jobs[0]["listed"] == "2026-06-12T10:00:00Z"

    def test_parses_url(self):
        jobs = parse_listing_page(SAMPLE_HTML)
        assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/1234567890"

    def test_url_without_query_params(self):
        jobs = parse_listing_page(SAMPLE_HTML)
        assert "?" not in jobs[0]["url"]

    def test_empty_url_when_no_href(self):
        jobs = parse_listing_page(SAMPLE_HTML_NO_LINK)
        assert jobs[0]["url"] == ""

    def test_multiple_jobs(self):
        html = SAMPLE_HTML + SAMPLE_HTML_NO_LINK
        jobs = parse_listing_page(html)
        assert len(jobs) == 2
        assert jobs[0]["id"] == "1234567890"
        assert jobs[1]["id"] == "1234567891"

    def test_empty_html(self):
        assert parse_listing_page("") == []

    def test_html_without_jobs(self):
        assert parse_listing_page("<html><body>no jobs here</body></html>") == []


class TestRelativeTime:
    def test_empty_string(self):
        assert relative_time("") == ""

    def test_invalid_date_returns_raw(self):
        assert relative_time("not-a-date") == "not-a-date"


class TestIsBlocked:
    def test_captcha_detection(self):
        assert is_blocked("Please verify you're not a robot")

    def test_challenge_platform(self):
        assert is_blocked("challenge-platform")

    def test_normal_html_not_blocked(self):
        assert not is_blocked("<html><body>normal jobs page</body></html>")

    def test_empty_not_blocked(self):
        assert not is_blocked("")
