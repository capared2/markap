"""Vuelca la estructura de una pagina de Marca para ajustar los selectores.

Marca cambia su maquetacion cada tanto; cuando el cuerpo de las noticias venga
sucio o falten campos, esta herramienta dice exactamente que clases usar:

    python tools/inspect_page.py https://www.marca.com/futbol/...html
"""
from __future__ import annotations

import sys

from bs4 import BeautifulSoup

sys.path.insert(0, ".")

from scraper.fetcher import Fetcher  # noqa: E402
from scraper.parser import BODY_SELECTORS, parse_article  # noqa: E402


def describe(node) -> str:
    classes = " ".join(node.get("class", []))
    ident = node.get("id", "")
    return f"<{node.name}{' id=' + ident if ident else ''}{' class=' + classes if classes else ''}>"


def arbol(nodo, nivel: int, maximo: int = 3) -> None:
    """Imprime la estructura de bloques con el inicio de su texto."""
    if nivel >= maximo:
        return
    for hijo in nodo.find_all(recursive=False):
        if hijo.name in ("script", "style", "noscript"):
            continue
        texto = hijo.get_text(" ", strip=True)[:78].replace("\n", " ")
        sangria = "  " * (nivel + 2)
        print(f"{sangria}{describe(hijo)[:64]:66} | {texto}")
        arbol(hijo, nivel + 1, maximo)


def main(url: str) -> int:
    fetcher = Fetcher(delay=0)
    resp = fetcher.get(url)
    if resp is None:
        print(f"no se pudo descargar {url}")
        return 1
    soup = BeautifulSoup(resp.text, "lxml")

    print("=" * 70)
    print("META")
    print("=" * 70)
    for tag in soup.find_all("meta"):
        key = tag.get("property") or tag.get("name") or tag.get("itemprop")
        if key and tag.get("content"):
            print(f"  {key:36} = {tag['content'][:100]}")

    print()
    print("=" * 70)
    print("CONTENEDOR DEL CUERPO")
    print("=" * 70)
    container = None
    for selector in BODY_SELECTORS:
        container = soup.select_one(selector)
        print(f"  {'HIT ' if container else 'miss'} {selector}")
        if container:
            break

    if container is not None:
        print(f"\n  contenedor elegido: {describe(container)}")
        print("\n  arbol de bloques (hasta 3 niveles):")
        arbol(container, 0)

    print()
    print("=" * 70)
    print("CANDIDATOS A MIGA DE PAN")
    print("=" * 70)
    for node in soup.find_all(["nav", "ol", "ul"]):
        classes = " ".join(node.get("class", []))
        if "bread" in classes.lower() or "miga" in classes.lower() or "bread" in (node.get("aria-label") or "").lower():
            print(f"  {describe(node)} -> {[a.get_text(strip=True) for a in node.find_all('a')][:6]}")

    print()
    print("=" * 70)
    print("RESULTADO ACTUAL DEL PARSER")
    print("=" * 70)
    article = parse_article(resp.text, url, 2)
    if article is None:
        print("  el parser no reconocio la pagina")
        return 1
    for key in ("title", "standfirst", "authors", "tags", "published_at", "section", "breadcrumbs", "word_count"):
        print(f"  {key:14}: {str(article.get(key))[:110]}")
    print("\n  primeros parrafos extraidos:")
    for parrafo in article["paragraphs"][:6]:
        print(f"    - {parrafo[:100]}")

    fetcher.close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
