"""Generate similar questions node: produce search queries for current subtopic."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.helpers import _extract_section_heading, _llm, extract_json_object
from deep_research.state import Configuration, SummaryState


def generate_similar_questions(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    """Generate a targeted follow-up search query to fill research gaps.
    
    This optional loop node (step 07) is triggered when evaluate_coverage determines
    more research is needed. Uses an LLM to create ONE specific search query that
    directly addresses the gaps identified in reflection_text. Loops back to search_web.
    
    Args:
        state: Graph state with topic, reflection_text, and written_sections
        runtime: Runtime context with model and language configuration
    
    Returns:
        dict: Updated state with:
            - search_queries: List with one new targeted query
    
    Notes:
        - Generates exactly 1 query per iteration (not multiple)
        - Query addresses specific gaps from reflection_text
        - Avoids overlapping with already-written section headings
        - Falls back to topic itself if LLM fails to generate query
    """
    cfg = runtime.context
    lang = cfg.language
    topic = state["topic"]
    written_sections = state.get("written_sections") or []
    written_headings = [_extract_section_heading(s) for s in written_sections]

    main_topic = state.get("main_topic") or topic
    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "generate_similar_questions"))
    human = HumanMessage(
        content=P.generate_similar_questions_human(
            lang,
            topic,
            state.get("reflection_text", "") or "",
            written_headings,
            main_topic=main_topic,
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
