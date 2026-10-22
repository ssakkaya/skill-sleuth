"""dis_kaynak_ara.py without a network: the privacy guard, the offline exit, argument errors, and the
community catalog answered from a synthetic cache (trust lines, elimination, byte cap). Every run has
DIS_KAYNAK_TEST_OFFLINE=1, so not one request leaves the machine."""
from __future__ import annotations

import json
import unittest

from sleuth_testlib import (OFFLINE_LINE, SCRIPTS, SKILL_FOLDER, T4_TRUST, T5_TRUST, Sandbox, ScriptTestCase,
                            FAKE_SKILLS_SH, community_fixture, make_private, script_version, write_json, zw)

GUARD = "gizlilik korumasi: sorgu reddedildi (%s); aga cikilmadi."
SHA = "0123456789abcdef0123456789abcdef01234567"


class PrivacyGuard(ScriptTestCase):
    """--query is checked before any network access: rejected -> exit 2, accepted -> offline exit 3."""

    REJECTED = [
        ("a", "uzunluk 1 (2-80 olmali)"),
        ("", "uzunluk 0 (2-80 olmali)"),
        ("   ", "uzunluk 0 (2-80 olmali)"),
        ("x" * 81, "uzunluk 81 (2-80 olmali)"),
        ("one two three four five six seven eight nine", "9 kelime (en cok 8)"),
        ("pdf/table", "izin verilmeyen karakter: '/'"),
        ("report.pdf", "izin verilmeyen karakter: '.'"),
        ("name@example", "izin verilmeyen karakter: '@'"),
        ("snake_case words", "izin verilmeyen karakter: '_'"),
        ("drive:path", "izin verilmeyen karakter: ':'"),
        ("back\\slash", "izin verilmeyen karakter: '\\\\'"),
        ("tab\there", "izin verilmeyen karakter: '\\t'"),
        ("invoice 12345", "5+ haneli sayi"),
        ("a12b c34d e56f g7h", "cok fazla rakam (veri gibi gorunuyor)"),
        ("pdf 12 34", "cok fazla rakam (veri gibi gorunuyor)"),
    ]
    ACCEPTED = [
        "pdf table extract",
        "ab",
        "x" * 80,
        "one two three four five six seven eight",
        "invoice 2024",
        "a12b c34d e56f",
        "pdf 12",
        "c++ c# co-author",
        "tablo çıkar",
    ]

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.addClassCleanup(cls.sb.close)
        cls.cache = cls.sb.mk("dk-empty")

    def query(self, q, *extra):
        return self.sb.run("dis_kaynak_ara.py", "--query=" + q, "--cache-dir", self.cache, *extra)

    def test_rejected_queries(self):
        for q, reason in self.REJECTED:
            with self.subTest(query=q):
                r = self.query(q)
                self.assertRan(r, 2)
                self.assertTrue(r.text.startswith(GUARD % reason), r.describe())

    def test_invisible_character_is_rejected(self):
        r = self.query("pdf" + zw(1) + "table")
        self.assertRan(r, 2)
        self.assertIn("izin verilmeyen karakter", r.text)
        self.assertNoInvisible(r)

    def test_accepted_queries_reach_the_offline_exit(self):
        for q in self.ACCEPTED:
            with self.subTest(query=q):
                r = self.query(q)
                self.assertRan(r, 3)
                self.assertTrue(r.text.startswith(OFFLINE_LINE + " ("), r.describe())
                self.assertNotIn("gizlilik korumasi", r.text)


