"""katalog_indeksle.py and skill_envanteri.py (the offline diagnostic scripts) on synthetic trees."""
from __future__ import annotations

import json
import os
import unittest

from sleuth_testlib import (SCRIPTS, SKILL_FOLDER, WITHOUT_ISJUNCTION, Sandbox, ScriptTestCase, invisible_chars,
                            lone_surrogate_json, make_junction, official_catalog, write_bytes, write_json, write_skill,
                            zw)


def odd_shapes(sb):
    """Claude Code / marketplace files whose fields have unexpected JSON types (every value below is a wrong type
    or an out-of-range number), plus a marketplace clone that holds two plugin folders."""
    mkt = sb.plugins / "marketplaces" / "m1"
    write_json(mkt / ".claude-plugin" / "marketplace.json", {"name": "m1", "renames": [1], "plugins": [
        {"name": "p-int", "source": 5, "skills": ["./skills/a", 3]},
        {"name": "p-list", "source": [1, 2], "skills": "./skills/b", "category": ["x"], "homepage": 9},
        {"name": "p-local", "source": {"source": ["url"], "url": 5, "path": [1]}, "keywords": {"k": 1}},
        {"name": "p-gh", "source": {"source": "github", "repo": {"a": 1}}, "tags": 7}, 4, None]})
    write_skill(mkt / "plugins" / "p-local" / "skills", "walrus-a", description="Walrus local.")
    write_json(mkt / "plugins" / "lonely" / ".claude-plugin" / "plugin.json", {"name": 5, "description": ["d"]})
    write_skill(mkt / "plugins" / "lonely" / "skills", "walrus-b", description="Walrus lonely.")
    write_json(mkt / "plugins" / "lonely" / ".mcp.json", {"mcpServers": [1]})
    write_json(mkt / "plugins" / "lonely" / "hooks" / "hooks.json", {"hooks": "x"})
    write_json(sb.plugins / "known_marketplaces.json",
               {"m1": {"installLocation": str(mkt), "lastUpdated": 5, "source": [1]}, "m2": {"installLocation": 7}})
    write_json(sb.plugins / "installed_plugins.json", {"version": 2, "plugins": {"p-int@m1": 5, "x": None}})
    write_json(sb.config / "settings.json", {"enabledPlugins": {"p-int@m1": [1]}})
    write_bytes(sb.plugins / "plugin-catalog-cache.json",
                '{"version": 1, "fetchedAt": 7, "catalog": {"generated_at": [1], "plugins": {'
                '"p-int@m1": {"unique_installs": "many", "components": {"skills": [{"name": "s", "chars": 5}],'
                ' "hooks": 3, "mcpServers": {"m": 1}}, "marketplace_entry": {"name": "p-int", "homepage": 9,'
                ' "source": {"source": "url", "url": 5, "path": [1]}}},'
                '"p-list@m1": {"unique_installs": 1e400, "marketplace_entry": {"source": {"source": ["x"]}}},'
                '"q@m1": {"unique_installs": [3], "components": [1]},'
                '"r@m1": {"unique_installs": 12.7, "marketplace_entry": 5}}}}')
    lams = sb.desktop / "local-agent-mode-sessions"
    write_json(lams / "acc" / "org" / "scheduled-tasks.json", {"scheduledTasks": 5})
    write_json(lams / "acc2" / "org" / "scheduled-tasks.json", {"scheduledTasks": {"filePath": "x"}})
    write_json(lams / "acc" / "org" / "rpm" / "manifest.json", {"plugins": {"id": "plugin_1"}})
    write_skill(lams / "acc" / "org" / "rpm" / "plugin_1" / "skills", "walrus-r", description="Walrus rpm.")
    write_json(lams / "skills-plugin" / "o" / "a" / "manifest.json", {"skills": "all"})
    write_skill(lams / "skills-plugin" / "o" / "a" / "skills", "walrus-d", description="Walrus desktop.")
    write_json(sb.desktop / "claude_desktop_config.json", {"coworkUserFilesPath": ["x"]})


