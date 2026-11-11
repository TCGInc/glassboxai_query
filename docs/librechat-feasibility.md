# LibreChat Feasibility Assessment: OMB DB Query Agent

**Prepared:** November 9, 2026
**Scope:** Whether LibreChat can host the Glass Box DB Query agent with OMB branding, a locked-down "DB Query only" experience, a reproducible Docker deployment, and external authentication, without an enterprise license.
**Method:** Review of the LibreChat documentation, its release notes, and its source code (stable `v0.8.8` and the current `main` branch). Nothing has been installed or run yet. Items marked **To verify** need a short hands-on trial.

---

## Summary

LibreChat can deliver everything OMB has asked for, using the open-source (MIT-licensed) edition. Most of the work is **configuration**: settings in `.env` and `librechat.yaml`. The remaining branding is a light **customization**: a small custom Docker image that adds a stylesheet, a logo and favicons. No fork of LibreChat is needed.

| Area | Difficulty | Estimated effort | Type of change |
|---|---|---|---|
| Set up the agent (system prompt, skills, tools) | Moderate | 2–4 days | Configuration, plus a small tool server and a provisioning script |
| Lock users into the DB Query agent | Easy | about 1 day | Configuration |
| Branding: title, logo, colors, look and feel | Easy to moderate | 1–2 days | Configuration (title) and customization (logo, CSS) |
| Docker deployment with agent and branding built in | Moderate | 1–2 days | Docker Compose and a thin custom image |
| User accounts: manual first, Keycloak later | Easy | under 1 day | Configuration |

**Overall estimate:** about 1.5–2 weeks to reach a provisioned, branded, locked-down LibreChat stack that passes the same automated test suite as the current runtimes. We recommend starting with a 2–3 day trial build to resolve the **To verify** items.

**Main risks:**

1. **Agents cannot be defined in configuration files.** LibreChat stores agents in its database. Automated setup depends on a management API that is still in beta, or on undocumented internal APIs.
2. **The supported deployment-wide color theme isn't in a stable release yet.** It is in the `v0.8.9` release candidate. On stable `v0.8.8`, colors are changed with a custom stylesheet, which works but must be re-checked at each upgrade.
3. **LibreChat moves fast.** It ships releases every few weeks. We should pin a version and upgrade on purpose.

---

## Background

Open WebUI, the current demo interface, needs an enterprise license for branding changes such as a custom logo, title and colors, and for hiding model selection from regular users. LibreChat was the original alternative under consideration. It is MIT-licensed and supports these changes in the open-source edition.

**Versions reviewed:**

- `v0.8.8`: the latest stable release (October 1, 2026)
- `v0.8.9-rc1`: a release candidate (October 26, 2026), which adds the deployment-wide color theme

---

## 1. Setting up the DB Query agent

The agent is the same in every runtime: one system prompt, two informational skills (`database` and `terminology`), and three tools (`run_query`, `create_plan`, `complete_step`).

### Tools: moderate

- LibreChat connects agents to outside tools through **MCP servers** (Model Context Protocol, a standard way to expose tools to an agent).
- We would wrap the existing Python tool code in a small MCP server and run it as its own container. The tool logic stays the same and only gets a new wrapper, just as the Open WebUI integration wraps it today.
- The tool server keeps connecting to Postgres as the read-only `agent_ro` role. That role remains the real security control.
- LibreChat blocks connections to private network addresses by default, to protect against server-side request forgery (SSRF). The tool server's container name must be listed in `mcpSettings.allowedAddresses` (or `allowedDomains`).
- **Design fix needed:** `create_plan` stores the plan in one shared variable. If several users share one tool server, their plans will overwrite each other. Open WebUI has the same issue today, but it matters with real users. The plan should be stored per session.

### Skills: easy

- LibreChat supports `SKILL.md` files natively, since about `v0.8.6`.
- Administrators can provide skills from a folder on the server. LibreChat loads them as read-only skills, so they stay in sync with the source files.
- A skill can be loaded on demand, the way the AWS Strands runtime does it, or injected in full with `always-apply: true`, the way the Open WebUI runtime does it. Either choice keeps the skill text identical across runtimes.
- Skills are attached to the agent with the agent's Skills setting, set to **Selected**.

### System prompt and agent definition: moderate (main gap)

- Agents live in LibreChat's MongoDB database and **cannot be declared in `librechat.yaml`**.
- To keep one source of truth for the prompt, skills and tools, we need a provisioning script, like the one that sets up Open WebUI today. The script creates or updates the agent from the project files.
- **Provisioning options:**
  - **Agent Management API (beta):** create, read, update and delete agents and skills. It authenticates with a machine OIDC client, an account an automated service signs in with, so it needs an identity provider such as Keycloak.
  - **LibreChat's internal API** (the one its web interface uses): this works without an identity provider, but isn't documented and may change between versions.
