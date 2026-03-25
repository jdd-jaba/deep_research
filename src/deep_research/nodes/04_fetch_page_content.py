"""Fetch pages node: full-page HTTP fetches."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.runtime import Runtime

from deep_research.fetching import fetch_page_text
from deep_research.state import Configuration, SummaryState


def fetch_pages(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    """Fetch full HTML page content for up to N sources from search results.
    
    Downloads complete web pages (not just snippets) using HTTP, extracts main text
    content with trafilatura, and adds it to source records. Supports parallel fetching
    for speed. Skips already-fetched pages and respects fetch page limits.
    
    Args:
        state: Graph state with sources list from search_web
        runtime: Runtime context with fetch configuration (max pages, timeout, workers)
    
    Returns:
        dict: Updated state with:
            - sources: Same list but with fetched_text or fetch_error added to each record
    
    Notes:
        - Only fetches up to max_fetch_pages (default 12, 0=disabled)
        - Respects timeouts and byte limits to prevent hanging
        - Extracts clean text from HTML, removing scripts/styles
        - Marks page_fetch_done=True to avoid re-fetching
    """
    cfg = runtime.context
    sources = state.get("sources") or []
    max_n = max(0, cfg.max_fetch_pages)
    if max_n == 0 or not sources:
        print("\n--- Phase: fetch_page_content — skipped (max_fetch_pages=0 or no sources)\n", flush=True)
        return {}

    workers = max(1, min(cfg.fetch_parallel_workers, max_n))
    print("\n--- Phase: fetch_page_content\n", flush=True)

    out: list[dict | None] = [None] * len(sources)
    jobs: list[tuple[int, dict, int]] = []  # (index, row copy, fetch_num 1..max_n)
    attempted = 0

    for i, s in enumerate(sources):
        row = dict(s)
        if row.get("page_fetch_done"):
            out[i] = row
            continue
        url = (row.get("url") or "").strip()
        row["page_fetch_done"] = True
        if attempted >= max_n or not url.startswith(("http://", "https://")):
            out[i] = row
            continue
        attempted += 1
        jobs.append((i, row, attempted))

    def _run_one(url: str) -> tuple[str, str | None]:
        return fetch_page_text(
            url,
            timeout=cfg.fetch_timeout,
            max_response_bytes=cfg.max_fetch_response_bytes,
            max_output_chars=cfg.max_chars_per_fetched_page,
        )

    if not jobs:
        return {"sources": [out[i] for i in range(len(sources))]}  # type: ignore[list-item]

    if workers == 1 or len(jobs) == 1:
        for i, row, num in jobs:
            url = (row.get("url") or "").strip()
            print(f"    fetch [{num}/{max_n}]: {url[:100]!r}", flush=True)
            text, err = _run_one(url)
            row["fetched_text"] = text
            if err:
                row["fetch_error"] = err
                print(f"        -> error: {err[:120]}", flush=True)
            out[i] = row
    else:
        for _, row, num in jobs:
            url = (row.get("url") or "").strip()
            print(f"    fetch [{num}/{max_n}]: {url[:100]!r}", flush=True)
        with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as pool:
            future_to_meta = {
                pool.submit(_run_one, (row.get("url") or "").strip()): (i, row)
                for i, row, _num in jobs
            }
            for fut in as_completed(future_to_meta):
                i, row = future_to_meta[fut]
                try:
                    text, err = fut.result()
                except Exception as e:  # noqa: BLE001
                    text, err = "", str(e)[:200]
                row["fetched_text"] = text
                if err:
                    row["fetch_error"] = err
                    u = (row.get("url") or "").strip()
                    print(f"        -> error ({u[:60]!r}): {err[:120]}", flush=True)
                out[i] = row

    return {"sources": [out[i] for i in range(len(sources))]}  # type: ignore[list-item]
