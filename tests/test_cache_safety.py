"""Cache and output locations (shared decision D3). The default folder per OS; on macOS/Linux a cache folder or
file that another user owns, that group or others can write, or that is a symlink is never used (no cache, a
'not:' line, never a crash); the six helper functions are one and the same text in all four scripts, and nothing is
ever written into a Claude config tree (claude_tree)."""
from __future__ import annotations

import os
import re
import stat
import tempfile
import time
import types
import unittest
from unittest import mock

from sleuth_testlib import (FAKE_SKILLS_SH, OFFLINE_LINE, POSIX, SCRIPT_NAMES, SCRIPTS, Sandbox, ScriptTestCase,
                            community_fixture, helper_sources, make_file_symlink, write_bytes, write_skill)

HELPERS = ("cache_root", "unsafe_stat", "private_dir", "read_private", "claude_tree", "write_private")
SHA = "0123456789abcdef0123456789abcdef01234567"


def load_helpers(names=HELPERS, os_module=os):
    """The helper functions of skill_ara.py, executed on their own (the script itself is not imported)."""
    src = helper_sources("skill_ara.py")
    ns = {"os": os_module, "stat": stat, "tempfile": tempfile, "time": time}
    for n in names:
        exec(compile(src[n], "skill_ara.py:%s" % n, "exec"), ns)
    return ns


def fake_stat(mode, uid):
    return os.stat_result((mode, 0, 0, 1, uid, 0, 0, 0, 0, 0))


def same_path(a, b):
    return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))


class SharedHelpers(unittest.TestCase):
    def test_helpers_are_identical_in_the_four_scripts(self):
        base = helper_sources(SCRIPT_NAMES[0])
        for script in SCRIPT_NAMES[1:]:
            other = helper_sources(script)
            for name in HELPERS:
                with self.subTest(script=script, function=name):
                    self.assertIn(name, other)
                    self.assertEqual(other[name], base[name])


