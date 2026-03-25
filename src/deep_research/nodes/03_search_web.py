"""Web research node: DuckDuckGo searches."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from ddgs import DDGS
from langgraph.runtime import Runtime

from deep_research.helpers import _is_relevant, merge_sources
from deep_research.state import Configuration, SummaryState


def _ddg_search_one_query(query: str, max_results: int) -> tuple[list[dict], str | None]:
    """Run one DDG text search in its own DDGS context (thread-safe). Returns (items, error)."""
    rows: list[dict] = []
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                rows.append(
                    {
                        "title": item.get("title") or "",
                        "url": (item.get("href") or "").strip(),
                        "snippet": (item.get("body") or "")[:800],
                        "from_query": query,
                    }
                )
        return rows, None
    except Exception as e:  # noqa: BLE001
        return rows, str(e)


def web_research(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    """Execute DuckDuckGo searches for the current topic/queries in parallel.
    
    Performs web searches using search_queries (or topic as fallback), filters results
    for relevance, deduplicates URLs, and merges with existing sources. Supports
    parallel execution for faster results.
    
    Args:
        state: Graph state with topic and optionally search_queries
        runtime: Runtime context with search configuration (workers, max_results)
    
    Returns:
        dict: Updated state with:
            - sources: Merged and deduplicated list of sources with metadata
            - last_search_preview: Text preview of top 10 URLs for logging
    
    Notes:
        - Uses bigram matching for CJK text and word matching for Latin text
        - Filters out clearly unrelated results (ads, wrong topics)
        - Maintains source ID continuity via source_id_offset
    """
    cfg = runtime.context
    queries = state.get("search_queries") or [state["topic"]]
    workers = max(1, min(cfg.search_parallel_workers, len(queries)))
    print("\n--- Phase: search_web\n", flush=True)
    for q in queries:
        print(f"    searching: {q[:100]!r}", flush=True)

    new_items: list[dict] = []
    if workers == 1:
        for q in queries:
            rows, err = _ddg_search_one_query(q, cfg.max_results_per_query)
            if err:
                print(f"    (search error for {q!r}: {err})", flush=True)
            new_items.extend(rows)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_q = {
                pool.submit(_ddg_search_one_query, q, cfg.max_results_per_query): q for q in queries
            }
            for fut in as_completed(future_to_q):
                q = future_to_q[fut]
                try:
                    rows, err = fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"    (search error for {q!r}: {e})", flush=True)
                    continue
                if err:
                    print(f"    (search error for {q!r}: {err})", flush=True)
                new_items.extend(rows)

    topic = state["topic"]
    before = len(new_items)
    new_items = [item for item in new_items if _is_relevant(item, topic)]
    dropped = before - len(new_items)
    if dropped:
        print(f"    (relevance filter dropped {dropped} unrelated result(s))", flush=True)

    offset = int(state.get("source_id_offset", 0))
    merged = merge_sources(state.get("sources"), new_items, start_id=offset + 1)
    preview = []
    for s in merged[: min(10, len(merged))]:
        preview.append(f"    {s.get('url', '')}")
    print("\n    top results:\n" + "\n".join(preview) if preview else "\n    (no results)", flush=True)
    return {
        "sources": merged,
        "last_search_preview": "\n".join(preview),
    }