class OfflineExit(ScriptTestCase):
    """DIS_KAYNAK_TEST_OFFLINE=1 and no cache: every mode says 'skip the layer' with exit 3."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        self.cache = self.sb.mk("dk-empty")

    def run_dk(self, *args):
        return self.sb.run("dis_kaynak_ara.py", *(args + ("--cache-dir", self.cache)))

    def test_every_mode_is_exit_3(self):
        cases = [("--query", "pdf table extract"), ("--query", "pdf table", "--source", "skills.sh"),
                 ("--query", "pdf table", "--source", "community"), ("--repo", "octo-org/demo-repo"),
                 ("--repo", "https://github.com/octo-org/demo-repo.git"), ("--audit", "octo-org/demo-repo/demo"),
                 ("--show", "community:demo-plugin"), ("--show", "octo-org/demo-repo/demo")]
        for args in cases:
            with self.subTest(args=args):
                r = self.run_dk(*args)
                self.assertRan(r, 3)
                self.assertTrue(r.text.startswith(OFFLINE_LINE + " ("), r.describe())

    def test_partial_outage_keeps_exit_0_when_a_source_answers(self):
        cache = community_fixture(self.sb.path("dk-cat"), [
            {"name": "zebra-widget", "description": "Zebra widget helper.",
             "source": {"source": "url", "url": "https://github.com/acme-test/zebra-widget.git", "sha": SHA}}],
            {"acme-test/zebra-widget": {"stars": 500}})
        r = self.sb.run("dis_kaynak_ara.py", "--query", "zebra", "--cache-dir", cache)
        self.assertRan(r, 0)
        self.assertIn("not: skills.sh ulasilamadi (test: cevrimdisi); yalniz topluluk katalogu", r.lines)


class Arguments(ScriptTestCase):
    """Bad arguments and refused cache folders: exit 2, nothing sent."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)

    def test_bad_arguments(self):
        cache = str(self.sb.mk("dk-empty"))
        cases = [
            ((), "tam olarak bir mod gerekli"),
            (("--query", "pdf", "--repo", "a/b"), "tam olarak bir mod gerekli"),
            (("--query", "pdf table", "--max-bytes", "299"), "hata: --max-bytes en az 300 olmali"),
            (("--query", "pdf table", "--min-stars", "-1"), "negatif olamaz"),
            (("--query", "pdf table", "--new-days", "-5"), "negatif olamaz"),
            (("--repo", "octo-org/report.pdf"), "gecersiz depo: dosya adina benziyor"),
            (("--repo", "not a repo"), "gecersiz depo"),
            (("--repo", "https://example.com/a/b"), "gecersiz depo"),
            (("--show", "octo-org/demo"), "gecersiz kimlik"),
            (("--show", "../../etc/passwd"), "gecersiz kimlik"),
            (("--audit", "a/b/c.docx"), "gecersiz kimlik: dosya adina benziyor"),
            (("--show", "community:bad/name"), "gecersiz kimlik"),
        ]
        for args, msg in cases:
            with self.subTest(args=args):
                r = self.sb.run("dis_kaynak_ara.py", *(args + ("--cache-dir", cache)))
                self.assertRan(r, 2)
                self.assertIn(msg, r.text, r.describe())

    def test_refused_cache_folders(self):
        sb = self.sb
        for where, msg in ((SKILL_FOLDER / "x-test-cache", "skill klasorunun icinde olamaz"),
                           (sb.config / "cache", "~/.claude altinda olamaz"),
                           (sb.home / ".claude" / "sub", "~/.claude altinda olamaz")):
            with self.subTest(cache_dir=str(where)):
                r = sb.run("dis_kaynak_ara.py", "--query", "pdf table", "--cache-dir", where)
                self.assertRan(r, 2)
                self.assertIn(msg, r.text, r.describe())
                self.assertFalse(where.exists())
        other = sb.mk("other-config")
        r = sb.run("dis_kaynak_ara.py", "--query", "pdf table", "--cache-dir", other / "c",
                   env=sb.env(CLAUDE_CONFIG_DIR=other))
        self.assertRan(r, 2)
        self.assertIn("~/.claude altinda olamaz", r.text)
        plug = sb.mk("plugcache")
        for where, env in ((sb.mk("home", "work", "proj") / ".claude" / "dk", sb.env()),
                           (plug / "dk", sb.env(CLAUDE_CODE_PLUGIN_CACHE_DIR=plug))):
            with self.subTest(claude_tree=str(where)):
                r = sb.run("dis_kaynak_ara.py", "--query", "pdf table", "--cache-dir", where, env=env)
                self.assertRan(r, 2)
                self.assertIn("Claude ayar agacinda (.claude) olamaz", r.text, r.describe())
                self.assertFalse(where.exists(), "no folder is created in a Claude config tree")


