"""Where skill_ara.py and skill_envanteri.py look for the Claude desktop app's data (desktop_data_dir(), one text in
both scripts): $CLAUDE_DESKTOP_DATA_DIR when set, as is; on Windows the first of %APPDATA%/Claude,
%LOCALAPPDATA%/Claude-Data/<id> (of several, the one whose local-agent-mode-sessions was modified last) and
%LOCALAPPDATA%/Packages/Claude_<suffix>/LocalCache/Roaming/Claude that holds a local-agent-mode-sessions folder,
else %APPDATA%/Claude. The claude.ai plugin caches (rpm_dirs(), one text in both scripts) are read from both layouts:
<desktop>/rpm/<acct8>/<org8> (observed 2026-10-22) and <desktop>/local-agent-mode-sessions/<acct>/<org>/rpm.
Synthetic trees only: the sandbox points APPDATA and LOCALAPPDATA into a temporary folder."""
from __future__ import annotations

import glob
import json
import os
import time
import types
import unittest
from unittest import mock

from sleuth_testlib import (POSIX, Sandbox, ScriptTestCase, helper_sources, tier_counts, write_bytes, write_json,
                            write_skill)

LAMS = "local-agent-mode-sessions"
WINDOWS_ONLY = unittest.skipIf(POSIX, "the Windows desktop data locations (a Windows-only branch)")
NEW_RPM = ("rpm", "acct0001", "org00001")         # <desktop>/rpm/<acct8>/<org8> (observed 2026-10-22), synthetic


def write_rpm(rpm, skill, plugin="heronplug", pref="available", pid="plugin_1", manifest_name=None):
    """One claude.ai plugin cache folder: manifest.json in the shape observed on 2026-10-22 (top-level lastUpdated;
    per plugin id, name, displayName, marketplaceId, marketplaceName, installedBy, installationPreference, updatedAt,
    updatedAtVerified; synthetic values) and <pid>/ holding one skill. pref None: the plugin is not in the manifest.
    manifest_name: the manifest's "name" (some entries carry a directory id there; plugin.json names the plugin)."""
    rows = [] if pref is None else [{
        "id": pid, "name": manifest_name or plugin, "updatedAt": "2026-10-22T00:00:00.000000Z",
        "updatedAtVerified": True, "displayName": plugin.title(), "marketplaceId": "mkt-0001",
        "marketplaceName": "heron-market", "installedBy": "user", "installationPreference": pref}]
    mani = rpm / "manifest.json"
    old = json.loads(mani.read_text(encoding="utf-8"))["plugins"] if mani.is_file() else []
    write_json(mani, {"lastUpdated": 1761091200000, "plugins": old + rows})
    write_json(rpm / pid / ".claude-plugin" / "plugin.json", {"name": plugin, "version": "1.0.0"})
    write_skill(rpm / pid / "skills", skill, description="Heron %s claude.ai plugin skill." % skill)
    return rpm


def desktop_tree(data_dir, tag, rpm_at_data=False):
    """<data_dir>/local-agent-mode-sessions with one desktop-bundled skill (skills-plugin/<org>/<acct>) and one
    claude.ai plugin skill, both named after tag. The plugin cache is <data_dir>/rpm/<acct8>/<org8> when rpm_at_data
    (the layout observed on 2026-10-22: local-agent-mode-sessions/<acct>/<org> then holds only session files), else
    local-agent-mode-sessions/<acct>/<org>/rpm. -> the local-agent-mode-sessions folder."""
    lams = data_dir / LAMS
    bundle = lams / "skills-plugin" / "org-1" / "acct-1"
    write_json(bundle / ".claude-plugin" / "plugin.json", {"name": "anthropic-skills"})
    write_json(bundle / "manifest.json", {"skills": [{"name": "heron-%s-d" % tag, "enabled": True}]})
    write_skill(bundle / "skills", "heron-%s-d" % tag, description="Heron %s desktop bundle skill." % tag)
    if rpm_at_data:
        write_json(lams / "acct-1" / "org-1" / "session-files.json", {})
        write_rpm(data_dir.joinpath(*NEW_RPM), "heron-%s-r" % tag)
    else:
        write_rpm(lams / "acct-1" / "org-1" / "rpm", "heron-%s-r" % tag)
    return lams


