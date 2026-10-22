# tools/

[Türkçe](#türkçe) · [English](#english)

## Türkçe

### build_yayin.py

Yayın ağacını kaynak skill klasörlerinden kurar ve denetler. Yalnız standart kütüphane; Python 3.9+.

| Komut | Ne yapar | Kim, ne zaman |
|---|---|---|
| `PYTHONUTF8=1 python tools/build_yayin.py` | Kaynaklardan (`../skill-bulucu/`, varsa `../skill-sleuth/`) yalnız `SKILL.md`, `references/`, `scripts/` dosyalarını `plugins/<ad>/skills/<ad>/` altına kopyalar (`evals/`, `__pycache__`, `*.pyc` dışarıda kalır); depo kökündeki `LICENSE`'ı da her `plugins/<ad>/` klasörüne kopyalar, sonra denetler | Sahip, kaynak düzenlendikten sonra |
| `... --dry-run` | Kaynak dosyaları denetler, hiçbir şey yazmaz | Kopyalamadan önce bakmak için |
| `... --check` | Depo içi denetim: ağacı olduğu gibi (üretilmiş skill klasörleri dahil) denetler, hiçbir şey kopyalamaz, 0 ya da 1 ile çıkar | CI, temiz klon, katkıcı |

- Kaynak klasörler deponun yanında yoksa (temiz klon) ve `--source-root` verilmemişse script kendiliğinden `--check` biçimine geçer ve bunu ilk satırda yazar. `--source-root` açıkça verilmiş ama orada kaynak yoksa çıkış 2'dir.
- `--check` kaynakları da yanında bulursa üretilmiş kopyayı kaynakla karşılaştırır; fark varsa `WARN` yazar (başarısızlık sayılmaz; düzeltmek için bayraksız çalıştırın).
- Diğer seçenekler: `--skip-en` İngilizce plugin'i ne kurar ne denetler; `--source-root DIR` kaynakların yeri (varsayılan: deponun üst klasörü); `--repo DIR` kurulacak ya da denetlenecek yayın ağacı (varsayılan: `tools/`'un üst klasörü; testler geçici bir ağaç için kullanır); `--zip [DIR]` denetimler geçerse (`--dry-run` dışında) `DIR/<ad>.zip` ve onunla aynı baytlı `DIR/<ad>.skill` yazar ve SHA-256'larını basar; DIR verilmezse `dist/v<sürüm>/` (`.gitignore`'da, denetlenen ağaca girmez). `--dry-run` ile `--check` birlikte verilemez.
- Çıkış kodları: 0 hepsi geçti · 1 en az bir denetim başarısız · 2 kullanım hatası, Türkçe kaynak yok ya da `SOURCE_DATE_EPOCH` tamsayı değil.
- Ardından: `claude plugin validate . --strict`, `claude plugin validate plugins/skill-bulucu --strict`, `claude plugin validate plugins/skill-sleuth --strict`.

**Denetimler** (her biçimde; biri bile başarısızsa çıkış 1):

- Kişisel veri deseni: skill dosyalarında ve ağaçtaki her metin dosyasında (`dist/` hariç; kullanıcı adı, hesap kimliği, yerel yol; `README`/`LICENSE`/manifestlerdeki `ssakkaya` kapsam dışı).
- Bayt sınırları: `SKILL.md` gövdesi ≤ 17.000; `references/dis-kaynaklar.md` / `external-sources.md` ≤ 9.500; `references/guvenlik-kontrol-listesi.md` / `security-checklist.md` ≤ 11.000; `scripts/README.md` ≤ 16.000.
- Ağaçta (`dist/` hariç) CRLF ya da BOM.
- Frontmatter'da yalnız `name` ve `description`; `name` klasör adıyla aynı.
- İki plugin de varsa `scripts/*.py` ve `builtins.json` bayt bayt aynı.
- `marketplace.json` okunuyor; her plugin'in `plugin.json`'ı ve `skills/<ad>/SKILL.md`'si var.
- Her plugin klasöründeki `LICENSE` depo kökündeki `LICENSE` ile aynı (bayraksız `build_yayin.py` çalıştırması kopyalar; dizin kullanıcıya yalnız plugin klasörünü verir).
- Sürüm tutarlılığı: her `plugins/<ad>/.claude-plugin/plugin.json` sürümü `marketplace.json`'daki girdisininkine eşit (ya da girdide `version` yok) ve `CHANGELOG.md`'deki en üstteki `## x.y.z` başlığına eşit (`## Unreleased` atlanır). İkisi birden yazılınca kurulumda `plugin.json` kazanır (yalnız `claude plugin validate` uyarır); bu yüzden fark burada FAIL'dir. Sürüm yükseltirken aynı commit'te: `plugin.json`, girdide varsa `marketplace.json`, `CHANGELOG.md`'ye yeni `## x.y.z — YYYY-AA-GG` bölümü.
- Yalnız `--check`: üretilmiş skill klasöründe `SKILL.md`, `references/`, `scripts/` dışında dosya.