class CommunityCatalogOffline(ScriptTestCase):
    """The community catalog answered from a fresh cache while every host is down: T4 trust line (D1), the
    no-install-counter elimination incl. unverified stars (D2), hidden characters, byte cap."""

    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.addClassCleanup(cls.sb.close)
        tag = "".join(chr(0xE0000 + ord(c)) for c in "IGNORE")
        plugins = [
            {"name": "zebra-widget", "description": "Zebra widget for striped tables. Second sentence.",
             "source": {"source": "url", "url": "https://github.com/acme-test/zebra-widget.git", "sha": SHA}},
            {"name": "zebra-lowstar", "description": "Zebra helper with few stars.",
             "source": {"source": "url", "url": "https://github.com/acme-test/zebra-low.git", "sha": SHA}},
            {"name": "zebra-unknown", "description": "Zebra helper whose stars cannot be fetched.",
             "source": {"source": "url", "url": "https://github.com/acme-test/zebra-unknown.git", "sha": SHA}},
            {"name": "zebra-hosted", "description": "Zebra plugin stored inside the catalog repository.",
             "source": "./plugins/zebra-hosted", "author": {"name": "someone"}},
            {"name": "zebra-hidden", "description": "Zebra " + zw(3) + "hidden" + tag + " helper.",
             "source": {"source": "url", "url": "https://github.com/acme-test/zebra-hidden.git", "sha": SHA}},
            {"name": "unrelated-tool", "description": "Something else entirely.",
             "source": {"source": "url", "url": "https://github.com/acme-test/unrelated.git", "sha": SHA}},
        ]
        meta = {"acme-test/zebra-widget": {"stars": 500}, "acme-test/zebra-low": {"stars": 12},
                "acme-test/zebra-hidden": {"stars": 300}}
        cls.cache = community_fixture(cls.sb.path("dk-cat"), plugins, meta)
        cls.version = script_version("dis_kaynak_ara.py")

    def query(self, *extra):
        return self.sb.run("dis_kaynak_ara.py", "--query", "zebra", "--cache-dir", self.cache, *extra)

    def elim_line(self, r, plugin):
        rows = [ln for ln in r.lines if ln.startswith("- community:%s  " % plugin)]
        self.assertEqual(len(rows), 1, r.describe())
        return rows[0]

    def test_title_carries_only_the_t4_trust_line(self):
        r = self.query("--max-bytes", "4096")
        self.assertRan(r)
        title = r.lines[0]
        self.assertTrue(title.startswith("dis_kaynak_ara %s | q='zebra' | skills.sh: ulasilamadi | topluluk: 5"
                                         % self.version), title)
        self.assertTrue(title.endswith(" | T4: " + T4_TRUST), title)
        self.assertNotIn("T5:", title)
        self.assertNotIn("Anthropic incelemedi", r.text)

    def test_kept_and_eliminated_hits(self):
        r = self.query("--max-bytes", "4096")
        self.assertRan(r)
        self.assertTrue([ln for ln in r.lines if "[topluluk T4] zebra-widget  kurulum=veri-yok  yildiz=500" in ln],
                        r.describe())
        self.assertIn("-- elenenler (yeni / populer degil): --", r.lines)
        self.assertTrue(self.elim_line(r, "zebra-lowstar").endswith("(kurulum sayaci yok + az yildiz)"))
        self.assertTrue(self.elim_line(r, "zebra-unknown").endswith(
            "(kurulum sayaci yok, yildiz dogrulanamadi: GitHub ulasilamadi)"))
        self.assertTrue(self.elim_line(r, "zebra-hosted").endswith(
            "(kurulum sayaci yok, yildiz dogrulanamadi: katalog deposunda barinir: yildiz plugin'e ait degil)"))
        self.assertNotIn("community:unrelated-tool", r.text)

    def test_json_trust_and_reasons(self):
        r = self.query("--json")
        self.assertRan(r)
        d = json.loads(r.text)
        self.assertEqual(d["sources"]["community"]["trust"], T4_TRUST)
        self.assertEqual(d["sources"]["skills.sh"]["trust"], T5_TRUST)
        self.assertFalse(d["sources"]["skills.sh"]["ok"])
        self.assertTrue(d["sources"]["community"]["ok"])
        rows = dict((x["id"], x) for x in d["results"])
        self.assertEqual(set(x["trust"] for x in d["results"]), {T4_TRUST})
        self.assertFalse(rows["community:zebra-widget"]["eliminated"])
        self.assertEqual(rows["community:zebra-lowstar"]["eliminated_reason"], "kurulum sayaci yok + az yildiz")
        self.assertTrue(rows["community:zebra-unknown"]["eliminated"])
        self.assertTrue(rows["community:zebra-unknown"]["eliminated_reason"].startswith(
            "kurulum sayaci yok, yildiz dogrulanamadi"))
        self.assertTrue(rows["community:zebra-hosted"]["eliminated"])

    def test_star_threshold_zero_keeps_unverified_hits(self):
        r = self.query("--json", "--min-stars", "0")
        self.assertRan(r)
        d = json.loads(r.text)
        rows = dict((x["id"], x) for x in d["results"])
        self.assertFalse(rows["community:zebra-unknown"]["eliminated"])
        self.assertTrue([n for n in d["notes"] if n.startswith("esikler varsayilan degil: ")], d["notes"])

    def test_hidden_characters_are_stripped_and_named(self):
        r = self.query("--max-bytes", "4096")
        self.assertRan(r)
        self.assertNoInvisible(r)
        self.assertIn("not: community:zebra-hidden: 9 gizli karakter silindi (kirmizi bayrak)", r.lines)

    def test_text_output_respects_the_byte_cap(self):
        for cap in (2048, 600, 300):
            with self.subTest(max_bytes=cap):
                r = self.query("--max-bytes", str(cap))
                self.assertRan(r)
                self.assertLessEqual(len(r.out), cap, r.describe())
                self.assertNotIn(b"\r", r.out)

    def test_show_community_plugin(self):
        r = self.sb.run("dis_kaynak_ara.py", "--show", "community:zebra-widget", "--cache-dir", self.cache)
        self.assertRan(r)
        self.assertTrue(r.lines[0].startswith("dis_kaynak_ara %s | show | topluluk T4" % self.version), r.lines[0])
        self.assertTrue(r.lines[0].endswith(" | " + T4_TRUST), r.lines[0])
        self.assertIn("ad: zebra-widget  (claude-community katalogu)", r.lines)
        self.assertNotIn("Anthropic incelemedi", r.text)
        self.assertLessEqual(len(r.out), 2048)

    def test_show_hosted_plugin_has_no_review_claim(self):
        r = self.sb.run("dis_kaynak_ara.py", "--show", "community:zebra-hosted", "--cache-dir", self.cache)
        self.assertRan(r)
        self.assertTrue([ln for ln in r.lines if ln.startswith("not: katalog deposunun icinde barinir; ")],
                        r.describe())
        self.assertNotIn("Anthropic incelemedi", r.text)


