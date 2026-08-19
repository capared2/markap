"""Pipeline: discover URLs, fetch articles, store them per category."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import config, discovery
from . import urls as urlutil
from .fetcher import Fetcher
from .parser import parse_article
from .storage import ArticleStore, RunState

log = logging.getLogger(__name__)

FLUSH_EVERY = 200
BATCH_SIZE = 100


@dataclass
class Options:
    mode: str = "incremental"
    sources: list[str] = field(default_factory=lambda: ["rss", "sitemap", "crawl"])
    crawl_depth: int = 1
    max_articles: int = 0            # 0 = no limit
    workers: int = config.DEFAULT_WORKERS
    delay: float = config.DEFAULT_DELAY
    timeout: int = config.DEFAULT_TIMEOUT
    retries: int = config.DEFAULT_RETRIES
    shard_size: int = config.DEFAULT_SHARD_SIZE
    category_depth: int = config.DEFAULT_CATEGORY_DEPTH
    time_budget: int = config.DEFAULT_TIME_BUDGET
    since: str | None = None         # ISO date, drops older stories
    max_failures: int = 3            # give up on a URL after this many failed runs
    data_dir: str = "data"
    state_dir: str = "state"
    user_agent: str = config.DEFAULT_USER_AGENT
    respect_robots: bool = True
    skip_discovery: bool = False


def _too_old(url: str, since: str | None) -> bool:
    if not since:
        return False
    encoded = urlutil.path_date(url)
    return bool(encoded and encoded < since)


def _fetch_one(fetcher: Fetcher, url: str, category_depth: int) -> tuple[str, dict | None]:
    resp = fetcher.get(url)
    if resp is None:
        return url, None
    if "html" not in resp.content_type.lower() and "<html" not in resp.text[:2000].lower():
        return url, None
    try:
        return url, parse_article(resp.text, resp.url, category_depth)
    except Exception:  # a single malformed page must not kill the run
        log.exception("failed to parse %s", url)
        return url, None


def run(options: Options) -> dict:
    started = time.monotonic()
    fetcher = Fetcher(
        user_agent=options.user_agent,
        delay=options.delay,
        timeout=options.timeout,
        retries=options.retries,
        respect_robots=options.respect_robots,
    )
    store = ArticleStore(options.data_dir, options.shard_size)
    state = RunState(options.state_dir, max_failures=options.max_failures)

    summary = {
        "mode": options.mode,
        "discovered": 0,
        "queued": 0,
        "fetched": 0,
        "saved": 0,
        "skipped_old": 0,
        "failed": 0,
        "categories": {},
    }

    try:
        if not options.skip_discovery:
            sources = options.sources
            if options.mode == "incremental" and "crawl" in sources and options.crawl_depth > 1:
                # Incremental runs only need the front pages.
                options.crawl_depth = 1
            found = discovery.discover(fetcher, sources, crawl_depth=options.crawl_depth)
            summary["discovered"] = len(found)

            fresh = []
            for url in sorted(found, key=lambda u: (urlutil.path_date(u) or ""), reverse=True):
                if _too_old(url, options.since):
                    summary["skipped_old"] += 1
                    continue
                fresh.append(url)
            summary["queued"] = state.enqueue(fresh)
            log.info("queued %s new URLs (%s already known)", summary["queued"], len(found) - summary["queued"])

        limit = options.max_articles if options.max_articles > 0 else float("inf")
        since_flush = 0

        while state.pending and summary["fetched"] < limit:
            elapsed = time.monotonic() - started
            if options.time_budget and elapsed > options.time_budget:
                log.info("time budget of %ss reached; %s URLs stay queued", options.time_budget, len(state.pending))
                break

            remaining = limit - summary["fetched"]
            batch = state.take(int(min(BATCH_SIZE, remaining)))
            if not batch:
                break

            with ThreadPoolExecutor(max_workers=options.workers) as pool:
                futures = {
                    pool.submit(_fetch_one, fetcher, url, options.category_depth): url
                    for url in batch
                }
                for future in as_completed(futures):
                    url, article = future.result()
                    summary["fetched"] += 1
                    if article is None:
                        summary["failed"] += 1
                        state.mark_failed(url)
                        continue
                    if options.since and (article.get("published_at") or "")[:10] < options.since:
                        summary["skipped_old"] += 1
                        state.mark_seen(url)
                        continue
                    store.add(article)
                    state.mark_seen(url)
                    state.mark_seen(article["url"])
                    summary["saved"] += 1
                    since_flush += 1

            if since_flush >= FLUSH_EVERY:
                for category, count in store.flush().items():
                    summary["categories"][category] = summary["categories"].get(category, 0) + count
                state.save()
                since_flush = 0
                log.info(
                    "progress: %s saved, %s pending, %s requests",
                    summary["saved"], len(state.pending), fetcher.stats["requests"],
                )

        for category, count in store.flush().items():
            summary["categories"][category] = summary["categories"].get(category, 0) + count

    finally:
        for category, count in store.flush().items():
            summary["categories"][category] = summary["categories"].get(category, 0) + count
        index = store.rebuild_index()
        summary["total_articles"] = index["total_articles"]
        summary["total_categories"] = index["total_categories"]
        summary["duration_seconds"] = round(time.monotonic() - started, 1)
        summary["http"] = dict(fetcher.stats)
        state.save({"last_run": summary})
        fetcher.close()

    return summary
