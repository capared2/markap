"""Find article URLs through sitemaps, RSS feeds and section crawling."""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import config
from . import urls as urlutil
from .fetcher import Fetcher

log = logging.getLogger(__name__)

MAX_SITEMAP_DEPTH = 4
MAX_CRAWL_PAGES = 300   # techo de paginas de seccion por ejecucion


def _expired(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _soup(text: str) -> BeautifulSoup:
    return BeautifulSoup(text, "xml")


def _collect_sitemap(
    fetcher: Fetcher, url: str, seen: set[str], depth: int, out: set[str], deadline: float | None
) -> None:
    if depth > MAX_SITEMAP_DEPTH or url in seen or _expired(deadline):
        return
    seen.add(url)
    resp = fetcher.get(url)
    if resp is None:
        return

    soup = _soup(resp.text)

    children = [loc.get_text(strip=True) for loc in soup.select("sitemapindex > sitemap > loc")]
    for child in children:
        _collect_sitemap(fetcher, child, seen, depth + 1, out, deadline)

    added = 0
    for loc in soup.select("urlset > url > loc"):
        candidate = urlutil.normalize(loc.get_text(strip=True))
        if urlutil.is_article_url(candidate):
            out.add(candidate)
            added += 1
    if added or children:
        log.info("sitemap %s -> %s articles, %s child sitemaps", url, added, len(children))


def from_sitemaps(
    fetcher: Fetcher, extra: list[str] | None = None, deadline: float | None = None
) -> set[str]:
    found: set[str] = set()
    visited: set[str] = set()

    roots = list(fetcher.sitemaps_from_robots(config.BASE_URL))
    roots += [urljoin(config.BASE_URL, path) for path in config.SITEMAP_CANDIDATES]
    roots += list(extra or [])

    for root in dict.fromkeys(roots):
        _collect_sitemap(fetcher, root, visited, 0, found, deadline)

    if _expired(deadline):
        log.info("sitemap discovery stopped early: out of time budget")
    log.info("sitemaps produced %s article URLs", len(found))
    return found


def discover_feeds(fetcher: Fetcher) -> list[str]:
    """RSS endpoints advertised by the homepage, plus the known static list."""
    feeds = list(config.RSS_CANDIDATES)
    resp = fetcher.get(config.BASE_URL)
    if resp is not None:
        soup = BeautifulSoup(resp.text, "lxml")
        for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
            if re.search(r"rss|atom|xml", link.get("type", ""), re.I) and link.get("href"):
                feeds.append(urljoin(config.BASE_URL, link["href"]))
    return list(dict.fromkeys(feeds))


def from_feeds(
    fetcher: Fetcher, feeds: list[str] | None = None, deadline: float | None = None
) -> set[str]:
    found: set[str] = set()
    for feed in feeds if feeds is not None else discover_feeds(fetcher):
        if _expired(deadline):
            log.info("feed discovery stopped early: out of time budget")
            break
        resp = fetcher.get(feed)
        if resp is None:
            continue
        soup = _soup(resp.text)
        before = len(found)
        for node in soup.find_all(["item", "entry"]):
            link = node.find("link")
            raw = None
            if link is not None:
                raw = link.get_text(strip=True) or link.get("href")
            if not raw:
                guid = node.find("guid")
                raw = guid.get_text(strip=True) if guid else None
            if not raw:
                continue
            candidate = urlutil.normalize(raw)
            if urlutil.is_article_url(candidate):
                found.add(candidate)
        log.info("feed %s -> %s new URLs", feed, len(found) - before)
    log.info("feeds produced %s article URLs", len(found))
    return found


def crawl(
    fetcher: Fetcher,
    max_depth: int = 1,
    seeds: list[str] | None = None,
    deadline: float | None = None,
    max_pages: int = MAX_CRAWL_PAGES,
) -> set[str]:
    """Breadth-first walk over section pages, harvesting article links.

    Marca's section pages link to thousands of other section pages, so the walk
    is capped both by ``max_pages`` and by the run's time budget.
    """
    articles: set[str] = set()
    visited: set[str] = set()
    frontier = [
        urlutil.normalize(urljoin(config.BASE_URL, path))
        for path in (seeds if seeds is not None else config.SECTION_SEEDS)
    ]

    for depth in range(max_depth + 1):
        next_frontier: list[str] = []
        for page in frontier:
            if page in visited:
                continue
            if len(visited) >= max_pages or _expired(deadline):
                log.info("crawl stopped early after %s pages", len(visited))
                return articles
            visited.add(page)
            resp = fetcher.get(page)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            for anchor in soup.find_all("a", href=True):
                candidate = urlutil.normalize(urljoin(page, anchor["href"]))
                if not urlutil.host_allowed(candidate) or urlutil.is_excluded(candidate):
                    continue
                if urlutil.is_article_url(candidate):
                    articles.add(candidate)
                elif depth < max_depth and candidate not in visited:
                    next_frontier.append(candidate)
        log.info("crawl depth %s: %s pages, %s articles so far", depth, len(frontier), len(articles))
        frontier = list(dict.fromkeys(next_frontier))
        if not frontier:
            break

    return articles


def discover(
    fetcher: Fetcher,
    sources: list[str],
    crawl_depth: int = 1,
    deadline: float | None = None,
) -> set[str]:
    """Run every requested discovery source and merge the results.

    Feeds go first: they are the cheapest way to reach the freshest stories, so
    a tight time budget still yields today's news.
    """
    found: set[str] = set()
    if "rss" in sources:
        found |= from_feeds(fetcher, deadline=deadline)
    if "sitemap" in sources:
        found |= from_sitemaps(fetcher, deadline=deadline)
    if "crawl" in sources:
        found |= crawl(fetcher, max_depth=crawl_depth, deadline=deadline)
    log.info("discovery total: %s unique article URLs", len(found))
    return found
