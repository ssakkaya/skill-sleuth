"""Shared helpers of the offline test suite (standard library only, Python 3.9+).

Run from the repository root (CI does exactly this on Windows, macOS and Linux):

    PYTHONUTF8=1 python -m unittest discover -s tests -v

Scripts under test: plugins/skill-sleuth/skills/skill-sleuth/scripts/ (the generated copy that ships). To test
another copy, e.g. a source edition before tools/build_yayin.py has regenerated the plugins, set SKILL_SCRIPTS_DIR:

    SKILL_SCRIPTS_DIR=<source-root>/skill-sleuth/scripts python -m unittest discover -s tests -v

Isolation: every script run happens in a throw-away tree made by tempfile.mkdtemp(). HOME and USERPROFILE,
CLAUDE_CONFIG_DIR, CLAUDE_DESKTOP_DATA_DIR, XDG_CACHE_HOME, XDG_CONFIG_HOME, APPDATA, LOCALAPPDATA and
TMPDIR / TEMP / TMP all point into it, and CLAUDE_CODE_PLUGIN_CACHE_DIR, SKILL_ARA_CACHE and DIS_KAYNAK_CACHE_DIR
are removed, so the real home folder, the real Claude config, the real desktop app data and the real cache are
never read or written. Nothing touches the network:
dis_kaynak_ara.py runs with DIS_KAYNAK_TEST_OFFLINE=1 (the scripted-HTTP tests replace
urllib's opener in the child process instead). Nothing is written inside the repository
(sys.dont_write_bytecode for the modules these tests import; PYTHONDONTWRITEBYTECODE=1 for the child processes).
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
from pathlib import Path

sys.dont_write_bytecode = True   # importing tools/ or scripts/ must never leave a __pycache__ inside the repository

REPO = Path(__file__).resolve().parent.parent
EDITIONS = ("skill-sleuth", "skill-bulucu")
PLUGIN_SCRIPTS = dict((name, REPO / "plugins" / name / "skills" / name / "scripts") for name in EDITIONS)
SCRIPTS = Path(os.environ.get("SKILL_SCRIPTS_DIR") or PLUGIN_SCRIPTS["skill-sleuth"]).resolve()
SKILL_FOLDER = SCRIPTS.parent           # the skill folder: read-only for every script
SCRIPT_NAMES = ("skill_ara.py", "dis_kaynak_ara.py", "katalog_indeksle.py", "skill_envanteri.py")
POSIX = os.name != "nt"

# The trust lines of the two third-party registries (exact script tokens; shared decision D1).
T5_TRUST = "UCUNCU TARAF - Anthropic incelemedi"
T4_TRUST = "TOPLULUK KATALOGU - Anthropic taradi ve onayladi; kodu garanti etmez"
OFFLINE_LINE = "ag yok / kaynak ulasilamadi: katmani atla"

# Variables that point a script at a real location; every run removes or replaces them.
_SCRUBBED = ("CLAUDE_CONFIG_DIR", "CLAUDE_CODE_PLUGIN_CACHE_DIR", "CLAUDE_DESKTOP_DATA_DIR", "SKILL_ARA_CACHE",
             "DIS_KAYNAK_CACHE_DIR", "DIS_KAYNAK_TEST_OFFLINE", "XDG_CACHE_HOME", "XDG_CONFIG_HOME", "APPDATA",
             "LOCALAPPDATA", "HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP")


def script_version(script):
    """VERSION = "x.y.z" of one script under test, read from its source (no import)."""
    m = re.search(r'^VERSION = "([^"]+)"', (SCRIPTS / script).read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def zw(n):
    """n zero-width spaces, built at run time so that the test files stay free of invisible characters."""
    return chr(0x200B) * n


def write_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def write_json(path, data):
    return write_bytes(path, json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def write_skill(parent, folder, name=None, description="", extra="", body="Body text.\n"):
    """<parent>/<folder>/SKILL.md with a plain frontmatter (LF line ends). -> the skill folder."""
    text = "---\nname: %s\ndescription: %s\n%s---\n\n%s" % (folder if name is None else name, description, extra, body)
    write_bytes(Path(parent) / folder / "SKILL.md", text)
    return Path(parent) / folder


def make_private(path):
    """POSIX: mode 0700 for a directory we created as a cache (the scripts refuse group/world-writable ones)."""
    if POSIX:
        os.chmod(str(path), 0o700)
    return path


def remove_tree(path):
    """rmtree that also works after a test changed modes (read-only files on Windows, 0o000 dirs on POSIX)."""
    path = str(path)
    if not os.path.lexists(path):
        return
    for dp, dns, fns in os.walk(path):
        for n in dns + fns:
            p = os.path.join(dp, n)
            try:
                if not os.path.islink(p):
                    os.chmod(p, stat.S_IRWXU)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


def tier_counts(stats_text):
    """skill_ara.py --stats -> {tier: count} from its '  <tier>   <n>' lines."""
    out = {}
    for line in stats_text.splitlines():
        m = re.match(r"^  ([a-z][a-z-]*)\s+(\d+)$", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def invisible_chars(text):
    """Characters of a Unicode C* category in text, newline excepted (what a script must never print)."""
    return [c for c in text if c != "\n" and unicodedata.category(c)[0] == "C"]


def make_dir_link(target, link, allow_junction=True):
    """A directory symlink link -> target; on Windows without the symlink privilege a junction instead (when
    allow_junction). Skips the calling test when neither can be made here. -> "symlink" | "junction"."""
    target, link = str(target), str(link)
    Path(link).parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError, AttributeError) as exc:
        err = exc
    if os.name == "nt" and allow_junction:
        try:
            import _winapi
            _winapi.CreateJunction(target, link)
            return "junction"
        except Exception as exc:     # noqa: BLE001 - any failure means: no link on this machine
            err = exc
    raise unittest.SkipTest("cannot create a directory link here (%s)" % err)


def make_junction(testcase, target, link):
    """Windows only: a directory junction link -> target (no privilege needed), removed again before the sandbox
    is (os.walk follows junctions; register the sandbox cleanup first). Skips the test on other systems."""
    if os.name != "nt":
        raise unittest.SkipTest("junctions are a Windows feature")
    import _winapi
    Path(link).parent.mkdir(parents=True, exist_ok=True)
    _winapi.CreateJunction(str(target), str(link))
    testcase.addCleanup(os.rmdir, str(link))      # removes the junction itself, never its target


# Runs a script as on Python < 3.12, where os.path.isjunction does not exist: argv = [script, args...].
WITHOUT_ISJUNCTION = r'''
import os, runpy, sys
if hasattr(os.path, "isjunction"):
    del os.path.isjunction
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name="__main__")
'''


def lone_surrogate_json():
    """A JSON string literal holding a lone surrogate escape ("x\\ud800y"), built at run time (no such text here)."""
    return '"x' + chr(92) + 'ud800y"'


def make_file_symlink(target, link):
    try:
        os.symlink(str(target), str(link))
    except (OSError, NotImplementedError, AttributeError) as exc:
        raise unittest.SkipTest("cannot create a file symlink here (%s)" % exc)


def helper_sources(script):
    """{function name: source text} of the top-level functions of one script (ast, no import)."""
    text = (SCRIPTS / script).read_text(encoding="utf-8")
    tree = ast.parse(text)
    return dict((n.name, ast.get_source_segment(text, n)) for n in tree.body if isinstance(n, ast.FunctionDef))


class Result(object):
    """Outcome of one script run: exit code, raw stdout / stderr bytes and decoded text."""

    def __init__(self, cmd, code, out, err):
        self.cmd, self.code, self.out, self.err = cmd, code, out, err
        self.text = self.out.decode("utf-8", "replace")
        self.errtext = self.err.decode("utf-8", "replace")
        self.lines = self.text.splitlines()

    def describe(self):
        return "command: %s\nexit: %s\n--- stdout ---\n%s\n--- stderr ---\n%s" % (
            " ".join(self.cmd[1:]), self.code, self.text[-3000:], self.errtext[-3000:])


class Sandbox(object):
    """A synthetic machine in a temporary folder: home, Claude config, desktop data, caches, temp."""

    def __init__(self, prefix="sleuth-"):
        self.root = Path(os.path.realpath(tempfile.mkdtemp(prefix=prefix)))
        self.home = self.mk("home")
        self.config = self.home / ".claude"          # = the default <config> (~/.claude) of this machine
        self.desktop = self.mk("desktop")
        self.xdg_cache = self.mk("xdg-cache")
        self.xdg_config = self.mk("xdg-config")
        self.appdata = self.mk("appdata")
        self.localappdata = self.mk("localappdata")    # %LOCALAPPDATA%: Claude-Data/<id>, Packages/Claude_<suffix>
        self.tmp = self.mk("tmp")
        self.work = self.mk("home", "work")          # default cwd: below home, so the project walk stops at home
        self.cache = self.root / "cache" / "skill_ara_cache.json"

    # -- layout ------------------------------------------------------------------------------------------------
    def mk(self, *parts):
        p = self.root.joinpath(*parts)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def path(self, *parts):
        return self.root.joinpath(*parts)

    @property
    def user_skills(self):
        return self.config / "skills"

    @property
    def plugins(self):
        return self.config / "plugins"

    def close(self):
        remove_tree(self.root)

    # -- running -----------------------------------------------------------------------------------------------
    def env(self, **over):
        """Environment of a child process: the real one minus every location variable, plus this sandbox.
        over: NAME=value to set, NAME=None to leave unset."""
        e = dict((k, v) for k, v in os.environ.items() if k.upper() not in _SCRUBBED)
        e.update({
            "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
            "HOME": str(self.home), "USERPROFILE": str(self.home),
            "CLAUDE_CONFIG_DIR": str(self.config), "CLAUDE_DESKTOP_DATA_DIR": str(self.desktop),
            "XDG_CACHE_HOME": str(self.xdg_cache), "XDG_CONFIG_HOME": str(self.xdg_config),
            "APPDATA": str(self.appdata), "LOCALAPPDATA": str(self.localappdata),
            "TMPDIR": str(self.tmp), "TEMP": str(self.tmp), "TMP": str(self.tmp),
            "DIS_KAYNAK_TEST_OFFLINE": "1",
        })
        for k, v in over.items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = str(v)
        return e

    def command(self, script, args):
        return [sys.executable, str(SCRIPTS / script)] + [str(a) for a in args]

    def run(self, script, *args, **kw):
        """Run one script under test to completion. kw: env (dict), cwd, timeout (s)."""
        return self._run(self.command(script, args), kw)

    def run_code(self, code, *args, **kw):
        """python -c <code> <args...> with the sandbox environment (for a run with one function replaced)."""
        return self._run([sys.executable, "-c", code] + [str(a) for a in args], kw)

    def _run(self, cmd, kw):
        proc = subprocess.run(cmd, cwd=str(kw.get("cwd") or self.work), env=kw.get("env") or self.env(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=kw.get("timeout", 180))
        return Result(cmd, proc.returncode, proc.stdout, proc.stderr)

    def start(self, script, *args, **kw):
        """Start one script without waiting (parallel runs); finish() collects it."""
        cmd = self.command(script, args)
        proc = subprocess.Popen(cmd, cwd=str(kw.get("cwd") or self.work), env=kw.get("env") or self.env(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return cmd, proc

    @staticmethod
    def finish(started, timeout=180):
        cmd, proc = started
        out, err = proc.communicate(timeout=timeout)
        return Result(cmd, proc.returncode, out, err)

    def skill_ara(self, *args, **kw):
        """skill_ara.py with this sandbox's cache file unless the caller passes --cache itself."""
        if "--cache" not in args:
            args = args + ("--cache", str(self.cache))
        return self.run("skill_ara.py", *args, **kw)