class ClaudeTree(unittest.TestCase):
    """claude_tree(): a --cache / --out / $SKILL_ARA_CACHE pointing into a Claude config tree (~/.claude/settings.json,
    a project's .claude/, ~/.claude.json, $CLAUDE_CONFIG_DIR, $CLAUDE_CODE_PLUGIN_CACHE_DIR) is never written to."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        self.h = load_helpers()

    def test_claude_trees_are_recognised(self):
        ct = self.h["claude_tree"]
        cfg, plug = self.sb.mk("cfg"), self.sb.mk("pcache")
        env = {"HOME": str(self.sb.home), "USERPROFILE": str(self.sb.home), "CLAUDE_CONFIG_DIR": str(cfg),
               "CLAUDE_CODE_PLUGIN_CACHE_DIR": str(plug)}
        with mock.patch.dict(os.environ, env):
            for p in (self.sb.path("home", ".claude", "settings.json"), self.sb.path("x", ".Claude", "rules", "a.json"),
                      self.sb.path("y", ".claude.json"), cfg / "skill_ara_cache.json", plug / "sub" / "c.json", cfg,
                      self.sb.path("CFG", "x.json")):          # case-insensitive, as on macOS / Windows
                with self.subTest(inside=str(p)):
                    self.assertTrue(ct(str(p)))
            for p in (self.sb.path("cache", "skill_ara_cache.json"), self.sb.path("x", ".claudette", "a.json"),
                      self.sb.path("cfg-other", "a.json")):
                with self.subTest(outside=str(p)):
                    self.assertFalse(ct(str(p)))

    def test_write_private_refuses_and_creates_nothing(self):
        target = self.sb.path("w", ".claude", "x.json")
        self.assertEqual(self.h["write_private"](str(target), b"{}"), "Claude ayar agaci (.claude)")
        self.assertFalse(self.sb.path("w").exists(), "not even the parent folder is created")

    def test_a_link_into_a_claude_tree_counts(self):
        real = write_bytes(self.sb.path("home", ".claude", "settings.json"), b'{"keep": true}')
        link = self.sb.path("p", "link.json")
        link.parent.mkdir(parents=True, exist_ok=True)
        make_file_symlink(real, link)
        self.assertTrue(self.h["claude_tree"](str(link)))
        self.assertEqual(self.h["write_private"](str(link), b"{}"), "Claude ayar agaci (.claude)")
        self.assertEqual(real.read_bytes(), b'{"keep": true}')


class UnsafeStat(unittest.TestCase):
    """The ownership / mode rule itself, on synthetic stat results (runs on every OS)."""

    def setUp(self):
        self.us = load_helpers(("unsafe_stat",))["unsafe_stat"]

    def test_rule(self):
        d, f = stat.S_IFDIR, stat.S_IFREG
        cases = [((d | 0o700, 1000), True, None), ((d | 0o750, 1000), True, None),
                 ((d | 0o755, 1000), True, None),
                 ((d | 0o770, 1000), True, "grup/herkes yazabilir"), ((d | 0o702, 1000), True, "grup/herkes yazabilir"),
                 ((d | 0o1777, 1000), True, "grup/herkes yazabilir"),
                 ((d | 0o700, 0), True, "sahibi baska kullanici"), ((d | 0o1777, 0), True, "sahibi baska kullanici"),
                 ((f | 0o600, 1000), True, "beklenen tur degil"), ((d | 0o700, 1000), False, "beklenen tur degil"),
                 ((stat.S_IFLNK | 0o777, 1000), False, "beklenen tur degil"),
                 ((f | 0o600, 1000), False, None), ((f | 0o644, 1000), False, None),
                 ((f | 0o620, 1000), False, "grup/herkes yazabilir"),
                 ((f | 0o666, 1001), False, "sahibi baska kullanici")]
        with mock.patch.object(os, "getuid", return_value=1000, create=True):
            for (mode, uid), is_dir, want in cases:
                with self.subTest(mode=oct(mode), uid=uid, is_dir=is_dir):
                    self.assertEqual(self.us(fake_stat(mode, uid), is_dir), want)

    def test_no_uid_means_no_check(self):
        """Windows has no os.getuid: %TEMP% is per-user, the rule does not apply."""
        us = load_helpers(("unsafe_stat",), os_module=types.SimpleNamespace())["unsafe_stat"]
        self.assertIsNone(us(fake_stat(stat.S_IFDIR | 0o777, 0), True))


class PrivateFiles(unittest.TestCase):
    """private_dir / read_private / write_private on real files of a temporary folder."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        self.h = load_helpers()

    def test_round_trip_leaves_no_temp_file(self):
        d = self.sb.path("c", "sub")
        target = d / "x.json"
        self.assertIsNone(self.h["write_private"](str(target), b'{"a": 1}'))
        self.assertEqual(self.h["read_private"](str(target)), b'{"a": 1}')
        self.assertIsNone(self.h["write_private"](str(target), b"second"))
        self.assertEqual(target.read_bytes(), b"second")
        self.assertEqual(os.listdir(str(d)), ["x.json"])
        if POSIX:
            self.assertEqual(stat.S_IMODE(os.stat(str(d)).st_mode) & 0o077, 0)
            self.assertEqual(stat.S_IMODE(os.stat(str(target)).st_mode) & 0o077, 0)

    def test_missing_and_blocked_paths_never_raise(self):
        self.assertIsNone(self.h["read_private"](str(self.sb.path("nope.json"))))
        blocker = write_bytes(self.sb.path("blocker"), b"a file, not a folder")
        self.assertEqual(self.h["private_dir"](str(blocker)), "dizin olusturulamadi (FileExistsError)")
        why = self.h["write_private"](str(blocker / "x.json"), b"data")
        self.assertTrue(why and why.startswith("dizin "), why)
        self.assertEqual(blocker.read_bytes(), b"a file, not a folder")

    def test_cache_root_follows_the_os_rule(self):
        cr = self.h["cache_root"]
        if os.name == "nt":
            with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.sb.xdg_cache)}):
                self.assertEqual(cr(), os.path.join(tempfile.gettempdir(), "skill-sleuth"))
            return
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(self.sb.xdg_cache), "HOME": str(self.sb.home)}):
            self.assertEqual(cr(), os.path.join(str(self.sb.xdg_cache), "skill-sleuth"))
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": "relative/dir", "HOME": str(self.sb.home)}):
            self.assertEqual(cr(), os.path.join(str(self.sb.home), ".cache", "skill-sleuth"))
        env = dict((k, v) for k, v in os.environ.items() if k != "XDG_CACHE_HOME")
        env["HOME"] = str(self.sb.home)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(cr(), os.path.join(str(self.sb.home), ".cache", "skill-sleuth"))

    @unittest.skipUnless(os.name == "nt", "Windows: a target held open by another handle")
    def test_target_held_open_gives_a_reason(self):
        target = self.sb.path("held", "x.json")
        self.assertIsNone(self.h["write_private"](str(target), b"old"))
        with open(str(target), "rb"):
            why = self.h["write_private"](str(target), b"new")
        self.assertEqual(why, "yazilamadi (dosya baska bir surecte acik)")
        self.assertEqual(target.read_bytes(), b"old")
        self.assertEqual(os.listdir(str(target.parent)), ["x.json"])

    @unittest.skipUnless(POSIX, "POSIX: modes and symlinks")
    def test_posix_refusals(self):
        h = self.h
        open_dir = self.sb.mk("open-dir")
        os.chmod(str(open_dir), 0o777)
        self.assertEqual(h["private_dir"](str(open_dir)), "grup/herkes yazabilir")
        self.assertEqual(h["write_private"](str(open_dir / "x.json"), b"data"), "grup/herkes yazabilir")
        self.assertEqual(os.listdir(str(open_dir)), [])
        own = self.sb.mk("own")
        os.chmod(str(own), 0o700)
        shared_file = write_bytes(own / "shared.json", b"{}")
        os.chmod(str(shared_file), 0o666)
        self.assertIsNone(h["read_private"](str(shared_file)))
        victim = write_bytes(self.sb.path("victim.json"), b"VICTIM")
        link = own / "link.json"
        make_file_symlink(victim, link)
        self.assertIsNone(h["read_private"](str(link)), "a symlinked cache file is never read")
        self.assertIsNone(h["write_private"](str(link), b"fresh"))
        self.assertFalse(os.path.islink(str(link)), "the link itself is replaced")
        self.assertEqual(victim.read_bytes(), b"VICTIM", "the link target is never written")


