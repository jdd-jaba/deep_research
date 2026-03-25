"""Advance plan node: load next subtopic, reset per-plan state."""

from __future__ import annotations

from langgraph.runtime import Runtime

from deep_research.state import Configuration, SummaryState


def advance_plan(state: SummaryState, runtime: Runtime[Configuration]) -> dict:  # noqa: ARG001
    """Load the next subtopic and reset per-plan state for a fresh research cycle.
    
    This node is called after completing a subtopic (or at the start after planning).
    It loads the next subtopic from research_plans, displays progress, and resets
    all per-plan variables (sources, queries, summary, etc.) while maintaining
    global state like all_sources for continuous source ID numbering.
    
    Args:
        state: Graph state with research_plans and current_plan_index
        runtime: Runtime context (not used, but required by LangGraph signature)
    
    Returns:
        dict: Updated state with:
            - topic: Current subtopic to research
            - source_id_offset: Continuation of source IDs from previous plans
            - sources: Empty list for new sources
            - search_queries: Empty list for new queries
            - working_summary: Reset to empty
            - reflection_text: Reset to empty
            - need_more_research: Reset to False
            - loop_count: Reset to 0
            - last_search_preview: Reset to empty
    """
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
