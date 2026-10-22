#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_ara.py - query-first LOCAL skill index for the skill-sleuth meta-skill (scripts/ directory).
The builtins.json sidecar must sit in the SAME directory as this script (it is looked up next to __file__).

Design goals:
  * stdlib only (no PyYAML), Windows/UTF-8/CRLF safe, NO network, NO writes except its own cache file
    (cache_root(): Windows <tempdir>/skill-sleuth, macOS/Linux $XDG_CACHE_HOME/skill-sleuth or ~/.cache/skill-sleuth,
    never inside the skill folder; a --cache inside the skill folder is refused; a --cache that does not end in
    .json, lies in a Claude config tree (.claude) or holds a file that is not our index is not used: one not: line)
  * enumerates every ON-DISK skill source with provenance ("tier") and the exact name the Skill tool
    expects ("invoke"), plus install/enable hints for things that are not usable yet
  * answers a query in <= 2 KB instead of dumping a megabyte-sized inventory into the model's context

Roots (derived at run time from the environment and cwd - nothing is hard-coded):
  <config>  = $CLAUDE_CONFIG_DIR, else ~/.claude (every OS)                  claude_config_dir()
  <plugins> = $CLAUDE_CODE_PLUGIN_CACHE_DIR, else <config>/plugins            plugins_root()
  <desktop> = $CLAUDE_DESKTOP_DATA_DIR, else                                 desktop_data_dir()
              Windows  the first that holds local-agent-mode-sessions of: %APPDATA%/Claude;
                       %LOCALAPPDATA%/Claude-Data/<id> (observed 2026-10-22; of several, the one whose
                       local-agent-mode-sessions changed last);
                       %LOCALAPPDATA%/Packages/Claude_*/LocalCache/Roaming/Claude (observed 2026-10-14);
                       none: %APPDATA%/Claude
              macOS    ~/Library/Application Support/Claude                  (not verified on a real machine)
              Linux    $XDG_CONFIG_HOME/Claude, else ~/.config/Claude        (not verified on a real machine)
  user              <config>/skills/<name>/SKILL.md                          invoke = <name>
  user-synced       <config>/skills/synced/<org_acct>/<name>/SKILL.md        claude.ai skill sync (CLI >= 2.1.273)
  project           <cwd>/.claude/skills and every ancestor up to the git root (without a repository: up to the
                    home directory, which is never a project; a .claude/skills that is <config>/skills is skipped)
  plugin-cache      <plugins>/cache/<mkt>/<plugin>/<ver>/                    installed Claude Code plugins: only the
                    version folder Claude Code uses in this cwd (an installPath of an install record that applies
                    here; no .orphaned_at marker); its plugin id comes from installed_plugins.json
  marketplace-clone <plugins>/marketplaces/<mkt>/{plugins,external_plugins}/<p>/   never invoked from here: Claude
                    Code loads plugins from the plugin cache only
  desktop-bundle    <desktop>/local-agent-mode-sessions/skills-plugin/*/*/skills/<name>/  (anthropic-skills:*)
  claudeai-plugin   <desktop>/rpm/*/*/plugin_*/ (observed 2026-10-22: rpm/<acct8>/<org8>) and the older
                    <desktop>/local-agent-mode-sessions/*/*/rpm/plugin_*/, both read (rpm_dirs())  (<plugin>:<skill>)
  catalog-remote    <plugins>/plugin-catalog-cache.json                      plugins with no SKILL.md on disk
  builtin           <script dir>/builtins.json (optional sidecar: skills built into the Claude Code binary, no SKILL.md)
  other             any --root DIR given on the command line (walked for SKILL.md)
