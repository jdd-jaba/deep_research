"""LangGraph node implementations."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from ddgs import DDGS
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.fetching import fetch_page_text
from deep_research.state import Configuration, SummaryState

# Cap prior-section text passed to write_section prompt to keep context bounded.
_WRITE_SECTION_PRIOR_MAX_CHARS = 30_000


def _truncate_prior_sections(text: str, max_chars: int, lang: str) -> str:
    if len(text) <= max_chars:
        return text
    note = (
        "…（前のセクションの一部は長さのため省略）\n\n"
        if P.normalize_lang(lang) == "ja"
        else "…(earlier section text truncated for length)\n\n"
    )
    return note + text[-max_chars:]


def _extract_section_heading(section_md: str) -> str:
    """Return the ## heading line from a written section, or the first 80 chars."""
    for line in section_md.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            return stripped
    return section_md[:80].strip()


def _derive_output_path(main_topic: str) -> str:
    sanitized = re.sub(r"[^\w\s-]", "", main_topic).strip()
    sanitized = re.sub(r"\s+", "_", sanitized)[:60]
    return f"report_{sanitized}.md"


@lru_cache(maxsize=16)
def _llm_cached(model: str, base_url_key: str) -> ChatOllama:
    """One client per (model, base_url) to avoid extra idle sockets (httpx/ollama)."""
    kwargs: dict = {"model": model, "temperature": 0.2}
    if base_url_key:
        kwargs["base_url"] = base_url_key
    return ChatOllama(**kwargs)


def _llm(cfg: Configuration) -> ChatOllama:
    return _llm_cached(cfg.ollama_model, cfg.ollama_base_url or "")


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    p = urlparse(u)
    if not p.netloc:
        return u.lower().rstrip("/")
    netloc = p.netloc.lower()
    path = p.path.rstrip("/") or "/"
    scheme = (p.scheme or "https").lower()
    return urlunparse((scheme, netloc, path, "", "", ""))


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


def extract_json_object(text: str) -> dict:
    raw = text.strip()
    block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if block:
        raw = block.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(raw[start : end + 1])


# ---------------------------------------------------------------------------
# plan_research — break main topic into subtopics
# ---------------------------------------------------------------------------


def plan_research(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    main_topic = state["topic"]
    cap = max(3, min(cfg.max_plan_sections, 8))
    print(f"\n--- Phase: plan_research — breaking topic into ≤{cap} subtopics\n", flush=True)

    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "plan_research"))
    human = HumanMessage(content=P.plan_research_human(lang, main_topic, cap))
    resp = llm.invoke([sys, human])
    text = getattr(resp, "content", str(resp)) or ""

    try:
        data = extract_json_object(text)
        raw_plans = data.get("plans") or []
        plans = [str(p).strip() for p in raw_plans if str(p).strip()]
        plans = plans[:cap]
    except (json.JSONDecodeError, ValueError, TypeError):
        plans = []

    if not plans:
        plans = [main_topic]

    for i, p in enumerate(plans, 1):
        print(f"    plan {i}: {p}", flush=True)

    output_file_path = state.get("output_file_path") or _derive_output_path(main_topic)

    return {
        "main_topic": main_topic,
        "research_plans": plans,
        "current_plan_index": 0,
        "written_sections": [],
        "output_file_path": output_file_path,
    }


# ---------------------------------------------------------------------------
# advance_plan — load next subtopic, reset per-plan state
# ---------------------------------------------------------------------------


def advance_plan(state: SummaryState, runtime: Runtime[Configuration]) -> dict:  # noqa: ARG001
    plans = state.get("research_plans") or []
    idx = int(state.get("current_plan_index", 0))
    subtopic = plans[idx] if idx < len(plans) else state.get("main_topic", state["topic"])
    all_sources = state.get("all_sources") or []
    print(
        f"\n{'='*60}\n"
        f"Plan {idx + 1}/{len(plans)}: {subtopic}\n"
        f"{'='*60}\n",
        flush=True,
    )
    return {
        "topic": subtopic,
        # Offset so this plan's source IDs continue from where previous plans left off
        "source_id_offset": len(all_sources),
        # Reset per-plan state
        "sources": [],
        "search_queries": [],
        "working_summary": "",
        "reflection_text": "",
        "need_more_research": False,
        "loop_count": 0,
        "last_search_preview": "",
    }


# ---------------------------------------------------------------------------
# generate_similar_questions — produce search queries for current subtopic
# ---------------------------------------------------------------------------


def generate_similar_questions(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    topic = state["topic"]
    written_sections = state.get("written_sections") or []
    written_headings = [_extract_section_heading(s) for s in written_sections]

    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "generate_similar_questions"))
    human = HumanMessage(
        content=P.generate_similar_questions_human(
            lang,
            topic,
            state.get("reflection_text", "") or "",
            written_headings,
        )
    )
    resp = llm.invoke([sys, human])
    text = getattr(resp, "content", str(resp)) or ""
    try:
        data = extract_json_object(text)
        raw_list = data.get("similar_questions") or data.get("queries") or []
        queries = [str(q).strip() for q in raw_list if str(q).strip()]
    except (json.JSONDecodeError, ValueError, TypeError):
        queries = [topic]
    if not queries:
        queries = [topic]
    for q in queries:
        print(f"    {q}", flush=True)
    return {"search_queries": queries}


# ---------------------------------------------------------------------------
# web_research — DuckDuckGo searches
# ---------------------------------------------------------------------------


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
    cfg = runtime.context
    queries = state.get("search_queries") or [state["topic"]]
    workers = max(1, min(cfg.search_parallel_workers, len(queries)))
    print("\n--- Phase: web_research\n", flush=True)
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


# ---------------------------------------------------------------------------
# fetch_pages — full-page HTTP fetches
# ---------------------------------------------------------------------------


