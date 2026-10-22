#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill_envanteri.py  -  READ-ONLY inventory of every on-disk skill / plugin location
of the machine it runs on (Claude Code + Claude desktop app + marketplaces). Windows, macOS, Linux.
  Not scanned: Cowork scheduled tasks and session uploads, Claude Desktop's own config file, and
  other tools' folders such as ~/.codex (pass --extra-root DIR to include a folder on purpose).

* Where it looks (nothing is hard-coded; the same rules as skill_ara.py):
    <config>  = $CLAUDE_CONFIG_DIR, else ~/.claude (every OS)
    <plugins> = $CLAUDE_CODE_PLUGIN_CACHE_DIR, else <config>/plugins
    <desktop> = $CLAUDE_DESKTOP_DATA_DIR, else Windows: the first that holds local-agent-mode-sessions of
                %APPDATA%/Claude, %LOCALAPPDATA%/Claude-Data/<id> (observed 2026-10-22; of several, the newest
                local-agent-mode-sessions) and %LOCALAPPDATA%/Packages/Claude_*/LocalCache/Roaming/Claude (observed
                2026-10-14), none: %APPDATA%/Claude; macOS ~/Library/Application Support/Claude, Linux
                $XDG_CONFIG_HOME/Claude or ~/.config/Claude (macOS / Linux: not verified on a real machine)
  User, project and --extra-root skill folders that are symlinks (npx skills on macOS/Linux) are followed, with a
  cycle guard. Project ancestors go up to the git root and never include the home directory (~/.claude/skills is the
  user tier, never a project).

* Arguments (all optional):
    --out DIR            where the two JSON files go (default: cache_root(): Windows <tempdir>/skill-sleuth,
                         macOS/Linux $XDG_CACHE_HOME/skill-sleuth or ~/.cache/skill-sleuth, mode 0700).
                         An --out inside the skill folder is refused (exit 2): the skill folder is read-only.
                         On macOS/Linux an --out owned by another user or writable by group/others is not written
                         to ("not: ... yazilmadi" on stdout, exit 0).
    --project-dir DIR    the "current project" whose .claude/skills (+ ancestors up to the git root) count as
                         tier "project" (default: the current working directory).
    --extra-root DIR     extra tree to scan for */.claude/skills and standalone SKILL.md files
                         (repeatable; default: none).
* Modifies NOTHING except writing two JSON files into --out:
    02-skill-envanteri.json        -> list of skill/command entries (large, can reach 1 MB: keep it out of context)
    02-skill-envanteri-ozet.json   -> summary counts + root metadata (small)
  stdout: a short summary table (a few KB). Exit codes: 0 ok, 2 bad arguments / refused --out.
* No third-party dependencies (PyYAML is not required) -> hand-written
  YAML-frontmatter subset parser that handles plain, "double-quoted" (multi-line,
  \\n escapes), 'single-quoted' ('' escapes), >/| block scalars, nested maps,
  lists, flow lists and trailing "# comments".

Entry schema (every entry):
  name, description, path, source_kind, plugin, marketplace, installed, enabled,
  has_scripts, has_references
Extra fields (additive):
  entry_type ("skill" | "command"), root_label, skill_tool_name (expected name in
  the Claude Code Skill tool listing, or null), disable_model_invocation,
  frontmatter_keys, has_assets, has_agents, notes, project_root, plugin_version,
  plugin_id, marketplace_display, frontmatter_error, ...
"""
import os, re, json, glob, datetime, stat, sys, time, argparse, tempfile, unicodedata, builtins

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ---------------------------------------------------------------- third-party text (_INVIS, clean, hidden_count, scrub: identical to skill_ara.py)
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


def print(*args, **kw):
    """Every line this script prints goes through scrub(): no invisible character reaches the reader."""
    builtins.print(*(scrub(str(a)) for a in args), **kw)

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


HOME = os.path.expanduser("~")
CLAUDE_HOME = claude_config_dir()
PLUGINS = plugins_root()
DESKTOP_DATA = desktop_data_dir()
LAMS = os.path.join(DESKTOP_DATA, "local-agent-mode-sessions")
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)                        # the skill folder (read-only for this script)
DEFAULT_OUT = cache_root()


def _is_under(path, parent):
    p = os.path.normpath(os.path.abspath(path)).lower()
    q = os.path.normpath(os.path.abspath(parent)).lower()
    return p == q or p.startswith(q + os.sep)


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="read-only inventory of every on-disk skill/plugin location")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="output dir for 02-skill-envanteri.json + 02-skill-envanteri-ozet.json (default: %s)" % DEFAULT_OUT)
    ap.add_argument("--project-dir", default=os.getcwd(),
                    help="project whose .claude/skills (+ ancestors) count as tier 'project' (default: cwd)")
    ap.add_argument("--extra-root", action="append", default=[],
                    help="extra tree to scan for */.claude/skills and standalone SKILL.md (repeatable; default: none)")
    return ap.parse_args(argv)


ARGS = _parse_args()
PROJECT_DIR = os.path.abspath(ARGS.project_dir)
EXTRA_SCAN_ROOTS = [os.path.abspath(r) for r in ARGS.extra_root]
OUT_DIR = os.path.abspath(ARGS.out)
if _is_under(OUT_DIR, SKILL_DIR):
    print("error: --out must not point inside the skill folder (%s); default is %s" % (SKILL_DIR, DEFAULT_OUT), file=sys.stderr)
    sys.exit(2)
OUT_LIST = os.path.join(OUT_DIR, "02-skill-envanteri.json")
OUT_SUMMARY = os.path.join(OUT_DIR, "02-skill-envanteri-ozet.json")

SKIP_DIRS = {".git", "node_modules", ".in_use", "__pycache__", ".venv", "venv"}

# ----------------------------------------------------------------------------- helpers
def read_text(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""

def read_json(p, default=None):
    """Parsed JSON file, else default; utf-8-sig: a file saved with a BOM is read like Claude Code reads it."""
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default

def norm(p):
    return os.path.normpath(p).replace("\\", "/")

def jdict(x):
    """x when it is a JSON object, else {}: a file of another shape never raises."""
    return x if isinstance(x, dict) else {}

def by_key(rows, key):
    """[{key: <str>, ...}, ...] -> {<str>: row}; rows that are not objects or lack a string key are skipped."""
    return dict((r[key], r) for r in (rows if isinstance(rows, list) else [])
                if isinstance(r, dict) and isinstance(r.get(key), str))

def jlist(x):
    """x when it is a JSON array, else []."""
    return x if isinstance(x, list) else []

def src_kind(src):
    """The 'source' of a marketplace.json plugin entry: a string as is, an object's "source" field, else None."""
    return src if isinstance(src, str) else jdict(src).get("source")

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

