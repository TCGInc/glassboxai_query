# Plan: Replace Open WebUI with LibreChat

**Status:** Draft for review. No code has changed yet.
**Rollback point:** tag `Open_WebUI_First_Demo` (commit `b070d56`), the working Open WebUI demo.
**Background:** [librechat-feasibility.md](librechat-feasibility.md)
**LibreChat version:** `v0.8.8`, the current stable release. Image: `registry.librechat.ai/librechat-ai/librechat:v0.8.8`. Everything below was checked against the `v0.8.8` source.

---

## Goals

1. Replace Open WebUI with LibreChat as the demo's chat interface (Runtime B).
2. Keep it **simple**. The agent stays as it is: one system prompt, two skills, three tools, all in `agent/`. LibreChat gets as few containers, services and moving parts as possible.
3. A fresh checkout plus `./start.sh` gives a working, configured agent, with no clicking in the UI.
4. Log in as one admin user for now. External authentication (Keycloak) comes later.
5. Keep the parity tests: the same question suite runs through Strands and LibreChat.

Branding (logo, colors, OMB styling) is **out of scope** for this step. It goes on top later, as described in the feasibility report.

---

## The approach in one paragraph

LibreChat runs from its **official image, unmodified**, with one extra container: MongoDB, which LibreChat requires.

The agent is **pure configuration**. LibreChat's model specs (`modelSpecs` in `librechat.yaml`) can carry the system prompt, the tools and the skills directly. So we don't create a LibreChat "agent" object in its database, and we don't need a provisioning script, an API login, sharing steps or a generated agent ID.

The three tools reach LibreChat through MCP (Model Context Protocol). LibreChat starts a small Python wrapper, `agent/mcp_server.py`, inside its own container. That wrapper calls `agent/tools.py`, just as Open WebUI's tool does today.

The two skills are mounted read-only into LibreChat's skills folder.

`start.sh` writes `librechat.yaml` from `agent/` and `.env`, and creates the admin user on first start.

---

## Architecture

| Service | Today | After |
|---|---|---|
| `postgres` | FDA data | unchanged |
| `jupyter` | Strands, notebook, tests | unchanged. It gains the `mcp` package for one test and loses the Open WebUI settings. |
| `openwebui` | chat interface | **removed** |
| `librechat` | none | official image, pinned. It runs the tool server as a child process. |
| `mongodb` | none | LibreChat's own database (users, chats). Internal only; no host port. |

**Four containers in total, up from three.** We deliberately leave out several things:

| Left out | Why it's safe to leave out |
|---|---|
| Meilisearch (conversation search) | `SEARCH=false`. The sidebar still lists chats; only full-text search across them is lost. |
| `rag_api` and its vector database (file search) | The agent doesn't use files. |
| LibreChat's admin panel | Not needed for a single admin user. |
| A separate tool-server container | LibreChat starts the tools itself (see Tools below). |
| A custom LibreChat image | Not needed until branding. |

MongoDB has no lighter substitute: LibreChat stores everything in it.

```
   browser ──► librechat (127.0.0.1:3080) ──► mongodb
                   │
                   ├─ starts: python agent/mcp_server.py  ──► postgres (as agent_ro)
                   └─ reads:  agent/skills/  (read-only, as LibreChat skills)

   jupyter (Strands, notebook, tests) ──► postgres (as agent_ro)
                                      └─► librechat (parity tests)
```

---

## The agent in LibreChat

### System prompt, model and landing page: one model spec

`librechat.yaml` defines a single model spec, "Glass Box FDA":

```yaml
modelSpecs:
  enforce: true
  prioritize: true
  list:
    - name: glassbox-fda
      label: Glass Box FDA
      description: FDA inspections, citations and recalls, with the work shown.
      default: true                  # every new chat starts here
      showOnLanding: true
      mcpServers: [fda]              # the three tools
      skills: true                   # the deployment skills (ours are the only ones)
      conversation_starters:         # the four demo prompts from tests/questions.yaml
        - "For fiscal year 2024, how many recall events were there in each recall class?"
        - "..."
      preset:
        endpoint: openAI
        model: gpt-6-luna            # from LLM_MODEL_ID
        reasoning_effort: none       # from LLM_REASONING_EFFORT
        promptPrefix: |              # agent/system_prompt.md, verbatim
          You are a careful data analyst assistant ...
```

Because the spec names no saved agent, LibreChat builds a temporary agent for each chat from these settings. Its source calls this an "ephemeral agent".

- **System prompt:** `promptPrefix` becomes the agent's instructions.
- **Tools:** `mcpServers` attaches our MCP server's tools.
- **Skills:** `skills: true` turns on skills.
- **No extra tools:** web search, code execution, file search and memory stay off unless the spec turns them on.

