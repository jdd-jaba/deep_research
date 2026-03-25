"""Reflect on summary node: decide if more research is needed."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.helpers import _llm, extract_json_object
from deep_research.state import Configuration, SummaryState


def reflect_on_summary(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    """Evaluate research coverage and decide if more searches are needed.
    
    Uses an LLM to review the working summary and determine if important aspects
    of the topic are still missing or if contradictions need resolution. Returns
    a boolean decision and reason. This drives the conditional loop back to
    generate_similar_question_if_necessary or forward to write_section.
    
    Args:
        state: Graph state with topic, working_summary, and sources
        runtime: Runtime context with model configuration
    
    Returns:
        dict: Updated state with:
            - need_more_research: Boolean (True = loop again, False = proceed to writing)
            - reflection_text: Short explanation of decision
            - loop_count: Incremented if need_more_research=True
    
    Notes:
        - Limited by max_loops configuration (default 3) to prevent infinite loops
        - Looks for gaps in coverage, unresolved contradictions, thin evidence
        - Falls back to False on JSON parse errors to avoid getting stuck
    """
    cfg = runtime.context
    lang = cfg.language
    print("\n--- Phase: evaluate_coverage\n", flush=True)
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
