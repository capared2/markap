import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

from scraper import seo

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
      "news": "http://www.google.com/schemas/sitemap-news/0.9"}


def articulo(n, categoria="futbol/real-madrid", horas=1, titulo=None):
    cuando = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat().replace("+00:00", "Z")
    return {
        "id": f"noticia-{n}",
        "category": categoria,
        "title": titulo or f"Titular {n}",
        "published_at": cuando,
        "modified_at": cuando,
    }


def construir(tmp_path, articulos, categorias=None):
    return seo.construir(
        tmp_path, "https://jomperr.com/", articulos,
        categorias or [{"category": "futbol/real-madrid", "articles": len(articulos)}],
    )


def locs(ruta):
    raiz = ElementTree.parse(ruta).getroot()
    return [n.text for n in raiz.findall(".//sm:loc", NS)]


def test_el_indice_agrupa_todos_los_sitemaps(tmp_path):
    manifiesto = construir(tmp_path, [articulo(n) for n in range(3)])
    enlaces = locs(tmp_path / "seo" / "sitemap.xml")
    assert f"https://jomperr.com/sitemap-secciones.xml" in enlaces
    assert f"https://jomperr.com/sitemap-news.xml" in enlaces
    assert f"https://jomperr.com/sitemap-noticias-0001.xml" in enlaces
    assert manifiesto["site_url"] == "https://jomperr.com"


def test_cada_noticia_tiene_su_url_absoluta(tmp_path):
    construir(tmp_path, [articulo(n) for n in range(3)])
    # el orden lo comprueba otro test; aqui importa que esten todas y bien formadas
    assert set(locs(tmp_path / "seo" / "sitemap-noticias-0001.xml")) == {
        "https://jomperr.com/noticia/futbol/real-madrid/noticia-0",
        "https://jomperr.com/noticia/futbol/real-madrid/noticia-1",
        "https://jomperr.com/noticia/futbol/real-madrid/noticia-2",
    }


def test_las_secciones_y_la_portada_entran_en_su_sitemap(tmp_path):
    construir(tmp_path, [articulo(1)], [{"category": "tenis", "articles": 1},
                                        {"category": "futbol", "articles": 1}])
    enlaces = locs(tmp_path / "seo" / "sitemap-secciones.xml")
    assert "https://jomperr.com/" in enlaces
    assert "https://jomperr.com/categorias" in enlaces
    assert "https://jomperr.com/categoria/tenis" in enlaces
    assert "https://jomperr.com/categoria/futbol" in enlaces


def test_el_sitemap_de_noticias_solo_lleva_las_ultimas_48_horas(tmp_path):
    manifiesto = construir(tmp_path, [
        articulo(1, horas=2), articulo(2, horas=40), articulo(3, horas=100),
    ])
    enlaces = locs(tmp_path / "seo" / "sitemap-news.xml")
    assert len(enlaces) == 2
    assert manifiesto["news_urls"] == 2
    assert enlaces[0].endswith("noticia-1")


def test_el_sitemap_de_noticias_lleva_los_datos_que_pide_google(tmp_path):
    construir(tmp_path, [articulo(1, titulo="Un titular")])
    raiz = ElementTree.parse(tmp_path / "seo" / "sitemap-news.xml").getroot()
    assert raiz.find(".//news:name", NS).text == "jomperr"
    assert raiz.find(".//news:language", NS).text == "es"
    assert raiz.find(".//news:title", NS).text == "Un titular"
    assert raiz.find(".//news:publication_date", NS) is not None


def test_se_trocea_al_pasar_del_limite(tmp_path, monkeypatch):
    monkeypatch.setattr(seo, "URLS_POR_SITEMAP", 2)
    construir(tmp_path, [articulo(n) for n in range(5)])
    assert (tmp_path / "seo" / "sitemap-noticias-0001.xml").exists()
    assert (tmp_path / "seo" / "sitemap-noticias-0003.xml").exists()
    assert len(locs(tmp_path / "seo" / "sitemap-noticias-0003.xml")) == 1


def test_los_titulares_con_caracteres_xml_no_rompen_el_fichero(tmp_path):
    construir(tmp_path, [articulo(1, titulo='Casillas & "el Madrid" <en directo>')])
    raiz = ElementTree.parse(tmp_path / "seo" / "sitemap-news.xml").getroot()
    assert raiz.find(".//news:title", NS).text == 'Casillas & "el Madrid" <en directo>'


def test_las_mas_recientes_van_primero_y_con_mas_prioridad(tmp_path):
    construir(tmp_path, [articulo(1, horas=50), articulo(2, horas=1)])
    xml = (tmp_path / "seo" / "sitemap-noticias-0001.xml").read_text(encoding="utf-8")
    assert xml.index("noticia-2") < xml.index("noticia-1")
    assert "<priority>0.8</priority>" in xml


def test_las_secciones_sin_pagina_propia_tambien_entran(tmp_path):
    """«hockey» solo tiene hijas, pero su pagina existe y reune lo de ellas."""
    construir(tmp_path, [articulo(1, "hockey/hockey-hielo")], [
        {"category": "hockey/hockey-hielo", "articles": 5},
        {"category": "hockey/hockey-patines", "articles": 2},
        {"category": "tenis", "articles": 9},
    ])
    enlaces = locs(tmp_path / "seo" / "sitemap-secciones.xml")
    assert "https://jomperr.com/categoria/hockey" in enlaces
    assert "https://jomperr.com/categoria/hockey/hockey-hielo" in enlaces
    assert "https://jomperr.com/categoria/hockey/hockey-patines" in enlaces
    assert "https://jomperr.com/categoria/tenis" in enlaces
    # sin duplicar las que ya tienen pagina propia
    assert enlaces.count("https://jomperr.com/categoria/tenis") == 1
