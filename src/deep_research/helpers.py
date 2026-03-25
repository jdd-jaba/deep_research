"""Helper functions and utilities for deep research nodes."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from urllib.parse import urlparse, urlunparse

from langchain_ollama import ChatOllama

from deep_research import prompts as P
from deep_research.state import Configuration

# Constants
_WRITE_SECTION_PRIOR_MAX_CHARS = 30_000


# ---------------------------------------------------------------------------
# LLM Client Management
# ---------------------------------------------------------------------------


@lru_cache(maxsize=16)
def _llm_cached(model: str, base_url_key: str) -> ChatOllama:
    """One client per (model, base_url) to avoid extra idle sockets (httpx/ollama)."""
    kwargs: dict = {"model": model, "temperature": 0.2}
    if base_url_key:
        kwargs["base_url"] = base_url_key
    return ChatOllama(**kwargs)


def _llm(cfg: Configuration) -> ChatOllama:
    return _llm_cached(cfg.ollama_model, cfg.ollama_base_url or "")


# ---------------------------------------------------------------------------
# Text Processing Utilities
# ---------------------------------------------------------------------------


def _truncate_prior_sections(text: str, max_chars: int, lang: str) -> str:
    if len(text) <= max_chars:
        return text
    note = (
        "…（前のセクションの一部は長さのため省略）\n\n"
        if P.normalize_lang(lang) == "ja"
        else "…(earlier section text truncated for length)\n\n"
    )
    return note + text[-max_chars:]


def _extract_section_heading(section_md: str) -> str:
    """Return the ## heading line from a written section, or the first 80 chars."""
    for line in section_md.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## "):
            return stripped
    return section_md[:80].strip()


def _strip_citations(text: str) -> str:
    """Remove inline [number] citations from prior-section text.

    Prevents the LLM from borrowing citation IDs that belong to earlier sections
    into the current section, which would create cross-section citation leaking.
    """
    return re.sub(r"\[\d+\]", "", text)


# ---------------------------------------------------------------------------
# URL Utilities
# ---------------------------------------------------------------------------


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    p = urlparse(u)
    if not p.netloc:
        return u.lower().rstrip("/")
    netloc = p.netloc.lower()
    path = p.path.rstrip("/") or "/"
    scheme = (p.scheme or "https").lower()
    return urlunparse((scheme, netloc, path, "", "", ""))


def _derive_output_path(main_topic: str) -> str:
    sanitized = re.sub(r"[^\w\s-]", "", main_topic).strip()
    sanitized = re.sub(r"\s+", "_", sanitized)[:60]
    return f"report_{sanitized}.md"


# ---------------------------------------------------------------------------
# Parsing & Validation
# ---------------------------------------------------------------------------


def extract_json_object(text: str) -> dict:
    raw = text.strip()
    block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if block:
        raw = block.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    return json.loads(raw[start : end + 1])


def _is_relevant(item: dict, topic: str) -> bool:
    """Return True if the search result has meaningful overlap with the topic.

    Uses bigram matching for CJK text and word matching for Latin text.
    This catches clearly unrelated pages (ads, missing persons, wrong country, etc.)
    while keeping a low false-negative rate.
    """
    text = (item.get("title", "") + " " + item.get("snippet", ""))
    topic_clean = topic.strip()

    # Word-level check — works for English / romaji portions
    words = [w for w in topic_clean.lower().split() if len(w) > 2]
    if words and any(w in text.lower() for w in words):
        return True

    # Bigram check — works for Japanese/CJK where words are not space-delimited
    bigrams = [
        topic_clean[i : i + 2]
        for i in range(len(topic_clean) - 1)
        if not topic_clean[i].isspace() and not topic_clean[i + 1].isspace()
    ]
    if bigrams:
        matches = sum(1 for bg in bigrams if bg in text)
        return matches >= max(1, len(bigrams) // 4)

    return True  # no criteria to filter on — keep


# ---------------------------------------------------------------------------
# Source Management
# ---------------------------------------------------------------------------


def merge_sources(
    existing: list[dict] | None,
    new_items: list[dict],
    start_id: int = 1,
) -> list[dict]:
    existing = existing or []
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for s in existing:
        url = (s.get("url") or "").strip()
        k = normalize_url(url)
        if not k:
            continue
        if k not in by_key:
            by_key[k] = {
                "id": 0,
                "title": s.get("title", ""),
                "url": url,
                "snippet": (s.get("snippet") or "")[:800],
                "from_query": s.get("from_query", ""),
                "fetched_text": s.get("fetched_text"),
                "fetch_error": s.get("fetch_error"),
                "page_fetch_done": s.get("page_fetch_done", False),
            }
            order.append(k)
    for s in new_items:
        url = (s.get("url") or "").strip()
        k = normalize_url(url)
        if not k:
            continue
        if k not in by_key:
            by_key[k] = {
                "id": 0,
                "title": s.get("title", ""),
                "url": url,
                "snippet": (s.get("snippet") or "")[:800],
                "from_query": s.get("from_query", ""),
                "fetched_text": s.get("fetched_text"),
                "fetch_error": s.get("fetch_error"),
                "page_fetch_done": s.get("page_fetch_done", False),
            }
            order.append(k)
    out = [by_key[k] for k in order]
    for i, row in enumerate(out, start=start_id):
        row["id"] = i
    return out
