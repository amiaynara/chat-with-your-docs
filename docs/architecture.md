# System Architecture

Full planned architecture of **Chat With Your Docs**, as frozen in issue #1 and decomposed
across tickets 1–16. This reflects the whole plan, not just what's built so far — see the
[status legend](#status-legend) and [ticket ledger](#ticket-ledger) below for what's actually
shipped.

An interactive version of this same diagram (with hover-friendly layout) is also available as a
published artifact from this session, if you have that link.

## Status legend

| Style | Meaning |
| --- | --- |
| 🟢 solid green | **Built** — tickets 1–6, closed |
| 🟠 dashed amber | **Planned** — tickets 7–16, `ready-for-agent`, not yet built |
| 🔵 blue | External AI provider (Anthropic, OpenAI) |
| ⬜ grey | Data store / infrastructure |

## Diagram

```mermaid
flowchart TB
    subgraph LEGEND["Legend"]
        direction LR
        LB["Built"]:::built
        LP["Planned"]:::planned
        LE["External provider"]:::external
        LS["Data store"]:::store
    end

    subgraph CLIENT["Client · Browser (React + TypeScript + Vite + Tailwind)"]
        direction LR
        C1["Upload & documents"]:::built
        C2["Chat (ask questions)"]:::built
        C3["Citations panel"]:::built
        C4["Multi-turn history · #7"]:::planned
        C5["Document scope · #8"]:::planned
        C6["Trace panel · #13"]:::planned
    end

    subgraph API["API · FastAPI"]
        direction LR
        A1["Documents API"]:::built
        A2["Delete document"]:::built
        A3["Session cookie"]:::built
        A4["Chat API"]:::built
        A5["Chat history · #7"]:::planned
        A6["Guardrails"]:::built
    end

    R["Redis (broker)"]:::store

    subgraph WORKER["Worker · Celery — separate process (async ingest)"]
        direction LR
        W1["Parse"]:::built --> W2["Chunk"]:::built --> W3["Embed"]:::built --> W4["Index"]:::built
    end

    subgraph ASK["Retrieval & Answer · in-process (sync ask)"]
        direction LR
        Q1["Embed query"]:::built --> Q2["Retrieve<br/>+hybrid #10, +scope #8"]:::built --> Q3["Rerank · #11"]:::planned --> Q4["Generate<br/>+citations, +guardrails"]:::built
    end

    subgraph DATA["Data stores"]
        direction LR
        D1["Postgres + pgvector<br/>documents · chunks<br/>+ sessions/messages · #7"]:::store
        D2["Object storage<br/>MinIO → S3 (prod)"]:::store
    end

    subgraph PROVIDERS["AI providers (behind adapter interfaces)"]
        direction LR
        P1["LLM — Anthropic"]:::external
        P2["Embeddings — OpenAI"]:::external
        P3["Reranker (opt.) · #11"]:::planned
    end

    subgraph SUPPORT["Supporting systems — build-time & quality, not on the request path"]
        direction LR
        S1["Observability · #13"]:::planned
        S2["Evaluation harness · #12 #14"]:::planned
        S3["CI/CD — lint, tests, 100% cov"]:::built
    end

    subgraph PROD["Production target · AWS reference — NOT deployed (backlog · #15)"]
        direction LR
        X1["ALB + ECS Fargate"]:::planned
        X2["RDS Postgres (pgvector)"]:::planned
        X3["ElastiCache Redis"]:::planned
        X4["S3 / Secrets Manager / CloudWatch"]:::planned
    end

    CLIENT -->|"HTTPS + anonymous session cookie"| API
    API -->|"async: enqueue task"| R --> WORKER
    API -->|"sync: invoke pipeline"| ASK

    W1 -->|"read file"| D2
    W4 -->|"write chunks"| D1
    W3 -->|"embed"| P2

    Q2 -->|"search (hybrid, scoped)"| D1
    Q4 -->|"generate"| P1
    Q3 -->|"rerank"| P3

    classDef built fill:#e9f5ef,stroke:#1f7a5c,stroke-width:1.5px,color:#12362a;
    classDef planned fill:#fbf1e3,stroke:#a8631f,stroke-width:1.5px,stroke-dasharray:4 3,color:#5c3d13;
    classDef external fill:#eaf0f7,stroke:#35577f,stroke-width:1.5px,color:#1d3350;
    classDef store fill:#eef1f4,stroke:#1b2430,stroke-width:1.5px,color:#1b2430;
```

Two request-time lanes hang off the API: an **asynchronous ingest path** (API → Redis → Celery
worker → object storage / pgvector / embeddings) and a **synchronous ask path** (API → retrieval
& answer, in the same process → pgvector / LLM / reranker). Supporting systems (observability,
evaluation, CI/CD) surround the request path but don't sit on it. The AWS panel is the documented
production target — dashed throughout, because none of it is deployed.

## Ticket ledger

| # | GH issue | Ticket | Status | Diagram area |
| - | - | - | - | - |
| 1 | #2 | Project scaffolding (prefactoring) | 🟢 Built | Repo, Docker Compose, CI |
| 2 | #3 | Upload → background ingest → status tracking | 🟢 Built | Client, API, Worker, Data stores |
| 3 | #4 | Single-turn Q&A over ingested documents | 🟢 Built | Client, API, Retrieval & Answer, LLM |
| 4 | #5 | Citations & source panel | 🟢 Built | Client, Retrieval & Answer |
| 5 | #6 | Answer-time guardrails | 🟢 Built | API, Retrieval & Answer |
| 6 | #7 | Document deletion | 🟢 Built | API, Data stores |
| 7 | #8 | Multi-turn conversation + session persistence + empty states | 🟠 Planned | Client, API, Data stores |
| 8 | #9 | Document-scoped retrieval filtering | 🟠 Planned | Client, Retrieval & Answer |
| 9 | #10 | Structure-aware chunking upgrade | 🟠 Planned | Worker |
| 10 | #11 | Hybrid retrieval (vector + keyword) | 🟠 Planned | Retrieval & Answer, Data stores |
| 11 | #12 | Optional reranker toggle | 🟠 Planned | Retrieval & Answer, AI providers |
| 12 | #13 | Evaluation harness | 🟠 Planned | Evaluation & Quality |
| 13 | #14 | In-app trace panel + structured logging | 🟠 Planned | Client, Observability |
| 14 | #15 | CI: add eval harness job | 🟠 Planned | CI/CD, Evaluation & Quality |
| 15 | #16 | Deployment follow-up backlog | 🟠 Planned | Production target (AWS) |
| 16 | #17 | Final README + submission polish | 🟠 Planned | — |

16 tickets · 6 built · 10 planned. Zero open `needs-triage`/`needs-info` items — every ticket
above is `ready-for-agent` in the tracker.
