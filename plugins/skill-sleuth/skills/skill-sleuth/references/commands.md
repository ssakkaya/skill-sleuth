# Commands: binary, plugin CLI, slash commands, settings.json, claude.ai, copying, Windows

## When to read
- When you decide to install, enable or copy a skill/plugin, or to look at the inventory of a plugin that is not installed.
- When you need to tell the user `/reload-plugins`, `/reload-skills` or the claude.ai steps (ready-made sentences in §3 and
  §5).
- When `claude` or `python` gives an encoding/path error in Bash/PowerShell, or when no Python can be found at all (§7).

Contents: §1 Binary · §2 Commands · §3 Slash · §4 settings.json · §5 claude.ai · §6 Copying · §7 Windows

Abbreviations: `MKT` = `~/.claude/plugins/marketplaces/claude-plugins-official`, `LAMS` =
`<data>/local-agent-mode-sessions`. "(unverified)" = open question; hedge it. "Measurement environment" = Windows 11, desktop
app, 2026-10.

Directory rule (the offline scripts `skill_ara.py`, `skill_envanteri.py`, `katalog_indeksle.py` apply the same one):
- `<data>` = the desktop app's data directory: `CLAUDE_DESKTOP_DATA_DIR` when set, as is; otherwise on Windows the first
  that holds a `local-agent-mode-sessions` folder: `%APPDATA%/Claude`; `%LOCALAPPDATA%/Claude-Data/<id>` (observed
  2026-10-22; of several, the one whose `local-agent-mode-sessions` changed last);
  `%LOCALAPPDATA%/Packages/Claude_<suffix>/LocalCache/Roaming/Claude` (MSIX, observed 2026-10-14); if none does,
  `%APPDATA%/Claude`. macOS `~/Library/Application Support/Claude` (unverified); Linux `$XDG_CONFIG_HOME/Claude`,
  or `~/.config/Claude` when that is unset too (unverified). The macOS and Linux locations were not tested on a real machine.
- `~/.claude` = the Claude Code configuration directory: on every operating system `$CLAUDE_CONFIG_DIR`, or `~/.claude` when
  it is not set. Every path written as `~/.claude/...` in this file resolves by this rule.
- `<plugins>` = the plugins root: `$CLAUDE_CODE_PLUGIN_CACHE_DIR` when set, else `~/.claude/plugins` (by the rule above). The paths
  written as `~/.claude/plugins/...` in this file (`installed_plugins.json`, `cache/`, `marketplaces/`, `plugin-catalog-cache.json`)
  live under `<plugins>`.
- Cache: %TEMP%\skill-sleuth on Windows (Python `tempfile.gettempdir()`; `%TEMP%` is per-user), ~/.cache/skill-sleuth on
  macOS/Linux (`$XDG_CACHE_HOME/skill-sleuth` when `$XDG_CACHE_HOME` is set; created with mode 0700). A cache directory or file not
  owned by the current user, or group/world-writable, is not used, and a symlinked temp file is never followed: the script does not
  crash, it runs without the cache and warns. `$SKILL_ARA_CACHE`, `$DIS_KAYNAK_CACHE_DIR`, `--cache`, `--cache-dir`, `--out` remain valid;
  on macOS/Linux they are subject to the same ownership/permission rule (`skill_ara` 0.6.0, `dis_kaynak_ara` 0.4.0).

## 1. Choosing the binary: which `claude` will run

A machine can have two binaries: the bundle binary the desktop session actually runs (`CLAUDE_CODE_EXECPATH`;
under `<data>/claude-code/<version>/`, and from 2.1.286 there may be a hash subdirectory below the version directory) and the npm
install on PATH (may be older; in the measurement environment the bundle was **2.1.284-2.1.286**, npm **2.1.217**). For `install`,
`-y`/`--json`/`--accept-command` exist only in a ≥2.1.271 binary (in the measurement environment only the bundle binary); so use the
environment variable first. Learn the version without running a command: from something like `AI_AGENT=claude-code_2-1-286_agent` (Bash: `echo
$AI_AGENT`).