def walk_files(root, filename=None, pattern=None, maxdepth=50, follow=False):
    """Yield files under root (skipping SKIP_DIRS). filename = exact basename match. follow=True also descends
    into symlinked directories; a directory whose real path is already on its own path from root (a cycle) is not
    entered again (same walk as skill_ara.py)."""
    root = os.path.normpath(root)
    if not os.path.isdir(root):
        return
    base_depth = root.count(os.sep)
    real = {root: os.path.normcase(os.path.realpath(root))}
    chain = {root: frozenset([real[root]])}
    for dp, dns, fns in os.walk(root, followlinks=follow):
        if dp != root:
            up = os.path.dirname(dp)
            r = (os.path.normcase(os.path.realpath(dp)) if _is_link(dp)
                 else os.path.join(real.get(up, up), os.path.normcase(os.path.basename(dp))))
            seen = chain.get(up, frozenset())
            if r in seen:
                dns[:] = []
                continue
            real[dp], chain[dp] = r, seen | {r}
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        if dp.count(os.sep) - base_depth >= maxdepth:
            dns[:] = []
        for fn in fns:
            if filename and fn == filename:
                yield os.path.join(dp, fn)
            elif pattern and re.search(pattern, fn):
                yield os.path.join(dp, fn)

# ----------------------------------------------------------------------------- frontmatter parser
KEY_RE = re.compile(r'^([A-Za-z0-9_.\-]+)\s*:(?:\s+(.*))?$')

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

_ESC = {"n": "\n", "t": "\t", '"': '"', "\\": "\\", "/": "/", "'": "'", " ": " "}
def _unescape_dq(s):
    return re.sub(r"\\(.)", lambda m: _ESC.get(m.group(1), m.group(1)), s)

def _strip_scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        return _unescape_dq(inner) if v[0] == '"' else inner.replace("''", "'")
    return re.sub(r"\s+#.*$", "", v)

def _coerce(v):
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    return v

def parse_frontmatter(text):
    """Return (dict, error). Hand-rolled YAML subset sufficient for SKILL.md files."""
    text = text.lstrip("\ufeff")
    lines = text.splitlines()
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
                        sub[mm.group(1)] = _coerce(_strip_scalar(mm.group(2) or ""))
                fm[key] = sub
            else:
                fm[key] = " ".join(b.strip() for b in block if b.strip())
            i = j
            continue
        c = rest[0]
        if c in "|>" and re.match(r'^[|>][+-]?\d*\s*(#.*)?$', rest):
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
                buf += " " + body[j].strip()      # YAML folds line breaks inside quotes to a space
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
        if c == "[":                                  # flow list
            fm[key] = [_strip_scalar(x) for x in rest.strip("[]").split(",") if x.strip()]
            i += 1
            continue
        # plain scalar (may continue on indented lines)
        val = rest
        j = i + 1
        while j < len(body) and body[j][:1] in (" ", "\t") and body[j].strip() and not KEY_RE.match(body[j].strip()):
            val += " " + body[j].strip()
            j += 1
        fm[key] = _coerce(re.sub(r"\s+#.*$", "", val).strip())
        i = j
    return fm, None

# ----------------------------------------------------------------------------- config sources
def _same_path(a, b):
    return os.path.normcase(os.path.normpath(os.path.abspath(a))) == os.path.normcase(os.path.normpath(os.path.abspath(b)))


def _pkey(p):
    return os.path.normcase(os.path.normpath(os.path.abspath(p)))


def git_root(d):
    """Same as skill_ara.py: the nearest folder from d upwards (d included) holding a .git entry, else None."""
    p = os.path.normpath(os.path.abspath(d))
    while True:
        if os.path.lexists(os.path.join(p, ".git")):
            return p
        q = os.path.dirname(p)
        if q == p:
            return None
        p = q


def main_checkout(root):
    """Same as skill_ara.py: the main checkout's root for a git worktree root (commondir followed; a bare
    repository's common dir itself), else None."""
    try:
        with open(os.path.join(root, ".git"), "r", encoding="utf-8-sig", errors="replace") as f:
            line = f.read(4096).strip()
    except (OSError, ValueError):
        return None
    if not line.startswith("gitdir:"):
        return None
    gd = os.path.normpath(os.path.join(root, line[len("gitdir:"):].strip()))
    try:
        with open(os.path.join(gd, "commondir"), "r", encoding="utf-8-sig", errors="replace") as f:
            common = os.path.normpath(os.path.join(gd, f.read(4096).strip()))
    except (OSError, ValueError):
        common = os.path.dirname(os.path.dirname(gd))
    if not _same_path(os.path.dirname(gd), os.path.join(common, "worktrees")):
        return None
    if os.path.basename(common) != ".git":
        return None if os.path.lexists(os.path.join(common, ".git")) else common
    return os.path.dirname(common)


def env_true(name):
    """Same as skill_ara.py: an environment flag is true only for 1 / true / yes / on."""
    return (os.environ.get(name) or "").strip().lower() in ("1", "true", "yes", "on")


