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
| **Tool 1: `run_query(sql: str)`** | Executes a single `SELECT` (or `WITH ... SELECT`) and returns at most 50 rows as a text table, so results don't flood the context. A simple regex rejects anything else; it is a convenience and a visible limit, not the security control (the database role is). The model uses it for schema discovery too (`information_schema`). |
| **Tool 2: `create_plan(steps: str)`** | The model records a multi-step plan, one step per line. The plan lives in a module-level variable, so a new plan replaces the old one. Returns the plan rendered with numbered lines, a status, and notes. |
| **Tool 3: `complete_step(step: int, note: str = "")`** | Marks a step done, with an optional note, and returns the re-rendered plan. |

Skill loading differs slightly by runtime, and that is documented rather than hidden. Strands' native loader (`AgentSkills`) lists each skill's name and description in the prompt and adds a `skills` tool the model calls to read one. Open WebUI's native behavior for skills attached to a model is to inject their full text, and its own built-in tools (including its `view_skill` loader) are switched off for the Glass Box model, so the model sees exactly our three tools. "Three tools" counts the tools we write. The skill text is identical in both; `tests/test_openwebui.py` checks that.

Design principle: keep the tools simple and assume the model is capable. Planned but not built: saving large query results to disk and processing them outside the context.

### Hard constraints
- **Three tools. Two skills. One system prompt.** Do not add tools, skills, retrieval/RAG, or helper agents without explicit approval from the project lead. Simplicity is the point of the demo.
  - **One exception, for automated tests only:** the test harness (not the product) may add a short addendum to the system prompt, for example telling the agent that no one can answer questions, so it should make reasonable assumptions (stating them) and give a single answer, but still never guess. This exists so automated tests get consistent single answers. It lives in `tests/`, is applied per run (appended to the prompt for Strands, sent as an extra system message to Open WebUI), and must not change the tools, the skills, or the honesty rules. The product prompt in `agent/` stays single. Not yet built; see section 9.
- **Skills are informational only.** They contain no code and no instructions to call tools.
- **Use each framework's native skill loading** (Strands and Open WebUI). This has produced consistent results across runtimes so far.
- **Temperature stays at the model default.** Repeatability comes from conditioning (tone, context, skills), not from sampling settings. The one exception is reasoning effort, set to `none` (`LLM_REASONING_EFFORT`) so the model reasons in visible text rather than hidden reasoning tokens, which suits the Glass Box goal. It is applied identically in both runtimes.
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
- All ports are bound to `127.0.0.1`. The Open WebUI demo login defaults to `admin@tcg.com` / `demo`, which is acceptable only because of that; set your own in `.env` before sharing the stack.
- Secrets live in `.env` (gitignored). Never commit keys or `webui.db` files that contain them.
- Public data only. No customer data, ever.
- **Known limitation:** system prompts and skills are susceptible to prompt injection and social engineering. Don't overclaim.

---

## 4. Dataset

**Status: chosen and loaded.**
- USAspending is **excluded** (already used elsewhere).
- **Dataset:** three FDA Data Dashboard exports (inspections, citations, recalls), loaded into five tables in the `fda` schema. Table grains, keys, and join cautions are in `DATA_IMPORT.md`. Compliance actions (warning letters, seizures, injunctions) are not included.
- **Known coverage limits to put in the database skill:** inspections span FY 2009 through FY 2027 (end dates 2008-10-01 to 2026-10-14), and FY 2027 holds only its first two weeks; recall classification dates run 2012-06-08 to 2026-10-16; recall rows carry a classification date but no initiation date; `FEI Number` identifies a firm, not a specific inspection-to-recall relationship; the exports are finalized, posted records and FDA says they are not comprehensive.
- Drugs@FDA remains a fallback if this dataset proves unsuitable.

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
- **Parity:** `EVAL_RUNTIME=openwebui pytest -m agent` runs the same suite through Open WebUI, so cross-runtime consistency is measured rather than assumed. It must drive Open WebUI the way its chat UI does (saved chat plus session): a bare API call does not execute tools server-side, and the model then has no way to query and may invent a number. `tests/openwebui_runtime.py` does this.

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

`tests/questions.yaml` currently has 28 questions across the five tiers, including skill-resolved questions (wording that is only unambiguous with the skills' defaults) and skill-dependent traps. `tests/ablate.py` runs questions with and without the skills to show what they contribute. Prefer questions that are unambiguous once the domain knowledge is applied over questions with no single right answer; the `ambiguous` tier is kept because it backs the demo's honesty claim and is graded only in interactive mode. Grow the set only when a new behavior needs covering.

---

## 6. Workflow

1. Profile and choose the dataset. Build the loader and frozen snapshot.
2. Write the two skills and the system prompt.
3. Implement the three tools and the Tier 1 tests.
4. Build the Strands agent in Jupyter. Write `questions.yaml`. Get the Tier 2 evals passing consistently.
5. Replicate in Open WebUI. Done by `agent/openwebui_provision.py` (run by `start.sh`), which builds the tool, skills and model from `agent/` over Open WebUI's API, so there is no hand-configured state to drift. This replaces the earlier idea of exporting `webui.db`. Change `agent/`, rerun the provisioner, and `tests/test_openwebui.py` confirms the two match.
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
./start.sh                        # convert data if needed, start the stack
docker compose logs -f postgres   # watch the initial data load
docker compose exec jupyter pytest -m "not agent"   # fast tests
docker compose exec jupyter pytest -m agent         # agent evals (uses tokens)
./stop.sh                         # stop the stack
./stop.sh --reset                 # full reset, including reloading the DB
```

---

## 9. Open decisions
- Automated-test addendum (section 2), applied by the test harness. Needs the project lead to name, for each `ambiguous` question, the single interpretation that counts as reasonable, so a gold query can grade the assumed answer. In that mode an ambiguous question passes by stating its assumption and answering correctly instead of asking; the interactive behavior, which the demo uses, is unchanged.
- Matching rule for free-text final answers: how to extract a scalar or result set from prose (the normalization rules are in section 5).
