"""Elimina del dataset las noticias que no tienen cuerpo que mostrar.

Las narraciones en directo cargan el minuto a minuto por JavaScript, y algunos
albumes y promociones no llevan texto: en el sitio se veian como una pagina en
blanco. El scraper ya las descarta al vuelo (`--min-words`), pero las que se
guardaron antes de eso hay que quitarlas.

    python tools/purge.py --min-words 10 --dry-run
    python tools/purge.py --min-words 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper.config import ALLOWED_HOSTS  # noqa: E402
from scraper.storage import ArticleStore  # noqa: E402


def motivo(articulo: dict, min_words: int) -> str | None:
    """Por que hay que quitar esta noticia, si es que hay que quitarla."""
    if urlsplit(articulo.get("url", "")).netloc.lower() not in ALLOWED_HOSTS:
        return "fuera del dominio"
    if articulo.get("word_count", 0) < min_words:
        return "sin cuerpo"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--min-words", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    por_categoria: dict[str, list[dict]] = {}
    ficheros: dict[str, list[Path]] = {}
    motivos: dict[str, int] = {}
    quitadas: list[tuple[str, str]] = []

    for parte in sorted(data_dir.rglob("part-*.json")):
        with parte.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        categoria = payload.get("category")
        if not categoria:
            continue
        ficheros.setdefault(categoria, []).append(parte)
        for articulo in payload.get("articles", []):
            razon = motivo(articulo, args.min_words)
            if razon:
                motivos[razon] = motivos.get(razon, 0) + 1
                quitadas.append((razon, articulo.get("title", "")[:60]))
            else:
                por_categoria.setdefault(categoria, []).append(articulo)

    if not quitadas:
        print("No hay nada que quitar.")
        return 0

    for razon, cuantas in sorted(motivos.items(), key=lambda x: -x[1]):
        print(f"  {cuantas:>4}  {razon}")
    print("\n  ejemplos:")
    for razon, titulo in quitadas[:5]:
        print(f"    [{razon}] {titulo}")

    if args.dry_run:
        print(f"\n(simulacro) se quitarian {len(quitadas)} noticias")
        return 0

    store = ArticleStore(data_dir, 1)  # el tamaño real lo fija cada categoria abajo
    for categoria, partes in ficheros.items():
        for parte in partes:
            parte.unlink()
        directorio = store.category_dir(categoria)
        if not por_categoria.get(categoria) and directorio.exists():
            for resto in directorio.glob("lookup.json"):
                resto.unlink()
            if not any(directorio.iterdir()):
                directorio.rmdir()

    from scraper.config import DEFAULT_SHARD_SIZE

    store = ArticleStore(data_dir, DEFAULT_SHARD_SIZE)
    for articulos in por_categoria.values():
        for articulo in articulos:
            store.add(articulo)
    store.flush()
    indice = store.rebuild_index()

    print(f"\nquitadas {len(quitadas)} noticias")
    print(f"quedan {indice['total_articles']} en {indice['total_categories']} categorias")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