Bash tool (Windows; verified in the measurement environment; a backslash path passes the `[ -x ]` test):
```bash
EXE="${CLAUDE_CODE_EXECPATH:-}"
[ -x "$EXE" ] || EXE="$(ls -t "$APPDATA"/Claude/claude-code/*/claude.exe "$APPDATA"/Claude/claude-code/*/*/claude.exe "$LOCALAPPDATA"/Claude-Data/*/claude-code/*/*/claude.exe 2>/dev/null | head -1)"   # desktop bundle; 2.1.286+ added a hash subdirectory; Claude-Data observed 2026-10-22
[ -x "$EXE" ] || EXE="$(command -v claude)"      # old npm binary (< 2.1.271): no -y/--json, parse the text (§2 N6)
"$EXE" --version
```
macOS/Linux: without `CLAUDE_CODE_EXECPATH` the same block falls through to `command -v claude`; where the bundle binary lives under `<data>`
on these systems is (unverified).

PowerShell tool (verified with Windows PowerShell 5.1; in the measurement environment the PowerShell tool itself returned exit
code 1 in two sessions; switch to Bash if there is trouble):
```powershell
$EXE = $env:CLAUDE_CODE_EXECPATH
if (-not ($EXE -and (Test-Path $EXE))) { $EXE = (Get-ChildItem "$env:APPDATA\Claude\claude-code","$env:LOCALAPPDATA\Claude-Data\*\claude-code" -Recurse -Filter claude.exe -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName }
if (-not (Test-Path $EXE)) { $EXE = (Get-Command claude).Source }   # npm install (may be old)
& $EXE --version
```
On 2026-10-14 the `CLAUDE_CODE_EXECPATH` MSIX path (`...\Packages\Claude_<suffix>\LocalCache\Roaming\...`) and the Roaming
copy were the same file. On 2026-10-22 (observed) the app moved its data to `%LOCALAPPDATA%\Claude-Data\<id>\`:
`CLAUDE_CODE_EXECPATH` points to `claude-code\<version>\<hash>\claude.exe` there, and the two old folders keep only an
empty `.user-data-left.<id>` marker file. Both blocks look under `%APPDATA%\Claude` and `%LOCALAPPDATA%\Claude-Data\<id>`.

## 2. Command table (`claude plugin …`; `claude plugins` is an alias)

Below, `claude` = the `"$EXE"` from §1. The "Session" column = when the change reaches the running session; `/reload-plugins` =
the user types it, or a new session (plugin containing an MCP server: new session only).

| Command | What changes on disk | Output / exit | Session | Consent |
|---|---|---|---|---|
| `plugin list [--json]` | nothing (npm: `.in_use/<pid>` trace) | JSON array → N1 | — | no |
| `plugin list --json --available` | nothing, no network | `{installed,available}`, large (142 KB in the measurement) → N2 | — | no |
| `plugin details <name>@<market>` (installed) | nothing | inventory + `Always-on ~N tok`; exit 0 | — | no |
| same, plugin not installed | nothing | `Plugin "…" not found`, exit 1 → N3 | — | no |
| `--plugin-dir MKT/plugins/<name> plugin details <name>` | nothing | same inventory, source `<name>@inline` | — | no |
| `plugin install <name>@<market> -s user\|project\|local --json` | N4 | last line JSON → N5 | `/reload-plugins` | **yes** |
| `plugin uninstall <name>@<market> [-s] --json` | record + `enabledPlugins` removed → N8 | JSON | same | yes |
| `plugin enable\|disable <name>@<market> [-s] --json` | `enabledPlugins` value | JSON | same | yes |
| `plugin marketplace update [name]` | clone git fetch; `known_marketplaces.json` | text | — | yes (network) |
| `plugin marketplace add <source>` | `extraKnownMarketplaces`, `known_marketplaces.json`, clone | text | — | yes |
| `plugin marketplace remove <name>` | the marketplace record + EVERY plugin installed from that marketplace is uninstalled, `enabledPlugins` entries removed | text | `/reload-plugins` | **yes** (say so in the rollback sentence) |
| `plugin update <name>@<market>` | new version into the cache; the way updates arrive on community and third-party marketplaces (auto-update off by default) | text | `/reload-plugins` | yes (review the new sha first) |
| `plugin prune` | auto-installed dependencies that no plugin needs any more are removed | text | `/reload-plugins` | yes |
| `plugin validate <path> [--json] [--strict]` | nothing | → N7 | — | no |
| `plugin init <name>` | `~/.claude/skills/<name>/` plugin skeleton (`@skills-dir`) | text | next session | yes |

Notes:
- **N1** `list --json`: `[{id, version, scope, enabled, installPath, installedAt, lastUpdated}]`. In text mode, groups:
  Installed / Session-only / Skills-directory / Synced. Installed ≠ enabled: enablement comes from `enabledPlugins`.
- **N2** `--available`: reads from the clone's `marketplace.json` (installed ones excluded; in the measurement environment a clone dated 2026-07,
  254 records), no network.
  Fields `pluginId,name,description,marketplaceName,source,installCount,version?`. Do not print it into context; filter with Python:
  ```bash
  "$EXE" plugin list --json --available | python -c \
    "import json,sys; d=json.load(sys.stdin); print([p['pluginId'] for p in d['available'] if 'NAME' in p['name']])"
  ```
  Newer and richer data (components, hook/MCP names, token cost; 315 plugins on the measurement date)
  is in `~/.claude/plugins/plugin-catalog-cache.json`; `skill_ara.py` already reads it, do not open it by hand.
- **N3** `details` refuses a plugin that is not installed (2.1.217 and 2.1.284 alike). Fix: the top-level `--plugin-dir` flag, BEFORE the
  subcommand (`plugin details --plugin-dir X` → `unknown option`). Only for plugins whose files are in the clone
  (`./plugins/*`, `./external_plugins/*`); for `git-subdir`/`url` sources look at the catalog cache.
  The folder-of-plugins form also works: `--plugin-dir MKT/plugins plugin details <name>`. It changes no state (verified with
  a diff).
- **N4** `install` on disk: `~/.claude/plugins/cache/<market>/<name>/<sha12>/`, an `installed_plugins.json` record; the plugin's declared
  dependencies are installed and enabled at the same scope too (the success message lists them; one from another marketplace only if allowlisted),
  `enabledPlugins` → `-s user`: `~/.claude/settings.json` · `-s project`: `<cwd>/.claude/settings.json` · `-s local`:
  `<cwd>/.claude/settings.local.json`. The `<name>@<market>` form first refreshes the clone with git (unless it was refreshed in the last 30 s;
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` skips it but installs a stale version); `known_marketplaces.json.lastUpdated` and
  the clone HEAD change. No install rehearsal was done because there was no consent channel: that `-s local` silently creates `.claude/settings.local.json`
  and that the refresh moves the clone to the current sha are (unverified). Do not use `-s user` silently;
  ask the user for the scope with a numbered choice.
- **N5** `--json`: parse only the LAST stdout line: `{command, outcome:"ok"|"failed", message, pluginId, scope,
  failureCode?, shownCommand?, alreadyInGoalState?}` (binary strings + documentation; the real success payload is unverified).
  `failureCode` glossary: `already_in_goal_state` (count as success; `enable` if needed), `not_installed_at_scope`,
  `settings_still_on` (uninstall; ≥2.1.282), `not_found`, `not_found_stale_catalog`, `marketplace_refresh_failed`,
  `command_source_refused|declined`, `entry_helper_unconfirmed|declined`, `settings_write_failed`, `op_failed`.
  If `shownCommand` is present, STOP → N6.
- **N6** The `Kat()` gate: in the Bash tool `CLAUDECODE=1` and `CLAUDE_CODE_CHILD_SESSION=1` are set and there is no TTY →
  for a plugin with a `command`/`headersHelper` source, `-y` and `--accept-command` are ignored ("is ignored inside a Claude Code
  session"), exit 1. NEVER remove the environment variables; give the user the command and `shownCommand.sha256`: in their own
  terminal `claude plugin install <name>@<market> --accept-command <sha256>`. The official marketplace has no such entry
  (0/315 on the measurement date), so official installs never hit this gate. Old npm binary (< 2.1.271; e.g. 2.1.217) fallback:
  `install` has no `-y`/`--json` → look for
  `Successfully installed plugin:` / `is already installed` in stdout; `list --json --available`, `--plugin-dir … details`,
  `validate --strict` work in both versions.
- **N7** `validate`: wants a directory containing a manifest or `skills/`; refuses a folder that directly contains SKILL.md (`No
  manifest found`, exit 1); warns only about a missing `description`; does NOT catch a bad name, `<>`, or an unknown key →
  it is no substitute for `quick_validate.py`. The `init` skeleton "auto-loads next session"; whether it loads live in the same session is
  (unverified).
- **N8** `uninstall`: `data/<id>` is deleted (except with `--keep-data`); `.orphaned_at` is written into the cache directory and cleaned up in the
  background after 14 days; `--prune` wants `-y` without a TTY and does not combine with `--json`. `update <name>`: "Restart to apply" →
  new session.
- Single-session loading: `claude --plugin-dir <dir|.zip>` (`<name>@inline`), `--plugin-url <zip>`,
  `CLAUDE_CODE_PLUGIN_DIRS` (≥2.1.280, `;` separator on Windows). Does not affect the running session; a nested `claude -p` brings cost +
  a `synced/` side effect, avoid it.

## 3. Slash commands only the user can type

These cannot be called with the `Skill` tool and are not in the listing; the user types them into the prompt box. Desktop UI path: **+ → Plugins →
Add plugin / Manage plugins**; `/` or the **+ → Slash commands** menu.

| Command | What it does | Sentence to say (verbatim) |
|---|---|---|
| `/reload-plugins [--force]` | reloads the plugin layer; prints `Reloaded: N plugins · N skills · …` | C1 |
| `/reload-skills` | rescans the skill directories; prints the number added/removed | C2 |
| `/plugin`, `/plugin install <name>@<market>` | the Discover panel; opens the detail panel and installs once a scope is chosen | C3 |
| `/skills` | writes visibility into `skillOverrides`: on / name-only / user-invocable-only / off | C4 |

- C1 (after install/enable/disable/uninstall): "Install done. Please type `/reload-plugins` into the prompt box and send it;
  when I see the `Reloaded: …` line I will call `<plugin>:<skill>`. If the plugin contains an MCP server, a new session is needed."
  Facts: on desktop/`-p` it works only when the user types it (≥2.1.260); when it comes over Remote Control/Slack: "isn't
  available over a remote connection"; it does not apply MCP changes. Hot reload of a plugin install was not observed.
- C2 (when you created `<cwd>/.claude/skills/` and it did not exist at session start): "I put the skill under `<cwd>/.claude/skills/<name>/`,
  but this directory did not exist at session start. Please type `/reload-skills`, then I will continue." Whether it behaves in the desktop
  prompt box as in the terminal is (unverified) — if it does not work, switch to the personal layer (§6).
- C3: "If you like, you can also type `/plugin` and install `<name>` yourself from Discover; it installs once you pick a scope." `/plugin` does not exist in `-p`
  mode.
- C4: "If the skill does not show in the listing, type `/skills` and set the visibility for `<name>` to `on`." Others: `/skill-doctor`,
  `/context`, `/doctor`, `/mcp` — for diagnosis; only the user types them.

## 4. `settings.json` keys (read-only for the skill)

File: `~/.claude/settings.json` (every key is optional; on a fresh install `skillOverrides`, `permissions`,
`hooks` may be absent entirely). Read `enabledPlugins` merged user < project < local (a file with a BOM too). This reads
only the cwd's files; for the full view that also counts the git root's `settings.local.json` on macOS/Linux: `skill_ara.py --show <plugin>`:

```bash
PYTHONUTF8=1 python -c "import json,os;d=os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude');e={};[e.update(json.load(open(f,encoding='utf-8-sig')).get('enabledPlugins') or {}) for f in (os.path.join(d,'settings.json'),'.claude/settings.json','.claude/settings.local.json') if os.path.isfile(f)];print(e)"
```

Rule: never write this file or `.claude/settings*.json` directly. If a change is needed, get numbered consent in that turn;
leave the writing to a `claude plugin …` command or to the `update-config` built-in.

| Key | Format | Who writes it | Note |
|---|---|---|---|
| `enabledPlugins` | `{"<name>@<market>": true\|false}` | `plugin install/enable/disable` | precedence: below |
| `extraKnownMarketplaces` | `{name: {source, autoUpdate?}}` | `plugin marketplace add` | persistent setting + network → consent |
| `skillOverrides` | `{name: on\|name-only\|user-invocable-only\|off}` | `/skills` (user) | does not apply to plugin skills |

`enabledPlugins` precedence: `--add-dir` < user < project < local < `--settings` < managed; a remote plugin that is `true` only in the project
file is not downloaded. Other related keys: `skillListingBudgetFraction` (0.01),
`skillListingMaxDescChars` (1536), `syncClaudeAiSkills`/`syncClaudeAiPlugins` (`false` → `.trash/`),
`permissions.allow/deny` (`Skill(name)` rules), `disableSkillShellExecution`. Other registry files:
`~/.claude/plugins/installed_plugins.json` (v2), `known_marketplaces.json` — both read-only.

## 5. The claude.ai side (the user does it)

Claude cannot change an account setting; it only shows a card (`SuggestSkills`/`SuggestPluginInstall`, at most once per
item) and states the step. Sentence: "I cannot turn this on myself. In claude.ai, turn on `<name>` from the **Customize > Skills** page (**Customize > Plugins** for a plugin);
sync takes about 10 minutes, open a new session if it does not arrive. Meanwhile I am continuing the task directly."

- Turning a skill on: **Customize > Skills** → toggle. Prerequisite: **Settings > Capabilities > Code execution and file creation**.
  "Disabled skills won't be available to Claude." Enabled skills also reach Claude Code under the same account (terminal
  ≥2.1.273).
- Uploading a skill: **Customize > Skills > + > Upload a skill** → zip; the top folder = the skill name (`<name>/SKILL.md`).
- Plugin: **Customize > Plugins** → Discover / Add marketplace (`owner/repo`) / Upload plugin (.zip/.plugin; 25
  marketplaces, 5,000 files / 200 MB). Reaches Claude Code as `<name>@synced`; ones installed with the CLI are not added to the account.
- Platform: skills everywhere; agents/hooks only Cowork + Claude Code; local MCP only Cowork (local) + Claude Code;
  `bin/`, LSP, output style only Claude Code.
- Connector (claude.ai connector directory; `sources.md` row 17): the user does the connecting, with Connect on the
  `suggest_connectors` card (at most one card per task) and, if the service shows one, its own consent (OAuth) screen
  (that every service shows a consent screen is unverified). Claude does not connect or turn it on, and asks for no token
  or credential. Whether a connector connected through the card reaches the running session is unverified; if not, a new
  session. Connected on the account but off in this session → the user turns it on from the session's connector settings
  or in a new session (unverified). A server awaiting authorization (the system note's "require authentication"): the
  claude.ai connector settings or `/mcp` (SKILL.md Step 1). A server that failed to connect (the system note's "configured
  but failed to connect"): say "<server> failed to connect; fix or retry it with `/mcp` or the claude.ai connector
  settings"; the repair belongs to `/mcp` and `ai-tools-setup`; no directory search, no card.

`synced/` folder facts:
- Path `~/.claude/skills/synced/<org>_<account>/<name>/SKILL.md` + `manifest.json`
  (`skillId,name,description,source,updatedAt`); appears in the Skill listing as `anthropic-skills:<name>`.
- Refreshed about every 10 min (documentation value; not measured) and sync overwrites → **never edit by hand**,
  never copy a skill there; the names `synced` and `anthropic-skills` are reserved.
- In the measurement environment `~/.claude/plugins/synced/` stayed empty; the sync of claude.ai plugins (e.g. `legal:*`, `data:*`) to the
  terminal is (unverified). In terminal mode read these skills from the path `<data>/rpm/<account8>/<org8>/plugin_<id>/skills/<name>/SKILL.md`
  (observed 2026-10-22; `<account8>` / `<org8>` = the first 8 hex digits of the ids) or the older
  `LAMS/<account>/<org>/rpm/plugin_<id>/skills/<name>/SKILL.md` (`LAMS` = `<data>/local-agent-mode-sessions`, the directory rule above).
- Skills that are off / not uploaded on the account are not on disk; only `SearchSkills` sees them (`enabled:false`).

## 6. Copying a skill folder under `~/.claude/skills/<name>/`

Writing into the user directory needs consent: offer a numbered choice in that turn and do not copy before an explicit "yes" arrives. Why the personal
layer? `~/.claude/skills/` exists at session start and is watched live; the project layer is not live when the directory is created
later.

```bash
cp -r "<source>" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/<name>"            # Bash
```
```powershell
Copy-Item -Recurse "<source>" "$env:USERPROFILE\.claude\skills\<name>"   # PowerShell; if CLAUDE_CONFIG_DIR is set, "$env:CLAUDE_CONFIG_DIR\skills\<name>"
```
- Contents: only `SKILL.md` + `references/` + `scripts/` + `assets/`. Do not copy `evals/`. Do NOT add `.claude-plugin/plugin.json`
  (it turns into an `@skills-dir` plugin and waits for the next session). Folder name = frontmatter `name` = kebab-case; the listing
  shows the folder name.
- Poll, do not assume: `Skill("<name>")` at ~10 s intervals, for at most 60 s (in the measurement environment: unknown at 12 s, loaded at 40 s;
  others ≤25 s).
  - `Launching skill: <name>` → loaded; the body comes with `Base directory for this skill: <path>`.
  - `Unknown skill: <name>` (no suggestion) → not registered yet, keep polling.
  - `Unknown skill: X. Did you mean Y?` → `Y` is registered; call it only if it is the name of the folder you copied (prefix difference aside);
    if it is a different skill, keep polling, and after 60 s path A.
  - the "The following skills are available…" notification → registered, call it right away.
- The project layer only if `test -d "<cwd>/.claude/skills"` was true at session start and the skill must travel with the repo; otherwise
  C2.
- If it does not arrive within 60 s: read SKILL.md, tell yourself `Base directory for this skill: <path>`, resolve relative paths against that
  directory and apply; tell the user once about `/reload-skills`.
- Editing is live (≤19 s), deletion is live and silent (~30 s). No watcher in bare mode. Do not touch anything under `synced/`.

## 7. Windows pitfalls

The script call in the two shells (use no other form):
```text
Bash:       PYTHONUTF8=1 python "<skill_dir>/scripts/skill_ara.py" --query "..."
PowerShell: $env:PYTHONUTF8=1; python "<skill_dir>\scripts\skill_ara.py" --query "..."
```

| Pitfall | Symptom | Do |
|---|---|---|
| cp1254 encoding | mojibake; non-ASCII letters such as `Ş`/`Ğ` → `UnicodeDecodeError` | `PYTHONUTF8=1` before every Python call |
| `PYTHONIOENCODING` alone | stdout is fixed, `read_text()` is not | still `PYTHONUTF8=1` |
| `python3` | Microsoft Store stub, "Python was not found" | on every system the order is `python` → `python3`, on Windows `py -3` last; if `python` is Python 2 (macOS / Linux), `python3`; details below |
| `/c/…` path inside Python | file not found | `C:/…` forward slashes |
| Path with spaces | the shell splits it | double-quote every path |
| `VAR=x cmd` in PowerShell | syntax error | `$env:VAR='x'; cmd` (block above) |
| PowerShell tool | exit code 1, no output (in two sessions in the measurement environment) | prefer Bash (block above) |
| Bash heredoc `<<EOF` | `$` expands, content is corrupted | `<<'EOF'` single-quoted delimiter |
| Bash tool + heredoc with apostrophes | "unexpected EOF" (observed in the measurement environment) | write long non-ASCII or apostrophe-laden text with the Write tool |
| `open`/`xdg-open` | absent | `start "" "<file>"` |
| `subprocess.Popen(["claude"])` | `WinError 2` (`claude.CMD`) | `shutil.which("claude")` + resolve `.cmd` |
| `select.select()` | does not work on pipes | reader thread / `for line in proc.stdout` |
| `CLAUDE_CODE_PLUGIN_DIRS` | path separator | `;` (≥2.1.280) |
| `pyyaml` missing | `quick_validate.py` → `No module named 'yaml'` | the user runs `pip install pyyaml` themselves |

**If no Python can be found.** On every operating system try `python --version`, then `python3 --version`. If `python` gives
Python 2 (macOS / Linux; unverified), move on to `python3`. On Windows, if only the Microsoft Store alias answers (no version,
"Python was not found", or the Store opens) or neither exists, try `py -3 --version` last. Call the scripts the same way with the
first command that gives Python 3 (e.g. `py -3`: Bash: `PYTHONUTF8=1 py -3 "<skill_dir>/scripts/skill_ara.py" …`; PowerShell:
`$env:PYTHONUTF8=1; py -3 "<skill_dir>\scripts\skill_ara.py" …`). If none of them gives Python 3:
- Skip layer 2 (`skill_ara.py`), layer 5 (`dis_kaynak_ara.py --query`) and the star / age check (`--repo`); continue with layers 1, 3
  and 4. The stars and age of a not-installed candidate become "could not be verified"; the elimination rules of
  `external-sources.md` §3.1 apply unchanged (a candidate with installs below the threshold or on a counter-less source is eliminated).
- Write it on the provenance block's Skipped line, e.g. `Skipped: local index (layer 2), third-party search (layer 5), star/age
  check — Python not found`.
- Suggest that the user install Python 3.9 or later (so that `python` is on `PATH`); do not install it yourself, run no command.
  The PATH change after the install usually needs a new session (unverified).
- Do not hunt for Python elsewhere (scanning random directories for `python.exe`, downloading); saying it was not found is enough.

## 8. Optional: a reminder hook on every turn (unverified)

The description alone cannot guarantee every turn: in the 2026-10-02 trigger measurement (40 queries, `claude -p` 2.1.284), on jobs that clearly matched a skill
in the listing the model went straight to that skill even when told "find and use the appropriate skill" (~half of the positives).
The official documentation rule: "a rule that must hold every time → hook". If the user wants, the following hook can be added to `~/.claude/settings.json`
(only the user writes it; this skill does not touch the settings file, see §4):

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
  "command": "echo Reminder: for a multi-step job or a skill/plugin question, call the skill-sleuth skill first."}]}]}}
```

Notes: the stdout of a `UserPromptSubmit` hook is added to Claude's context on every prompt (documentation); not tried, and
which shell the `echo` output passes through on Windows is also unverified. Hook setup is the job of the `update-config`
built-in; this skill only shows the suggestion.