**Yeni dosyalar da denetlenir.** CRLF/BOM ve kişisel veri denetimleri ağaçtaki (`dist/` dışındaki) her metin dosyasına uygulanır: `.github/workflows/ci.yml`, `tests/` altındaki testler ve test verileri dahil. Testlerde ev klasörü yolu ve CRLF içeren veri dosyaya düz metin olarak yazılmaz, çalışma anında üretilir (`tempfile`, `Path.home()`, `"\r\n".join(...)`, parçalanmış dize). `.gitattributes` bilerek attribute tanımlamaz, yalnız yorum içerir (Claude plugin dizini, dosya içeriğini yeniden yazan attribute'lu depoyu doğrulamaz). Windows'ta LF için klonlarken ayarlayın: `git clone -c core.autocrlf=false <url>` (ya da klonlamadan önce `git config --global core.autocrlf false`); var olan bir klonda önce (ayarı değiştirmeden) değişikliklerinizi commit edin ya da stash'leyin, çünkü `git reset --hard` commit edilmemiş değişiklikleri siler; sonra ayarı yapıp `git rm -r --cached -q .` ve `git reset --hard` ile dosyaları yeniden yazdırın. CI bunu checkout'tan önce ayarlar.

**Kişisel desenler.** Script'te yalnız genel ev klasörü desenleri vardır. Makineye özgü desenler (kullanıcı adı, hesap kimliği, kendi proje yolları) depo dışındaki `<source-root>/yayin-private-patterns.txt` dosyasından ya da `$YAYIN_PRIVATE_PATTERNS` yolundan okunur (satır başına bir regex, `#` yorum). Dosya yoksa (CI, temiz klon) script bunu INFO olarak yazar.

### Yeniden üretilebilir zip'ler

`--zip DIR` aynı dosyalardan her seferinde aynı baytları yazar: girdiler yola göre sıralı; her zaman damgası `$SOURCE_DATE_EPOCH` (UTC, zip aralığına kırpılır; yoksa 1980-01-01 00:00:00); izin 0644 ve Unix ana sistem baytı; deflate düzey 9; ek alan yok. Zip'in tek üst klasörü `<ad>/`'dır (claude.ai yükleme kuralı). Çıktı başlığı tarihi ve zlib sürümünü yazar: SHA-256 aynı zlib ile tekrarlanır, başka bir zlib (ör. zlib-ng) başka sıkıştırılmış bayt verebilir. Kaynak dosyaların değişiklik zamanı, klasör yolu ve işletim sistemi sonucu etkilemez; kaynaklarsız bir klonda `--check --zip DIR` aynı zip'leri depodaki üretilmiş klasörlerden yazar. Her sürüm kendi `dist/v<sürüm>/` klasörüne gider (DIR verilmeyen `--zip`); aynı sürümle yeniden çalıştırmak o klasörü yeniden yazar, bu yüzden yayımlanmış bir sürümden sonra önce sürümü yükseltin.

```
PYTHONUTF8=1 python tools/build_yayin.py --zip
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) PYTHONUTF8=1 python tools/build_yayin.py --check --zip DIR
```

### CI

`.github/workflows/ci.yml` her push ve pull request'te çalışır: ubuntu / macos / windows × Python 3.9 / 3.12, `PYTHONUTF8=1`, `permissions: contents: read`, gizli anahtar yok, ağ yok. Adımlar: `git config --global core.autocrlf false` (checkout'tan önce), `actions/checkout` ve `actions/setup-python` tam commit SHA'sıyla sabit (v7.0.1 ve v7.0.0; 2026-10-10'da sürüm ve etiket sayfalarından doğrulandı), `python tools/build_yayin.py --check`, `python -m unittest discover -s tests -v`. Testler `tests/test_*.py` dosyalarındadır, depo kökünden çalışır ve ağa çıkmaz. Python 3.9'un Windows ve macOS arm64 için son derlemesi 3.9.13'tür; setup-python onu kurar. Bir action'ı güncellerken sürüm sayfasındaki commit SHA'sını alın ve satır sonundaki `# vX.Y.Z` yorumunu da değiştirin.