We use `skills: true` rather than listing skill names. In `v0.8.8`, a named list is looked up in MongoDB, but folder-loaded skills aren't stored there. With `skills: true` the agent uses all available skills, and ours are the only ones.

Temperature and other sampling settings stay at the model's defaults, as they do today.

### Tools: a small MCP wrapper, started by LibreChat

`agent/mcp_server.py` is new, about 25 lines:

- It uses the official MCP Python SDK to expose `run_query`, `create_plan` and `complete_step` straight from `agent/tools.py`. The docstrings and signatures are unchanged, so the model sees the same descriptions.
- It declares its own dependencies in a header (`mcp`, `psycopg[binary]`), in the standard format `uv` reads (PEP 723). The official LibreChat image already includes Python 3.12 and `uv`, so no custom image is needed.

`librechat.yaml` registers it as a stdio server, meaning LibreChat starts it and talks to it over standard input and output:

```yaml
mcpServers:
  fda:
    type: stdio
    command: uv
    args: [run, --script, /opt/glassbox/agent/mcp_server.py]
    env:
      FDA_DATABASE_URL: "${FDA_DATABASE_URL}"   # read-only agent_ro role
    chatMenu: false                              # only through the spec, not a user toggle
```

`./agent` is mounted read-only at `/opt/glassbox/agent`, the same path the Open WebUI container uses today.

`uv` downloads the two dependencies the first time it runs, which takes a few seconds and needs internet access. The stack already needs internet for the LLM. A small volume for `uv`'s cache keeps that download from repeating on restarts.

### Skills: mounted as deployment skills

- `./agent/skills` is mounted read-only at `/app/skill`, the folder LibreChat loads "deployment skills" from (`DEPLOYMENT_SKILLS_DIR`).
- Our `SKILL.md` files already have the frontmatter LibreChat expects (`name`, `description`).
- LibreChat loads skills **on demand**: the model sees each skill's name and description and calls LibreChat's `skill` tool to read one. **This is how Strands works too**, so the two runtimes now load skills the same way. Open WebUI injected the full text, which was a documented difference.

### Single source of truth

`librechat.yaml` is **generated, not hand-written**:

- `agent/librechat_config.py` is new, about 80 lines.
- It builds `librechat/librechat.yaml` from `agent/system_prompt.md`, the demo prompts, `LLM_MODEL_ID` and `LLM_REASONING_EFFORT`.
- `start.sh` runs it before starting LibreChat, inside the existing `jupyter` image, which already has PyYAML.
- The generated file is gitignored, like `webui.db` today.

This replaces `agent/openwebui_provision.py`. The difference is that it writes a file instead of calling an API, so there's no running service to configure and nothing to drift.

---

## Admin user and login

| Item | Approach |
|---|---|
| Admin account | `start.sh` runs LibreChat's own script once: `npm run create-user -- <email> <name> <username> <password>`. The first user created is automatically the admin. Rerunning it is harmless: an existing user is reported and skipped. |
| Credentials | Reuse the current settings, renamed `ADMIN_EMAIL` / `ADMIN_PASSWORD` (defaults `admin@tcg.com` / `glassbox`). `start.sh` prints them, as it does today. |
| Password length | LibreChat requires 8 characters by default, which `glassbox` meets. |
| Sign-up | `ALLOW_REGISTRATION=false`. Only the admin account exists. |
| Secrets | LibreChat needs four random secrets (`CREDS_KEY`, `CREDS_IV`, `JWT_SECRET`, `JWT_REFRESH_SECRET`), added to `.env.example` with a one-line `openssl` command to generate them. |
| Exposure | Port bound to `127.0.0.1` only, as today. |

**Security:** LibreChat's container gets only the settings it needs, passed explicitly in `docker-compose.yml`. We don't mount our whole `.env` into it, as LibreChat's own compose file does, because that file holds the Postgres admin password. Our rule that admin database credentials never reach the chat container still holds.

---

## Repository changes

**New:**
- `agent/mcp_server.py`: the MCP wrapper for the three tools.
- `agent/librechat_config.py`: writes `librechat.yaml` from `agent/` and `.env`.
- `tests/librechat_runtime.py`: runs one question through LibreChat for the parity evals. It replaces `tests/openwebui_runtime.py` and works the same way: log in, send the question to the "Glass Box FDA" spec through the chat endpoint the web UI uses (`/api/agents/chat`), wait for the stream to finish, and convert the saved messages and tool calls into the same `Answer` object the Strands runner returns.
- `tests/test_librechat.py`: Tier 1 checks (fast, no LLM tokens):
  - The generated config matches `agent/`: prompt verbatim, demo prompts, model and reasoning effort.
  - The MCP server exposes exactly the three tools, with the same names, signatures and docstrings as `agent/tools.py`.
  - Live checks, skipped if LibreChat isn't running: LibreChat lists the three `fda` tools and the two skills.
- `librechat/`: holds the generated `librechat.yaml` (gitignored).

