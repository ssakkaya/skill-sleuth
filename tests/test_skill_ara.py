"""skill_ara.py on synthetic trees: output caps, broken input, the project walk, parallel cold runs, linked skill
folders, self-exclusion, hidden characters. Offline; never the real home folder."""
from __future__ import annotations

import json
import os
import re
import unittest

from sleuth_testlib import (SCRIPTS, SKILL_FOLDER, WITHOUT_ISJUNCTION, Sandbox, ScriptTestCase, lone_surrogate_json,
                            make_dir_link, make_junction, make_private, official_catalog, script_version, tier_counts,
                            write_bytes, write_json, write_skill, zw)

CUT = "…(cut at %d bytes; use --top/--max-bytes)"
BOTH_NOTE = "skill-sleuth ve skill-bulucu birlikte kurulu (ayni skill'in iki dil surumu): yalniz birini tut"


class OutputCap(ScriptTestCase):
    """stdout never exceeds --max-bytes (default 2048), in text and in --json."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.addClassCleanup(cls.sb.close)
        for i in range(30):
            write_skill(cls.sb.user_skills, "zebra-tool-%02d" % i,
                        description="Zebra stripes counter number %d. " % i
                        + "Counts zebra stripes in photos and writes a long report about every stripe. " * 3)

    def test_text_output_is_cut_at_the_default_cap(self):
        r = self.sb.skill_ara("--query", "zebra stripes", "--top", "30")
        self.assertRan(r)
        self.assertLessEqual(len(r.out), 2048, r.describe())
        self.assertTrue(r.text.startswith("skill_ara %s | q='zebra stripes' | " % script_version("skill_ara.py")),
                        r.describe())
        self.assertEqual(r.lines[-1], CUT % 2048, r.describe())
        self.assertNotIn(b"\r", r.out)

    def test_text_output_respects_a_smaller_cap(self):
        r = self.sb.skill_ara("--query", "zebra stripes", "--top", "30", "--max-bytes", "700")
        self.assertRan(r)
        self.assertLessEqual(len(r.out), 700, r.describe())
        self.assertEqual(r.lines[-1], CUT % 700, r.describe())

    def test_json_is_compact_and_capped(self):
        r = self.sb.skill_ara("--query", "zebra stripes", "--top", "30", "--json")
        self.assertRan(r)
        self.assertLessEqual(len(r.out), 2048, r.describe())
        self.assertEqual(r.out.count(b"\n"), 1, "compact JSON is one line")
        d = json.loads(r.text)
        self.assertEqual(d["version"], script_version("skill_ara.py"))
        self.assertGreaterEqual(d["hits"], 30)
        self.assertIsNotNone(d["truncated"], d)
        self.assertEqual(d["truncated"]["max_bytes"], 2048)
        self.assertEqual(len(d["results"]) + d["truncated"]["dropped"], 30)
        self.assertGreater(d["truncated"]["dropped"], 0)

    def test_json_respects_a_smaller_cap(self):
        r = self.sb.skill_ara("--query", "zebra stripes", "--top", "30", "--json", "--max-bytes", "1200")
        self.assertRan(r)
        self.assertLessEqual(len(r.out), 1200, r.describe())
        self.assertGreater(json.loads(r.text)["truncated"]["dropped"], 0)

    def test_json_not_truncated_when_it_fits(self):
        r = self.sb.skill_ara("--query", "zebra stripes", "--top", "30", "--json", "--max-bytes", "200000")
        self.assertRan(r)
        d = json.loads(r.text)
        self.assertIsNone(d["truncated"])
        self.assertEqual(len(d["results"]), 30)

    def test_show_is_capped(self):
        r = self.sb.skill_ara("--show", "zebra")          # no exact match: every invoke name containing "zebra"
        self.assertRan(r)
        self.assertLessEqual(len(r.out), 2048, r.describe())
        self.assertIn("(+", r.text)
        self.assertIn(" more: --show ", r.text)

    def test_max_bytes_below_300_is_exit_2(self):
        for value in ("299", "0", "-1"):
            with self.subTest(max_bytes=value):
                r = self.sb.skill_ara("--query", "zebra stripes", "--max-bytes", value)
                self.assertRan(r, 2)
                self.assertIn("--max-bytes must be at least 300", r.errtext)
                self.assertEqual(r.out, b"", "nothing on stdout")
        self.assertRan(self.sb.skill_ara("--query", "zebra stripes", "--max-bytes", "300"))

    def test_long_query_and_notes_never_exceed_the_cap(self):
        """The header alone can be longer than --max-bytes (a long query, three not: lines): text and --json are
        still cut to the cap, and --json stays valid JSON."""
        sb = Sandbox()
        self.addCleanup(sb.close)
        for i in range(12):
            write_skill(sb.user_skills, "zeb-%02d" % i, description="Zebra stripes " + "long words " * 40)
        write_skill(sb.user_skills, "skill-sleuth", description="x")          # not: both editions
        write_skill(sb.user_skills, "skill-bulucu", description="x")
        write_json(sb.plugins / "installed_plugins.json", {"version": 99, "plugins": {}})    # not: file formats
        write_json(sb.plugins / "plugin-catalog-cache.json", {"version": 42, "catalog": {"plugins": {}}})
        blocker = write_bytes(sb.path("blocker", "file"), "a file where the cache folder should be")
        cache = blocker / "cache.json"                                            # not: cache unusable
        r = sb.skill_ara("--query", "zebra", "--cache", cache)
        self.assertRan(r)
        self.assertEqual(len([ln for ln in r.lines if ln.startswith("not: ")]), 3, r.describe())
        for q in ("\U0001F993" * 500 + " zebra", "zebra " * 300, "ş" * 900 + " zebra"):
            for cap in (300, 333, 700):
                with self.subTest(query=q[:8], cap=cap):
                    r = sb.skill_ara("--query", q, "--top", "12", "--max-bytes", cap, "--cache", cache)
                    self.assertRan(r)
                    self.assertLessEqual(len(r.out), cap, r.describe())
                    self.assertEqual(r.lines[-1], CUT % cap, r.describe())
                    r = sb.skill_ara("--query", q, "--top", "12", "--max-bytes", cap, "--json", "--cache", cache)
                    self.assertRan(r)
                    self.assertLessEqual(len(r.out), cap, r.describe())
                    d = json.loads(r.text)
                    self.assertEqual(d["truncated"]["max_bytes"], cap, d)
                    self.assertEqual(len(d["results"]) + d["truncated"]["dropped"], 12, d)


class BrokenInput(ScriptTestCase):
    """Malformed frontmatter, non-UTF-8 files and odd Claude Code files never crash the index."""

    @classmethod
    def setUpClass(cls):
        cls.sb = sb = Sandbox()
        cls.addClassCleanup(cls.sb.close)
        us = sb.user_skills
        write_skill(us, "quirk-good", description="A quirkyword helper that works.")
        write_bytes(us / "quirk-unterminated" / "SKILL.md", "---\nname: unterm\ndescription: quirkyword open\n")
        write_bytes(us / "quirk-quotes" / "SKILL.md",
                    '---\nname: "unclosed\ndescription: [quirkyword, b\nkey: \'x\n---\n')
        write_bytes(us / "quirk-binary" / "SKILL.md",
                    b"---\nname: bin\xff\xfe\ndescription: \x80\x81 quirkyword \x00\x01\n---\n\xc3\x28 body")
        write_bytes(us / "quirk-latin1" / "SKILL.md",
                    "---\nname: latin\ndescription: café quirkyword\n---\n".encode("latin-1"))
        write_bytes(us / "quirk-list" / "SKILL.md",
                    "---\nname: listdesc\ndescription:\n  - quirkyword one\n  - two\n---\n")
        write_bytes(us / "quirk-map" / "SKILL.md", "---\nname: mapdesc\ndescription:\n  a: quirkyword\n---\n")
        write_bytes(us / "quirk-empty" / "SKILL.md", b"")
        write_bytes(us / "quirk-nofm" / "SKILL.md", "just text quirkyword, no frontmatter")
        write_bytes(us / "quirk-bom-crlf" / "SKILL.md",
                    b"\xef\xbb\xbf---\r\nname: bomcrlf\r\ndescription: quirkyword crlf\r\n---\r\n")
        cls.n_files = 10
        write_bytes(sb.plugins / "installed_plugins.json", b"\xff\xfe{not json")
        write_bytes(sb.plugins / "known_marketplaces.json", "[1, 2, 3]")
        write_json(sb.plugins / "plugin-catalog-cache.json", {"version": 99, "catalog": {"plugins": {}}})
        write_bytes(sb.config / "settings.json", "{oops")

    def test_query_survives_and_reports_changed_file_formats(self):
        r = self.sb.skill_ara("--query", "quirkyword")
        self.assertRan(r)
        self.assertIn("Skill(quirk-good)", r.text)
        note = [ln for ln in r.lines if ln.startswith("not: Claude Code dosya bicimi degismis olabilir: ")]
        self.assertEqual(len(note), 1, r.describe())
        self.assertIn("installed_plugins.json okunamadi", note[0])
        self.assertIn("known_marketplaces.json beklenmeyen bicim", note[0])
        self.assertIn("plugin-catalog-cache.json version=99 bilinmiyor", note[0])
        self.assertTrue(note[0].endswith("; plugin/katalog sonuclari eksik olabilir"), note[0])

    def test_every_skill_file_is_indexed(self):
        r = self.sb.skill_ara("--stats")
        self.assertRan(r)
        self.assertEqual(tier_counts(r.text).get("user"), self.n_files, r.describe())

    def test_json_and_show_survive(self):
        r = self.sb.skill_ara("--query", "quirkyword", "--json", "--top", "20")
        self.assertRan(r)
        d = json.loads(r.text)
        self.assertTrue(any(n.startswith("Claude Code dosya bicimi") for n in d["notes"]), d["notes"])
        for name in ("quirk-binary", "quirk-latin1", "quirk-empty", "bomcrlf"):
            r = self.sb.skill_ara("--show", name)
            self.assertRan(r)
            self.assertNotIn("no entry matches", r.text, r.describe())

    def test_lone_surrogate_in_a_json_file(self):
        """A "\\ud800" escape in plugin.json / the catalog: no crash, '?' in the output, and the cache round-trips."""
        sb = Sandbox()
        self.addCleanup(sb.close)
        ver = sb.plugins / "cache" / "mkt" / "plug" / "1.0.0"
        write_bytes(ver / ".claude-plugin" / "plugin.json", '{"name": %s}' % lone_surrogate_json())
        write_skill(ver / "skills", "surro-tool", description="Surrogateword helper.")
        write_json(sb.config / "settings.json", {"enabledPlugins": {"plug@mkt": True}})
        write_bytes(sb.plugins / "plugin-catalog-cache.json",
                    '{"version": 1, "catalog": {"plugins": {"surro-cat@claude-plugins-official": {"marketplace_entry":'
                    ' {"name": "surro-cat", "description": "Surrogateword catalog %s"}}}}}' % lone_surrogate_json())
        for args in (("--query", "surrogateword"), ("--query", "surrogateword", "--json"), ("--show", "surro-cat"),
                     ("--stats",)):
            with self.subTest(args=args):
                r = sb.skill_ara(*args)
                self.assertRan(r)
                self.assertNoInvisible(r)
        first, second = sb.skill_ara("--query", "surrogateword", "--refresh"), sb.skill_ara("--query", "surrogateword")
        self.assertIn(", rebuilt:refresh)", first.lines[0])
        self.assertNotIn("rebuilt:", second.lines[0], second.describe())
        self.assertIn("x?y:surro-tool", second.text, second.describe())

    def test_second_run_uses_the_cache(self):
        sb = Sandbox()
        try:
            write_skill(sb.user_skills, "cache-probe", description="Cacheprobe helper.")
            first = sb.skill_ara("--query", "cacheprobe")
            second = sb.skill_ara("--query", "cacheprobe")
            self.assertRan(first)
            self.assertRan(second)
            self.assertIn(", rebuilt:no-cache)", first.lines[0])
            self.assertNotIn("rebuilt:", second.lines[0])
            self.assertTrue(sb.cache.is_file())
        finally:
            sb.close()


class ProjectWalk(ScriptTestCase):
    """Project skills: cwd and ancestors BELOW the home folder; home is never a project."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def test_home_is_not_a_project(self):
        sb = self.sb
        write_skill(sb.user_skills, "alpha-solo", description="Alphasolo helper.")
        env = sb.env(CLAUDE_CONFIG_DIR=None)                 # default <config> = ~/.claude of the sandbox home
        r = sb.skill_ara("--stats", cwd=sb.home, env=env)
        self.assertRan(r)
        counts = tier_counts(r.text)
        counts.pop("builtin", None)                           # builtins.json next to the script, if any
        self.assertEqual(counts, {"user": 1}, r.describe())
        r = sb.skill_ara("--show", "alpha-solo", cwd=sb.home, env=env)
        self.assertRan(r)
        self.assertEqual(r.text.count('"tier": '), 1, r.describe())
        self.assertIn('"tier": "user"', r.text)

    def test_walk_stops_at_home(self):
        sb = self.sb
        cfg = sb.mk("cfg")                                    # <config> outside home
        write_skill(sb.home / ".claude" / "skills", "beta-home", description="Betahome helper.")
        write_skill(sb.work / ".claude" / "skills", "delta-anc", description="Deltaanc helper.")
        proj = sb.mk("home", "work", "proj")
        write_skill(proj / ".claude" / "skills", "gamma-proj", description="Gammaproj helper.")
        env = sb.env(CLAUDE_CONFIG_DIR=cfg)
        r = sb.skill_ara("--stats", cwd=proj, env=env)
        self.assertRan(r)
        self.assertEqual(tier_counts(r.text).get("project"), 2, r.describe())
        r = sb.skill_ara("--show", "beta-home", cwd=proj, env=env)
        self.assertIn("no entry matches 'beta-home'", r.text, r.describe())
        r = sb.skill_ara("--show", "delta-anc", cwd=proj, env=env)      # an ancestor below home: loaded too
        self.assertIn('"invoke": "delta-anc"', r.text, r.describe())
        r = sb.skill_ara("--query", "gammaproj", cwd=proj, env=env)
        self.assertIn("Skill(gamma-proj)", r.text, r.describe())
        sb.mk("home", "work", "proj", ".git")                          # a repository: the walk stops at its root
        r = sb.skill_ara("--stats", cwd=proj, env=env)
        self.assertEqual(tier_counts(r.text).get("project"), 1, r.describe())

    def test_cwd_change_rebuilds_only_when_project_dirs_change(self):
        sb = self.sb
        a, b, c = sb.mk("home", "work", "a"), sb.mk("home", "work", "b"), sb.mk("home", "work", "c")
        write_skill(c / ".claude" / "skills", "c-skill", description="Cskill helper.")
        self.assertRan(sb.skill_ara("--stats", cwd=a))
        r = sb.skill_ara("--query", "anything", cwd=b)
        self.assertRan(r)
        self.assertNotIn("rebuilt:", r.lines[0])
        r = sb.skill_ara("--query", "anything", cwd=c)
        self.assertRan(r)
        self.assertIn("rebuilt:cwd-changed", r.lines[0])