### builtins.json yenileme rutini

Ayda bir ve her Claude Code güncellemesinden sonra önerilir. Rutin sahibin kaynak ağacında yapılır: aşağıdaki `<source-root>`, kaynak skill klasörlerini (`skill-bulucu/`, `skill-sleuth/`) tutan klasördür (varsayılan olarak bu deponun üst klasörü, bkz. `--source-root`). Depoda yalnız üretilmiş kopya vardır: `plugins/skill-bulucu/skills/skill-bulucu/scripts/`. Onu okumak ve denemek için kullanabilirsiniz (ör. `skill_ara.py --stats`), ama elle düzenlemeyin; `build_yayin.py` onu kaynaktan yeniden yazar.

1. Bir Claude Code oturumunda sürümü not edin (`claude --version`). Skill aracının listesindeki adlardan plugin öneki (`ad:`) olmayanlar built-in adayıdır. Diskte SKILL.md'si olanları ayırın: `PYTHONUTF8=1 python <source-root>/skill-bulucu/scripts/skill_ara.py --show <ad>` `builtin` dışında bir katman (user, project ...) gösteriyorsa o ad built-in değildir.
2. Kalan adları `<source-root>/skill-bulucu/scripts/builtins.json` ile karşılaştırın. Yeni ad için kayıt ekleyin: `name`, `version` (`claude-code <sürüm> (desktop)`), `source` (`keyword summary written for this index; not the skill's own description`), `description`: kendi cümlenizle kısa bir anahtar kelime özeti. Skill'in kendi açıklamasını kopyalamayın (telif; depo MIT lisanslı). Listeden kalkan adı silin.
3. Her kaydın `version` alanını güncel sürüme çekin; dosya biçimini (kayıt başına bir satır, UTF-8, LF, BOM yok) koruyun.
4. Dosyayı İngilizce sürüme bayt bayt kopyalayın (yeniden kaydetmeyin): `cp <source-root>/skill-bulucu/scripts/builtins.json <source-root>/skill-sleuth/scripts/builtins.json`.
5. Sayı ve sürüm atıflarını güncelleyin: `<source-root>/skill-bulucu/scripts/README.md` ve `<source-root>/skill-sleuth/scripts/README.md` (bayt sınırı 16.000; aynı uzunlukta değişiklik), `<source-root>/skill-bulucu/references/kaynaklar.md` ve `<source-root>/skill-sleuth/references/sources.md` (9. katman satırı), bu depodaki `CHANGELOG.md`'nin "Known limitations" satırı.
6. Doğrulayın: `skill_ara.py --stats` `builtin` sayısını gösteriyor, `--query` yeni built-in'i buluyor; sonra depoda `build_yayin.py` (kopyalar, iki sürümün aynılığını denetler) ve `build_yayin.py --check`.

Aynı ziyarette `skill_ara.py --stats` çıktısında plugin ve katalog katmanlarının boş olmadığına da bakın: Claude Code iç dosya biçimini değiştirirse bu katmanlar uyarısız boşalabilir.

## English

### build_yayin.py

Assembles the publication tree from the source skill folders and checks it. Standard library only; Python 3.9+.

| Command | What it does | Who, when |
|---|---|---|
| `PYTHONUTF8=1 python tools/build_yayin.py` | Copies only `SKILL.md`, `references/` and `scripts/` from the sources (`../skill-bulucu/` and, when present, `../skill-sleuth/`) into `plugins/<name>/skills/<name>/` (excluding `evals/`, `__pycache__`, `*.pyc`); also copies the root `LICENSE` into each `plugins/<name>/`, then checks | The owner, after editing the sources |
| `... --dry-run` | Checks the source files, writes nothing | To look before copying |
| `... --check` | In-repo check: checks the tree as it is (generated skill folders included), copies nothing, exits 0 or 1 | CI, a clean clone, contributors |

