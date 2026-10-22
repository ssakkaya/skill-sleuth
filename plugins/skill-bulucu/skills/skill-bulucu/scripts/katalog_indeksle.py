#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
katalog_indeksle.py - Offline Claude Code plugin/skill catalog indexer.

Reads (all read-only; <plugins_dir> defaults to $CLAUDE_CODE_PLUGIN_CACHE_DIR, else <config>/plugins, where
<config> = $CLAUDE_CONFIG_DIR, else ~/.claude on every OS - the same rule as skill_ara.py and skill_envanteri.py;
nothing is hard-coded):
  <plugins_dir>/plugin-catalog-cache.json                      (official catalog: skill NAMES only, no descriptions)
  <plugins_dir>/installed_plugins.json                         (which plugins are installed + install path + sha)
  <plugins_dir>/known_marketplaces.json                        (marketplace clone locations)
  <plugins_dir>/marketplaces/<mkt>/.claude-plugin/marketplace.json
  <plugins_dir>/marketplaces/<mkt>/{plugins,external_plugins}/*/   (SKILL.md frontmatter, plugin.json, commands/, agents/, .mcp.json, hooks/)
  <config>/settings.json < <cwd>/.claude/settings.json < <cwd>/.claude/settings.local.json (macOS / Linux: < the git
  root's settings.local.json)                                 (enabledPlugins)

Writes (only with --out / default, skipped with --no-write):
  <out_dir>/03-katalog-indeksi.json
  <out_dir>/03-katalog-ozeti.md
  default <out_dir> = cache_root(): Windows <tempdir>/skill-sleuth, macOS/Linux $XDG_CACHE_HOME/skill-sleuth or
  ~/.cache/skill-sleuth (mode 0700); never the skill folder (an --out inside it is refused, exit 2). On macOS/Linux
  an --out owned by another user or writable by group/others is not written to ("not: ... yazilmadi", exit 0).
  A record of an unexpected shape in any input file is skipped, never a traceback.

Usage:
  python katalog_indeksle.py                       # regenerate both files
  python katalog_indeksle.py --search pdf          # regenerate AND print plugins/skills matching "pdf"
  python katalog_indeksle.py --search deploy --no-write
  python katalog_indeksle.py --plugins-dir "<config>/plugins" --out "<dir>" --today 2026-10-01

Starts no other program (no git, no shell). Search is case-insensitive over: plugin id, name, displayName, description, category, keywords, tags,
skill names, skill descriptions (when the plugin is vendored in the marketplace clone), command names,
agent names, MCP server names, LSP server names, homepage / source repo URL.
"""
import argparse
import builtins
import datetime as _dt
import io
import json
import os
import re
import stat
import sys
import tempfile
import time
import unicodedata

# Windows console: force UTF-8 so em-dashes etc. in descriptions do not crash printing (a lone surrogate -> "?").
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


# ----------------------------------------------------------------------------- helpers
# Location rules. claude_config_dir() and plugins_root() are identical in skill_ara.py, skill_envanteri.py and
# katalog_indeksle.py.
def claude_config_dir():
    """Claude Code config dir on every OS: $CLAUDE_CONFIG_DIR, else ~/.claude."""
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def plugins_root():
    """Claude Code plugins root (cache/, marketplaces/, installed_plugins.json, known_marketplaces.json,
    plugin-catalog-cache.json): $CLAUDE_CODE_PLUGIN_CACHE_DIR when set (a leading ~ is expanded, as Claude Code
    does), else <config>/plugins."""
    d = (os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR") or "").strip()
    return os.path.expanduser(d) if d else os.path.join(claude_config_dir(), "plugins")


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


def jdict(x):
    """x when it is a JSON object, else {}: a file of another shape never raises."""
    return x if isinstance(x, dict) else {}


def jlist(x):
    """x when it is a JSON array, else []."""
    return x if isinstance(x, list) else []


def named(rows):
    """The objects of a JSON array that carry a string "name" (other rows are skipped)."""
    return [r for r in jlist(rows) if isinstance(r, dict) and isinstance(r.get("name"), str)]


def txt(x):
    """x when it is a string, else ""."""
    return x if isinstance(x, str) else ""


def num(v):
    """An install count: v when it is a finite JSON number (not a bool), as an int; else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        return int(v)
    except (OverflowError, ValueError):      # inf / nan
        return None


def listdir(p):
    """os.listdir(p) sorted, [] when p cannot be listed."""
    try:
        return sorted(os.listdir(p))
    except (OSError, ValueError):
        return []


def strs(x):
    """Names of a JSON array of strings / {name: ...} objects, or of an object keyed by name."""
    if isinstance(x, dict):
        return [k for k in x if isinstance(k, str)]
    return [r if isinstance(r, str) else r["name"] for r in jlist(x)
            if isinstance(r, str) or (isinstance(r, dict) and isinstance(r.get("name"), str))]


def read_json(path, default=None):
    """Parsed JSON file, else default; utf-8-sig: a file saved with a BOM is read like Claude Code reads it."""
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def parse_frontmatter(text):
    """Minimal YAML frontmatter parser (no PyYAML dependency).
    Supports `key: value`, quoted values, and block scalars (| / > / |- / >-)."""
    m = re.match(r"^\ufeff?---[ \t]*\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return {}
    fm = m.group(1).replace("\r\n", "\n")
    lines = fm.split("\n")
    out = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not km:
            i += 1
            continue
        key, val = km.group(1), km.group(2).strip()
        if val in ("|", ">", "|-", ">-", ""):
            body = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith(" ") or lines[j].startswith("\t") or lines[j].strip() == ""):
                body.append(lines[j].strip())
                j += 1
            val = " ".join(x for x in body if x).strip()
            i = j
        else:
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            i += 1
        out[key] = val
    return out


def frontmatter_names_and_bodies(skill_md_path):
    try:
        with io.open(skill_md_path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception:
        return {}, 0
    return parse_frontmatter(txt), len(txt)


def one_line(s, n):
    """Third-party text -> one table / search line: clean() (invisible characters stripped), '|' -> '/', cut to n
    chars; ' GIZLI-KARAKTER(<k>)' is added when k >= 8 invisible characters were removed (a red flag, as in skill_ara)."""
    k = hidden_count(s)
    s = clean(s.replace("|", "/") if isinstance(s, str) else s, n)
    return s + (" GIZLI-KARAKTER(%d)" % k if k >= 8 else "")


def source_repo_of(entry_source):
    """Return (source_type, repo_or_path) for a marketplace `source` field."""
    if isinstance(entry_source, str):
        return ("relative", entry_source)
    if isinstance(entry_source, dict):
        t = txt(entry_source.get("source"))
        if t == "github":
            return ("github", "https://github.com/" + txt(entry_source.get("repo")))
        if t in ("git-subdir", "url", "git"):
            u = txt(entry_source.get("url"))
            p = txt(entry_source.get("path"))
            return (t, u + ("#" + p if p else ""))
        return (t or "unknown", json.dumps(entry_source, ensure_ascii=False))
    return ("unknown", "")


# ----------------------------------------------------------------------------- clone walk
def walk_marketplace_clone(clone_dir):
    """Return {plugin_dir_name: {...}} for every plugin directory under plugins/ and external_plugins/."""
    found = {}
    for sub in ("plugins", "external_plugins"):
        base = os.path.join(clone_dir, sub)
        if not os.path.isdir(base):
            continue
        for d in listdir(base):
            pdir = os.path.join(base, d)
            if not os.path.isdir(pdir):
                continue
            rel = sub + "/" + d
            manifest = jdict(read_json(os.path.join(pdir, ".claude-plugin", "plugin.json"), {}))
            skills = []
            sdir = os.path.join(pdir, "skills")
            if os.path.isdir(sdir):
                for root, dirs, files in os.walk(sdir):
                    if "SKILL.md" in files:
                        sp = os.path.join(root, "SKILL.md")
                        fm, size = frontmatter_names_and_bodies(sp)
                        skills.append({
                            "dir_name": os.path.basename(root),
                            "name": fm.get("name") or os.path.basename(root),
                            "description": fm.get("description", ""),
                            "path_in_marketplace_clone": os.path.relpath(sp, clone_dir).replace(os.sep, "/"),
                            "skill_md_chars": size,
                            "frontmatter_keys": sorted(fm.keys()),
                        })
            commands = sorted(os.path.splitext(f)[0] for f in listdir(os.path.join(pdir, "commands")) if f.endswith(".md"))
            agents = sorted(os.path.splitext(f)[0] for f in listdir(os.path.join(pdir, "agents")) if f.endswith(".md"))
            mcp = jdict(read_json(os.path.join(pdir, ".mcp.json"), {}))
            # external plugins use top-level {server: cfg}; some use {"mcpServers": {...}}
            mcp_names = sorted(k for k in jdict(mcp.get("mcpServers") or mcp) if isinstance(k, str))
            hooks_file = os.path.join(pdir, "hooks", "hooks.json")
            hj = jdict(read_json(hooks_file, {}) if os.path.exists(hooks_file) else {})
            hooks = sorted(k for k in jdict(hj.get("hooks") or hj) if isinstance(k, str))
            found[d] = {
                "clone_path": rel,
                "vendored_dir": sub,                     # "plugins" (Anthropic-internal) or "external_plugins" (partner)
                "manifest": manifest,
                "skills": skills,
                "commands": commands,
                "agents": agents,
                "mcp_servers": mcp_names,
                "hooks": hooks,
            }
    return found


def _same_path(a, b):
    return os.path.normcase(os.path.normpath(os.path.abspath(a))) == os.path.normcase(os.path.normpath(os.path.abspath(b)))


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
    """Same as skill_ara.py: the main checkout's root for a git worktree root (commondir followed), else None."""
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


def record_applies(r, cwd):
    """Same as skill_ara.py (Claude Code's hx()): an install record applies in cwd when its scope is user or managed
    (or not recorded), or its projectPath is cwd or shares cwd's git root."""
    if r.get("scope") in (None, "user", "managed"):
        return True
    pp = r.get("projectPath")
    if not isinstance(pp, str) or not pp:
        return False
    if _same_path(pp, cwd):
        return True
    a, b = git_root(cwd), git_root(pp)
    return a is not None and b is not None and _same_path(main_checkout(a) or a, main_checkout(b) or b)


def local_settings_root(cwd):
    """Same rule as skill_ara.py: macOS / Linux, the canonical git root's .claude/settings.local.json (root, .git and
    .claude owned by the current user; not cwd itself, not the home directory), which Claude Code reads on top of
    the cwd's, else None."""
    if os.name == "nt" or not hasattr(os, "geteuid"):
        return None
    root = git_root(cwd)
    if root is None:
        return None
    root = main_checkout(root) or root
    if _same_path(root, cwd) or _same_path(os.path.realpath(root), os.path.realpath(os.path.expanduser("~"))):
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


# ----------------------------------------------------------------------------- build index
def build_index(plugins_dir, settings_path, today):
    cache_path = os.path.join(plugins_dir, "plugin-catalog-cache.json")
    cache = jdict(read_json(cache_path, {}))
    catalog = jdict(cache.get("catalog"))
    cplugins = dict((k, v) for k, v in jdict(catalog.get("plugins")).items() if isinstance(k, str) and isinstance(v, dict))

    installed = jdict(jdict(read_json(os.path.join(plugins_dir, "installed_plugins.json"), {})).get("plugins"))
    known = jdict(read_json(os.path.join(plugins_dir, "known_marketplaces.json"), {}))
    # enabledPlugins as Claude Code sees it in the current directory (same rule as skill_ara.py merged_setting()):
    # --settings (user) < <cwd>/.claude/settings.json < <cwd>/.claude/settings.local.json, a later file winning
    enabled = {}
    for f in (settings_path, os.path.join(os.getcwd(), ".claude", "settings.json"),
              os.path.join(os.getcwd(), ".claude", "settings.local.json"), local_settings_root(os.getcwd())):
        if not f:
            continue
        enabled.update(jdict(jdict(read_json(f, {})).get("enabledPlugins")))

    marketplaces = {}
    for mname, minfo in known.items():
        if not isinstance(minfo, dict):
            continue
        loc = minfo.get("installLocation") if isinstance(minfo.get("installLocation"), str) else ""
        loc = loc or os.path.join(plugins_dir, "marketplaces", mname)
        mjson = jdict(read_json(os.path.join(loc, ".claude-plugin", "marketplace.json"), {}))
        marketplaces[mname] = {
            "install_location": loc,
            "last_updated": minfo.get("lastUpdated"),
            "source": minfo.get("source"),
            "marketplace_json_name": mjson.get("name"),
            "renames": jdict(mjson.get("renames")),
            "entries": {e["name"]: e for e in named(mjson.get("plugins"))},
            "clone": walk_marketplace_clone(loc),
        }

    index = []
    all_ids = set(cplugins.keys())
    # plugins listed in marketplace.json but absent from cache (e.g. renamed) are added too
    for mname, m in marketplaces.items():
        for n in m["entries"]:
            all_ids.add(n + "@" + mname)

    for pid in sorted(all_ids):
        name, _, mname = pid.partition("@")
        cp = cplugins.get(pid, {})
        m = marketplaces.get(mname, {})
        entry = (m.get("entries") or {}).get(name) or jdict(cp.get("marketplace_entry"))
        # renames: old-name -> new-name
        renamed_to = (m.get("renames") or {}).get(name)
        src_type, src_repo = source_repo_of(entry.get("source"))
        clone_rec = None
        if src_type == "relative":
            clone_rec = (m.get("clone") or {}).get(os.path.basename(entry["source"].rstrip("/")))
        comps = jdict(cp.get("components"))
        clone_skills_by_name = {}
        if clone_rec:
            for s in clone_rec["skills"]:
                clone_skills_by_name[s["name"]] = s
                clone_skills_by_name[s["dir_name"]] = s
        skills = []
        seen = set()
        for s in named(comps.get("skills")):
            cs = clone_skills_by_name.get(s["name"])
            skills.append({
                "name": s["name"],
                "description": cs["description"] if cs else None,
                "path_in_marketplace_clone": cs["path_in_marketplace_clone"] if cs else None,
                "chars_always_on": jdict(s.get("chars")).get("always_on"),
                "chars_on_invoke": jdict(s.get("chars")).get("on_invoke"),
                "description_source": "marketplace-clone SKILL.md" if cs else None,
            })
            seen.add(s["name"])
        if clone_rec:  # skills present in clone but missing from cache
            for s in clone_rec["skills"]:
                if s["name"] not in seen and s["dir_name"] not in seen:
                    skills.append({
                        "name": s["name"], "description": s["description"],
                        "path_in_marketplace_clone": s["path_in_marketplace_clone"],
                        "chars_always_on": None, "chars_on_invoke": s["skill_md_chars"],
                        "description_source": "marketplace-clone SKILL.md (not in cache)",
                    })
        inst = installed.get(pid) or []
        rec = {
            "id": pid,
            "name": name,
            "display_name": txt(entry.get("displayName")) or None,
            "renamed_to": renamed_to,
            "description": txt(entry.get("description")),
            "category": txt(entry.get("category")) or None,
            "version": cp.get("version") or entry.get("version") or (clone_rec or {}).get("manifest", {}).get("version"),
            "unique_installs": num(cp.get("unique_installs")),
            "last_updated": cp.get("last_updated"),
            "installed": any(record_applies(r, os.getcwd()) for r in (inst if isinstance(inst, list) else [inst])
                             if isinstance(r, dict)),   # only a record that applies here (Claude Code's hx())
            "install_records": inst,
            "enabled": bool(enabled.get(pid, False)),
            "in_catalog_cache": pid in cplugins,
            "in_marketplace_clone": clone_rec is not None,
            "vendored_dir": (clone_rec or {}).get("vendored_dir"),
            "clone_path": (clone_rec or {}).get("clone_path"),
            "source_type": src_type,
            "source_repo": src_repo,
            "source_sha_cache": jdict(jdict(cp.get("marketplace_entry")).get("source")).get("sha"),
            "source_sha_clone": (entry.get("source") or {}).get("sha") if isinstance(entry.get("source"), dict) else None,
            "author": entry.get("author") or (clone_rec or {}).get("manifest", {}).get("author"),
            "homepage": txt(entry.get("homepage")) or None,
            "keywords": strs(entry.get("keywords")) or strs((clone_rec or {}).get("manifest", {}).get("keywords")),
            "tags": strs(entry.get("tags")),
            "strict": entry.get("strict"),
            "marketplace_declared_skills": entry.get("skills"),
            "skills": skills,
            "commands": [c["name"] for c in named(comps.get("commands"))] or (clone_rec or {}).get("commands", []),
            "agents": [a["name"] for a in named(comps.get("agents"))] or (clone_rec or {}).get("agents", []),
            "hooks": strs(comps.get("hooks")) or (clone_rec or {}).get("hooks", []),
            "mcp_servers": strs(comps.get("mcpServers")) or (clone_rec or {}).get("mcp_servers", []),
            "lsp_servers": strs(comps.get("lspServers")),
            "tokens": cp.get("tokens"),
        }
        index.append(rec)

    # clone directories that are not published in marketplace.json (e.g. example-plugin)
    clone_only = []
    for mname, m in marketplaces.items():
        published = {os.path.basename(e["source"].rstrip("/")) for e in m["entries"].values() if isinstance(e.get("source"), str)}
        for d, rec in m["clone"].items():
            if d not in published:
                clone_only.append({"marketplace": mname, "dir": rec["clone_path"],
                                   "manifest_name": txt(rec["manifest"].get("name")) or None,
                                   "description": txt(rec["manifest"].get("description")) or None,
                                   "skills": [{"name": s["name"], "description": s["description"],
                                               "path_in_marketplace_clone": s["path_in_marketplace_clone"]} for s in rec["skills"]]})

    fetched = cache.get("fetchedAt")
    stale_days = None
    if fetched:
        try:
            fd = _dt.datetime.strptime(fetched[:10], "%Y-%m-%d").date()
            stale_days = (today - fd).days
        except Exception:
            pass

    total_cache_skills = sum(len(named(jdict(p.get("components")).get("skills"))) for p in cplugins.values())
    total_clone_skills = sum(len(r["skills"]) for m in marketplaces.values() for r in m["clone"].values())
    meta = {
        "generated_by": "katalog_indeksle.py",
        "generated_on": today.isoformat(),
        "plugins_dir": plugins_dir,
        "settings_path": settings_path,
        "cache": {
            "path": cache_path,
            "version": cache.get("version"),
            "fetchedAt": fetched,
            "stale_days_vs_today": stale_days,
            "catalog_generated_at": catalog.get("generated_at"),
            "installs_generated_at": catalog.get("installs_generated_at"),
            "marketplace_sha": catalog.get("marketplace_sha"),
            "models": catalog.get("models"),
            "plugin_count": len(cplugins),
            "skill_entries_total": total_cache_skills,
            "skill_descriptions_present": False,  # cache skill entries hold only {name, chars{always_on,on_invoke}}
        },
        "marketplaces": {k: {kk: vv for kk, vv in v.items() if kk not in ("entries", "clone")} | {
            "entry_count": len(v["entries"]),
            "clone_plugin_dirs": len(v["clone"]),
            "clone_skill_md_count": sum(len(r["skills"]) for r in v["clone"].values()),
        } for k, v in marketplaces.items()},
        "installed_plugin_ids": sorted(installed.keys()),
        "enabled_plugin_ids": sorted(k for k, v in enabled.items() if v),
        "totals": {
            "plugins_indexed": len(index),
            "skills_in_cache": total_cache_skills,
            "skills_with_description_from_clone": sum(1 for p in index for s in p["skills"] if s["description"]),
            "skill_md_files_in_clone": total_clone_skills,
            "plugins_in_clone": sum(1 for p in index if p["in_marketplace_clone"]),
            "plugins_external_only": sum(1 for p in index if not p["in_marketplace_clone"]),
        },
        "clone_only_plugins": clone_only,
    }
    return {"meta": meta, "plugins": index}


# ----------------------------------------------------------------------------- outputs
def write_outputs(idx, out_dir):
    """Both files go through write_private() (private dir, unique temp name, os.replace). -> (json path, md path,
    reasons of the files that were not written)."""
    jp = os.path.join(out_dir, "03-katalog-indeksi.json")
    fails = []
    # errors="replace": a lone surrogate (a "\ud800" escape in a JSON file, an undecodable POSIX file name) -> "?"
    why = write_private(jp, json.dumps(idx, ensure_ascii=False, indent=1).encode("utf-8", "replace"))
    if why:
        fails.append("not: 03-katalog-indeksi.json yazilmadi (%s: %s)" % (out_dir, why))

    meta, plugins = idx["meta"], idx["plugins"]
    L = []
    L.append("# Claude Code plugin katalog ozeti (offline)\n")
    L.append("Uretim: `katalog_indeksle.py` - %s\n" % meta["generated_on"])
    c = meta["cache"]
    L.append("## Kaynak durumu\n")
    L.append("| Alan | Deger |\n|---|---|")
    L.append("| plugin-catalog-cache.json fetchedAt | %s (bugune gore %s gun eski) |" % (c["fetchedAt"], c["stale_days_vs_today"]))
    L.append("| catalog.generated_at | %s |" % c["catalog_generated_at"])
    L.append("| catalog.installs_generated_at | %s |" % c["installs_generated_at"])
    L.append("| catalog.marketplace_sha | %s |" % c["marketplace_sha"])
    L.append("| cache plugin sayisi | %s |" % c["plugin_count"])
    L.append("| cache skill girdisi (sadece isim) | %s |" % c["skill_entries_total"])
    for mk, mv in meta["marketplaces"].items():
        L.append("| marketplace `%s` lastUpdated (known_marketplaces.json) | %s |" % (mk, mv.get("last_updated")))
        L.append("| marketplace `%s` marketplace.json girdi / clone dizin / SKILL.md | %s / %s / %s |" % (mk, mv["entry_count"], mv["clone_plugin_dirs"], mv["clone_skill_md_count"]))
    L.append("| kurulu (installed_plugins.json) | %s |" % (", ".join(meta["installed_plugin_ids"]) or "-"))
    L.append("| etkin (settings.json enabledPlugins) | %s |" % (", ".join(meta["enabled_plugin_ids"]) or "-"))
    t = meta["totals"]
    L.append("| clone'da bulunan plugin / sadece uzak repo | %s / %s |" % (t["plugins_in_clone"], t["plugins_external_only"]))
    L.append("| aciklamasi clone'dan alinabilen skill | %s / %s |" % (t["skills_with_description_from_clone"], t["skills_in_cache"]))
    L.append("")

    L.append("## Tablo 1 - En cok kurulan 60 plugin (unique_installs azalan)\n")
    L.append("| # | plugin | category | installs | kurulu/etkin | skills (names) | one-line description |")
    L.append("|---|---|---|---|---|---|---|")
    top = sorted(plugins, key=lambda p: (p["unique_installs"] or 0), reverse=True)[:60]
    for i, p in enumerate(top, 1):
        sk = ", ".join(s["name"] for s in p["skills"]) or "-"
        flag = ("INSTALLED" if p["installed"] else "") + ("/ENABLED" if p["enabled"] else "")
        L.append("| %d | %s | %s | %s | %s | %s | %s |" % (i, p["name"], p["category"] or "-", p["unique_installs"] if p["unique_installs"] is not None else "-", flag or "-", one_line(sk, 140), one_line(p["description"], 110)))
    L.append("")

    L.append("## Tablo 2 - Marketplace clone'unda bulunan TUM skill'ler (SKILL.md frontmatter)\n")
    L.append("| plugin | dizin | skill | description (120) | clone yolu |")
    L.append("|---|---|---|---|---|")
    rows = []
    for p in plugins:
        for s in p["skills"]:
            if s["path_in_marketplace_clone"]:
                rows.append((p["name"], p["vendored_dir"] or "", s["name"], one_line(s["description"] or "", 120), s["path_in_marketplace_clone"]))
    for co in meta["clone_only_plugins"]:
        for s in co["skills"]:
            rows.append((co["manifest_name"] or co["dir"], co["dir"].split("/")[0] + " (marketplace.json'da yok)", s["name"], one_line(s["description"] or "", 120), s["path_in_marketplace_clone"]))
    for r in sorted(rows):
        L.append("| %s | %s | %s | %s | `%s` |" % r)
    L.append("")
    L.append("Toplam clone SKILL.md: %d" % len(rows))
    mp = os.path.join(out_dir, "03-katalog-ozeti.md")
    why = write_private(mp, scrub("\n".join(L) + "\n").encode("utf-8", "replace"))
    if why:
        fails.append("not: 03-katalog-ozeti.md yazilmadi (%s: %s)" % (out_dir, why))
    return jp, mp, fails


# ----------------------------------------------------------------------------- search
def search(idx, term):
    q = term.lower()
    hits = []
    for p in idx["plugins"]:
        fields = {
            "id": p["id"], "name": p["name"], "display_name": p.get("display_name") or "",
            "description": p["description"], "category": p["category"] or "",
            "keywords": " ".join(p["keywords"]), "tags": " ".join(p["tags"]),
            "skills": " ".join(s["name"] for s in p["skills"]),
            "skill_descriptions": " ".join((s["description"] or "") for s in p["skills"]),
            "commands": " ".join(p["commands"]), "agents": " ".join(p["agents"]),
            "mcp_servers": " ".join(p["mcp_servers"]), "lsp_servers": " ".join(p["lsp_servers"]),
            "homepage": p.get("homepage") or "", "source_repo": p.get("source_repo") or "",
        }
        matched = [k for k, v in fields.items() if q in (v or "").lower()]
        if matched:
            hits.append((p, matched))
    hits.sort(key=lambda h: (h[0]["unique_installs"] or 0), reverse=True)
    print("SEARCH %r -> %d plugin(s)" % (term, len(hits)))
    for p, matched in hits:
        flag = ("[INSTALLED]" if p["installed"] else "") + ("[ENABLED]" if p["enabled"] else "")
        print("- %s | installs=%s | cat=%s | matched=%s %s" % (p["id"], p["unique_installs"], p["category"], ",".join(matched), flag))
        print("    desc: %s" % one_line(p["description"], 160))
        msk = [s for s in p["skills"] if q in s["name"].lower() or q in (s["description"] or "").lower()]
        for s in (msk or p["skills"])[:8]:
            print("    skill: %s%s" % (s["name"], (" - " + one_line(s["description"], 110)) if s["description"] else ""))
        if p["commands"]:
            print("    commands: %s" % ", ".join(p["commands"][:10]))
        if p["mcp_servers"]:
            print("    mcp: %s" % ", ".join(p["mcp_servers"][:10]))
        if p["installed"] and p["enabled"]:
            print("    state: kurulu ve etkin (nothing to install)")
        elif p["installed"]:
            print("    enable: claude plugin enable %s" % p["id"])
        else:
            print("    install: /plugin install %s" % p["id"])
    # clone-only
    for co in idx["meta"]["clone_only_plugins"]:
        blob = " ".join([co["dir"], co["manifest_name"] or "", co["description"] or ""] + [s["name"] + " " + (s["description"] or "") for s in co["skills"]]).lower()
        if q in blob:
            print("- (clone-only, not published) %s : %s" % (co["dir"], one_line(co["description"], 120)))
    return hits


# ----------------------------------------------------------------------------- main
def main():
    config = claude_config_dir()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plugins-dir", default=plugins_root(),
                    help="default: $CLAUDE_CODE_PLUGIN_CACHE_DIR, else <config>/plugins "
                         "(<config> = $CLAUDE_CONFIG_DIR, else ~/.claude)")
    ap.add_argument("--settings", default=os.path.join(config, "settings.json"),
                    help="default: <config>/settings.json")
    ap.add_argument("--out", default=cache_root(),
                    help="output dir for the two files (default: %s; never the skill folder)" % cache_root())
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (default: system date)")
    ap.add_argument("--search", default=None, help="case-insensitive keyword over names/descriptions/skills/keywords")
    ap.add_argument("--no-write", action="store_true", help="do not (re)write the JSON/MD outputs")
    a = ap.parse_args()
    skill_dir = os.path.normpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))).lower()
    out_abs = os.path.normpath(os.path.abspath(a.out)).lower()
    if not a.no_write and (out_abs == skill_dir or out_abs.startswith(skill_dir + os.sep)):
        print("error: --out must not point inside the skill folder (%s); use --no-write or another dir" % skill_dir, file=sys.stderr)
        sys.exit(2)
    try:
        today = _dt.date.fromisoformat(a.today) if a.today else _dt.date.today()
    except ValueError:
        ap.error("--today must be YYYY-MM-DD")          # exit 2
    idx = build_index(a.plugins_dir.replace("\\", "/"), a.settings.replace("\\", "/"), today)
    if not a.no_write:
        jp, mp, fails = write_outputs(idx, a.out)
        t = idx["meta"]["totals"]
        for line in fails:
            print(line)
        if not any("03-katalog-indeksi.json" in x for x in fails):
            print("wrote %s (%d plugins, %d cache skills, %d clone SKILL.md)" % (jp, t["plugins_indexed"], t["skills_in_cache"], t["skill_md_files_in_clone"]))
        if not any("03-katalog-ozeti.md" in x for x in fails):
            print("wrote %s" % mp)
    if a.search:
        search(idx, a.search)


if __name__ == "__main__":
    main()
