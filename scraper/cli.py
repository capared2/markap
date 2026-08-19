"""Command line entry point: ``python -m scraper``."""
from __future__ import annotations

import argparse
import json
import logging
import sys

from . import config
from .runner import Options, run

SOURCES = ("sitemap", "rss", "crawl")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="Scrapea noticias de marca.com y las guarda en JSON por categoria.",
    )
    parser.add_argument(
        "--mode",
        choices=("incremental", "full"),
        default="incremental",
        help="incremental: solo lo nuevo. full: recorre todos los sitemaps (reanudable).",
    )
    parser.add_argument(
        "--sources",
        default="",
        help=f"fuentes separadas por coma: {','.join(SOURCES)} (por defecto segun --mode)",
    )
    parser.add_argument("--crawl-depth", type=int, default=1, help="profundidad del crawl HTML")
    parser.add_argument("--max-articles", type=int, default=0, help="0 = sin limite")
    parser.add_argument("--workers", type=int, default=config.DEFAULT_WORKERS)
    parser.add_argument("--delay", type=float, default=config.DEFAULT_DELAY, help="segundos entre peticiones")
    parser.add_argument("--timeout", type=int, default=config.DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=config.DEFAULT_RETRIES)
    parser.add_argument("--shard-size", type=int, default=config.DEFAULT_SHARD_SIZE,
                        help="articulos por archivo JSON")
    parser.add_argument("--category-depth", type=int, default=config.DEFAULT_CATEGORY_DEPTH,
                        help="niveles de la URL usados como categoria")
    parser.add_argument("--time-budget", type=int, default=config.DEFAULT_TIME_BUDGET,
                        help="segundos maximos de ejecucion (0 = sin limite)")
    parser.add_argument("--since", default=None, help="descarta noticias anteriores a YYYY-MM-DD")
    parser.add_argument("--max-failures", type=int, default=3,
                        help="intentos por URL antes de descartarla definitivamente")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--state-dir", default="state")
    parser.add_argument("--user-agent", default=config.DEFAULT_USER_AGENT)
    parser.add_argument("--ignore-robots", action="store_true",
                        help="no recomendado: ignora robots.txt")
    parser.add_argument("--skip-discovery", action="store_true",
                        help="solo procesa la cola pendiente, sin buscar URLs nuevas")
    parser.add_argument("--summary-file", default=None, help="escribe el resumen del run en este JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    if args.sources.strip():
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        unknown = [s for s in sources if s not in SOURCES]
        if unknown:
            print(f"fuentes desconocidas: {', '.join(unknown)}", file=sys.stderr)
            return 2
    elif args.mode == "full":
        sources = ["sitemap", "rss", "crawl"]
    else:
        sources = ["rss", "crawl"]

    options = Options(
        mode=args.mode,
        sources=sources,
        crawl_depth=args.crawl_depth,
        max_articles=args.max_articles,
        workers=args.workers,
        delay=args.delay,
        timeout=args.timeout,
        retries=args.retries,
        shard_size=args.shard_size,
        category_depth=args.category_depth,
        time_budget=args.time_budget,
        since=args.since,
        max_failures=args.max_failures,
        data_dir=args.data_dir,
        state_dir=args.state_dir,
        user_agent=args.user_agent,
        respect_robots=not args.ignore_robots,
        skip_discovery=args.skip_discovery,
    )

    summary = run(options)
    rendered = json.dumps(summary, ensure_ascii=False, indent=2)
    print("\n=== RESUMEN ===")
    print(rendered)

    if args.summary_file:
        with open(args.summary_file, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