def local_settings_root(cwd):
    """Same as skill_ara.py: macOS / Linux, the canonical git root's .claude/settings.local.json (owned by the
    current user, not cwd itself), else None."""
    if os.name == "nt" or not hasattr(os, "geteuid"):
        return None
    root = git_root(cwd)
    if root is None:
        return None
    root = main_checkout(root) or root
    if _same_path(root, cwd) or _same_path(os.path.realpath(root), os.path.realpath(HOME)):
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


# enabledPlugins and skillOverrides as Claude Code sees them in the project dir (same rule as skill_ara.py
# merged_setting()): user < project < local (macOS / Linux: < the git root's local file), a later file winning per entry
SETTINGS_FILES = [f for f in (os.path.join(CLAUDE_HOME, "settings.json"), os.path.join(PROJECT_DIR, ".claude", "settings.json"),
                              os.path.join(PROJECT_DIR, ".claude", "settings.local.json"), local_settings_root(PROJECT_DIR)) if f]
enabled_plugins, skill_overrides = {}, {}
for _f in SETTINGS_FILES:
    _d = jdict(read_json(_f, {}))
    enabled_plugins.update(jdict(_d.get("enabledPlugins")))
    skill_overrides.update(jdict(_d.get("skillOverrides")))
# folders of a skills dir switched off with enabledPlugins "<name>@skills-dir": false (they load neither way)
SD_OFF = set(k[:-len("@skills-dir")] for k, v in enabled_plugins.items()
             if v is False and isinstance(k, str) and k.endswith("@skills-dir"))
_installed_doc = jdict(read_json(os.path.join(PLUGINS, "installed_plugins.json"), {}))
installed_known = isinstance(_installed_doc.get("plugins"), dict)
installed_plugins = jdict(_installed_doc.get("plugins"))
known_marketplaces = jdict(read_json(os.path.join(PLUGINS, "known_marketplaces.json"), {}))


def _records(x):
    return [r for r in (x if isinstance(x, list) else [x]) if isinstance(r, dict)]


def record_applies(r, cwd):
    """Same as skill_ara.py (Claude Code's hx()): user / managed scope, or a projectPath that is cwd or shares its
    git root."""
    if r.get("scope") in (None, "user", "managed"):
        return True
    pp = r.get("projectPath")
    if not isinstance(pp, str) or not pp:
        return False
    if _same_path(pp, cwd):
        return True
    a, b = git_root(cwd), git_root(pp)
    return a is not None and b is not None and _same_path(main_checkout(a) or a, main_checkout(b) or b)


LIVE = {}                                    # _pkey(install folder) -> plugin id: per plugin the first record that
for _pid, _recs in installed_plugins.items():  # applies here and names a folder that exists (Claude Code's cbn())
    for _r in _records(_recs):
        _ip = _r.get("installPath")
        if isinstance(_pid, str) and isinstance(_ip, str) and _ip and record_applies(_r, PROJECT_DIR) and os.path.isdir(_ip):
            LIVE.setdefault(_pkey(_ip), _pid)
            break
INSTALLED_HERE = set(pid for pid, recs in installed_plugins.items()
                     if isinstance(pid, str) and any(record_applies(r, PROJECT_DIR) for r in _records(recs)))


def cache_key_of(ver, folder_key):
    """Same rule as skill_ara.py cache_key_of(): the plugin id whose live install the cache folder ver is, else None."""
    if os.path.lexists(os.path.join(ver, ".orphaned_at")):
        return None
    if not installed_known:
        return folder_key
    k = LIVE.get(_pkey(ver))
    if k is not None:
        return k
    recs = [r for r in _records(installed_plugins.get(folder_key)) if record_applies(r, PROJECT_DIR)]
    if recs and not any(isinstance(r.get("installPath"), str) and os.path.isdir(r["installPath"]) for r in recs):
        return folder_key
    return None

entries = []
roots_meta = []

def add_root(label, path, exists, note=""):
    roots_meta.append({"label": label, "path": norm(path), "exists": bool(exists), "note": note})

def make_entry(path, source_kind, entry_type="skill", plugin=None, marketplace=None,
               installed=True, enabled=None, root_label=None, skill_tool_name=None,
               notes=None, **extra):
    d = os.path.dirname(path)
    fm, err = parse_frontmatter(read_text(path))
    fm_name = fm.get("name")
    if isinstance(fm_name, str) and fm_name.strip():
        name = fm_name.strip()
    elif entry_type == "skill":
        name = os.path.basename(d)
    else:
        name = os.path.splitext(os.path.basename(path))[0]
    desc = fm.get("description", "")
    if not isinstance(desc, str):
        desc = json.dumps(desc, ensure_ascii=False)
    dmi = fm.get("disable-model-invocation")
    if isinstance(dmi, bool):
        pass
    elif dmi is None:
        dmi = False
    else:
        dmi = str(dmi).strip().lower() == "true"
    is_skill = entry_type == "skill"
    # The Claude Code Skill tool keys plugin skills by DIRECTORY name, not by frontmatter `name`
    # (verified: rpm/.../skills/strip-profile/SKILL.md has `name: fsi-strip-profile` but is listed
    # as investment-banking:strip-profile). Commands are keyed by file stem.
    dir_name = os.path.basename(d) if is_skill else os.path.splitext(os.path.basename(path))[0]
    e = {
        "name": name,
        "dir_name": dir_name,
        "frontmatter_name": fm_name if isinstance(fm_name, str) else None,
        "description": desc,
        "path": norm(path),
        "source_kind": source_kind,
        "plugin": plugin,
        "marketplace": marketplace,
        "installed": bool(installed),
        "enabled": enabled,
        "has_scripts": os.path.isdir(os.path.join(d, "scripts")) if is_skill else False,
        "has_references": (os.path.isdir(os.path.join(d, "references")) or os.path.isdir(os.path.join(d, "reference"))) if is_skill else False,
        "entry_type": entry_type,
        "root_label": root_label,
        "skill_tool_name": (None if dmi else skill_tool_name),
        "disable_model_invocation": dmi,
        "frontmatter_keys": list(fm.keys()),
        "has_assets": os.path.isdir(os.path.join(d, "assets")) if is_skill else False,
        "has_agents": os.path.isdir(os.path.join(d, "agents")) if is_skill else False,
        "frontmatter_error": err,
        "notes": notes,
    }
    e.update(extra)
    entries.append(e)
    return e

