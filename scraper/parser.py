"""Turn a Marca article page into a structured record."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import urls as urlutil

log = logging.getLogger(__name__)

ARTICLE_TYPES = {
    "newsarticle",
    "article",
    "reportagenewsarticle",
    "sportsarticle",
    "liveblogposting",
    "blogposting",
    "videoobject",
}

BODY_SELECTORS = [
    "div.ue-l-article__body",
    "div.ue-c-article__body",
    "div.ue-l-article__main",
    "[data-ue-c-article-body]",
    "div.article-body",
    "div.cuerpo-noticia",
    "article",
]

# Wrappers that sit inside the body but are not part of the story.
NOISE_PATTERN = re.compile(
    r"(related|newsletter|publicidad|advert|banner|social|share|promo|comment|"
    r"suscri|paywall|widget|taboola|outbrain|footer|breadcrumb|tags?-list)",
    re.I,
)
DROP_TAGS = ("script", "style", "noscript", "aside", "nav", "footer", "form", "iframe", "svg")


def _text(node) -> str:
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip() if node else ""


def parse_date(value) -> str | None:
    """Normalise any date Marca hands us to an ISO-8601 UTC string."""
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
        if not value:
            return None
    raw = str(value).strip()
    if not raw:
        return None

    candidate = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
            if not match:
                return None
            parsed = datetime(int(match[1]), int(match[2]), int(match[3]))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Marca occasionally emits trailing commas / concatenated blobs.
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
            except json.JSONDecodeError:
                continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                if "@graph" in item:
                    stack.append(item["@graph"])
                yield item


def _article_jsonld(soup: BeautifulSoup) -> dict:
    best: dict = {}
    for item in _iter_jsonld(soup):
        types = item.get("@type") or item.get("type") or ""
        if isinstance(types, str):
            types = [types]
        names = {str(t).lower() for t in types}
        if names & ARTICLE_TYPES:
            # Prefer the richest block when several are present.
            if len(json.dumps(item, default=str)) > len(json.dumps(best, default=str)):
                best = item
    return best


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        for attr in ("property", "name", "itemprop"):
            tag = soup.find("meta", attrs={attr: name})
            if tag and tag.get("content"):
                return tag["content"].strip()
    return None


def _people(value) -> list[str]:
    out: list[str] = []
    stack = [value]
    while stack:
        item = stack.pop(0)
        if isinstance(item, str):
            name = item.strip()
            if name:
                out.append(name)
        elif isinstance(item, list):
            stack = list(item) + stack
        elif isinstance(item, dict):
            name = item.get("name") or item.get("@id")
            if isinstance(name, str) and name.strip():
                out.append(name.strip())
    seen: set[str] = set()
    return [n for n in out if not (n.lower() in seen or seen.add(n.lower()))]


def _images(soup: BeautifulSoup, data: dict, base_url: str) -> list[dict]:
    found: list[dict] = []
    seen: set[str] = set()

    def add(url: str | None, caption: str = "") -> None:
        if not url or not isinstance(url, str):
            return
        absolute = urljoin(base_url, url.strip())
        if absolute.startswith("data:") or absolute in seen:
            return
        seen.add(absolute)
        found.append({"url": absolute, "caption": caption})

    image = data.get("image")
    stack = [image]
    while stack:
        item = stack.pop(0)
        if isinstance(item, str):
            add(item)
        elif isinstance(item, list):
            stack = list(item) + stack
        elif isinstance(item, dict):
            add(item.get("url") or item.get("contentUrl"), item.get("caption", "") or "")

    add(_meta(soup, "og:image", "twitter:image"))

    for figure in soup.select("figure"):
        img = figure.find("img")
        if not img:
            continue
        caption = _text(figure.find("figcaption"))
        add(img.get("src") or img.get("data-src") or img.get("data-original"), caption)

    return found


def _body_text(soup: BeautifulSoup) -> tuple[str, list[str]]:
    container = None
    for selector in BODY_SELECTORS:
        container = soup.select_one(selector)
        if container:
            break
    if container is None:
        container = soup.body or soup

    working = BeautifulSoup(str(container), "lxml")
    for tag in working.find_all(DROP_TAGS):
        tag.decompose()
    for tag in working.find_all(attrs={"class": NOISE_PATTERN}):
        tag.decompose()
    for tag in working.find_all(attrs={"id": NOISE_PATTERN}):
        tag.decompose()
    for tag in working.find_all("figure"):
        tag.decompose()

    paragraphs: list[str] = []
    for node in working.find_all(["p", "h2", "h3", "li"]):
        text = _text(node)
        if len(text) < 25 or text in paragraphs:
            continue
        paragraphs.append(text)

    return "\n\n".join(paragraphs), paragraphs


def parse_article(html: str, url: str, category_depth: int) -> dict | None:
    """Build the article record. Returns ``None`` when the page has no story."""
    soup = BeautifulSoup(html, "lxml")
    data = _article_jsonld(soup)

    canonical_tag = soup.find("link", rel=lambda v: v and "canonical" in v)
    canonical = urlutil.normalize(
        urljoin(url, canonical_tag["href"]) if canonical_tag and canonical_tag.get("href") else url
    )

    title = (
        (data.get("headline") if isinstance(data.get("headline"), str) else None)
        or _meta(soup, "og:title", "twitter:title")
        or _text(soup.find("h1"))
    )
    if not title:
        log.debug("no headline found for %s", url)
        return None

    body, paragraphs = _body_text(soup)
    summary = (
        (data.get("description") if isinstance(data.get("description"), str) else None)
        or _meta(soup, "og:description", "description", "twitter:description")
        or ""
    )
    standfirst = _text(
        soup.select_one(".ue-c-article__standfirst")
        or soup.select_one(".ue-c-article__subtitle")
        or soup.select_one("h2.subtitle")
    )

    authors = _people(data.get("author"))
    if not authors:
        authors = [
            _text(node)
            for node in soup.select(".ue-c-article__byline-name, .author-name, [rel=author]")
            if _text(node)
        ]

    keywords = data.get("keywords")
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",")]
    tags = [str(k).strip() for k in (keywords or []) if str(k).strip()]
    news_keywords = _meta(soup, "news_keywords")
    if news_keywords:
        tags.extend(k.strip() for k in news_keywords.split(",") if k.strip())
    seen_tags: set[str] = set()
    tags = [t for t in tags if not (t.lower() in seen_tags or seen_tags.add(t.lower()))]

    published = (
        parse_date(data.get("datePublished"))
        or parse_date(_meta(soup, "article:published_time", "date", "pubdate"))
        or (f"{urlutil.path_date(canonical)}T00:00:00Z" if urlutil.path_date(canonical) else None)
    )
    modified = parse_date(data.get("dateModified")) or parse_date(
        _meta(soup, "article:modified_time", "lastModified")
    )

    section = (
        (data.get("articleSection") if isinstance(data.get("articleSection"), str) else None)
        or _meta(soup, "article:section")
        or ""
    )
    breadcrumbs = [
        _text(node)
        for node in soup.select(".ue-c-breadcrumb a, nav[aria-label*=migas] a, .breadcrumb a")
        if _text(node)
    ]

    videos = [
        urljoin(url, node.get("src"))
        for node in soup.select("video source[src], video[src]")
        if node.get("src")
    ]

    return {
        "id": urlutil.article_id(canonical),
        "url": canonical,
        "source_url": urlutil.normalize(url),
        "category": urlutil.category_key(canonical, category_depth),
        "category_path": urlutil.category_segments(canonical),
        "section": section,
        "breadcrumbs": breadcrumbs,
        "title": title.strip(),
        "standfirst": standfirst,
        "summary": summary.strip(),
        "body": body,
        "paragraphs": paragraphs,
        "word_count": len(body.split()),
        "authors": authors,
        "tags": tags,
        "published_at": published,
        "modified_at": modified,
        "language": (soup.html.get("lang") if soup.html else None) or "es",
        "images": _images(soup, data, url),
        "videos": videos,
        "is_premium": bool(soup.select_one(".ue-c-article--premium, [data-premium=true]"))
        or data.get("isAccessibleForFree") is False,
        "source": "marca.com",
        "scraped_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