class BothRegistries(ScriptTestCase):
    """When both registries answer, the title names both trust lines by tier (D1)."""

    def test_title_with_both_registries(self):
        sb = Sandbox()
        try:
            cache = community_fixture(sb.path("dk-cat"), [
                {"name": "zebra-widget", "description": "Zebra widget helper.",
                 "source": {"source": "url", "url": "https://github.com/acme-test/zebra-widget.git", "sha": SHA}}],
                {"acme-test/zebra-widget": {"stars": 500}, "acme-test/zebra-kit": {"stars": 800}})
            script = SCRIPTS / "dis_kaynak_ara.py"
            r = sb.run_code(FAKE_SKILLS_SH, script, "hit", "--query", "zebra", "--cache-dir", cache,
                            "--max-bytes", "4096")
            self.assertRan(r)
            title = r.lines[0]
            self.assertTrue(title.endswith(" | T5: %s | T4: %s" % (T5_TRUST, T4_TRUST)), title)
            self.assertIn("skills.sh: 1 | topluluk: 1", title)
            self.assertTrue([ln for ln in r.lines if "[skills.sh T5] acme-test/zebra-kit/zebra-skill" in ln],
                            r.describe())
            r = sb.run_code(FAKE_SKILLS_SH, script, "hit", "--query", "zebra", "--cache-dir", cache, "--json")
            d = json.loads(r.text)
            trust = dict((x["registry"], x["trust"]) for x in d["results"])
            self.assertEqual(trust, {"skills.sh": T5_TRUST, "topluluk": T4_TRUST})
        finally:
            sb.close()


