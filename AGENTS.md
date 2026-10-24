# AGENTS.md

Context for AI coding agents (Claude Code, Codex, Copilot, Cursor, etc.) and the developers who use them.
Read this file before making changes. If something here conflicts with a request, ask before proceeding.

> Claude Code users: create a one-line `CLAUDE.md` containing `@AGENTS.md` so both tools share this file.

---

## 1. What we are building

A **Glass Box AI** demonstration: one natural-language-to-SQL analysis agent, defined once and run in two runtimes against a US government public dataset.

- **Runtime A, AWS Strands (Python, in Jupyter):** Used for development and automated evaluation.
- **Runtime B, Open WebUI:** Used for interactive live demos with non-technical audiences.

The demo shows that a *simple*, well-conditioned agent gives correct, repeatable answers. It also shows the agent being honest about ambiguity and limits.

### Glass Box principles (TCG's approach to AI)
- **People define the problem.**
- **People can inspect the AI's work and limits.**
- **People check the result before using it.**

Every design choice should make the agent's reasoning, queries, and uncertainty *visible*, not hidden.

### Lineage
This demo follows an analysis-assistant pattern TCG built for a federal financial data program. That program ran the same agent in Strands and Open WebUI, with doc-style skills and a tiered benchmark. That pattern is reproduced here on public FDA data.

- **Do not copy client code, prompts, or data from that program.** Re-implement the design from this file.

---

## 2. The agent definition (the contract)

"Same agent" means **identical in both runtimes**:

| Component | Definition |
|---|---|
| **LLM** | Set via `LLM_MODEL_ID` in `.env`. Initial target: OpenAI GPT-6 Luna (`gpt-6-luna`). If the agentic environment has reliability problems, evaluate GPT-5.6 Luna or a Sol tier. |
| **System prompt** | Professional, context-rich. Instructs the model to say plainly when a question is ambiguous or the data can't answer it, and to **ask the user for clarification rather than guess**. |
| **Skill 1: database** | Informational doc: what the dataset is, tables, keys, joins, coverage limits, known data-quality gotchas. |
| **Skill 2: terminology** | Informational doc: analyst/regulatory vocabulary mapped to columns and coded values. |
| **Tool 1: `run_query(sql)`** | Executes a single read-only `SELECT` and returns rows (with a row cap). The model uses it for schema discovery too (`information_schema`). |
| **Tool 2: `create_plan(steps)`** | The model records an ordered list of steps for a multi-step question. |
| **Tool 3: `next_step(...)`** | Records the outcome of the current step and returns the next one. Keeps small models on track. |

### Hard constraints
- **Three tools. Two skills. One system prompt.** Do not add tools, skills, retrieval/RAG, or helper agents without explicit approval from the project lead. Simplicity is the point of the demo.
- **Skills are informational only.** They contain no code and no instructions to call tools.
- **Use each framework's native skill loading** (Strands and Open WebUI). This has produced consistent results across runtimes so far.
- **Temperature stays at the model default.** Repeatability comes from conditioning (tone, context, skills), not from sampling settings.
- **Single source of truth:** the system prompt, skills, and tool behavior live in `agent/`. The Open WebUI configuration must match them exactly. Any change in one runtime must be mirrored in the other in the same PR.

---

## 3. Architecture

Three containers via Docker Compose, targeting local Linux or WSL2:

| Service | Purpose |
|---|---|
| `postgres` | Holds the dataset. Loaded from cleaned CSVs on first start. Agents connect only as a read-only role. |
| `jupyter` | JupyterLab + AWS Strands. Hosts the Python agent, the demo notebook, and the pytest suites. |
| `openwebui` | Open WebUI with the same agent configured (prompt, skills, tools) for live demos. |

### Security posture (demo-grade, but deliberate)
- Agents use `agent_ro`: `SELECT` only, `default_transaction_read_only = on`, and a `statement_timeout`. The role is the real guardrail. String-checking SQL is a convenience, not a control.
- The admin DB credentials are used only by Postgres init scripts. They are never exposed to `jupyter` or `openwebui`.
- All ports are bound to `127.0.0.1`.
- Secrets live in `.env` (gitignored). Never commit keys or `webui.db` files that contain them.
- Public data only. No customer data, ever.
- **Known limitation:** system prompts and skills are susceptible to prompt injection and social engineering. Don't overclaim.

---

## 4. Dataset

**Status: not final.**
- USAspending is **excluded** (already used elsewhere).
- **Leading candidate:** FDA compliance data from the FDA Data Dashboard (inspections, compliance actions, recalls). It has strong public-sector appeal, clean categorical fields, and rich terminology (recall classes, inspection classifications, fiscal years).
- **Fallback:** Drugs@FDA (12 tab-delimited relational tables with a published ERD). It's the cleanest option for unit tests.
- **First task:** download candidate exports, profile them, and confirm the join keys (e.g., FEI number), row counts, and date fields. Report findings before building the loader.

