"""HTTP layer: throttled session, retries and robots.txt compliance."""
from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from . import config

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class Response:
    url: str
    status: int
    text: str
    content_type: str


class RateLimiter:
    """Global minimum spacing between outbound requests."""

    def __init__(self, delay: float):
        self.delay = max(0.0, delay)
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        if self.delay <= 0:
            return
        with self._lock:
            now = time.monotonic()
            sleep_for = self._next_at - now
            if sleep_for < 0:
                sleep_for = 0.0
            self._next_at = max(now, self._next_at) + self.delay
        if sleep_for > 0:
            time.sleep(sleep_for)

    def set_delay(self, delay: float) -> None:
        with self._lock:
            self.delay = max(0.0, delay)


class Fetcher:
    """Thread-safe HTTP client that stays polite to the origin."""

    def __init__(
        self,
        user_agent: str = config.DEFAULT_USER_AGENT,
        delay: float = config.DEFAULT_DELAY,
        timeout: int = config.DEFAULT_TIMEOUT,
        retries: int = config.DEFAULT_RETRIES,
        respect_robots: bool = True,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.retries = retries
        self.respect_robots = respect_robots
        self.limiter = RateLimiter(delay)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
            }
        )
        self._robots: dict[str, RobotFileParser | None] = {}
        self._robots_lock = threading.Lock()
        self.stats = {"requests": 0, "errors": 0, "blocked": 0}

    # -- robots -----------------------------------------------------------
    def _robots_for(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self._robots_lock:
            if origin in self._robots:
                return self._robots[origin]
        parser: RobotFileParser | None = None
        try:
            self.stats["requests"] += 1
            resp = self.session.get(f"{origin}/robots.txt", timeout=self.timeout)
            if resp.status_code == 200:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
                delay = parser.crawl_delay(self.user_agent)
                if delay and float(delay) > self.limiter.delay:
                    log.info("robots.txt crawl-delay=%ss honoured for %s", delay, origin)
                    self.limiter.set_delay(float(delay))
        except requests.RequestException as exc:
            log.warning("could not read robots.txt for %s: %s", origin, exc)
        with self._robots_lock:
            self._robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def sitemaps_from_robots(self, origin: str) -> list[str]:
        parser = self._robots_for(origin)
        if parser is None:
            return []
        return list(getattr(parser, "sitemaps", None) or [])

    # -- fetching ---------------------------------------------------------
    def get(self, url: str) -> Response | None:
        if not self.allowed(url):
            self.stats["blocked"] += 1
            log.debug("robots.txt disallows %s", url)
            return None

        last_error: str | None = None
        for attempt in range(1, self.retries + 1):
            self.limiter.wait()
            try:
                self.stats["requests"] += 1
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                last_error = str(exc)
            else:
                if resp.status_code == 200:
                    if resp.encoding is None:
                        resp.encoding = resp.apparent_encoding or "utf-8"
                    return Response(
                        url=str(resp.url),
                        status=resp.status_code,
                        text=resp.text,
                        content_type=resp.headers.get("Content-Type", ""),
                    )
                if resp.status_code not in RETRYABLE_STATUS:
                    log.debug("GET %s -> HTTP %s", url, resp.status_code)
                    self.stats["errors"] += 1
                    return None
                last_error = f"HTTP {resp.status_code}"

            if attempt < self.retries:
                backoff = min(30.0, (2 ** attempt) + random.uniform(0, 0.75))
                log.debug("retry %s/%s for %s in %.1fs (%s)", attempt, self.retries, url, backoff, last_error)
                time.sleep(backoff)

        self.stats["errors"] += 1
        log.warning("giving up on %s (%s)", url, last_error)
        return None

    def close(self) -> None:
        self.session.close()
