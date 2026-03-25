"""Summarize sources node: synthesize collected sources into working summary."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.helpers import _extract_section_heading, _llm
from deep_research.state import Configuration, SummaryState


def summarize_sources(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    """Synthesize collected sources into a dense factual working summary.
    
    Uses an LLM to analyze all sources (snippets + fetched pages) and create a
    structured summary focused on the current subtopic. Avoids repeating content
    from already-written sections. This summary feeds into the final section writing.
    
    Args:
        state: Graph state with sources and topic
        runtime: Runtime context with model and language configuration
    
    Returns:
        dict: Updated state with:
            - working_summary: Dense markdown summary with ### headings and [n] citations
    
    Notes:
        - Citations use source IDs: [1], [2], etc.
        - Avoids content overlap with written_sections
        - Focuses on NEW information specific to current subtopic
        - Includes uncertainty flags where sources conflict
    """
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