class CacheFile(ScriptTestCase):
    """The cache's roots object keeps only the four compared roots (no cwd, home, cwd_dir or project_dirs keys);
    project skill folders that exist are still stored (project_roots, fingerprint, entry paths). --cache never
    replaces a file that is not ours, never goes into a Claude config tree, must end in .json and never blocks on a
    FIFO (soft: a 'not:' line, the index is built in memory, exit 0)."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def test_cache_keeps_no_cwd_or_project_folder_names(self):
        sb = self.sb
        proj = sb.mk("home", "work", "zebra-client-77")
        self.assertRan(sb.skill_ara("--stats", cwd=proj))
        text = sb.cache.read_text(encoding="utf-8")
        idx = json.loads(text)
        self.assertNotIn("zebra-client-77", text)
        self.assertNotIn("cwd", idx)
        self.assertEqual(sorted(idx["roots"]), ["claude_home", "extra", "lams", "plugins"])
        kiwi = sb.mk("home", "work", "kiwi-proj-12")
        write_skill(kiwi / ".claude" / "skills", "kiwi-skill", description="Kiwi helper.")
        self.assertRan(sb.skill_ara("--stats", cwd=kiwi))
        idx = json.loads(sb.cache.read_text(encoding="utf-8"))
        self.assertTrue(any("kiwi-proj-12" in p[0] for p in idx["project_roots"]),
                        "a project skill folder that exists is stored, as the README says")

    def test_roots_change_rebuilds(self):
        sb = self.sb
        self.assertRan(sb.skill_ara("--stats"))
        r = sb.skill_ara("--query", "anything", env=sb.env(CLAUDE_DESKTOP_DATA_DIR=sb.mk("desktop2")))
        self.assertRan(r)
        self.assertIn("rebuilt:roots-changed", r.lines[0], r.describe())

    def test_foreign_files_and_claude_trees_are_never_written(self):
        sb = self.sb
        victim = write_bytes(sb.path("p", "notes.json"), b'{"a": 1}\n')
        settings = sb.path("x", ".claude", "settings.json")
        txt = sb.path("c", "idx.txt")
        for path, reason in ((victim, "baska bir dosya"), (settings, "Claude ayar agaci"), (txt, "uzanti .json degil")):
            with self.subTest(cache=str(path)):
                r = sb.skill_ara("--query", "anything", "--cache", path)
                self.assertRan(r)
                self.assertIn(reason, r.text, r.describe())
        self.assertEqual(victim.read_bytes(), b'{"a": 1}\n')
        self.assertFalse(sb.path("x").exists(), "no folder is created in a Claude tree")
        self.assertFalse(sb.path("c").exists())
        empty = write_bytes(sb.path("e", "empty.json"), b"")
        make_private(empty.parent)                  # POSIX: whatever the umask, the folder may hold our cache
        self.assertRan(sb.skill_ara("--stats", "--cache", empty))
        self.assertTrue(empty.read_bytes().startswith(b'{"version": '), "an empty file may be replaced")
        self.assertRan(sb.skill_ara("--stats"))
        self.assertTrue(sb.cache.read_bytes().startswith(b'{"version": '), "the own cache is still written")

    def test_a_fifo_at_the_cache_path_never_blocks(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("no FIFOs on this OS")
        sb = self.sb
        d = sb.mk("fifo")
        make_private(d)
        fifo = d / "idx.json"
        os.mkfifo(str(fifo))
        r = sb.skill_ara("--query", "anything", "--cache", fifo, timeout=60)
        self.assertRan(r)
        self.assertIn("beklenen tur degil", r.text, r.describe())


class ParallelColdRuns(ScriptTestCase):
    """Two or more cold runs on one cache file at the same time never crash and leave a valid cache."""

    def test_parallel_cold_runs(self):
        sb = Sandbox()
        try:
            for i in range(6):
                write_skill(sb.user_skills, "race-%d" % i, description="Racecondition helper %d." % i)
            for _ in range(3):
                if sb.cache.exists():
                    sb.cache.unlink()
                started = [sb.start("skill_ara.py", "--query", "racecondition", "--cache", sb.cache)
                           for _ in range(4)]
                for s in started:
                    r = sb.finish(s)
                    self.assertRan(r)
                    self.assertTrue(r.text.startswith("skill_ara "), r.describe())
                    self.assertIn("Skill(race-", r.text)
                idx = json.loads(sb.cache.read_text(encoding="utf-8"))
                self.assertEqual(idx["version"], script_version("skill_ara.py"))
                self.assertEqual(sorted(os.listdir(str(sb.cache.parent))), [sb.cache.name], "no temp file left")
        finally:
            sb.close()


class LinkedSkillFolders(ScriptTestCase):
    """Symlinked skill folders (npx skills links them on macOS/Linux) are found; link cycles are not followed."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def test_linked_user_skill_is_found(self):
        sb = self.sb
        target = write_skill(sb.mk("elsewhere"), "otter-real", name="linked-otter", description="Otterlink helper.")
        make_dir_link(target, sb.user_skills / "linked-otter")
        r = sb.skill_ara("--query", "otterlink")
        self.assertRan(r)
        self.assertIn("Skill(linked-otter)  (user", r.text, r.describe())

    def test_linked_project_skill_is_found(self):
        sb = self.sb
        target = write_skill(sb.mk("elsewhere"), "heron-real", name="linked-heron", description="Heronlink helper.")
        make_dir_link(target, sb.work / ".claude" / "skills" / "linked-heron")
        r = sb.skill_ara("--query", "heronlink")
        self.assertRan(r)
        self.assertIn("Skill(linked-heron)  (project", r.text, r.describe())

    def test_linked_folder_under_extra_root_is_found(self):
        sb = self.sb
        target = write_skill(sb.mk("elsewhere"), "lynx-real", name="linked-lynx", description="Lynxlink helper.")
        root = sb.mk("extra-root")
        make_dir_link(target, root / "pack" / "linked-lynx")
        r = sb.skill_ara("--query", "lynxlink", "--root", root)
        self.assertRan(r)
        self.assertTrue([ln for ln in r.lines if "NOT USABLE -> " in ln and ln.endswith("  (other)")], r.describe())

    def test_link_cycle_is_not_followed(self):
        sb = self.sb
        write_skill(sb.user_skills, "cycle-owl", description="Cycleowl helper.")
        make_dir_link(sb.user_skills, sb.user_skills / "loop", allow_junction=False)
        make_dir_link(sb.user_skills / "cycle-owl", sb.user_skills / "cycle-owl" / "back", allow_junction=False)
        r = sb.skill_ara("--stats")
        self.assertRan(r)
        self.assertEqual(tier_counts(r.text).get("user"), 1, r.describe())

    def test_junction_cycle_without_isjunction(self):
        """Windows: junctions back into the tree are not followed, also on Python < 3.12 (no os.path.isjunction;
        the run below deletes it): the reparse-point attribute is checked instead."""
        sb = self.sb
        write_skill(sb.user_skills, "cycle-owl", description="Cycleowl helper.")
        make_junction(self, sb.user_skills, sb.user_skills / "loop")
        make_junction(self, sb.user_skills / "cycle-owl", sb.user_skills / "cycle-owl" / "back")
        for label, r in (("isjunction", sb.skill_ara("--stats", "--refresh")),
                         ("no isjunction", sb.run_code(WITHOUT_ISJUNCTION, SCRIPTS / "skill_ara.py", "--stats",
                                                       "--refresh", "--cache", sb.cache))):
            with self.subTest(label):
                self.assertRan(r)
                self.assertEqual(tier_counts(r.text).get("user"), 1, r.describe())


