"""LangGraph StateGraph definition."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import get_runtime

from deep_research.nodes import (
    fetch_pages,
    generate_similar_questions,
    plan_outline,
    reflect_on_summary,
    summarize_sources,
    web_research,
    write_report,
)
from deep_research.state import Configuration, SummaryState, SummaryStateInput, SummaryStateOutput


def route_research(state: SummaryState) -> Literal["generate_similar_questions", "plan_outline"]:
    runtime = get_runtime(Configuration)
    ctx = runtime.context
    max_loops = ctx.max_loops if ctx is not None else 3
    if state.get("need_more_research") and int(state.get("loop_count", 0)) < max_loops:
        return "generate_similar_questions"
    return "plan_outline"


def build_compiled_graph():
    builder = StateGraph(
        state_schema=SummaryState,
        input_schema=SummaryStateInput,
        output_schema=SummaryStateOutput,
        context_schema=Configuration,
    )
    builder.add_node("generate_similar_questions", generate_similar_questions)
    builder.add_node("web_research", web_research)
    builder.add_node("fetch_pages", fetch_pages)
    builder.add_node("summarize_sources", summarize_sources)
    builder.add_node("reflect_on_summary", reflect_on_summary)
    builder.add_node("plan_outline", plan_outline)
    builder.add_node("write_report", write_report)

    builder.add_edge(START, "generate_similar_questions")
    builder.add_edge("generate_similar_questions", "web_research")
    builder.add_edge("web_research", "fetch_pages")
    builder.add_edge("fetch_pages", "summarize_sources")
    builder.add_edge("summarize_sources", "reflect_on_summary")
    builder.add_conditional_edges("reflect_on_summary", route_research)
    builder.add_edge("plan_outline", "write_report")
    builder.add_edge("write_report", END)
    return builder.compile()
