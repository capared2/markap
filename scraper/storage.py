"""Sharded JSON dataset split by category, plus resumable run state."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

PART_TEMPLATE = "part-{:04d}.json"
LATEST_LIMIT = 200          # noticias en la portada ligera del frontend
# Campos que el frontend necesita para una tarjeta: el cuerpo se deja fuera
# para que latest.json siga pesando poco.
CARD_FIELDS = (
    "id", "url", "category", "title", "standfirst", "summary",
    "authors", "published_at", "images", "is_premium",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload) -> None:
    """Atomic write so an interrupted run never leaves half a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        log.error("corrupt JSON at %s (%s); starting that file over", path, exc)
        return default


class ArticleStore:
    """Writes ``data/<categoria>/part-NNNN.json`` files of bounded size."""

    def __init__(self, data_dir: str | Path, shard_size: int):
        self.data_dir = Path(data_dir)
        self.shard_size = max(1, shard_size)
        self._lock = threading.Lock()
        self._buffers: dict[str, list[dict]] = {}

    def add(self, article: dict) -> None:
        with self._lock:
            self._buffers.setdefault(article["category"], []).append(article)

    @property
    def pending_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._buffers.values())

    def category_dir(self, category: str) -> Path:
        return self.data_dir.joinpath(*category.split("/"))

    def _parts(self, category: str) -> list[Path]:
        directory = self.category_dir(category)
        if not directory.is_dir():
            return []
        return sorted(p for p in directory.glob("part-*.json") if p.is_file())

    def flush(self) -> dict[str, int]:
        """Persist buffered articles. Returns articles written per category."""
        with self._lock:
            buffers, self._buffers = self._buffers, {}

        written: dict[str, int] = {}
        for category, articles in buffers.items():
            if not articles:
                continue
            written[category] = self._append(category, articles)
        return written

    def _append(self, category: str, articles: list[dict]) -> int:
        directory = self.category_dir(category)
        directory.mkdir(parents=True, exist_ok=True)

        parts = self._parts(category)
        index = int(parts[-1].stem.split("-")[-1]) if parts else 1
        current = directory / PART_TEMPLATE.format(index)
        payload = _read_json(current, None)
        bucket = payload.get("articles", []) if isinstance(payload, dict) else []

        known = {a.get("url") for a in bucket}
        total = 0
        for article in articles:
            if article["url"] in known:
                continue
            if len(bucket) >= self.shard_size:
                self._save_part(current, category, index, bucket)
                index += 1
                current = directory / PART_TEMPLATE.format(index)
                bucket, known = [], set()
            bucket.append(article)
            known.add(article["url"])
            total += 1

        self._save_part(current, category, index, bucket)
        return total

    @staticmethod
    def _save_part(path: Path, category: str, index: int, articles: list[dict]) -> None:
        articles.sort(key=lambda a: (a.get("published_at") or "", a.get("id") or ""))
        _write_json(
            path,
            {
                "category": category,
                "part": index,
                "count": len(articles),
                "updated_at": _now(),
                "articles": articles,
            },
        )

    def rebuild_index(self) -> dict:
        """Write ``data/index.json`` and the ``data/latest.json`` cover feed."""
        categories: list[dict] = []
        latest: list[dict] = []
        total = 0
        for part in sorted(self.data_dir.rglob("part-*.json")):
            payload = _read_json(part, {})
            if not payload.get("category"):
                continue
            latest.extend(
                {key: article.get(key) for key in CARD_FIELDS}
                for article in payload.get("articles", [])
            )
            relative = part.relative_to(self.data_dir).as_posix()
            entry = next(
                (c for c in categories if c["category"] == payload["category"]),
                None,
            )
            if entry is None:
                entry = {"category": payload["category"], "articles": 0, "files": []}
                categories.append(entry)
            entry["articles"] += payload.get("count", 0)
            entry["files"].append({"file": relative, "count": payload.get("count", 0)})
            total += payload.get("count", 0)

        categories.sort(key=lambda c: (-c["articles"], c["category"]))
        latest.sort(key=lambda a: (a.get("published_at") or "", a.get("id") or ""), reverse=True)
        latest = latest[:LATEST_LIMIT]
        for article in latest:
            # una sola imagen por tarjeta: la de portada
            images = article.get("images") or []
            article["image"] = images[0]["url"] if images else None
            article.pop("images", None)
        _write_json(
            self.data_dir / "latest.json",
            {"generated_at": _now(), "count": len(latest), "articles": latest},
        )

        index = {
            "source": "marca.com",
            "generated_at": _now(),
            "total_articles": total,
            "total_categories": len(categories),
            "categories": categories,
        }
        _write_json(self.data_dir / "index.json", index)
        return index


class RunState:
    """Tracks scraped URLs, the queue of URLs still to fetch and failure counts."""

    def __init__(self, state_dir: str | Path, max_failures: int = 3):
        self.state_dir = Path(state_dir)
        self.seen_path = self.state_dir / "seen.txt"
        self.pending_path = self.state_dir / "pending.txt"
        self.failed_path = self.state_dir / "failed.json"
        self.meta_path = self.state_dir / "run.json"
        self.max_failures = max(1, max_failures)

        self.seen: set[str] = self._read_lines(self.seen_path)
        self.pending: list[str] = [u for u in self._read_ordered(self.pending_path) if u not in self.seen]
        failed = _read_json(self.failed_path, {})
        self.failed: dict[str, int] = failed if isinstance(failed, dict) else {}
        self._lock = threading.Lock()

    def _exhausted(self) -> set[str]:
        """URLs that failed too many times to be worth queueing again."""
        return {url for url, count in self.failed.items() if count >= self.max_failures}

    @staticmethod
    def _read_lines(path: Path) -> set[str]:
        if not path.exists():
            return set()
        with path.open(encoding="utf-8") as handle:
            return {line.strip() for line in handle if line.strip()}

    @staticmethod
    def _read_ordered(path: Path) -> list[str]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]

    def enqueue(self, candidates) -> int:
        """Add unseen URLs to the queue, preserving order and dropping dupes."""
        with self._lock:
            known = self.seen | set(self.pending) | self._exhausted()
            added = 0
            for url in candidates:
                if url not in known:
                    self.pending.append(url)
                    known.add(url)
                    added += 1
            return added

    def take(self, count: int) -> list[str]:
        with self._lock:
            batch = self.pending[:count]
            self.pending = self.pending[count:]
            return batch

    def mark_seen(self, url: str) -> None:
        with self._lock:
            self.seen.add(url)
            self.failed.pop(url, None)

    def mark_failed(self, url: str) -> None:
        with self._lock:
            self.failed[url] = self.failed.get(url, 0) + 1

    def requeue(self, items) -> None:
        with self._lock:
            self.pending = list(items) + self.pending

    def save(self, meta: dict | None = None) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._write_lines(self.seen_path, sorted(self.seen))
            self._write_lines(self.pending_path, self.pending)
            _write_json(self.failed_path, dict(sorted(self.failed.items())))
            payload = {
                "updated_at": _now(),
                "seen": len(self.seen),
                "pending": len(self.pending),
                "failed": len(self.failed),
                "abandoned": len(self._exhausted()),
            }
            payload.update(meta or {})
            _write_json(self.meta_path, payload)

    @staticmethod
    def _write_lines(path: Path, lines) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(f"{line}\n")
        os.replace(tmp, path)
