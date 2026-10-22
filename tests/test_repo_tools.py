"""The repository itself: the two plugins ship byte-identical scripts, the script READMEs name the script
versions and trust lines, the SKILL.md frontmatter keeps its two keys and its byte-frozen description, and
tools/build_yayin.py --check passes here and fails on what it must catch (on synthetic copies)."""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import time
import unittest
import zipfile
from unittest import mock

from sleuth_testlib import (EDITIONS, PLUGIN_SCRIPTS, REPO, SCRIPT_NAMES, SCRIPTS, T4_TRUST, T5_TRUST, Sandbox,
                            script_version)

SHIPPED_SAME = SCRIPT_NAMES + ("builtins.json",)


def twin_scripts():
    """scripts/ of the other edition next to the scripts under test: the other plugin when SCRIPTS is a plugin copy,
    <source-root>/<other edition>/scripts when it is a source edition; None when there is none."""
    other = dict(zip(EDITIONS, reversed(EDITIONS))).get(SCRIPTS.parent.name)
    if other is None:
        return None
    if SCRIPTS == PLUGIN_SCRIPTS[SCRIPTS.parent.name].resolve():
        return PLUGIN_SCRIPTS[other]
    twin = SCRIPTS.parent.parent / other / "scripts"
    return twin.resolve() if twin.is_dir() else None


def readme_dirs():
    """The scripts under test and their twin edition: the READMEs that ship with the scripts being tested."""
    return [SCRIPTS] + [d for d in (twin_scripts(),) if d is not None]