- LibreChat assigns each agent an ID (for example `agent_abc123`), and the configuration must name that ID. Provisioning is therefore two steps: create the agent, then write its ID into `librechat.yaml` and restart.

### Automated testing

- LibreChat's beta Agents API is OpenAI-compatible and runs the tools on the server.
- That should make the cross-runtime parity test simpler for LibreChat than it is for Open WebUI.

### Transparency (Glass Box)

- Tool calls appear in the chat as cards that expand to show the tool's **input** (the SQL query) and **output** (the result rows).
- Users can see exactly what the agent ran, in line with the Glass Box principle "people can inspect the AI's work and limits."

---

## 2. Putting users directly into the DB Query agent

Once a user signs in, they should land in the DB Query agent rather than a general-purpose chat. Five pieces are needed. All of them are configuration.

### 2.1 Share the agent with all users (required)

- Agents are private to the account that created them. LibreChat hides any agent a user can't access, even when the configuration names it.
- The agent must be shared as **Viewer** with the `USER` role, or with everyone.
- Viewers can chat with the agent but can't see or change its prompt, tools or skills.
- **To verify:** the provisioning script must do this sharing step too, and the management API docs don't yet show a sharing route.

### 2.2 Make the agent the default and only choice

```yaml
modelSpecs:
  enforce: true
  prioritize: true
  list:
    - name: db-query
      label: "DB Query"
      description: "Ask questions about FDA inspections, citations and recalls."
      default: true          # selected on every new chat
      showOnLanding: true    # label and description replace the generic greeting
      iconURL: /assets/omb-agent.svg
      preset:
        agent_id: agent_xxx  # written by the provisioning script
```

Also set `ENDPOINTS=agents` in `.env` so no other AI providers are offered.

**To verify:** that the **New chat** button always returns to the DB Query agent. The documentation implies it but doesn't say so directly.

### 2.3 Lock down the agents endpoint

```yaml
endpoints:
  agents:
    disableBuilder: true          # no agent builder for users
    allowedProviders: [openAI]
    capabilities: [tools, skills] # drops web search, code execution, file search,
                                  # memory, subagents and other built-in tools
    recursionLimit: 25
    maxRecursionLimit: 25
```

Trimming `capabilities` keeps the agent to its own three tools and its skills. This matches the project rule of three tools, two skills and one system prompt.

### 2.4 Remove generic chat features from the interface

```yaml
interface:
  modelSelect: false
  parameters: false
  presets: false
  multiConvo: false
  agents: { use: true, create: false, share: false, public: false }
  marketplace: { use: false }
  prompts: false
  memories: false
  webSearch: false
  fileSearch: false
  runCode: false
  mascot: false
  landingHeading: entity
  customWelcome: "Welcome to OMB DB Query, {{user.name}}"
```

- **Conversation history stays.** It is useful to analysts, who return to earlier questions and answers.
- These settings set up the default `USER` role's permissions when LibreChat starts. Later changes made in LibreChat's Admin Panel take precedence, so whoever administers the deployment should know this.

### 2.5 Landing page

- The agent can have up to four **conversation starters**: buttons on the empty chat screen that send a prepared question. The four current demo questions fit exactly, and each is already covered by the automated tests.
- The model spec's icon gives the agent its own image in the header and on its messages.
- Login: see section 5.

### What configuration can't hide

- The sidebar (conversation history, search, bookmarks) and the user settings menu remain.
- If a more stripped-down screen is wanted, the custom stylesheet can hide specific elements. This kind of change has to be re-checked at every upgrade, so it should be kept small.

### A trade-off to discuss

Viewer access hides the system prompt and skills from users, which is in some tension with the Glass Box goal of letting people inspect the AI's limits. The SQL and results stay fully visible through the tool cards. If OMB wants users to see the prompt and skills too, a footer or welcome-text link to a read-only page can provide that without giving users edit access.

---

## 3. Branding and look and feel

OMB wants the DB Query environment to look distinct from its existing chatbots. The changes split into **configuration**, which is supported settings, and **customization**, which means adding files to the Docker image.

### Configuration (supported settings)