class DefaultLocations(ScriptTestCase):
    """Without --cache / --cache-dir / --out and without the env overrides every script uses cache_root()."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        write_skill(self.sb.user_skills, "loc-skill", description="Locationword helper.")

    def expected_root(self, sb, xdg=True):
        if os.name == "nt":
            return sb.tmp / "skill-sleuth"
        return (sb.xdg_cache if xdg else sb.home / ".cache") / "skill-sleuth"

    def stats_cache(self, r):
        m = re.match(r"^cache: (.+) \(", r.lines[0])
        self.assertTrue(m, r.describe())
        return m.group(1)

    def test_skill_ara_default_cache(self):
        sb = self.sb
        r = sb.run("skill_ara.py", "--stats")
        self.assertRan(r)
        want = self.expected_root(sb) / "skill_ara_cache.json"
        self.assertTrue(same_path(self.stats_cache(r), want), (self.stats_cache(r), str(want)))
        self.assertTrue(want.is_file())
        if POSIX:
            self.assertEqual(stat.S_IMODE(os.stat(str(want.parent)).st_mode), 0o700)

    @unittest.skipUnless(POSIX, "XDG_CACHE_HOME is a macOS/Linux rule")
    def test_relative_or_missing_xdg_cache_home_means_home_cache(self):
        sb = self.sb
        for value in ("relative-cache", None):
            with self.subTest(XDG_CACHE_HOME=value):
                r = sb.run("skill_ara.py", "--stats", env=sb.env(XDG_CACHE_HOME=value))
                self.assertRan(r)
                want = self.expected_root(sb, xdg=False) / "skill_ara_cache.json"
                self.assertTrue(same_path(self.stats_cache(r), want), r.describe())

    def test_env_override_wins(self):
        sb = self.sb
        target = sb.path("elsewhere", "my-cache.json")
        r = sb.run("skill_ara.py", "--stats", env=sb.env(SKILL_ARA_CACHE=target))
        self.assertRan(r)
        self.assertTrue(same_path(self.stats_cache(r), target))
        self.assertTrue(target.is_file())
        self.assertFalse((self.expected_root(sb) / "skill_ara_cache.json").exists())

    def test_dis_kaynak_ara_default_cache_dir(self):
        sb = self.sb
        r = sb.run("dis_kaynak_ara.py", "--query", "pdf table")
        self.assertRan(r, 3)
        self.assertTrue(self.expected_root(sb).is_dir())
        own = sb.path("dk-env")
        r = sb.run("dis_kaynak_ara.py", "--query", "pdf table", env=sb.env(DIS_KAYNAK_CACHE_DIR=own))
        self.assertRan(r, 3)
        self.assertTrue(own.is_dir())

    def test_inventory_scripts_default_out(self):
        sb = self.sb
        r = sb.run("skill_envanteri.py")
        self.assertRan(r)
        self.assertTrue((self.expected_root(sb) / "02-skill-envanteri.json").is_file(), r.describe())
        self.assertTrue((self.expected_root(sb) / "02-skill-envanteri-ozet.json").is_file())
        r = sb.run("katalog_indeksle.py")
        self.assertRan(r)
        self.assertTrue((self.expected_root(sb) / "03-katalog-indeksi.json").is_file(), r.describe())
        self.assertTrue((self.expected_root(sb) / "03-katalog-ozeti.md").is_file())


@unittest.skipUnless(POSIX, "ownership and mode checks are a macOS/Linux rule (Windows %TEMP% is per-user)")
class PosixRefusal(ScriptTestCase):
    """End to end: the scripts keep working, without the cache, and say so."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        write_skill(self.sb.user_skills, "refuse-skill", description="Refuseword helper.")
        self.open_dir = self.sb.mk("open-dir")
        os.chmod(str(self.open_dir), 0o777)

    def test_skill_ara_world_writable_cache_dir(self):
        r = self.sb.run("skill_ara.py", "--query", "refuseword", "--cache", self.open_dir / "c.json")
        self.assertRan(r)
        self.assertIn("Skill(refuse-skill)", r.text)
        self.assertIn("not: onbellek kullanilamadi (%s: grup/herkes yazabilir); indeks bellekte kuruldu"
                      % str(self.open_dir), r.lines, r.describe())
        self.assertEqual(os.listdir(str(self.open_dir)), [])
        r = self.sb.run("skill_ara.py", "--stats", "--cache", self.open_dir / "c.json")
        self.assertIn("(not written, ", r.lines[0])

    def test_skill_ara_folder_of_another_user(self):
        tmp = "/tmp"
        if not os.path.isdir(tmp) or os.stat(tmp).st_uid == os.getuid():
            self.skipTest("needs a %s owned by another user (not running as its owner)" % tmp)
        target = os.path.join(tmp, "skill-sleuth-test-%d-%d.json" % (os.getpid(), int(time.time())))
        try:
            r = self.sb.run("skill_ara.py", "--query", "refuseword", "--cache", target)
            self.assertRan(r)
            self.assertIn("Skill(refuse-skill)", r.text)
            self.assertTrue([ln for ln in r.lines if ln.startswith("not: onbellek kullanilamadi (")
                             and "sahibi baska kullanici" in ln], r.describe())
            self.assertFalse(os.path.lexists(target), "nothing is written into a shared folder")
        finally:
            if os.path.lexists(target):
                os.remove(target)

    def test_skill_ara_symlinked_cache_file_is_not_followed(self):
        sb = self.sb
        planted = sb.path("planted", "idx.json")
        self.assertRan(sb.run("skill_ara.py", "--stats", "--cache", planted))
        r = sb.run("skill_ara.py", "--stats", "--cache", planted)
        self.assertIn("rebuilt_because=None", r.lines[0], "control: the file itself is a valid cache")
        before = planted.read_bytes()
        cdir = sb.mk("own-cache")
        os.chmod(str(cdir), 0o700)
        link = cdir / "c.json"
        make_file_symlink(planted, link)
        r = sb.run("skill_ara.py", "--stats", "--cache", link)
        self.assertRan(r)
        self.assertIn("rebuilt_because=no-cache", r.lines[0], r.describe())
        self.assertFalse(os.path.islink(str(link)))
        self.assertEqual(planted.read_bytes(), before)

    def test_skill_ara_group_writable_cache_file_is_not_read(self):
        sb = self.sb
        self.assertRan(sb.skill_ara("--stats"))
        os.chmod(str(sb.cache), 0o666)
        r = sb.skill_ara("--stats")
        self.assertRan(r)
        self.assertIn("rebuilt_because=no-cache", r.lines[0], r.describe())
        self.assertEqual(stat.S_IMODE(os.stat(str(sb.cache)).st_mode) & 0o077, 0, "rewritten privately")

    def test_dis_kaynak_ara_unsafe_cache_dir_is_not_used(self):
        sb = self.sb
        plugins = [{"name": "zebra-widget", "description": "Zebra widget helper.",
                    "source": {"source": "url", "url": "https://github.com/acme-test/zebra-widget.git", "sha": SHA}}]
        good = community_fixture(sb.path("dk-good"), plugins, {"acme-test/zebra-widget": {"stars": 500}})
        self.assertRan(sb.run("dis_kaynak_ara.py", "--query", "zebra", "--cache-dir", good), 0)
        bad = community_fixture(sb.path("dk-bad"), plugins, {"acme-test/zebra-widget": {"stars": 500}})
        os.chmod(str(bad), 0o777)
        before = sorted((p.name, p.read_bytes()) for p in bad.iterdir())
        r = sb.run("dis_kaynak_ara.py", "--query", "zebra", "--cache-dir", bad)
        self.assertRan(r, 3)
        self.assertTrue(r.text.startswith(OFFLINE_LINE), r.describe())
        r = sb.run_code(FAKE_SKILLS_SH, SCRIPTS / "dis_kaynak_ara.py", "none", "--query", "zebra",
                        "--cache-dir", bad)
        self.assertRan(r, 0)
        self.assertIn("not: onbellek kullanilamadi (grup/herkes yazabilir); onbelleksiz calisildi (--cache-dir)",
                      r.lines, r.describe())
        self.assertIn("topluluk: ulasilamadi", r.lines[0])
        self.assertEqual(sorted((p.name, p.read_bytes()) for p in bad.iterdir()), before)

    def test_dis_kaynak_ara_symlinked_catalog_is_not_read(self):
        sb = self.sb
        plugins = [{"name": "zebra-widget", "description": "Zebra widget helper.",
                    "source": {"source": "url", "url": "https://github.com/acme-test/zebra-widget.git", "sha": SHA}}]
        src = community_fixture(sb.path("dk-src"), plugins, {})
        cdir = community_fixture(sb.path("dk-link"), [], {})
        (cdir / "community-marketplace.json").unlink()
        make_file_symlink(src / "community-marketplace.json", cdir / "community-marketplace.json")
        r = sb.run("dis_kaynak_ara.py", "--query", "zebra", "--cache-dir", cdir)
        self.assertRan(r, 3)

    def test_inventory_scripts_refuse_an_open_out_dir(self):
        sb = self.sb
        r = sb.run("katalog_indeksle.py", "--out", self.open_dir)
        self.assertRan(r)
        self.assertIn("not: 03-katalog-indeksi.json yazilmadi (", r.text)
        self.assertIn("not: 03-katalog-ozeti.md yazilmadi (", r.text)
        r = sb.run("skill_envanteri.py", "--out", self.open_dir)
        self.assertRan(r)
        self.assertIn("not: 02-skill-envanteri.json yazilmadi (", r.text)
        self.assertIn("not: 02-skill-envanteri-ozet.json yazilmadi (", r.text)
        self.assertEqual(os.listdir(str(self.open_dir)), [])


if __name__ == "__main__":
    unittest.main()