### Subset guidelines
- A few related tables with real joins.
- Loads in minutes.
- Small enough to version the cleaned CSVs or a reproducible download script.
- Keep the downloaded workbooks in git as the frozen snapshot, and record the download date in the README. Gold answers are computed from gold SQL (section 5), so refreshing the data does not require re-keying expected values.

---

## 5. Testing

Tests are `.py` files under `tests/` (not notebooks). The notebook is a demo surface that imports the same code.

### Tier 1: deterministic (`pytest -m "not agent"`), fast and free
- `run_query` rejects non-`SELECT` statements and respects the row cap.
- The `agent_ro` role cannot write, and the timeout fires.
- The plan tools behave correctly (ordering, completion, edge cases).
- Every gold SQL in `questions.yaml` runs as `agent_ro` within the timeout and returns the declared shape (column count, plausible row count, non-empty unless `shape` says otherwise). Gold answers are not hard-coded: the harness computes them from `gold_sql`, so tests hold up when the underlying data is refreshed. Hand-verify each gold query once when authoring it, and say how in `notes`.

### Tier 2: agent evals (`pytest -m agent`), slow and costs tokens
- Each question runs **N times** (default 3–5, configurable).
- **Correctness:** grade on the *result*, not the SQL text. Run the gold SQL at test time and compare the agent's final answer (or its last query's result set) against that result. Normalize before comparing: unordered unless the gold SQL has an `ORDER BY`, small numeric tolerance, column names ignored.
- **Consistency:** the fraction of runs that agree with each other. Report both metrics per question and in aggregate.
- **Ambiguity questions (`ambiguous` tier):** some questions are intentionally ambiguous. A correct response asks for clarification instead of answering.
- **Unanswerable questions (`unanswerable` tier):** some questions ask for something the dataset does not contain (for example, an attribute no table has, or a period outside the coverage). A correct response says plainly that the data cannot answer it, ideally noting what is available instead. It must not invent an answer or silently substitute a different measure. These questions have no `gold_sql`.
- Pin time frames to explicit fiscal years in answerable questions. "Last year" belongs in the `ambiguous` tier.
- **Parity (planned):** run the same suite against Open WebUI's OpenAI-compatible chat API, so cross-runtime consistency is measured rather than assumed.

### `tests/questions.yaml` schema (draft)
```yaml
- id: q001
  tier: easy            # easy | medium | hard | ambiguous | unanswerable
  expect: answer        # answer | clarify | unavailable (ambiguous -> clarify, unanswerable -> unavailable)
  question: "How many Class I recall events were classified in fiscal year 2025?"
  gold_sql: |           # required when expect: answer; omitted otherwise
    SELECT COUNT(*) FROM ...
  shape:                # optional sanity bounds checked by Tier 1
    columns: 1
    min_rows: 1
  notes: "Fiscal year runs Oct 1 - Sep 30. Verified by hand against ..."
```

Start with ~10 questions across the tiers and grow toward ~20.

---

## 6. Workflow

1. Profile and choose the dataset. Build the loader and frozen snapshot.
2. Write the two skills and the system prompt.
3. Implement the three tools and the Tier 1 tests.
4. Build the Strands agent in Jupyter. Write `questions.yaml`. Get the Tier 2 evals passing consistently.
5. Replicate in Open WebUI. Configuration may be done manually in the UI, then `webui.db` is exported for reuse (scrubbed of secrets).
6. Add the automated parity run.

Iterate in small steps. Prefer working, verified increments over large changes.

---

## 7. Conventions

- Python 3.12. Format with `ruff`. Type hints on public functions.
- The model ID, keys, and DB URLs come from environment variables only.
- Don't upgrade pinned images or packages without noting it in the PR.
- Keep the demo notebook runnable top-to-bottom on a fresh `docker compose up`.
- When unsure, choose the simpler option and ask.

---

## 8. Common commands

```bash
cp .env.example .env              # then fill in keys
docker compose up -d --build      # start the stack
docker compose logs -f postgres   # watch the initial data load
docker compose exec jupyter pytest -m "not agent"   # fast tests
docker compose exec jupyter pytest -m agent         # agent evals (uses tokens)
docker compose down -v            # full reset, including reloading the DB
```

---

## 9. Open decisions
- Final dataset and subset (see section 4).
- Precise signatures for `create_plan` / `next_step` (mirror the proven design).
- Matching rule for free-text final answers: how to extract a scalar or result set from prose (the normalization rules are in section 5).
