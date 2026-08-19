from pathlib import Path

import pytest

from scraper.parser import parse_article, parse_date

FIXTURE = Path(__file__).parent / "fixtures" / "article.html"
URL = "https://www.marca.com/futbol/real-madrid/2026/08/19/vinicius-decide-clasico.html"


@pytest.fixture(scope="module")
def article():
    return parse_article(FIXTURE.read_text(encoding="utf-8"), URL, category_depth=2)


def test_core_fields(article):
    assert article["title"] == "Vinicius decide el clasico en el 93"
    assert article["id"] == "vinicius-decide-clasico"
    assert article["url"] == URL
    assert article["category"] == "futbol/real-madrid"
    assert article["category_path"] == ["futbol", "real-madrid"]
    assert article["language"] == "es"
    assert article["is_premium"] is True


def test_dates_are_normalised_to_utc(article):
    assert article["published_at"] == "2026-08-19T20:47:00Z"
    assert article["modified_at"] == "2026-08-19T23:10:00Z"


def test_authors_and_tags(article):
    assert article["authors"] == ["Juan Castro", "Marca Redaccion"]
    assert "Real Madrid" in article["tags"]
    assert "Clasico" in article["tags"]
    # deduplicated case-insensitively across json-ld and news_keywords
    assert sum(t.lower() == "real madrid" for t in article["tags"]) == 1


def test_body_keeps_prose_and_drops_noise(article):
    assert "gol de Vinicius en el minuto 93" in article["body"]
    assert "Un final de infarto" in article["body"]
    assert "Te puede interesar" not in article["body"]
    assert "corto" not in article["body"]
    assert "var ads" not in article["body"]
    assert article["word_count"] > 20
    assert len(article["paragraphs"]) == 3


def test_images_and_breadcrumbs(article):
    sources = [img["url"] for img in article["images"]]
    assert "https://phantom-marca.uecdn.es/foto/vini-jsonld.jpg" in sources
    assert "https://www.marca.com/foto/interior.jpg" in sources
    assert article["breadcrumbs"] == ["Marca", "Futbol", "Real Madrid"]


def test_parse_article_returns_none_without_headline():
    assert parse_article("<html><body><p>nada</p></body></html>", URL, 2) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-08-19T22:47:00+02:00", "2026-08-19T20:47:00Z"),
        ("2026-08-19T10:00:00Z", "2026-08-19T10:00:00Z"),
        ("Tue, 19 Aug 2026 10:00:00 GMT", "2026-08-19T10:00:00Z"),
        ("2026-08-19", "2026-08-19T00:00:00Z"),
        ("basura", None),
        (None, None),
    ],
)
def test_parse_date_handles_every_format_marca_emits(raw, expected):
    assert parse_date(raw) == expected


def test_related_teasers_from_the_sidebar_stay_out_of_the_body(article):
    """La columna secundaria de Marca son noticias relacionadas, no el cuerpo."""
    assert "Mercado cerrado" not in article["body"]
    assert "Mourinho" not in article["body"]
    assert not any("Mercado cerrado" in p for p in article["paragraphs"])


def test_breadcrumbs_come_from_the_real_marca_markup(article):
    assert article["breadcrumbs"] == ["Marca", "Futbol", "Real Madrid"]
    # el submenu de secciones no es una miga de pan
    assert "Plantilla" not in article["breadcrumbs"]


def test_slug_words_are_not_kept_as_tags(article):
    """news_keywords repite el slug de la URL; eso no son etiquetas."""
    assert "decide" not in article["tags"]
    assert "vinicius" not in article["tags"]
    assert "Vinicius" in article["tags"]
    assert "Real Madrid" in article["tags"]


def test_content_type_is_read_from_marca_metadata(article):
    assert article["content_type"] == "opinion"
