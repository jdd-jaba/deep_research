"""LangGraph node implementations."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from ddgs import DDGS
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.fetching import fetch_page_text
from deep_research.state import Configuration, SummaryState


# Cap prior-section text in write_report prompts so context stays bounded on long reports.
_WRITE_REPORT_PRIOR_SECTIONS_MAX_CHARS = 40_000


def _truncate_prior_sections_for_prompt(text: str, max_chars: int, lang: str) -> str:
    if len(text) <= max_chars:
        return text
    note = (
        "…（前の節の一部は長さのため省略）\n\n"
        if P.normalize_lang(lang) == "ja"
        else "…(earlier section text truncated for length)\n\n"
    )
    return note + text[-max_chars:]


def _strip_model_reference_sections(body: str) -> str:
    headings = ("References", "Sources", "参考文献", "参照")
    out = body
    for h in headings:
        out = re.sub(rf"\n##\s*{re.escape(h)}\s*\n[\s\S]*$", "", out, flags=re.IGNORECASE)
    return out


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


def merge_sources(existing: list[dict] | None, new_items: list[dict]) -> list[dict]:
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
    for i, row in enumerate(out, start=1):
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


def generate_similar_questions(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    topic = state["topic"]
    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "generate_similar_questions"))
    human = HumanMessage(
        content=P.generate_similar_questions_human(
            lang,
            topic,
            state.get("reflection_text", "") or "",
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

    merged = merge_sources(state.get("sources"), new_items)
    preview = []
    for s in merged[: min(10, len(merged))]:
        preview.append(f"    {s.get('url', '')}")
    print("\n    top results:\n" + "\n".join(preview) if preview else "\n    (no results)", flush=True)
    return {
        "sources": merged,
        "last_search_preview": "\n".join(preview),
    }


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


def summarize_sources(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    print("\n--- Phase: summarize_sources — synthesizing from collected sources\n", flush=True)
    sources = state.get("sources") or []
    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "summarize_sources"))
    human = HumanMessage(
        content=P.summarize_sources_human(
            lang,
            state["topic"],
            P.sources_context(sources, lang, fetched_context_chars=cfg.context_chars_per_fetched_source),
        )
    )
    resp = llm.invoke([sys, human])
    text = getattr(resp, "content", str(resp)) or ""
    return {"working_summary": text.strip()}


def _default_outline(lang: str, topic: str) -> tuple[str, list[dict]]:
    """Fallback outline when JSON planning fails."""
    if P.normalize_lang(lang) == "ja":
        title = f"調査レポート: {topic[:120].strip()}"
        sections: list[dict] = [
            {"heading": "エグゼクティブサマリー", "focus": "結論、主要な発見、読者が取るべき行動や理解の要点"},
            {"heading": "背景とスコープ", "focus": "論点の文脈、対象範囲、用語の定義"},
            {"heading": "主要な事実と要件", "focus": "情報源に基づく中核事実、条件、数値・手続きの要点"},
            {"heading": "手続き・プロセス・タイムライン", "focus": "該当する場合のステップ、順序、目安時期"},
            {"heading": "例外・特例・よくある論点", "focus": "情報源で触れられる例外、注意点"},
            {"heading": "不確実性・限界・情報の抜け", "focus": "矛盾、薄い根拠、追加調査が必要な点"},
        ]
    else:
        title = f"Research report: {topic[:120].strip()}"
        sections = [
            {
                "heading": "Executive summary",
                "focus": "Key conclusions, main findings, and what the reader should take away",
            },
            {"heading": "Background and scope", "focus": "Context, definitions, and boundaries of the question"},
            {
                "heading": "Key facts and requirements",
                "focus": "Core claims grounded in sources, conditions, figures, and procedural essentials",
            },
            {
                "heading": "Process, steps, and timeline",
                "focus": "If applicable: ordered steps, sequencing, and indicative timing",
            },
            {
                "heading": "Exceptions, edge cases, and common points of confusion",
                "focus": "What sources say about exceptions and caveats",
            },
            {
                "heading": "Uncertainties, limitations, and gaps",
                "focus": "Conflicts between sources, weak evidence, and what is still unknown",
            },
        ]
    return title, sections


def plan_outline(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    print("\n--- Phase: plan_outline — structuring long-form report\n", flush=True)
    topic = state["topic"]
    sources = state.get("sources") or []
    working = state.get("working_summary", "")
    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "plan_outline"))
    human = HumanMessage(
        content=P.plan_outline_human(
            lang,
            topic,
            working,
            P.sources_context(sources, lang, fetched_context_chars=cfg.context_chars_per_fetched_source),
        )
    )
    resp = llm.invoke([sys, human])
    text = getattr(resp, "content", str(resp)) or ""
    cap = max(4, min(cfg.max_report_sections, 12))
    try:
        data = extract_json_object(text)
        report_title = str(data.get("report_title") or topic).strip() or topic
        raw = data.get("sections") or []
        outline: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            h = str(item.get("heading", "")).strip()
            if not h:
                continue
            f = str(item.get("focus", "")).strip() or h
            outline.append({"heading": h, "focus": f})
        outline = outline[:cap]
    except (json.JSONDecodeError, ValueError, TypeError):
        report_title, outline = _default_outline(lang, topic)
        outline = outline[:cap]

    if len(outline) < 3:
        report_title, outline = _default_outline(lang, topic)
        outline = outline[:cap]

    print(f"    {len(outline)} sections planned: {', '.join(s['heading'][:40] for s in outline[:5])}…", flush=True)
    return {"report_title": report_title, "report_outline": outline}


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


def write_report(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    print("\n--- Phase: write_report — drafting sections + references\n", flush=True)
    sources = state.get("sources") or []
    sources_block = P.sources_context(
        sources,
        lang,
        fetched_context_chars=cfg.context_chars_per_fetched_source,
    )
    working = state.get("working_summary", "")
    outline = state.get("report_outline") or []
    report_title = (state.get("report_title") or state["topic"]).strip() or state["topic"]
    topic = state["topic"]

    if not outline:
        _, outline = _default_outline(lang, topic)
        outline = outline[: cfg.max_report_sections]

    all_headings = [str(s.get("heading", "")).strip() for s in outline if s.get("heading")]
    llm = _llm(cfg)
    sys_sec = P.system_prompt(lang, "write_report_section")
    parts: list[str] = [f"# {report_title}\n"]
    prior_sections_md = ""

    for i, sec in enumerate(outline):
        heading = str(sec.get("heading", "")).strip()
        focus = str(sec.get("focus", "")).strip() or heading
        if not heading:
            continue
        print(f"    section {i + 1}/{len(outline)}: {heading[:70]!r}", flush=True)
        others = [h for j, h in enumerate(all_headings) if h != heading]
        prior_for_prompt = _truncate_prior_sections_for_prompt(
            prior_sections_md,
            _WRITE_REPORT_PRIOR_SECTIONS_MAX_CHARS,
            lang,
        )
        human = HumanMessage(
            content=P.write_report_section_human(
                lang,
                topic,
                working,
                sources_block,
                heading,
                focus,
                others,
                prior_for_prompt,
            )
        )
        resp = llm.invoke([SystemMessage(content=sys_sec), human])
        chunk = (getattr(resp, "content", str(resp)) or "").strip()
        chunk = _strip_model_reference_sections(chunk)
        if chunk:
            parts.append(chunk)
            prior_sections_md = chunk if not prior_sections_md else f"{prior_sections_md}\n\n{chunk}"

    body = "\n\n".join(parts).strip()
    ref_lines = ["", P.references_heading(lang), ""]
    for s in sources:
        sid = s["id"]
        title = s.get("title", "Untitled").replace("\n", " ")
        url = s.get("url", "")
        snip = (s.get("snippet") or "").replace("\n", " ").strip()
        if snip:
            ref_lines.append(f"{sid}. **{title}** — {url}  \n   _{snip[:240]}{'…' if len(snip) > 240 else ''}_\n")
        else:
            ref_lines.append(f"{sid}. **{title}** — {url}\n")

    final_document = body.rstrip() + "\n" + "\n".join(ref_lines).rstrip() + "\n"
    return {"final_document": final_document}
