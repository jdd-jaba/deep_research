"""Advance plan node: load next subtopic, reset per-plan state."""

from __future__ import annotations

from langgraph.runtime import Runtime

from deep_research.state import Configuration, SummaryState


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
