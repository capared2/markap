"""URL normalisation, article detection and category derivation."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

from . import config

# https://www.marca.com/futbol/real-madrid/2026/08/19/68a1....html
DATED_ARTICLE_RE = re.compile(
    r"^/(?P<section>.+?)/(?P<year>(?:19|20)\d{2})/(?P<month>\d{2})/(?P<day>\d{2})/"
    r"(?P<slug>[^/]+)\.html$"
)

TRACKING_PREFIXES = ("utm_", "cmpid", "intcmp", "xtor", "s_kw", "fb_", "gclid", "ncid")

# Section names that are containers rather than editorial verticals.
GENERIC_SEGMENTS = {"albumes", "album", "videos", "video", "fotos", "galeria", "en"}


def normalize(url: str, drop_fragment: bool = True) -> str:
    """Canonical form of a URL: no fragment, no tracking params, no trailing slash."""
    parts = urlsplit(url.strip())
    scheme = "https" if parts.scheme in ("", "http", "https") else parts.scheme
    netloc = parts.netloc.lower()
    if netloc.startswith("marca.com"):
        netloc = "www." + netloc

    query = "&".join(
        piece
        for piece in parts.query.split("&")
        if piece and not piece.split("=")[0].lower().startswith(TRACKING_PREFIXES)
    )

    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, query, "" if drop_fragment else parts.fragment))


def host_allowed(url: str) -> bool:
    return urlsplit(url).netloc.lower() in config.ALLOWED_HOSTS


def is_excluded(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return path.startswith(config.EXCLUDED_PATH_PREFIXES)


def is_article_url(url: str) -> bool:
    """True for URLs that look like an individual Marca story."""
    if not host_allowed(url) or is_excluded(url):
        return False
    path = urlsplit(url).path
    if not path.endswith(".html"):
        return False
    if DATED_ARTICLE_RE.match(path):
        return True
    # Undated permalinks still carry Marca's hexadecimal story id. A hyphenated
    # leaf is not enough: section pages look exactly like that
    # (/futbol/primera-division.html).
    leaf = path.rsplit("/", 1)[-1][:-5]
    return bool(re.fullmatch(r"[0-9a-f]{16,}", leaf))


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "sin-categoria"


def article_id(url: str) -> str:
    """Marca's own story id when present, otherwise the slug."""
    path = urlsplit(url).path
    leaf = path.rsplit("/", 1)[-1]
    return leaf[:-5] if leaf.endswith(".html") else leaf


def path_date(url: str) -> str | None:
    """ISO date encoded in the URL, if any."""
    match = DATED_ARTICLE_RE.match(urlsplit(url).path)
    if not match:
        return None
    return f"{match['year']}-{match['month']}-{match['day']}"


def category_segments(url: str) -> list[str]:
    """Section segments of a URL, with the date and file name stripped off."""
    path = urlsplit(url).path
    match = DATED_ARTICLE_RE.match(path)
    if match:
        raw = match["section"]
    else:
        raw = path.rsplit("/", 1)[0]
    return [s for s in raw.split("/") if s]


def category_key(url: str, depth: int = config.DEFAULT_CATEGORY_DEPTH) -> str:
    """Category path used to shard the dataset, e.g. ``futbol/real-madrid``."""
    segments = [slugify(s) for s in category_segments(url)]
    # "/albumes/futbol/..." reads better as "futbol/albumes".
    if segments and segments[0] in GENERIC_SEGMENTS and len(segments) > 1:
        segments = segments[1:] + segments[:1]
    segments = [s for s in segments if s][: max(1, depth)]
    return "/".join(segments) if segments else "portada"
