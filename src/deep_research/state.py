"""Graph state, I/O schemas, and run configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


@dataclass
class Configuration:
    """Static context passed to each graph run (`context=...` on invoke/stream)."""

    ollama_model: str = "llama3.2"
    ollama_base_url: str | None = None
    max_loops: int = 3
    max_results_per_query: int = 5
    search_parallel_workers: int = 4  # DuckDuckGo queries in parallel (1 = sequential)
    language: str = "ja"  # prompt locale: "ja" (default) or "en"
    max_report_sections: int = 7  # cap outline sections for multi-pass report
    max_fetch_pages: int = 12  # full-page fetches after search (0 = off)
    fetch_parallel_workers: int = 4  # concurrent HTTP fetches (1 = sequential)
    fetch_timeout: float = 20.0
    max_fetch_response_bytes: int = 2_000_000
    max_chars_per_fetched_page: int = 12_000
    context_chars_per_fetched_source: int = 6_000  # cap in LLM prompt per source


class SummaryStateInput(TypedDict):
    topic: str


class SummaryStateOutput(TypedDict):
    final_document: str


class SummaryState(TypedDict, total=False):
    """Full graph state."""

    topic: str
    search_queries: list[str]
    sources: list[dict]
    working_summary: str
    reflection_text: str
    need_more_research: bool
    loop_count: int
    final_document: str
    last_search_preview: str
    report_title: str
    report_outline: list[dict]
