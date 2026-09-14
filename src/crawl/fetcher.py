"""Polite HTTP fetcher shared by all site spiders.

Enforces robots.txt, a jittered per-host delay, and exponential backoff on
429/5xx responses. One Fetcher instance == one host's crawl session.

An anti-bot challenge page (a CAPTCHA / "verify you're not a robot" form) is
a hard stop, never something to retry or wait out -- see CLAUDE.md's
crawling-conduct rules. Pass a site's `challenge_markers` and any response
containing one raises ChallengeEncountered immediately, whatever its status.
"""
from __future__ import annotations

import random
import time
import urllib.robotparser as robotparser
from dataclasses import dataclass
from urllib.parse import urlparse

import requests


class DisallowedByRobots(Exception):
    """Raised when a URL is blocked by the target site's robots.txt."""


class ChallengeEncountered(Exception):
    """Raised when the site serves an anti-bot challenge instead of the page.

    Never retried: backoff retries are just more requests into a wall the site
    put up on purpose. Also raised for a challenge served with HTTP 200, which
    must not reach a parser -- it would read as an empty list page (i.e. "end
    of slice") or as a detail page with every field missing.
    """


@dataclass
class RateLimit:
    min_delay_s: float = 1.5
    max_delay_s: float = 3.0


@dataclass
class RetryPolicy:
    max_attempts: int = 4
    backoff_base_s: float = 2.0
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504)


class Fetcher:
    def __init__(
        self,
        user_agent: str,
        robots_txt_url: str,
        rate_limit: RateLimit | None = None,
        retry: RetryPolicy | None = None,
        timeout_s: float = 20.0,
        challenge_markers: tuple[str, ...] = (),
    ):
        self.user_agent = user_agent
        self.rate_limit = rate_limit or RateLimit()
        self.retry = retry or RetryPolicy()
        self.timeout_s = timeout_s
        self.challenge_markers = tuple(challenge_markers)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
            }
        )
        # RobotFileParser.read() fetches with bare urllib, whose default
        # User-Agent gets a Cloudflare 403 on sites like mogi.vn -- which
        # RobotFileParser then (mis)interprets as "disallow everything".
        # Fetch it ourselves with our real UA and hand it the text instead.
        robots_resp = self._session.get(robots_txt_url, timeout=timeout_s)
        self._raise_if_challenge(robots_resp, robots_txt_url)
        robots_resp.raise_for_status()
        self._robots = robotparser.RobotFileParser()
        self._robots.parse(robots_resp.text.splitlines())
        self._last_request_at = 0.0

    def _check_allowed(self, url: str) -> None:
        if not self._robots.can_fetch(self.user_agent, url):
            raise DisallowedByRobots(url)

    def _raise_if_challenge(self, resp: requests.Response, url: str) -> None:
        if not self.challenge_markers:
            return
        final_url = getattr(resp, "url", "") or ""
        for marker in self.challenge_markers:
            if marker in final_url or marker in resp.text:
                raise ChallengeEncountered(
                    f"anti-bot challenge (HTTP {resp.status_code}, marker {marker!r}) for {url}"
                )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        delay = random.uniform(self.rate_limit.min_delay_s, self.rate_limit.max_delay_s)
        remaining = delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get(self, url: str) -> requests.Response:
        """GET a URL, obeying robots.txt, rate limit, and retry-with-backoff."""
        self._check_allowed(url)
        last_exc: Exception | None = None
        for attempt in range(1, self.retry.max_attempts + 1):
            self._throttle()
            self._last_request_at = time.monotonic()
            try:
                resp = self._session.get(url, timeout=self.timeout_s)
            except requests.RequestException as exc:
                last_exc = exc
            else:
                self._raise_if_challenge(resp, url)
                if resp.status_code not in self.retry.retry_on_status:
                    resp.raise_for_status()
                    return resp
                last_exc = requests.HTTPError(f"{resp.status_code} for {url}")
            if attempt < self.retry.max_attempts:
                backoff = self.retry.backoff_base_s * (2 ** (attempt - 1))
                backoff *= random.uniform(0.8, 1.2)  # jitter
                time.sleep(backoff)
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def host_of(url: str) -> str:
        return urlparse(url).netloc
