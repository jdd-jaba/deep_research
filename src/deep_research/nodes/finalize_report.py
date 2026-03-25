"""Finalize report node: append one unified References section at the bottom."""

from __future__ import annotations

from pathlib import Path

from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.nodes.utils import _derive_output_path
from deep_research.state import Configuration, SummaryState


def finalize_report(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    output_file_path = state.get("output_file_path") or _derive_output_path(
        state.get("main_topic") or state.get("topic", "report")
    )
    section_sources = state.get("section_sources") or []
    all_sources = state.get("all_sources") or []
    print("\n--- Phase: finalize_report — writing grouped References section\n", flush=True)

    top_heading = P.references_heading(lang)  # "## 参考文献" or "## References"
    lines: list[str] = [f"\n---\n\n{top_heading}\n"]

    for entry in section_sources:
        sources = entry.get("sources") or []
        if not sources:
            continue
        for s in sources:
            sid = s["id"]
            title = (s.get("title") or "Untitled").replace("\n", " ")
            url = s.get("url", "")
            snip = (s.get("snippet") or "").replace("\n", " ").strip()
            short_snip = snip[:200] + ("…" if len(snip) > 200 else "")
            if short_snip:
                lines.append(f"{sid}. **{title}** — {url}  \n   _{short_snip}_\n")
            else:
                lines.append(f"{sid}. **{title}** — {url}\n")

    path = Path(output_file_path)
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(
        f"    grouped references ({len(all_sources)} sources, {len(section_sources)} sections) "
        f"written to: {path.resolve()}\n",
        flush=True,
    )
    return {}