def fetch_pages(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    sources = state.get("sources") or []
    max_n = max(0, cfg.max_fetch_pages)
    if max_n == 0 or not sources:
        print("\n--- Phase: fetch_pages — skipped (max_fetch_pages=0 or no sources)\n", flush=True)
        return {}

    workers = max(1, min(cfg.fetch_parallel_workers, max_n))
    print("\n--- Phase: fetch_pages\n", flush=True)

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


# ---------------------------------------------------------------------------
# summarize_sources — synthesize collected sources into working summary
# ---------------------------------------------------------------------------


def summarize_sources(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    print("\n--- Phase: summarize_sources — synthesizing from collected sources\n", flush=True)
    sources = state.get("sources") or []
    written_sections = state.get("written_sections") or []
    written_headings = [_extract_section_heading(s) for s in written_sections]

    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "summarize_sources"))
    human = HumanMessage(
        content=P.summarize_sources_human(
            lang,
            state["topic"],
            P.sources_context(sources, lang, fetched_context_chars=cfg.context_chars_per_fetched_source),
            written_headings,
        )
    )
    resp = llm.invoke([sys, human])
    text = getattr(resp, "content", str(resp)) or ""
    return {"working_summary": text.strip()}


# ---------------------------------------------------------------------------
# reflect_on_summary — decide if more research is needed
# ---------------------------------------------------------------------------


def reflect_on_summary(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    print("\n--- Phase: reflect_on_summary\n", flush=True)
    sources = state.get("sources") or []
    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "reflect_on_summary"))
    human = HumanMessage(
        content=P.reflect_on_summary_human(
            lang,
            state["topic"],
            state.get("working_summary", ""),
            [s["id"] for s in sources],
        )
    )
    resp = llm.invoke([sys, human])
    text = getattr(resp, "content", str(resp)) or ""
    try:
        data = extract_json_object(text)
        need_more = bool(data.get("need_more_research"))
        reason = str(data.get("reason", "")).strip()
    except (json.JSONDecodeError, ValueError, TypeError):
        need_more = False
        reason = (
            "JSONの解析に失敗したため終了します"
            if P.normalize_lang(lang) == "ja"
            else "parse_error_defaulting_to_finalize"
        )
    prev = int(state.get("loop_count", 0))
    new_loop = prev + (1 if need_more else 0)
    print(f"    need_more_research={need_more} loop_count->{new_loop} ({reason[:120]})", flush=True)
    return {
        "need_more_research": need_more,
        "reflection_text": reason,
        "loop_count": new_loop,
    }


# ---------------------------------------------------------------------------
# write_section — write one section to the MD file, then flush to disk
# ---------------------------------------------------------------------------


def write_section(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    subtopic = state["topic"]
    main_topic = state.get("main_topic") or subtopic
    sources = state.get("sources") or []
    working = state.get("working_summary", "")
    written_sections = list(state.get("written_sections") or [])
    current_idx = int(state.get("current_plan_index", 0))
    output_file_path = state.get("output_file_path") or _derive_output_path(main_topic)

    print(f"\n--- Phase: write_section — drafting section for: {subtopic[:80]!r}\n", flush=True)

    sources_block = P.sources_context(
        sources,
        lang,
        fetched_context_chars=cfg.context_chars_per_fetched_source,
    )
    prior_md = "\n\n".join(written_sections)
    prior_for_prompt = _truncate_prior_sections(prior_md, _WRITE_SECTION_PRIOR_MAX_CHARS, lang)

    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "write_section"))
    human = HumanMessage(
        content=P.write_section_human(
            lang,
            subtopic,
            main_topic,
            working,
            sources_block,
            prior_for_prompt,
        )
    )
    resp = llm.invoke([sys, human])
    section_body = (getattr(resp, "content", str(resp)) or "").strip()

    # Write section body only — references go in one block at the very end (finalize_report)
    path = Path(output_file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if current_idx == 0:
        # First plan: create file with top-level title
        path.write_text(f"# {main_topic}\n\n{section_body}\n", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n\n{section_body}\n")

    print(f"    written to: {path.resolve()}", flush=True)

    # Accumulate slim source records (no fetched_text) for the final References section
    all_sources = list(state.get("all_sources") or [])
    for s in sources:
        all_sources.append({
            "id": s["id"],
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "snippet": s.get("snippet", ""),
        })

    written_sections.append(section_body)
    return {
        "written_sections": written_sections,
        "current_plan_index": current_idx + 1,
        "all_sources": all_sources,
    }


# ---------------------------------------------------------------------------
# finalize_report — append one unified References section at the bottom
# ---------------------------------------------------------------------------


def finalize_report(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    all_sources = state.get("all_sources") or []
    output_file_path = state.get("output_file_path") or _derive_output_path(
        state.get("main_topic") or state.get("topic", "report")
    )
    print("\n--- Phase: finalize_report — writing unified References section\n", flush=True)

    ref_lines: list[str] = ["", P.references_heading(lang), ""]
    for s in all_sources:
        sid = s["id"]
        title = (s.get("title") or "Untitled").replace("\n", " ")
        url = s.get("url", "")
        snip = (s.get("snippet") or "").replace("\n", " ").strip()
        if snip:
            ref_lines.append(
                f"{sid}. **{title}** — {url}  \n"
                f"   _{snip[:240]}{'…' if len(snip) > 240 else ''}_\n"
            )
        else:
            ref_lines.append(f"{sid}. **{title}** — {url}\n")

    refs_block = "\n".join(ref_lines).rstrip() + "\n"
    path = Path(output_file_path)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n{refs_block}")

    print(f"    references ({len(all_sources)} sources) written to: {path.resolve()}", flush=True)
    return {}
