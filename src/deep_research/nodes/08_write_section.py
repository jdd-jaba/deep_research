"""Write section node: write one section to the MD file, then flush to disk."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.helpers import (
    _WRITE_SECTION_PRIOR_MAX_CHARS,
    _derive_output_path,
    _llm,
    _strip_citations,
    _truncate_prior_sections,
)
from deep_research.state import Configuration, SummaryState


def write_section(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    """Write one comprehensive markdown section and immediately flush to disk.
    
    Uses an LLM to transform the working summary into a well-structured section
    with ## heading, ### subheadings, detailed paragraphs, and [n] citations.
    Citations are isolated per-section (prior section IDs are stripped to prevent
    cross-section leaking). Writes directly to the output .md file.
    
    Args:
        state: Graph state with topic, working_summary, sources, and written_sections
        runtime: Runtime context with model and language configuration
    
    Returns:
        dict: Updated state with:
            - written_sections: List appended with new section markdown
            - current_plan_index: Incremented to move to next plan
            - all_sources: Slim source records accumulated for final References
            - section_sources: Tracks which sources belong to which section heading
    
    Notes:
        - First section creates file with # main_topic title
        - Subsequent sections are appended
        - Prior sections are truncated to 30k chars to fit in context
        - Citations stripped from prior sections to avoid ID conflicts
        - Each section gets unique source IDs continuing from previous plans
    """
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
