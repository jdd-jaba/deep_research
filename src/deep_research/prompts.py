"""LLM system prompts and human-message templates for graph nodes."""

from __future__ import annotations

from typing import Literal

Lang = Literal["ja", "en"]


def normalize_lang(code: str | None) -> Lang:
    c = (code or "ja").strip().lower()
    if c in ("en", "english"):
        return "en"
    return "ja"


_SYSTEM: dict[Lang, dict[str, str]] = {
    "en": {
        "generate_similar_questions": (
            "You generate similar search questions for web research. Reply with one JSON object only, "
            "no markdown fences, shape:\n"
            '{"similar_questions": ["...", "..."]}\n'
            "Include 3 to 6 diverse, concrete questions/phrases that would make good search engine queries "
            "and together cover the user's topic from different angles. Write each string in English. "
            "No other keys, no prose outside JSON."
        ),
        "summarize_sources": (
            "You are a research analyst. Write a dense factual synthesis of the sources. "
            "Use inline numeric citations like [1], [2] only for source ids listed below — "
            "never invent ids. If information is missing, say so. Use Markdown paragraphs and ### headings. "
            "Write in English."
        ),
        "reflect_on_summary": (
            "You review research coverage. Reply with one JSON object only, no markdown fences, shape:\n"
            '{"need_more_research": true|false, "reason": "short explanation"}\n'
            "Set need_more_research true only if important aspects of the topic are still unsupported "
            "by the sources or contradictions need resolution. Use English for reason."
        ),
        "plan_outline": (
            "You plan a long-form research report. Reply with one JSON object only, no markdown fences, shape:\n"
            '{"report_title": "Concise title", "sections": [{"heading": "Short section title", "focus": "What this section must cover"}]}\n'
            "Include between 6 and 8 sections for depth. First section should be an executive summary / overview. "
            "Include sections for background, key facts or requirements, process or timeline where relevant, "
            "risks/limitations/uncertainties, and notable gaps. Headings must be unique. Write in English."
        ),
        "write_report_section": (
            "You write ONE section of a deep research report in Markdown. Requirements:\n"
            "- First line must be exactly: ### <section heading> (use the heading you are given)\n"
            "- Then write several substantial paragraphs (be detailed, not bullet-only unless a table helps)\n"
            "- Use inline [n] citations only for source ids from the provided list; never invent ids\n"
            "- Do NOT add a top-level # title, do NOT add other ### sections, do NOT add References/Sources\n"
            "- If \"Already written\" sections are provided, do NOT repeat, re-introduce, or re-summarize that text; "
            "only add content for THIS section’s focus\n"
            "- Flag uncertainty where sources conflict or are thin\n"
            "- Write in English."
        ),
    },
    "ja": {
        "generate_similar_questions": (
            "あなたはウェブ検索用の「類似の調査質問」を生成します。マークダウンのコードブロックは使わず、JSONオブジェクトのみを出力してください。\n"
            '形式: {"similar_questions": ["...", "..."]}\n'
            "ユーザーのトピックを異なる角度からカバーする、具体的で検索に向いた質問文を 3〜6 個含めてください。"
            "言語はユーザーの質問と揃えてください（日本語の質問なら日本語の文）。JSON 以外の文章は書かないでください。"
        ),
        "summarize_sources": (
            "あなたはリサーチアナリストです。与えられた情報源に基づき、事実を高密度に要約してください。"
            "文中の引用は [1]、[2] のように、下に示すソース id のみを使ってください。id を捏造しないでください。"
            "情報が不足している場合はその旨を書いてください。Markdown の段落と ### 見出しを使ってください。本文は日本語で書いてください。"
        ),
        "reflect_on_summary": (
            "調査の網羅性をレビューします。マークダウンのコードブロックは使わず、JSONオブジェクトのみを出力してください。形式:\n"
            '{"need_more_research": true|false, "reason": "簡潔な説明"}\n'
            "トピックの重要な側面がまだ情報源で裏付けられていない、または矛盾の解消が必要な場合のみ need_more_research を true にしてください。"
            "reason は日本語で書いてください。"
        ),
        "plan_outline": (
            "長文の調査レポートの構成を計画します。マークダウンのコードブロックは使わず、JSONオブジェクトのみを出力してください。形式:\n"
            '{"report_title": "簡潔なレポート題名", "sections": [{"heading": "節の短い見出し", "focus": "この節で必ず扱う内容"}]}\n'
            "6〜8 個の節を含め、深掘りした構成にしてください。最初の節はエグゼクティブサマリー／概要。"
            "背景、主要な事実・要件、手続き・スケジュール（該当時）、リスク・限界・不確実性、情報の抜けを扱う節を含めてください。"
            "見出しは重複させない。日本語で書く。"
        ),
        "write_report_section": (
            "調査レポートの「1つの節」だけを Markdown で書きます。要件:\n"
            "- 1 行目は必ず次の形式: ### （指定された見出し）\n"
            "- その後、十分な量の段落で詳述する（箇条書きだけにしない。比較表があるとよい場合は表を使ってよい）\n"
            "- 引用は [n] 形式のみ。与えられたソース id のみ。捏造しない\n"
            "- トップレベルの # タイトルは付けない。他の ### 見出しは増やさない。参考文献セクションは付けない\n"
            "- 「すでに書いた節」が提示されている場合は、その内容の繰り返し・再説明・要約し直しをしない。"
            "この節の焦点に沿った新しい内容だけを書く\n"
            "- 情報源が矛盾・薄弱な点は不確実性として明記\n"
            "- 本文は日本語で書く"
        ),
    },
}


