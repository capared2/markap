from scraper import urls


def test_normalize_strips_tracking_and_trailing_slash():
    raw = "http://marca.com/futbol/real-madrid.html/?utm_source=twitter&id=7#comentarios"
    assert urls.normalize(raw) == "https://www.marca.com/futbol/real-madrid.html?id=7"


def test_normalize_is_idempotent():
    once = urls.normalize("https://www.marca.com/futbol/2026/08/19/abc123.html")
    assert urls.normalize(once) == once


def test_is_article_url_accepts_dated_stories():
    assert urls.is_article_url("https://www.marca.com/futbol/real-madrid/2026/08/19/68a1b2c3ca4741f1234b45a8.html")


def test_is_article_url_accepts_undated_permalinks_with_a_story_id():
    assert urls.is_article_url("https://www.marca.com/futbol/68a1b2c3ca4741f1234b45a8.html")


def test_is_article_url_rejects_sections_and_other_hosts():
    assert not urls.is_article_url("https://www.marca.com/futbol.html")
    # secciones con guion: el caso que antes se colaba como noticia
    assert not urls.is_article_url("https://www.marca.com/futbol/primera-division.html")
    assert not urls.is_article_url("https://www.marca.com/futbol/real-madrid.html")
    assert not urls.is_article_url("https://www.marca.com/baloncesto/nba.html")
    assert not urls.is_article_url("https://www.elmundo.es/futbol/2026/08/19/abc.html")
    assert not urls.is_article_url("https://www.marca.com/servicios/2026/08/19/abc.html")


def test_category_key_uses_section_before_the_date():
    url = "https://www.marca.com/futbol/real-madrid/2026/08/19/68a1.html"
    assert urls.category_key(url, depth=2) == "futbol/real-madrid"
    assert urls.category_key(url, depth=1) == "futbol"


def test_category_key_moves_generic_containers_to_the_back():
    url = "https://www.marca.com/albumes/futbol/2026/08/19/68a1.html"
    assert urls.category_key(url, depth=2) == "futbol/albumes"


def test_category_key_falls_back_to_portada():
    assert urls.category_key("https://www.marca.com/index.html") == "portada"


def test_path_date_and_article_id():
    url = "https://www.marca.com/tenis/2026/08/19/68a1b2c3.html"
    assert urls.path_date(url) == "2026-08-19"
    assert urls.article_id(url) == "68a1b2c3"


def test_slugify_removes_accents():
    assert urls.slugify("Fórmula 1 / Móvil") == "formula-1-movil"