| Item | Setting |
|---|---|
| Application title | `APP_TITLE` in `.env` |
| Welcome message | `interface.customWelcome` |
| Footer text and links | `CUSTOM_FOOTER` in `.env` |
| Help link | `HELP_AND_FAQ_URL` in `.env` |
| Privacy policy and terms of service | `interface.privacyPolicy`, `interface.termsOfService` (terms can require acceptance on first use) |
| Agent icon | `modelSpecs.list[].iconURL` |
| Login button text and image (Keycloak) | `OPENID_BUTTON_LABEL`, `OPENID_IMAGE_URL` |
| Color theme (from `v0.8.9`) | `interface.theme` in `librechat.yaml` |

### Customization (a thin custom image)

| Item | Approach |
|---|---|
| Logo | Replace `/app/client/dist/assets/logo.svg` |
| Favicons and app icons | Replace the `favicon-*.png` and `apple-touch-icon*.png` files in `/app/client/dist/assets/` |
| Browser tab title and description | Edit `/app/client/dist/index.html` |
| Name shown when the app is installed on a device | Replace `manifest.webmanifest` |
| Colors and splash styling (on `v0.8.8`) | Add `omb-theme.css` and link it from `index.html` |

These steps fit in a few lines of a Dockerfile built on the official LibreChat image. The client application does not need to be rebuilt.

LibreChat has no supported logo setting yet. A documentation proposal for a `branding` section (logo, favicon, title) exists but hasn't been merged.

### How color customization works

- Every color in LibreChat's interface comes from a named CSS variable, about 200 of them, defined once for light mode and once for dark mode. Examples are `--surface-primary`, `--accent-primary`, `--button-primary`, `--link` and `--header-primary`.
- These names build on base color scales such as `--gray-*`, `--green-*` and `--blue-*`. Each color is written as three numbers, for example `--accent-primary: 29 78 216`.
- A stylesheet loaded after LibreChat's own CSS can redefine these variables to recolor the whole application, including the login page.
- In practice this means redefining the base scales and about 15–20 key named colors (accent, buttons, header, links, focus rings), then checking the main screens in light and dark mode.
- LibreChat reads `index.html` from its built files when it starts, so an edited `index.html` with the added stylesheet link takes effect.

### Splash styling for launch

If OMB wants a distinctive launch look, a temporary stylesheet is a good fit. Examples include a branded landing banner, a background treatment or a distinct accent color. It can be added or removed by changing one file, with no change to the application.

### Things to watch

- **Upgrades:** variable names change between versions. Between `v0.8.8` and the current `main` branch, the definitions moved to a different file. Each upgrade needs about an hour to check the stylesheet against the new names.
- **Path to the supported feature:** the `v0.8.9` `interface.theme` setting uses the same variable names and the same three-number format. The custom stylesheet's values can move almost directly into `librechat.yaml`, and the stylesheet can then be dropped.
- **Browser caching:** static files are cached for 2 days by default (`STATIC_CACHE_MAX_AGE`). Putting a version in the stylesheet's file name (for example `omb-theme.v1.css`) makes sure changes reach users. LibreChat's offline cache (its service worker) may keep showing old favicons to anyone who visited before the rebrand. New OMB users are not affected.
- **Accessibility:** LibreChat's high-contrast modes take precedence over any theme. They should be left unchanged, which supports Section 508 compliance.

### Options we don't recommend

- **Rebuilding the client with `REACT_APP_THEME_*` build settings:** this changes the same color variables but requires a full client build and covers colors only.
- **Forking LibreChat's source:** this creates an ongoing maintenance burden given how often LibreChat releases.

---

## 4. Docker deployment

### Services

| Service | Purpose |
|---|---|
| `api` | LibreChat, the web application and server. It would be our thin custom image. |
| `mongodb` | LibreChat's own database: users, conversations, agents, skills |
| `meilisearch` | Search across conversation history |
| `fda-tools` (new) | The MCP server that wraps the three agent tools |
| `postgres` (existing) | The FDA dataset, accessed only as the read-only `agent_ro` role |

LibreChat's optional file-search services (`rag_api` and its vector database) aren't needed, because the agent doesn't use file search.

### Configuration and startup

- Configuration lives in `.env` and a mounted `librechat.yaml`. The skills folder is also mounted.
- A startup script, like the current `start.sh`, would:
  1. Start the stack.
  2. Run the provisioning script to create or update the agent, its skills and its sharing.
  3. Write the agent's ID into `librechat.yaml` and restart LibreChat.
- Any change to `librechat.yaml` requires a LibreChat restart.
- LibreChat exits on startup if `librechat.yaml` has a validation error. This catches configuration mistakes early.

### Versions

- Pin the LibreChat image to an exact version, for example `v0.8.8`, and upgrade on purpose. Each upgrade should include a re-run of the automated tests and a check of the custom stylesheet.