def plugin_commands(plugin_dir):
    cdir = os.path.join(plugin_dir, "commands")
    if not os.path.isdir(cdir):
        return []
    return sorted(glob.glob(os.path.join(cdir, "*.md")))

def _escapes(plugin_dir, p):
    """Same as skill_ara.py: the path leaves plugin_dir (Claude Code rejects it)."""
    try:
        rel = os.path.relpath(os.path.realpath(p), os.path.realpath(plugin_dir))
    except ValueError:
        return True
    return rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel)

def _skill_dirs(plugin_dir, v):
    out = []
    for x in ([v] if isinstance(v, str) else jlist(v)):
        if isinstance(x, str) and x:
            p = os.path.normpath(os.path.join(plugin_dir, x))
            if os.path.isdir(p) and not _escapes(plugin_dir, p) and not any(_same_path(p, q) for q in out):
                out.append(p)
    return out

def _js_true(v):
    """Same as skill_ara.py: JavaScript truthiness of a JSON value."""
    return not (v is None or v is False or v == "" or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0))

def plugin_skill_paths(plugin_dir, pj, entry=None, skills_dir=False):
    """Same rule as skill_ara.py plugin_skill_paths(): plugin.json (pj None: none) and the marketplace entry decide
    the skill paths; None when Claude Code refuses the plugin (strict: false and components on both sides)."""
    root = os.path.normpath(plugin_dir)
    default = os.path.join(root, "skills")
    base = default if os.path.isdir(default) else None
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
                base, paths = None, []
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
    p = os.path.join(d, ".claude-plugin", "plugin.json")
    return jdict(read_json(p, {})) if os.path.isfile(p) else None

def skills_dir_plugins(skills_root, user=True):
    """Same rule as skill_ara.py: a folder of a skills dir with a readable .claude-plugin/plugin.json loads as a
    plugin "<name>@skills-dir" (user dir: dot-prefixed folders and synced/ skipped; none with
    CLAUDE_CODE_RESTRICT_PERSONAL_CONFIG)."""
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
    """Same as skill_ara.py: the plugin.json name (a string), else the folder name."""
    n = jdict(pj).get("name")
    return n if isinstance(n, str) and n else os.path.basename(d)

def marketplace_entries():
    """Same as skill_ara.py: {marketplace: {plugin name: marketplace.json entry}}."""
    locs = {}
    for name, info in known_marketplaces.items():
        loc = jdict(info).get("installLocation")
        if isinstance(name, str) and isinstance(loc, str) and loc:
            locs[name] = loc
    for d in glob.glob(os.path.join(glob.escape(os.path.join(PLUGINS, "marketplaces")), "*")):
        if os.path.isdir(d):
            locs.setdefault(os.path.basename(d), d)
    return dict((m, by_key(jdict(read_json(os.path.join(loc, ".claude-plugin", "marketplace.json"), {})).get("plugins"),
                           "name")) for m, loc in locs.items())

REFUSED_NOTE = "its marketplace entry has strict: false and declares components while the plugin has a plugin.json: Claude Code refuses to load it"

def plugin_skill_slot(skill_md, paths):
    """Same rule as skill_ara.py: "dir" (<path>/<name>/SKILL.md), "self" (<path>/SKILL.md: that path is one skill)
    or None (not loaded: deeper, or outside every skill path)."""
    d = os.path.dirname(skill_md)
    for sp in paths:
        if os.path.isfile(os.path.join(sp, "SKILL.md")):
            if _same_path(d, sp):
                return "self"
        elif _same_path(os.path.dirname(d), sp):
            return "dir"
    return None

def _rel(path, base):
    """path relative to base for a note; the absolute path when there is none (Windows: another drive or a UNC
    share makes os.path.relpath raise ValueError)."""
    try:
        return norm(os.path.relpath(path, base))
    except ValueError:
        return norm(path)

def top_level(skill_md, root):
    """User and project skills: only <root>/<name>/SKILL.md (one level) is loaded."""
    return _same_path(os.path.dirname(os.path.dirname(skill_md)), root)

GHOST_NOTE = "not loaded by Claude Code: only <skills dir>/<name>/SKILL.md (one level) is a skill"

def set_tool_name(e, prefix=None, slot="dir"):
    """Expected Skill-tool name: bare for user/project, '<plugin>:<name>' for plugins. A plugin skill path that holds
    the SKILL.md itself (slot "self") is named by its frontmatter name (a leading '<plugin>:' removed); plugin
    skill names keep only [A-Za-z0-9_-] (same rules as skill_ara.py)."""
    if e["disable_model_invocation"] or not e["enabled"]:
        e["skill_tool_name"] = None
        return
    key = e["dir_name"]
    if slot == "self" and isinstance(e.get("frontmatter_name"), str) and e["frontmatter_name"].strip():
        key = e["frontmatter_name"].strip()
        if prefix and key.startswith(prefix + ":"):
            key = key[len(prefix) + 1:] or e["dir_name"]
    if prefix and e["entry_type"] == "skill":
        key = re.sub(r"[^a-zA-Z0-9_-]", "-", key)
    e["skill_tool_name"] = f"{prefix}:{key}" if prefix else key

def apply_overrides(e):
    """Same rule as skill_ara.py overridden(): skillOverrides "off" / "user-invocable-only" for a user or project skill
    (looked up by its folder name) -> no Skill-tool name."""
    v = skill_overrides.get(e["dir_name"])
    if v in ("off", "user-invocable-only"):
        e["skill_tool_name"] = None
        e["notes"] = "skillOverrides: %s (switched on again in /skills)" % v