def left_marker(folder):
    """An old data folder the app moved away from: only an empty '.user-data-left.<id>' marker file remains."""
    write_bytes(folder / ".user-data-left.claude_testid", b"")


def set_mtime(path, when):
    os.utime(str(path), (when, when))


def same(a, b):
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


class Base(ScriptTestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        self.roaming = self.sb.appdata / "Claude"
        self.data = self.sb.localappdata / "Claude-Data"
        self.msix = self.sb.localappdata / "Packages" / "Claude_testsuffix" / "LocalCache" / "Roaming" / "Claude"

    def chosen(self, **env):
        """skill_ara.py --stats --refresh, without $CLAUDE_DESKTOP_DATA_DIR unless env sets it.
        -> (the local-agent-mode-sessions folder the index used, {tier: count}, the run)."""
        env.setdefault("CLAUDE_DESKTOP_DATA_DIR", None)
        r = self.sb.skill_ara("--stats", "--refresh", env=self.sb.env(**env))
        self.assertRan(r)
        lams = json.loads(self.sb.cache.read_text(encoding="utf-8"))["roots"]["lams"]
        return lams, tier_counts(r.text), r

    def assertUses(self, lams, data_dir):
        self.assertTrue(same(lams, data_dir / LAMS), "index used %s, expected %s" % (lams, data_dir / LAMS))


@WINDOWS_ONLY
class SkillAraWindows(Base):
    def test_claude_data_folder_alone(self):
        """The layout observed on 2026-10-22: the data lives in %LOCALAPPDATA%/Claude-Data/<id> (claude.ai plugins in
        its rpm/<acct8>/<org8>), the two old folders hold only the marker file. Both desktop tiers are indexed from
        there and callable."""
        desktop_tree(self.data / "claude_testid", "new", rpm_at_data=True)
        write_bytes(self.data / "README.txt", b"not a data folder\n")
        left_marker(self.roaming)
        left_marker(self.msix)
        lams, counts, r = self.chosen()
        self.assertUses(lams, self.data / "claude_testid")
        self.assertEqual(counts.get("desktop-bundle"), 1, r.describe())
        self.assertEqual(counts.get("claudeai-plugin"), 1, r.describe())
        r = self.sb.skill_ara("--query", "heron", "--installed-only", env=self.sb.env(CLAUDE_DESKTOP_DATA_DIR=None))
        self.assertRan(r)
        self.assertIn("Skill(anthropic-skills:heron-new-d)", r.text)
        self.assertIn("Skill(heronplug:heron-new-r)", r.text)

    def test_appdata_comes_first(self):
        desktop_tree(self.roaming, "roam")
        new = desktop_tree(self.data / "claude_testid", "new")
        set_mtime(new, time.time() + 60)              # a newer Claude-Data folder does not outrank %APPDATA%/Claude
        lams, counts, r = self.chosen()
        self.assertUses(lams, self.roaming)
        self.assertEqual(counts.get("desktop-bundle"), 1, r.describe())

    def test_most_recently_modified_claude_data_folder_wins(self):
        a = desktop_tree(self.data / "claude_aaa", "a")
        b = desktop_tree(self.data / "claude_bbb", "b")
        now = time.time()
        set_mtime(a, now - 3600)
        set_mtime(b, now)
        self.assertUses(self.chosen()[0], self.data / "claude_bbb")
        set_mtime(a, now + 60)
        self.assertUses(self.chosen()[0], self.data / "claude_aaa")

    def test_packages_folder_comes_last(self):
        desktop_tree(self.msix, "msix")
        left_marker(self.roaming)
        lams, counts, r = self.chosen()
        self.assertUses(lams, self.msix)
        self.assertEqual(counts.get("claudeai-plugin"), 1, r.describe())
        desktop_tree(self.data / "claude_testid", "new")
        self.assertUses(self.chosen()[0], self.data / "claude_testid")

    def test_nothing_found_falls_back_to_appdata(self):
        left_marker(self.roaming)
        left_marker(self.msix)
        self.sb.mk("localappdata", "Claude-Data", "claude_testid", "claude-code")   # a data folder without sessions
        lams, counts, r = self.chosen()
        self.assertUses(lams, self.roaming)
        self.assertNotIn("desktop-bundle", counts, r.describe())
        self.assertNotIn("claudeai-plugin", counts, r.describe())

    def test_missing_appdata_variables_use_the_home_folder(self):
        """No APPDATA / LOCALAPPDATA: <home>/AppData/Roaming and <home>/AppData/Local, as before."""
        lams, _, _ = self.chosen(APPDATA=None, LOCALAPPDATA=None)
        self.assertUses(lams, self.sb.home / "AppData" / "Roaming" / "Claude")
        desktop_tree(self.sb.home / "AppData" / "Local" / "Claude-Data" / "claude_testid", "home")
        lams, counts, r = self.chosen(APPDATA=None, LOCALAPPDATA=None)
        self.assertUses(lams, self.sb.home / "AppData" / "Local" / "Claude-Data" / "claude_testid")
        self.assertEqual(counts.get("desktop-bundle"), 1, r.describe())


class EveryPlatform(Base):
    def test_the_variable_decides_as_is(self):
        """$CLAUDE_DESKTOP_DATA_DIR wins over every default folder, even one without local-agent-mode-sessions."""
        desktop_tree(self.sb.desktop, "var")
        desktop_tree(self.roaming, "roam")
        desktop_tree(self.data / "claude_testid", "new")
        desktop_tree(self.msix, "msix")
        lams, counts, r = self.chosen(CLAUDE_DESKTOP_DATA_DIR=self.sb.desktop)
        self.assertUses(lams, self.sb.desktop)
        self.assertEqual(counts.get("desktop-bundle"), 1, r.describe())
        empty = self.sb.mk("empty-desktop")
        lams, counts, r = self.chosen(CLAUDE_DESKTOP_DATA_DIR=empty)
        self.assertUses(lams, empty)
        self.assertNotIn("desktop-bundle", counts, r.describe())

    def test_one_rule_in_both_scripts(self):
        """desktop_data_dir() and rpm_dirs() are one text in skill_ara.py and skill_envanteri.py; claude_config_dir()
        and plugins_root() are one text in those two and katalog_indeksle.py."""
        ara = helper_sources("skill_ara.py")
        for script, names in (("skill_envanteri.py", ("desktop_data_dir", "rpm_dirs", "claude_config_dir",
                                                      "plugins_root")),
                              ("katalog_indeksle.py", ("claude_config_dir", "plugins_root"))):
            other = helper_sources(script)
            for name in names:
                with self.subTest(script=script, function=name):
                    self.assertIn(name, other)
                    self.assertEqual(other[name], ara[name])

    def test_windows_order_on_any_platform(self):
        """The Windows branch run in this process with sys.platform faked, so CI on macOS / Linux covers it too."""
        ns = {"os": os, "glob": glob, "sys": types.SimpleNamespace(platform="win32")}
        exec(compile(helper_sources("skill_ara.py")["desktop_data_dir"], "skill_ara.py:desktop_data_dir", "exec"), ns)
        env = {"APPDATA": str(self.sb.appdata), "LOCALAPPDATA": str(self.sb.localappdata)}

        def run():
            with mock.patch.dict(os.environ, env):
                os.environ.pop("CLAUDE_DESKTOP_DATA_DIR", None)
                return ns["desktop_data_dir"]()
        self.assertTrue(same(run(), self.roaming), "nothing found: %APPDATA%/Claude")
        set_mtime(desktop_tree(self.msix, "msix"), time.time() - 60)
        self.assertTrue(same(run(), self.msix))
        old = desktop_tree(self.data / "claude_old", "old")
        new = desktop_tree(self.data / "claude_new", "new")
        set_mtime(old, time.time() - 3600)
        set_mtime(new, time.time())
        self.assertTrue(same(run(), self.data / "claude_new"))
        desktop_tree(self.roaming, "roam")
        self.assertTrue(same(run(), self.roaming))
        with mock.patch.dict(os.environ, {"CLAUDE_DESKTOP_DATA_DIR": "X:/as-is"}):
            self.assertEqual(ns["desktop_data_dir"](), "X:/as-is")


class RpmLayouts(ScriptTestCase):
    """claude.ai plugin caches on every platform ($CLAUDE_DESKTOP_DATA_DIR = the sandbox's desktop folder): the new
    layout <desktop>/rpm/<acct8>/<org8> alone, the old <desktop>/local-agent-mode-sessions/<acct>/<org>/rpm alone,
    both together; a skill is callable as Skill(<plugin>:<skill>) only when its plugin's manifest row says
    installationPreference "available"; a cache that appears or changes rebuilds the index."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        self.new = self.sb.desktop.joinpath(*NEW_RPM)
        self.old = self.sb.desktop / LAMS / "acct-2" / "org-2" / "rpm"

    def stats(self):
        r = self.sb.skill_ara("--stats", "--refresh")
        self.assertRan(r)
        return tier_counts(r.text)

    def query(self, *args):
        r = self.sb.skill_ara("--query", "heron", "--top", "20", *args)
        self.assertRan(r)
        return r

    def test_new_location_alone(self):
        """The plugin name comes from plugin.json; the manifest's "name" may be a directory id."""
        write_rpm(self.new, "heron-new-r", manifest_name="dir-entry-0001")
        self.assertEqual(self.stats().get("claudeai-plugin"), 1)
        r = self.query("--installed-only")
        self.assertIn("Skill(heronplug:heron-new-r)", r.text, r.describe())
        r = self.sb.skill_ara("--show", "heron-new-r")
        self.assertRan(r)
        self.assertIn('"invoke": "heronplug:heron-new-r"', r.text, r.describe())
        self.assertIn('"marketplace": "heron-market"', r.text, r.describe())

    def test_callable_only_when_available(self):
        write_rpm(self.new, "heron-on-r")
        write_rpm(self.new, "heron-off-r", plugin="heronoff", pref="not-available", pid="plugin_2")
        write_rpm(self.new, "heron-gone-r", plugin="herongone", pref=None, pid="plugin_3")
        self.assertEqual(self.stats().get("claudeai-plugin"), 3)
        r = self.query("--installed-only")
        self.assertIn("Skill(heronplug:heron-on-r)", r.text, r.describe())
        self.assertNotIn("heronoff", r.text, r.describe())
        self.assertNotIn("herongone", r.text, r.describe())
        r = self.query()
        self.assertEqual(r.text.count("NOT USABLE -> enable the plugin on claude.ai"), 2, r.describe())

    def test_old_layout_alone(self):
        """Before the move: <desktop>/local-agent-mode-sessions/<acct>/<org>/rpm; an rpm folder below skills-plugin/
        (the desktop bundle) is never a plugin cache."""
        write_rpm(self.old, "heron-old-r")
        write_rpm(self.sb.desktop / LAMS / "skills-plugin" / "org-3" / "rpm", "heron-bundle-r", plugin="heronbundle")
        self.assertEqual(self.stats().get("claudeai-plugin"), 1)
        r = self.query("--installed-only")
        self.assertIn("Skill(heronplug:heron-old-r)", r.text, r.describe())
        self.assertNotIn("heronbundle", r.text, r.describe())

    def test_both_locations_together(self):
        """Both caches are read; a plugin found in both is one hit (the copies share the invoke name)."""
        write_rpm(self.new, "heron-new-r")
        write_rpm(self.new, "heron-twin-r", plugin="herontwin", pid="plugin_2")
        write_rpm(self.old, "heron-old-r", plugin="heronold", pid="plugin_3")
        write_rpm(self.old, "heron-twin-r", plugin="herontwin", pid="plugin_2")
        self.assertEqual(self.stats().get("claudeai-plugin"), 4)
        r = self.query("--installed-only")
        for inv in ("heronplug:heron-new-r", "heronold:heron-old-r", "herontwin:heron-twin-r"):
            with self.subTest(invoke=inv):
                self.assertEqual(r.text.count("Skill(%s)" % inv), 1, r.describe())

    def test_a_cache_that_appears_or_changes_rebuilds_the_index(self):
        write_rpm(self.old, "heron-old-r")
        self.assertRan(self.sb.skill_ara("--stats"))
        self.assertNotIn("rebuilt:", self.query().lines[0])
        write_rpm(self.new, "heron-new-r", plugin="heronnew")
        r = self.query("--installed-only")
        self.assertIn("rebuilt:fingerprint", r.lines[0], r.describe())
        self.assertIn("Skill(heronnew:heron-new-r)", r.text, r.describe())
        self.assertNotIn("rebuilt:", self.query().lines[0])
        set_mtime(self.new / "manifest.json", time.time() + 120)
        self.assertIn("rebuilt:fingerprint", self.query().lines[0])

    def test_inventory_reads_both_layouts(self):
        write_rpm(self.new, "heron-new-r", manifest_name="dir-entry-0001")
        write_rpm(self.new, "heron-off-r", plugin="heronoff", pref="not-available", pid="plugin_2")
        write_rpm(self.old, "heron-old-r", plugin="heronold", pid="plugin_3")
        out = self.sb.path("eout")
        r = self.sb.run("skill_envanteri.py", "--out", out)
        self.assertRan(r)
        entries = json.loads((out / "02-skill-envanteri.json").read_text(encoding="utf-8"))
        rows = dict((e["name"], e) for e in entries if e.get("source_kind") == "claudeai-plugin")
        self.assertEqual(sorted(rows), ["heron-new-r", "heron-off-r", "heron-old-r"], entries)
        self.assertEqual(rows["heron-new-r"]["skill_tool_name"], "heronplug:heron-new-r")
        self.assertEqual(rows["heron-old-r"]["skill_tool_name"], "heronold:heron-old-r")
        self.assertIs(rows["heron-off-r"]["enabled"], False)
        self.assertIsNone(rows["heron-off-r"]["skill_tool_name"])
        summary = json.loads((out / "02-skill-envanteri-ozet.json").read_text(encoding="utf-8"))
        root = [x for x in summary["roots"] if x["label"] == "claudeai-plugin"]
        self.assertEqual(len(root), 1, summary["roots"])
        self.assertTrue(root[0]["exists"], root)


@WINDOWS_ONLY
class SkillEnvanteriWindows(Base):
    def test_inventory_uses_the_same_rule(self):
        home = self.data / "claude_testid"
        desktop_tree(home, "inv", rpm_at_data=True)
        left_marker(self.roaming)
        out = self.sb.path("eout")
        r = self.sb.run("skill_envanteri.py", "--out", out, env=self.sb.env(CLAUDE_DESKTOP_DATA_DIR=None))
        self.assertRan(r)
        entries = json.loads((out / "02-skill-envanteri.json").read_text(encoding="utf-8"))
        kinds = dict((e["name"], e["source_kind"]) for e in entries)
        self.assertEqual(kinds.get("heron-inv-d"), "desktop-bundled", entries)
        self.assertEqual(kinds.get("heron-inv-r"), "claudeai-plugin", entries)
        for e in entries:
            if e["name"].startswith("heron-inv-"):
                with self.subTest(name=e["name"]):
                    path = os.path.normcase(os.path.normpath(e["path"]))
                    below = home / (LAMS if e["source_kind"] == "desktop-bundled" else "rpm")
                    self.assertTrue(path.startswith(os.path.normcase(str(below)) + os.sep), e["path"])


if __name__ == "__main__":
    unittest.main()