class ScriptTestCase(unittest.TestCase):
    maxDiff = None

    def assertRan(self, r, code=0):
        """No traceback on stderr, and the expected exit code."""
        self.assertNotIn("Traceback (most recent call last)", r.errtext, r.describe())
        self.assertEqual(r.code, code, r.describe())

    def assertNoInvisible(self, r):
        self.assertEqual(invisible_chars(r.text), [], r.describe())


def iso_days_ago(days):
    """ISO-8601 UTC timestamp 'days' days before now, the way GitHub writes it."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400))


def community_fixture(cache_dir, plugins, meta):
    """dis_kaynak_ara.py cache files for an offline run: the community catalog (fresh, so it is not downloaded)
    and the GitHub repository metadata cache. meta: {"owner/repo": {"stars": n, ...}} -> fresh entries."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    make_private(cache_dir)
    write_json(cache_dir / "community-marketplace.json", {"name": "claude-community", "plugins": plugins})
    now = int(time.time())
    rows = {}
    for key, m in meta.items():
        row = {"stars": None, "forks": 0, "created_at": iso_days_ago(400), "pushed_at": iso_days_ago(10),
               "archived": False, "license": "MIT", "ts": now}
        row.update(m)
        rows[key.lower()] = row
    write_json(cache_dir / "dis_kaynak_github.json",
               {"repos": {}, "meta": rows, "first": {}, "heads": {}, "paths": {}})
    if POSIX:
        for p in cache_dir.iterdir():
            os.chmod(str(p), 0o600)
    return cache_dir