class SelfExclusion(ScriptTestCase):
    """The skill never lists itself (either edition); both editions installed -> one 'not:' line."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def install_both(self, record=True):
        """skill-sleuth as a user skill, skill-bulucu as an installed plugin (record=False: its cache folder exists
        but installed_plugins.json does not list it, as after an uninstall). -> the plugin's version folder."""
        sb = self.sb
        write_skill(sb.user_skills, "skill-sleuth", description="Finds the right skill for a quokka task.")
        ver = sb.plugins / "cache" / "skill-sleuth" / "skill-bulucu" / "0.1.0"
        write_json(ver / ".claude-plugin" / "plugin.json", {"name": "skill-bulucu", "version": "0.1.0"})
        write_skill(ver / "skills", "skill-bulucu", description="Quokka isi icin dogru skill'i bulur.")
        write_json(sb.config / "settings.json", {"enabledPlugins": {"skill-bulucu@skill-sleuth": True}})
        plugins = {"skill-bulucu@skill-sleuth": [{"scope": "user", "installPath": str(ver), "version": "0.1.0"}]}
        write_json(sb.plugins / "installed_plugins.json", {"version": 2, "plugins": plugins if record else {}})
        write_skill(sb.user_skills, "quokka-helper", description="Quokka photo helper skill.")
        return ver

    NOTE = "not: " + BOTH_NOTE

    def test_query_never_lists_either_edition(self):
        self.install_both()
        r = self.sb.skill_ara("--query", "quokka skill finds right")
        self.assertRan(r)
        self.assertIn("Skill(quokka-helper)", r.text)
        self.assertNotIn("Skill(skill-sleuth)", r.text)
        self.assertNotIn("skill-bulucu:skill-bulucu", r.text)
        d = json.loads(self.sb.skill_ara("--query", "quokka skill finds right", "--json").text)
        names = set(x["name"] for x in d["results"]) | set(x["plugin"] or "" for x in d["results"])
        self.assertFalse(names & {"skill-sleuth", "skill-bulucu"}, d["results"])

    def test_both_editions_note(self):
        self.install_both()
        r = self.sb.skill_ara("--query", "quokka")
        self.assertRan(r)
        self.assertIn(self.NOTE, r.lines[1:4], r.describe())
        r = self.sb.skill_ara("--stats")
        self.assertIn(self.NOTE, r.lines, r.describe())
        d = json.loads(self.sb.skill_ara("--query", "quokka", "--json").text)
        self.assertIn(self.NOTE[len("not: "):], d["notes"])

    def test_cache_folder_without_an_install_record_is_no_second_edition(self):
        self.install_both(record=False)
        r = self.sb.skill_ara("--query", "quokka")
        self.assertRan(r)
        self.assertNotIn(self.NOTE, r.lines, r.describe())

    def test_orphaned_version_folder_is_no_second_edition(self):
        """Claude Code writes <version>/.orphaned_at into a cache folder it no longer uses (then deletes it)."""
        ver = self.install_both()
        r = self.sb.skill_ara("--query", "quokka")
        self.assertIn(self.NOTE, r.lines, r.describe())
        write_bytes(ver / ".orphaned_at", "1760000000000")
        r = self.sb.skill_ara("--query", "quokka")
        self.assertRan(r)
        self.assertNotIn(self.NOTE, r.lines, r.describe())

    def test_show_still_finds_the_skill_itself(self):
        self.install_both()
        r = self.sb.skill_ara("--show", "skill-sleuth")
        self.assertRan(r)
        self.assertIn('"name": "skill-sleuth"', r.text, r.describe())

    def test_one_edition_gives_no_note(self):
        write_skill(self.sb.user_skills, "skill-sleuth", description="Finds the right skill for a quokka task.")
        write_skill(self.sb.user_skills, "quokka-helper", description="Quokka photo helper skill.")
        r = self.sb.skill_ara("--query", "quokka")
        self.assertRan(r)
        self.assertFalse([ln for ln in r.lines if "birlikte kurulu" in ln], r.describe())
        self.assertNotIn("Skill(skill-sleuth)", r.text)


