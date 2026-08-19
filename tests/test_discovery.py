from scraper import discovery

from fake_site import FakeFetcher


def test_sitemaps_are_followed_recursively_and_filtered():
    found = discovery.from_sitemaps(FakeFetcher())
    assert "https://www.marca.com/futbol/real-madrid/2026/08/19/aaa1.html" in found
    assert "https://www.marca.com/baloncesto/nba/2026/08/18/bbb2.html" in found
    # section landing pages are not articles
    assert "https://www.marca.com/futbol.html" not in found


def test_feeds_read_link_and_guid_and_tolerate_404s():
    found = discovery.from_feeds(FakeFetcher(), feeds=[
        "https://e00-marca.uecdn.es/rss/portada.xml",
        "https://e00-marca.uecdn.es/rss/no-existe.xml",
    ])
    assert found == {
        "https://www.marca.com/tenis/2026/08/19/ccc3.html",
        "https://www.marca.com/futbol/real-madrid/2026/08/19/aaa1.html",
    }


def test_crawl_follows_sections_and_stays_on_marca():
    found = discovery.crawl(FakeFetcher(), max_depth=1, seeds=["https://www.marca.com/"])
    assert "https://www.marca.com/motor/formula1/2026/08/19/ddd4.html" in found
    assert "https://www.marca.com/futbol/barcelona/2026/08/19/fff6.html" in found
    assert not any("otrodiario" in url for url in found)


def test_crawl_depth_zero_does_not_follow_sections():
    found = discovery.crawl(FakeFetcher(), max_depth=0, seeds=["https://www.marca.com/"])
    assert "https://www.marca.com/futbol/barcelona/2026/08/19/fff6.html" not in found


def test_crawl_respects_the_page_cap():
    fetcher = FakeFetcher()
    discovery.crawl(fetcher, max_depth=1, seeds=["https://www.marca.com/"], max_pages=1)
    # solo la semilla se descarga; la seccion enlazada queda fuera
    assert fetcher.requested == ["https://www.marca.com/"]


def test_crawl_stops_when_the_deadline_has_passed():
    import time

    fetcher = FakeFetcher()
    found = discovery.crawl(
        fetcher, max_depth=1, seeds=["https://www.marca.com/"], deadline=time.monotonic() - 1
    )
    assert found == set()
    assert fetcher.requested == []


def test_feeds_stop_when_the_deadline_has_passed():
    import time

    fetcher = FakeFetcher()
    found = discovery.from_feeds(
        fetcher,
        feeds=["https://e00-marca.uecdn.es/rss/portada.xml"],
        deadline=time.monotonic() - 1,
    )
    assert found == set()
    assert fetcher.requested == []


def test_sitemaps_stop_when_the_deadline_has_passed():
    import time

    fetcher = FakeFetcher()
    assert discovery.from_sitemaps(fetcher, deadline=time.monotonic() - 1) == set()
    assert fetcher.requested == []