- When the source folders are not next to the repository (a clean clone) and `--source-root` was not given, the script switches to `--check` by itself and says so on its first line. An explicit `--source-root` without sources is exit 2.
- When `--check` also finds the sources, it compares each generated copy with its source and prints `WARN` on a difference (not a failure; run without flags to rebuild).
- Other options: `--skip-en` neither builds nor checks the English plugin; `--source-root DIR` relocates the sources (default: the folder above the repository); `--repo DIR` is the publication tree to build or check (default: the folder above `tools/`; tests use it for a temporary tree); `--zip [DIR]` writes `DIR/<name>.zip` and a byte-identical `DIR/<name>.skill` after passing checks (not with `--dry-run`) and prints their SHA-256; without DIR it writes to `dist/v<version>/` (git-ignored, outside the checked tree). `--dry-run` and `--check` cannot be combined.
- Exit codes: 0 all checks passed · 1 at least one check failed · 2 usage error, Turkish source missing, or `SOURCE_DATE_EPOCH` not an integer.
- Then run `claude plugin validate . --strict`, `claude plugin validate plugins/skill-bulucu --strict` and `claude plugin validate plugins/skill-sleuth --strict`.

**Checks** (every mode; any failure means exit 1):

- Personal-data patterns in the skill files and in every text file of the tree (`dist/` excluded; user name, account ids, local paths; `ssakkaya` in `README`/`LICENSE`/manifests is out of scope).
- Byte caps: `SKILL.md` body ≤ 17,000; `references/dis-kaynaklar.md` / `external-sources.md` ≤ 9,500; `references/guvenlik-kontrol-listesi.md` / `security-checklist.md` ≤ 11,000; `scripts/README.md` ≤ 16,000.
- CRLF or BOM anywhere in the tree (`dist/` excluded).
- Frontmatter keys only `name` and `description`; `name` equals the folder name.
- When both plugins exist, `scripts/*.py` and `builtins.json` byte-identical between them.
- `marketplace.json` parses; every plugin has its `plugin.json` and `skills/<name>/SKILL.md`.
- Each plugin folder's `LICENSE` equals the repository `LICENSE` (copied by a build; the directory hands users only the plugin folder).
- Version consistency: each `plugins/<name>/.claude-plugin/plugin.json` version equals its `marketplace.json` entry's (or the entry omits `version`) and the topmost `## x.y.z` heading of `CHANGELOG.md` (`## Unreleased` is skipped). When both are set, `plugin.json` wins at install time (only `claude plugin validate` warns), so a mismatch is a FAIL here. To bump, change in one commit: `plugin.json`, `marketplace.json` if its entry has a version, and a new `## x.y.z — YYYY-MM-DD` section in `CHANGELOG.md`.
- `--check` only: files other than `SKILL.md`, `references/`, `scripts/` in a generated skill folder.

**New files are checked too.** The CRLF/BOM and personal-data checks cover every text file of the tree except `dist/`, including `.github/workflows/ci.yml`, the tests under `tests/` and their data. Tests must not store home-folder paths or CRLF data as literal file content; build them at run time (`tempfile`, `Path.home()`, `"\r\n".join(...)`, a split string). `.gitattributes` sets no attributes on purpose, comments only (the Claude plugin directory does not validate a repository whose attributes rewrite file contents). On Windows, set LF at clone time: `git clone -c core.autocrlf=false <url>` (or `git config --global core.autocrlf false` before cloning); in an existing clone, first commit or stash your changes (before changing the setting; `git reset --hard` discards uncommitted changes), then set it and rewrite the files with `git rm -r --cached -q .` and `git reset --hard`. CI sets it before checkout.

**Personal patterns.** The script holds only generic home-folder patterns. Machine-specific ones (user name, account ids, own project paths) are read from `<source-root>/yayin-private-patterns.txt`, outside the repository, or from the path in `$YAYIN_PRIVATE_PATTERNS` (one regex per line, `#` for comments). When the file is missing (CI, a clean clone) the script reports it as INFO.

