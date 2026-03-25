"""LangGraph StateGraph definition."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import get_runtime

from deep_research.nodes import (
    advance_plan,
    fetch_pages,
    finalize_report,
    generate_similar_questions,
    plan_research,
    reflect_on_summary,
    summarize_sources,
    web_research,
    write_section,
)
from deep_research.state import Configuration, SummaryState, SummaryStateInput, SummaryStateOutput


def route_research(
    state: SummaryState,
) -> Literal["generate_similar_questions", "write_section"]:
    """After reflect_on_summary: loop for more research or move on to writing."""
    runtime = get_runtime(Configuration)
    ctx = runtime.context
    max_loops = ctx.max_loops if ctx is not None else 3
    if state.get("need_more_research") and int(state.get("loop_count", 0)) < max_loops:
        return "generate_similar_questions"
    return "write_section"


def route_plans(state: SummaryState) -> Literal["advance_plan", "finalize_report"]:
    """After write_section: process next plan, or write the unified References section."""
    plans = state.get("research_plans") or []
    idx = int(state.get("current_plan_index", 0))
    if idx < len(plans):
        return "advance_plan"
    return "finalize_report"


def build_compiled_graph():
    builder = StateGraph(
        state_schema=SummaryState,
        input_schema=SummaryStateInput,
        output_schema=SummaryStateOutput,
        context_schema=Configuration,
    )

    builder.add_node("plan_research", plan_research)
    builder.add_node("advance_plan", advance_plan)
    builder.add_node("generate_similar_questions", generate_similar_questions)
    builder.add_node("web_research", web_research)
    builder.add_node("fetch_pages", fetch_pages)
    builder.add_node("summarize_sources", summarize_sources)
    builder.add_node("reflect_on_summary", reflect_on_summary)
    builder.add_node("write_section", write_section)
    builder.add_node("finalize_report", finalize_report)

    # Initial planning
    builder.add_edge(START, "plan_research")
    builder.add_edge("plan_research", "advance_plan")

    # Per-plan research loop — start with direct web search using the plan topic
    builder.add_edge("advance_plan", "web_research")
    builder.add_edge("generate_similar_questions", "web_research")
    builder.add_edge("web_research", "fetch_pages")
    builder.add_edge("fetch_pages", "summarize_sources")
    builder.add_edge("summarize_sources", "reflect_on_summary")

    # After reflection: more research or write this section
    builder.add_conditional_edges("reflect_on_summary", route_research)

    # After writing: next plan or append unified References and finish
    builder.add_conditional_edges("write_section", route_plans)
    builder.add_edge("finalize_report", END)

    return builder.compile()