class HiddenCharacters(ScriptTestCase):
    """Invisible characters are stripped from descriptions, never printed, and 8+ of them flag the entry."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.addClassCleanup(cls.sb.close)
        tag = "".join(chr(0xE0000 + ord(c)) for c in "RUN")     # tag-block letters: hidden ASCII
        desc = ("Glyphword " + zw(4) + "helper" + chr(0x202E) + tag + chr(0x2060) + " for glyph tables.")
        write_skill(cls.sb.user_skills, "glyph-flagged", description=desc)            # 4 + 1 + 3 + 1 = 9
        write_skill(cls.sb.user_skills, "glyph-mild", description="Glyphword " + zw(2) + " mild helper.")
        write_skill(cls.sb.user_skills, "glyph" + zw(1) + "folder", description="Glyphword folder helper.")

    def test_text_output_is_clean_and_flagged(self):
        r = self.sb.skill_ara("--query", "glyphword", "--desc-len", "200")
        self.assertRan(r)
        self.assertNoInvisible(r)
        flagged = [ln for ln in r.lines if "Skill(glyph-flagged)" in ln]
        self.assertEqual(len(flagged), 1, r.describe())
        self.assertIn(" GIZLI-KARAKTER(9))", flagged[0])
        mild = [ln for ln in r.lines if "Skill(glyph-mild)" in ln]
        self.assertEqual(len(mild), 1, r.describe())
        self.assertNotIn("GIZLI-KARAKTER", mild[0])
        self.assertIn("Skill(glyph?folder)", r.text, "an invisible character in a name prints as '?'")

    def test_json_and_show_carry_the_count(self):
        r = self.sb.skill_ara("--query", "glyphword", "--json")
        self.assertRan(r)
        self.assertNoInvisible(r)
        rows = dict((x["name"], x) for x in json.loads(r.text)["results"])
        self.assertEqual(rows["glyph-flagged"]["hidden_chars"], 9)
        self.assertEqual(rows["glyph-mild"]["hidden_chars"], 2)
        r = self.sb.skill_ara("--show", "glyph-flagged")
        self.assertRan(r)
        self.assertNoInvisible(r)
        self.assertIn('"hidden_chars": 9', r.text)


class CatalogCandidates(ScriptTestCase):
    """Official-catalog plugins that are not usable yet carry popularity and freshness markers; AZ-KURULUM costs
    points (offline: plugin-catalog-cache.json only)."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.addClassCleanup(cls.sb.close)
        official_catalog(cls.sb)

    def line(self, r, plugin):
        rows = [ln for ln in r.lines if "NOT USABLE -> claude plugin install %s@claude-plugins-official  (" % plugin
                in ln]
        self.assertEqual(len(rows), 1, r.describe())
        return rows[0]

    def test_markers(self):
        r = self.sb.skill_ara("--query", "walrus")
        self.assertRan(r)
        self.assertRegex(self.line(r, "walrus-tool"), r"\(catalog-remote/plugin installs=50 AZ-KURULUM "
                                                      r"guncel=\d{4}-\d{2}-\d{2}\)$")
        self.assertRegex(self.line(r, "walrus-popular"), r" installs=50000 guncel=\d{4}-\d{2}-\d{2} BAYAT\)$")
        self.assertRegex(self.line(r, "walrus-nocount"), r" installs=veri-yok guncel=\d{4}-\d{2}-\d{2}\)$")
        self.assertIn("   skills: walrus-skill", r.lines)

    def test_low_installs_rank_below_an_unknown_count(self):
        d = json.loads(self.sb.skill_ara("--query", "walrus", "--json").text)
        rows = dict((x["name"], x) for x in d["results"])
        self.assertEqual(rows["walrus-tool"]["labels"], ["AZ-KURULUM"])
        self.assertEqual(rows["walrus-popular"]["labels"], ["BAYAT"])
        self.assertLess(rows["walrus-tool"]["score"], rows["walrus-nocount"]["score"])

    def test_show_plugin_record(self):
        r = self.sb.skill_ara("--show", "walrus-tool")
        self.assertRan(r)
        rec = json.loads(r.text)                              # one record: the plugin entry of the index
        self.assertEqual(rec["unique_installs"], 50)
        self.assertEqual(rec["source_url"], "https://github.com/acme-test/walrus-tool.git")
        self.assertLessEqual(len(r.out), 2048)

    def test_show_plugin_record_carries_the_catalog_date(self):
        """A review block takes the catalog's own date from --show, never from last_updated or a guess."""
        rec = json.loads(self.sb.skill_ara("--show", "walrus-tool").text)
        self.assertRegex(rec["catalog_fetched_at"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsNone(rec["installs_as_of"])              # the fixture records no installs_generated_at


class PluginsRoot(ScriptTestCase):
    """$CLAUDE_CODE_PLUGIN_CACHE_DIR moves the plugins root (a leading ~ is expanded)."""

    def test_plugin_root_variable(self):
        sb = Sandbox()
        try:
            ver = sb.home / "pc" / "cache" / "mkt" / "plug" / "1.0.0"
            write_json(ver / ".claude-plugin" / "plugin.json", {"name": "plug", "version": "1.0.0"})
            write_skill(ver / "skills", "badger-tool", description="Badgerword helper.")
            write_json(sb.config / "settings.json", {"enabledPlugins": {"plug@mkt": True}})
            r = sb.skill_ara("--query", "badgerword")
            self.assertRan(r)
            self.assertNotIn("Skill(plug:badger-tool)", r.text)
            for value in (sb.home / "pc", "~/pc"):
                r = sb.skill_ara("--query", "badgerword", env=sb.env(CLAUDE_CODE_PLUGIN_CACHE_DIR=value))
                self.assertRan(r)
                self.assertIn("Skill(plug:badger-tool)  (plugin-cache", r.text, r.describe())
        finally:
            sb.close()


class Arguments(ScriptTestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def test_no_mode_is_exit_2(self):
        self.assertRan(self.sb.run("skill_ara.py"), 2)

    def test_cache_inside_the_skill_folder_is_refused(self):
        target = SKILL_FOLDER / "x-test-cache.json"
        r = self.sb.run("skill_ara.py", "--stats", "--cache", target)
        self.assertRan(r, 2)
        self.assertIn("--cache must not point inside the skill folder", r.errtext)
        self.assertFalse(target.exists())

    def test_stats_names_the_cache(self):
        r = self.sb.skill_ara("--stats")
        self.assertRan(r)
        m = re.match(r"^cache: (.+) \((\d+) bytes, built ", r.lines[0])
        self.assertTrue(m, r.describe())
        self.assertEqual(os.path.normcase(m.group(1)), os.path.normcase(str(self.sb.cache)))


class ClaudeCodeLoadRules(ScriptTestCase):
    """Skill(<name>) only for what Claude Code 2.1.295 loads: enabledPlugins / skillOverrides merged from the user,
    project and local settings; only the live plugin-cache version folder; a plugin's default skills/ folder plus
    its declared paths (or a SKILL.md at its root); one-level skill folders; never a marketplace clone. An installed
    plugin without skills is never offered for installation; a BOM does not empty a JSON file."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def cached(self, name, ver="1.0.0", skills=("otter-one",), pj=None, mkt="mkt"):
        """<cache>/<mkt>/<name>/<ver>/ with .claude-plugin/plugin.json and skills/<s>/SKILL.md -> the folder."""
        d = self.sb.plugins / "cache" / mkt / name / ver
        write_json(d / ".claude-plugin" / "plugin.json", pj or {"name": name, "version": ver})
        for s in skills:
            write_skill(d / "skills", s, description="Otter %s helper skill." % s)
        return d

    def installed(self, **records):
        """installed_plugins.json: plugin key (name__mkt, '__' standing for '@') -> list of install folders."""
        write_json(self.sb.plugins / "installed_plugins.json", {"version": 2, "plugins": dict(
            (k.replace("__", "@"), [{"scope": "user", "installPath": str(p), "version": p.name} for p in v])
            for k, v in records.items())})

    def settings(self, where, data):
        path = {"user": self.sb.config / "settings.json",
                "project": self.sb.work / ".claude" / "settings.json",
                "local": self.sb.work / ".claude" / "settings.local.json"}[where]
        write_json(path, data)

    def query(self, q="otter", *extra, cached=False):
        """--refresh unless cached: two writes of installed_plugins.json can share one mtime second."""
        r = self.sb.skill_ara("--query", q, "--top", "12", "--max-bytes", "8192", *(() if cached else ("--refresh",)),
                              *extra)
        self.assertRan(r)
        return r

    def names(self, *extra):
        """Names of the --json results of the query 'otter'."""
        return [x["name"] for x in json.loads(self.query("otter", "--json", *extra).text)["results"]]

    def test_local_and_project_settings_decide_enablement(self):
        d = self.cached("plug")
        self.installed(plug__mkt=[d])
        self.settings("local", {"enabledPlugins": {"plug@mkt": True}})     # claude plugin install --scope local
        self.assertIn("Skill(plug:otter-one)", self.query().text)
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        self.settings("local", {"enabledPlugins": {"plug@mkt": False}})    # switched off in this project only
        r = self.query()
        self.assertNotIn("Skill(plug:otter-one)", r.text, r.describe())
        self.assertIn("NOT USABLE -> claude plugin enable plug@mkt", r.text, r.describe())

    def test_skill_overrides_stop_model_invocation(self):
        for name in ("otter-off", "otter-uio", "otter-on"):
            write_skill(self.sb.user_skills, name, description="Otter %s helper skill." % name)
        r = self.query(cached=True)
        self.assertIn("Skill(otter-off)", r.text, r.describe())
        self.settings("user", {"skillOverrides": {"otter-off": "off", "otter-uio": "user-invocable-only",
                                                  "otter-on": "name-only"}})
        r = self.query(cached=True)          # the cache must notice the new overrides (fingerprint)
        self.assertIn("Skill(otter-on)", r.text, r.describe())
        for name in ("otter-off", "otter-uio"):
            self.assertNotIn("Skill(%s)" % name, r.text, r.describe())
        self.assertIn("NOT USABLE -> skillOverrides: off; /skills ile ac", r.text, r.describe())

    def test_only_the_live_version_folder_counts(self):
        old = self.cached("plug", "0.9.0", ("otter-old", "otter-keep"))
        new = self.cached("plug", "1.0.0", ("otter-keep",))
        self.installed(plug__mkt=[new])      # an update left 0.9.0 behind, still without a marker
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        r = self.query()
        self.assertIn("Skill(plug:otter-keep)", r.text, r.describe())
        self.assertNotIn("otter-old", r.text, r.describe())
        d = json.loads(self.sb.skill_ara("--show", "plug:otter-keep").text)
        self.assertEqual(d["plugin_version"], "1.0.0")
        self.installed()                     # uninstalled: the folder stays for days, the plugin is gone
        self.assertNotIn("otter-keep", self.query().text)
        self.assertTrue(old.is_dir())

    def test_installed_plugin_without_skills_is_not_offered_for_install(self):
        write_json(self.sb.plugins / "plugin-catalog-cache.json", {"version": 1, "catalog": {"plugins": {
            "walrus-mcp@claude-plugins-official": {
                "marketplace_entry": {"name": "walrus-mcp", "description": "Walrus tracker MCP server.",
                                      "source": {"source": "url", "url": "https://github.com/acme-test/walrus-mcp.git"}},
                "components": {"mcpServers": ["walrus"]}, "unique_installs": 5000}}}})
        d = self.cached("walrus-mcp", "abc123", skills=(), mkt="claude-plugins-official")
        write_json(d / ".mcp.json", {"mcpServers": {"walrus": {"command": "walrus-server"}}})
        self.installed(**{"walrus-mcp__claude-plugins-official": [d]})
        self.settings("user", {"enabledPlugins": {"walrus-mcp@claude-plugins-official": True}})
        r = self.query("walrus tracker")
        self.assertIn("NOT USABLE -> kurulu ve etkin; Skill adi yok (yalniz MCP/LSP/hook bileseni)", r.text,
                      r.describe())
        self.assertNotIn("claude plugin install walrus-mcp", r.text, r.describe())

    def test_clone_plugin_without_skill_md_is_searchable(self):
        clone = self.sb.plugins / "marketplaces" / "claude-plugins-official"
        write_json(clone / ".claude-plugin" / "marketplace.json", {"name": "claude-plugins-official", "plugins": [
            {"name": "octopus-mcp", "source": "./external_plugins/octopus-mcp", "description": "Octopus tracker."}]})
        write_json(clone / "external_plugins" / "octopus-mcp" / ".claude-plugin" / "plugin.json", {"name": "octopus-mcp"})
        write_json(clone / "external_plugins" / "octopus-mcp" / ".mcp.json", {"mcpServers": {}})
        write_json(self.sb.plugins / "plugin-catalog-cache.json", {"version": 1, "catalog": {"plugins": {
            "octopus-mcp@claude-plugins-official": {
                "marketplace_entry": {"name": "octopus-mcp", "description": "Octopus issue tracker tickets.",
                                      "source": "./external_plugins/octopus-mcp"},
                "components": {"mcpServers": ["octopus"]}, "unique_installs": 40000}}}})
        r = self.query("octopus tracker")
        self.assertIn("NOT USABLE -> claude plugin install octopus-mcp@claude-plugins-official", r.text, r.describe())

    def test_marketplace_clone_is_never_callable(self):
        d = self.cached("plug")
        clone = self.sb.plugins / "marketplaces" / "mkt"
        write_json(clone / ".claude-plugin" / "marketplace.json", {"name": "mkt", "plugins": [{"name": "plug"}]})
        write_json(clone / "plugins" / "plug" / ".claude-plugin" / "plugin.json", {"name": "plug"})
        for s in ("otter-one", "otter-two"):
            write_skill(clone / "plugins" / "plug" / "skills", s, description="Otter %s helper skill." % s)
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        self.installed()                     # enabled in settings, but no install record: nothing is loaded
        r = self.query()
        self.assertNotIn("Skill(plug:", r.text, r.describe())
        self.assertIn("NOT USABLE -> claude plugin install plug@mkt", r.text, r.describe())
        self.installed(plug__mkt=[d])
        r = self.query()
        self.assertIn("Skill(plug:otter-one)  (plugin-cache)", r.text, r.describe())
        self.assertNotIn("Skill(plug:otter-two)", r.text, r.describe())
        self.assertIn("NOT USABLE -> claude plugin update plug@mkt (kurulu surumde bu skill yok)", r.text, r.describe())

    def test_plugin_skill_paths(self):
        d = self.cached("plug", pj={"name": "plug", "skills": "./extra"})          # default skills/ AND ./extra
        write_skill(d / "extra", "otter-two", description="Otter otter-two helper skill.")
        write_skill(d / "skills" / "otter-one" / "templates", "otter-tmpl", description="Otter template.")
        solo = self.sb.plugins / "cache" / "mkt" / "solo" / "1.0.0"                  # a SKILL.md at the root only
        write_json(solo / ".claude-plugin" / "plugin.json", {"name": "solo"})
        write_skill(solo.parent, solo.name, name="solo:otter solo", description="Otter solo helper skill.")
        single = self.cached("single", pj={"name": "single", "skills": ["./tool"]}, skills=())
        write_skill(single, "tool", name="otter-single", description="Otter single helper skill.")
        self.installed(plug__mkt=[d], solo__mkt=[solo], single__mkt=[single])
        self.settings("user", {"enabledPlugins": {"plug@mkt": True, "solo@mkt": True, "single@mkt": True}})
        r = self.query()
        for inv in ("plug:otter-one", "plug:otter-two", "solo:otter-solo", "single:otter-single"):
            self.assertIn("Skill(%s)" % inv, r.text, r.describe())
        self.assertNotIn("otter-tmpl", self.names())                            # nested: not loaded
        self.assertIn("otter-tmpl", self.names("--all"))

    def test_nested_user_skill_is_not_callable(self):
        write_skill(self.sb.user_skills / "my-collection" / "skills", "otter-deep", description="Otter deep skill.")
        write_skill(self.sb.user_skills, "otter-top", description="Otter top skill.")
        r = self.query()
        self.assertIn("Skill(otter-top)", r.text, r.describe())
        self.assertNotIn("otter-deep", self.names())
        self.assertNotIn("Skill(otter-deep)", self.query("otter", "--all").text)
        self.assertIn("otter-deep", self.names("--all"))

    def test_settings_with_a_bom(self):
        d = self.cached("plug")
        self.installed(plug__mkt=[d])
        write_bytes(self.sb.config / "settings.json", "﻿" + json.dumps({"enabledPlugins": {"plug@mkt": True}}))
        self.assertIn("Skill(plug:otter-one)", self.query().text)

    def test_turkish_capital_i_and_short_stems(self):
        write_skill(self.sb.user_skills, "review-helper", description="Review code changes and audit them.")
        write_skill(self.sb.user_skills, "data-cleaner", description="Cleans data tables.")
        write_skill(self.sb.user_skills, "calendar-tool", description="Pick a date on the calendar.")
        write_skill(self.sb.user_skills, "code-helper", description="Helps with code changes.")
        self.assertIn("Skill(review-helper)", self.query("İncele", "--tier", "user").text)
        self.assertIn("Skill(code-helper)", self.query("coding", "--tier", "user").text)   # code / coding still meet
        r = self.query("date", "--tier", "user")
        first = [ln for ln in r.lines if ln.startswith("1. ")]
        self.assertTrue(first and "Skill(calendar-tool)" in first[0], r.describe())
        self.assertNotIn("Skill(data-cleaner)", r.text, r.describe())

    def catalog(self, plugins):
        write_json(self.sb.plugins / "plugin-catalog-cache.json", {"version": 1, "catalog": {"plugins": plugins}})

    def test_show_installed_plugin_with_skills_needs_nothing(self):
        d = self.cached("plug", mkt="claude-plugins-official")
        self.catalog({"plug@claude-plugins-official": {
            "marketplace_entry": {"name": "plug", "description": "Otter plugin.", "source": {"source": "url", "url": "x"}},
            "components": {"skills": [{"name": "otter-one"}]}}})
        self.installed(**{"plug__claude-plugins-official": [d]})
        self.settings("user", {"enabledPlugins": {"plug@claude-plugins-official": True}})
        r = self.sb.skill_ara("--show", "plug")
        self.assertRan(r)
        record = json.loads(r.text.split("\n}\n")[0] + "\n}")
        self.assertIsNone(record["install_cmd"], r.describe())
        self.assertNotIn("Skill adi yok", r.text, r.describe())

    def test_clone_copy_never_replaces_the_callable_copy(self):
        d = self.sb.plugins / "cache" / "mkt" / "plug" / "1.0.0"
        write_json(d / ".claude-plugin" / "plugin.json", {"name": "plug"})
        write_skill(d / "skills", "otter-one", description="Old description.")
        clone = self.sb.plugins / "marketplaces" / "mkt" / "plugins" / "plug"
        write_json(clone / ".claude-plugin" / "plugin.json", {"name": "plug"})
        write_skill(clone / "skills", "otter-one", description="Use when you need otter tracking reports.")
        self.installed(plug__mkt=[d])
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        r = self.query("otter reports")
        self.assertIn("Skill(plug:otter-one)", r.text, r.describe())
        self.assertNotIn("claude plugin update", r.text, r.describe())

    def test_install_folder_comes_from_the_record(self):
        d = self.cached("otter-tools", pj={"name": "otter.tools"})       # Claude Code sanitizes the folder name
        self.installed(**{"otter.tools__mkt": [d]})
        self.settings("user", {"enabledPlugins": {"otter.tools@mkt": True}})
        self.assertIn("Skill(otter.tools:otter-one)", self.query().text)

    def test_install_record_of_another_project_does_not_apply(self):
        old = self.cached("plug", "1.0.0", ("otter-legacy",))
        new = self.cached("plug", "2.0.0", ("otter-new",))
        other = self.sb.mk("home", "other-project")
        write_json(self.sb.plugins / "installed_plugins.json", {"version": 2, "plugins": {"plug@mkt": [
            {"scope": "user", "installPath": str(new), "version": "2.0.0"},
            {"scope": "local", "projectPath": str(other), "installPath": str(old), "version": "1.0.0"}]}})
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        r = self.query()
        self.assertIn("Skill(plug:otter-new)", r.text, r.describe())
        self.assertNotIn("otter-legacy", self.names("--all"))

    def test_marketplace_entry_decides_the_skill_paths(self):
        mkt = self.sb.plugins / "marketplaces" / "mkt"
        write_json(mkt / ".claude-plugin" / "marketplace.json", {"name": "mkt", "plugins": [
            {"name": "doc-skills", "source": "./", "strict": False, "skills": ["./skills/otter-xlsx"]},
            {"name": "amd", "source": {"source": "git-subdir", "url": "https://github.com/acme-test/amd.git",
                                        "path": "skills"}, "strict": False, "skills": ["./otter-local"]}]})
        doc = self.sb.plugins / "cache" / "mkt" / "doc-skills" / "abc123"            # a whole repository, no plugin.json
        for s in ("otter-xlsx", "otter-art"):
            write_skill(doc / "skills", s, description="Otter %s helper skill." % s)
        amd = self.sb.plugins / "cache" / "mkt" / "amd" / "1.0.0"
        write_skill(amd, "otter-local", description="Otter local helper skill.")
        self.installed(**{"doc-skills__mkt": [doc], "amd__mkt": [amd]})
        self.settings("user", {"enabledPlugins": {"doc-skills@mkt": True, "amd@mkt": True}})
        r = self.query()
        self.assertIn("Skill(doc-skills:otter-xlsx)", r.text, r.describe())
        self.assertIn("Skill(amd:otter-local)", r.text, r.describe())
        self.assertNotIn("Skill(doc-skills:otter-art)", r.text, r.describe())

    def test_skills_dir_plugin(self):
        root = self.sb.user_skills / "myinit"
        write_json(root / ".claude-plugin" / "plugin.json", {"name": "myinit", "skills": ["./"]})
        write_skill(self.sb.user_skills, "myinit", description="Otter myinit helper skill.")
        write_skill(root / "skills", "otter-example", description="Otter example helper skill.")
        r = self.query()
        self.assertIn("Skill(myinit)", r.text, r.describe())
        self.assertIn("Skill(myinit:otter-example)", r.text, r.describe())
        self.settings("user", {"enabledPlugins": {"myinit@skills-dir": False}})
        r = self.query()
        self.assertNotIn("Skill(myinit", r.text, r.describe())
        self.assertIn("NOT USABLE -> enabledPlugins myinit@skills-dir: false", r.text, r.describe())

    def test_bundled_skills_follow_overrides_and_the_disable_switch(self):
        self.assertIn("Skill(code-review)", self.query("code review", "--tier", "builtin").text)
        self.settings("user", {"skillOverrides": {"code-review": "off"}})
        r = self.query("code review", "--tier", "builtin")
        self.assertNotIn("Skill(code-review)", r.text, r.describe())
        self.settings("user", {"disableBundledSkills": True})
        r = self.query("code review", "--tier", "builtin")
        self.assertNotIn("Skill(", r.text, r.describe())

    def test_a_ghost_of_the_other_edition_is_no_second_install(self):
        write_skill(self.sb.user_skills, "skill-sleuth", description="Finds the right skill for an otter task.")
        write_skill(self.sb.user_skills / "old-backup", "skill-bulucu", description="Otter isi icin skill bulur.")
        r = self.query()
        self.assertFalse([ln for ln in r.lines if "birlikte kurulu" in ln], r.describe())

    @unittest.skipUnless(os.name != "nt", "local settings at the git root: macOS / Linux only (Claude Code)")
    def test_local_settings_of_the_git_root(self):
        d = self.cached("plug")
        self.installed(plug__mkt=[d])
        repo = self.sb.mk("home", "work", "repo")
        self.sb.mk("home", "work", "repo", ".git")
        sub = self.sb.mk("home", "work", "repo", "sub")
        write_json(repo / ".claude" / "settings.local.json", {"enabledPlugins": {"plug@mkt": True}})
        r = self.sb.skill_ara("--query", "otter", "--refresh", cwd=sub)
        self.assertRan(r)
        self.assertIn("Skill(plug:otter-one)", r.text, r.describe())

    def test_skills_dir_plugin_needs_its_manifest_and_follows_its_name(self):
        bare = self.sb.user_skills / "nojson"                          # .claude-plugin/ without plugin.json
        (bare / ".claude-plugin").mkdir(parents=True)
        write_skill(bare / "skills", "otter-nojson", description="Otter nojson helper skill.")
        named = self.sb.user_skills / "folder-x"                       # manifest name differs from the folder
        write_json(named / ".claude-plugin" / "plugin.json", {"name": "otterkit"})
        write_skill(self.sb.user_skills, "folder-x", description="Otter folder helper skill.")
        write_skill(named / "skills", "otter-kit", description="Otter kit helper skill.")
        write_bytes(named / "commands" / "otter-cmd.md", "---\ndescription: Otter command helper.\n---\nBody.\n")
        off = self.sb.user_skills / "sleepy"                           # defaultEnabled: false
        write_json(off / ".claude-plugin" / "plugin.json", {"name": "sleepy", "defaultEnabled": False})
        write_skill(off / "skills", "otter-sleepy", description="Otter sleepy helper skill.")
        r = self.query()
        self.assertNotIn("nojson:", r.text, r.describe())
        for inv in ("folder-x", "otterkit:otter-kit", "otterkit:otter-cmd"):
            self.assertIn("Skill(%s)" % inv, r.text, r.describe())
        self.assertNotIn("Skill(sleepy:otter-sleepy)", r.text, r.describe())
        self.settings("user", {"enabledPlugins": {"folder-x@skills-dir": False, "sleepy@skills-dir": True}})
        r = self.query()                     # the folder name is not the key; enabledPlugins true wins
        self.assertIn("Skill(otterkit:otter-kit)", r.text, r.describe())
        self.assertIn("Skill(folder-x)", r.text, r.describe())
        self.assertIn("Skill(sleepy:otter-sleepy)", r.text, r.describe())
        self.settings("user", {"enabledPlugins": {"otterkit@skills-dir": False}})
        r = self.query()
        self.assertNotIn("Skill(otterkit:", r.text, r.describe())
        self.assertNotIn("Skill(folder-x)", r.text, r.describe())

    def test_only_the_first_applying_install_record_loads(self):
        one = self.cached("plug", "1.0.0", ("otter-first",))
        two = self.cached("plug", "2.0.0", ("otter-second",))
        write_json(self.sb.plugins / "installed_plugins.json", {"version": 2, "plugins": {"plug@mkt": [
            {"scope": "user", "installPath": str(one), "version": "1.0.0"},
            {"scope": "project", "projectPath": str(self.sb.work), "installPath": str(two), "version": "2.0.0"}]}})
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        r = self.query()
        self.assertIn("Skill(plug:otter-first)", r.text, r.describe())
        self.assertNotIn("otter-second", self.names("--all"))

    def test_a_skill_path_may_not_leave_the_plugin(self):
        d = self.cached("plug", pj={"name": "plug", "skills": ["../../outside"]}, skills=())
        write_skill(d.parent.parent / "outside", "otter-out", description="Otter outside helper skill.")
        self.installed(plug__mkt=[d])
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        self.assertNotIn("Skill(plug:otter-out)", self.query().text)

    def test_refused_plugin_says_why(self):
        mkt = self.sb.plugins / "marketplaces" / "mkt"
        write_json(mkt / ".claude-plugin" / "marketplace.json", {"name": "mkt", "plugins": [
            {"name": "plug", "source": {"source": "url", "url": "https://github.com/acme-test/plug.git"},
             "strict": False, "commands": []}]})
        d = self.cached("plug")
        self.installed(plug__mkt=[d])
        self.settings("user", {"enabledPlugins": {"plug@mkt": True}})
        r = self.query("otter", "--all")
        self.assertNotIn("Skill(plug:otter-one)", r.text, r.describe())
        self.assertIn("NOT USABLE -> Claude Code bu plugin'i yuklemez", r.text, r.describe())

    def test_environment_flags_are_booleans(self):
        env = self.sb.env(CLAUDE_CODE_DISABLE_BUNDLED_SKILLS="0")
        r = self.sb.skill_ara("--query", "code review", "--tier", "builtin", "--refresh", env=env)
        self.assertIn("Skill(code-review)", r.text, r.describe())
        env = self.sb.env(CLAUDE_CODE_DISABLE_BUNDLED_SKILLS="true")
        r = self.sb.skill_ara("--query", "code review", "--tier", "builtin", "--refresh", env=env)
        self.assertNotIn("Skill(code-review)", r.text, r.describe())


if __name__ == "__main__":
    unittest.main()
