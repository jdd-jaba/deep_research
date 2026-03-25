"""Write section node: write one section to the MD file, then flush to disk."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.nodes.utils import (
    _WRITE_SECTION_PRIOR_MAX_CHARS,
    _derive_output_path,
    _llm,
    _strip_citations,
    _truncate_prior_sections,
)
from deep_research.state import Configuration, SummaryState


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
    # Strip citation IDs from prior sections so the LLM cannot borrow them
    # into the current section's citations (cross-section leaking).
    prior_md = "\n\n".join(_strip_citations(s) for s in written_sections)
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

    path = Path(output_file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if current_idx == 0:
        # First plan: create file with top-level title
        path.write_text(f"# {main_topic}\n\n{section_body}\n", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n\n{section_body}\n")

    print(f"    written to: {path.resolve()}", flush=True)

    # Accumulate slim source records for offset tracking and grouped references
    slim_sources = [
        {
            "id": s["id"],
            "title": s.get("title", ""),
            "url": s.get("url", ""),
            "snippet": s.get("snippet", ""),
        }
        for s in sources
    ]
    all_sources = list(state.get("all_sources") or [])
    all_sources.extend(slim_sources)

    # Track which sources belong to this section for the grouped References block
    section_sources = list(state.get("section_sources") or [])
    section_sources.append({"heading": subtopic, "sources": slim_sources})

    written_sections.append(section_body)
    return {
        "written_sections": written_sections,
        "current_plan_index": current_idx + 1,
        "all_sources": all_sources,
        "section_sources": section_sources,
    }