def _under(p, d):
    return _pkey(p).startswith(_pkey(d).rstrip(os.sep) + os.sep)

def add_skills_dir(root, source_kind, root_label, plugins, **kw):
    """Same rules as skill_ara.py build_index() add_skills_dir(): <root>/<name>/SKILL.md are skills with bare names
    (deeper ones are ghosts); a folder with .claude-plugin/plugin.json is also a plugin "<name>@skills-dir" (name =
    its plugin.json name, else the folder) whose skills and commands are <name>:<x>, enabled unless enabledPlugins
    says false (or plugin.json "defaultEnabled": false without enabledPlugins true); "<name>@skills-dir": false
    also switches that folder's own SKILL.md off. plugins is None for an ancestor project dir."""
    sdp = dict((_pkey(d), (d, pj, skills_dir_name(d, pj))) for d, pj in plugins or [])
    roots = [d for d, _, _ in sdp.values()]
    for p in walk_files(root, filename="SKILL.md", follow=True):
        if source_kind == "user" and _under(p, os.path.join(root, "synced")):
            if "/.staging/" not in norm(p):  # claude.ai sync: never a bare name (skill_ara.py tier user-synced)
                make_entry(p, "user-synced", installed=True, enabled=None, root_label="user-synced",
                           notes="claude.ai synced skill: no bare Skill-tool name (desktop: anthropic-skills:<name>)")
            continue
        top = top_level(p, root)
        if not top and any(_under(p, d) for d in roots):
            continue
        folder = sdp.get(_pkey(os.path.dirname(p)))
        off = bool(top and folder and folder[2] in SD_OFF)
        e = make_entry(p, source_kind, installed=True, enabled=top and not off, root_label=root_label,
                       notes=GHOST_NOTE if not top else ("enabledPlugins %s@skills-dir: false" % folder[2]) if off else None,
                       **kw)
        set_tool_name(e)
        apply_overrides(e)
    for d, pj, name in sdp.values():
        ep = enabled_plugins.get(name + "@skills-dir")
        en = ep if isinstance(ep, bool) else pj.get("defaultEnabled") is not False
        note_off = None if en else ("enabledPlugins %s@skills-dir: false" % name if ep is False else
                                    "defaultEnabled: false (enabledPlugins %s@skills-dir: true switches it on)" % name)
        spaths = plugin_skill_paths(d, pj, skills_dir=True)
        for p in walk_files(d, filename="SKILL.md", follow=True):
            if _same_path(os.path.dirname(p), d):
                continue
            slot = plugin_skill_slot(p, spaths)
            e = make_entry(p, source_kind, plugin=name, marketplace="skills-dir", installed=True,
                           enabled=bool(slot) and en, root_label=root_label + "(skills-dir plugin)",
                           notes=note_off or (None if slot else "outside the plugin's skill paths, or nested -> not loaded"),
                           **kw)
            set_tool_name(e, name, slot)
        if not _js_true(pj.get("commands")):
            for c in plugin_commands(d):
                e = make_entry(c, source_kind, entry_type="command", plugin=name, marketplace="skills-dir",
                               installed=True, enabled=en, root_label=root_label + "(skills-dir plugin)", notes=note_off,
                               **kw)
                set_tool_name(e, name)

# ----------------------------------------------------------------------------- 1. user skills
user_skills = os.path.join(CLAUDE_HOME, "skills")
add_root("user", user_skills, os.path.isdir(user_skills),
         "~/.claude/skills/<name>/SKILL.md - always loaded by Claude Code, listed by bare name")
add_skills_dir(user_skills, "user", "user-skills", skills_dir_plugins(user_skills))

# ----------------------------------------------------------------------------- 2. project skills (cwd + ancestors; other trees via --extra-root)
def ancestors(p):
    """Same rule as skill_ara.py project_dirs(): p and its ancestors up to the git root (without a repository: up to
    the filesystem root, stopping at the home directory, which is never a project), a dir whose .claude/skills IS
    the user skills dir skipped; in a worktree without its own .claude/skills, the main checkout follows."""
    def key(x):
        return os.path.normcase(os.path.realpath(x))
    hk, us = key(HOME), key(user_skills)
    start = os.path.normpath(os.path.abspath(p))
    root = git_root(start)
    p = start
    out = []
    while True:
        if key(p) == hk:                     # the home directory is never a project (same as skill_ara.py)
            break
        if key(os.path.join(p, ".claude", "skills")) != us:
            out.append(p)
        if root is not None and _same_path(p, root):
            break
        q = os.path.dirname(p)
        if q == p:
            break
        p = q
    main = main_checkout(root) if root is not None else None
    if main and not os.path.isdir(os.path.join(root, ".claude", "skills")) and not any(_same_path(main, x) for x in out):
        if key(os.path.join(main, ".claude", "skills")) != us:
            out.append(main)
    return out

seen_project_roots = set()
for anc in ancestors(PROJECT_DIR):
    sk = os.path.join(anc, ".claude", "skills")
    is_cwd = os.path.normpath(anc).lower() == os.path.normpath(PROJECT_DIR).lower()
    add_root("project" if is_cwd else "project-ancestor", sk, os.path.isdir(sk),
             "<project>/.claude/skills (cwd)" if is_cwd else "ancestor .claude/skills up to the git root (loaded too)")
    seen_project_roots.add(os.path.normpath(anc).lower())
    add_skills_dir(sk, "project", "project-skills", skills_dir_plugins(sk, user=False) if is_cwd else None,
                   project_root=norm(anc))

def marketplace_repo_root(p, stop_root):
    """Walk up from p (a SKILL.md) to stop_root; return the first dir holding .claude-plugin/marketplace.json, else None."""
    d = os.path.dirname(p)
    stop = os.path.normpath(stop_root).lower()
    while True:
        if os.path.isfile(os.path.join(d, ".claude-plugin", "marketplace.json")):
            return d
        q = os.path.dirname(d)
        if os.path.normpath(d).lower() == stop or q == d:
            return None
        d = q