### Effort

About 1–2 days. This assumes the tool server and provisioning script from section 1 are done.

---

## 5. User accounts and authentication

### Phase 1: manually provisioned users

- Turn off self-registration with `ALLOW_REGISTRATION=false` and keep `ALLOW_EMAIL_LOGIN=true`.
- Administrators manage accounts with LibreChat's built-in command-line scripts, run inside the container. For example:

```bash
docker compose exec api npm run create-user
```

- Other built-in scripts: `list-users`, `reset-password`, `ban-user`, `delete-user` and `invite-user`. The invite script needs email configured.
- Users sign in on LibreChat's own login page, which carries the OMB branding.

### Phase 2: Keycloak (recommended for production)

- Supported natively through OpenID Connect (OIDC), and LibreChat publishes a Keycloak setup guide.
- **Basic setup:** create an OIDC client in a Keycloak realm, then set `OPENID_ISSUER`, `OPENID_CLIENT_ID`, `OPENID_CLIENT_SECRET`, `OPENID_SESSION_SECRET`, `OPENID_CALLBACK_URL`, `OPENID_SCOPE` and `ALLOW_SOCIAL_LOGIN=true`.
- **Access control:**
  - `OPENID_REQUIRED_ROLE` restricts sign-in to users with specific Keycloak roles. For Keycloak, the roles are read from `realm_access.roles`.
  - `OPENID_ADMIN_ROLE` makes holders of a Keycloak role LibreChat administrators.
  - Role sync (`OPENID_ROLE_SYNC_*`) can map other Keycloak roles to LibreChat roles.
- **Sign-in experience:** with `OPENID_AUTO_REDIRECT=true` and email login turned off, users skip LibreChat's login page. They sign in through Keycloak and land directly in the DB Query agent.
- **Sign-out:** `OPENID_USE_END_SESSION_ENDPOINT=true` also ends the Keycloak session.
- **Provisioning benefit:** Keycloak also provides the machine OIDC client that the Agent Management API needs. That makes the supported provisioning route from section 1 available.
- **Limit:** only one OIDC provider can be configured.

### Alternatives

- **LDAP:** supported natively (`LDAP_URL`, bind account, search base and filter, TLS options). Users sign in on LibreChat's login form with their directory credentials.
- **SAML:** supported, but it is disabled automatically when OIDC is configured.

### Effort

- Manual users: under an hour of configuration.
- Keycloak: half a day to a day, assuming a Keycloak realm is available.

---

## Recommended next steps

1. **Trial build (2–3 days).** Stand up LibreChat `v0.8.8` locally with the tool server, and settle the open questions:
   - Can the agent be shared with all users from the provisioning script?
   - Does **New chat** always return to the DB Query agent?
   - Do the logo, favicon and stylesheet overrides work in the official image?
   - Do the tool-call cards show the SQL and results as expected?
2. **Decide on the version.** Stable `v0.8.8` with the custom stylesheet, or `v0.8.9` (in release candidate) with the supported `interface.theme` setting.
3. **Get OMB's brand assets.** Logo (SVG), favicon, color palette, and any splash or landing styling.
4. **Build:** tool server, provisioning script, Docker Compose, custom image, and a LibreChat runner for the automated tests.
5. **Keycloak** when OMB is ready to move from manually provisioned users.

---

## References

- LibreChat documentation:
  - Agents: https://www.librechat.ai/docs/features/agents
  - Agents API and Agent Management API: https://www.librechat.ai/docs/features/agents_api
  - Skills: https://www.librechat.ai/docs/features/skills
  - MCP: https://www.librechat.ai/docs/features/mcp
  - MCP settings (network restrictions): https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/mcp_settings
  - Agents endpoint configuration: https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/agents
  - Model specs: https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/model_specs
  - Interface configuration: https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/interface
  - Theme: https://www.librechat.ai/docs/configuration/librechat_yaml/object_structure/theme
  - Environment variables: https://www.librechat.ai/docs/configuration/dotenv
  - Keycloak: https://www.librechat.ai/docs/configuration/authentication/OAuth2-OIDC/keycloak
  - Docker: https://www.librechat.ai/docs/local/docker
- LibreChat source and releases:
  - Releases: https://github.com/danny-avila/LibreChat/releases
  - Dockerfile: https://github.com/danny-avila/LibreChat/blob/main/Dockerfile
  - Community UI customization guide: https://github.com/danny-avila/LibreChat/discussions/6288
  - Proposed branding configuration (unmerged): https://github.com/LibreChat-AI/librechat.ai/pull/557