def load_builder():
    spec = importlib.util.spec_from_file_location("build_yayin_under_test", str(REPO / "tools" / "build_yayin.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ShippedScripts(unittest.TestCase):
    def test_plugin_scripts_are_byte_identical(self):
        a, b = PLUGIN_SCRIPTS["skill-sleuth"], PLUGIN_SCRIPTS["skill-bulucu"]
        names_a = sorted(p.name for p in a.iterdir() if p.suffix == ".py" or p.name == "builtins.json")
        names_b = sorted(p.name for p in b.iterdir() if p.suffix == ".py" or p.name == "builtins.json")
        self.assertEqual(names_a, names_b)
        self.assertTrue(set(SHIPPED_SAME) <= set(names_a), names_a)
        for name in names_a:
            with self.subTest(file=name):
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())

    def test_scripts_under_test_match_their_other_edition(self):
        """With SKILL_SCRIPTS_DIR=<source-root>/<edition>/scripts: the other source edition must be the same."""
        twin = twin_scripts()
        if twin is None or twin in PLUGIN_SCRIPTS.values():
            self.skipTest("SKILL_SCRIPTS_DIR is not a source edition with its twin next to it")
        for name in SHIPPED_SAME:
            with self.subTest(file=name):
                self.assertEqual((SCRIPTS / name).read_bytes(), (twin / name).read_bytes())

    def test_builtins_sidecar_is_valid(self):
        data = json.loads((SCRIPTS / "builtins.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        self.assertTrue(data)
        for row in data:
            self.assertIsInstance(row.get("name"), str)
            self.assertIsInstance(row.get("description"), str)

    def test_readmes_name_the_script_versions(self):
        for d in readme_dirs():
            text = (d / "README.md").read_text(encoding="utf-8")
            for script, head in (("skill_ara.py", "skill_ara"), ("dis_kaynak_ara.py", "dis_kaynak_ara")):
                ver = (d / script).read_text(encoding="utf-8").split('VERSION = "', 1)[1].split('"', 1)[0]
                with self.subTest(readme=str(d.relative_to(d.parent.parent)), script=script):
                    self.assertIn("%s %s | " % (head, ver), text)

    def test_readmes_quote_the_trust_lines(self):
        for d in readme_dirs():
            text = (d / "README.md").read_text(encoding="utf-8")
            with self.subTest(readme=str(d.relative_to(d.parent.parent))):
                self.assertIn(T5_TRUST, text)
                self.assertIn(T4_TRUST, text)

    def test_no_script_starts_a_program(self):
        banned_modules = {"subprocess", "multiprocessing", "pty", "asyncio"}

        def banned_os(attr):
            return attr in ("system", "popen", "startfile", "fork", "forkpty") or attr.startswith(("exec", "spawn",
                                                                                                    "posix_spawn"))
        for name in SCRIPT_NAMES:
            tree = ast.parse((SCRIPTS / name).read_text(encoding="utf-8"))
            os_names = {"os"} | {a.asname for n in ast.walk(tree) if isinstance(n, ast.Import)
                                 for a in n.names if a.name == "os" and a.asname}
            bad = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    bad += [a.name for a in node.names if a.name.split(".")[0] in banned_modules]
                if isinstance(node, ast.ImportFrom):
                    if (node.module or "").split(".")[0] in banned_modules:
                        bad.append(node.module)
                    if node.module == "os":
                        bad += ["os." + a.name for a in node.names if banned_os(a.name)]
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in os_names \
                        and banned_os(node.attr):
                    bad.append("os." + node.attr)
            with self.subTest(script=name):
                self.assertEqual(bad, [])

    def test_no_script_reads_the_desktop_config(self):
        for name in SCRIPT_NAMES:
            with self.subTest(script=name):
                self.assertNotIn("claude_desktop_config", (SCRIPTS / name).read_text(encoding="utf-8"))

    def test_invisible_text_helpers_are_identical(self):
        def parts(script):
            text = (SCRIPTS / script).read_text(encoding="utf-8")
            out = {}
            for n in ast.parse(text).body:
                if isinstance(n, ast.FunctionDef) and n.name in ("clean", "hidden_count", "scrub"):
                    out[n.name] = ast.get_source_segment(text, n)
                if isinstance(n, ast.Assign) and any(getattr(x, "id", "") == "_INVIS" for x in n.targets):
                    out["_INVIS"] = ast.get_source_segment(text, n)
            return out
        base = parts("skill_ara.py")
        self.assertEqual(sorted(base), ["_INVIS", "clean", "hidden_count", "scrub"])
        for script in ("katalog_indeksle.py", "skill_envanteri.py"):
            with self.subTest(script=script):
                self.assertEqual(parts(script), base)
                tree = ast.parse((SCRIPTS / script).read_text(encoding="utf-8"))
                self.assertIn("print", [n.name for n in tree.body if isinstance(n, ast.FunctionDef)],
                              "every printed line goes through scrub()")

    def test_printed_reference_files_exist_in_each_edition(self):
        code = ("import importlib.util, sys\n"
                "spec = importlib.util.spec_from_file_location('dka', sys.argv[1])\n"
                "m = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(m)\n"
                "print(m.ref('hard7'))\n"
                "print(m.ref('review'))\n"
                "print(m.audit_verdict([{'status': 'fail', 'risk': 'HIGH'}])[-1])\n")
        sb = Sandbox()
        try:
            for scripts in readme_dirs():           # the scripts under test and their twin edition
                edition = scripts.parent.name
                r = sb.run_code(code, scripts / "dis_kaynak_ara.py")
                with self.subTest(edition=edition):
                    self.assertEqual(r.code, 0, r.describe())
                    hard7, review, verdict = r.lines[:3]
                    for pointer in (hard7.split(" ")[0], review.split(",")[0]):
                        self.assertTrue((scripts.parent / pointer).is_file(), pointer)
                    self.assertTrue(verdict.endswith(hard7), verdict)
                    self.assertEqual("guvenlik-kontrol-listesi.md" in hard7, edition == "skill-bulucu")
        finally:
            sb.close()

    def test_user_agent_is_quoted_in_the_disclosures(self):
        ua = re.search(r'^UA = "([^"]+)"', (SCRIPTS / "dis_kaynak_ara.py").read_text(encoding="utf-8"), re.M).group(1)
        docs = [REPO / "plugins" / e / "README.md" for e in EDITIONS]
        docs += [REPO / "plugins" / "skill-sleuth" / "skills" / "skill-sleuth" / "references" / "external-sources-details.md",
                 REPO / "plugins" / "skill-bulucu" / "skills" / "skill-bulucu" / "references" / "dis-kaynaklar-ayrinti.md"]
        for doc in docs:
            with self.subTest(doc=str(doc.relative_to(REPO))):
                self.assertIn(ua, doc.read_text(encoding="utf-8"))

    def test_versions_under_test(self):
        for script in ("skill_ara.py", "dis_kaynak_ara.py"):
            self.assertRegex(script_version(script) or "", r"^\d+\.\d+\.\d+$")


# SHA-256 of the 'description:' line of each edition's SKILL.md. The line is byte-frozen: the trigger evaluation
# was measured against exactly these bytes. Changing it means re-running that evaluation, then this table.
FROZEN_DESCRIPTION = {
    "skill-sleuth": "ce73db256fcc856acfcf228f6b0f6e51c15c0c85b20cd583721a24f6e20675c0",
    "skill-bulucu": "59322df2b195ee20ba85c2568d6e083a0636dbf3863bfd99d0cd87457895e3bb",
}


class FrozenFrontmatter(unittest.TestCase):
    def skill_files(self):
        out = [(e, REPO / "plugins" / e / "skills" / e / "SKILL.md") for e in EDITIONS]
        if SCRIPTS.parent.name in EDITIONS and (SCRIPTS.parent / "SKILL.md").is_file():
            out.append((SCRIPTS.parent.name, SCRIPTS.parent / "SKILL.md"))
        return out

    def test_frontmatter_keys_name_and_frozen_description(self):
        for edition, path in self.skill_files():
            raw = path.read_bytes()
            m = re.match(rb"\A---\n(.*?)\n---\n", raw, re.S)
            with self.subTest(skill=str(path.relative_to(path.parent.parent))):
                self.assertTrue(m, "frontmatter block at the top")
                lines = m.group(1).split(b"\n")
                keys = [ln.split(b":", 1)[0] for ln in lines if ln and not ln[:1].isspace()]
                self.assertEqual(keys, [b"name", b"description"])
                self.assertEqual(lines[0], b"name: " + edition.encode("ascii"))
                desc = [ln for ln in lines if ln.startswith(b"description:")][0]
                self.assertEqual(hashlib.sha256(desc).hexdigest(), FROZEN_DESCRIPTION[edition],
                                 "the description line is byte-frozen (re-run the trigger evaluation first)")


class BuildCheck(unittest.TestCase):
    """tools/build_yayin.py imported (no bytecode written), run in --check mode."""

    @classmethod
    def setUpClass(cls):
        cls.by = load_builder()
        cls.sb = Sandbox("sleuth-build-")
        cls.addClassCleanup(cls.sb.close)
        cls.nopat = str(cls.sb.path("no-private-patterns.txt"))      # does not exist: generic patterns only

    def build(self, *argv, **env):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = self.by.main([str(a) for a in argv])
            except SystemExit as exc:              # argparse usage errors
                code = exc.code
        return code, out.getvalue() + err.getvalue()

    def copy_repo(self, name):
        """A copy of the repository in the sandbox: <sandbox>/<name>/skill-sleuth (no sources next to it)."""
        dst = self.sb.path(name, "skill-sleuth")
        base = os.path.normcase(os.path.abspath(str(REPO)))
        common = shutil.ignore_patterns(".git", "__pycache__", "*.pyc")

        def ignore(d, names):                                   # build outputs: only the top-level dist/
            skip = set(common(d, names))
            if os.path.normcase(os.path.abspath(d)) == base:
                skip.add("dist")
            return skip
        shutil.copytree(str(REPO), str(dst), ignore=ignore)
        return dst

    def check(self, repo, *extra, **env):
        env.setdefault("YAYIN_PRIVATE_PATTERNS", self.nopat)
        return self.build("--check", "--repo", repo, *extra, **env)

    def assertFails(self, result, *needles):
        code, text = result
        self.assertEqual(code, 1, text)
        self.assertIn("RESULT: FAIL", text)
        for n in needles:
            self.assertIn(n, text)

    # -- the real repository ---------------------------------------------------------------------------------
    def test_check_passes_on_the_repository(self):
        code, text = self.build("--check", "--repo", REPO)
        self.assertEqual(code, 0, text)
        self.assertIn("RESULT: PASS (0 failure(s)", text)

    # -- synthetic copies --------------------------------------------------------------------------------------
    def test_clean_copy_passes_and_copies_nothing(self):
        repo = self.copy_repo("clean")
        before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))
        code, text = self.build("--repo", repo, YAYIN_PRIVATE_PATTERNS=self.nopat)
        self.assertEqual(code, 0, text)
        self.assertIn("CHECK (in-repo, automatic: no source folders next to the repository)", text)
        self.assertEqual(sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*")), before)

    def test_crlf_and_bom_fail(self):
        repo = self.copy_repo("crlf")
        p = repo / "README.md"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n", 3))
        q = repo / "SECURITY.md"
        q.write_bytes(b"\xef\xbb\xbf" + q.read_bytes())
        self.assertFails(self.check(repo), "README.md: CRLF", "SECURITY.md: BOM")

    def test_personal_data_fails(self):
        repo = self.copy_repo("personal")
        home_path = "C:" + "\\Users\\" + "someone\\.claude"     # assembled at run time: never in this file
        with (repo / "CHANGELOG.md").open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n- path %s\n" % home_path)
        self.assertFails(self.check(repo), "personal data pattern (whole tree)")

    def test_private_pattern_file_is_used(self):
        repo = self.copy_repo("private")
        pat = self.sb.path("private-patterns.txt")
        word = "zebra" + "corn"                                 # assembled at run time: never in this file
        pat.write_bytes(("# test\n%s-[0-9]+\n" % word).encode("ascii"))
        with (repo / "plugins" / "skill-sleuth" / "README.md").open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n%s-42\n" % word)
        self.assertFails(self.check(repo, YAYIN_PRIVATE_PATTERNS=str(pat)), "personal data pattern (whole tree)")
        self.assertEqual(self.check(repo)[0], 0, "without the pattern file the same tree passes")

    def test_version_mismatch_fails(self):
        repo = self.copy_repo("version")
        pj = repo / "plugins" / "skill-sleuth" / ".claude-plugin" / "plugin.json"
        data = json.loads(pj.read_text(encoding="utf-8"))
        data["version"] = "9.9.9"
        pj.write_bytes((json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        self.assertFails(self.check(repo), "version consistent (skill-sleuth)")

    def test_script_drift_between_plugins_fails(self):
        repo = self.copy_repo("drift")
        p = repo / "plugins" / "skill-bulucu" / "skills" / "skill-bulucu" / "scripts" / "skill_ara.py"
        p.write_bytes(p.read_bytes() + b"# drift\n")
        self.assertFails(self.check(repo), "scripts/skill_ara.py: differs")

    def test_stray_file_in_a_generated_skill_folder_fails(self):
        repo = self.copy_repo("stray")
        (repo / "plugins" / "skill-sleuth" / "skills" / "skill-sleuth" / "evals").mkdir()
        (repo / "plugins" / "skill-sleuth" / "skills" / "skill-sleuth" / "evals" / "evals.json").write_bytes(b"{}\n")
        self.assertFails(self.check(repo), "generated skill folder holds only SKILL.md, references/, scripts/")

    def test_size_cap_and_frontmatter_fail(self):
        repo = self.copy_repo("caps")
        sk = repo / "plugins" / "skill-bulucu" / "skills" / "skill-bulucu" / "SKILL.md"
        raw = sk.read_bytes()
        sk.write_bytes(raw.replace(b"\n---\n", b"\nextra-key: x\n---\n", 1) + b"x" * 17001 + b"\n")
        self.assertFails(self.check(repo), "size SKILL.md (body) (skill-bulucu)", "frontmatter keys (skill-bulucu)")

    def test_usage_errors(self):
        repo = self.copy_repo("usage")
        self.assertEqual(self.build("--check", "--dry-run", "--repo", repo)[0], 2)
        self.assertEqual(self.build("--repo", repo, "--source-root", self.sb.path("no-sources"),
                                    YAYIN_PRIVATE_PATTERNS=self.nopat)[0], 2)
        self.assertEqual(self.check(repo, "--zip", self.sb.path("z-bad"), SOURCE_DATE_EPOCH="soon")[0], 2)
        self.assertEqual(self.build("--zip", "--check", "--repo", repo, SOURCE_DATE_EPOCH="soon",
                                    YAYIN_PRIVATE_PATTERNS=self.nopat)[0], 2, "a bare --zip still validates the epoch")
        self.assertEqual(self.build("--check", "--repo", self.sb.path("missing-repo"))[0], 2)

    def test_zips_are_reproducible(self):
        repo = self.copy_repo("zips")
        z1, z2 = self.sb.path("z1"), self.sb.path("z2")
        code1, text1 = self.check(repo, "--zip", z1)
        time.sleep(1.1)                                         # a wall-clock dependency would show now
        code2, text2 = self.check(repo, "--zip", z2)
        self.assertEqual((code1, code2), (0, 0), text1 + text2)
        for name in EDITIONS:
            with self.subTest(zip=name):
                a, b = (z1 / ("%s.zip" % name)).read_bytes(), (z2 / ("%s.zip" % name)).read_bytes()
                self.assertEqual(a, b)
                with zipfile.ZipFile(str(z1 / ("%s.zip" % name))) as zf:
                    infos = zf.infolist()
                    self.assertTrue(infos)
                    self.assertEqual([i.filename for i in infos], sorted(i.filename for i in infos))
                    for i in infos:
                        self.assertTrue(i.filename.startswith(name + "/"), i.filename)
                        self.assertEqual(i.date_time, (1980, 1, 1, 0, 0, 0))
                        self.assertEqual(i.external_attr >> 16, 0o100644)
                    self.assertIn(name + "/SKILL.md", [i.filename for i in infos])
        code, _ = self.check(repo, "--zip", self.sb.path("z3"), SOURCE_DATE_EPOCH="1700000000")
        self.assertEqual(code, 0)
        with zipfile.ZipFile(str(self.sb.path("z3", "skill-sleuth.zip"))) as zf:
            self.assertEqual(zf.infolist()[0].date_time, tuple(time.gmtime(1700000000)[:6]))

    def test_zip_without_dir_goes_to_dist_and_dist_is_not_checked(self):
        repo = self.copy_repo("dist")
        ver = self.by.changelog_version(repo)[0]
        code, text = self.build("--zip", "--check", "--repo", repo, YAYIN_PRIVATE_PATTERNS=self.nopat)
        self.assertEqual(code, 0, text)                         # a bare --zip followed by another flag
        out = repo / "dist" / ("v%s" % ver)
        for name in EDITIONS:
            with self.subTest(package=name):
                z, s = out / ("%s.zip" % name), out / ("%s.skill" % name)
                self.assertTrue(z.is_file() and s.is_file(), sorted(p.name for p in out.iterdir()))
                self.assertEqual(z.read_bytes(), s.read_bytes())
                self.assertIn(hashlib.sha256(z.read_bytes()).hexdigest(), text)
        self.assertEqual(sorted(p.name for p in out.iterdir() if p.name.startswith(".")), [], "no temporary files left")
        home_path = "C:" + "\\Users\\" + "someone\\.claude"     # assembled at run time: never in this file
        (repo / "dist" / "notes.md").write_bytes(("path %s\r\n" % home_path).encode("ascii"))
        self.assertEqual(self.check(repo)[0], 0, "dist/ holds build outputs and is not part of the checked tree")

    def test_plugin_license_must_match_the_repository_license(self):
        repo = self.copy_repo("license")
        (repo / "plugins" / "skill-sleuth" / "LICENSE").unlink()
        p = repo / "plugins" / "skill-bulucu" / "LICENSE"
        p.write_bytes(p.read_bytes() + b"extra\n")
        self.assertFails(self.check(repo),
                         "FAIL  plugin folder LICENSE = repository LICENSE (skill-sleuth) -- plugins/skill-sleuth/LICENSE missing",
                         "FAIL  plugin folder LICENSE = repository LICENSE (skill-bulucu) -- plugins/skill-bulucu/LICENSE differs")

    def test_build_copies_the_license_and_dry_run_reports_it(self):
        repo = self.copy_repo("license-build")
        src = self.sb.path("license-build-src")
        for name in EDITIONS:
            shutil.copytree(str(repo / "plugins" / name / "skills" / name), str(src / name))
        (repo / "plugins" / "skill-sleuth" / "LICENSE").unlink()
        code, text = self.build("--dry-run", "--repo", repo, "--source-root", src, YAYIN_PRIVATE_PATTERNS=self.nopat)
        self.assertEqual(code, 0, text)
        self.assertIn("INFO  plugin folder LICENSE = repository LICENSE (skill-sleuth) -- a real run copies it", text)
        self.assertFalse((repo / "plugins" / "skill-sleuth" / "LICENSE").exists(), "a dry run writes nothing")
        code, text = self.build("--repo", repo, "--source-root", src, YAYIN_PRIVATE_PATTERNS=self.nopat)
        self.assertEqual(code, 0, text)
        for name in EDITIONS:
            with self.subTest(plugin=name):
                self.assertEqual((repo / "plugins" / name / "LICENSE").read_bytes(), (repo / "LICENSE").read_bytes())

    def test_builder_helpers(self):
        repo = self.copy_repo("helpers")
        pv = json.loads((repo / "plugins" / "skill-sleuth" / ".claude-plugin" / "plugin.json")
                        .read_text(encoding="utf-8"))["version"]
        self.assertEqual(self.by.changelog_version(repo), (pv, ""))
        (repo / "CHANGELOG.md").unlink()
        self.assertEqual(self.by.changelog_version(repo), (None, "CHANGELOG.md missing"))
        self.assertEqual(self.by.zip_date_time({}), (1980, 1, 1, 0, 0, 0))
        self.assertEqual(self.by.zip_date_time({"SOURCE_DATE_EPOCH": "0"}), (1980, 1, 1, 0, 0, 0))
        with self.assertRaises(ValueError):
            self.by.zip_date_time({"SOURCE_DATE_EPOCH": "x"})
        files = self.by.collect(repo / "plugins" / "skill-sleuth" / "skills" / "skill-sleuth")
        self.assertIn("SKILL.md", files)
        self.assertTrue(all(not k.startswith(("evals/", "__pycache__")) for k in files))


if __name__ == "__main__":
    unittest.main()