def system_prompt(lang: str | None, key: str) -> str:
    L = normalize_lang(lang)
    return _SYSTEM[L][key]


def references_heading(lang: str | None) -> str:
    return "## 参考文献" if normalize_lang(lang) == "ja" else "## References"


def empty_sources_note(lang: str | None) -> str:
    return "（情報源はまだありません）" if normalize_lang(lang) == "ja" else "(no sources yet)"


def generate_similar_questions_human(lang: str | None, topic: str, reflection_text: str) -> str:
    if normalize_lang(lang) == "ja":
        none_ = "（なし）"
        return (
            f"元の調査トピック / 質問:\n{topic}\n\n"
            "類似の検索質問を生成する際、前回のリフレクションの不足点を踏まえてください:\n"
            f"{reflection_text or none_}"
        )
    return (
        f"Original research topic / question:\n{topic}\n\n"
        "When generating similar search questions, incorporate gaps from the prior reflection:\n"
        f"{reflection_text or '(none)'}"
    )


def summarize_sources_human(lang: str | None, topic: str, sources_block: str) -> str:
    if normalize_lang(lang) == "ja":
        return (
            f"トピック:\n{topic}\n\n"
            f"情報源（次の [n] の id のみ使用）:\n{sources_block}\n\n"
            "作業用の要約を更新してください。"
        )
    return (
        f"Topic:\n{topic}\n\n"
        f"Sources (use only these [n] ids):\n{sources_block}\n\n"
        "Produce an updated working summary."
    )


def reflect_on_summary_human(lang: str | None, topic: str, working_summary: str, source_ids: list[int]) -> str:
    if normalize_lang(lang) == "ja":
        return (
            f"トピック:\n{topic}\n\n"
            f"作業用要約:\n{working_summary}\n\n"
            f"利用可能なソース id: {source_ids}\n"
        )
    return (
        f"Topic:\n{topic}\n\n"
        f"Working summary:\n{working_summary}\n\n"
        f"Source ids available: {source_ids}\n"
    )


def plan_outline_human(lang: str | None, topic: str, working_summary: str, sources_block: str) -> str:
    if normalize_lang(lang) == "ja":
        return (
            f"トピック:\n{topic}\n\n"
            f"作業用要約:\n{working_summary}\n\n"
            f"情報源一覧:\n{sources_block}\n\n"
            "上記に基づき、レポートの見出しと各節の焦点を JSON で返してください。"
        )
    return (
        f"Topic:\n{topic}\n\n"
        f"Working summary:\n{working_summary}\n\n"
        f"Sources:\n{sources_block}\n\n"
        "Return the report outline JSON as specified."
    )


def write_report_section_human(
    lang: str | None,
    topic: str,
    working_summary: str,
    sources_block: str,
    section_heading: str,
    section_focus: str,
    other_headings: list[str],
    prior_sections_markdown: str,
) -> str:
    others = ", ".join(other_headings) if other_headings else ("（なし）" if normalize_lang(lang) == "ja" else "(none)")
    prior = (prior_sections_markdown or "").strip()
    if normalize_lang(lang) == "ja":
        prior_block = (
            prior
            if prior
            else "（この節より前にレポート本文はまだありません。繰り返し不要の対象なし。）"
        )
        return (
            f"トピック:\n{topic}\n\n"
            f"作業用要約（全体の文脈）:\n{working_summary}\n\n"
            "【すでに書いた節】（繰り返さない。以下は参照のみ）\n"
            f"{prior_block}\n\n"
            f"この節の見出し（1 行目にそのまま使用）:\n{section_heading}\n\n"
            f"この節で扱う内容:\n{section_focus}\n\n"
            f"他の節の見出し（重複を避ける）:\n{others}\n\n"
            f"情報源:\n{sources_block}\n"
        )
    prior_block = prior if prior else "(No prior sections yet — nothing to avoid repeating.)"
    return (
        f"Topic:\n{topic}\n\n"
        f"Working summary (context for whole report):\n{working_summary}\n\n"
        "Already written (reference only; do not repeat — write only the new section below):\n"
        f"{prior_block}\n\n"
        f"Section heading (use as first line ### exactly):\n{section_heading}\n\n"
        f"What this section must cover:\n{section_focus}\n\n"
        f"Other section headings (avoid repeating their content):\n{others}\n\n"
        f"Sources:\n{sources_block}\n"
    )


def sources_context(
    sources: list[dict],
    lang: str | None = None,
    *,
    fetched_context_chars: int = 6000,
) -> str:
    lines: list[str] = []
    for s in sources:
        lines.append(
            f"[{s['id']}] title={s.get('title', '')!r}\n"
            f"    url={s.get('url', '')}\n"
            f"    snippet={s.get('snippet', '')!r}\n"
        )
        ft = (s.get("fetched_text") or "").strip()
        if ft:
            excerpt = ft[:fetched_context_chars]
            if len(ft) > fetched_context_chars:
                excerpt += "…"
            lines.append(f"    page_text_excerpt={excerpt!r}\n")
        elif s.get("fetch_error"):
            lines.append(f"    page_fetch_error={s.get('fetch_error')!r}\n")
    return "\n".join(lines) if lines else empty_sources_note(lang)
