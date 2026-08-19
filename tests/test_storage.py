import json

from scraper.storage import ArticleStore, RunState


def make_article(n, category="futbol/real-madrid"):
    return {
        "id": f"id{n:03d}",
        "url": f"https://www.marca.com/{category}/2026/08/19/id{n:03d}.html",
        "category": category,
        "title": f"Noticia {n}",
        "published_at": f"2026-08-19T{n % 24:02d}:00:00Z",
    }


def test_articles_are_split_into_shards_of_bounded_size(tmp_path):
    store = ArticleStore(tmp_path, shard_size=3)
    for n in range(7):
        store.add(make_article(n))
    assert store.flush() == {"futbol/real-madrid": 7}

    parts = sorted((tmp_path / "futbol" / "real-madrid").glob("part-*.json"))
    assert [p.name for p in parts] == ["part-0001.json", "part-0002.json", "part-0003.json"]
    counts = [json.loads(p.read_text(encoding="utf-8"))["count"] for p in parts]
    assert counts == [3, 3, 1]


def test_each_category_gets_its_own_directory(tmp_path):
    store = ArticleStore(tmp_path, shard_size=100)
    store.add(make_article(1, "futbol/barcelona"))
    store.add(make_article(2, "baloncesto/nba"))
    store.flush()

    assert (tmp_path / "futbol" / "barcelona" / "part-0001.json").exists()
    assert (tmp_path / "baloncesto" / "nba" / "part-0001.json").exists()


def test_second_run_appends_to_the_last_open_shard(tmp_path):
    store = ArticleStore(tmp_path, shard_size=5)
    store.add(make_article(1))
    store.flush()

    reopened = ArticleStore(tmp_path, shard_size=5)
    reopened.add(make_article(2))
    reopened.flush()

    payload = json.loads((tmp_path / "futbol" / "real-madrid" / "part-0001.json").read_text(encoding="utf-8"))
    assert payload["count"] == 2
    assert not (tmp_path / "futbol" / "real-madrid" / "part-0002.json").exists()


def test_duplicate_urls_are_never_written_twice(tmp_path):
    store = ArticleStore(tmp_path, shard_size=10)
    store.add(make_article(1))
    store.add(make_article(1))
    assert store.flush() == {"futbol/real-madrid": 1}

    again = ArticleStore(tmp_path, shard_size=10)
    again.add(make_article(1))
    assert again.flush() == {"futbol/real-madrid": 0}


def test_index_summarises_every_category(tmp_path):
    store = ArticleStore(tmp_path, shard_size=2)
    for n in range(3):
        store.add(make_article(n, "futbol/real-madrid"))
    store.add(make_article(9, "tenis"))
    store.flush()

    index = store.rebuild_index()
    assert index["total_articles"] == 4
    assert index["total_categories"] == 2
    top = index["categories"][0]
    assert top["category"] == "futbol/real-madrid"
    assert top["articles"] == 3
    assert [f["file"] for f in top["files"]] == [
        "futbol/real-madrid/part-0001.json",
        "futbol/real-madrid/part-0002.json",
    ]
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))["total_articles"] == 4


def test_corrupt_shard_is_replaced_instead_of_crashing(tmp_path):
    directory = tmp_path / "tenis"
    directory.mkdir(parents=True)
    (directory / "part-0001.json").write_text("{roto", encoding="utf-8")

    store = ArticleStore(tmp_path, shard_size=10)
    store.add(make_article(1, "tenis"))
    assert store.flush() == {"tenis": 1}
    assert json.loads((directory / "part-0001.json").read_text(encoding="utf-8"))["count"] == 1


def test_state_queue_survives_a_restart(tmp_path):
    state = RunState(tmp_path)
    assert state.enqueue(["https://a", "https://b", "https://a"]) == 2
    batch = state.take(1)
    assert batch == ["https://a"]
    state.mark_seen("https://a")
    state.mark_failed("https://c")
    state.save()

    resumed = RunState(tmp_path)
    assert resumed.pending == ["https://b"]
    assert resumed.seen == {"https://a"}
    assert resumed.failed == {"https://c": 1}
    # already scraped URLs are never queued again
    assert resumed.enqueue(["https://a", "https://b", "https://d"]) == 1


def test_mark_seen_clears_a_previous_failure(tmp_path):
    state = RunState(tmp_path)
    state.mark_failed("https://a")
    state.mark_seen("https://a")
    state.save()
    assert RunState(tmp_path).failed == {}


def test_failures_are_retried_until_the_limit_then_abandoned(tmp_path):
    for _ in range(2):
        state = RunState(tmp_path, max_failures=3)
        assert state.enqueue(["https://dead"]) == 1
        state.take(1)
        state.mark_failed("https://dead")
        state.save()

    # third and last attempt
    state = RunState(tmp_path, max_failures=3)
    assert state.enqueue(["https://dead"]) == 1
    state.take(1)
    state.mark_failed("https://dead")
    state.save()

    exhausted = RunState(tmp_path, max_failures=3)
    assert exhausted.failed["https://dead"] == 3
    assert exhausted.enqueue(["https://dead"]) == 0


def test_latest_feed_holds_the_newest_cards_without_bodies(tmp_path):
    store = ArticleStore(tmp_path, shard_size=50)
    for n in range(5):
        article = make_article(n, "futbol/real-madrid")
        article["published_at"] = f"2026-08-{10 + n:02d}T00:00:00Z"
        article["body"] = "un cuerpo larguisimo " * 100
        article["images"] = [{"url": f"https://img/{n}.jpg", "caption": ""}]
        store.add(article)
    store.add({**make_article(9, "tenis"), "published_at": "2020-01-01T00:00:00Z"})
    store.flush()
    store.rebuild_index()

    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["count"] == 6
    # ordenadas de mas nueva a mas vieja, sin importar la categoria
    assert latest["articles"][0]["published_at"] == "2026-08-14T00:00:00Z"
    assert latest["articles"][-1]["category"] == "tenis"
    # tarjetas ligeras: sin cuerpo, con una sola imagen de portada
    assert "body" not in latest["articles"][0]
    assert "images" not in latest["articles"][0]
    assert latest["articles"][0]["image"] == "https://img/4.jpg"