registered_marketplace_dirs = {norm(v.get("installLocation")).lower() for v in known_marketplaces.values()
                               if isinstance(v, dict) and isinstance(v.get("installLocation"), str)}

for root in EXTRA_SCAN_ROOTS:
    add_root("extra-scan", root, os.path.isdir(root),
             "scanned for */.claude/skills/*/SKILL.md and standalone SKILL.md (node_modules/.git skipped; docs/ copies inside a marketplace repo skipped)")
    for p in walk_files(root, filename="SKILL.md", maxdepth=12, follow=True):
        np_ = norm(p)
        mroot = marketplace_repo_root(p, root)
        if mroot and "/docs/" in np_[len(norm(mroot)):]:    # translated/duplicate copies under <repo>/docs/
            continue
        m = re.search(r"^(.*)/\.claude/skills/([^/]+)/SKILL\.md$", np_)
        if m:
            proj = os.path.normpath(m.group(1))
            if proj.lower() in seen_project_roots:
                continue
            make_entry(p, "project", installed=True, enabled=False, root_label="other-project-skills",
                       project_root=norm(proj),
                       notes="belongs to a different project dir; only loaded when Claude Code runs with that cwd")
            continue
        if mroot:
            mname = os.path.basename(mroot)
            registered = norm(mroot).lower() in registered_marketplace_dirs
            pm = re.search(r"/plugins/([^/]+)/", np_[len(norm(mroot)):])
            state = "registered" if registered else "unregistered"
            make_entry(p, "unknown", installed=True, enabled=False, root_label=f"local-{state}-marketplace-repo({mname})",
                       plugin=(pm.group(1) if pm else mname.lower()), marketplace=f"{mname.lower()}({state})",
                       notes=(f"{norm(mroot)} ships .claude-plugin/marketplace.json but is NOT in known_marketplaces.json -> not loadable until added via /plugin marketplace add"
                              if not registered else
                              f"{norm(mroot)} is a registered marketplace clone outside ~/.claude/plugins; install its plugins with claude plugin install <plugin>@{mname}"))
            continue
        make_entry(p, "unknown", installed=True, enabled=False, root_label="standalone-skill-folder",
                   notes="SKILL.md in a plain folder (not under any .claude/skills, plugin or bundle) -> not loaded by any harness")

# ----------------------------------------------------------------------------- 3. plugin cache (installed Claude Code plugins)
plugin_cache = os.path.join(PLUGINS, "cache")
MKT_ENTRIES = marketplace_entries()
CATALOG_PLUGINS = jdict(jdict(jdict(read_json(os.path.join(PLUGINS, "plugin-catalog-cache.json"), {})).get("catalog")).get("plugins"))
add_root("plugin-cache", plugin_cache, os.path.isdir(plugin_cache),
         "~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/ ; enabled via settings.json enabledPlugins['<plugin>@<marketplace>']")
for mkt in sorted(glob.glob(os.path.join(plugin_cache, "*"))):
    if not os.path.isdir(mkt):
        continue
    for plug in sorted(glob.glob(os.path.join(mkt, "*"))):
        if not os.path.isdir(plug):
            continue
        for ver in sorted(glob.glob(os.path.join(plug, "*"))):
            if not os.path.isdir(ver):
                continue
            vname = os.path.basename(ver)
            folder_key = "%s@%s" % (os.path.basename(plug), os.path.basename(mkt))
            key = cache_key_of(ver, folder_key)   # None: a folder an update, an uninstall or another project left
            live = key is not None                # behind (listed, never enabled)
            key = key or folder_key
            kname, _, mname = key.rpartition("@")
            pj = plugin_json(ver)
            entry = (jdict(MKT_ENTRIES.get(mname)).get(kname) or jdict(CATALOG_PLUGINS.get(key)).get("marketplace_entry")
                     or None)
            pdisp = jdict(pj).get("name") if isinstance(jdict(pj).get("name"), str) and jdict(pj).get("name") else \
                (jdict(entry).get("name") or kname)
            inst_rec = installed_plugins.get(key)
            en = live and bool(enabled_plugins.get(key, False))
            spaths = plugin_skill_paths(ver, pj, entry)
            for p in walk_files(ver, filename="SKILL.md"):
                slot = plugin_skill_slot(p, spaths) if spaths is not None else None
                e = make_entry(p, "plugin-cache", plugin=pdisp, marketplace=mname, installed=live,
                               enabled=(en and bool(slot)), root_label="plugin-cache",
                               plugin_version=vname, installed_record=bool(inst_rec),
                               notes=("version folder not in use here (an update, an uninstall or another project's "
                                      "install left it behind)" if not live else None if slot else
                                      REFUSED_NOTE if spaths is None else
                                      "outside the plugin's skill paths, or nested -> not loaded"))
                set_tool_name(e, pdisp, slot)
            for c in plugin_commands(ver):
                e = make_entry(c, "plugin-cache", entry_type="command", plugin=pdisp, marketplace=mname,
                               installed=live, enabled=en and spaths is not None, root_label="plugin-cache",
                               plugin_version=vname)
                set_tool_name(e, pdisp)

# ----------------------------------------------------------------------------- 4. marketplace clones (catalog copies, mostly NOT installed)
mkts_root = os.path.join(PLUGINS, "marketplaces")
add_root("marketplace-clone", mkts_root, os.path.isdir(mkts_root),
         "~/.claude/plugins/marketplaces/<marketplace>/ full git clone; .claude-plugin/marketplace.json lists all plugins (remote 'url'/'git-subdir' sources have NO SKILL.md on disk)")
