"""Source management utilities."""

from __future__ import annotations

from deep_research.nodes.utils import normalize_url


def merge_sources(
    existing: list[dict] | None,
    new_items: list[dict],
    start_id: int = 1,
) -> list[dict]:
    existing = existing or []
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for s in existing:
        url = (s.get("url") or "").strip()
        k = normalize_url(url)
        if not k:
            continue
        if k not in by_key:
            by_key[k] = {
                "id": 0,
                "title": s.get("title", ""),
                "url": url,
                "snippet": (s.get("snippet") or "")[:800],
                "from_query": s.get("from_query", ""),
                "fetched_text": s.get("fetched_text"),
                "fetch_error": s.get("fetch_error"),
                "page_fetch_done": s.get("page_fetch_done", False),
            }
            order.append(k)
    for s in new_items:
        url = (s.get("url") or "").strip()
        k = normalize_url(url)
        if not k:
            continue
        if k not in by_key:
            by_key[k] = {
                "id": 0,
                "title": s.get("title", ""),
                "url": url,
                "snippet": (s.get("snippet") or "")[:800],
                "from_query": s.get("from_query", ""),
                "fetched_text": s.get("fetched_text"),
                "fetch_error": s.get("fetch_error"),
                "page_fetch_done": s.get("page_fetch_done", False),
            }
            order.append(k)
    out = [by_key[k] for k in order]
    for i, row in enumerate(out, start=start_id):
        row["id"] = i
    return out
