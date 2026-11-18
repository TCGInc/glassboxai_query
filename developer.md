# Developer guide: LibreChat look and feel

How the LibreChat demo is branded for the agency it runs for (today: the FDA), and how to change it. Everything lives in `branding/`. LibreChat still runs from its official, unmodified image (AGENTS.md §3).

Checked against LibreChat **v0.8.8**, the version pinned in `docker-compose.yml`. Recheck it when you upgrade (see [Upgrading LibreChat](#upgrading-librechat)).

## What is customized

| What | Where it shows | File |
|---|---|---|
| Chat area: white, with dark text | Chat and new-chat pages (messages, tables, the message box, the bar above) | `branding/theme.css` (the `main:has(#prompt-textarea)` rules) |
| Code boxes: light blue, with dark code text | Code in answers (for example the SQL the agent ran) | `branding/theme.css` (`--surface-code`, `--syntax-*`) |
| Primary buttons, links and focus rings | Login button, send button, links in answers | `branding/theme.css` (dominant color) |
| Sidebar, menus, dialogs, login page | Everywhere outside the chat area | `branding/theme.css` (secondary color) |
| Borders | Everywhere | `branding/theme.css` (accent color) |
| Login-page logo | Top of the login page | `branding/logo.svg` (white version of the logo, for the navy background) |
| Agent icon | Model menu, new-chat screen, next to each answer | `branding/icon.svg` (the logo on a white circle) |
| Application title | Browser tab, login page | `APP_TITLE` in `docker-compose.yml` |
| Welcome text | New-chat screen | `customWelcome` in `agent/librechat_config.py` |

The FDA palette in `theme.css`:

| Role | Share | Color | Used for |
|---|---|---|---|
| Dominant | 60% | `#007cba` | Primary buttons, links and focus rings; pale tints of it for your own messages, table headers and cards |
| Secondary | 30% | `#222c67` | Sidebar, menus, dialogs, login page |
| Accent | 8% | `#a0a0a3` | Borders |
| (chat area) | | `#ffffff` | The page behind messages, so answers, tables and code are easy to read |
| (code boxes) | | `#9196b3` | The secondary navy lightened 50% toward white |

Text is white on the navy areas and near-black (`#212529`) in the chat area. Every syntax color in code boxes has at least 4.5:1 contrast on `#9196b3`. The brand look is the same in LibreChat's light and dark modes. The two **high-contrast** modes (the half-circle button on the login page and in Settings) are deliberately left as LibreChat ships them, for accessibility.

## How it works

LibreChat v0.8.8 has no setting for a logo or colors. (`interface.theme` arrives in v0.8.9.) Instead:

1. `docker-compose.yml` mounts `./branding` read-only into the `librechat` container at `/opt/glassbox/branding`. It also replaces the container's command with `sh /opt/glassbox/branding/apply.sh`.
2. On every start, `branding/apply.sh`:
   - copies `logo.svg` over LibreChat's own `assets/logo.svg`;
   - copies `icon.svg` to `assets/glassbox-icon.svg` and `theme.css` to `assets/glassbox-theme.css`;
   - adds `<link rel="stylesheet" href="assets/glassbox-theme.css?v=<hash>">` to `index.html`, just before `</head>`;
   - runs the image's normal command, `npm run backend`.
3. LibreChat reads `index.html` once, at startup, and serves every page from that copy. The theme stylesheet loads after LibreChat's own stylesheet, so its values win.
4. The Glass Box FDA model spec's `iconURL` (`SPEC_ICON_URL` in `agent/librechat_config.py`) points at `/assets/glassbox-icon.svg`.

Details that matter:
- The copies go into the container's own writable layer, never into the image. `apply.sh` always edits a pristine backup (`index.html.orig`), so restarts don't stack up links.
- The `?v=<hash>` changes whenever `theme.css` changes, so browsers fetch the new stylesheet instead of keeping a cached one.
- `start.sh` restarts LibreChat when anything in `branding/` changes, just as it does when `librechat.yaml` changes.

## Making changes

### Change a color

1. Edit `branding/theme.css`. Values are RGB triplets with spaces and no commas, the format LibreChat uses: `#007cba` is `0 124 186`. One way to convert: `printf '%d %d %d\n' 0x00 0x7c 0xba`.
2. Apply it: run `./start.sh`, which notices the change and restarts LibreChat, or run `docker compose restart librechat`.
3. Reload the page. There is no need to clear the browser cache for the stylesheet.

Keep text readable: aim for a contrast ratio of at least 4.5:1 between text and its background (WCAG AA). Check with any WCAG contrast checker.
- White on `#007cba` (the buttons) is about 4.6:1, so don't make the dominant color any lighter.
- The code-box color is a mid-tone, which is the hardest background for colored text. If you change `--surface-code`, recheck the `--syntax-*` colors next to it; they were darkened just enough to pass on `#9196b3`.

**The chat area is a separate block.** The rules that start with `html:not(.high-contrast) main:has(#prompt-textarea)` apply only inside the chat page's main area, the one that contains the message box. They switch it to a white page with dark text. They don't affect the sidebar, menus, dialogs or the login page, which also uses a `<main>` but has no message box. Inside that block:
- answers (`.markdown`) use LibreChat's typography variables (`--tw-prose-*`); in dark mode LibreChat switches them to light text (`dark:prose-invert`), which the theme turns back;
- code boxes (`.markdown pre`) get every surface variable set to `--surface-code`, and code colors come from `--syntax-*`;
- table headers and inline code use fixed grays in LibreChat, so the theme sets their colors directly.

### Change the logo or agent icon

- **Login page:** replace `branding/logo.svg`. It appears about 40 px tall on the secondary (navy) background, so use a light or reversed version of the logo. Any aspect ratio works.
- **Agent icon:** replace `branding/icon.svg`. LibreChat shows it small (about 20 px) and crops it to a circle, so use a square image with the mark centered and some padding. The current file is the logo path, centered in a 540 × 540 `viewBox` on a white circle.
- Restart LibreChat as above.
- Browsers cache images for up to 2 days (LibreChat's `STATIC_CACHE_MAX_AGE`), so force-reload (Ctrl+Shift+R) to see a new logo right away.

The browser-tab icons (favicons) are still LibreChat's. To brand them too, add `favicon-16x16.png`, `favicon-32x32.png` and `apple-touch-icon-180x180.png` to `branding/`, and copy each one over the file of the same name in `$dist/assets/` in `apply.sh`. LibreChat's offline cache can keep showing the old icon to earlier visitors for a while.

SVG is preferred. A PNG works too: keep the file names `logo.svg` and `icon.svg` (or update `apply.sh`, `SPEC_ICON_URL` and the test). LibreChat serves these files to every visitor, so use only plain image files from a trusted source. An SVG must not contain scripts or links to outside resources.

### Change other parts of the interface

Every color in LibreChat's interface comes from a named CSS variable. To restyle something not covered yet:

1. In the browser, right-click the element and choose **Inspect**. Its classes name the variables it uses. For example, `bg-surface-chat` uses `--surface-chat`, and `text-text-secondary` uses `--text-secondary`.
2. Add that variable to the `html:not(.high-contrast), html.dark:not(.high-contrast)` block in `theme.css`.

To list every variable LibreChat defines:

```bash
docker compose exec librechat sh -c \
  'grep -oE "html\{[^}]*--presentation:[^}]*\}" /app/client/dist/assets/index.*.css | tr ";" "\n"'
```

Variables already set in `theme.css` (light-mode defaults in brackets):

| Variable | Paints |
|---|---|
| `--presentation` | The chat area (white) |
| `--header-primary`, `--header-hover` | The bar above the chat |
| `--surface-primary`, `--surface-primary-alt` | Sidebar, login page, popovers |
| `--surface-chat` | The message box |
| `--surface-code`, `--syntax-text`, `--syntax-keyword`, `--syntax-string`, ... | Code boxes and the colors of code in them (gray-blue, dark text) |
| `--surface-secondary`, `--surface-tertiary`, `--surface-dialog` | Cards, conversation starters, dialogs |
| `--surface-hover`, `--surface-active` | Hover and selected states |
| `--surface-submit` | Primary buttons (green) |
| `--text-primary`, `--text-secondary`, `--text-tertiary` | Text |
| `--border-light`, `--border-medium`, `--ring-primary` | Borders and focus rings |

One exception: LibreChat fills the login and sign-up fields with a fixed white (or near-black) color rather than a variable. The `.webkit-dark-styles` rule at the end of `theme.css` overrides it.

### Rebrand for a different agency

Replace the two SVGs and the color values in `theme.css`. Then update `APP_TITLE` in `docker-compose.yml`, plus the spec label, description and welcome text in `agent/librechat_config.py` if they name the agency. Restart, and check the screens below.

## Checking a change

Look at these screens in both light and dark mode. Switch with the sun/moon button on the login page, or in Settings → General → Theme.
- **Login page:** the logo is visible, typed text in the fields is readable, and the button is on brand.
- **New-chat screen:** the agent icon, the conversation starters and the message box.
- **A conversation:** an answer with a table and a code block (text, table and code readable on the white chat area), and the `ask_user_question` form for an ambiguous question.
- **Open menus:** the model menu (click **Glass Box FDA**), the account menu and Settings.

Then select high contrast and confirm it still looks like stock LibreChat (pure black or white).

The automated checks are in `tests/test_librechat.py`:
- `test_branding_files_are_where_apply_sh_copies_them` (offline) checks that every branding file exists, that `apply.sh` copies it where the configuration expects it, and that the spec uses the icon.
- `test_live_branding_is_the_branding_files` (needs the stack) checks that LibreChat links the theme and serves exactly the current files in `branding/`. If it fails, restart LibreChat.

```bash
docker compose exec jupyter pytest tests/test_librechat.py
```

## Upgrading LibreChat

The theme depends on LibreChat internals that can change between versions: variable names, the `assets/logo.svg` path, the `</head>` tag in `index.html`, the `.webkit-dark-styles` and `dark:prose-invert` classes, the `#prompt-textarea` id, and the `.markdown pre` / `th` markup of answers. After changing the image tag:

1. Run `./start.sh`, then `pytest tests/test_librechat.py`.
2. Go through [Checking a change](#checking-a-change).
3. Compare the variable list (command above) with the one in `theme.css`, and look for new or renamed `--surface-*` and `--text-*` names.
4. Check that the image's command is still `npm run backend`: `docker image inspect <image> --format '{{json .Config.Cmd}}'`. `apply.sh` ends by running it.

**Moving to v0.8.9 or later:** `interface.theme` in `librechat.yaml` takes the same variable names and the same RGB-triplet values. Once on that version, the colors can move into `build_config()` in `agent/librechat_config.py` and `theme.css` can be dropped. The logo still needs `apply.sh` until LibreChat adds a logo setting.
