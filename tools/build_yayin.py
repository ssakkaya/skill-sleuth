#!/usr/bin/env python3
"""build_yayin.py -- assemble the publication tree from the source skill folders, then check it.

The repository working tree (the folder that contains this tools/ directory) does not keep
copies of the skills by hand. This script copies, for each language edition,
    <source-root>/<edition>/{SKILL.md,references,scripts}
into
    <repo>/plugins/<edition>/skills/<edition>/
copies <repo>/LICENSE to <repo>/plugins/<edition>/LICENSE (users receive only the plugin folder),
and then runs the release checks. The English edition (skill-sleuth) is optional: when its
source folder does not exist the script says so and builds only the Turkish plugin.

In a clean clone (no source folders next to the repository) there is nothing to copy: the
script then runs the in-repo check instead -- the same checks on the tree as it is, generated
skill folders included -- and copies nothing. CI runs that mode explicitly with --check.

Usage:
    PYTHONUTF8=1 python tools/build_yayin.py [--dry-run | --check] [--skip-en]
                                             [--source-root DIR] [--repo DIR] [--zip [DIR]]

    (no flag)       copy the sources into plugins/<edition>/skills/<edition>/ and the LICENSE
                    into each plugin folder, then check
    --dry-run       plan and check the SOURCE files, write nothing
    --check         in-repo check: check the tree as it is, copy nothing (exit 0/1). Chosen
                    automatically when the Turkish source folder is absent and --source-root
                    was not given; an explicit --source-root without sources is an error (exit 2)
    --skip-en       never build or check the English plugin
    --source-root   folder that holds the source skill folders (default: parent of the repo)
    --repo DIR      publication tree to build or check (default: the folder above tools/)
    --zip [DIR]     after passing checks (build or --check, not --dry-run), write
                    DIR/<edition>.zip (claude.ai upload and release assets: one top-level
                    <edition>/ folder) plus a byte-identical DIR/<edition>.skill, and print their
                    SHA-256. Without DIR: <repo>/dist/v<version>/ (dist/ is git-ignored)

Checks (every mode): personal-data patterns in the skill files, SKILL.md frontmatter keys and name,
byte caps, personal data and CRLF / BOM over every text file of the tree (dist/ excluded), scripts/*.py + builtins.json
identical across the two plugins, marketplace.json / plugin.json present, each plugin folder's
LICENSE equal to the repository LICENSE, one version everywhere (plugin.json =
marketplace.json entry, or the entry omits it = top '## x.y.z' heading of CHANGELOG.md; plugin.json
wins at install time and only `claude plugin validate` warns, so a mismatch is a FAIL here).
--check also fails on unexpected files in a generated skill folder and, when the sources are
present, warns (WARN, not a failure) if a generated copy differs from its source.

Zips are reproducible: entries sorted by path, every timestamp set to $SOURCE_DATE_EPOCH
(clamped to the zip range; default 1980-01-01 00:00:00 UTC), mode 0644 with a Unix host byte,
deflate level 9, no extra fields. The same files and the same zlib give the same SHA-256.

Exit codes: 0 all checks passed · 1 at least one check failed · 2 usage error / source missing.
Standard library only; Python 3.9+ (3.12 tested).
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile
import zlib
from pathlib import Path

DEFAULT_REPO = Path(__file__).resolve().parent.parent
REPO = DEFAULT_REPO  # kept for importers; functions take the tree as a parameter

# (plugin / skill name, source folder name, required)
EDITIONS = [
    ("skill-bulucu", "skill-bulucu", True),
    ("skill-sleuth", "skill-sleuth", False),
]
COPY_ITEMS = ("SKILL.md", "references", "scripts")
LICENSE_NAME = "LICENSE"         # <repo>/LICENSE, copied into every plugin folder
DIST_DIR = "dist"                # build outputs (zips); git-ignored, never checked as part of the tree
EXCLUDE_DIRS = {"evals", "__pycache__"}
EXCLUDE_SUFFIXES = (".pyc",)

# Personal-data patterns. Checked per edition on the copied skill folders and once more on every
# text file of the tree (hand-written README, CHANGELOG, manifests, workflows, tests ...); the
# GitHub login is blanked before the whole-tree pass. Backslashes are normalised to
# forward slashes before matching, so "C:\\Users\\" is caught as well. Only generic home-folder
# patterns live here; machine-specific ones (user name, account ids, own project paths) are read
# from a private file OUTSIDE the repository, one regex per line ("#" starts a comment):
# <source-root>/yayin-private-patterns.txt, or the path in $YAYIN_PRIVATE_PATTERNS.
GENERIC_PERSONAL = (r"[A-Za-z]:/Users/", r"/[c]/Users/", r"/home/[A-Za-z0-9_.-]+/")  # written so they never match themselves
PRIVATE_PATTERNS_NAME = "yayin-private-patterns.txt"
GITHUB_LOGIN = "ssakkaya"  # public; appears in README, LICENSE and the manifests on purpose


def load_personal(src_root: Path) -> tuple[re.Pattern[str], Path | None]:
    env = os.environ.get("YAYIN_PRIVATE_PATTERNS")
    path = Path(env) if env else src_root / PRIVATE_PATTERNS_NAME
    patterns = list(GENERIC_PERSONAL)
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():   # -sig: a BOM must not spoil line 1
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    else:
        path = None
    return re.compile("|".join(patterns), re.IGNORECASE), path

SIZE_LIMITS = {
    "SKILL.md (body)": 17_000,
    "references/dis-kaynaklar.md": 9_500,
    "references/guvenlik-kontrol-listesi.md": 11_000,
    "scripts/README.md": 16_000,
}
# per-plugin names of the two run-time "core" references (Turkish edition / English edition)
CORE_FILES = {
    "skill-bulucu": ("references/dis-kaynaklar.md", "references/guvenlik-kontrol-listesi.md"),
    "skill-sleuth": ("references/external-sources.md", "references/security-checklist.md"),
}
ALLOWED_FM_KEYS = {"name", "description"}
IDENTICAL_GLOBS = ("scripts/*.py", "scripts/builtins.json")
BINARY_SUFFIXES = {".zip", ".skill", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2"}
FM_RE = re.compile(rb"\A---\r?\n(.*?)\r?\n---\r?\n", re.S)
VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
# "## 0.1.0 — 2026-10-09", "## [0.2.0] - ...", "## v0.2.0"; "## Unreleased" is skipped
CHANGELOG_RE = re.compile(r"##\s+\[?v?(" + VERSION_RE.pattern + r")\]?(?=\s|$)")

ZIP_EPOCH_MIN = 315_532_800      # 1980-01-01 00:00:00 UTC: the earliest time a zip entry can hold
ZIP_EPOCH_MAX = 4_354_819_198    # 2107-12-31 23:59:58 UTC: the latest
ZIP_FILE_MODE = 0o100644         # regular file, rw-r--r--
ZIP_LEVEL = 9


class Finding:
    __slots__ = ("status", "check", "detail")

    def __init__(self, status: str, check: str, detail: str = "") -> None:
        self.status, self.check, self.detail = status, check, detail


def rel_to(p: Path, base: Path) -> str:
    return (p.relative_to(base) if p.is_relative_to(base) else p).as_posix()


def collect(src_skill: Path) -> dict[str, Path]:
    """Return {relative posix path: file} for everything that ships from one skill folder."""
    files: dict[str, Path] = {}
    for item in COPY_ITEMS:
        p = src_skill / item
        if not p.exists():
            continue
        if p.is_file():
            files[item] = p
            continue
        for f in sorted(p.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(src_skill)
            if any(part in EXCLUDE_DIRS for part in rel.parts) or f.suffix in EXCLUDE_SUFFIXES:
                continue
            files[rel.as_posix()] = f
    return dict(sorted(files.items()))


def copy_edition(files: dict[str, Path], dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    for rel, src in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)  # bytes only; no metadata, no permission bits


def parse_frontmatter(raw: bytes) -> tuple[dict[str, str] | None, int]:
    m = FM_RE.match(raw)
    if not m:
        return None, 0
    keys: dict[str, str] = {}
    for line in m.group(1).decode("utf-8", "replace").splitlines():
        if line and not line[0].isspace() and ":" in line:
            k, _, v = line.partition(":")
            keys[k.strip()] = v.strip()
    return keys, m.end()


def check_edition(name: str, files: dict[str, Path], rows: list[tuple],
                  personal: re.Pattern[str]) -> list[Finding]:
    out: list[Finding] = []

    # --- personal data --------------------------------------------------------------------
    hits: list[str] = []
    for rel, p in files.items():
        text = p.read_bytes().decode("utf-8", "replace").replace("\\", "/")
        for m in personal.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{rel}:{line}: ...{text[max(0, m.start()-20):m.end()+20]!r}")
    if hits:
        out.append(Finding("FAIL", f"personal data pattern ({name})", "; ".join(hits[:10])))
    else:
        out.append(Finding("OK", f"personal data pattern ({name}, {len(files)} files)"))

    # --- SKILL.md frontmatter ---------------------------------------------------------------
    skill_md = files.get("SKILL.md")
    body_len = None
    if skill_md is None:
        out.append(Finding("FAIL", f"SKILL.md present ({name})", "missing"))
    else:
        raw = skill_md.read_bytes()
        keys, end = parse_frontmatter(raw)
        if keys is None:
            out.append(Finding("FAIL", f"frontmatter ({name})", "no --- block at top of SKILL.md"))
        else:
            body_len = len(raw) - end
            extra = sorted(set(keys) - ALLOWED_FM_KEYS)
            missing = sorted(ALLOWED_FM_KEYS - set(keys))
            if extra or missing:
                out.append(Finding("FAIL", f"frontmatter keys ({name})",
                                   f"extra={extra} missing={missing}"))
            else:
                out.append(Finding("OK", f"frontmatter keys ({name}): name, description"))
            fm_name = keys.get("name", "").strip("\"'")
            if fm_name == name:
                out.append(Finding("OK", f"frontmatter name matches folder ({name})"))
            else:
                out.append(Finding("FAIL", f"frontmatter name matches folder ({name})",
                                   f"name: {fm_name!r} != folder {name!r}"))

    # --- size limits ----------------------------------------------------------------------
    cores = CORE_FILES.get(name, CORE_FILES["skill-bulucu"])
    limits = {"SKILL.md (body)": SIZE_LIMITS["SKILL.md (body)"], cores[0]: 9_500, cores[1]: 11_000,
              "scripts/README.md": SIZE_LIMITS["scripts/README.md"]}
    for label, limit in limits.items():
        if label == "SKILL.md (body)":
            size = body_len
        else:
            p = files.get(label)
            size = p.stat().st_size if p else None
        if size is None:
            rows.append((name, label, "-", limit, "MISSING"))
            out.append(Finding("FAIL", f"size {label} ({name})", "file missing"))
        elif size > limit:
            rows.append((name, label, size, limit, "OVER"))
            out.append(Finding("FAIL", f"size {label} ({name})", f"{size} > {limit}"))
        else:
            rows.append((name, label, size, limit, "OK"))
    return out


def check_stray(name: str, dest: Path, files: dict[str, Path], repo: Path) -> Finding:
    """--check only: a generated skill folder holds nothing but what a build would copy."""
    stray = []
    for p in sorted(dest.rglob("*")):
        rel = p.relative_to(dest)
        if p.is_file() and "__pycache__" not in rel.parts and p.suffix not in EXCLUDE_SUFFIXES \
                and rel.as_posix() not in files:
            stray.append(rel_to(p, repo))
    if stray:
        return Finding("FAIL", f"generated skill folder holds only SKILL.md, references/, scripts/ ({name})",
                       "unexpected: " + "; ".join(stray[:10]))
    return Finding("OK", f"generated skill folder holds only SKILL.md, references/, scripts/ ({name})")


def check_sync(name: str, src_files: dict[str, Path], tree_files: dict[str, Path]) -> Finding:
    """--check with the sources present: is the generated copy what a build would write?"""
    diff = sorted(set(src_files) ^ set(tree_files))
    diff += [rel for rel in sorted(set(src_files) & set(tree_files))
             if src_files[rel].read_bytes() != tree_files[rel].read_bytes()]
    if diff:
        return Finding("WARN", f"generated copy matches its source ({name})",
                       f"{len(diff)} file(s) differ: {', '.join(diff[:6])}; run without --check to rebuild")
    return Finding("OK", f"generated copy matches its source ({name})")


def check_crlf_bom(paths: list[Path], bases: tuple[Path, ...], label: str) -> Finding:
    bad: list[str] = []
    for p in paths:
        if p.suffix.lower() in BINARY_SUFFIXES:
            continue
        raw = p.read_bytes()
        rel = p.as_posix()
        for base in bases:
            if p.is_relative_to(base):
                rel = p.relative_to(base).as_posix()
                break
        if raw.startswith(b"\xef\xbb\xbf"):
            bad.append(f"{rel}: BOM")
        if b"\r\n" in raw:
            bad.append(f"{rel}: CRLF")
    if bad:
        return Finding("FAIL", f"CRLF / BOM ({label})", "; ".join(bad[:10]))
    return Finding("OK", f"CRLF / BOM ({label}, {len(paths)} files)")


def check_tree_personal(paths: list[Path], personal: re.Pattern[str], repo: Path) -> Finding:
    """Personal-data patterns over every text file that ships, hand-written ones included.
    The GitHub login is blanked first (a private pattern may be part of it). This script is
    checked too; its generic patterns are written so that they never match themselves."""
    hits: list[str] = []
    for p in paths:
        if p.suffix.lower() in BINARY_SUFFIXES:
            continue
        text = p.read_bytes().decode("utf-8", "replace").replace("\\", "/")
        text = re.sub(GITHUB_LOGIN, "", text, flags=re.IGNORECASE)
        rel = rel_to(p, repo)
        hits += [f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {m.group(0)!r}"
                 for m in personal.finditer(text)]
    if hits:
        return Finding("FAIL", "personal data pattern (whole tree)", "; ".join(hits[:10]))
    return Finding("OK", f"personal data pattern (whole tree, {len(paths)} files)")


def repo_files(repo: Path) -> list[Path]:
    out: list[Path] = []
    for p in repo.rglob("*"):
        if not p.is_file():
            continue
        parts = p.relative_to(repo).parts
        if ".git" in parts or "__pycache__" in parts or parts[0] == DIST_DIR or p.suffix in EXCLUDE_SUFFIXES:
            continue
        out.append(p)
    return sorted(out, key=lambda q: q.relative_to(repo).as_posix())


def copy_license(repo: Path, name: str) -> bool:
    """BUILD: the repository LICENSE goes into the plugin folder (the directory hands out only that folder).
    False when there is no <repo>/LICENSE to copy (check_license then reports it)."""
    src = repo / LICENSE_NAME
    if not src.is_file():
        return False
    shutil.copyfile(src, repo / "plugins" / name / LICENSE_NAME)
    return True


def check_license(repo: Path, names: list[str], dry_run: bool) -> list[Finding]:
    """Each plugin folder holds a LICENSE equal to <repo>/LICENSE."""
    src = repo / LICENSE_NAME
    if not src.is_file():
        return [Finding("FAIL", "LICENSE at the repository root", "missing")]
    out: list[Finding] = []
    for name in names:
        target = repo / "plugins" / name / LICENSE_NAME
        label = f"plugin folder LICENSE = repository LICENSE ({name})"
        if target.is_file() and target.read_bytes() == src.read_bytes():
            out.append(Finding("OK", label))
        elif dry_run:
            out.append(Finding("INFO", label, "a real run copies it"))
        else:
            out.append(Finding("FAIL", label, f"{rel_to(target, repo)} {'differs' if target.is_file() else 'missing'}; "
                                              "run `python tools/build_yayin.py` where the sources are to copy it"))
    return out


def check_identical(tr: dict[str, Path], en: dict[str, Path]) -> Finding:
    problems: list[str] = []
    for pattern in IDENTICAL_GLOBS:
        tr_set = {rel for rel in tr if fnmatch.fnmatch(rel, pattern)}
        en_set = {rel for rel in en if fnmatch.fnmatch(rel, pattern)}
        for rel in sorted(tr_set - en_set):
            problems.append(f"{rel}: only in skill-bulucu")
        for rel in sorted(en_set - tr_set):
            problems.append(f"{rel}: only in skill-sleuth")
        for rel in sorted(tr_set & en_set):
            if tr[rel].read_bytes() != en[rel].read_bytes():
                problems.append(f"{rel}: differs")
    if problems:
        return Finding("FAIL", "scripts/*.py + builtins.json identical across plugins", "; ".join(problems))
    return Finding("OK", "scripts/*.py + builtins.json identical across plugins")


def changelog_version(repo: Path) -> tuple[str | None, str]:
    """(version of the topmost '## x.y.z' heading, problem text when there is none)."""
    path = repo / "CHANGELOG.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, "CHANGELOG.md missing"
    for line in text.splitlines():
        m = CHANGELOG_RE.match(line)
        if m:
            return m.group(1), ""
    return None, "CHANGELOG.md has no '## x.y.z' heading"


def check_versions(repo: Path, data: dict) -> list[Finding]:
    """One version everywhere: plugin.json = its marketplace.json entry (or the entry omits
    'version') = CHANGELOG.md top heading. When both manifests set it, plugin.json wins at install
    time (only `claude plugin validate` warns), so a mismatch is a FAIL here."""
    out: list[Finding] = []
    top, problem = changelog_version(repo)
    if top is None:
        out.append(Finding("FAIL", "version: CHANGELOG.md top '## x.y.z' heading", problem))
    for entry in data.get("plugins", []):
        name, source = entry.get("name"), entry.get("source")
        label = f"version consistent ({name})"
        if not isinstance(source, str):
            continue  # reported by check_manifests
        pj = repo / source / ".claude-plugin" / "plugin.json"
        try:
            pv = json.loads(pj.read_text(encoding="utf-8")).get("version")
        except (OSError, ValueError, AttributeError) as exc:
            out.append(Finding("FAIL", label, f"cannot read {rel_to(pj, repo)}: {exc}"))
            continue
        mv = entry.get("version")
        bad: list[str] = []
        if not isinstance(pv, str) or not VERSION_RE.fullmatch(pv):
            out.append(Finding("FAIL", label, f"{rel_to(pj, repo)}: 'version' is {pv!r}, expected x.y.z "
                                              f"(keep the version in plugin.json)"))
            continue
        if mv is not None and mv != pv:
            bad.append(f"plugin.json {pv} != marketplace.json entry {mv} (make them equal or drop "
                       f"'version' from the marketplace entry)")
        if top is not None and pv != top:
            bad.append(f"plugin.json {pv} != CHANGELOG.md top heading '## {top}' (add a "
                       f"'## {pv} — YYYY-MM-DD' section or fix plugin.json)")
        if bad:
            out.append(Finding("FAIL", label, "; ".join(bad)))
        else:
            where = "marketplace entry" if mv is not None else "marketplace entry omits it"
            out.append(Finding("OK", f"{label}: {pv} in plugin.json, {where}, CHANGELOG.md"))
    return out


def check_manifests(repo: Path, built: list[str], dry_run: bool) -> list[Finding]:
    out: list[Finding] = []
    mp = repo / ".claude-plugin" / "marketplace.json"
    try:
        data = json.loads(mp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Finding("FAIL", "marketplace.json parses", str(exc))]
    listed = {p.get("name"): p.get("source") for p in data.get("plugins", [])}
    out.append(Finding("OK", f"marketplace.json parses ({len(listed)} plugins: {', '.join(map(str, listed))})"))
    for name, source in listed.items():
        pdir = (repo / source).resolve() if isinstance(source, str) else None
        if pdir is None or not (pdir / ".claude-plugin" / "plugin.json").is_file():
            out.append(Finding("FAIL", f"plugin.json for {name}", f"missing under {source}"))
            continue
        skills_dir = pdir / "skills" / name / "SKILL.md"
        if skills_dir.is_file():
            out.append(Finding("OK", f"{name}: plugin.json + skills/{name}/SKILL.md present"))
        elif name in built and dry_run:
            out.append(Finding("INFO", f"{name}: skills/{name}/SKILL.md would be written by a real run"))
        elif name in built:
            out.append(Finding("FAIL", f"{name}: skills/{name}/SKILL.md", "built but not found"))
        else:
            out.append(Finding("INFO", f"{name}: listed in marketplace.json, skill not built yet "
                                       f"(no SKILL.md under {source}/skills/{name}/)"))
    out.extend(check_versions(repo, data))
    return out


def zip_date_time(environ: dict | None = None) -> tuple[int, int, int, int, int, int]:
    """Timestamp for every zip entry: $SOURCE_DATE_EPOCH (UTC, clamped to the zip range), else
    1980-01-01 00:00:00. Raises ValueError when $SOURCE_DATE_EPOCH is set but not an integer."""
    raw = (os.environ if environ is None else environ).get("SOURCE_DATE_EPOCH", "").strip()
    epoch = int(raw) if raw else ZIP_EPOCH_MIN
    epoch = min(max(epoch, ZIP_EPOCH_MIN), ZIP_EPOCH_MAX)
    return tuple(time.gmtime(epoch)[:6])  # type: ignore[return-value]


def write_zips(editions: dict[str, dict[str, Path]], out_dir: Path,
               date_time: tuple[int, int, int, int, int, int]) -> list[str]:
    """One zip per edition whose only top-level entry is <edition>/ (the claude.ai upload rule), plus a
    byte-identical <edition>.skill copy (the same package under the extension claude.ai also accepts).
    Byte-for-byte reproducible: sorted entries, fixed time, fixed mode, fixed host, fixed level."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for name, files in editions.items():
        target, skill = out_dir / f"{name}.zip", out_dir / f"{name}.skill"
        tmp, skill_tmp = out_dir / f".{name}.zip.tmp", out_dir / f".{name}.skill.tmp"
        try:
            with zipfile.ZipFile(tmp, "w") as zf:
                for rel in sorted(files):
                    info = zipfile.ZipInfo(f"{name}/{rel}", date_time=date_time)
                    info.create_system = 3             # Unix on every OS, so the mode bits count
                    info.external_attr = ZIP_FILE_MODE << 16
                    info.compress_type = zipfile.ZIP_DEFLATED
                    zf.writestr(info, files[rel].read_bytes(),
                                compress_type=zipfile.ZIP_DEFLATED, compresslevel=ZIP_LEVEL)
            shutil.copyfile(tmp, skill_tmp)            # both temp files first, then the pair of renames
            os.replace(tmp, target)
            os.replace(skill_tmp, skill)
        finally:
            for t in (tmp, skill_tmp):
                if t.exists():
                    t.unlink()
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        lines.append(f"{digest}  {target.as_posix()}")
        lines.append(f"{digest}  {skill.as_posix()}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="plan and check the source files; write nothing")
    mode.add_argument("--check", action="store_true",
                      help="in-repo check of the tree as it is; copy nothing (automatic without sources)")
    ap.add_argument("--skip-en", action="store_true", help="do not build or check the English plugin")
    ap.add_argument("--source-root", type=Path, default=None,
                    help="folder holding the source skill folders (default: parent of the repo)")
    ap.add_argument("--repo", type=Path, default=None,
                    help=f"publication tree to build or check (default: {DEFAULT_REPO.as_posix()})")
    ap.add_argument("--zip", nargs="?", const="", default=None, metavar="DIR",
                    help="after passing checks, write reproducible DIR/<edition>.zip and .skill and print their "
                         f"SHA-256 (without DIR: <repo>/{DIST_DIR}/v<version>)")
    args = ap.parse_args(argv)
    repo: Path = (args.repo if args.repo is not None else DEFAULT_REPO).resolve()
    src_root: Path = (args.source_root if args.source_root is not None else repo.parent).resolve()
    if not repo.is_dir():
        print(f"ERROR: --repo {repo.as_posix()} is not a folder", file=sys.stderr)
        return 2
    want_zip = args.zip is not None
    try:
        date_time = zip_date_time() if want_zip else None
    except ValueError:
        print(f"ERROR: SOURCE_DATE_EPOCH={os.environ.get('SOURCE_DATE_EPOCH')!r} is not an integer",
              file=sys.stderr)
        return 2

    check, auto = args.check, False
    tr_name, tr_folder, _ = EDITIONS[0]
    if not check and not (src_root / tr_folder / "SKILL.md").is_file():
        if args.source_root is not None:
            print(f"[{tr_name}] ERROR: source skill not found at {(src_root / tr_folder).as_posix()}",
                  file=sys.stderr)
            return 2
        check, auto = True, True
    dry_run = args.dry_run and not check

    label = ("CHECK (in-repo, automatic: no source folders next to the repository)" if auto
             else "CHECK (in-repo)" if check else "DRY RUN" if dry_run else "BUILD")
    print(f"build_yayin | {label} | source: {src_root.as_posix()} -> repo: {repo.as_posix()}")

    findings: list[Finding] = []
    personal, private_file = load_personal(src_root)
    if private_file is None:
        findings.append(Finding("INFO", "private patterns", f"no {PRIVATE_PATTERNS_NAME} next to the source "
                                "folders and no $YAYIN_PRIVATE_PATTERNS; only generic home-folder patterns checked"))
    else:
        findings.append(Finding("OK", "private patterns loaded (file kept outside the repository)"))
    rows: list[tuple] = []
    views: dict[str, dict[str, Path]] = {}
    built: list[str] = []
    planned_sources: list[Path] = []

    for name, folder, required in EDITIONS:
        src = src_root / folder
        dest = repo / "plugins" / name / "skills" / name
        dest_rel = rel_to(dest, repo)
        if name == "skill-sleuth" and args.skip_en:
            print(f"[{name}] skipped (--skip-en)")
            continue
        if check:
            if not (dest / "SKILL.md").is_file():
                if required:
                    findings.append(Finding("FAIL", f"{name}: generated skill folder",
                                            f"no SKILL.md under {dest_rel}; build it where the sources are"))
                else:
                    print(f"[{name}] no SKILL.md under {dest_rel}; checking only the Turkish plugin")
                continue
            files = collect(dest)
            print(f"[{name}] checking {len(files)} files in {dest_rel} (nothing copied)")
            views[name] = files
            findings.append(check_stray(name, dest, files, repo))
            if (src / "SKILL.md").is_file():
                findings.append(check_sync(name, collect(src), files))
            built.append(name)
            continue
        if not src.is_dir() or not (src / "SKILL.md").is_file():
            if required:
                print(f"[{name}] ERROR: source skill not found at {src.as_posix()}", file=sys.stderr)
                return 2
            print(f"[{name}] source not found at {src.as_posix()}; building only the Turkish plugin")
            continue
        files = collect(src)
        if dry_run:
            print(f"[{name}] would copy {len(files)} files -> {dest_rel}")
            views[name] = files
            planned_sources.extend(files.values())
        else:
            copy_edition(files, dest)
            lic = f" (+ {LICENSE_NAME} into plugins/{name}/)" if copy_license(repo, name) else ""
            views[name] = {rel: dest / rel for rel in files}
            print(f"[{name}] copied {len(files)} files -> {dest_rel}{lic}")
        built.append(name)

    for name, files in views.items():
        findings.extend(check_edition(name, files, rows, personal))

    tree = repo_files(repo)
    if dry_run:
        tree = [p for p in tree if "skills" not in p.relative_to(repo).parts] + planned_sources
    findings.append(check_crlf_bom(tree, (repo, src_root), "whole tree"))
    findings.append(check_tree_personal(tree, personal, repo))

    if "skill-bulucu" in views and "skill-sleuth" in views:
        findings.append(check_identical(views["skill-bulucu"], views["skill-sleuth"]))
    else:
        findings.append(Finding("SKIP", "scripts/*.py + builtins.json identical across plugins",
                                "only one plugin in this run"))

    findings.extend(check_manifests(repo, built, dry_run))
    findings.extend(check_license(repo, built, dry_run))

    # --- report ---------------------------------------------------------------------------
    print("\nSize limits")
    print(f"  {'plugin':<14} {'file':<40} {'bytes':>7} {'limit':>7}  status")
    for plugin, label_, size, limit, status in rows:
        print(f"  {plugin:<14} {label_:<40} {str(size):>7} {limit:>7}  {status}")
    print("\nChecks")
    for f in findings:
        line = f"  {f.status:<5} {f.check}"
        if f.detail:
            line += f" -- {f.detail}"
        print(line)
    failures = [f for f in findings if f.status == "FAIL"]
    warnings = [f for f in findings if f.status == "WARN"]
    verb = "checked" if check else "planned" if dry_run else "built"
    print(f"\nRESULT: {'FAIL' if failures else 'PASS'} ({len(failures)} failure(s), {len(warnings)} warning(s); "
          f"{verb}: {', '.join(built) or 'nothing'})")
    if want_zip and not failures and not dry_run:
        zip_dir = Path(args.zip) if args.zip else repo / DIST_DIR / f"v{changelog_version(repo)[0]}"
        stamp = "%04d-%02d-%02d %02d:%02d:%02d UTC" % date_time
        print(f"\nZips (SHA-256; entries dated {stamp}, deflate {ZIP_LEVEL}, zlib {zlib.ZLIB_RUNTIME_VERSION})")
        for line in write_zips({n: views[n] for n in built}, zip_dir.resolve(), date_time):
            print(f"  {line}")
    elif want_zip:
        print(f"\nZips not written ({'dry run' if dry_run else 'checks failed'})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
