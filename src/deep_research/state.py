"""Graph state, I/O schemas, and run configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypedDict


@dataclass
class Configuration:
    """Static context passed to each graph run (`context=...` on invoke/stream)."""

    ollama_model: str = "llama3.2"
    ollama_base_url: str | None = None
    max_loops: int = 3
    max_results_per_query: int = 5
    search_parallel_workers: int = 4  # DuckDuckGo queries in parallel (1 = sequential)
    language: str = "ja"  # prompt locale: "ja" (default) or "en"
    max_plan_sections: int = 6  # number of subtopics plan_research generates (4–8)
    max_fetch_pages: int = 12  # full-page fetches after search (0 = off)
    fetch_parallel_workers: int = 4  # concurrent HTTP fetches (1 = sequential)
    fetch_timeout: float = 20.0
    max_fetch_response_bytes: int = 2_000_000
    max_chars_per_fetched_page: int = 12_000
    context_chars_per_fetched_source: int = 6_000  # cap in LLM prompt per source


class SummaryStateInput(TypedDict):
    topic: str
    output_file_path: NotRequired[str]  # optional override; derived from topic if omitted


class SummaryStateOutput(TypedDict):
    output_file_path: str


class SummaryState(TypedDict, total=False):
    """Full graph state."""

    # Original user topic — constant throughout the run
    main_topic: str
    # Current subtopic — set by advance_plan before each research loop
    topic: str

    # Research plan (list of subtopic strings, produced by plan_research)
    research_plans: list[str]
    current_plan_index: int  # index into research_plans; incremented by write_section

    # Accumulated written section markdown (for anti-repetition context)
    written_sections: list[str]

    # Output file path (derived from topic or provided by caller)
    output_file_path: str

    # Global source accumulator — slim records (id, title, url, snippet) across all plans
    all_sources: list[dict]
    # Per-section source accumulator for grouped References block at the end of the report.
    # Each entry: {"heading": str, "sources": list[dict]}
    section_sources: list[dict]
    # Number of sources collected before the current plan; used to offset source IDs
    source_id_offset: int

    # Per-plan state — reset by advance_plan on each iteration
    search_queries: list[str]
    sources: list[dict]
    working_summary: str
    reflection_text: str
    need_more_research: bool
    loop_count: int
    last_search_preview: str
