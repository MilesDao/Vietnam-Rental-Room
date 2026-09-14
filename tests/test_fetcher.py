"""Fetcher's anti-bot challenge handling, offline (requests.Session.get is monkeypatched)."""
from pathlib import Path

import pytest
import requests
import yaml

from src.crawl.fetcher import ChallengeEncountered, Fetcher, RateLimit, RetryPolicy

REPO = Path(__file__).resolve().parents[1]
ALONHADAT_FIXTURES = REPO / "tests" / "fixtures" / "alonhadat"
CHALLENGE_HTML = (ALONHADAT_FIXTURES / "challenge_page.html").read_text(encoding="utf-8")
MARKERS = ("/xac-thuc-nguoi-dung.html",)


class FakeResponse:
    def __init__(self, status_code: int, text: str = "ok", url: str = ""):
        self.status_code = status_code
        self.text = text
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def make_fetcher(monkeypatch, responses, robots=None, **kwargs):
    """A Fetcher whose session serves `robots` for robots.txt, then `responses` in order."""
    queue = list(responses)
    page_calls = []

    def fake_get(self, url, timeout=None):
        if url.endswith("/robots.txt"):
            return robots or FakeResponse(200, "User-agent: *\nDisallow:\n")
        page_calls.append(url)
        return queue.pop(0)

    monkeypatch.setattr(requests.Session, "get", fake_get)
    fetcher = Fetcher(
        user_agent="test-agent",
        robots_txt_url="https://example.test/robots.txt",
        rate_limit=RateLimit(0.0, 0.0),
        retry=RetryPolicy(max_attempts=3, backoff_base_s=0.0),
        **kwargs,
    )
    return fetcher, page_calls


def test_challenge_served_as_429_stops_without_retrying(monkeypatch):
    fetcher, calls = make_fetcher(
        monkeypatch, [FakeResponse(429, CHALLENGE_HTML)], challenge_markers=MARKERS
    )
    with pytest.raises(ChallengeEncountered):
        fetcher.get("https://example.test/page")
    assert len(calls) == 1


def test_challenge_served_as_200_is_not_returned_as_a_page(monkeypatch):
    fetcher, _ = make_fetcher(
        monkeypatch, [FakeResponse(200, CHALLENGE_HTML)], challenge_markers=MARKERS
    )
    with pytest.raises(ChallengeEncountered):
        fetcher.get("https://example.test/page")


def test_redirect_to_challenge_url_is_detected(monkeypatch):
    redirected = FakeResponse(200, "<html></html>", url="https://example.test/xac-thuc-nguoi-dung.html")
    fetcher, _ = make_fetcher(monkeypatch, [redirected], challenge_markers=MARKERS)
    with pytest.raises(ChallengeEncountered):
        fetcher.get("https://example.test/page")


def test_challenge_on_robots_txt_fails_construction(monkeypatch):
    with pytest.raises(ChallengeEncountered):
        make_fetcher(monkeypatch, [], robots=FakeResponse(429, CHALLENGE_HTML),
                     challenge_markers=MARKERS)


def test_normal_page_passes_through(monkeypatch):
    html = (ALONHADAT_FIXTURES / "detail_page_1.html").read_text(encoding="utf-8")
    fetcher, _ = make_fetcher(monkeypatch, [FakeResponse(200, html)], challenge_markers=MARKERS)
    assert fetcher.get("https://example.test/page").text == html


def test_without_markers_429_keeps_short_retries(monkeypatch):
    """mogi configures no markers, so its 429 handling must be unchanged."""
    fetcher, calls = make_fetcher(monkeypatch, [FakeResponse(429, CHALLENGE_HTML)] * 3)
    with pytest.raises(requests.HTTPError):
        fetcher.get("https://example.test/page")
    assert len(calls) == 3


def test_configured_alonhadat_markers_match_challenge_but_not_real_pages():
    cfg = yaml.safe_load((REPO / "config" / "sources.yaml").read_text(encoding="utf-8"))
    markers = cfg["alonhadat"]["challenge_markers"]
    assert markers
    assert all(m in CHALLENGE_HTML for m in markers)
    for name in ("list_page_hanoi.html", "detail_page_1.html"):
        page = (ALONHADAT_FIXTURES / name).read_text(encoding="utf-8")
        assert not any(m in page for m in markers), name