### Reproducible zips

`--zip DIR` writes the same bytes from the same files every time: entries sorted by path; every timestamp set to `$SOURCE_DATE_EPOCH` (UTC, clamped to the zip range; default 1980-01-01 00:00:00); mode 0644 with a Unix host byte; deflate level 9; no extra fields. The only top-level entry is `<name>/` (the claude.ai upload rule). The output header prints the date and the zlib version: the SHA-256 repeats with the same zlib, while another zlib (e.g. zlib-ng) may compress differently. File modification times, the folder path and the operating system do not change the result; in a clone without sources, `--check --zip DIR` writes the same zips from the generated folders in the repository. Each version gets its own `dist/v<version>/` (`--zip` without DIR); re-running with the same version rewrites that folder, so bump the version once a release is out.

```
PYTHONUTF8=1 python tools/build_yayin.py --zip
SOURCE_DATE_EPOCH=$(git log -1 --format=%ct) PYTHONUTF8=1 python tools/build_yayin.py --check --zip DIR
```

### CI

`.github/workflows/ci.yml` runs on every push and pull request: ubuntu / macos / windows × Python 3.9 / 3.12, `PYTHONUTF8=1`, `permissions: contents: read`, no secrets, no network. Steps: `git config --global core.autocrlf false` (before checkout), `actions/checkout` and `actions/setup-python` pinned to full commit SHAs (v7.0.1 and v7.0.0, checked on their release and tag pages on 2026-10-10), `python tools/build_yayin.py --check`, `python -m unittest discover -s tests -v`. Tests live in `tests/test_*.py`, run from the repository root and stay offline. The last Python 3.9 build for Windows and macOS arm64 is 3.9.13, which setup-python installs there. To update an action, take the commit SHA from its release page and change the trailing `# vX.Y.Z` comment too.

### builtins.json refresh routine

Suggested monthly and after every Claude Code update. The routine is done in the owner's source tree: `<source-root>` below is the folder that holds the source skill folders (`skill-bulucu/`, `skill-sleuth/`; by default the folder above this repository, see `--source-root`). The repository holds only the generated copy, `plugins/skill-bulucu/skills/skill-bulucu/scripts/`. You can read and run it (e.g. `skill_ara.py --stats`), but do not edit it; `build_yayin.py` rewrites it from the source.

1. In a Claude Code session, note the version (`claude --version`). Names in the Skill tool listing without a plugin prefix (`name:`) are built-in candidates. Drop the ones with a SKILL.md on disk: if `PYTHONUTF8=1 python <source-root>/skill-bulucu/scripts/skill_ara.py --show <name>` shows a tier other than `builtin` (user, project ...), the name is not a built-in.
2. Compare the remaining names with `<source-root>/skill-bulucu/scripts/builtins.json`. Add an entry for each new name: `name`, `version` (`claude-code <version> (desktop)`), `source` (`keyword summary written for this index; not the skill's own description`) and `description`, a short keyword summary in your own words. Never copy the skill's own description (copyright; the repository is MIT-licensed). Remove names that left the listing.
3. Set every entry's `version` to the current version; keep the file format (one entry per line, UTF-8, LF, no BOM).
4. Copy the file byte-identically to the English edition (do not re-save it): `cp <source-root>/skill-bulucu/scripts/builtins.json <source-root>/skill-sleuth/scripts/builtins.json`.
5. Update the counts and version mentions: `<source-root>/skill-bulucu/scripts/README.md` and `<source-root>/skill-sleuth/scripts/README.md` (16,000-byte cap; same-length edit), `<source-root>/skill-bulucu/references/kaynaklar.md` and `<source-root>/skill-sleuth/references/sources.md` (tier 9 row), the "Known limitations" line of this repository's `CHANGELOG.md`.
6. Verify: `skill_ara.py --stats` shows the `builtin` count and `--query` finds a new built-in; then, in the repository, `build_yayin.py` (copies, checks identity across the editions) and `build_yayin.py --check`.

On the same visit, check that the plugin and catalog tiers in `skill_ara.py --stats` are not empty: if Claude Code changes its internal file format, those tiers can go empty without a warning.
