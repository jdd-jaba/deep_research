"""Summarize sources node: synthesize collected sources into working summary."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.nodes.utils import _extract_section_heading, _llm
from deep_research.state import Configuration, SummaryState


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
