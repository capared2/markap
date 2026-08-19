"""An in-memory stand-in for marca.com so the pipeline can be tested offline."""
from pathlib import Path

from scraper.fetcher import Response

ARTICLE_HTML = (Path(__file__).parent / "fixtures" / "article.html").read_text(encoding="utf-8")

SITEMAP_INDEX = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://www.marca.com/sitemap-2026-08.xml</loc></sitemap>
</sitemapindex>"""

SITEMAP_URLS = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://www.marca.com/futbol/real-madrid/2026/08/19/aaa1.html</loc></url>
  <url><loc>https://www.marca.com/baloncesto/nba/2026/08/18/bbb2.html</loc></url>
  <url><loc>https://www.marca.com/futbol/real-madrid/2019/01/01/old1.html</loc></url>
  <url><loc>https://www.marca.com/futbol.html</loc></url>
</urlset>"""

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item><link>https://www.marca.com/tenis/2026/08/19/ccc3.html</link></item>
  <item><guid>https://www.marca.com/futbol/real-madrid/2026/08/19/aaa1.html</guid></item>
</channel></rss>"""

SECTION_HTML = """<html><body>
  <a href="/motor/formula1/2026/08/19/ddd4.html">Alonso</a>
  <a href="https://www.marca.com/futbol/barcelona.html">Barca</a>
  <a href="https://www.otrodiario.es/2026/08/19/eee5.html">externo</a>
</body></html>"""

SUBSECTION_HTML = """<html><body>
  <a href="/futbol/barcelona/2026/08/19/fff6.html">Yamal</a>
</body></html>"""


class FakeFetcher:
    """Implements the Fetcher surface the pipeline relies on."""

    def __init__(self, *_, **__):
        self.stats = {"requests": 0, "errors": 0, "blocked": 0}
        self.requested: list[str] = []
        self.closed = False

    def sitemaps_from_robots(self, _origin):
        return ["https://www.marca.com/sitemap.xml"]

    def get(self, url):
        self.stats["requests"] += 1
        self.requested.append(url)

        if url.endswith("/sitemap.xml"):
            return Response(url, 200, SITEMAP_INDEX, "application/xml")
        if url.endswith("sitemap-2026-08.xml"):
            return Response(url, 200, SITEMAP_URLS, "application/xml")
        if "rss" in url or url.endswith(".xml"):
            if url == "https://e00-marca.uecdn.es/rss/portada.xml":
                return Response(url, 200, RSS, "application/xml")
            self.stats["errors"] += 1
            return None  # every other feed 404s, as many really do
        if url.rstrip("/") == "https://www.marca.com":
            return Response(url, 200, SECTION_HTML, "text/html")
        if url == "https://www.marca.com/futbol/barcelona.html":
            return Response(url, 200, SUBSECTION_HTML, "text/html")
        if url.endswith(".html") and "/20" in url:
            return Response(url, 200, ARTICLE_HTML.replace(
                "https://www.marca.com/futbol/real-madrid/2026/08/19/68a1b2c3ca4741f1234b45a8.html", url
            ), "text/html")
        self.stats["errors"] += 1
        return None

    def close(self):
        self.closed = True
