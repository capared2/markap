"""Reparte el dataset existente en ficheros del tamaño actual.

Bajar `--shard-size` solo afecta a los ficheros nuevos: los que ya estan
escritos conservan su tamaño porque el scraper solo abre uno nuevo cuando el
ultimo se llena. Esta herramienta reescribe cada categoria desde cero con el
tamaño vigente, y regenera indices y lookups.

    python tools/reshard.py --data-dir data --shard-size 100
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scraper.storage import ArticleStore  # noqa: E402


def categorias(data_dir: Path) -> dict[str, list[Path]]:
    """Agrupa los ficheros part por la categoria que declaran dentro."""
    encontradas: dict[str, list[Path]] = {}
    for parte in sorted(data_dir.rglob("part-*.json")):
        try:
            with parte.open(encoding="utf-8") as handle:
                categoria = json.load(handle).get("category")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  aviso: {parte} ilegible ({exc}); se omite")
            continue
        if categoria:
            encontradas.setdefault(categoria, []).append(parte)
    return encontradas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--shard-size", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    grupos = categorias(data_dir)
    if not grupos:
        print("No hay datos que reorganizar.")
        return 0

    total = tocadas = 0
    for categoria, partes in sorted(grupos.items()):
        articulos: list[dict] = []
        for parte in partes:
            with parte.open(encoding="utf-8") as handle:
                articulos.extend(json.load(handle).get("articles", []))

        # Sin duplicados y en el mismo orden que usa el scraper al guardar.
        vistos: set[str] = set()
        unicos = [a for a in articulos if a.get("url") and not (a["url"] in vistos or vistos.add(a["url"]))]
        unicos.sort(key=lambda a: (a.get("published_at") or "", a.get("id") or ""))
        total += len(unicos)

        necesarios = max(1, -(-len(unicos) // args.shard_size))
        if len(partes) == necesarios and all(
            len(json.loads(p.read_text(encoding="utf-8")).get("articles", [])) <= args.shard_size
            for p in partes
        ):
            continue  # ya esta como debe

        tocadas += 1
        print(f"  {categoria}: {len(unicos)} noticias · {len(partes)} -> {necesarios} ficheros")
        if args.dry_run:
            continue

        for parte in partes:
            parte.unlink()
        store = ArticleStore(data_dir, args.shard_size)
        for articulo in unicos:
            store.add(articulo)
        store.flush()

    print(f"\n{total} noticias · {len(grupos)} categorias · {tocadas} reorganizadas")
    if not args.dry_run:
        indice = ArticleStore(data_dir, args.shard_size).rebuild_index()
        print(f"indices regenerados: {indice['total_articles']} noticias en {indice['total_categories']} categorias")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