# A run with a scripted HTTP layer: urllib's opener is replaced inside the child process, so no socket is opened.
# argv: <script> <routes.json> <script args...>; routes = [[url prefix, status, body text], ...], first match wins.
FAKE_HTTP = r"""
import importlib.util, io, json, os, sys, urllib.error
spec = importlib.util.spec_from_file_location("dk_under_test", sys.argv[1])
dk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dk)
routes = json.load(open(sys.argv[2], encoding="utf-8"))
class Resp(object):
    def __init__(self, status, body):
        self.status, self.headers, self._b = status, {}, body
    def read(self, n=-1):
        return self._b if n is None or n < 0 else self._b[:n]
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
class Opener(object):
    def open(self, req, timeout=None):
        for prefix, status, body in routes:
            if req.full_url.startswith(prefix):
                b = body.encode("utf-8")
                if status != 200:
                    raise urllib.error.HTTPError(req.full_url, status, "scripted", {}, io.BytesIO(b))
                return Resp(status, b)
        raise urllib.error.URLError("no scripted route")
dk.urllib.request.build_opener = lambda *a: Opener()
os.environ.pop("DIS_KAYNAK_TEST_OFFLINE", None)
sys.exit(dk.main(sys.argv[3:]))
"""

SID = "acme-test/zebra-kit/zebra-skill"
API = "https://api.github.com/repos/acme-test/zebra-kit"
SEARCH_ROW = {"id": SID, "source": "acme-test/zebra-kit", "skillId": "zebra-skill", "name": "zebra-skill",
              "installs": 5000}


def tags(n):
    """n characters of the Unicode tag block, built at run time (the test file stays free of them)."""
    return "".join(chr(0xE0041 + i % 26) for i in range(n))


