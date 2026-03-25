"""CLI: stream graph execution; the graph writes the Markdown report to disk directly."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from deep_research.graph import build_compiled_graph
from deep_research.prompts import normalize_lang
from deep_research.state import Configuration

# Nodes that output raw JSON — suppress their token stream in the CLI.
_JSON_NODES = {"plan_research", "generate_similar_questions", "reflect_on_summary"}


def _print_graph_step_started(task: dict) -> None:
    """LangGraph `tasks` stream: start payloads have `triggers`; completed ones have `result`."""
    if not isinstance(task, dict):
        return
    if "triggers" not in task or "result" in task:
        return
    name = task.get("name")
    if not name or str(name).startswith("__"):
        return
    print(f"\n[graph] step started: {name}", flush=True)


def _print_message_token(chunk) -> None:
    if chunk is None:
        return
    if (
        isinstance(chunk, tuple)
        and len(chunk) >= 2
        and isinstance(chunk[1], dict)
        and chunk[1].get("langgraph_node") in _JSON_NODES
    ):
        return
    token = chunk[0] if isinstance(chunk, tuple) and len(chunk) >= 1 else chunk
    content = getattr(token, "content", None)
    if content:
        print(content, end="", flush=True)


def run(topic: str, ctx: Configuration) -> str:
    graph = build_compiled_graph()
    print(
        f"\n{'='*60}\nDeep research ({ctx.language}): {topic[:200]!r}\n{'='*60}\n",
        flush=True,
    )

    input_state: dict = {"topic": topic}

    last_values: dict | None = None
    stream = graph.stream(
        input_state,
        stream_mode=["tasks", "updates", "messages", "values"],
        context=ctx,
    )
    for event in stream:
        if isinstance(event, tuple) and len(event) == 2:
            mode, data = event
            if mode == "tasks":
                _print_graph_step_started(data)
            elif mode == "messages":
                _print_message_token(data)
            elif mode == "values" and isinstance(data, dict):
                last_values = data
        elif isinstance(event, dict):
            pass

    if not last_values:
        last_values = graph.invoke(input_state, context=ctx)

    written_path = (last_values or {}).get("output_file_path") or ""
    if written_path:
        print(
            f"\n\n{'='*60}\nReport written to: {Path(written_path).resolve()}\n{'='*60}\n",
            flush=True,
        )
    else:
        print("\nWarning: output_file_path not found in final state.", flush=True)

    return written_path


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Local deep research agent (Ollama + LangGraph).")
    parser.add_argument("topic", help="Research question or topic")
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "deepseek-r1:8b"),
        help="Ollama model name (default: env OLLAMA_MODEL or deepseek-r1:8b)",
    )
    parser.add_argument(
        "--max-loops",
        type=int,
        default=int(os.environ.get("DEEP_RESEARCH_MAX_LOOPS", "3")),
        help="Max extra research rounds per plan after reflection (default: 3)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=int(os.environ.get("DEEP_RESEARCH_MAX_RESULTS", "5")),
        help="Max DuckDuckGo hits per query (default: 5)",
    )
    parser.add_argument(
        "--search-workers",
        type=int,
        default=int(os.environ.get("DEEP_RESEARCH_SEARCH_WORKERS", "4")),
        help="Parallel DuckDuckGo searches per round (default: 4; 1=sequential; env DEEP_RESEARCH_SEARCH_WORKERS)",
    )
    parser.add_argument(
        "--lang",
        choices=("ja", "en"),
        default=normalize_lang(os.environ.get("DEEP_RESEARCH_LANG", "ja")),
        help="Prompt and report language: ja (default) or en (or env DEEP_RESEARCH_LANG)",
    )
    parser.add_argument(
        "--max-plans",
        type=int,
        default=int(os.environ.get("DEEP_RESEARCH_MAX_PLANS", "6")),
        help="Max number of research plan subtopics to generate (default: 6; env DEEP_RESEARCH_MAX_PLANS)",
    )
    _default_fetch = int(os.environ.get("DEEP_RESEARCH_FETCH_PAGES", "8"))
    fetch_grp = parser.add_mutually_exclusive_group()
    fetch_grp.add_argument(
        "--fetch-pages",
        nargs="?",
        const=_default_fetch,
        type=int,
        default=None,
        metavar="N",
        help=(
            "Full-page fetches per research round (default: %d, or DEEP_RESEARCH_FETCH_PAGES). "
            "Use `--fetch-pages` alone for that default, or `--fetch-pages 12` to set N. "
            "See also --no-fetch-pages."
            % _default_fetch
        ),
    )
    fetch_grp.add_argument(
        "--no-fetch-pages",
        action="store_true",
        help="Disable full-page fetch (search snippets only)",
    )
    parser.add_argument(
        "--fetch-workers",
        type=int,
        default=int(os.environ.get("DEEP_RESEARCH_FETCH_WORKERS", "4")),
        help=(
            "Parallel HTTP fetches in fetch_pages (default: 4; 1=sequential; "
            "max 16; env DEEP_RESEARCH_FETCH_WORKERS)"
        ),
    )
    args = parser.parse_args(argv)

    if args.no_fetch_pages:
        max_fetch = 0
    elif args.fetch_pages is not None:
        max_fetch = max(0, args.fetch_pages)
    else:
        max_fetch = max(0, _default_fetch)

    ctx = Configuration(
        ollama_model=args.model,
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL"),
        max_loops=max(1, args.max_loops),
        max_results_per_query=max(1, args.max_results),
        search_parallel_workers=max(1, min(16, args.search_workers)),
        language=args.lang,
        max_plan_sections=max(3, min(8, args.max_plans)),
        max_fetch_pages=max_fetch,
        fetch_parallel_workers=max(1, min(16, args.fetch_workers)),
    )

    try:
        run(args.topic, ctx)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001 — CLI boundary
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
