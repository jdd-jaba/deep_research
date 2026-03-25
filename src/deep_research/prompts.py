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
        "plan_research": (
            "You generate a structured research plan. Reply with one JSON object only, no markdown fences, shape:\n"
            '{"plans": ["subtopic 1", "subtopic 2", ...]}\n'
            "Break the main topic into 5-8 focused, distinct subtopics that together give comprehensive coverage. "
            "Each subtopic should be a short, specific research question or angle that can be researched independently. "
            "Subtopics must be non-overlapping. Write each string in English. "
            "No other keys, no prose outside JSON."
        ),
        "generate_similar_questions": (
            "You generate a follow-up search query for web research. Reply with one JSON object only, "
            "no markdown fences, shape:\n"
            '{"similar_questions": ["..."]}\n'
            "Include exactly 1 targeted search query that directly addresses the specific gap identified "
            "in the prior reflection. Write the string in English. "
            "Do NOT generate a query that overlaps with already-written sections listed by the user. "
            "No other keys, no prose outside JSON."
        ),
        "summarize_sources": (
            "You are a research analyst. Write a dense factual synthesis of the sources. "
            "Use inline numeric citations like [1], [2] only for source ids listed below — "
            "never invent ids. If information is missing, say so. Use Markdown paragraphs and ### headings. "
            "Focus on what is NEW and specific to the current subtopic — do not repeat content "
            "already covered in the previously written sections listed by the user. "
            "Write in English."
        ),
        "reflect_on_summary": (
            "You review research coverage. Reply with one JSON object only, no markdown fences, shape:\n"
            '{"need_more_research": true|false, "reason": "short explanation"}\n'
            "Set need_more_research true only if important aspects of the topic are still unsupported "
            "by the sources or contradictions need resolution. Use English for reason."
        ),
        "write_section": (
            "You write ONE comprehensive section of a deep research report in Markdown. Requirements:\n"
            "- First line must be exactly: ## <subtopic> (use the subtopic title you are given, verbatim)\n"
            "- Then write several detailed, well-structured paragraphs (aim for depth)\n"
            "- Structure content with ### sub-headings, NOT numbered lists (1. 2. 3.); "
            "use bullet points only for short, truly list-like items\n"
            "- Use inline citations like [1], [2] — only numeric ids from the provided Sources list; "
            "never invent ids. The token [n] is FORBIDDEN — it is not a valid source id\n"
            "- Citation ids found in 'Already written sections' belong to those sections only — "
            "do NOT reuse them here. Only cite ids from the Sources list below\n"
            "- Do NOT add a top-level # title and do NOT add a References/Sources section "
            "(references are handled separately)\n"
            "- If 'Already written sections' are shown, do NOT repeat, re-introduce, or summarize "
            "that content — add only what is new and specific to THIS subtopic\n"
            "- Flag uncertainty where sources conflict or are thin\n"
            "- Write in English."
        ),
    },
    "ja": {
        "plan_research": (
            "構造化された調査計画を作成します。マークダウンのコードブロックは使わず、JSONオブジェクトのみを出力してください。\n"
            '形式: {"plans": ["サブトピック1", "サブトピック2", ...]}\n'
            "メインテーマを 5〜8 個の焦点が絞られた異なるサブトピックに分解し、全体として包括的な調査ができるようにしてください。"
            "各サブトピックは独立して調査できる、具体的な問いや切り口にしてください。"
            "【必須】各サブトピックの文字列には、必ずメインテーマの固有名詞・主キーワードをそのまま含めてください。"
            "サブトピックが単独でウェブ検索クエリとして使われるため、主キーワードが欠けると無関係な結果しか得られません。"
            "例: メインテーマが「ABC株式会社について」の場合、サブトピックは「デジタルサービスの種類」ではなく「ABC株式会社が提供するデジタルサービスの種類」と書く。"
            "サブトピック同士は重複させないでください。各文字列は日本語で書いてください。JSON 以外の文章は書かないでください。"
        ),
        "generate_similar_questions": (
            "あなたはウェブ検索用のフォローアップ検索クエリを生成します。マークダウンのコードブロックは使わず、JSONオブジェクトのみを出力してください。\n"
            '形式: {"similar_questions": ["..."]}\n'
            "前回のリフレクションで指摘された不足点を直接補う、具体的で検索に向いたクエリを 1 個だけ含めてください。"
            "すでに書き済みのセクションと重複するクエリは生成しないでください。"
            "言語はユーザーの質問と揃えてください。JSON 以外の文章は書かないでください。"
        ),
        "summarize_sources": (
            "【重要】出力は必ず日本語で書いてください。中国語・英語など他の言語は絶対に使用しないでください。\n\n"
            "あなたはリサーチアナリストです。与えられた情報源に基づき、事実を高密度に要約してください。"
            "文中の引用は [1]、[2] のような数字形式のみ使用し、下に示すソース id のみを使ってください。"
            "id を捏造しないでください。記号 [n] は絶対に使用禁止です。"
            "情報が不足している場合はその旨を書いてください。Markdown の段落と ### 見出しを使ってください。"
            "現在のサブトピックに新しく固有の内容に集中し、すでに書き済みのセクションの内容は繰り返さないでください。"
            "対象国・地域（日本）に関係のない情報源は完全に無視してください。"
            "本文は日本語で書いてください。"
        ),
        "reflect_on_summary": (
            "調査の網羅性をレビューします。マークダウンのコードブロックは使わず、JSONオブジェクトのみを出力してください。形式:\n"
            '{"need_more_research": true|false, "reason": "簡潔な説明"}\n'
            "トピックの重要な側面がまだ情報源で裏付けられていない、または矛盾の解消が必要な場合のみ need_more_research を true にしてください。"
            "reason は日本語で書いてください。"
        ),
        "write_section": (
            "【重要】出力は必ず日本語で書いてください。中国語・英語など他の言語は絶対に使用しないでください。\n\n"
            "調査レポートの「1つのセクション」だけを Markdown で書きます。要件:\n"
            "- 1 行目は必ず次の形式: ## （指定されたサブトピックタイトルをそのまま使用）\n"
            "- その後、十分な量の段落で詳述する（深さを重視）\n"
            "- 内容は「1. 2. 3.」のような番号付きリストではなく、### サブ見出しで構成する。"
            "短い箇条書き項目にのみ「-」を使用する\n"
            "- 引用は [1]、[2] のような数字形式のみ使用すること。下記「情報源」に記載された id のみ使用可。"
            "  id を捏造しないこと。記号 [n] は絶対に使用禁止（n は変数名であり有効なソース id ではない）\n"
            "- 「すでに書いたセクション」に含まれる引用番号（例: [2][3]）はそのセクション専用の id であり、"
            "  現在のセクションでは使用禁止。現在のセクションで引用できるのは下記「情報源」の id のみ\n"
            "- トップレベルの # タイトルは付けない。参考文献セクションは付けない（別途追加される）\n"
            "- 「すでに書いたセクション」が提示されている場合は、その内容の繰り返し・再説明をしない。"
            "このサブトピックに固有の新しい内容だけを書く\n"
            "- 情報源が矛盾・薄弱な点は不確実性として明記\n"
            "- 対象国・地域（日本）に関係のない情報源は完全に無視すること\n"
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


def plan_research_human(lang: str | None, main_topic: str, max_plans: int) -> str:
    if normalize_lang(lang) == "ja":
        return (
            f"メインテーマ:\n{main_topic}\n\n"
            f"このテーマを {max_plans} 個以内の非重複サブトピックに分解してください。\n"
            "各サブトピックは独立して調査できる具体的な切り口にしてください。\n"
            f"【重要】各サブトピックの文字列には必ず「{main_topic}」のキーワードを含めてください。"
            "サブトピックはそのままウェブ検索クエリとして使用されるため、主キーワードが入っていないと無関係な結果になります。"
        )
    return (
        f"Main research topic:\n{main_topic}\n\n"
        f"Break this into up to {max_plans} non-overlapping subtopics. "
        "Each should be a specific angle that can be researched independently. "
        f"IMPORTANT: every subtopic string must include the main entity/keyword from the topic "
        f"('{main_topic}'), since each subtopic is used directly as a web search query."
    )


def generate_similar_questions_human(
    lang: str | None,
    topic: str,
    reflection_text: str,
    written_headings: list[str] | None = None,
    main_topic: str | None = None,
) -> str:
    headings = written_headings or []
    if normalize_lang(lang) == "ja":
        none_ = "（なし）"
        headings_block = (
            "（なし）" if not headings else "\n".join(f"- {h}" for h in headings)
        )
        anchor = f"\nメインテーマ（検索クエリに必ず含めること）: {main_topic}" if main_topic else ""
        return (
            f"現在の調査サブトピック:\n{topic}{anchor}\n\n"
            "前回のリフレクションで指摘された不足点:\n"
            f"{reflection_text or none_}\n\n"
            "すでに書き済みのセクション見出し（重複を避ける）:\n"
            f"{headings_block}"
        )
    headings_block = (
        "(none)" if not headings else "\n".join(f"- {h}" for h in headings)
    )
    anchor = f"\nMain topic (must appear in the search query): {main_topic}" if main_topic else ""
    return (
        f"Current research subtopic:\n{topic}{anchor}\n\n"
        "Gaps from prior reflection:\n"
        f"{reflection_text or '(none)'}\n\n"
        "Already-written section headings (avoid overlapping these):\n"
        f"{headings_block}"
    )


def summarize_sources_human(
    lang: str | None,
    topic: str,
    sources_block: str,
    written_headings: list[str] | None = None,
) -> str:
    headings = written_headings or []
    if normalize_lang(lang) == "ja":
        headings_block = (
            "（なし）" if not headings else "\n".join(f"- {h}" for h in headings)
        )
        return (
            "対象国・地域: 日本（日本以外の国・地域の情報源は無視してください）\n\n"
            f"現在のサブトピック:\n{topic}\n\n"
            "すでに書き済みのセクション見出し（これらの内容は繰り返さない）:\n"
            f"{headings_block}\n\n"
            f"情報源（次の [n] の id のみ使用）:\n{sources_block}\n\n"
            "作業用の要約を生成してください。"
        )
    headings_block = (
        "(none)" if not headings else "\n".join(f"- {h}" for h in headings)
    )
    return (
        f"Current subtopic:\n{topic}\n\n"
        "Already-written section headings (do not repeat their content):\n"
        f"{headings_block}\n\n"
        f"Sources (use only these [n] ids):\n{sources_block}\n\n"
        "Produce a working summary focused on this subtopic."
    )


def reflect_on_summary_human(
    lang: str | None, topic: str, working_summary: str, source_ids: list[int]
) -> str:
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


def write_section_human(
    lang: str | None,
    subtopic: str,
    main_topic: str,
    working_summary: str,
    sources_block: str,
    prior_sections_markdown: str,
) -> str:
    prior = (prior_sections_markdown or "").strip()
    if normalize_lang(lang) == "ja":
        prior_block = (
            prior
            if prior
            else "（まだ書き済みのセクションはありません）"
        )
        return (
            "対象国・地域: 日本（日本以外の国・地域の情報源は無視してください）\n\n"
            f"メインテーマ（全体の文脈）:\n{main_topic}\n\n"
            f"現在のサブトピック（この節の ## 見出しとして使用）:\n{subtopic}\n\n"
            f"作業用要約（このサブトピックの調査結果）:\n{working_summary}\n\n"
            "【すでに書いたセクション】（繰り返さない。参照のみ）:\n"
            f"{prior_block}\n\n"
            f"情報源:\n{sources_block}\n"
        )
    prior_block = prior if prior else "(No prior sections yet.)"
    return (
        f"Main topic (overall context):\n{main_topic}\n\n"
        f"Current subtopic (use verbatim as the ## heading):\n{subtopic}\n\n"
        f"Working summary (research findings for this subtopic):\n{working_summary}\n\n"
        "Already written sections (reference only; do not repeat):\n"
        f"{prior_block}\n\n"
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