for mkt in sorted(glob.glob(os.path.join(mkts_root, "*"))):
    if not os.path.isdir(mkt):
        continue
    mname = os.path.basename(mkt)
    catalog = by_key(jdict(read_json(os.path.join(mkt, ".claude-plugin", "marketplace.json"), {})).get("plugins"), "name")

    def _plugin_of(rel_parts):
        if len(rel_parts) > 2 and rel_parts[0] in ("plugins", "external_plugins"):
            return rel_parts[1], os.path.join(mkt, rel_parts[0], rel_parts[1])
        return rel_parts[0], mkt

    for p in walk_files(mkt, filename="SKILL.md"):
        rel = norm(os.path.relpath(p, mkt)).split("/")
        pname, pdir = _plugin_of(rel)
        pj = jdict(read_json(os.path.join(pdir, ".claude-plugin", "plugin.json"), {}))
        pdisp = pj.get("name") if isinstance(pj.get("name"), str) and pj.get("name") else pname
        key = f"{pdisp}@{mname}"
        en = bool(enabled_plugins.get(key, False))
        cat = catalog.get(pdisp, {})
        e = make_entry(p, "marketplace-clone", plugin=pdisp, marketplace=mname, installed=True, enabled=en,
                       root_label="marketplace-clone", installed_record=key in INSTALLED_HERE,
                       catalog_category=cat.get("category"), catalog_source=src_kind(cat.get("source")),
                       notes=("catalog copy; Claude Code loads the plugin from plugins/cache, never from here"
                              if key in INSTALLED_HERE else
                              "catalog copy; install with `claude plugin install <plugin>@<marketplace>` (copies into plugins/cache and sets enabledPlugins)"))
        e["skill_tool_name"] = None          # a marketplace clone is not a load path (same rule as skill_ara.py)
    for c in walk_files(mkt, pattern=r"\.md$"):
        if os.path.basename(os.path.dirname(c)) != "commands":
            continue
        rel = norm(os.path.relpath(c, mkt)).split("/")
        pname, _ = _plugin_of(rel)
        key = f"{pname}@{mname}"
        en = bool(enabled_plugins.get(key, False))
        e = make_entry(c, "marketplace-clone", entry_type="command", plugin=pname, marketplace=mname,
                       installed=True, enabled=en, root_label="marketplace-clone")
        e["skill_tool_name"] = None          # not a load path
    # catalog entries whose content is NOT on disk (remote sources)
    local_plugins = {os.path.basename(d) for sub in ("plugins", "external_plugins")
                     for d in glob.glob(os.path.join(mkt, sub, "*")) if os.path.isdir(d)}
    for pname, cat in catalog.items():
        if pname in local_plugins:
            continue
        for sk in jlist(cat.get("skills")):
            if not isinstance(sk, str):
                continue
            entries.append({
                "name": os.path.basename(sk.rstrip("/")), "description": cat.get("description", ""),
                "path": None, "source_kind": "marketplace-clone", "plugin": pname, "marketplace": mname,
                "installed": False, "enabled": False, "has_scripts": None, "has_references": None,
                "entry_type": "skill", "root_label": "marketplace-catalog-remote",
                "skill_tool_name": None, "disable_model_invocation": None, "frontmatter_keys": [],
                "has_assets": None, "has_agents": None, "frontmatter_error": None,
                "catalog_category": cat.get("category"),
                "catalog_source": src_kind(cat.get("source")),
                "notes": "declared in marketplace.json 'skills' but the plugin source is remote; not on disk until installed",
            })

# ----------------------------------------------------------------------------- 5. desktop-bundled (anthropic-skills)
bundle_glob = os.path.join(LAMS, "skills-plugin", "*", "*")
bundles = [d for d in glob.glob(bundle_glob) if os.path.isdir(d)]
add_root("desktop-bundled", bundle_glob, bool(bundles),
         "<desktop data dir>/local-agent-mode-sessions/skills-plugin/<orgId>/<accountId>/{.claude-plugin/plugin.json, manifest.json, skills/*/SKILL.md}")
for b in bundles:
    pj = jdict(read_json(os.path.join(b, ".claude-plugin", "plugin.json"), {}))
    man_by = by_key(jdict(read_json(os.path.join(b, "manifest.json"), {})).get("skills"), "name")
    pname = pj.get("name") if isinstance(pj.get("name"), str) and pj.get("name") else "anthropic-skills"
    for p in walk_files(os.path.join(b, "skills"), filename="SKILL.md"):
        ms = man_by.get(os.path.basename(os.path.dirname(p)), {})
        en = ms.get("enabled")
        e = make_entry(p, "desktop-bundled", plugin=pname, marketplace=None, installed=True,
                       enabled=(bool(en) if en is not None else None), root_label="desktop-bundled",
                       plugin_version=pj.get("version"), manifest_source=ms.get("source"),
                       manifest_creator=ms.get("creatorType"), manifest_updated=ms.get("updatedAt"),
                       bundle_dir=norm(b))
        set_tool_name(e, pname)
        if e["disable_model_invocation"]:
            e["notes"] = "disable-model-invocation: true -> hidden from the Skill tool listing; user-only (/slash) invocation"

# ----------------------------------------------------------------------------- 6. claude.ai plugins materialised by the desktop app (rpm)
rpm_glob = os.path.join(DESKTOP_DATA, "rpm", "*", "*") + " ; " + os.path.join(LAMS, "*", "*", "rpm")
rpms = rpm_dirs(DESKTOP_DATA)
add_root("claudeai-plugin", rpm_glob, bool(rpms),
         "<desktop data dir>/rpm/<acct8>/<org8>/ (observed 2026-10-22; first 8 hex digits of accountId / orgId) and "
         "<desktop data dir>/local-agent-mode-sessions/<accountId>/<orgId>/rpm/, both read, each {manifest.json, "
         "plugin_<id>/...} ; persistent per account+org, refreshed by the app (NOT per-session)")