def official_catalog(sb):
    """plugin-catalog-cache.json with three walrus plugins of the official marketplace."""
    def rec(name, extra):
        r = {"marketplace_entry": {"name": name, "description": "Walrus tool for photos.",
                                   "source": {"source": "url", "url": "https://github.com/acme-test/%s.git" % name}},
             "components": {}}
        r.update(extra)
        return r
    write_json(sb.plugins / "plugin-catalog-cache.json", {"version": 1, "fetchedAt": iso_days_ago(1), "catalog": {
        "plugins": {
            "walrus-tool@claude-plugins-official": rec("walrus-tool", {
                "unique_installs": 50, "last_updated": iso_days_ago(20),
                "components": {"skills": [{"name": "walrus-skill"}]}}),
            "walrus-popular@claude-plugins-official": rec("walrus-popular", {
                "unique_installs": 50000, "last_updated": iso_days_ago(400)}),
            "walrus-nocount@claude-plugins-official": rec("walrus-nocount", {"last_updated": iso_days_ago(30)}),
        }}})


# A run in which skills.sh "answers" without the network: the search function is replaced inside a child
# process, the rest of the script is unchanged (and every host still reports itself down).
FAKE_SKILLS_SH = r'''
import importlib.util, sys
spec = importlib.util.spec_from_file_location("dk_under_test", sys.argv[1])
dk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dk)
rows = [{"id": "acme-test/zebra-kit/zebra-skill", "source": "acme-test/zebra-kit", "skillId": "zebra-skill",
         "name": "zebra-skill", "installs": 5000}] if sys.argv[2] == "hit" else []
dk.skills_sh_search = lambda net, q, limit, qtokens: (
    [h for h in (dk.norm_skill(r, i) for i, r in enumerate(rows)) if h], "keyword", 0)
sys.exit(dk.main(sys.argv[3:]))
'''
