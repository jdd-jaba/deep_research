"""Plan research node: break main topic into subtopics."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.nodes.utils import _derive_output_path, _llm, extract_json_object
from deep_research.state import Configuration, SummaryState


def plan_research(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    main_topic = state["topic"]
    cap = max(5, min(cfg.max_plan_sections, 8))
    print(f"\n--- Phase: plan_research — breaking topic into ≤{cap} subtopics\n", flush=True)

    llm = _llm(cfg)
    sys = SystemMessage(content=P.system_prompt(lang, "plan_research"))
    human = HumanMessage(content=P.plan_research_human(lang, main_topic, cap))
    resp = llm.invoke([sys, human])
    text = getattr(resp, "content", str(resp)) or ""

    try:
        data = extract_json_object(text)
        raw_plans = data.get("plans") or []
        plans = [str(p).strip() for p in raw_plans if str(p).strip()]
        plans = plans[:cap]
    except (json.JSONDecodeError, ValueError, TypeError):
        plans = []

    if not plans:
        plans = [main_topic]

    for i, p in enumerate(plans, 1):
        print(f"    plan {i}: {p}", flush=True)

    output_file_path = state.get("output_file_path") or _derive_output_path(main_topic)

    return {
        "main_topic": main_topic,
        "research_plans": plans,
        "current_plan_index": 0,
        "written_sections": [],
        "section_sources": [],
        "output_file_path": output_file_path,
    }
