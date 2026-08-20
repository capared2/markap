"""Configuration constants and tunables for the Marca scraper."""
from __future__ import annotations

import os

BASE_URL = "https://www.marca.com"

# Dominio publico del sitio que consume este dataset (para los sitemaps).
SITE_URL = os.environ.get("SITE_URL", "https://jomperr.com")

# Hosts we are willing to fetch article HTML from.
ALLOWED_HOSTS = {
    "www.marca.com",
    "marca.com",
}

# Hosts that only serve feeds/sitemaps (Unidad Editorial CDN).
FEED_HOSTS = {
    "e00-marca.uecdn.es",
    "estaticos.marca.com",
}

DEFAULT_USER_AGENT = os.environ.get(
    "MARCA_USER_AGENT",
    "markap-scraper/1.0 (+https://github.com/capared2/markap)",
)

# Polite defaults. Every one of these is overridable from the CLI.
DEFAULT_DELAY = 0.6          # seconds between requests per worker slot
DEFAULT_WORKERS = 6
DEFAULT_TIMEOUT = 25         # seconds
DEFAULT_RETRIES = 3
DEFAULT_SHARD_SIZE = 100     # articulos por fichero JSON (ver README: limite de CPU)
DEFAULT_CATEGORY_DEPTH = 2   # /futbol/real-madrid/... -> "futbol/real-madrid"
DEFAULT_TIME_BUDGET = 3300   # seconds of article fetching per run

# Sitemap locations to probe when robots.txt does not advertise any.
SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemaps.xml",
    "/sitemap-news.xml",
    "/sitemap_news.xml",
    "/sitemap-noticias.xml",
    "/news-sitemap.xml",
]

# Classic Unidad Editorial RSS endpoints. Missing ones are skipped silently;
# the homepage is also scanned for <link rel="alternate"> feeds at runtime.
RSS_CANDIDATES = [
    "https://e00-marca.uecdn.es/rss/portada.xml",
    "https://e00-marca.uecdn.es/rss/futbol/primera-division.xml",
    "https://e00-marca.uecdn.es/rss/futbol/segunda-division.xml",
    "https://e00-marca.uecdn.es/rss/futbol/real-madrid.xml",
    "https://e00-marca.uecdn.es/rss/futbol/barcelona.xml",
    "https://e00-marca.uecdn.es/rss/futbol/atletico.xml",
    "https://e00-marca.uecdn.es/rss/futbol/champions-league.xml",
    "https://e00-marca.uecdn.es/rss/futbol/europa-league.xml",
    "https://e00-marca.uecdn.es/rss/futbol/copa-del-rey.xml",
    "https://e00-marca.uecdn.es/rss/futbol/seleccion.xml",
    "https://e00-marca.uecdn.es/rss/futbol/futbol-internacional.xml",
    "https://e00-marca.uecdn.es/rss/futbol/premier-league.xml",
    "https://e00-marca.uecdn.es/rss/futbol/serie-a.xml",
    "https://e00-marca.uecdn.es/rss/futbol/bundesliga.xml",
    "https://e00-marca.uecdn.es/rss/futbol/liga-francesa.xml",
    "https://e00-marca.uecdn.es/rss/futbol/futbol-femenino.xml",
    "https://e00-marca.uecdn.es/rss/baloncesto.xml",
    "https://e00-marca.uecdn.es/rss/baloncesto/nba.xml",
    "https://e00-marca.uecdn.es/rss/baloncesto/acb.xml",
    "https://e00-marca.uecdn.es/rss/baloncesto/euroliga.xml",
    "https://e00-marca.uecdn.es/rss/motor.xml",
    "https://e00-marca.uecdn.es/rss/motor/formula1.xml",
    "https://e00-marca.uecdn.es/rss/motor/motogp.xml",
    "https://e00-marca.uecdn.es/rss/tenis.xml",
    "https://e00-marca.uecdn.es/rss/ciclismo.xml",
    "https://e00-marca.uecdn.es/rss/golf.xml",
    "https://e00-marca.uecdn.es/rss/atletismo.xml",
    "https://e00-marca.uecdn.es/rss/balonmano.xml",
    "https://e00-marca.uecdn.es/rss/boxeo.xml",
    "https://e00-marca.uecdn.es/rss/nfl.xml",
    "https://e00-marca.uecdn.es/rss/esports.xml",
    "https://e00-marca.uecdn.es/rss/mas-deporte.xml",
    "https://e00-marca.uecdn.es/rss/juegos-olimpicos.xml",
    "https://e00-marca.uecdn.es/rss/tiramillas.xml",
]

# Section landing pages used as crawl seeds when sitemaps/feeds fall short.
SECTION_SEEDS = [
    "/",
    "/futbol.html",
    "/futbol/primera-division.html",
    "/futbol/segunda-division.html",
    "/futbol/real-madrid.html",
    "/futbol/barcelona.html",
    "/futbol/atletico.html",
    "/futbol/champions-league.html",
    "/futbol/europa-league.html",
    "/futbol/copa-del-rey.html",
    "/futbol/seleccion.html",
    "/futbol/futbol-internacional.html",
    "/futbol/premier-league.html",
    "/futbol/futbol-femenino.html",
    "/baloncesto.html",
    "/baloncesto/nba.html",
    "/baloncesto/acb.html",
    "/baloncesto/euroliga.html",
    "/motor.html",
    "/motor/formula1.html",
    "/motor/motogp.html",
    "/tenis.html",
    "/ciclismo.html",
    "/golf.html",
    "/atletismo.html",
    "/balonmano.html",
    "/boxeo.html",
    "/nfl.html",
    "/esports.html",
    "/mas-deporte.html",
    "/juegos-olimpicos.html",
    "/tiramillas.html",
    "/apuestas.html",
]

# Path prefixes that never hold editorial articles.
EXCLUDED_PATH_PREFIXES = (
    "/servicios/",
    "/registro/",
    "/suscripcion",
    "/estaticos/",
    "/newsletters",
    "/hemeroteca",
    "/rss",
    "/comentarios",
    "/promociones",
    "/participacion/",
    "/buscador",
)
