"""Ejercita la capa HTTP real contra un servidor local (sin salir a internet)."""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from scraper.fetcher import Fetcher, RateLimiter

ROBOTS = b"""User-agent: *
Disallow: /servicios/
Sitemap: http://%s/sitemap.xml
"""


class Handler(BaseHTTPRequestHandler):
    flaky_hits = 0

    def do_GET(self):
        if self.path == "/robots.txt":
            body = ROBOTS % self.headers["Host"].encode()
            self._send(200, body, "text/plain")
        elif self.path == "/ok.html":
            self._send(200, b"<html><body>hola</body></html>", "text/html")
        elif self.path == "/flaky.html":
            Handler.flaky_hits += 1
            if Handler.flaky_hits < 3:
                self._send(503, b"nope", "text/plain")
            else:
                self._send(200, b"<html>por fin</html>", "text/html")
        elif self.path == "/servicios/secreto.html":
            self._send(200, b"<html>no deberias ver esto</html>", "text/html")
        else:
            self._send(404, b"missing", "text/plain")

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture
def fetcher():
    client = Fetcher(delay=0, retries=3, timeout=5)
    client.session.trust_env = False  # ignora proxies del entorno
    yield client
    client.close()


def test_get_returns_page_contents(server, fetcher):
    resp = fetcher.get(f"{server}/ok.html")
    assert resp is not None
    assert resp.status == 200
    assert "hola" in resp.text
    assert "text/html" in resp.content_type


def test_missing_page_returns_none_without_retrying(server, fetcher):
    assert fetcher.get(f"{server}/falta.html") is None
    assert fetcher.stats["requests"] == 2  # robots.txt + la peticion fallida
    assert fetcher.stats["errors"] == 1


def test_server_errors_are_retried_with_backoff(server, fetcher, monkeypatch):
    monkeypatch.setattr("scraper.fetcher.time.sleep", lambda _: None)
    Handler.flaky_hits = 0
    resp = fetcher.get(f"{server}/flaky.html")
    assert resp is not None
    assert "por fin" in resp.text
    assert Handler.flaky_hits == 3


def test_robots_disallow_is_honoured(server, fetcher):
    assert fetcher.get(f"{server}/servicios/secreto.html") is None
    assert fetcher.stats["blocked"] == 1


def test_sitemaps_are_read_from_robots(server, fetcher):
    assert fetcher.sitemaps_from_robots(server) == [f"http://127.0.0.1:{server.rsplit(':', 1)[1]}/sitemap.xml"]


def test_robots_is_fetched_once_per_origin(server, fetcher):
    fetcher.get(f"{server}/ok.html")
    fetcher.get(f"{server}/ok.html")
    assert fetcher.stats["requests"] == 3  # 1 robots.txt + 2 paginas


def test_rate_limiter_spaces_requests_out():
    import time

    limiter = RateLimiter(0.05)
    started = time.monotonic()
    for _ in range(3):
        limiter.wait()
    assert time.monotonic() - started >= 0.09