def surrogate_files(sb):
    """Text fields holding a lone surrogate escape (a valid JSON file that Python decodes to an unencodable str)."""
    s = lone_surrogate_json()
    mkt = sb.plugins / "marketplaces" / "m1"
    write_bytes(mkt / ".claude-plugin" / "marketplace.json",
                '{"name": "m1", "plugins": [{"name": "p1", "source": "./plugins/p1", "category": %s,'
                ' "description": %s}]}' % (s, s))
    write_bytes(mkt / "plugins" / "p1" / ".claude-plugin" / "plugin.json", '{"name": "p1", "description": %s}' % s)
    write_skill(mkt / "plugins" / "p1" / "skills", "walrus-s", description="Walrus surrogate.")
    write_json(sb.plugins / "known_marketplaces.json", {"m1": {"installLocation": str(mkt)}})
    write_bytes(sb.plugins / "plugin-catalog-cache.json",
                '{"version": 1, "catalog": {"plugins": {"walrus-p9@m1": {"marketplace_entry": {"name": "walrus-p9",'
                ' "description": %s, "category": %s}}}}}' % (s, s))


class KatalogIndeksle(ScriptTestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def test_empty_machine(self):
        r = self.sb.run("katalog_indeksle.py", "--search", "walrus", "--no-write")
        self.assertRan(r)
        self.assertIn("SEARCH 'walrus' -> 0 plugin(s)", r.lines)

    def test_search_and_write(self):
        official_catalog(self.sb)
        out = self.sb.path("kout")
        r = self.sb.run("katalog_indeksle.py", "--search", "walrus", "--out", out)
        self.assertRan(r)
        self.assertIn("SEARCH 'walrus' -> 3 plugin(s)", r.lines)
        self.assertTrue([ln for ln in r.lines if ln.startswith("- walrus-tool@claude-plugins-official | installs=50 ")],
                        r.describe())
        idx = json.loads((out / "03-katalog-indeksi.json").read_text(encoding="utf-8"))
        self.assertIsInstance(idx, dict)
        self.assertTrue((out / "03-katalog-ozeti.md").is_file())

    def test_broken_inputs(self):
        sb = self.sb
        write_bytes(sb.plugins / "plugin-catalog-cache.json", b"\xff\xfe not json")
        write_bytes(sb.plugins / "installed_plugins.json", '{"version": 2, "plugins": [1, 2]}')
        write_bytes(sb.plugins / "known_marketplaces.json", '{"x": 5, "y": {"installLocation": 7}}')
        write_bytes(sb.config / "settings.json", '{"enabledPlugins": "yes"}')
        r = sb.run("katalog_indeksle.py", "--search", "walrus", "--no-write")
        self.assertRan(r)

    def test_out_inside_the_skill_folder_is_refused(self):
        target = SKILL_FOLDER / "x-test-out"
        r = self.sb.run("katalog_indeksle.py", "--out", target)
        self.assertRan(r, 2)
        self.assertFalse(target.exists())

    def test_fields_of_unexpected_types(self):
        odd_shapes(self.sb)
        out = self.sb.path("kout")
        r = self.sb.run("katalog_indeksle.py", "--search", "walrus", "--out", out)
        self.assertRan(r)
        self.assertIn("SEARCH 'walrus' -> 0 plugin(s)", r.lines)
        self.assertTrue([ln for ln in r.lines if ln.startswith("- (clone-only, not published) plugins/lonely")],
                        r.describe())
        idx = json.loads((out / "03-katalog-indeksi.json").read_text(encoding="utf-8"))
        installs = dict((p["id"], p["unique_installs"]) for p in idx["plugins"])
        self.assertEqual(installs, {"p-int@m1": None, "p-list@m1": None, "q@m1": None, "r@m1": 12,
                                    "p-local@m1": None, "p-gh@m1": None}, "non-numeric / infinite -> None")
        for p in idx["plugins"]:
            with self.subTest(plugin=p["id"]):
                self.assertIsInstance(p["source_repo"], str)
                self.assertIsNone(p["homepage"])
        r = self.sb.run("katalog_indeksle.py", "--search", "p-", "--no-write")
        self.assertRan(r)
        self.assertIn("SEARCH 'p-' -> 4 plugin(s)", r.lines)

    def test_lone_surrogate_in_a_json_file(self):
        surrogate_files(self.sb)
        out = self.sb.path("kout")
        r = self.sb.run("katalog_indeksle.py", "--search", "walrus", "--out", out)
        self.assertRan(r)
        self.assertIn("SEARCH 'walrus' -> 2 plugin(s)", r.lines)
        self.assertIn("x?y", (out / "03-katalog-indeksi.json").read_text(encoding="utf-8"))

    def test_hidden_characters_are_stripped_and_git_fields_are_gone(self):
        sb = self.sb
        mkt = sb.plugins / "marketplaces" / "m1"
        two = "walrus" + zw(1) + "two"
        write_json(mkt / ".claude-plugin" / "marketplace.json", {"name": "m1", "plugins": [
            {"name": "walrus-hid", "source": "./plugins/walrus-hid",
             "description": "Walrus " + zw(9) + chr(0x202E) + "tool."},
            {"name": two, "source": "./plugins/" + two}]})
        write_skill(mkt / "plugins" / "walrus-hid" / "skills", "walrus-s", description="Walrus" + zw(3) + " skill.")
        write_skill(mkt / "plugins" / two / "skills", "walrus" + zw(1) + "s2", description="Walrus second.")
        write_json(sb.plugins / "known_marketplaces.json", {"m1": {"installLocation": str(mkt)}})
        (mkt / ".git").mkdir()                      # a clone: its HEAD is not read by starting git any more
        out = sb.path("kout")
        r = sb.run("katalog_indeksle.py", "--search", "walrus", "--out", out)
        self.assertRan(r)
        self.assertEqual(invisible_chars(r.text.replace("\r\n", "\n")), [], r.describe())   # Windows console: CRLF
        self.assertIn("GIZLI-KARAKTER(10)", r.text, r.describe())
        self.assertIn("walrus?two@m1", r.text, "a hidden character in a name shows as '?' (print wrapper)")
        md = (out / "03-katalog-ozeti.md").read_text(encoding="utf-8")
        self.assertEqual(invisible_chars(md), [])
        self.assertNotIn("clone HEAD", md)
        idx = json.loads((out / "03-katalog-indeksi.json").read_text(encoding="utf-8"))
        self.assertNotIn("git", idx["meta"]["marketplaces"]["m1"])

    def test_local_scope_enablement(self):
        """enabledPlugins merged like Claude Code: user < <cwd>/.claude/settings.json < settings.local.json."""
        official_catalog(self.sb)
        write_json(self.sb.config / "settings.json", {"enabledPlugins": {"walrus-popular@claude-plugins-official": True}})
        write_json(self.sb.work / ".claude" / "settings.local.json", {"enabledPlugins": {
            "walrus-tool@claude-plugins-official": True, "walrus-popular@claude-plugins-official": False}})
        out = self.sb.path("kout")
        r = self.sb.run("katalog_indeksle.py", "--out", out)
        self.assertRan(r)
        idx = json.loads((out / "03-katalog-indeksi.json").read_text(encoding="utf-8"))
        self.assertEqual(idx["meta"]["enabled_plugin_ids"], ["walrus-tool@claude-plugins-official"])

    def test_bad_today_is_exit_2(self):
        r = self.sb.run("katalog_indeksle.py", "--today", "10/10/2026", "--no-write")
        self.assertRan(r, 2)
        self.assertIn("--today must be YYYY-MM-DD", r.errtext)


class SkillEnvanteri(ScriptTestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def test_inventory_of_a_synthetic_machine(self):
        sb = self.sb
        write_skill(sb.user_skills, "inv-user", description="Inventory user skill.")
        write_skill(sb.work / ".claude" / "skills", "inv-project", description="Inventory project skill.")
        write_bytes(sb.user_skills / "inv-broken" / "SKILL.md", b"---\nname: \xff\xfe\n")
        out = sb.path("eout")
        r = sb.run("skill_envanteri.py", "--out", out)
        self.assertRan(r)
        entries = json.loads((out / "02-skill-envanteri.json").read_text(encoding="utf-8"))
        names = sorted(e["name"] for e in entries if isinstance(e, dict))
        self.assertIn("inv-user", names)
        self.assertIn("inv-project", names)
        self.assertEqual(len(entries), 3, names)
        summary = json.loads((out / "02-skill-envanteri-ozet.json").read_text(encoding="utf-8"))
        home = os.path.normcase(os.path.realpath(str(sb.home)))
        for root in summary["roots"]:
            if root["label"] in ("project", "project-ancestor"):
                p = os.path.normcase(os.path.realpath(root["path"]))
                with self.subTest(root=root["path"]):
                    self.assertTrue(p.startswith(home + os.sep), "project roots stay below the home folder")

    def test_claude_code_load_rules(self):
        """Same rules as skill_ara.py: local-scope enablement, only the live version folder, one-level user skills."""
        sb = self.sb
        old = sb.plugins / "cache" / "mkt" / "plug" / "0.9.0"
        new = sb.plugins / "cache" / "mkt" / "plug" / "1.0.0"
        for d, name in ((old, "inv-old"), (new, "inv-new")):
            write_json(d / ".claude-plugin" / "plugin.json", {"name": "plug"})
            write_skill(d / "skills", name, description="Inventory plugin skill.")
        write_json(sb.plugins / "installed_plugins.json", {"version": 2, "plugins": {
            "plug@mkt": [{"scope": "local", "projectPath": str(sb.work), "installPath": str(new), "version": "1.0.0"}]}})
        write_json(sb.work / ".claude" / "settings.local.json", {"enabledPlugins": {"plug@mkt": True}})
        write_skill(sb.user_skills / "my-collection" / "skills", "inv-deep", description="Nested skill.")
        out = sb.path("eout")
        r = sb.run("skill_envanteri.py", "--out", out)
        self.assertRan(r)
        entries = json.loads((out / "02-skill-envanteri.json").read_text(encoding="utf-8"))
        tool = dict((e["name"], e.get("skill_tool_name")) for e in entries)
        self.assertEqual(tool.get("inv-new"), "plug:inv-new", entries)
        for name in ("inv-old", "inv-deep"):         # an update left 0.9.0 behind; a nested SKILL.md is not loaded
            with self.subTest(name=name):
                self.assertIn(name, tool)
                self.assertIsNone(tool[name])

    def test_cowork_codex_and_the_desktop_config_are_not_listed(self):
        sb = self.sb
        write_skill(sb.home / ".codex" / "skills", "codex-owl", description="Owl codex.")
        sched = sb.home / "Claude" / "Scheduled"
        write_skill(sched, "task-owl", description="Owl task.")
        lams = sb.desktop / "local-agent-mode-sessions"
        write_json(lams / "acc" / "org" / "scheduled-tasks.json", {"scheduledTasks": [
            {"filePath": str(sched / "task-owl" / "SKILL.md"), "enabled": True, "lastRunAt": "2026-10-01"}]})
        write_skill(lams / "acc" / "org" / "local_s1" / "uploads", "upload-owl", description="Owl upload.")
        write_json(sb.desktop / "claude_desktop_config.json", {"coworkUserFilesPath": str(sb.home / "Claude"),
                                                               "mcpServers": {"x": {"env": {"TOKEN": "sekret-canary-1"}}}})
        out = sb.path("eout")
        r = sb.run("skill_envanteri.py", "--out", out)
        self.assertRan(r)
        text = r.text + "".join((out / f).read_text(encoding="utf-8")
                                for f in ("02-skill-envanteri.json", "02-skill-envanteri-ozet.json"))
        for word in ("codex-owl", "task-owl", "upload-owl", "coworkUserFilesPath", "claude_desktop_config"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)
        r = sb.run("skill_envanteri.py", "--out", out, "--extra-root", sb.home / ".codex")
        self.assertRan(r)
        self.assertIn("codex-owl", (out / "02-skill-envanteri.json").read_text(encoding="utf-8"),
                      "an extra folder is still scanned when asked for")

    def test_printed_paths_show_hidden_characters(self):
        sb = self.sb
        write_bytes(sb.user_skills / ("owl" + zw(1) + "broken") / "SKILL.md", b"---\nname: \xff\xfe\n")
        r = sb.run("skill_envanteri.py", "--out", sb.path("eout"))
        self.assertRan(r)
        self.assertEqual(invisible_chars(r.text.replace("\r\n", "\n")), [], r.describe())
        self.assertIn("owl?broken", r.text, r.describe())

    def test_home_skills_are_listed_once(self):
        sb = self.sb
        write_skill(sb.user_skills, "inv-once", description="Listed once.")
        out = sb.path("eout")
        r = sb.run("skill_envanteri.py", "--out", out, "--project-dir", sb.home, env=sb.env(CLAUDE_CONFIG_DIR=None))
        self.assertRan(r)
        entries = json.loads((out / "02-skill-envanteri.json").read_text(encoding="utf-8"))
        self.assertEqual([e["name"] for e in entries], ["inv-once"])

    def test_out_inside_the_skill_folder_is_refused(self):
        target = SKILL_FOLDER / "x-test-out"
        r = self.sb.run("skill_envanteri.py", "--out", target)
        self.assertRan(r, 2)
        self.assertFalse(target.exists())

    def test_fields_of_unexpected_types(self):
        """A marketplace 'source' that is a number or a list, 'scheduledTasks' that is not a list, manifests of the
        wrong shape: no traceback, every SKILL.md still listed."""
        odd_shapes(self.sb)
        out = self.sb.path("eout")
        r = self.sb.run("skill_envanteri.py", "--out", out)
        self.assertRan(r)
        entries = json.loads((out / "02-skill-envanteri.json").read_text(encoding="utf-8"))
        names = sorted(e["name"] for e in entries)
        for name in ("walrus-a", "walrus-b", "walrus-r", "walrus-d", "a"):
            self.assertIn(name, names)
        remote = [e for e in entries if e["root_label"] == "marketplace-catalog-remote"]
        self.assertEqual([(e["plugin"], e["catalog_source"]) for e in remote], [("p-int", None)])
        local = [e for e in entries if e["name"] == "walrus-a"][0]
        self.assertEqual(local["catalog_source"], ["url"])

    def test_lone_surrogate_in_a_json_file(self):
        surrogate_files(self.sb)
        out = self.sb.path("eout")
        r = self.sb.run("skill_envanteri.py", "--out", out)
        self.assertRan(r)
        text = (out / "02-skill-envanteri.json").read_text(encoding="utf-8")
        self.assertIn('"catalog_category": "x?y"', text)

    def test_junction_cycle_without_isjunction(self):
        """Windows, Python < 3.12 (no os.path.isjunction; the run deletes it): a junction cycle is not followed."""
        sb = self.sb
        write_skill(sb.user_skills, "cycle-owl", description="Cycleowl helper.")
        make_junction(self, sb.user_skills, sb.user_skills / "loop")
        make_junction(self, sb.user_skills / "cycle-owl", sb.user_skills / "cycle-owl" / "back")
        for label, code in (("isjunction", None), ("no isjunction", WITHOUT_ISJUNCTION)):
            with self.subTest(label):
                out = sb.path("eout-" + label.replace(" ", "-"))
                r = (sb.run("skill_envanteri.py", "--out", out) if code is None
                     else sb.run_code(code, SCRIPTS / "skill_envanteri.py", "--out", out))
                self.assertRan(r)
                entries = json.loads((out / "02-skill-envanteri.json").read_text(encoding="utf-8"))
                self.assertEqual([e["name"] for e in entries], ["cycle-owl"])


if __name__ == "__main__":
    unittest.main()
