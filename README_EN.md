# deep_research

> [日本語 README（デフォルト）](README.md)

A local **deep research CLI** powered by **LangGraph**, **Ollama**, **DuckDuckGo** (`ddgs`), and full-page fetch (**httpx + trafilatura**).

The topic is first **broken into 5–8 subtopics** (`plan_research`). For each subtopic, a direct web search is run first. If the model decides more research is needed, it generates **1 targeted follow-up query** and searches again — repeating until satisfied. Then that subtopic's section is **immediately written to disk** (`write_section`) before moving to the next. This keeps local context window usage bounded while producing a **long-form Markdown report**.

---

## Graph flow

```mermaid
sequenceDiagram
    actor User
    participant Graph as LangGraph
    participant LLM as Ollama LLM
    participant DDG as DuckDuckGo
    participant Web as Web Pages
    participant File as report_*.md

    User->>Graph: topic

    Graph->>LLM: plan_research
    Note right of LLM: Break topic into N subtopics
    LLM-->>Graph: ["Subtopic 1", "Subtopic 2", ...]

    loop For each subtopic (N iterations)
        Graph->>Graph: advance_plan
        Note right of Graph: Set subtopic, reset per-plan state, set source ID offset

        Graph->>DDG: web_research (plan topic as query)
        DDG-->>Graph: URLs + snippets (globally numbered IDs)

        Graph->>Web: fetch_pages (parallel)
        Web-->>Graph: page text

        Graph->>LLM: summarize_sources
        LLM-->>Graph: working summary

        Graph->>LLM: reflect_on_summary
        LLM-->>Graph: need_more_research: true / false

        loop Only if need_more_research = true
            Graph->>LLM: generate_similar_questions
            LLM-->>Graph: 1 targeted follow-up query

            Graph->>DDG: web_research (parallel)
            DDG-->>Graph: URLs + snippets

            Graph->>Web: fetch_pages (parallel)
            Web-->>Graph: page text

            Graph->>LLM: summarize_sources
            LLM-->>Graph: working summary

            Graph->>LLM: reflect_on_summary
            LLM-->>Graph: need_more_research: true / false
        end

        Graph->>LLM: write_section
        LLM-->>Graph: ## Subtopic body (no references)

        Graph->>File: flush section body to disk immediately
        Note right of File: accumulate sources into all_sources
    end

    Graph->>File: finalize_report
    Note right of File: append single ## References block at the end

    Graph-->>User: output_file_path
```

---

## Setup

### 1. Install Ollama and pull a model

[Install Ollama](https://ollama.com/), then pull a model (reasoning-oriented example):

```bash
ollama pull deepseek-r1:8b
```

### 2. Python environment (Python 3.11+)

```bash
cd /path/to/deep-research
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Optional `.env`

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=deepseek-r1:8b
DEEP_RESEARCH_MAX_LOOPS=3
DEEP_RESEARCH_MAX_RESULTS=5
DEEP_RESEARCH_LANG=en
DEEP_RESEARCH_MAX_PLANS=6
DEEP_RESEARCH_FETCH_PAGES=8
DEEP_RESEARCH_SEARCH_WORKERS=4
DEEP_RESEARCH_FETCH_WORKERS=4
```

---

## Usage

```bash
python -m deep_research "Your research question" --out report.md
```

Or use the console script:

```bash
deep-research "Your research question" -o report.md
```

### Flags

| Flag                  | Description                                                                                                                       |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `--out` / `-o`        | Output Markdown path (default: `report_<topic>.md` in current directory)                                                         |
| `--model`             | Ollama model name (overrides `OLLAMA_MODEL`)                                                                                      |
| `--base-url`          | Ollama server URL (overrides `OLLAMA_BASE_URL`)                                                                                   |
| `--max-loops`         | Reflection loop cap per subtopic (default 3)                                                                                      |
| `--max-results`       | DuckDuckGo results per query (default 5)                                                                                          |
| `--search-workers`    | Parallel DDG queries per round (default 4, max 16; `1` = sequential; or `DEEP_RESEARCH_SEARCH_WORKERS`)                           |
| `--lang`              | `ja` (default) or `en` — prompt and report language (or `DEEP_RESEARCH_LANG`)                                                    |
| `--max-plans`         | Number of subtopics to generate (5–8, default 6; or `DEEP_RESEARCH_MAX_PLANS`)                                                   |
| `--fetch-pages [N]`   | Full-page fetches per round (default 8; or `DEEP_RESEARCH_FETCH_PAGES`). Pass `N` to override; `--fetch-pages` uses the default. |
| `--fetch-workers`     | Parallel HTTP fetches (default 4, max 16; `1` = sequential; or `DEEP_RESEARCH_FETCH_WORKERS`)                                     |
| `--no-fetch-pages`    | Disable full-page fetch (snippets only)                                                                                           |

---

## Output file structure

```markdown
# Research Topic

## Subtopic 1
(body text with inline citations [1][2]…)

## Subtopic 2
(body text with inline citations [3][4]…)

## References
1. Title A — URL
   _snippet_
2. Title B — URL
   _snippet_
3. Title C — URL
…
```

- Each section body is **flushed to disk immediately** after its research loop completes.
- Source citation numbers (`[n]`) are **globally sequential** across all subtopics.
- References are appended in one block at the very end by `finalize_report`, so the file is readable even if the run is interrupted mid-way.

---

## Troubleshooting

- **`Connection refused` (Ollama)**: run `ollama serve` and check `--base-url`.
- **JSON parse errors**: try a smaller model (e.g. `llama3.2`) or lower `temperature` in `nodes.py`.
- **DuckDuckGo rate limits**: reduce `--max-results`, use `--search-workers 1`, or wait a moment.
- **Fetch errors / empty page text**: many sites block bots or require JavaScript — use `--no-fetch-pages`. For HTTP 429 floods try `--fetch-workers 1`.