**Changed:**
- `docker-compose.yml`: drop `openwebui`; add `librechat` and `mongodb`; update the `jupyter` settings.
- `start.sh`, `stop.sh`, `.env.example`, `.gitignore`: as described above.
- `tests/test_agent_evals.py`, `tests/conftest.py`: `EVAL_RUNTIME=librechat`.
- `jupyter/requirements.txt`: add `mcp` (pinned), for the Tier 1 test.
- **Docs:** `README.md`, `AGENTS.md` (sections 1, 2, 3, 5, 6), the notebook's two markdown cells that mention Open WebUI, the docstring in `agent/tools.py`, and a comment in `tests/questions.yaml`.

**Removed:** `agent/openwebui_provision.py`, `tests/openwebui_runtime.py`, `tests/test_openwebui.py`, `tests/test_openwebui_runtime.py`, `openwebui/`.

**Unchanged:** `agent/tools.py` (except one docstring line), `agent/system_prompt.md`, the skills, the Strands agent, the database, the question set and the grading.

---

## Differences to document (and check in the evals)

1. **Tool names carry a suffix.** LibreChat names MCP tools `<tool>_mcp_<server>`, so the model sees `run_query_mcp_fda`, `create_plan_mcp_fda` and `complete_step_mcp_fda`. The descriptions are unchanged, and the system prompt's references to `run_query` and so on should still be clear to the model. The evals will show whether they are. If they aren't, a one-line note in the system prompt would cover it.
2. **One extra built-in tool:** LibreChat's `skill` loader, the counterpart of Strands' `skills` tool. "Three tools" still counts the tools we write, as AGENTS.md already says.
3. **The plan is shared across chats.** LibreChat runs one copy of the tool server for everyone, so `create_plan` keeps one plan for all conversations, just as Open WebUI's process does today. That's fine for a single-user demo. Supporting several users at once would mean storing plans per conversation, which is a later change.
4. **Skill descriptions are slightly long.** LibreChat cuts descriptions longer than 250 characters in the list the model sees; ours are 256 and 302. We'll trim both, for both runtimes (step 0).
5. **Chat titles:** LibreChat makes one small extra model call to title each chat. That's useful for history; leave it on.
6. **Gemini:** today Gemini models reach Open WebUI through Google's OpenAI-compatible endpoint. The generator would add the same endpoint as a LibreChat custom endpoint and pick it when `LLM_MODEL_ID` starts with `gemini`. It's a few lines, so we keep current behavior.

---

## Steps

Each step is small and checked before the next.

0. **Trim the skill descriptions** to under 250 characters, then rerun the Strands evals to confirm the results haven't changed. This step doesn't depend on LibreChat.
1. **Trial:** bring up `librechat` + `mongodb` next to the current stack, on a different port, with a hand-written `librechat.yaml`. Check:
   - The spec opens on login, and **New chat** returns to it.
   - The three tools and two skills load.
   - Tool cards show the SQL and its results.
   - A demo question gets the right answer.
   - The chat request that the parity runner will copy, captured from the browser.
2. **Generator:** `agent/librechat_config.py`, with its Tier 1 tests.
3. **Compose and scripts:** replace `openwebui` in `docker-compose.yml`, `start.sh`, `stop.sh` and `.env.example`, then check a fresh clone with `./start.sh`.
4. **Parity runner:** `tests/librechat_runtime.py`, then `EVAL_RUNTIME=librechat pytest -m agent`, comparing the results with Strands and with the last Open WebUI report.
5. **Clean up and update the docs:** remove the Open WebUI files, then update README, AGENTS.md and the notebook text.

Estimate: **3–5 days.** Most of the uncertainty is in step 4: the exact request format, and how the suffixed tool names affect the evals.

---

## Decisions (agreed in review)

1. **Admin password:** the default becomes `admin@tcg.com` / `glassbox`. It meets LibreChat's 8-character minimum, so `MIN_PASSWORD_LENGTH` stays unchanged. `start.sh` prints the login, as it does today.
2. **Other models:** keep the plain Luna / Terra / Sol models selectable next to Glass Box FDA (`interface.modelSelect: true`, with the allowlist in `OPENAI_MODELS`). Hiding them for OMB comes later, with the rest of the customization.
3. **Port:** LibreChat's default, `3080`.
4. **Skill descriptions:** trim both to under 250 characters, a change that also applies to Strands. Then rerun the Strands evals (`pytest -m agent`) to confirm the results haven't changed before moving on.
5. **AGENTS.md:** update it in the same change. This is a permanent replacement, so when the work is finished nothing in the repo should still refer to Open WebUI, apart from the `Open_WebUI_First_Demo` tag.

## Branch

The work is done on a feature branch, `librechat`, and merged into `main` through a pull request once the Tier 1 tests and the LibreChat parity evals pass. `main` stays a working demo throughout.
