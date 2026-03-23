# Deep research flow

## Single CLI run (one phase)

```mermaid
flowchart TB
  START([START]) --> PR[plan_research]
  PR --> WR[web_research]
  WR --> FP[fetch_pages]
  FP --> SS[summarize_sources]
  SS --> RF[reflect_on_summary]
  RF -->|more research| PR
  RF -->|done| PO[plan_outline]
  PO --> WRpt[write_report]
  WRpt --> END([END])
```

## Input / state

```mermaid
flowchart LR
  subgraph input
    T[topic]
    P[prior_report_markdown optional]
  end
  subgraph graph
    SQ[search_queries]
    SRC[sources]
    WS[working_summary]
    FD[final_document]
  end
  T --> PR2[plan_research]
  P --> PR2
  PR2 --> SQ --> SRC --> WS --> FD
```

## Two ways to get Part 1 + Part 2 in one file

### A) Two terminal commands

1. `deep-research "Q1" -o report.md`
2. `deep-research "Q2" -o report.md --prior-report report.md`

### B) One terminal command (`--follow-up`)

```bash
deep-research "First question" -o report.md --follow-up "Second question"
```

```mermaid
flowchart TB
  subgraph p1["Phase 1/2"]
    A1[Full graph\nno prior] --> MD1[report.md\nPart 1]
  end
  subgraph p2["Phase 2/2"]
    A2[Full graph\nprior = Part 1] --> MD2[report.md\nPart 1 + Part 2]
  end
  MD1 -.->|in-memory + file| A2
```

Repeat `--follow-up` for a third pass (each pass appends after the previous merged document).
