"""Genera los artefactos de SEO del sitio a partir del dataset.

Se producen aqui, en el mismo paso que los indices, por dos razones: quedan
actualizados solos en cada ejecucion sin intervencion, y el sitio los puede
servir tal cual, sin gastar CPU en construirlos en cada peticion (Cloudflare
Workers corta a los 10 ms en el plan gratuito).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

log = logging.getLogger(__name__)

# Limite del protocolo: 50.000 URLs y 50 MB por fichero. Se usa la mitad para
# dejar margen y que cada fichero sea rapido de servir.
URLS_POR_SITEMAP = 25_000
# Google News solo mira las ultimas 48 horas y admite 1.000 URLs.
HORAS_NOTICIAS = 48
MAX_NOTICIAS = 1_000


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _escribir(ruta: Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")


def _urlset(urls: list[str], namespaces: str = "") -> str:
    cabecera = f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"{namespaces}>'
    return "\n".join(['<?xml version="1.0" encoding="UTF-8"?>', cabecera, *urls, "</urlset>", ""])


def _entrada(loc: str, lastmod: str | None = None, prioridad: str | None = None,
             frecuencia: str | None = None, extra: str = "") -> str:
    partes = [f"  <url>", f"    <loc>{escape(loc)}</loc>"]
    if lastmod:
        partes.append(f"    <lastmod>{lastmod}</lastmod>")
    if frecuencia:
        partes.append(f"    <changefreq>{frecuencia}</changefreq>")
    if prioridad:
        partes.append(f"    <priority>{prioridad}</priority>")
    if extra:
        partes.append(extra)
    partes.append("  </url>")
    return "\n".join(partes)


def _fecha_sitemap(iso: str | None) -> str | None:
    """Los sitemaps piden W3C datetime; el dataset ya guarda ISO-8601 UTC."""
    return iso if iso else None


def construir(
    data_dir: str | Path,
    site_url: str,
    articulos: list[dict],
    categorias: list[dict],
) -> dict:
    """Escribe sitemaps y manifiesto en ``data/seo/``.

    ``articulos`` son entradas ligeras {url, category, id, published_at,
    modified_at, title, image}; ``categorias`` es lo que ya publica index.json.
    """
    base = site_url.rstrip("/")
    destino = Path(data_dir) / "seo"

    ordenados = sorted(
        articulos,
        key=lambda a: (a.get("modified_at") or a.get("published_at") or ""),
        reverse=True,
    )

    # --- sitemaps de noticias, troceados ---
    trozos: list[str] = []
    for numero, comienzo in enumerate(range(0, len(ordenados), URLS_POR_SITEMAP), start=1):
        lote = ordenados[comienzo : comienzo + URLS_POR_SITEMAP]
        urls = [
            _entrada(
                f"{base}/noticia/{a['category']}/{a['id']}",
                _fecha_sitemap(a.get("modified_at") or a.get("published_at")),
                prioridad="0.8" if numero == 1 else "0.5",
                frecuencia="daily" if numero == 1 else "monthly",
            )
            for a in lote
        ]
        nombre = f"sitemap-noticias-{numero:04d}.xml"
        _escribir(destino / nombre, _urlset(urls))
        trozos.append(nombre)

    # --- sitemap de secciones y paginas fijas ---
    fijas = [
        _entrada(f"{base}/", _ahora(), "1.0", "hourly"),
        _entrada(f"{base}/categorias", _ahora(), "0.6", "weekly"),
    ]
    for categoria in categorias:
        fijas.append(
            _entrada(
                f"{base}/categoria/{categoria['category']}",
                _ahora(),
                "0.7",
                "hourly",
            )
        )
    _escribir(destino / "sitemap-secciones.xml", _urlset(fijas))

    # --- sitemap de Google News: solo lo publicado en las ultimas 48 h ---
    limite = datetime.now(timezone.utc) - timedelta(hours=HORAS_NOTICIAS)
    recientes: list[str] = []
    for a in ordenados:
        publicado = a.get("published_at")
        if not publicado:
            continue
        try:
            cuando = datetime.fromisoformat(publicado.replace("Z", "+00:00"))
        except ValueError:
            continue
        if cuando < limite:
            continue
        recientes.append(
            _entrada(
                f"{base}/noticia/{a['category']}/{a['id']}",
                _fecha_sitemap(publicado),
                extra=(
                    "    <news:news>\n"
                    "      <news:publication>\n"
                    "        <news:name>jomperr</news:name>\n"
                    "        <news:language>es</news:language>\n"
                    "      </news:publication>\n"
                    f"      <news:publication_date>{publicado}</news:publication_date>\n"
                    f"      <news:title>{escape(a.get('title', ''))}</news:title>\n"
                    "    </news:news>"
                ),
            )
        )
        if len(recientes) >= MAX_NOTICIAS:
            break
    _escribir(
        destino / "sitemap-news.xml",
        _urlset(recientes, ' xmlns:news="http://www.google.com/schemas/sitemap-news/0.9"'),
    )

    # --- indice que los agrupa ---
    hijos = ["sitemap-secciones.xml", "sitemap-news.xml", *trozos]
    lineas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for hijo in hijos:
        lineas += ["  <sitemap>", f"    <loc>{base}/{hijo}</loc>",
                   f"    <lastmod>{_ahora()}</lastmod>", "  </sitemap>"]
    lineas += ["</sitemapindex>", ""]
    _escribir(destino / "sitemap.xml", "\n".join(lineas))

    manifiesto = {
        "generated_at": _ahora(),
        "site_url": base,
        "total_urls": len(ordenados) + len(fijas),
        "sitemaps": hijos,
        "news_urls": len(recientes),
    }
    log.info("SEO: %s URLs en %s sitemaps (%s en el de noticias)",
             manifiesto["total_urls"], len(hijos), len(recientes))
    return manifiesto
