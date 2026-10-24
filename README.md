# Glass Box AI: Database Query Agent (FDA Demo)

**Ask questions of a federal dataset in plain English. See exactly how the AI got its answer, and get told when the question is ambiguous.**

This repository is a working demonstration of TCG's **Glass Box** approach to AI, applied to natural-language analysis of public FDA data.

> **Glass Box is our approach to AI:** people define the problem, can inspect the AI's work and limits, and check the result before using it.

---

## Why this demo exists

Most "chat with your data" tools are black boxes. They return a confident answer with no way to see how it was produced, and they rarely admit when a question can't be answered from the data.

This demo makes three claims and lets you verify each one:

1. **Simple beats clever.** A small, low-cost model with three tools and two short reference documents answers real analytical questions correctly.
2. **Answers are repeatable.** Every benchmark question runs multiple times, and we report both *correctness* and *consistency*.
3. **The agent is honest.** When a question is ambiguous ("last year": fiscal or calendar?) or outside what the data covers, it asks rather than guesses.

And one more: **the same agent behaves the same way in two different runtimes.** Developers use a Python notebook; analysts use a chat interface.

---

## How it works

```
                 ┌───────────────────────────────┐
                 │    The agent (defined once)   │
                 │  • System prompt              │
                 │  • 2 skills: database guide,  │
                 │    terminology guide          │
                 │  • 3 tools: run_query,        │
                 │    create_plan, next_step     │
                 └──────────────┬────────────────┘
                 ┌──────────────┴──────────────┐
        ┌────────▼────────┐          ┌─────────▼────────┐
        │  Jupyter +      │          │   Open WebUI     │
        │  AWS Strands    │          │   (live demo)    │
        │  (dev + tests)  │          │                  │
        └────────┬────────┘          └─────────┬────────┘
                 │      read-only SQL          │
                 └──────────────┬──────────────┘
                        ┌───────▼───────┐
                        │  PostgreSQL   │
                        │  (FDA data)   │
                        └───────────────┘
```

| Piece | What it does |
|---|---|
| **System prompt** | Sets a professional analyst's posture and tells the model to flag ambiguity and unknowns. |
| **Database skill** | A plain-language guide to the tables, how they connect, and what the data does *not* cover. |
| **Terminology skill** | Maps regulatory vocabulary (for example, recall classes and inspection outcomes) to the actual fields and codes. |
| **`run_query`** | Runs a single read-only `SELECT`. The agent uses it both to explore the schema and to answer questions. |
| **`create_plan` / `next_step`** | Let the agent write a short plan and work through it step by step, so multi-step questions don't go off the rails. |

### Guardrails
- The agent connects as a **read-only database role** with a query timeout. It cannot change data.
- Everything runs locally. Only public data is used.
- Prompts and skills can be manipulated by a determined user (prompt injection). This is a demo of trustworthy *behavior*, not a hardened security boundary.

---

## The data

> **Status: dataset selection in progress.**

We are evaluating FDA public datasets:

- **FDA compliance data** (leading candidate): inspections, compliance actions (warning letters, seizures, injunctions), and recalls from the FDA Data Dashboard.
- **Drugs@FDA** (fallback): drug applications, products, and submission history.

The chosen subset will be frozen as a snapshot so benchmark answers stay stable when FDA refreshes its data.

---

## Quick start

**Prerequisites:** Docker with Compose v2 on Linux or WSL2, plus an OpenAI and/or Gemini API key.

```bash
git clone <this-repo> && cd <this-repo>
cp .env.example .env        # add your API key(s) and passwords
docker compose up -d --build
```

| Service | URL |
|---|---|
| JupyterLab | http://localhost:8888 (token from `JUPYTER_TOKEN`) |
| Open WebUI | http://localhost:3000 |
| PostgreSQL | localhost:5432 (admin only; the agents use the read-only role) |

The first start loads the dataset into Postgres. To reload from scratch, run `docker compose down -v`.

### Key environment variables

| Variable | Purpose |
|---|---|
| `LLM_MODEL_ID` | Model used by both runtimes (e.g. `gpt-6-luna`) |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | Provider keys |
| `POSTGRES_PASSWORD` | Admin password (init scripts only) |
| `AGENT_RO_PASSWORD` | Password for the agents' read-only role |
| `JUPYTER_TOKEN` | JupyterLab access token |
| `WEBUI_SECRET_KEY` | Open WebUI session secret |

---

## Running the tests

```bash
# Fast, free: tool behavior, read-only enforcement, gold SQL answers
docker compose exec jupyter pytest -m "not agent"

# Agent benchmark: each question runs several times (uses API tokens)
docker compose exec jupyter pytest -m agent
```

The benchmark reports, per question and overall:
- **Correctness:** did the agent's answer match the verified answer?
- **Consistency:** how often did repeated runs agree with each other?
- **Clarification behavior:** for intentionally ambiguous questions, did the agent ask instead of guessing?
- **Honesty about limits:** for questions the data cannot answer, did the agent say so instead of inventing an answer?

Verified answers are not stored. Each question carries a gold SQL query that is run at test time, so the tests stay valid when the FDA data is refreshed.

---

## Repository layout

```
docker-compose.yml
.env.example
agent/
  system_prompt.md
  skills/
    database.md
    terminology.md
  tools.py              # run_query, create_plan, next_step
db/
  init/                 # roles, schema, data load (runs on first start)
data/                   # cleaned CSV snapshot (or download script)
jupyter/
  Dockerfile
  requirements.txt
notebooks/
  demo.ipynb
tests/
  questions.yaml        # NL question + gold SQL (answers computed at test time)
  test_tools.py
  test_agent_evals.py
openwebui/
  data/                 # Open WebUI state (webui.db), gitignored
AGENTS.md               # context for AI coding assistants and contributors
```

---

## Roadmap
- [ ] Select and profile the dataset; build the loader and frozen snapshot
- [ ] Write the system prompt and the two skills
- [ ] Implement the three tools and deterministic tests
- [ ] Build the Strands agent; reach consistent benchmark results
- [ ] Replicate the agent in Open WebUI
- [ ] Automated cross-runtime parity check

---

## Contributing
Read [`AGENTS.md`](AGENTS.md) first. The most important rule: **keep it simple.** Three tools, two skills, one prompt. Changes to the agent must be applied to both runtimes together.

---

*TCG, Inc. Glass Box AI Working Group*
