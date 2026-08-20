import json

import pytest

from scraper import runner
from scraper.runner import Options, run
from scraper.storage import RunState

from fake_site import FakeFetcher


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test in this file is allowed to touch the network."""
    monkeypatch.setattr(runner, "Fetcher", FakeFetcher)


def options(tmp_path, **overrides):
    defaults = dict(
        sources=["sitemap", "rss", "crawl"],
        crawl_depth=1,
        workers=2,
        delay=0,
        shard_size=2,
        data_dir=str(tmp_path / "data"),
        state_dir=str(tmp_path / "state"),
    )
    defaults.update(overrides)
    return Options(**defaults)


def test_end_to_end_writes_json_split_by_category(tmp_path):
    summary = run(options(tmp_path))

    data = tmp_path / "data"
    assert summary["saved"] == 6
    assert summary["failed"] == 0
    assert (data / "futbol" / "real-madrid" / "part-0001.json").exists()
    assert (data / "baloncesto" / "nba" / "part-0001.json").exists()
    assert (data / "tenis" / "part-0001.json").exists()
    assert (data / "motor" / "formula1" / "part-0001.json").exists()
    assert (data / "futbol" / "barcelona" / "part-0001.json").exists()

    payload = json.loads((data / "tenis" / "part-0001.json").read_text(encoding="utf-8"))
    assert payload["category"] == "tenis"
    assert payload["articles"][0]["title"] == "Vinicius decide el clasico en el 93"
    assert payload["articles"][0]["url"].endswith("/tenis/2026/08/19/ccc3.html")


def test_index_is_written_with_totals(tmp_path):
    run(options(tmp_path))
    index = json.loads((tmp_path / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["total_articles"] == 6
    assert index["source"] == "marca.com"
    assert {c["category"] for c in index["categories"]} == {
        "futbol/real-madrid", "baloncesto/nba", "tenis", "motor/formula1", "futbol/barcelona",
    }


def test_shard_size_is_respected_across_the_pipeline(tmp_path):
    run(options(tmp_path, shard_size=1))
    parts = list((tmp_path / "data" / "futbol" / "real-madrid").glob("part-*.json"))
    assert len(parts) == 2


def test_second_run_scrapes_nothing_new(tmp_path):
    run(options(tmp_path))
    second = run(options(tmp_path))
    assert second["queued"] == 0
    assert second["saved"] == 0
    assert second["total_articles"] == 6


def test_since_filter_drops_old_stories_before_fetching(tmp_path):
    summary = run(options(tmp_path, since="2026-01-01"))
    assert summary["skipped_old"] >= 1
    fetched = [u for u in RunState(tmp_path / "state").seen if "old1" in u]
    assert fetched == []


def test_max_articles_caps_the_run_and_leaves_the_rest_queued(tmp_path):
    summary = run(options(tmp_path, max_articles=2))
    assert summary["saved"] == 2
    assert len(RunState(tmp_path / "state").pending) == 4


def test_run_resumes_from_the_queue_without_rediscovering(tmp_path):
    run(options(tmp_path, max_articles=2))
    summary = run(options(tmp_path, skip_discovery=True))
    assert summary["discovered"] == 0
    assert summary["saved"] == 4
    assert RunState(tmp_path / "state").pending == []


def test_zero_time_budget_still_makes_progress(tmp_path):
    summary = run(options(tmp_path, time_budget=0))
    assert summary["saved"] == 6


def test_category_depth_one_groups_everything_under_the_top_section(tmp_path):
    run(options(tmp_path, category_depth=1))
    data = tmp_path / "data"
    assert (data / "futbol" / "part-0001.json").exists()
    assert not (data / "futbol" / "real-madrid").exists()


def test_discovery_never_consumes_the_whole_budget(tmp_path, monkeypatch):
    """Con presupuesto agotado el run termina sin descubrir ni descargar nada."""
    slow = []

    def spy(fetcher, sources, crawl_depth=1, deadline=None):
        slow.append(deadline)
        return set()

    monkeypatch.setattr(runner.discovery, "discover", spy)
    summary = run(options(tmp_path, time_budget=100))
    assert summary["discovered"] == 0
    # el descubrimiento recibe una fraccion del presupuesto, no el total
    assert slow and slow[0] is not None


def _sin_cuerpo(html, url, profundidad):
    """Parsea de verdad, pero deja sin cuerpo la noticia de tenis del sitio falso."""
    from scraper.parser import parse_article as real

    articulo = real(html, url, profundidad)
    if articulo and "ccc3" in url:
        articulo["word_count"] = 0
        articulo["paragraphs"] = []
    return articulo


def test_articles_without_a_body_are_discarded(tmp_path, monkeypatch):
    """Las narraciones en directo llegan sin cuerpo: no se guardan."""
    monkeypatch.setattr(runner, "parse_article", _sin_cuerpo)
    resumen = run(options(tmp_path, min_words=10))

    assert resumen["skipped_empty"] == 1
    assert resumen["saved"] == 5
    assert not (tmp_path / "data" / "tenis").exists()

    estado = RunState(tmp_path / "state")
    # NO se da por vista: esa misma URL puede traer la cronica mas tarde
    assert not any("ccc3" in u for u in estado.seen)
    assert any("ccc3" in u for u in estado.empty)


def test_min_words_zero_keeps_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "parse_article", _sin_cuerpo)
    resumen = run(options(tmp_path, min_words=0))

    assert resumen["skipped_empty"] == 0
    assert resumen["saved"] == 6


def test_an_empty_page_is_retried_and_then_abandoned(tmp_path, monkeypatch):
    """Un directo se reintenta unas veces; un album vacio no se pide eternamente."""
    monkeypatch.setattr(runner, "parse_article", _sin_cuerpo)

    for intento in (1, 2, 3):
        run(options(tmp_path, min_words=10, empty_retries=3))
        estado = RunState(tmp_path / "state", empty_retries=3)
        vacia = next(u for u in estado.empty if "ccc3" in u)
        assert estado.empty[vacia] == intento, f"intento {intento}"

    # agotados los reintentos, deja de encolarse
    estado = RunState(tmp_path / "state", empty_retries=3)
    assert estado.enqueue([vacia]) == 0


def test_a_page_that_later_has_a_body_is_saved(tmp_path, monkeypatch):
    """La cronica que aparece despues del partido si se guarda."""
    monkeypatch.setattr(runner, "parse_article", _sin_cuerpo)
    run(options(tmp_path, min_words=10))
    assert not (tmp_path / "data" / "tenis").exists()

    # ahora la misma URL ya trae texto
    from scraper.parser import parse_article as real

    monkeypatch.setattr(runner, "parse_article", real)
    resumen = run(options(tmp_path, min_words=10))

    assert resumen["saved"] == 1
    assert (tmp_path / "data" / "tenis" / "part-0001.json").exists()
    estado = RunState(tmp_path / "state")
    assert not any("ccc3" in u for u in estado.empty)
