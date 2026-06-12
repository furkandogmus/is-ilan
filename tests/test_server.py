from server import _is_blocked


class TestIsBlocked:
    def test_captcha_detection(self):
        assert _is_blocked("Please verify you're not a robot")

    def test_challenge_platform(self):
        assert _is_blocked("challenge-platform")

    def test_limit_exceeded(self):
        assert _is_blocked("too many requests limit exceeded")

    def test_normal_html_not_blocked(self):
        assert not _is_blocked("<html><body>normal response</body></html>")