class ScriptedNetwork(ScriptTestCase):
    """GitHub outages are not 'repository not found'; hidden characters are counted in every field; the plugin
    content line names monitors, LSP and settings; malformed registry JSON never ends in a traceback."""

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.close)
        self.n = 0

    def run_with(self, routes, *args):
        self.n += 1
        cache = make_private(self.sb.mk("dk-cache-%d" % self.n))
        path = write_json(self.sb.path("routes-%d.json" % self.n), routes)
        return self.sb.run_code(FAKE_HTTP, SCRIPTS / "dis_kaynak_ara.py", path, *args, "--cache-dir", cache)

    @staticmethod
    def skill_routes(meta_status=200, audit=None, search_body=None, frontmatter_extra="", history_status=200,
                     siblings=()):
        commit = json.dumps({"sha": SHA, "commit": {"committer": {"date": "2026-01-01T00:00:00Z"}}})
        meta = json.dumps({"stargazers_count": 500, "forks_count": 3, "created_at": "2020-01-01T00:00:00Z",
                           "pushed_at": "2026-09-01T00:00:00Z", "archived": False, "license": None})
        skill_md = "---\nname: zebra-skill\ndescription: Zebra helper.\n%s---\n\nBody.\n" % frontmatter_extra
        return [
            ["https://skills.sh/api/search?", 200, search_body or json.dumps({"skills": [SEARCH_ROW]})],
            ["https://skills.sh/api/v1/skills/audit/", 200 if audit else 404, audit or "{}"],
            [API + "/commits/HEAD", 200, commit],
            [API + "/commits?path=", history_status, json.dumps([json.loads(commit)])],
            [API + "/git/trees/", 200, json.dumps({"tree": [{"path": "skills/zebra-skill/" + f, "type": "blob"}
                                                            for f in ("SKILL.md",) + tuple(siblings)]})],
            [API, meta_status, meta if meta_status == 200 else "upstream error"],
            ["https://raw.githubusercontent.com/acme-test/zebra-kit/%s/skills/zebra-skill/SKILL.md" % SHA, 200, skill_md],
        ]

    def test_github_outage_keeps_the_install_command(self):
        r = self.run_with(self.skill_routes(meta_status=502), "--query", "zebra skill", "--source", "skills.sh")
        self.assertRan(r)
        self.assertIn("kur (kullanici calistirir): npx skills add acme-test/zebra-kit --skill zebra-skill", r.text,
                      r.describe())
        self.assertNotIn("depo bulunamadi", r.text, r.describe())
        self.assertIn("GitHub ulasilamadi (GitHub HTTP 502)", r.text, r.describe())

    def test_repo_outage_is_exit_3_and_not_found_is_a_fact(self):
        r = self.run_with([[API, 503, "unavailable"]], "--repo", "acme-test/zebra-kit")
        self.assertRan(r, 3)
        self.assertIn(OFFLINE_LINE, r.text, r.describe())
        r = self.run_with([[API, 404, "{}"]], "--repo", "acme-test/zebra-kit")
        self.assertRan(r)
        self.assertIn("depo bulunamadi (GitHub HTTP 404)", r.text, r.describe())

    def test_hidden_characters_in_frontmatter_and_audit_summary(self):
        audit = json.dumps({"audits": [{"provider": "Socket", "status": "pass", "summary": "Looks fine." + tags(9)}]})
        r = self.run_with(self.skill_routes(audit=audit, frontmatter_extra="allowed-tools: Bash%s(curl:*)\n" % zw(12)),
                          "--show", SID)
        self.assertRan(r)
        self.assertNoInvisible(r)
        for n in (12, 9):
            self.assertIn("not: %s: %d gizli karakter silindi (kirmizi bayrak)" % (SID, n), r.lines, r.describe())
        r = self.run_with([["https://skills.sh/api/v1/skills/audit/", 200, audit]], "--audit", SID)
        self.assertRan(r)
        self.assertIn("not: %s: 9 gizli karakter silindi (kirmizi bayrak)" % SID, r.lines, r.describe())

    def test_malformed_registry_json_is_not_a_traceback(self):
        search = ('{"skills": [{"id": "%s", "source": "acme-test/zebra-kit", "skillId": "zebra-skill", '
                  '"name": "zebra-skill", "installs": 1e400}]}' % SID)
        for audit in ('{"audits": [{"provider": "X", "status": "pass", "categories": 5}]}', '{"audits": 1}'):
            with self.subTest(audit=audit):
                r = self.run_with(self.skill_routes(audit=audit, search_body=search),
                                  "--query", "zebra skill", "--source", "skills.sh")
                self.assertRan(r)

    def test_plugin_markers_include_monitors_lsp_and_settings(self):
        code = ("import importlib.util, json, sys\n"
                "spec = importlib.util.spec_from_file_location('dka', sys.argv[1])\n"
                "m = importlib.util.module_from_spec(spec)\n"
                "spec.loader.exec_module(m)\n"
                "paths = ['plugins/zeb/.claude-plugin/plugin.json', 'plugins/zeb/monitors/monitors.json',\n"
                "         'plugins/zeb/.lsp.json', 'plugins/zeb/settings.json', 'plugins/zeb/README.md']\n"
                "d = m.digest_tree({'tree': [{'path': p, 'type': 'blob'} for p in paths]}, sys.argv[2])\n"
                "print(json.dumps(sorted(d['marks'])))\n")
        r = self.sb.run_code(code, SCRIPTS / "dis_kaynak_ara.py", SHA)
        self.assertRan(r)
        self.assertEqual(json.loads(r.text), ["plugins/zeb/.claude-plugin/plugin.json", "plugins/zeb/.lsp.json",
                                              "plugins/zeb/monitors/monitors.json", "plugins/zeb/settings.json"])

    def test_one_failed_history_request_keeps_the_rest(self):
        r = self.run_with(self.skill_routes(history_status=502, siblings=("run.sh",)), "--show", SID)
        self.assertRan(r)
        self.assertIn("dosyalar: SKILL.md + 1 dosya (run.sh)", r.lines, r.describe())
        self.assertTrue([ln for ln in r.lines if ln.startswith("yildiz: 500")], r.describe())

    def test_hidden_characters_in_file_names(self):
        r = self.run_with(self.skill_routes(siblings=("run" + tags(10) + ".py",)), "--show", SID)
        self.assertRan(r)
        self.assertNoInvisible(r)
        self.assertIn("not: %s: 10 gizli karakter silindi (kirmizi bayrak)" % SID, r.lines, r.describe())


if __name__ == "__main__":
    unittest.main()