The user, project and other tiers follow symlinked skill folders (npx skills links them on macOS/Linux), with a
cycle guard. The same rules are used by skill_envanteri.py and katalog_indeksle.py (the latter needs only <config>
and <plugins>).
Loading rules of Claude Code (2.1.295) that decide "invoke": a skill is <skills dir>/<name>/SKILL.md, one level
deep (a deeper SKILL.md is never loaded: a ghost, shown with --all), except in a folder of the user (or the cwd's)
skills dir that holds .claude-plugin/: Claude Code also loads it as a plugin "<name>@skills-dir" (its skills are
<plugin>:<skill>; enabledPlugins "<name>@skills-dir": false switches the folder off). A plugin's skill dirs are its
default skills/ folder AND the plugin.json "skills" paths, adjusted by its marketplace entry (plugin_skill_paths());
a path that itself holds a SKILL.md is one skill named by its frontmatter name; with neither, a SKILL.md at the
plugin root. Plugin skill names keep [A-Za-z0-9_-], other characters become "-". enabledPlugins, skillOverrides
and disableBundledSkills are merged from <config>/settings.json < <cwd>/.claude/settings.json <
<cwd>/.claude/settings.local.json (macOS / Linux: < the git root's settings.local.json); skillOverrides "off" /
"user-invocable-only" stops model invocation of a user, project or bundled skill (plugin skills ignore it), and so
do disableBundledSkills / CLAUDE_CODE_DISABLE_BUNDLED_SKILLS for the bundled ones.
Results never list this skill itself (skill-sleuth / skill-bulucu, any tier). "not:" lines under the header: both
editions installed at once; a Claude Code file (installed_plugins.json, known_marketplaces.json,
plugin-catalog-cache.json) that exists but yields nothing or carries an unknown "version"; a cache that could not
be used (the index was then built in memory). Descriptions are third-party text: invisible characters (C*
categories: zero-width, bidi, tag block ...) are removed before anything is printed, and 8 or more of them in one
entry add the marker GIZLI-KARAKTER(<n>) to its line ("hidden_chars" in --json / --show).

NOT covered (needs the claude.ai tools inside the session): the claude.ai skill library that is not synced
(SearchSkills), claude.ai plugin directory entries not materialised under rpm/ (SearchPlugins), MCP-served
skills (e.g. Figma get_figma_skill skill://index.json).

Usage:
  python skill_ara.py --query "pdf tablo çıkar" [--top 8] [--json] [--desc-len 90] [--max-bytes 2048]
  python skill_ara.py --query "..." --root <dir>                 (extra roots -> tier "other"; repeatable)
  python skill_ara.py --stats                                      per-tier counts, cache age, rebuild reason
  python skill_ara.py --show data:analyze                          one entry in full (<= 2 KB)
  python skill_ara.py --show superpowers                           a plugin of the official catalog: its plugin
                                                                   record comes FIRST and carries source_url, sha,
                                                                   unique_installs, last_updated, hooks (events),
                                                                   mcp_servers; then the entries of that exact name
--show <x> prints, best first and <= 2 KB in total: the plugin record when <x> (or <x>@<marketplace>) names a plugin
(taken from the index, or read from plugin-catalog-cache.json on demand when the index has no plugin entry: a
plugin whose skills and commands were indexed one by one, such as "plugin-dev" in the marketplace clone), then the
entries whose invoke name, name, directory name or path equals <x>. Only when nothing
matches exactly: entries whose invoke name contains <x> or whose path has <x> as whole "/" segment(s). Entries that
do not fit are named in one "(+N more: --show ...)" line; nothing is cut in the middle. No match: exit code 0 and
"no entry matches '<x>' (index + official catalog)".
Popularity / freshness of official-catalog candidates (plugin-catalog-cache.json; nothing is fetched): a list line
that is NOT usable yet shows installs=<unique_installs> (installs=veri-yok when the catalog has no count),
guncel=<last_updated, YYYY-MM-DD>, the marker AZ-KURULUM when the count is known and below 1,000 and the marker BAYAT
when last_updated is more than 365 days ago (thresholds: references/dis-kaynaklar.md section 3). A candidate that
is not usable and carries AZ-KURULUM loses LOW_PENALTY (4) points: a plugin few people installed should not outrank
a usable skill only because its name matches a synonym. Stars and repository age are not in the catalog:
dis_kaynak_ara.py --repo <source_url> when source_url is a GitHub repository (a "./plugins/<name>" source lives
inside the marketplace repository and has no repository of its own).
  python skill_ara.py --refresh --query ...                        force rebuild
Options:
  --cache PATH        cache file (default: $SKILL_ARA_CACHE or <cache_root()>/skill_ara_cache.json). On macOS/Linux
                      a cache dir or file owned by another user, group/world-writable or symlinked is not used.
  --max-age-hours N   rebuild if cache older than N hours even if the fingerprint is unchanged (default 24)
  --installed-only    only entries usable right now (invoke name known)
  --tier T            restrict to tiers (repeatable)
  --all               include non-loadable ghosts (a nested SKILL.md, or one outside a plugin's skill paths)
  --json              the same results as JSON, also <= --max-bytes: trailing results that do not fit are dropped
                      and "truncated" says how many
Exit codes: 0 ok, 2 bad arguments (incl. a --cache path inside the skill folder).
"""
import argparse
import functools
import glob
import io
import json
import math
import os
import re
import stat
import sys
import tempfile
import time
import unicodedata

VERSION = "0.6.3"

for _s in (sys.stdout, sys.stderr):           # Windows console: never crash on chars outside the ANSI code page
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace", newline="\n")   # no CRLF inflation of the byte cap
        except Exception:
            pass

SKIP_DIRS = {".git", "node_modules", ".in_use", "__pycache__", ".venv", "venv"}
DESC_CAP = 1536          # Claude Code truncates each listing description at 1,536 chars (skillListingMaxDescChars)
TIERS = ("user", "user-synced", "project", "plugin-cache", "marketplace-clone",
         "desktop-bundle", "claudeai-plugin", "catalog-remote", "builtin", "other")
MIN_INSTALLS = 1000      # AZ-KURULUM: unique_installs known and below this (references/dis-kaynaklar.md section 3)
STALE_DAYS = 365         # BAYAT: the catalog's last_updated is more than this many days ago (same table)
NO_COUNT = "veri-yok"    # the catalog record has no install count
SHOW_MAX = 2048          # bytes of the whole --show output
SHOW_HINT = 420          # bytes of the "(+N more: --show ...)" line of --show
OFFICIAL_MKT = "claude-plugins-official"
SELF_NAMES = ("skill-sleuth", "skill-bulucu")   # this skill's two editions: never a hit of its own search
LOW_PENALTY = 4          # points a not-usable catalog candidate with AZ-KURULUM loses (score())
HIDDEN_FLAG = 8          # invisible characters removed from one entry before GIZLI-KARAKTER(<n>) is printed
# "version" values of Claude Code's undocumented files that this script was written against (schema_notes())
KNOWN_VERSIONS = {"installed_json": (1, 2), "catalog_cache": (1,)}
# the only roots the cache stores: load_or_build() compares exactly these (the cwd and its parent folders are not
# stored as roots; project skill folders that exist are still in project_roots, the fingerprint and entry paths)
CACHE_ROOT_KEYS = ("extra", "claude_home", "plugins", "lams")


def norm(p):
    return os.path.normpath(p).replace("\\", "/")


def jdict(x):
    """x when it is a JSON object, else {}: a file of another shape never raises."""
    return x if isinstance(x, dict) else {}


def jlist(x):
    """x when it is a JSON array, else []."""
    return x if isinstance(x, list) else []


def jstr(x):
    """x when it is a non-empty string, else None."""
    return x if isinstance(x, str) and x else None


def read_text(p):
    try:
        with io.open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read().replace("\r\n", "\n").replace("\r", "\n")
    except Exception:
        return ""


def read_json(p, default=None):
    """Parsed JSON file, else default. utf-8-sig: a file saved with a BOM (PowerShell 5.1, some editors) is read
    like Claude Code reads it, not silently dropped."""
    try:
        with io.open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def mtime(p):
    try:
        return int(os.stat(p).st_mtime)
    except Exception:
        return 0


def _is_link(p):
    """A symlink, or a Windows junction (os.walk enters junctions even with followlinks=False). Python < 3.12 has no
    os.path.isjunction: on Windows every reparse point then counts as a link (FILE_ATTRIBUTE_REPARSE_POINT)."""
    try:
        if os.path.islink(p):
            return True
        if hasattr(os.path, "isjunction"):
            return bool(os.path.isjunction(p))
        return os.name == "nt" and bool(getattr(os.lstat(p), "st_file_attributes", 0)
                                        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except (OSError, ValueError):
        return False


def walk_files(root, filename, maxdepth=40, follow=False):
    """Yield <dir>/<filename> under root. follow=True also descends into symlinked directories (skill folders that
    npx skills links on macOS/Linux). Cycle guard: a directory whose real path is already on its own path from
    root (a link back into itself or into an ancestor) is not entered again. Only links cost a realpath call."""
    root = os.path.normpath(root)
    if not os.path.isdir(root):
        return
    base = root.count(os.sep)
    real = {root: os.path.normcase(os.path.realpath(root))}
    chain = {root: frozenset([real[root]])}  # dir -> real paths of the dirs from root down to it
    for dp, dns, fns in os.walk(root, followlinks=follow):
        if dp != root:
            up = os.path.dirname(dp)
            r = (os.path.normcase(os.path.realpath(dp)) if _is_link(dp)
                 else os.path.join(real.get(up, up), os.path.normcase(os.path.basename(dp))))
            seen = chain.get(up, frozenset())
            if r in seen:                    # a cycle: do not enter it again
                dns[:] = []
                continue
            real[dp], chain[dp] = r, seen | {r}
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        if dp.count(os.sep) - base >= maxdepth:
            dns[:] = []
        if filename in fns:
            yield os.path.join(dp, filename)


# ---------------------------------------------------------------- third-party text
# Invisible characters that are NOT in a Unicode C* category (same table as dis_kaynak_ara.py): combining grapheme
# joiner, Hangul fillers, Khmer inherent vowels, Mongolian and emoji variation selectors, line/paragraph separator,
# blank braille, object replacement, variation selectors supplement. Built from code points so that this source file
# itself stays free of invisible characters. Everything in a C* category (Cc controls, Cf format: soft hyphen,
# zero-width, bidi, BOM, the tag block U+E0000-E007F; Co private use; Cs lone surrogates; Cn unassigned) is caught
# by unicodedata.
_INVIS = re.compile("[%s]" % "".join("%s-%s" % (chr(a), chr(b)) for a, b in (
    (0x034f, 0x034f), (0x115f, 0x1160), (0x17b4, 0x17b5), (0x180b, 0x180f), (0x2028, 0x2029), (0x2800, 0x2800),
    (0x3164, 0x3164), (0xfe00, 0xfe0f), (0xffa0, 0xffa0), (0xfffc, 0xfffc), (0xe0100, 0xe01ef))))


def clean(s, n=None):
    """Third-party text -> one printable line, cut to n chars (same as dis_kaynak_ara.py). Every C*-category
    character and every character in _INVIS becomes a space, so hidden text (tag-block or zero-width encoded
    instructions, bidi overrides) never reaches the reader. Fail-closed: a character newer than this interpreter's
    Unicode tables is dropped."""
    if s is None:
        return ""
    if not isinstance(s, str):
        s = str(s)
    s = "".join(" " if unicodedata.category(c)[0] == "C" else c for c in _INVIS.sub(" ", s))
    s = re.sub(r"\s+", " ", s).strip()
    if n and len(s) > n:
        s = s[: max(1, n - 1)].rstrip() + "…"
    return s


def hidden_count(s):
    """How many invisible characters clean() strips from s (tab, newline, CR are ordinary whitespace: not counted)."""
    if not isinstance(s, str):
        return 0
    return sum(1 for c in s if c not in "\t\n\r" and (unicodedata.category(c)[0] == "C" or _INVIS.match(c)))


def scrub(text):
    """Last pass over everything printed: an invisible character left in a name, path or command becomes '?', so it
    shows instead of hiding (descriptions are clean()ed before, where a script prints them). Newlines are kept."""
    return "".join("?" if c != "\n" and (unicodedata.category(c)[0] == "C" or _INVIS.match(c)) else c for c in text)


# ---------------------------------------------------------------- YAML-frontmatter subset parser (no PyYAML)
# Handles the styles found in the corpus: plain, "double-quoted" (multi-line, \n escapes),
# 'single-quoted' ('' escapes), > folded and | literal block scalars, nested maps, lists, flow lists.
KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]+)\s*:(?:\s+(.*))?$")
_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/", "'": "'", " ": " "}


def _find_unescaped(s, ch):
    i = 0
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == ch:
            return i
        i += 1
    return None


def _find_sq_close(s):
    i = 0
    while i < len(s):
        if s[i] == "'":
            if i + 1 < len(s) and s[i + 1] == "'":
                i += 2
                continue
            return i
        i += 1
    return None


def _unescape_dq(s):
    return re.sub(r"\\(.)", lambda m: _ESC.get(m.group(1), m.group(1)), s)


def _strip_scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        return _unescape_dq(inner) if v[0] == '"' else inner.replace("''", "'")
    return re.sub(r"\s+#.*$", "", v)


def parse_frontmatter(text):
    """Return (dict, error_or_None)."""
    text = text.lstrip("\ufeff")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, "no-frontmatter"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return {}, "unterminated-frontmatter"
    body = lines[1:end]
    fm = {}

    def collect_indented(j):
        block = []
        while j < len(body) and (body[j][:1] in (" ", "\t") or not body[j].strip()):
            block.append(body[j])
            j += 1
        while block and not block[-1].strip():
            block.pop()
        return block, j

    i = 0
    while i < len(body):
        line = body[i]
        if not line.strip() or line.lstrip().startswith("#") or line[:1] in (" ", "\t"):
            i += 1
            continue
        m = KEY_RE.match(line)
        if not m:
            i += 1
            continue
        key, rest = m.group(1), (m.group(2) or "").strip()
        if rest == "" or rest.startswith("#"):
            block, j = collect_indented(i + 1)
            if block and block[0].strip().startswith("- "):
                fm[key] = [_strip_scalar(b.strip()[2:]) for b in block if b.strip().startswith("- ")]
            elif block and KEY_RE.match(block[0].strip()):
                sub = {}
                for b in block:
                    mm = KEY_RE.match(b.strip())
                    if mm:
                        sub[mm.group(1)] = _strip_scalar(mm.group(2) or "")
                fm[key] = sub
            else:
                fm[key] = " ".join(b.strip() for b in block if b.strip())
            i = j
            continue
        c = rest[0]
        if c in "|>" and re.match(r"^[|>][+-]?\d*\s*(#.*)?$", rest):
            block, j = collect_indented(i + 1)
            ind = min((len(b) - len(b.lstrip()) for b in block if b.strip()), default=0)
            stripped = [b[ind:] if b.strip() else "" for b in block]
            if c == "|":
                val = "\n".join(stripped).strip("\n")
            else:
                out, para = [], []
                for s in stripped:
                    if s == "":
                        out.append(" ".join(para))
                        para = []
                    else:
                        para.append(s.strip())
                out.append(" ".join(para))
                val = "\n".join(out).strip()
            fm[key] = val
            i = j
            continue
        if c == '"':
            buf, j = rest[1:], i
            while True:
                k = _find_unescaped(buf, '"')
                if k is not None:
                    buf = buf[:k]
                    break
                j += 1
                if j >= len(body):
                    break
                buf += " " + body[j].strip()
            fm[key] = _unescape_dq(buf)
            i = j + 1
            continue
        if c == "'":
            buf, j = rest[1:], i
            while True:
                k = _find_sq_close(buf)
                if k is not None:
                    buf = buf[:k]
                    break
                j += 1
                if j >= len(body):
                    break
                buf += " " + body[j].strip()
            fm[key] = buf.replace("''", "'")
            i = j + 1
            continue
        if c == "[":
            fm[key] = [_strip_scalar(x) for x in rest.strip("[]").split(",") if x.strip()]
            i += 1
            continue
        val = rest
        j = i + 1
        while j < len(body) and body[j][:1] in (" ", "\t") and body[j].strip() and not KEY_RE.match(body[j].strip()):
            val += " " + body[j].strip()
            j += 1
        fm[key] = re.sub(r"\s+#.*$", "", val).strip()
        i = j
    return fm, None


def _truthy(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


# ---------------------------------------------------------------- roots
# Location rules. claude_config_dir() and plugins_root() are identical in skill_ara.py, skill_envanteri.py and
# katalog_indeksle.py; desktop_data_dir() and rpm_dirs() are identical in skill_ara.py and skill_envanteri.py.
def claude_config_dir():
    """Claude Code config dir on every OS: $CLAUDE_CONFIG_DIR, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def plugins_root():
    """Claude Code plugins root (cache/, marketplaces/, installed_plugins.json, known_marketplaces.json,
    plugin-catalog-cache.json): $CLAUDE_CODE_PLUGIN_CACHE_DIR when set (a leading ~ is expanded, as Claude Code
    does), else <config>/plugins."""
    d = (os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR") or "").strip()
    return os.path.expanduser(d) if d else os.path.join(claude_config_dir(), "plugins")


def desktop_data_dir():
    """Data dir of the Claude desktop app: $CLAUDE_DESKTOP_DATA_DIR when set (as is). Windows: the first of these
    that holds a local-agent-mode-sessions folder: %APPDATA%/Claude; %LOCALAPPDATA%/Claude-Data/<id> (observed
    2026-10-22; of several, the one whose local-agent-mode-sessions was modified last);
    %LOCALAPPDATA%/Packages/Claude_*/LocalCache/Roaming/Claude (MSIX, observed 2026-10-14); none: %APPDATA%/Claude.
    macOS ~/Library/Application Support/Claude, Linux $XDG_CONFIG_HOME/Claude or ~/.config/Claude.
    The macOS and Linux locations were not verified on a real machine: set the variable when they are wrong."""
    d = os.environ.get("CLAUDE_DESKTOP_DATA_DIR")
    if d:
        return d
    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        roaming = os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "Claude")
        local = glob.escape(os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local"))
        for found in ([roaming], glob.glob(os.path.join(local, "Claude-Data", "*")),
                      glob.glob(os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude"))):
            hits = []
            for c in found:
                lams = os.path.join(c, "local-agent-mode-sessions")
                try:
                    if os.path.isdir(lams):
                        hits.append((os.path.getmtime(lams), c))
                except OSError:
                    pass
            if hits:
                return max(hits)[1]
        return roaming
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Claude")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "Claude")


def rpm_dirs(desktop):
    """The desktop app's claude.ai plugin caches (each: manifest.json + plugin_<id>/ folders) below the desktop data
    dir; both layouts are read: <desktop>/rpm/<acct8>/<org8> (observed 2026-10-22; the first 8 hex digits of the
    account / org id) first, then <desktop>/local-agent-mode-sessions/<acct>/<org>/rpm (skills-plugin/ there is the
    desktop bundle, never one). -> the folders that exist."""
    d = glob.escape(desktop)
    new = sorted(glob.glob(os.path.join(d, "rpm", "*", "*")))
    old = [r for r in sorted(glob.glob(os.path.join(d, "local-agent-mode-sessions", "*", "*", "rpm")))
           if os.path.basename(os.path.dirname(os.path.dirname(r))) != "skills-plugin"]
    return [r for r in new + old if os.path.isdir(r)]


def _real(p):
    return os.path.normcase(os.path.realpath(p))


def env_true(name):
    """An environment flag as Claude Code parses it: true only for 1 / true / yes / on (any case)."""
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


@functools.lru_cache(maxsize=None)
def git_root(d):
    """The nearest folder from d upwards (d included) that holds a .git entry (a folder, or the file of a worktree
    or submodule), else None. Memoised: install records ask for the same folders again and again."""
    p = os.path.normpath(os.path.abspath(d))
    while True:
        if os.path.lexists(os.path.join(p, ".git")):
            return p
        q = os.path.dirname(p)
        if q == p:
            return None
        p = q


@functools.lru_cache(maxsize=None)
def main_checkout(root):
    """For a git worktree root (its .git is a file "gitdir: <common dir>/worktrees/<name>"): the main checkout's
    root - the folder that holds the common .git dir, or for a bare repository the common dir itself - else None.
    The common dir comes from <gitdir>/commondir when it exists (Claude Code reads it the same way)."""
    try:
        with io.open(os.path.join(root, ".git"), "r", encoding="utf-8-sig", errors="replace") as f:
            line = f.read(4096).strip()
    except (OSError, ValueError):
        return None
    if not line.startswith("gitdir:"):
        return None
    gd = os.path.normpath(os.path.join(root, line[len("gitdir:"):].strip()))
    try:
        with io.open(os.path.join(gd, "commondir"), "r", encoding="utf-8-sig", errors="replace") as f:
            common = os.path.normpath(os.path.join(gd, f.read(4096).strip()))
    except (OSError, ValueError):
        common = os.path.dirname(os.path.dirname(gd))
    if not _same_path(os.path.dirname(gd), os.path.join(common, "worktrees")):
        return None
    if os.path.basename(common) != ".git":
        return None if os.path.lexists(os.path.join(common, ".git")) else common
    return os.path.dirname(common)


def project_dirs(cwd, home, user_skills):
    """The dirs whose .claude/skills Claude Code (2.1.295) loads as project skills, cwd first: cwd and its ancestors
    up to the git root (included); without a git repository, up to the filesystem root, but the walk stops at the
    home directory (home is never a project: ~/.claude/skills is the user tier). A dir whose .claude/skills IS the
    user skills dir is skipped for the same reason. In a git worktree whose root has no .claude/skills, the main
    checkout's root follows (Claude Code does the same)."""
    hk, us = _real(home), _real(user_skills)
    out = []
    start = os.path.normpath(os.path.abspath(cwd))
    root = git_root(start)
    p = start
    while True:
        if _real(p) == hk:
            break
        if _real(os.path.join(p, ".claude", "skills")) != us:
            out.append(p)
        if root is not None and _same_path(p, root):
            break
        q = os.path.dirname(p)
        if q == p:
            break
        p = q
    main = main_checkout(root) if root is not None else None
    if main and not os.path.isdir(os.path.join(root, ".claude", "skills")) and not any(_same_path(main, x) for x in out):
        if _real(os.path.join(main, ".claude", "skills")) != us:
            out.append(main)
    return out


def local_settings_root(cwd):
    """macOS / Linux: Claude Code reads the local settings (settings.local.json, where /skills and --scope local
    write) from the canonical git root of cwd (the main checkout of a worktree) on top of a legacy
    <cwd>/.claude/settings.local.json, when the root, its .git entry and its .claude entry (if any) belong to the
    current user and the root is not the home directory. That root's file, or None (Windows: cwd only)."""
    if os.name == "nt" or not hasattr(os, "geteuid"):
        return None
    root = git_root(cwd)
    if root is None:
        return None
    root = main_checkout(root) or root
    if _same_path(root, cwd) or _real(root) == _real(os.path.expanduser("~")):
        return None
    uid = os.geteuid()
    try:
        if os.stat(root).st_uid != uid or os.lstat(os.path.join(root, ".git")).st_uid != uid:
            return None
        c = os.path.join(root, ".claude")
        if os.path.lexists(c) and os.lstat(c).st_uid != uid:
            return None
    except OSError:
        return None
    return os.path.join(root, ".claude", "settings.local.json")


def derive_roots(cwd, extra_roots):
    home = os.path.expanduser("~")
    claude_home = claude_config_dir()
    plugins = plugins_root()
    desktop = desktop_data_dir()
    lams = os.path.join(desktop, "local-agent-mode-sessions")
    here = os.path.dirname(os.path.abspath(__file__))
    return {
        "home": home,
        "claude_home": claude_home,
        "plugins": plugins,
        "user_skills": os.path.join(claude_home, "skills"),
        "user_synced": os.path.join(claude_home, "skills", "synced"),
        "cwd_dir": os.path.normpath(os.path.abspath(cwd)),
        "project_dirs": project_dirs(cwd, home, os.path.join(claude_home, "skills")),
        "plugin_cache": os.path.join(plugins, "cache"),
        "marketplaces": os.path.join(plugins, "marketplaces"),
        "catalog_cache": os.path.join(plugins, "plugin-catalog-cache.json"),
        "installed_json": os.path.join(plugins, "installed_plugins.json"),
        "known_mkts": os.path.join(plugins, "known_marketplaces.json"),
        "settings": os.path.join(claude_home, "settings.json"),
        "settings_project": os.path.join(os.path.abspath(cwd), ".claude", "settings.json"),
        "settings_local": os.path.join(os.path.abspath(cwd), ".claude", "settings.local.json"),
        "settings_local_root": local_settings_root(cwd),
        "desktop": desktop,                  # not a compared root: "lams" is derived from it
        "lams": lams,
        "bundle_glob": os.path.join(lams, "skills-plugin", "*", "*"),
        "builtins": os.path.join(here, "builtins.json"),
        "extra": [os.path.normpath(r) for r in (extra_roots or [])],
    }


def settings_files(R):
    """The settings files Claude Code merges in this cwd, lowest precedence first: user (<config>/settings.json),
    project (<cwd>/.claude/settings.json), local (<cwd>/.claude/settings.local.json; on macOS / Linux also the git
    root's, which wins: local_settings_root()). Managed (policy) settings and --settings files are not read."""
    return [f for f in (R["settings"], R["settings_project"], R["settings_local"], R.get("settings_local_root")) if f]


def merged_setting(R, key):
    """One object-valued setting (enabledPlugins, skillOverrides) as Claude Code sees it in this cwd: the
    settings_files(), a later file winning per entry. A plugin installed with --scope local is enabled only in a
    local file."""
    out = {}
    for f in settings_files(R):
        out.update(jdict(jdict(read_json(f, {})).get(key)))
    return out


def merged_flag(R, key):
    """A true/false setting (disableBundledSkills) as Claude Code sees it: the last settings file that sets it wins."""
    v = None
    for f in settings_files(R):
        x = jdict(read_json(f, {})).get(key)
        if isinstance(x, bool):
            v = x
    return v


def fingerprint(R):
    """Cheap change detection. Dir mtimes change when a direct child is added/removed, NOT when a file
    deeper inside changes -> edits inside an existing skill dir are caught by --refresh / --max-age-hours.
    The merged enabledPlugins / skillOverrides / disableBundledSkills and the install folders that apply to this
    cwd are part of it (a few entries): a settings or install change rebuilds the index, a cwd change that alters
    none of them does not."""
    fp = {}
    for key in ("installed_json", "known_mkts", "settings", "catalog_cache", "builtins"):
        fp[key] = mtime(R[key])
    for key in ("enabledPlugins", "skillOverrides"):
        fp[key] = json.dumps(merged_setting(R, key), sort_keys=True, ensure_ascii=True)
    fp["bundled_off"] = bundled_off(R)
    fp["restrict_personal"] = env_true("CLAUDE_CODE_RESTRICT_PERSONAL_CONFIG")
    installed = read_installed(R)
    fp["installs"] = [[k, v] for k, v in sorted(live_installs(R, installed).items())]   # lists: JSON round trip
    fp["installed_here"] = sorted(installed_here(R, installed))
    # skills-dir plugins: their manifest, skill paths and commands folder (a new skill there is a new entry)
    cwd_sk = os.path.join(R["cwd_dir"], ".claude", "skills")
    for d, pj in skills_dir_plugins(R["user_skills"]) + skills_dir_plugins(cwd_sk, user=False):
        fp["sdp:" + norm(d)] = ([mtime(os.path.join(d, ".claude-plugin", "plugin.json")), mtime(os.path.join(d, "commands"))]
                               + [mtime(x) for x in plugin_skill_paths(d, pj, skills_dir=True) or []])
    # version folders Claude Code marked as no longer used (cache_key_of): a new marker drops them from the index
    fp["orphaned"] = sorted(norm(os.path.dirname(m)) for m in
                            glob.glob(os.path.join(glob.escape(R["plugin_cache"]), "*", "*", "*", ".orphaned_at")))
    for d in ("user_skills", "plugin_cache", "marketplaces"):
        fp[d] = mtime(R[d])
    for sub in glob.glob(os.path.join(R["user_skills"], "*")):
        fp["user:" + os.path.basename(sub)] = mtime(os.path.join(sub, "SKILL.md")) or mtime(sub)
    for m in glob.glob(os.path.join(R["user_synced"], "*", "manifest.json")):
        fp["synced:" + os.path.basename(os.path.dirname(m))] = mtime(m)
    for pd in R["project_dirs"]:
        sk = os.path.join(pd, ".claude", "skills")
        if os.path.isdir(sk):
            fp["project:" + norm(sk)] = mtime(sk)
            for sub in glob.glob(os.path.join(sk, "*")):
                fp["project:" + norm(sub)] = mtime(os.path.join(sub, "SKILL.md")) or mtime(sub)
    for b in glob.glob(R["bundle_glob"]):
        fp["bundle:" + os.path.basename(b)] = mtime(os.path.join(b, "manifest.json"))
    for r in rpm_dirs(R["desktop"]):             # both layouts: a cache that appears, moves or changes rebuilds
        fp["rpm:" + norm(r)] = mtime(os.path.join(r, "manifest.json"))
    for x in R["extra"]:
        fp["extra:" + norm(x)] = mtime(x)
    return fp


def project_roots(R):
    """The project skill dirs that exist, each with its role ([dir, is_cwd]): what a cwd change can alter in the
    index. A new cwd with the same list needs no rebuild."""
    out = []
    for pd in R["project_dirs"]:
        sk = os.path.join(pd, ".claude", "skills")
        if os.path.isdir(sk):
            out.append([norm(sk), pd == R["cwd_dir"]])
    return out


_BAD = object()


def schema_notes(R):
    """Claude Code's installed_plugins.json, known_marketplaces.json and plugin-catalog-cache.json are undocumented;
    a CLI update can change them, and the plugin and catalog tiers would then come back empty without a word.
    -> one 'not:' text when such a file exists but cannot be read, yields 0 entries, or carries a 'version' this
    script does not know (KNOWN_VERSIONS); else None. An explicitly empty list ({"plugins": {}}, {}) is a valid
    state (nothing installed), not a warning; an empty catalog is not."""
    probs = []
    for key, fname in (("installed_json", "installed_plugins.json"), ("known_mkts", "known_marketplaces.json"),
                       ("catalog_cache", "plugin-catalog-cache.json")):
        if not os.path.isfile(R[key]):
            continue
        d = read_json(R[key], _BAD)
        if d is _BAD or not isinstance(d, dict):
            probs.append("%s %s" % (fname, "okunamadi" if d is _BAD else "beklenmeyen bicim"))
            continue
        why = []
        v = d.get("version")
        if key == "known_mkts":
            if "version" in d and not isinstance(v, dict):
                why.append("version=%s bilinmiyor" % clean(json.dumps(v), 20))
            if d and not any(isinstance(x, dict) for x in d.values()):
                why.append("0 kayit")
        else:
            if v is not None and v not in KNOWN_VERSIONS[key]:
                why.append("version=%s bilinmiyor" % clean(json.dumps(v), 20))
            box = d.get("plugins") if key == "installed_json" else jdict(d.get("catalog")).get("plugins")
            if not isinstance(box, dict):
                why.append("0 kayit (plugins alani yok)")
            elif (box or key == "catalog_cache") and not any(isinstance(x, (dict, list)) for x in box.values()):
                why.append("0 kayit")
        if why:
            probs.append("%s %s" % (fname, ", ".join(why)))
    if not probs:
        return None
    return "Claude Code dosya bicimi degismis olabilir: %s; plugin/katalog sonuclari eksik olabilir" % "; ".join(probs)


# ---------------------------------------------------------------- index building
def _same_path(a, b):
    return os.path.normcase(os.path.normpath(os.path.abspath(a))) == os.path.normcase(os.path.normpath(os.path.abspath(b)))


def _escapes(plugin_dir, p):
    """True when the path p leaves plugin_dir (.., an absolute path elsewhere, a link pointing outside): Claude Code
    rejects such a skill path ("escapes plugin directory")."""
    try:
        rel = os.path.relpath(os.path.realpath(p), os.path.realpath(plugin_dir))
    except ValueError:                       # Windows: another drive
        return True
    return rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel)


def _skill_dirs(plugin_dir, v):
    """The existing folders a "skills" value (a string or a list of strings) names, relative to plugin_dir; a path
    that leaves plugin_dir is dropped."""
    out = []
    for x in ([v] if isinstance(v, str) else jlist(v)):
        if isinstance(x, str) and x:
            p = os.path.normpath(os.path.join(plugin_dir, x))
            if os.path.isdir(p) and not _escapes(plugin_dir, p) and not any(_same_path(p, q) for q in out):
                out.append(p)
    return out


def _js_true(v):
    """JavaScript truthiness of a JSON value (Claude Code tests manifest fields that way): an empty list or object
    counts, None / false / 0 / "" do not."""
    return not (v is None or v is False or v == "" or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0))


def plugin_skill_paths(plugin_dir, pj, entry=None, skills_dir=False):
    """The skill paths Claude Code (2.1.295) loads for one plugin folder -> list, or None when Claude Code refuses to
    load the plugin. pj = its .claude-plugin/plugin.json (None: the plugin has none); entry = its marketplace entry
    (the marketplace's marketplace.json, else the catalog's marketplace_entry; None: unknown); skills_dir = a
    folder of a skills dir loaded as "<name>@skills-dir" (skills_dir_plugins()).
    plugin.json: the default <plugin>/skills when it exists, plus every "skills" path; with neither (no "skills" key,
    no skills/ folder) the plugin root itself if it holds a SKILL.md (never for a skills-dir plugin, whose own
    SKILL.md is a plain user skill). Then the marketplace entry: a root source ("./") with "skills" keeps only those
    paths (the default skills/ only when one of them names it or the root); without plugin.json the entry's skills
    replace the manifest's; with plugin.json and strict (the default) they are added; plugin.json, "strict": false
    and an entry that declares components: refused (conflicting manifests)."""
    root = os.path.normpath(plugin_dir)
    default = os.path.join(root, "skills")
    base = default if os.path.isdir(default) else None          # Claude Code's skillsPath
    s = jdict(pj).get("skills")
    paths = [p for p in _skill_dirs(root, s)
             if not _same_path(p, default) and not (skills_dir and _same_path(p, root))]
    has_key = isinstance(s, list) or (isinstance(s, str) and bool(s))
    if not base and not has_key and not skills_dir and os.path.isfile(os.path.join(root, "SKILL.md")):
        paths = [root]
    if isinstance(entry, dict):
        es = entry.get("skills")
        src = entry.get("source")
        if isinstance(src, str) and all(x in ("", ".") for x in re.split(r"[\\/]", src)) and es:
            decl = _skill_dirs(root, es)
            if decl:
                if not any(_same_path(d, default) or _same_path(d, root) for d in decl):
                    base = None
                paths = [d for d in decl if not _same_path(d, default) and not _same_path(d, root)]
            elif any(isinstance(x, str) and _escapes(root, os.path.join(root, x)) for x in ([es] if isinstance(es, str) else jlist(es))):
                base, paths = None, []       # every declared path leaves the plugin: no skill at all
        extra = [d for d in _skill_dirs(root, es) if not _same_path(d, default)] if es else []
        comps = (any(_js_true(entry.get(k)) for k in ("commands", "agents", "skills", "hooks", "outputStyles", "themes"))
                 or _js_true(jdict(entry.get("experimental")).get("themes")))
        if pj is None:
            if extra:
                paths = extra
        elif entry.get("strict") is False and comps:
            return None
        else:
            paths += [d for d in extra if not any(_same_path(d, q) for q in paths)]
    return ([base] if base else []) + paths


def plugin_json(d):
    """<d>/.claude-plugin/plugin.json as an object, None when the file does not exist (an unreadable one is {})."""
    p = os.path.join(d, ".claude-plugin", "plugin.json")
    return jdict(read_json(p, {})) if os.path.isfile(p) else None


def marketplace_entries(R):
    """{marketplace: {plugin name: entry}} read from each marketplace's .claude-plugin/marketplace.json (the
    installLocation in known_marketplaces.json, else <plugins>/marketplaces/<name>)."""
    locs = {}
    for name, info in jdict(read_json(R["known_mkts"], {})).items():
        loc = jdict(info).get("installLocation")
        if isinstance(name, str) and isinstance(loc, str) and loc:
            locs[name] = loc
    for d in glob.glob(os.path.join(glob.escape(R["marketplaces"]), "*")):
        if os.path.isdir(d):
            locs.setdefault(os.path.basename(d), d)
    return dict((m, by_key(jdict(read_json(os.path.join(loc, ".claude-plugin", "marketplace.json"), {})).get("plugins"),
                           "name")) for m, loc in locs.items())


def skills_dir_plugins(skills_root, user=True):
    """Folders of a skills dir that Claude Code (2.1.295) loads as a plugin "<name>@skills-dir" (name = the
    plugin.json name, else the folder name): a direct sub-folder with a readable .claude-plugin/plugin.json (the
    layout claude plugin init writes; without the manifest Claude Code adopts nothing). In the user dir dot-prefixed
    folders and synced/ are skipped, and with CLAUDE_CODE_RESTRICT_PERSONAL_CONFIG none is adopted. -> [(folder,
    plugin.json)]. Not modelled: folders the claude.ai sync manifest of the skills dir claims."""
    if user and env_true("CLAUDE_CODE_RESTRICT_PERSONAL_CONFIG"):
        return []
    out = []
    for d in sorted(glob.glob(os.path.join(glob.escape(skills_root), "*"))):
        b = os.path.basename(d)
        if user and (b.startswith(".") or b == "synced"):
            continue
        pjf = os.path.join(d, ".claude-plugin", "plugin.json")
        pj = read_json(pjf, None) if os.path.isfile(pjf) else None
        if os.path.isdir(d) and isinstance(pj, dict):
            out.append((d, pj))
    return out


def skills_dir_name(d, pj):
    """The plugin name of a skills-dir plugin folder: its plugin.json name, else the folder name."""
    return jstr(jdict(pj).get("name")) or os.path.basename(d)


def plugin_skill_slot(skill_md, paths):
    """How Claude Code loads the SKILL.md at skill_md from one of a plugin's skill paths -> "dir" (it is
    <path>/<name>/SKILL.md: the skill is named <name>), "self" (it is <path>/SKILL.md: that path is ONE skill,
    named by its frontmatter name) or None (not loaded: deeper, or outside every skill path). A path that holds a
    SKILL.md itself is that one skill: the folders below it are not read."""
    d = os.path.dirname(skill_md)
    for sp in paths:
        if os.path.isfile(os.path.join(sp, "SKILL.md")):
            if _same_path(d, sp):
                return "self"
        elif _same_path(os.path.dirname(d), sp):
            return "dir"
    return None


def skill_slot(skill_md, root):
    """User and project skills: Claude Code loads only <root>/<name>/SKILL.md (one level), following a symlinked
    <name> folder. True when skill_md is at that level."""
    return _same_path(os.path.dirname(os.path.dirname(skill_md)), root)


GHOST_NOTE = "not loaded by Claude Code: only <skills dir>/<name>/SKILL.md (one level) is a skill"


def make_entry(path, tier, kind="skill", plugin=None, marketplace=None, installed=True, enabled=None,
               prefix=None, install_cmd=None, note=None, loadable=True, self_named=False, **extra):
    d = os.path.dirname(path)
    fm, err = parse_frontmatter(read_text(path))
    dir_name = os.path.basename(d) if kind == "skill" else os.path.splitext(os.path.basename(path))[0]
    fm_name = clean(fm.get("name"), 200) if isinstance(fm.get("name"), str) else None
    desc = fm.get("description", "")
    if not isinstance(desc, str):
        desc = json.dumps(desc, ensure_ascii=False)
    dmi = _truthy(fm.get("disable-model-invocation", False))
    wtu = fm.get("when_to_use") or fm.get("whenToUse") or ""
    if not isinstance(wtu, str):
        wtu = ""
    extra.setdefault("hidden_chars", hidden_count(desc) + hidden_count(wtu))
    desc, wtu = clean(desc), clean(wtu)
    # The Skill tool keys plugin skills by DIRECTORY name, not frontmatter name (verified on rpm strip-profile:
    # frontmatter `name: fsi-strip-profile`, listed as investment-banking:strip-profile). Commands use the file stem.
    # Exception (self_named): a plugin skill path that itself holds the SKILL.md is named by the frontmatter name
    # (a leading "<plugin>:" removed), else by its folder. Plugin skill names keep only [A-Za-z0-9_-].
    key = dir_name
    if self_named and isinstance(fm.get("name"), str) and fm["name"].strip():
        key = fm["name"].strip()
        if prefix and key.startswith(prefix + ":"):
            key = key[len(prefix) + 1:] or dir_name
    if prefix and kind == "skill":
        key = re.sub(r"[^a-zA-Z0-9_-]", "-", key)
    invoke = None
    if enabled and loadable and not dmi:
        invoke = f"{prefix}:{key}" if prefix else key
    e = {
        "name": fm_name or dir_name, "key": key, "kind": kind, "tier": tier, "plugin": plugin,
        "marketplace": marketplace, "path": norm(path), "description": desc[:DESC_CAP],
        "when_to_use": wtu[:400], "installed": bool(installed), "enabled": enabled,
        "invoke": invoke, "hidden": dmi, "loadable": loadable, "install_cmd": install_cmd, "note": note, "fm_error": err,
    }
    e.update(extra)
    return e


def _num(v):
    """v when it is a finite JSON number (not a bool; 1e400 parses as inf), else None."""
    ok = isinstance(v, int) or (isinstance(v, float) and math.isfinite(v))
    return v if ok and not isinstance(v, bool) else None


def _always_on(cp):
    t = jdict(jdict(cp).get("tokens"))
    vals = [_num(v.get("always_on")) for v in t.values() if isinstance(v, dict)]
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def _names(x):
    """Component names of a catalog record: a list of strings / {name: ...} objects, or an object keyed by name."""
    if isinstance(x, dict):
        return [k for k in x if isinstance(k, str)]
    return [m if isinstance(m, str) else m.get("name") for m in jlist(x)
            if isinstance(m, str) or (isinstance(m, dict) and isinstance(m.get("name"), str))]


def _cat_fields(cp):
    """Review fields of one official-catalog record (plugin-catalog-cache.json), so that a single record never
    has to be read by hand: where the plugin comes from and its pinned sha, popularity and freshness, what runs
    (hook events, MCP servers). {} when the plugin has no catalog record.
    source_url is a GitHub URL, or "./plugins/<name>" when the plugin lives inside the marketplace repository
    itself (it has no repository of its own; sha is then the marketplace commit, the catalog's source_sha)."""
    if not isinstance(cp, dict) or not cp:
        return {}
    src = jdict(cp.get("marketplace_entry")).get("source")
    comps = jdict(cp.get("components"))
    url = src.get("url") if isinstance(src, dict) else src
    path = src.get("path") if isinstance(src, dict) else None
    sha = jstr(cp.get("sha")) or jstr(cp.get("source_sha"))
    out = {"source_url": url if isinstance(url, str) else None, "sha": sha,
           "unique_installs": _num(cp.get("unique_installs")), "last_updated": jstr(cp.get("last_updated")),
           "hooks": _names(comps.get("hooks")), "mcp_servers": _names(comps.get("mcpServers"))}
    if isinstance(path, str) and path:
        out["source_path"] = path           # git-subdir source: the plugin is this directory of source_url
    return out


PLUGIN_READY = "kurulu ve etkin; Skill adi yok (yalniz MCP/LSP/hook bileseni)"


def plugin_hint(pid, inst, en, has_parts=False):
    """install_cmd of a plugin record that has no callable skill: what would make the plugin usable. Installed and
    enabled: a plugin without skills or commands needs nothing (its MCP / LSP / hook components already run, the
    text says so: the 'NOT USABLE -> ...' line never proposes installing a plugin that is already there); one whose
    catalog record lists skills that are not on disk needs an update."""
    if inst and en:
        return ("claude plugin update %s (skill'leri kurulu surumde bulunamadi)" % pid) if has_parts else PLUGIN_READY
    return "claude plugin enable %s" % pid if inst else "claude plugin install %s" % pid


def catalog_entry(pid, cp, installed, enabled_plugins, tier="catalog-remote"):
    """One plugin-level record of the official catalog (plugin-catalog-cache.json). Build step 7 stores it for a
    catalog plugin without a loadable entry on disk (tier "catalog-remote"); --show builds it on demand (tier=None)
    for a catalog plugin that has no plugin entry in the index (its skills and commands were indexed one by one).
    installed = the plugin ids whose install record applies to this cwd (installed_here()). With tier=None the tier
    is derived ("marketplace-clone" when the plugin lives inside the marketplace repository, i.e. a relative source,
    else "catalog-remote"), install_cmd is None for an installed and enabled plugin (its skills are in the index),
    and the record is compact: only the fields a review needs, none of the index-only ones (key, path, invoke, ...)."""
    me = jdict(cp.get("marketplace_entry"))
    comps = jdict(cp.get("components"))
    skills = [s.get("name") for s in jlist(comps.get("skills")) if isinstance(s, dict) and jstr(s.get("name"))]
    cmds = [c.get("name") for c in jlist(comps.get("commands")) if isinstance(c, dict) and jstr(c.get("name"))]
    src = me.get("source")
    inst, en = bool(installed.get(pid)), bool(enabled_plugins.get(pid, False))
    desc = me.get("description") if isinstance(me.get("description"), str) else ""
    e = {
        "name": clean(jstr(me.get("name")) or pid.split("@")[0], 200), "key": pid.split("@")[0], "kind": "plugin",
        "tier": tier, "plugin": pid.split("@")[0],
        "marketplace": pid.split("@")[1] if "@" in pid else None, "path": None,
        "description": clean(desc)[:DESC_CAP], "when_to_use": "", "hidden_chars": hidden_count(desc),
        "installed": inst, "enabled": en,
        "invoke": None, "hidden": False, "loadable": True,
        "install_cmd": plugin_hint(pid, inst, en, bool(skills or cmds)),
        "note": ("catalog entry; no SKILL.md on disk (its folder in the marketplace repository ships only MCP / "
                 "LSP / hooks, or is not cloned)" if isinstance(src, str) else
                 "catalog entry only; source is remote (%s)" % clean(src.get("source") if isinstance(src, dict) else src, 60)),
        "fm_error": None, "category": me.get("category"),
        "installs": _num(cp.get("unique_installs")), "always_on_tokens": _always_on(cp), "version": cp.get("version"),
    }
    if tier is None:                         # --show, on demand
        e["tier"] = "marketplace-clone" if isinstance(src, str) else "catalog-remote"
        if inst and en:
            e["install_cmd"] = None
        e = {k: e[k] for k in ("name", "kind", "tier", "plugin", "marketplace", "description", "hidden_chars",
                               "installed", "enabled", "install_cmd", "category", "always_on_tokens", "version")}
    e.update(_cat_fields(cp))                # source_url, sha, unique_installs, last_updated, hooks, mcp_servers
    e["skills"], e["commands"] = skills, cmds                # long lists last: --show shortens them first
    return e


def catalog_record(R, pname, mkt=""):
    """--show: the plugin record of <pname>[@<mkt>] read from plugin-catalog-cache.json on demand (the official
    marketplace wins when several marketplaces carry the name). None when the catalog has no such plugin."""
    catalog = read_catalog(R)
    keys = [k for k in catalog if fold(k.partition("@")[0]) == pname and (not mkt or fold(k.partition("@")[2]) == mkt)]
    if not keys:
        return None
    pid = sorted(keys, key=lambda k: (k.partition("@")[2] != OFFICIAL_MKT, k))[0]
    return catalog_entry(pid, catalog[pid], installed_here(R, read_installed(R)), merged_setting(R, "enabledPlugins"),
                         tier=None)


def read_catalog(R):
    """plugin-catalog-cache.json -> {plugin id: record}; ids that are not strings and records that are not objects
    are skipped (never a traceback)."""
    c = jdict(jdict(jdict(read_json(R["catalog_cache"], {})).get("catalog")).get("plugins"))
    return dict((k, v) for k, v in c.items() if isinstance(k, str) and isinstance(v, dict))


def catalog_dates(R):
    """Dates of plugin-catalog-cache.json as YYYY-MM-DD for --show, so a review block never has to guess them:
    (when Claude Code fetched the catalog, when its install counts were computed); None when not recorded."""
    d = jdict(read_json(R["catalog_cache"], {}))
    day = lambda v: (jstr(v) or "")[:10] or None
    return day(d.get("fetchedAt")), day(jdict(d.get("catalog")).get("installs_generated_at"))


def read_installed(R):
    """installed_plugins.json -> {plugin id: install records}."""
    return jdict(jdict(read_json(R["installed_json"], {})).get("plugins"))


def installed_known(R):
    """True when installed_plugins.json exists and has a "plugins" object: only then does a missing record mean
    "not installed". When the file is missing or unreadable every plugin-cache folder without an .orphaned_at
    marker counts as installed (schema_notes() warns only about a file that exists but cannot be read)."""
    return isinstance(jdict(read_json(R["installed_json"], {})).get("plugins"), dict)


def _records(x):
    """The install records of one plugin id: a list of objects (a single object is accepted, anything else is [])."""
    return [r for r in (x if isinstance(x, list) else [x]) if isinstance(r, dict)]


def _pkey(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def record_applies(r, cwd):
    """Claude Code's hx(): an install record applies to a session in cwd when its scope is user or managed (or not
    recorded), or its projectPath is cwd or shares cwd's git root (the main checkout for a worktree)."""
    if r.get("scope") in (None, "user", "managed"):
        return True
    pp = r.get("projectPath")
    if not isinstance(pp, str) or not pp:
        return False
    if _same_path(pp, cwd):
        return True
    a, b = git_root(cwd), git_root(pp)
    return a is not None and b is not None and _same_path(main_checkout(a) or a, main_checkout(b) or b)


def installed_here(R, installed):
    """{plugin id: True} for every plugin with an install record that applies to this cwd (record_applies())."""
    return dict((pid, True) for pid, recs in installed.items()
                if isinstance(pid, str) and any(record_applies(r, R["cwd_dir"]) for r in _records(recs)))


def live_installs(R, installed):
    """{_pkey(install folder): plugin id}: per plugin, the first install record that applies to this cwd and names a
    folder that exists (Claude Code's cbn()). Claude Code names cache folders with sanitized ids (a "." in a plugin name becomes "-"), so the id of a
    folder comes from here, not from the folder names."""
    out = {}
    for pid, recs in installed.items():
        if not isinstance(pid, str):
            continue
        for r in _records(recs):              # Claude Code loads ONE record per plugin: the first that applies
            p = r.get("installPath")         # and whose folder exists
            if isinstance(p, str) and p and record_applies(r, R["cwd_dir"]) and os.path.isdir(p):
                out.setdefault(_pkey(p), pid)
                break
    return out


def cache_key_of(ver, folder_key, installed, live, cwd):
    """The plugin id whose live install the plugin-cache folder ver (<cache>/<marketplace>/<plugin>/<version>/) is,
    else None. Never with an .orphaned_at marker (Claude Code writes it into a folder it stopped using, then deletes
    the folder days later). live = live_installs(): an install folder of a record that applies to this cwd; an
    update leaves the previous version folder behind, often still without a marker, and a folder installed for
    another project is not used here. A record that applies but names no folder that exists (a moved config dir)
    keeps the folder-derived id. live None (installed_plugins.json missing or unreadable): every folder without a
    marker, with its folder-derived id (the behaviour before 0.6.2)."""
    if os.path.lexists(os.path.join(ver, ".orphaned_at")):
        return None
    if live is None:
        return folder_key
    k = live.get(_pkey(ver))
    if k is not None:
        return k
    recs = [r for r in _records(installed.get(folder_key)) if record_applies(r, cwd)]
    if recs and not any(isinstance(r.get("installPath"), str) and os.path.isdir(r["installPath"]) for r in recs):
        return folder_key
    return None


def overridden(e, overrides):
    """A user, project or bundled skill that skillOverrides switches off for the model ("off",
    "user-invocable-only") is not callable: Claude Code refuses Skill(<name>) for it until /skills switches it back
    on. Looked up by the skill's name as Claude Code lists it (the folder name), not the frontmatter name. Plugin
    skills ignore skillOverrides."""
    v = overrides.get(e.get("key")) if isinstance(e.get("key"), str) else None
    if v in ("off", "user-invocable-only"):
        e.update(invoke=None, enabled=False, install_cmd="skillOverrides: %s; /skills ile ac" % v)
    return e


def bundled_off(R):
    """Claude Code's _V(): CLAUDE_CODE_DISABLE_BUNDLED_SKILLS set, or disableBundledSkills: true in the merged
    settings -> the bundled skills (builtins.json) are user-invocable only, never Skill(<name>) by the model."""
    return env_true("CLAUDE_CODE_DISABLE_BUNDLED_SKILLS") or merged_flag(R, "disableBundledSkills") is True


def clone_hint(key, inst, en):
    """install_cmd of a skill seen in a marketplace clone (never callable from there): install the plugin, enable it,
    or - installed and enabled, but this skill is not in the installed version - update it."""
    if not inst:
        return "claude plugin install %s" % key
    if not en:
        return "claude plugin enable %s" % key
    return "claude plugin update %s (kurulu surumde bu skill yok)" % key


def by_key(rows, key):
    """[{key: <str>, ...}, ...] -> {<str>: row}; rows that are not objects or lack a string key are skipped."""
    return dict((r[key], r) for r in jlist(rows) if isinstance(r, dict) and isinstance(r.get(key), str))


REFUSED_NOTE = ("its marketplace entry has strict: false and declares components while the plugin has a plugin.json:"
                " Claude Code refuses to load it")
REFUSED_HINT = "Claude Code bu plugin'i yuklemez (strict: false + plugin.json; marketplace girdisi duzeltilmeli)"


def _under(p, d):
    return _pkey(p).startswith(_pkey(d).rstrip(os.sep) + os.sep)


def build_index(R):
    t0 = time.time()
    entries = []
    enabled_plugins = merged_setting(R, "enabledPlugins")
    overrides = merged_setting(R, "skillOverrides")
    installed = read_installed(R)
    here_inst = installed_here(R, installed)
    live = live_installs(R, installed) if installed_known(R) else None
    mentries = marketplace_entries(R)
    catalog = read_catalog(R)
    covered = set()                          # <plugin>@<marketplace> with a loadable entry: no step-7 record
    # enabledPlugins "<name>@skills-dir": false switches a folder of the user (or the cwd's) skills dir off
    sd_off = set(k[:-len("@skills-dir")] for k, v in enabled_plugins.items()
                 if v is False and isinstance(k, str) and k.endswith("@skills-dir"))
    synced_prefix = norm(R["user_synced"]).lower() + "/"

    def cover(n0, *keys):
        if any(e.get("loadable", True) for e in entries[n0:]):
            covered.update(keys)

    def add_skills_dir(root, tier, plugins, **kw):
        """One skills dir: every <root>/<name>/SKILL.md is a skill with a bare invoke name (symlinked folders are
        followed; a deeper SKILL.md is a ghost, --all). plugins = skills_dir_plugins(root) (user dir and the cwd's
        project dir only; None for an ancestor): such a folder is also a plugin "<name>@skills-dir" whose skills
        and commands are <name>:<x>, enabled unless enabledPlugins says false for it (or its plugin.json has
        "defaultEnabled": false and enabledPlugins does not say true); with "<name>@skills-dir": false its own
        SKILL.md is not loaded either."""
        sdp = dict((_pkey(d), (d, pj, skills_dir_name(d, pj))) for d, pj in plugins or [])
        roots = [d for d, _, _ in sdp.values()]
        for p in walk_files(root, "SKILL.md", maxdepth=6, follow=True):
            if tier == "user" and norm(p).lower().startswith(synced_prefix):
                continue
            top = skill_slot(p, root)
            if not top and any(_under(p, d) for d in roots):
                continue                     # a skills-dir plugin's own skill: below
            folder = sdp.get(_pkey(os.path.dirname(p)))
            off = bool(top and folder and folder[2] in sd_off)
            e = make_entry(p, tier, enabled=not off, loadable=top, note=None if top else GHOST_NOTE,
                           install_cmd=("enabledPlugins %s@skills-dir: false" % folder[2]) if off else None, **kw)
            entries.append(overridden(e, overrides))
        for d, pj, name in sdp.values():
            ep = enabled_plugins.get(name + "@skills-dir")
            en = ep if isinstance(ep, bool) else jdict(pj).get("defaultEnabled") is not False
            hint = None if en else ("enabledPlugins %s@skills-dir: false" % name if ep is False else
                                    "defaultEnabled: false; enabledPlugins %s@skills-dir: true ile ac" % name)
            spaths = plugin_skill_paths(d, pj, skills_dir=True)
            for p in walk_files(d, "SKILL.md", follow=True):
                if _same_path(os.path.dirname(p), d):
                    continue                 # the folder's own SKILL.md is the bare skill above
                slot = plugin_skill_slot(p, spaths)
                entries.append(make_entry(p, tier, plugin=name, marketplace="skills-dir", enabled=en,
                                          prefix=name, loadable=bool(slot), self_named=slot == "self",
                                          install_cmd=hint, note=None if slot else
                                          "outside the plugin's skill paths, or nested -> not loaded", **kw))
            if not _js_true(jdict(pj).get("commands")):          # the default commands/ folder, as for any plugin
                for c in sorted(glob.glob(os.path.join(glob.escape(d), "commands", "*.md"))):
                    entries.append(make_entry(c, tier, kind="command", plugin=name, marketplace="skills-dir",
                                              enabled=en, prefix=name, install_cmd=hint, **kw))

    # 1. user skills (<config>/skills, synced/ excluded: 1b) and its skills-dir plugins
    add_skills_dir(R["user_skills"], "user", skills_dir_plugins(R["user_skills"]))

    # 1b. claude.ai synced skills: ~/.claude/skills/synced/<org>_<acct>/<name>/SKILL.md + manifest.json
    for mani in glob.glob(os.path.join(R["user_synced"], "*", "manifest.json")):
        bucket = os.path.dirname(mani)
        man_by = by_key(jdict(read_json(mani, {})).get("skills"), "name")
        for p in walk_files(bucket, "SKILL.md", maxdepth=3):
            if "/.staging/" in norm(p):
                continue
            nm = os.path.basename(os.path.dirname(p))
            ms = man_by.get(nm, {})
            en = ms.get("enabled")
            e = make_entry(p, "user-synced", enabled=(bool(en) if en is not None else True))
            # In desktop sessions the same skill is listed as anthropic-skills:<name> (desktop-bundle copy);
            # whether a plain CLI session lists it by bare name is UNVERIFIED -> no invoke, but keep hints.
            e["probable_invoke"] = e["invoke"]
            e["alt_invoke"] = "anthropic-skills:" + nm
            e["invoke"] = None
            e["install_cmd"] = "desktop session: Skill(anthropic-skills:%s); plain CLI: bare name %s (unverified)" % (nm, nm)
            entries.append(e)

    # 2. project skills: cwd first, then its ancestors up to the git root (project_dirs(): Claude Code loads all of
    #    them); skills-dir plugins only in the cwd's own .claude/skills
    for pd in R["project_dirs"]:
        sk = os.path.join(pd, ".claude", "skills")
        here = pd == R["cwd_dir"]
        add_skills_dir(sk, "project", skills_dir_plugins(sk, user=False) if here else None, project_root=norm(pd))

    # 3. plugin cache (installed Claude Code plugins): only the version folder Claude Code uses in this cwd
    #    (cache_key_of(): its id comes from installed_plugins.json); a folder that an update, an uninstall or another
    #    project's install left behind is skipped (the clone and the catalog still list the plugin)
    live_keys = set()                        # (plugin, marketplace, key) of every loadable cached skill / command
    for ver in glob.glob(os.path.join(R["plugin_cache"], "*", "*", "*")):
        if not os.path.isdir(ver):
            continue
        plug = os.path.dirname(ver)
        key = cache_key_of(ver, "%s@%s" % (os.path.basename(plug), os.path.basename(os.path.dirname(plug))),
                           installed, live, R["cwd_dir"])
        if key is None:
            continue
        kname, _, mkt = key.rpartition("@")
        pj = plugin_json(ver)
        cat = catalog.get(key, {})
        entry = jdict(mentries.get(mkt)).get(kname) or jdict(cat.get("marketplace_entry")) or None
        pdisp = jstr(jdict(pj).get("name")) or jstr(jdict(entry).get("name")) or kname
        en = bool(enabled_plugins.get(key, False))
        spaths = plugin_skill_paths(ver, pj, entry)
        n0 = len(entries)
        for p in walk_files(ver, "SKILL.md"):
            slot = plugin_skill_slot(p, spaths) if spaths is not None else None
            entries.append(make_entry(p, "plugin-cache", plugin=pdisp, marketplace=mkt, installed=True,
                                      enabled=en, prefix=pdisp, loadable=bool(slot), self_named=slot == "self",
                                      install_cmd=REFUSED_HINT if spaths is None else None if en else
                                      f"claude plugin enable {key}",
                                      note=None if slot else REFUSED_NOTE if spaths is None else
                                      "outside the plugin's skill paths, or nested -> not loaded",
                                      plugin_version=os.path.basename(ver), installs=_num(cat.get("unique_installs")),
                                      always_on_tokens=_always_on(cat), **_cat_fields(cat)))
        for c in sorted(glob.glob(os.path.join(ver, "commands", "*.md"))):
            entries.append(make_entry(c, "plugin-cache", kind="command", plugin=pdisp, marketplace=mkt,
                                      installed=True, enabled=en, prefix=pdisp, loadable=spaths is not None,
                                      note=None if spaths is not None else REFUSED_NOTE,
                                      install_cmd=REFUSED_HINT if spaths is None else None if en else
                                      f"claude plugin enable {key}"))
        live_keys.update((e["plugin"], e["marketplace"], e["key"]) for e in entries[n0:] if e.get("loadable", True))
        if spaths is None:
            covered.update((key, f"{pdisp}@{mkt}"))   # refused, but on disk: its ghosts say why
        cover(n0, key, f"{pdisp}@{mkt}")

    # 4. marketplace clones (catalog copies). Never callable from here: Claude Code loads a plugin from the plugin
    #    cache only. A skill the installed version also has is left out (the plugin-cache copy is the one that loads)
    for mkt in glob.glob(os.path.join(R["marketplaces"], "*")):
        if not os.path.isdir(mkt):
            continue
        mname = os.path.basename(mkt)
        mcat = by_key(jdict(read_json(os.path.join(mkt, ".claude-plugin", "marketplace.json"), {})).get("plugins"),
                      "name")
        for sub in ("plugins", "external_plugins"):
            for pdir in glob.glob(os.path.join(mkt, sub, "*")):
                if not os.path.isdir(pdir):
                    continue
                pj = plugin_json(pdir)
                ment = mcat.get(jstr(jdict(pj).get("name")) or os.path.basename(pdir)) or mcat.get(os.path.basename(pdir))
                pdisp = jstr(jdict(pj).get("name")) or jstr(jdict(ment).get("name")) or os.path.basename(pdir)
                key = f"{pdisp}@{mname}"
                en = bool(enabled_plugins.get(key, False))
                inst = bool(here_inst.get(key))
                cat = catalog.get(key, {})
                spaths = plugin_skill_paths(pdir, pj, ment)
                hint = clone_hint(key, inst, en)
                n0 = len(entries)
                for p in walk_files(pdir, "SKILL.md"):
                    slot = plugin_skill_slot(p, spaths) if spaths is not None else None
                    entries.append(make_entry(p, "marketplace-clone", plugin=pdisp, marketplace=mname,
                                              installed=inst, enabled=en, prefix=pdisp, loadable=bool(slot),
                                              self_named=slot == "self",
                                              install_cmd=REFUSED_HINT if spaths is None else hint,
                                              note=("catalog copy" + ("" if inst else "; not installed")) if slot else
                                              REFUSED_NOTE if spaths is None else
                                              "outside the plugin's skill paths, or nested -> not loaded",
                                              category=jdict(ment).get("category"),
                                              installs=_num(cat.get("unique_installs")),
                                              always_on_tokens=_always_on(cat), **_cat_fields(cat)))
                for c in sorted(glob.glob(os.path.join(pdir, "commands", "*.md"))):
                    entries.append(make_entry(c, "marketplace-clone", kind="command", plugin=pdisp,
                                              marketplace=mname, installed=inst, enabled=en, prefix=pdisp,
                                              install_cmd=hint, installs=_num(cat.get("unique_installs")),
                                              **_cat_fields(cat)))
                entries[n0:] = [e for e in entries[n0:] if (e["plugin"], e["marketplace"], e["key"]) not in live_keys]
                for e in entries[n0:]:
                    e["invoke"] = None       # the clone is not a load path (sources.md, Table B row 5)
                cover(n0, key, f"{os.path.basename(pdir)}@{mname}")

    # 5. desktop-bundled skills (anthropic-skills:*)
    for b in glob.glob(R["bundle_glob"]):
        if not os.path.isdir(b):
            continue
        pj = jdict(read_json(os.path.join(b, ".claude-plugin", "plugin.json"), {}))
        man_by = by_key(jdict(read_json(os.path.join(b, "manifest.json"), {})).get("skills"), "name")
        pname = jstr(pj.get("name")) or "anthropic-skills"
        for p in walk_files(os.path.join(b, "skills"), "SKILL.md", maxdepth=3):
            ms = man_by.get(os.path.basename(os.path.dirname(p)), {})
            en = ms.get("enabled")
            entries.append(make_entry(p, "desktop-bundle", plugin=pname, installed=True,
                                      enabled=(bool(en) if en is not None else True), prefix=pname,
                                      manifest_source=ms.get("source")))

    # 6. claude.ai plugins materialised by the desktop app (rpm; both layouts, rpm_dirs())
    for r in rpm_dirs(R["desktop"]):
        man_by = by_key(jdict(read_json(os.path.join(r, "manifest.json"), {})).get("plugins"), "id")
        for pd in glob.glob(os.path.join(r, "plugin_*")):
            if not os.path.isdir(pd):
                continue
            pid = os.path.basename(pd)
            pj = jdict(read_json(os.path.join(pd, ".claude-plugin", "plugin.json"), {}))
            mp = man_by.get(pid, {})
            pname = jstr(pj.get("name")) or jstr(mp.get("name")) or pid
            avail = (mp.get("installationPreference") == "available") if mp else None
            spaths = plugin_skill_paths(pd, pj)
            for p in walk_files(pd, "SKILL.md"):
                slot = plugin_skill_slot(p, spaths)
                in_sd = bool(slot)
                en = (None if in_sd else False) if avail is None else bool(avail)
                entries.append(make_entry(p, "claudeai-plugin", plugin=pname, marketplace=jstr(mp.get("marketplaceName")),
                                          installed=True, enabled=en, prefix=pname, loadable=in_sd,
                                          self_named=slot == "self",
                                          install_cmd=None if (en and in_sd) else ("enable the plugin on claude.ai (Settings > Plugins)" if in_sd else None),
                                          note=None if in_sd else "outside the plugin's declared skills dir -> not listed",
                                          plugin_id=pid, plugin_display=mp.get("displayName")))
            for c in sorted(glob.glob(os.path.join(pd, "commands", "*.md"))):
                entries.append(make_entry(c, "claudeai-plugin", kind="command", plugin=pname,
                                          marketplace=jstr(mp.get("marketplaceName")), installed=True,
                                          enabled=(bool(avail) if avail is not None else None), prefix=pname,
                                          plugin_id=pid, plugin_display=mp.get("displayName")))

    # 7. catalog plugins without a loadable entry above (no SKILL.md or command on disk: a remote source, or a clone
    #    / cache folder that ships only MCP / LSP / hooks) -> one entry per plugin; install_cmd follows its state
    covered.update("%s@%s" % (e["plugin"], e["marketplace"] or "") for e in entries
                   if e.get("plugin") and e.get("loadable", True))
    for pid, cp in catalog.items():
        if pid in covered:
            continue
        entries.append(catalog_entry(pid, cp, here_inst, enabled_plugins))

    # 8. built-ins of the Claude Code binary (optional sidecar builtins.json: [{name, description, version}]); like
    #    Claude Code: skillOverrides applies to them, and disableBundledSkills / CLAUDE_CODE_DISABLE_BUNDLED_SKILLS
    #    leaves them to the user (bundled_off())
    boff = bundled_off(R)
    for b in jlist(read_json(R["builtins"], [])):
        if isinstance(b, dict) and jstr(b.get("name")):
            d = b.get("description") if isinstance(b.get("description"), str) else ""
            e = {"name": b["name"], "key": b["name"], "kind": "skill", "tier": "builtin", "plugin": None,
                 "marketplace": None, "path": None, "description": clean(d)[:DESC_CAP], "when_to_use": "",
                 "hidden_chars": hidden_count(d), "installed": True, "enabled": True, "invoke": b["name"],
                 "hidden": False, "loadable": True, "install_cmd": None,
                 "note": "built into Claude Code %s" % clean(b.get("version", ""), 20), "fm_error": None}
            if boff:
                e.update(invoke=None, enabled=False, install_cmd="disableBundledSkills: paketli skill'ler kapali")
            entries.append(overridden(e, overrides))

    # 9. extra roots (tier "other")
    for x in R["extra"]:
        for p in walk_files(x, "SKILL.md", maxdepth=12, follow=True):
            entries.append(make_entry(p, "other", installed=False, enabled=False,
                                      note="found under --root; not in any Claude load path",
                                      install_cmd="copy the folder to ~/.claude/skills/<name>/ or <project>/.claude/skills/<name>/"))

    for e in entries:                       # pre-computed, stemmed search fields
        e["_np"] = _pairs(name_words(e))
        e["_sk"] = _pairs(skill_words(e))
        e["_dw"] = _pairs(words(e.get("description") or ""))
        e["_tw"] = _pairs(trigger_words(e.get("description") or "", e.get("when_to_use") or ""))
        e["_id"] = ident_keys(e)            # twin-dedupe keys (main)
    return {"version": VERSION, "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "build_ms": int((time.time() - t0) * 1000),
            "roots": {k: (R[k] if isinstance(R[k], (str, list)) else str(R[k])) for k in CACHE_ROOT_KEYS},
            "project_roots": project_roots(R), "fingerprint": fingerprint(R), "schema_note": schema_notes(R),
            "entries": entries}


def ident_keys(e):
    """Keys of the skill an index entry stands for; entries that share one are copies of ONE skill and only the
    best-scored copy is listed: skill/command twins and user/project copies behind one invoke name, the user-synced
    copy of a desktop-bundle skill (its alt_invoke), the same plugin skill in the plugin cache and in a marketplace
    clone or in two cached versions (plugin@marketplace + name). Distinct skills never share a key, whatever their
    descriptions say (an empty or equal-prefix description used to merge them)."""
    ks = []
    inv = e.get("invoke") or e.get("alt_invoke")
    if inv:
        ks.append("i:" + fold(inv))
    if e.get("plugin"):
        ks.append("%s:%s@%s:%s" % ("P" if e.get("kind") == "plugin" else "p", fold(e["plugin"]),
                                   fold(e.get("marketplace")), fold(e.get("key") or e.get("name"))))
    if not ks:
        ks.append("f:%s:%s" % (e.get("tier"), fold(e.get("path") or e.get("name"))))
    return ks


def is_self(e):
    """True for an entry of this skill itself (either edition, any tier): it is never a hit of its own search."""
    return any(fold(e.get(k)) in SELF_NAMES for k in ("key", "name", "plugin"))


def self_note(entries, R):
    """'not:' text when both editions are installed at once (the user should keep one), else None. Only copies that
    Claude Code loads count: the index holds only live plugin-cache folders (cache_key_of), and a ghost (a nested
    SKILL.md) or a marketplace-clone copy is never loaded."""
    got = set()
    for e in entries:
        if (not e.get("installed") or not e.get("loadable", True)
                or e.get("tier") in ("catalog-remote", "other", "marketplace-clone")):
            continue
        got.update(n for n in (fold(e.get(k)) for k in ("key", "name", "plugin")) if n in SELF_NAMES)
    if len(got) < 2:
        return None
    return "skill-sleuth ve skill-bulucu birlikte kurulu (ayni skill'in iki dil surumu): yalniz birini tut"


# ---------------------------------------------------------------- normalisation / scoring
_TR = str.maketrans({"ş": "s", "ğ": "g", "ı": "i", "İ": "i", "ö": "o", "ü": "u", "ç": "c",
                     "Ş": "s", "Ğ": "g", "Ö": "o", "Ü": "u", "Ç": "c", "â": "a", "î": "i", "û": "u"})
STOP = set("""ve ile icin bir bu su o de da mi mu bana beni benim sen ben biz siz onlar var yok olarak gibi
the a an to for of in on at and or with from my me i it is are be this that these those into as by using use
please can could would should want need help make do get let lutfen istiyorum yap yapmak et etmek olsun""".split())
TR_SUFFIXES = ("larini", "lerini", "larina", "lerine", "lari", "leri", "lar", "ler", "nin", "nun", "sini", "sunu",
               "dan", "den", "tan", "ten", "ini", "unu", "ina", "ine", "si", "su", "da", "de", "ta", "te", "ya", "ye",
               "yi", "yu", "in", "un", "im", "um", "i", "u", "a", "e")
EN_SUFFIXES = ("ations", "ation", "ings", "ing", "ers", "er", "ies", "es", "ed", "s")
# tiny bilingual synonym map: Turkish task words (folded) -> English words that occur in skill descriptions.
SYN = {
    "tablo": ["table", "spreadsheet", "excel"], "cikar": ["extract", "parse"], "cikart": ["extract"],
    "arastirma": ["research", "analysis"], "arastir": ["research", "search"], "urun": ["product"],
    "kampanya": ["campaign"], "reklam": ["ads", "advertising"], "tasarim": ["design"], "kod": ["code"],
    "yayinla": ["deploy", "publish"], "dagit": ["deploy"], "belge": ["document", "docx"], "sunum": ["presentation", "pptx", "slides"],
    "hesap": ["account", "spreadsheet"], "veri": ["data"], "grafik": ["chart", "graph", "visualization"],
    "sozlesme": ["contract", "agreement", "nda"], "fatura": ["invoice"], "eposta": ["email"], "mail": ["email"],
    "rapor": ["report"], "ozet": ["summary", "digest"], "gorsel": ["image", "visual"], "resim": ["image"],
    "ses": ["audio", "voice"], "ceviri": ["translate"], "cevir": ["translate", "convert"], "donustur": ["convert"],
    "duzenle": ["edit"], "olustur": ["create", "generate", "build"], "yaz": ["write", "draft"],
    "incele": ["review", "analyze", "audit"], "denetle": ["audit", "review"], "guvenlik": ["security"],
    "hata": ["bug", "error", "debug"], "veritabani": ["database", "sql"], "sorgu": ["query", "sql"],
    "site": ["website", "web"], "mobil": ["mobile", "ios", "android"], "muhasebe": ["accounting", "finance", "journal"],
    "finans": ["finance"], "butce": ["budget"], "pazarlama": ["marketing"], "satis": ["sales", "crm"],
    "musteri": ["customer", "crm"], "gorev": ["task"], "takvim": ["calendar", "schedule"], "toplanti": ["meeting"],
    "not": ["note", "notes"], "bellek": ["memory"], "hafiza": ["memory"], "ogren": ["learn", "teach"],
    "ogret": ["teach", "learn"], "zamanla": ["schedule", "cron"], "otomatik": ["automation", "automate"],
    "ithalat": ["import", "sourcing", "wholesale"], "toptan": ["wholesale", "sourcing"], "tedarikci": ["supplier", "sourcing"],
    "marj": ["margin"], "beceri": ["skill"], "eklenti": ["plugin"], "kur": ["install", "setup"], "yukle": ["install"],
    "ayar": ["settings", "config"], "excel": ["xlsx", "spreadsheet"], "word": ["docx"], "powerpoint": ["pptx"],
    "ads": ["advertising"], "deploy": ["deployment", "publish"], "chart": ["visualization"],
}


def fold(s):
    """Lower-case ASCII-folded text. The Turkish table runs BEFORE lower(): "İ".lower() is "i" + U+0307 (combining
    dot above), which would split every word that holds a capital İ."""
    return (s if isinstance(s, str) else "").translate(_TR).lower()


def words(s):
    return [w for w in re.split(r"[^a-z0-9]+", fold(s)) if w]


def stem(w):
    if len(w) < 4:
        return w
    for suf in TR_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    for suf in EN_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    return w


def _pairs(ws):
    out, seen = [], set()
    for w in ws:
        if w not in seen:
            seen.add(w)
            out.append([w, stem(w)])
    return out


def name_words(e):
    ws = []
    for s in (e.get("name"), e.get("key"), e.get("plugin")):
        if s:
            ws.extend(words(s))
    return ws


def skill_words(e):
    ws = []
    for s in (e.get("skills") or []) + (e.get("commands") or []):
        ws.extend(words(s))
    return ws


def trigger_words(desc, wtu):
    """Words inside quotes or in 'Use when' / 'Trigger' sentences (what authors write as triggers)."""
    t = []
    for m in re.finditer(r"[\"'“‘]([^\"'”’]{3,80})[\"'”’]", desc):
        t.extend(words(m.group(1)))
    for m in re.finditer(r"(?i)(?:use (?:this )?(?:skill )?when|trigger(?:s|ed)?(?: on| for| when)?|use for|use it when)[^.]{0,220}", desc):
        t.extend(words(m.group(0)))
    t.extend(words(wtu))
    return t


def expand_query(q):
    """-> list of groups; each group = [token, stem] variants for ONE original query word (word + synonyms).
    A group is scored by its best member, so synonym expansion cannot inflate the score."""
    groups = []
    for w in words(q):
        if w in STOP or len(w) < 2:
            continue
        st = stem(w)
        members = [w]
        for syn in SYN.get(w, []) + (SYN.get(st, []) if st != w else []):
            if syn not in members:
                members.append(syn)
        groups.append([[m, stem(m)] for m in members])
    return groups


_E_SUFFIXES = ("ings", "ing", "ers", "er", "es", "ed")


def _e_form(w):
    """The English base of a word whose stem has 3 letters, with its dropped 'e' restored: coding / codes -> code,
    dated -> date, typing -> type; any other word unchanged."""
    for suf in _E_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) == 3:
            return w[: -len(suf)] + "e"
    return w


def _hit(tok, st, pairs):
    """2 = exact/stem-equal, 1 = prefix either way (>=4 chars), 0 = none. A stem of only 3 letters is too short to
    stand for a word on its own (stem() strips the Turkish one-vowel suffixes: data / date -> "dat", code / coda ->
    "cod"): it counts when one word begins with the other (note / notes) or both have the same English base
    (code / coding, date / dated: _e_form())."""
    best = 0
    for w, sw in pairs:
        if tok == w or (st == sw and (len(st) >= 4 or (len(st) == 3 and (
                w.startswith(tok) or tok.startswith(w) or _e_form(w) == _e_form(tok))))):
            return 2
        if len(st) >= 4 and (w.startswith(st) or sw.startswith(st)):
            best = 1
        elif len(sw) >= 4 and tok.startswith(sw):
            best = 1
    return best


def score(e, groups, qfold):
    """Lexical score. Per query-word group, best of:
         own name part exact 10 / prefix 5  (weights ported from Claude Code's ToolSearch ranking)
         full invoke-name substring 3
         trigger/when_to_use word 4
         description word 2
         catalog plugin's skill/command NAME exact 6 / prefix 3  (weaker: a 40-skill plugin matches everything)
       then + coverage 5*(matched/groups) + phrase 4 + usable-now 3 (installed 1) + popularity<=2 - command 1
       - LOW_PENALTY (4) for a not-usable catalog candidate with AZ-KURULUM (a plugin few people installed must not
       outrank a usable skill because its name happens to match a synonym)."""
    if not groups:
        return 0, []
    full = fold(e.get("invoke") or e.get("name") or "")
    s, matched, hit = 0.0, 0, []
    for g in groups:
        best = 0
        for tok, st in g:
            h = _hit(tok, st, e["_np"])
            if h == 2:
                best = max(best, 10)
            elif h == 1:
                best = max(best, 5)
            if best < 10 and len(tok) >= 3 and tok in full:
                best = max(best, 3)
            if best < 10 and _hit(tok, st, e["_tw"]):
                best = max(best, 4)
            if best < 6:
                h = _hit(tok, st, e["_sk"])
                if h == 2:
                    best = max(best, 6)
                elif h == 1:
                    best = max(best, 3)
            if best < 4 and _hit(tok, st, e["_dw"]):
                best = max(best, 2)
            if best >= 10:
                break
        if best:
            matched += 1
            hit.append(g[0][0])
        s += best
    if matched == 0:
        return 0, []
    s += 5.0 * matched / len(groups)
    if len(qfold) >= 6 and qfold in fold(e.get("description") or ""):
        s += 4
    if e.get("invoke"):
        s += 3
    elif e.get("installed"):
        s += 1
    inst = _num(e.get("installs")) or 0
    if inst > 0:
        s += min(2.0, math.log10(inst + 1) / 2)
    if e.get("kind") == "command":
        s -= 1
    if not e.get("invoke") and "last_updated" in e and low_installs(e):
        s = max(0.1, s - LOW_PENALTY)        # ranked lower, still listed (a search by its name still finds it)
    return round(s, 1), hit


# ---------------------------------------------------------------- cache location and safety
# cache_root(), unsafe_stat(), private_dir(), read_private(), claude_tree() and write_private() are identical in skill_ara.py,
# dis_kaynak_ara.py, katalog_indeksle.py and skill_envanteri.py.
def cache_root():
    """Default directory of every cache and output file: Windows <tempdir>/skill-sleuth (%TEMP% is per-user); macOS
    and Linux $XDG_CACHE_HOME/skill-sleuth, else ~/.cache/skill-sleuth (a shared /tmp would let another local user
    plant a cache or read the inventory). Created with mode 0700."""
    if os.name == "nt":
        return os.path.join(tempfile.gettempdir(), "skill-sleuth")
    x = os.environ.get("XDG_CACHE_HOME") or ""
    return os.path.join(x if os.path.isabs(x) else os.path.join(os.path.expanduser("~"), ".cache"), "skill-sleuth")


def unsafe_stat(st, is_dir):
    """Why a cache dir (is_dir) or file with this stat result must not be used, else None. POSIX only (Windows: None;
    %TEMP% is per-user): not of the expected type, owned by another user, or writable by group or others."""
    if not hasattr(os, "getuid"):
        return None
    if not (stat.S_ISDIR(st.st_mode) if is_dir else stat.S_ISREG(st.st_mode)):
        return "beklenen tur degil"
    if st.st_uid != os.getuid():
        return "sahibi baska kullanici"
    if st.st_mode & 0o022:
        return "grup/herkes yazabilir"
    return None


def private_dir(d):
    """Create d (mode 0700) when it is missing -> None when it may hold our files, else the reason. Never raises."""
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
    except (OSError, ValueError) as e:
        return "dizin olusturulamadi (%s)" % e.__class__.__name__
    try:
        return unsafe_stat(os.stat(d), True)
    except (OSError, ValueError) as e:
        return "dizin okunamadi (%s)" % e.__class__.__name__


def read_private(p):
    """Bytes of one of our cache files, else None: missing, unreadable, or (POSIX) a symlink (O_NOFOLLOW), not a
    regular file, owned by another user or writable by group or others. Never raises."""
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except (OSError, ValueError):
        return None
    try:
        if unsafe_stat(os.fstat(fd), False):
            return None
        out = []
        while True:
            b = os.read(fd, 1 << 20)
            if not b:
                return b"".join(out)
            out.append(b)
    except OSError:
        return None
    finally:
        os.close(fd)


def claude_tree(path):
    """True when path lies in a Claude config tree: a folder or file named .claude or .claude.json on the way (as
    given or resolved), or at / below ~/.claude, $CLAUDE_CONFIG_DIR or $CLAUDE_CODE_PLUGIN_CACHE_DIR. No cache or
    output file of ours goes there: a --cache / --out pointing there must never replace Claude's own files."""
    cands = []
    for q in (os.path.abspath(path), os.path.realpath(path)):
        q = os.path.normcase(q).lower()        # case-insensitive on every OS (macOS / Windows file systems are)
        cands.append(q)
        if {".claude", ".claude.json"} & set(q.replace("\\", "/").split("/")):
            return True
    roots = [os.path.join(os.path.expanduser("~"), ".claude")]
    for v in ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_PLUGIN_CACHE_DIR"):
        x = (os.environ.get(v) or "").strip()
        if x:
            roots.append(os.path.expanduser(x))
    for r in roots:
        r = os.path.normcase(os.path.realpath(os.path.abspath(r))).lower().rstrip("\\/")
        if r and any(q == r or q.startswith(r + os.sep) for q in cands):
            return True
    return False


def write_private(path, data):
    """Atomic write of one of our cache or output files -> None, else the reason; never raises. The bytes go to a
    temp file with a unique name in the same directory (mkstemp: O_EXCL, mode 0600, never follows a symlink), then
    os.replace, retried while another process holds the target open (Windows). The temp file never stays behind."""
    if claude_tree(path):                     # checked first: no folder is created there either
        return "Claude ayar agaci (.claude)"
    d = os.path.dirname(os.path.abspath(path))
    why = private_dir(d)
    if why:
        return why
    try:
        fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=d)
    except (OSError, ValueError) as e:
        return "yazilamadi (%s)" % e.__class__.__name__
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        for i in range(5):
            try:
                os.replace(tmp, path)
                return None
            except PermissionError:          # Windows: another process has the target open right now
                time.sleep(0.05 * 2 ** i)    # 0.05 + 0.1 + 0.2 + 0.4 + 0.8 s at most
        return "yazilamadi (dosya baska bir surecte acik)"
    except OSError as e:
        return "yazilamadi (%s)" % e.__class__.__name__
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def default_cache_path():
    return os.environ.get("SKILL_ARA_CACHE") or os.path.join(cache_root(), "skill_ara_cache.json")


def inside_skill_folder(path):
    """True when path is under the skill folder (parent of this scripts/ dir). The skill folder is read-only for us."""
    skill_dir = norm(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).lower()
    p = norm(os.path.abspath(path)).lower()
    return p == skill_dir or p.startswith(skill_dir + "/")


def foreign_file(path):
    """None when path is missing, empty or one of our own index files (it starts with {"version": "<x>"), else
    the reason: the cache never replaces somebody else's file (a --cache / $SKILL_ARA_CACHE typo, ~/.zshrc ...)."""
    try:                                      # O_NONBLOCK: a FIFO planted at the path never blocks the run
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return "dosya okunamadi"
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return "beklenen tur degil"
        head = os.read(fd, 64)
    except OSError:
        return "dosya okunamadi"
    finally:
        os.close(fd)
    return None if not head or re.match(rb'\{"version": "[0-9][0-9A-Za-z.+-]*"', head) else "baska bir dosya (skill_ara indeksi degil)"


def cache_refusal(path):
    """Why this --cache / $SKILL_ARA_CACHE path must not be used, decided before anything is created or opened, else
    None: it must end in .json and lie outside every Claude config tree (claude_tree). load_or_build() then checks the
    folder (private_dir) and only after that the file itself (foreign_file). A refusal is soft: the index is built
    in memory and a 'not:' line says why."""
    if not path.lower().endswith(".json"):
        return "uzanti .json degil"
    if claude_tree(path):
        return "Claude ayar agaci (.claude)"
    return None


def load_or_build(cache_path, R, refresh, max_age_hours):
    """-> the index. The cache is read and written only in a private directory (private_dir, read_private,
    write_private); when it cannot be used the index is built in memory and idx["cache_note"] says why (one
    'not:' line). A cwd change rebuilds only when it changes the project skill dirs (project_roots)."""
    reason = None
    why = (cache_refusal(cache_path) or private_dir(os.path.dirname(os.path.abspath(cache_path)))
           or foreign_file(cache_path))
    idx = None
    if not refresh and not why:
        raw = read_private(cache_path)
        try:
            idx = json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            idx = None
        idx = idx if isinstance(idx, dict) else None
    if idx is None:
        reason = "refresh" if refresh else "no-cache"
    elif idx.get("version") != VERSION:
        reason = "version"
    elif any(jdict(idx.get("roots")).get(k) != R[k] for k in CACHE_ROOT_KEYS):
        reason = "roots-changed"             # --root list, $CLAUDE_CONFIG_DIR / $CLAUDE_CODE_PLUGIN_CACHE_DIR /
                                             # $CLAUDE_DESKTOP_DATA_DIR changed
    elif idx.get("project_roots") != project_roots(R):
        reason = "cwd-changed"               # the new cwd has other project skill dirs (or the same in another role)
    elif idx.get("fingerprint") != fingerprint(R):
        reason = "fingerprint"
    else:
        try:
            age_h = (time.time() - time.mktime(time.strptime(idx["built_at"], "%Y-%m-%dT%H:%M:%S"))) / 3600
        except Exception:
            age_h = 1e9
        if age_h > max_age_hours:
            reason = "max-age"
    if reason:
        idx = build_index(R)
        idx["rebuilt_because"] = reason
        if not why:
            # ASCII JSON: a lone surrogate (a "\ud800" escape in a JSON file, an undecodable POSIX file name) round-trips
            why = write_private(cache_path, json.dumps(idx).encode("ascii"))
    else:
        idx["rebuilt_because"] = None
    idx["cache_note"] = ("onbellek kullanilamadi (%s: %s); indeks bellekte kuruldu" % (
        norm(os.path.dirname(os.path.abspath(cache_path))), why)) if why else None
    return idx


# ---------------------------------------------------------------- output
MIN_BYTES = 300          # smallest --max-bytes: the header and the cut line must fit


def one_line(s, n):
    """One printable line of at most n chars: invisible characters removed (clean())."""
    return clean(s, n)


def nbytes(s):
    """UTF-8 size of s as printed: a lone surrogate (a "\\ud800" escape in a JSON file) becomes "?" (1 byte)."""
    return len(s.encode("utf-8", "replace"))


def cut_bytes(s, n):
    """s cut to at most n UTF-8 bytes, never inside a character."""
    return s.encode("utf-8", "replace")[: max(0, n)].decode("utf-8", "ignore")


def low_installs(e):
    """AZ-KURULUM: the catalog knows the install count and it is below MIN_INSTALLS."""
    n = e.get("installs")
    return isinstance(n, int) and not isinstance(n, bool) and n < MIN_INSTALLS


def stale(e):
    """BAYAT: the catalog's last_updated is more than STALE_DAYS days ago (unknown or unreadable date: False)."""
    try:
        t = time.mktime(time.strptime(str(e.get("last_updated"))[:10], "%Y-%m-%d"))
    except Exception:
        return False
    return (time.time() - t) / 86400.0 > STALE_DAYS


def show_text(e, max_bytes=SHOW_MAX, cut=True):
    """One entry as JSON for --show, at most max_bytes (incl. the final newline). When it is too long the skill
    and command lists are shortened first, then the description; the review fields of a catalog plugin
    (source_url, sha, unique_installs, last_updated, hooks, mcp_servers) are never cut. When that is still not
    enough: cut=True cuts the text at the byte cap (last resort), cut=False returns None."""
    d = {k: v for k, v in e.items() if not k.startswith("_")}
    if "unique_installs" in d:
        d.pop("installs", None)              # same number; keep the catalog's own name
    if not d.get("hidden_chars"):
        d.pop("hidden_chars", None)          # shown only when invisible characters were removed

    def dump():
        return json.dumps(d, ensure_ascii=False, indent=1)

    def over():
        return nbytes(dump()) + 1 > max_bytes

    for n in (24, 12, 6, 3):
        if not over():
            break
        for key in ("skills", "commands"):
            v = e.get(key)
            if isinstance(v, list) and len(v) > n:
                d[key] = v[:n] + ["(+%d)" % (len(v) - n)]
    for n in (600, 300, 120):
        if not over():
            break
        d["description"] = one_line(e.get("description"), n)
    out = dump()
    if nbytes(out) + 1 > max_bytes:
        if not cut:
            return None
        out = cut_bytes(out, max_bytes - 1)
    return out


def find_show(arg, ents, R, tiers=(), installed_only=False):
    """Entries for --show <arg>, best first -> (folded arg, entries).
    1. the plugin record when <arg> (or <arg>@<marketplace>) names a plugin: the index entry of kind "plugin", else
       the official-catalog record read on demand (catalog_record);
    2. entries whose invoke name equals <arg>, then entries whose name or directory name equals <arg>, whose invoke
       name ends in ":<arg>" or whose path equals <arg>; usable ones (invoke known) first;
    3. only when 1 and 2 found nothing: entries whose invoke name contains <arg> or whose path has <arg> as whole
       "/" segment(s) ("data" does not match ".../AppData/...")."""
    s = fold(arg).strip().replace("\\", "/")
    if not s:
        return s, []
    shown, seen = [], set()

    def add(lst):
        for e in sorted(lst, key=lambda e: e.get("invoke") is None):       # stable: usable first
            if id(e) not in seen:
                seen.add(id(e))
                shown.append(e)

    if ":" not in s and "/" not in s:
        pname, _, mkt = s.partition("@")
        rec = next((e for e in ents if e.get("kind") == "plugin" and fold(e.get("plugin") or e.get("name")) == pname
                    and (not mkt or fold(e.get("marketplace")) == mkt)), None)
        if rec is None and not installed_only:
            rec = catalog_record(R, pname, mkt)
            if rec is not None and tiers and rec["tier"] not in tiers:
                rec = None
        if rec is not None:
            if "last_updated" in rec:                    # catalog-backed: say how old the catalog itself is
                seen.add(id(rec))                        # the index entry itself is not listed a second time
                rec = dict(rec)
                rec["catalog_fetched_at"], rec["installs_as_of"] = catalog_dates(R)
            add([rec])
    add([e for e in ents if fold(e.get("invoke")) == s])
    add([e for e in ents if s in (fold(e.get("name")), fold(e.get("key")), fold(e.get("path")))
         or fold(e.get("invoke")).endswith(":" + s)])
    if not shown:
        seg = "/" + s.strip("/") + "/"
        add([e for e in ents if s in fold(e.get("invoke")) or seg in "/" + fold(e.get("path")) + "/"])
    return s, shown


def show_many(shown, s, max_bytes=SHOW_MAX):
    """--show output, at most max_bytes in total (incl. the final newline). The first entry is always printed
    (show_text shortens its lists, then its description). Every further entry is printed only when it fits whole
    (after the same shortening); otherwise one line names the --show argument of each entry that was left out.
    Nothing is cut in the middle."""
    def nb(t):
        return nbytes(t) + 1

    def ident(e):                            # an argument that brings up this entry, never the one just used
        inv = e.get("invoke")
        if inv and fold(inv) != s:
            return inv
        if e.get("path"):
            return e["path"]
        return "%s@%s" % (e.get("plugin") or e.get("name"), e.get("marketplace") or "")

    def hint(rest):
        ids = []
        for e in rest:
            x = '--show "%s"' % ident(e)
            if x not in ids:
                ids.append(x)
        line = "(+%d more: %s)" % (len(rest), " | ".join(ids))
        while len(ids) > 1 and nb(line) > SHOW_HINT:
            ids.pop()
            line = "(+%d more: %s | ...)" % (len(rest), " | ".join(ids))
        return line

    out, used = [], 0
    for i, e in enumerate(shown):
        rest = shown[i + 1:]
        room = max_bytes - used - (nb(hint(rest)) if rest else 0)
        t = show_text(e, room, cut=(i == 0))
        if t is None:
            out.append(hint(shown[i:]))
            break
        out.append(t)
        used += nb(t)
    return "\n".join(out)


def fmt_text(q, idx, ranked, top, desc_len, max_bytes, notes=()):
    """The text answer: header, one 'not:' line per note, 2-3 lines per hit; at most max_bytes on stdout (incl. the
    final newline): whole trailing lines are dropped and one '…(cut at N bytes; ...)' line says so."""
    hdr = "skill_ara %s | q=%r | %d entries (%s%s) | %d hits" % (
        VERSION, q, len(idx["entries"]), idx["built_at"],
        (", rebuilt:" + idx["rebuilt_because"]) if idx.get("rebuilt_because") else "", len(ranked))
    lines = [hdr] + ["not: " + n for n in notes]
    for i, (sc, hit, e) in enumerate(ranked[:top], 1):
        inv = e.get("invoke")
        how = ("Skill(%s)" % inv) if inv else ("NOT USABLE -> %s" % (e.get("install_cmd") or "?"))
        flag = e["tier"] + ("/" + e["kind"] if e["kind"] != "skill" else "")
        extra = ""
        cand = not inv and "last_updated" in e       # official-catalog candidate that is not usable yet
        if e.get("installs") or (cand and e.get("installs") == 0):
            extra += " installs=%s" % e["installs"]
        elif cand:
            extra += " installs=%s" % NO_COUNT       # never left out silently
        if cand and low_installs(e):
            extra += " AZ-KURULUM"
        if cand and e.get("last_updated"):
            extra += " guncel=%s" % str(e["last_updated"])[:10] + (" BAYAT" if stale(e) else "")
        if e.get("always_on_tokens"):
            extra += " always_on~%stok" % e["always_on_tokens"]
        if (e.get("hidden_chars") or 0) >= HIDDEN_FLAG:
            extra += " GIZLI-KARAKTER(%d)" % e["hidden_chars"]      # removed from the description: a red flag
        lines.append("%d. [%s] %s  (%s%s)" % (i, sc, how, flag, extra))
        lines.append("   %s" % one_line(e.get("description") or "(no description)", desc_len))
        if e.get("skills") and not inv:
            lines.append("   skills: %s" % one_line(", ".join(e["skills"][:6]) + (", +%d" % (len(e["skills"]) - 6) if len(e["skills"]) > 6 else ""), 70))
    out = "\n".join(lines)
    tail = "…(cut at %d bytes; use --top/--max-bytes)" % max_bytes
    while nbytes(out) + 1 > max_bytes and len(lines) > 1:
        lines = lines[:-1]
        out = "\n".join(lines) + "\n" + tail
    if nbytes(out) + 1 > max_bytes:          # the header alone is too long (a long query): cut it, keep the tail
        out = cut_bytes(lines[0], max_bytes - nbytes(tail) - 2) + "\n" + tail
    return out


def fmt_json(q, idx, ranked, top, desc_len, max_bytes, notes=()):
    """The same answer as one compact JSON object, at most max_bytes (incl. the final newline) like the text answer:
    trailing results that do not fit are dropped and "truncated" says how many (null when nothing was dropped).
    When the fields around the results alone do not fit (a long query, long notes), the query and the notes are
    shortened, then "groups" and "notes" are emptied."""
    rows = []
    for sc, hit, e in ranked[:top]:
        cand = not e.get("invoke") and "last_updated" in e   # same condition as the text line (fmt_text)
        rows.append({"score": sc, "matched": hit, "invoke": e.get("invoke"), "alt_invoke": e.get("alt_invoke"),
                     "name": e.get("name"), "kind": e["kind"], "tier": e["tier"], "plugin": e.get("plugin"),
                     "marketplace": e.get("marketplace"), "installed": e.get("installed"), "enabled": e.get("enabled"),
                     "hidden": e.get("hidden"), "install_cmd": e.get("install_cmd"), "path": e.get("path"),
                     "description": one_line(e.get("description"), desc_len * 3), "skills": (e.get("skills") or [])[:12] or None,
                     "installs": e.get("installs"), "always_on_tokens": e.get("always_on_tokens"),
                     "last_updated": e.get("last_updated"), "hidden_chars": e.get("hidden_chars") or 0,
                     "labels": [x for x, on in (("AZ-KURULUM", low_installs(e)), ("BAYAT", stale(e))) if cand and on]})
    doc = {"version": VERSION, "query": q, "groups": [[m[0] for m in g] for g in expand_query(q)],
           "entries": len(idx["entries"]), "hits": len(ranked), "built_at": idx["built_at"],
           "rebuilt_because": idx.get("rebuilt_because"), "notes": list(notes), "truncated": None, "results": rows}

    def dump():
        return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))

    out = dump()
    while nbytes(out) + 1 > max_bytes and doc["results"]:
        doc["results"] = doc["results"][:-1]
        doc["truncated"] = {"dropped": len(rows) - len(doc["results"]), "max_bytes": max_bytes,
                            "hint": "--max-bytes / --top"}
        out = dump()
    for n in (160, 60, 20, 8):               # MIN_BYTES leaves room for n = 8 even in 4-byte characters
        if nbytes(out) + 1 <= max_bytes:
            break
        doc["truncated"] = {"dropped": len(rows), "max_bytes": max_bytes, "hint": "--max-bytes / --top"}
        doc.update(query=one_line(q, n), groups=doc["groups"] if n > 20 else [],
                   notes=[one_line(x, n) for x in notes] if n > 8 else [])
        out = dump()
    return out


def dedupe(ranked):
    """Best-scored copy of each skill (ident_keys); ranked is sorted best first."""
    seen, out = set(), []
    for r in ranked:
        ks = r[2].get("_id") or ident_keys(r[2])
        if any(k in seen for k in ks):
            continue
        seen.update(ks)
        out.append(r)
    return out


def emit(text):
    """Every stdout answer goes through scrub(): no invisible character reaches the reader."""
    print(scrub(text))


def main(argv=None):
    ap = argparse.ArgumentParser(description="query-first local skill index (stdlib only, read-only except its cache)")
    ap.add_argument("--query", "-q", default=None)
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--json", action="store_true", help="results as compact JSON, also <= --max-bytes")
    ap.add_argument("--desc-len", type=int, default=90)
    ap.add_argument("--max-bytes", type=int, default=2048)
    ap.add_argument("--cache", default=default_cache_path())
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--max-age-hours", type=float, default=24)
    ap.add_argument("--root", action="append", default=[], help="extra directory to scan (tier 'other'); repeatable")
    ap.add_argument("--tier", action="append", default=[], choices=TIERS)
    ap.add_argument("--installed-only", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="include non-loadable ghosts (a nested SKILL.md, or one outside a plugin's skill paths)")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--show", default=None,
                    help="plugin record first, then the entries of that exact invoke name / name / path (<= 2 KB)")
    a = ap.parse_args(argv)
    if not (a.query or a.stats or a.show):
        ap.print_usage()
        return 2
    if inside_skill_folder(a.cache):
        print("error: --cache must not point inside the skill folder (default: %s)" % default_cache_path(), file=sys.stderr)
        return 2
    if a.max_bytes < MIN_BYTES:              # a silent raise would break the cap the caller asked for
        print("error: --max-bytes must be at least %d (default 2048)" % MIN_BYTES, file=sys.stderr)
        return 2
    t0 = time.time()
    R = derive_roots(os.getcwd(), a.root)
    idx = load_or_build(a.cache, R, a.refresh, a.max_age_hours)
    notes = [n for n in (idx.get("schema_note"), self_note(idx["entries"], R), idx.get("cache_note")) if n]
    ents = idx["entries"]
    if not a.all:
        ents = [e for e in ents if e.get("loadable", True)]
    if a.tier:
        ents = [e for e in ents if e["tier"] in a.tier]
    if a.installed_only:
        ents = [e for e in ents if e.get("invoke")]
    if a.stats:
        from collections import Counter
        c = Counter(e["tier"] for e in idx["entries"])
        usable = sum(1 for e in idx["entries"] if e.get("invoke"))
        ghosts = sum(1 for e in idx["entries"] if not e.get("loadable", True))
        size = os.path.getsize(a.cache) if os.path.isfile(a.cache) else 0
        L = ["cache: %s (%s, built %s, build %sms, rebuilt_because=%s)" % (
            a.cache, ("%d bytes" % size) if size and not idx.get("cache_note") else "not written",
            idx["built_at"], idx.get("build_ms"), idx.get("rebuilt_because"))]
        L += ["not: " + n for n in notes]
        L.append("entries: %d  usable-now(invoke!=None): %d  ghosts(not loadable): %d" % (len(idx["entries"]), usable, ghosts))
        L += ["  %-18s %5d" % (k, c[k]) for k in TIERS if c.get(k)]
        L.append("fingerprint keys: %d ; elapsed %d ms" % (len(idx["fingerprint"]), int((time.time() - t0) * 1000)))
        emit("\n".join(L))
    if a.show:
        s, hits = find_show(a.show, ents, R, a.tier, a.installed_only)
        head = "".join("not: %s\n" % n for n in notes) if not a.stats else ""
        if hits:
            emit(head + show_many(hits, s, max(300, SHOW_MAX - nbytes(head))))
        else:                                # exit code stays 0: 2 is reserved for bad arguments
            emit(head + "no entry matches %r (index + official catalog)" % a.show)
    if a.query:
        groups = expand_query(a.query)
        qf = fold(a.query).strip()
        ranked = []
        for e in ents:
            if is_self(e):                         # this skill is never a hit of its own search
                continue
            sc, hit = score(e, groups, qf)
            if sc > 0:
                ranked.append((sc, hit, e))
        ranked.sort(key=lambda r: (-r[0], r[2].get("invoke") is None, r[2]["tier"], r[2].get("name") or ""))
        ranked = dedupe(ranked)
        shown = notes if not (a.stats or a.show) else []
        if a.json:
            emit(fmt_json(a.query, idx, ranked, a.top, a.desc_len, a.max_bytes, shown))
        else:
            emit(fmt_text(a.query, idx, ranked, a.top, a.desc_len, a.max_bytes, shown))
            print("(%d ms)" % int((time.time() - t0) * 1000), file=sys.stderr)   # keep stdout <= --max-bytes
    return 0


if __name__ == "__main__":
    sys.exit(main())
