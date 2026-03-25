"""Reflect on summary node: decide if more research is needed."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from deep_research import prompts as P
from deep_research.nodes.utils import _llm, extract_json_object
from deep_research.state import Configuration, SummaryState


def reflect_on_summary(state: SummaryState, runtime: Runtime[Configuration]) -> dict:
    cfg = runtime.context
    lang = cfg.language
    print("\n--- Phase: reflect_on_summary\n", flush=True)
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
