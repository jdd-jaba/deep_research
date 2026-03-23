# deep_research

Local **deep research** CLI: **LangGraph** orchestration, **Ollama** for the LLM, **DuckDuckGo** (via **`ddgs`**) for discovery, then **full-page fetch** (**`httpx` + `trafilatura`**) for the top N URLs each round so the model sees real page text—not only snippets. It streams phases and model tokens to the terminal and produces a **long-form Markdown report**: after research loops it **plans an outline** (`plan_outline`), then **writes each section in a separate LLM pass** (`write_report`) for more depth, with inline **`[n]` citations** and a references section (`## 参考文献` / `## References`) built from retrieved URLs (deduplicated). **Default prompt language is Japanese**; use `--lang en` for English.

## Setup

1. [Install Ollama](https://ollama.com/) and pull a model (reasoning-oriented example):

   ```bash
   ollama pull deepseek-r1:8b
   ```

2. Python 3.11+ and a virtualenv:

   ```bash
   cd /path/to/deep-research
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

3. Optional `.env` (same keys work as environment variables):

   ```env
   OLLAMA_BASE_URL=http://127.0.0.1:11434
   OLLAMA_MODEL=deepseek-r1:8b
   DEEP_RESEARCH_MAX_LOOPS=3
   DEEP_RESEARCH_MAX_RESULTS=5
   DEEP_RESEARCH_LANG=ja
   DEEP_RESEARCH_MAX_SECTIONS=7
   DEEP_RESEARCH_FETCH_PAGES=8
   DEEP_RESEARCH_SEARCH_WORKERS=4
   DEEP_RESEARCH_FETCH_WORKERS=4
   ```

## Run

```bash
python -m deep_research "Your research question" --out report.md
```

Or use the console script:

```bash
deep-research "Your research question" -o report.md
```

Flags:

| Flag | Meaning |
|------|--------|
| `--out` / `-o` | Write the final Markdown file |
| `--model` | Ollama model name (overrides `OLLAMA_MODEL`) |
| `--base-url` | Ollama server URL (overrides `OLLAMA_BASE_URL`) |
| `--max-loops` | Reflection loop cap (default 3) |
| `--max-results` | DuckDuckGo results per query (default 5) |
| `--search-workers` | Parallel DDG queries per round (default 4, max 16; `1` = sequential; or `DEEP_RESEARCH_SEARCH_WORKERS`) |
| `--lang` | `ja` (default) or `en` — system/human prompts and reference heading (or `DEEP_RESEARCH_LANG`) |
| `--max-sections` | Max outline sections (capped 4–12, default 7; or `DEEP_RESEARCH_MAX_SECTIONS`) |
| `--fetch-pages` `[N]` | **On by default** (8 pages/round, or `DEEP_RESEARCH_FETCH_PAGES`). Pass `N` to override; `--fetch-pages` alone uses the default. |
| `--fetch-workers` | Parallel full-page HTTP fetches (default 4, max 16; `1` = sequential; or `DEEP_RESEARCH_FETCH_WORKERS`) |
| `--no-fetch-pages` | Turn off full-page fetch (snippets only). |

## Graph flow

`generate_similar_questions` → `web_research` → **`fetch_pages`** → `summarize_sources` → `reflect_on_summary` → (optional loop) → **`plan_outline`** → **`write_report`** → end.

Reflection may loop back to `generate_similar_questions` until the model is satisfied or `--max-loops` is reached. Similar search strings are printed **one per line** (raw model JSON for that node is not streamed to the terminal). The final stage builds a **multi-section** report (executive summary, background, key facts, process, limitations, etc., as the model plans), then appends references.

## Tool calling vs JSON

Search is **not** left to the model’s native tool calling (which can be flaky on some reasoning models). The graph calls **DuckDuckGo inside `web_research`** (several queries can run **in parallel**, each with its own client; tune with `--search-workers`). Query generation and reflection use **JSON-shaped** model outputs with a small parser (including Markdown JSON code fences) so the flow stays reliable.

## Troubleshooting

- **`Connection refused` to Ollama**: start `ollama serve` and check `--base-url`.
- **Empty or odd JSON from the model**: try a smaller/faster model (e.g. `llama3.2`) or lower temperature in `nodes.py` (`ChatOllama(..., temperature=0.2)`).
- **DuckDuckGo errors / rate limits**: reduce `--max-results`, use `--search-workers 1` (sequential), or fewer queries; the CLI prints search errors per query without stopping the whole run.
- **Fetch errors / empty page text**: many sites block bots or need JavaScript; use **`--no-fetch-pages`** (or `DEEP_RESEARCH_FETCH_PAGES=0`) to disable. Some pages return `skip_non_html` if the MIME type is not HTML. If you see many HTTP 429s, try **`--fetch-workers 1`**.