for r in rpms:
    man_by = by_key(jdict(read_json(os.path.join(r, "manifest.json"), {})).get("plugins"), "id")
    for pd in sorted(glob.glob(os.path.join(r, "plugin_*"))):
        if not os.path.isdir(pd):
            continue
        pid = os.path.basename(pd)
        pj = jdict(read_json(os.path.join(pd, ".claude-plugin", "plugin.json"), {}))
        mp = man_by.get(pid, {})
        pname = next((x for x in (pj.get("name"), mp.get("name")) if isinstance(x, str) and x), pid)
        mkt = mp.get("marketplaceName")
        avail = (mp.get("installationPreference") == "available") if mp else None
        spaths = plugin_skill_paths(pd, pj)
        for p in walk_files(pd, filename="SKILL.md"):
            slot = plugin_skill_slot(p, spaths)
            in_sd = bool(slot)
            if avail is None:
                en = None if in_sd else False
            else:
                en = bool(avail) and in_sd
            e = make_entry(p, "claudeai-plugin", plugin=pname, marketplace=mkt, installed=True, enabled=en,
                           root_label="claudeai-plugin-rpm", plugin_id=pid, plugin_version=pj.get("version"),
                           marketplace_display=mp.get("displayName"), marketplace_id=mp.get("marketplaceId"),
                           installed_by=mp.get("installedBy"), installation_preference=mp.get("installationPreference"),
                           notes=None if in_sd else
                           "outside the plugin's skill path(s) %s, or nested -> NOT listed in the Skill tool"
                           % [_rel(x, pd) for x in spaths])
            set_tool_name(e, pname, slot)
        for c in plugin_commands(pd):
            e = make_entry(c, "claudeai-plugin", entry_type="command", plugin=pname, marketplace=mkt, installed=True,
                           enabled=(bool(avail) if avail is not None else None),
                           root_label="claudeai-plugin-rpm", plugin_id=pid, plugin_version=pj.get("version"),
                           marketplace_display=mp.get("displayName"),
                           notes="commands/<name>.md is listed in the Skill tool as <plugin>:<name>; when a skill has the same name the command's description is what the listing shows")
            set_tool_name(e, pname)

# ----------------------------------------------------------------------------- summary
def _pyyaml_available():
    try:
        import yaml  # noqa: F401
        return True
    except Exception:
        return False

def count_by(key):
    c = {}
    for e in entries:
        k = e.get(key)
        k = "null" if k is None else str(k)
        c[k] = c.get(k, 0) + 1
    return dict(sorted(c.items()))

summary = {
    "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "python": sys.version.split()[0],
    "pyyaml_available": _pyyaml_available(),
    "total_entries": len(entries),
    "by_source_kind": count_by("source_kind"),
    "by_root_label": count_by("root_label"),
    "by_entry_type": count_by("entry_type"),
    "by_source_kind_and_enabled": {},
    "skills_only_by_source_kind": {},
    "frontmatter_errors": [e["path"] for e in entries if e.get("frontmatter_error")],
    "disable_model_invocation_true": [e["path"] for e in entries if e.get("disable_model_invocation")],
    "expected_skill_tool_names": sorted({e["skill_tool_name"] for e in entries if e.get("skill_tool_name")}),
    "config_sources": {
        "settings_json": norm(os.path.join(CLAUDE_HOME, "settings.json")),
        "settings_files_merged": [norm(f) for f in SETTINGS_FILES if os.path.isfile(f)],
        "skillOverrides": skill_overrides,
        "enabledPlugins": enabled_plugins,
        "installed_plugins_json": norm(os.path.join(PLUGINS, "installed_plugins.json")),
        "installed_plugin_keys": sorted(installed_plugins.keys()),
        "known_marketplaces": {k: (v.get("installLocation") if isinstance(v, dict) else None) for k, v in known_marketplaces.items()},
    },
    "roots": roots_meta,
}
for e in entries:
    k = f"{e['source_kind']}|enabled={e['enabled']}"
    summary["by_source_kind_and_enabled"][k] = summary["by_source_kind_and_enabled"].get(k, 0) + 1
    if e["entry_type"] == "skill":
        summary["skills_only_by_source_kind"][e["source_kind"]] = summary["skills_only_by_source_kind"].get(e["source_kind"], 0) + 1
summary["by_source_kind_and_enabled"] = dict(sorted(summary["by_source_kind_and_enabled"].items()))
summary["skills_only_by_source_kind"] = dict(sorted(summary["skills_only_by_source_kind"].items()))

# Both files go through write_private(): a private --out dir (0700 on macOS/Linux), a unique temp name, os.replace.
# A refused or unwritable --out is reported and skipped; the summary below is printed either way.
for path, data in ((OUT_LIST, entries), (OUT_SUMMARY, summary)):
    # errors="replace": a lone surrogate (a "\ud800" escape in a JSON file, an undecodable POSIX file name) -> "?"
    why = write_private(path, json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8", "replace"))
    if why:
        print("not: %s yazilmadi (%s: %s)" % (os.path.basename(path), norm(OUT_DIR), why))
    elif path == OUT_LIST:
        print(f"wrote {OUT_LIST}  ({len(entries)} entries)")
    else:
        print(f"wrote {OUT_SUMMARY}")
print("\n== entries per source_kind (skills + commands) ==")
for k, v in summary["by_source_kind"].items():
    print(f"  {k:20s} {v}")
print("\n== SKILL.md only, per source_kind ==")
for k, v in summary["skills_only_by_source_kind"].items():
    print(f"  {k:20s} {v}")
print("\n== per source_kind x enabled ==")
for k, v in summary["by_source_kind_and_enabled"].items():
    print(f"  {k:40s} {v}")
print("\n== per root_label ==")
for k, v in summary["by_root_label"].items():
    print(f"  {k:45s} {v}")
print(f"\nfrontmatter errors: {len(summary['frontmatter_errors'])}")
for p in summary["frontmatter_errors"][:20]:
    print("   ", p)
print(f"disable-model-invocation=true: {len(summary['disable_model_invocation_true'])}")
print(f"expected Skill-tool names: {len(summary['expected_skill_tool_names'])}")
