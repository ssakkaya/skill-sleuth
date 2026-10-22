# Komutlar: ikili, plugin CLI, slash komutları, settings.json, claude.ai, kopyalama, Windows

## Ne zaman oku
- Bir skill/plugin'i kurmaya, açmaya, kopyalamaya ya da kurulmamış bir plugin'in envanterine bakmaya karar verdiğinde.
- Kullanıcıya `/reload-plugins`, `/reload-skills` veya claude.ai adımlarını söylemen gerektiğinde (hazır cümleler §3 ve
  §5).
- Bash/PowerShell'de `claude` ya da `python` kodlama/yol hatası verdiğinde ya da Python hiç bulunamadığında (§7).

İçindekiler: §1 İkili · §2 Komutlar · §3 Slash · §4 settings.json · §5 claude.ai · §6 Kopyalama · §7 Windows

Kısaltmalar: `MKT` = `~/.claude/plugins/marketplaces/claude-plugins-official`, `LAMS` =
`<veri>/local-agent-mode-sessions`. "(doğrulanmadı)" = açık soru; hedge'le. "Ölçüm ortamı" = Windows 11, masaüstü
uygulaması, 2026-10.

Dizin kuralı (çevrimdışı script'ler `skill_ara.py`, `skill_envanteri.py`, `katalog_indeksle.py` aynısını uygular):
- `<veri>` = masaüstü uygulamasının veri dizini: `CLAUDE_DESKTOP_DATA_DIR` ayarlıysa olduğu gibi o; yoksa Windows'ta
  `local-agent-mode-sessions` klasörü olan ilki: `%APPDATA%/Claude`; `%LOCALAPPDATA%/Claude-Data/<id>` (2026-10-22
  gözlendi; birden çoksa `local-agent-mode-sessions`'ı en son değişen);
  `%LOCALAPPDATA%/Packages/Claude_<suffix>/LocalCache/Roaming/Claude` (MSIX, 2026-10-14 gözlendi); hiçbiri yoksa
  `%APPDATA%/Claude`. macOS `~/Library/Application Support/Claude` (doğrulanmadı); Linux `$XDG_CONFIG_HOME/Claude`,
  o da yoksa `~/.config/Claude` (doğrulanmadı). macOS ve Linux konumları gerçek makinede sınanmadı.
- `~/.claude` = Claude Code yapılandırma dizini: her işletim sisteminde `$CLAUDE_CONFIG_DIR`, ayarlı değilse
  `~/.claude`. Bu dosyada `~/.claude/...` diye yazılan her yol bu kurala göre çözülür.
- `<plugins>` = plugin kökü: `$CLAUDE_CODE_PLUGIN_CACHE_DIR` ayarlıysa o, değilse `~/.claude/plugins` (yukarıdaki kuralla).
  Bu dosyada `~/.claude/plugins/...` diye yazılan yollar (`installed_plugins.json`, `cache/`, `marketplaces/`,
  `plugin-catalog-cache.json`) `<plugins>` altındadır.
- Önbellek: Windows'ta %TEMP%\skill-sleuth (Python `tempfile.gettempdir()`; `%TEMP%` kullanıcıya özeldir), macOS/Linux'ta
  ~/.cache/skill-sleuth (`$XDG_CACHE_HOME` ayarlıysa `$XDG_CACHE_HOME/skill-sleuth`; 0700 izinle kurulur). Sahibi geçerli
  kullanıcı olmayan ya da grup / herkes yazabilen önbellek dizini ya da dosyası kullanılmaz, symlink'li geçici dosya
  izlenmez: script çökmez, önbelleksiz sürer ve uyarır. `$SKILL_ARA_CACHE`, `$DIS_KAYNAK_CACHE_DIR`, `--cache`,
  `--cache-dir`, `--out` geçerli kalır; macOS/Linux'ta da sahiplik/izin kuralına tabidir (`skill_ara` 0.6.0,
  `dis_kaynak_ara` 0.4.0).

## 1. İkili seçimi: hangi `claude` çalışacak

Bir makinede iki ikili olabilir: masaüstü oturumunun gerçekten çalıştırdığı paket ikilisi (`CLAUDE_CODE_EXECPATH`;
`<veri>/claude-code/<sürüm>/` altında, 2.1.286+ sürüm dizininin altında bir hash alt dizini olabilir) ve PATH'teki npm
kurulumu (daha eski olabilir; ölçüm ortamında paket **2.1.284-2.1.286**, npm **2.1.217** idi). `install` için
`-y`/`--json`/`--accept-command` yalnız ≥2.1.271 ikilide var (ölçüm ortamında yalnız paket ikilisi); bu yüzden önce
ortam değişkenini kullan. Sürümü komut çalıştırmadan öğren: `AI_AGENT=claude-code_2-1-286_agent` gibi (Bash: `echo
$AI_AGENT`).

Bash aracı (Windows; ölçüm ortamında doğrulandı; ters eğik çizgili yol `[ -x ]` testinden geçer):
```bash
EXE="${CLAUDE_CODE_EXECPATH:-}"
[ -x "$EXE" ] || EXE="$(ls -t "$APPDATA"/Claude/claude-code/*/claude.exe "$APPDATA"/Claude/claude-code/*/*/claude.exe "$LOCALAPPDATA"/Claude-Data/*/claude-code/*/*/claude.exe 2>/dev/null | head -1)"   # masaüstü paketi; 2.1.286+ bir hash alt dizini ekledi; Claude-Data 2026-10-22 gözlendi
[ -x "$EXE" ] || EXE="$(command -v claude)"      # eski npm ikilisi (< 2.1.271): -y/--json yok, metni ayrıştır (§2 N6)
"$EXE" --version
```
macOS/Linux: `CLAUDE_CODE_EXECPATH` yoksa aynı blok `command -v claude`'a düşer; paket ikilisinin `<veri>` altındaki
yeri bu sistemlerde (doğrulanmadı).

PowerShell aracı (Windows PowerShell 5.1 ile doğrulandı; ölçüm ortamında PowerShell aracının kendisi iki oturumda çıkış
kodu 1 verdi, sorun olursa Bash'e geç):
```powershell
$EXE = $env:CLAUDE_CODE_EXECPATH
if (-not ($EXE -and (Test-Path $EXE))) { $EXE = (Get-ChildItem "$env:APPDATA\Claude\claude-code","$env:LOCALAPPDATA\Claude-Data\*\claude-code" -Recurse -Filter claude.exe -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName }
if (-not (Test-Path $EXE)) { $EXE = (Get-Command claude).Source }   # npm kurulumu (eski olabilir)
& $EXE --version
```
2026-10-14'te `CLAUDE_CODE_EXECPATH` MSIX yolu (`...\Packages\Claude_<suffix>\LocalCache\Roaming\...`) ile Roaming
kopyası aynı dosyaydı. 2026-10-22'de (gözlendi) uygulama verisini `%LOCALAPPDATA%\Claude-Data\<id>\` altına taşıdı:
`CLAUDE_CODE_EXECPATH` oradaki `claude-code\<sürüm>\<hash>\claude.exe`'yi gösterir, eski iki klasörde yalnız boş bir
`.user-data-left.<id>` işaret dosyası kalır. İki blok da hem `%APPDATA%\Claude` hem `%LOCALAPPDATA%\Claude-Data\<id>`
altına bakar.

## 2. Komut tablosu (`claude plugin …`; `claude plugins` takma ad)

Aşağıda `claude` = §1'deki `"$EXE"`. "Oturum" sütunu = değişiklik çalışan oturuma ne zaman girer; `/reload-plugins` =
kullanıcı yazar ya da yeni oturum (MCP sunucusu içeren plugin: yalnız yeni oturum).

| Komut | Diskte ne değişir | Çıktı / çıkış | Oturum | Onay |
|---|---|---|---|---|
| `plugin list [--json]` | yok (npm: `.in_use/<pid>` izi) | JSON dizi → N1 | — | hayır |
| `plugin list --json --available` | yok, ağ yok | `{installed,available}`, büyük (ölçümde 142 KB) → N2 | — | hayır |
| `plugin details <ad>@<market>` (kurulu) | yok | envanter + `Always-on ~N tok`; çıkış 0 | — | hayır |
| aynı, kurulmamış plugin | yok | `Plugin "…" not found`, çıkış 1 → N3 | — | hayır |
| `--plugin-dir MKT/plugins/<ad> plugin details <ad>` | yok | aynı envanter, kaynak `<ad>@inline` | — | hayır |
| `plugin install <ad>@<market> -s user\|project\|local --json` | N4 | son satır JSON → N5 | `/reload-plugins` | **evet** |
| `plugin uninstall <ad>@<market> [-s] --json` | kayıt + `enabledPlugins` silinir → N8 | JSON | aynı | evet |
| `plugin enable\|disable <ad>@<market> [-s] --json` | `enabledPlugins` değeri | JSON | aynı | evet |
| `plugin marketplace update [ad]` | clone git fetch; `known_marketplaces.json` | metin | — | evet (ağ) |
| `plugin marketplace add <kaynak>` | `extraKnownMarketplaces`, `known_marketplaces.json`, clone | metin | — | evet |
| `plugin marketplace remove <ad>` | marketplace kaydı + o marketplace'ten kurulan HER plugin kaldırılır, `enabledPlugins` girişleri silinir | metin | `/reload-plugins` | **evet** (geri alma cümlesinde bunu söyle) |
| `plugin update <ad>@<market>` | yeni sürüm cache'e; topluluk ve üçüncü taraf marketplace'lerinde güncellemenin yolu (otomatik güncelleme varsayılan kapalı) | metin | `/reload-plugins` | evet (yeni sha'yı önce incele) |
| `plugin prune` | kendiliğinden kurulup artık hiçbir plugin'in gerekmediği bağımlılıklar kaldırılır | metin | `/reload-plugins` | evet |
| `plugin validate <yol> [--json] [--strict]` | yok | → N7 | — | hayır |
| `plugin init <ad>` | `~/.claude/skills/<ad>/` plugin iskeleti (`@skills-dir`) | metin | sonraki oturum | evet |

Notlar:
- **N1** `list --json`: `[{id, version, scope, enabled, installPath, installedAt, lastUpdated}]`. Metin modunda gruplar:
  Installed / Session-only / Skills-directory / Synced. Kurulu ≠ etkin: etkinlik `enabledPlugins`'tan gelir.
- **N2** `--available`: clone'daki `marketplace.json`'dan okur (kurulular hariç; ölçüm ortamında 2026-07 tarihli clone,
  254 kayıt), ağa çıkmaz.
  Alanlar `pluginId,name,description,marketplaceName,source,installCount,version?`. Bağlama basma; Python ile süz:
  ```bash
  "$EXE" plugin list --json --available | python -c \
    "import json,sys; d=json.load(sys.stdin); print([p['pluginId'] for p in d['available'] if 'AD' in p['name']])"
  ```
  Daha yeni ve zengin veri (bileşenler, hook/MCP adları, token maliyeti; ölçüm tarihinde 315 plugin)
  `~/.claude/plugins/plugin-catalog-cache.json`'da; `skill_ara.py` bunu zaten okur, elle açma.
- **N3** `details` kurulmamış plugin'i reddeder (2.1.217 ve 2.1.284 aynı). Çözüm: üst düzey `--plugin-dir` bayrağı, alt
  komuttan ÖNCE (`plugin details --plugin-dir X` → `unknown option`). Yalnız clone'da dosyası olan plugin'ler için
  (`./plugins/*`, `./external_plugins/*`); `git-subdir`/`url` kaynaklılar için katalog önbelleğine bak.
  Klasör-of-plugins biçimi de çalışır: `--plugin-dir MKT/plugins plugin details <ad>`. Durum değiştirmez (diff ile
  doğrulandı).
- **N4** `install` diskte: `~/.claude/plugins/cache/<market>/<ad>/<sha12>/`, `installed_plugins.json` kaydı; plugin'in bildirdiği
  bağımlılıklar da aynı kapsamda kurulur ve etkinleşir (başarı mesajı sayar; başka marketplace'ten olan yalnız izin listesindeyse),
  `enabledPlugins` → `-s user`: `~/.claude/settings.json` · `-s project`: `<cwd>/.claude/settings.json` · `-s local`:
  `<cwd>/.claude/settings.local.json`. `<ad>@<market>` biçimi önce clone'u git ile yeniler (son 30 sn'de yenilenmediyse;
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` atlatır ama bayat sürüm kurar); `known_marketplaces.json.lastUpdated` ve
  clone HEAD değişir. Kurulum provası onay kanalı olmadığı için yapılmadı: `-s local`'in `.claude/settings.local.json`'ı
  sessizce oluşturması ve yenilemenin clone'u güncel sha'ya taşıması (doğrulanmadı). `-s user`'ı sessizce kullanma;
  kapsamı kullanıcıya numaralı seçenekle sor.
- **N5** `--json`: yalnız SON stdout satırını ayrıştır: `{command, outcome:"ok"|"failed", message, pluginId, scope,
  failureCode?, shownCommand?, alreadyInGoalState?}` (ikili dizgileri + doküman; gerçek başarı yükü doğrulanmadı).
  `failureCode` sözlüğü: `already_in_goal_state` (başarı say; gerekirse `enable`), `not_installed_at_scope`,
  `settings_still_on` (uninstall; ≥2.1.282), `not_found`, `not_found_stale_catalog`, `marketplace_refresh_failed`,
  `command_source_refused|declined`, `entry_helper_unconfirmed|declined`, `settings_write_failed`, `op_failed`.
  `shownCommand` varsa DUR → N6.
- **N6** `Kat()` kapısı: Bash aracında `CLAUDECODE=1` ve `CLAUDE_CODE_CHILD_SESSION=1` ayarlı, TTY yok →
  `command`/`headersHelper` kaynaklı plugin'de `-y` ve `--accept-command` yok sayılır ("is ignored inside a Claude Code
  session"), çıkış 1. Ortam değişkenlerini ASLA kaldırma; komutu ve `shownCommand.sha256`'yı kullanıcıya ver: kendi
  terminalinde `claude plugin install <ad>@<market> --accept-command <sha256>`. Resmi marketplace'te böyle girdi yok
  (ölçüm tarihinde 0/315), yani resmi kurulumlar bu kapıya takılmaz. Eski npm ikilisi (< 2.1.271; ör. 2.1.217) yedeği:
  `install`'da `-y`/`--json` yok → stdout'ta
  `Successfully installed plugin:` / `is already installed` ara; `list --json --available`, `--plugin-dir … details`,
  `validate --strict` iki sürümde de çalışır.
- **N7** `validate`: manifest ya da `skills/` içeren dizin ister; doğrudan SKILL.md içeren klasörü reddeder (`No
  manifest found`, çıkış 1); yalnız eksik `description`'ı uyarır, kötü adı, `<>`'yi, bilinmeyen anahtarı YAKALAMAZ →
  `quick_validate.py` yerine geçmez. `init` iskeleti "auto-loads next session"; aynı oturumda canlı yüklenmesi
  (doğrulanmadı).
- **N8** `uninstall`: `data/<id>` silinir (`--keep-data` hariç); cache dizinine `.orphaned_at` yazılır, 14 gün sonra
  arka planda temizlenir; `--prune` TTY yokken `-y` ister ve `--json` ile birleşmez. `update <ad>`: "Restart to apply" →
  yeni oturum.
- Tek-oturumluk yükleme: `claude --plugin-dir <dizin|.zip>` (`<ad>@inline`), `--plugin-url <zip>`,
  `CLAUDE_CODE_PLUGIN_DIRS` (≥2.1.280, Windows'ta `;` ayraç). Çalışan oturumu etkilemez; iç içe `claude -p` ücret +
  `synced/` yan etkisi getirir, kaçın.

## 3. Yalnız kullanıcının yazabileceği slash komutları

Bunlar `Skill` aracıyla çağrılamaz ve listede yoktur; kullanıcı istem kutusuna yazar. Desktop UI yolu: **+ → Plugins →
Add plugin / Manage plugins**; `/` ya da **+ → Slash commands** menüsü.

| Komut | Ne yapar | Söylenecek cümle (birebir) |
|---|---|---|
| `/reload-plugins [--force]` | plugin katmanını yeniler; `Reloaded: N plugins · N skills · …` basar | C1 |
| `/reload-skills` | skill dizinlerini yeniden tarar; eklenen/çıkan sayısını basar | C2 |
| `/plugin`, `/plugin install <ad>@<market>` | Discover paneli; ayrıntı panelini açar, kapsam seçilince kurar | C3 |
| `/skills` | görünürlüğü `skillOverrides`'a yazar: on / name-only / user-invocable-only / off | C4 |

- C1 (install/enable/disable/uninstall sonrası): "Kurulum tamam. Lütfen istem kutusuna `/reload-plugins` yazıp gönder;
  `Reloaded: …` satırını görünce `<plugin>:<skill>`'i çağıracağım. Plugin MCP sunucusu içeriyorsa yeni oturum gerekir."
  Gerçekler: desktop/`-p`'de yalnız kullanıcı yazarsa çalışır (≥2.1.260); Remote Control/Slack üzerinden gelirse "isn't
  available over a remote connection"; MCP değişikliklerini uygulamaz. Plugin kurulumunun hot-reload'u gözlenmedi.
- C2 (`<cwd>/.claude/skills/` oturum başında yokken oluşturduysan): "Skill'i `<cwd>/.claude/skills/<ad>/` altına koydum
  ama bu dizin oturum başında yoktu. Lütfen `/reload-skills` yaz, sonra devam edeyim." Desktop istem kutusunda
  terminaldeki gibi davranması (doğrulanmadı) — çalışmazsa kişisel katmana (§6) geç.
- C3: "İstersen `/plugin` yazıp Discover'dan `<ad>`'i kendin de kurabilirsin; kapsam seçince kurar." `/plugin` `-p`
  modunda yok.
- C4: "Skill listede görünmüyorsa `/skills` yazıp `<ad>` için görünürlüğü `on` yap." Diğerleri: `/skill-doctor`,
  `/context`, `/doctor`, `/mcp` — tanı için; yalnız kullanıcı yazar.

## 4. `settings.json` anahtarları (skill için salt okunur)

Dosya: `~/.claude/settings.json` (her anahtar isteğe bağlıdır; yeni bir kurulumda `skillOverrides`, `permissions`,
`hooks` hiç olmayabilir). `enabledPlugins`'i user < project < local sırasıyla (BOM'lu dosya da) birleştirip oku. Yalnız cwd'deki dosyaları
okur; macOS/Linux'ta git kökündeki `settings.local.json`'ı da sayan tam görünüm: `skill_ara.py --show <plugin>`:

```bash
PYTHONUTF8=1 python -c "import json,os;d=os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude');e={};[e.update(json.load(open(f,encoding='utf-8-sig')).get('enabledPlugins') or {}) for f in (os.path.join(d,'settings.json'),'.claude/settings.json','.claude/settings.local.json') if os.path.isfile(f)];print(e)"
```

Kural: bu dosyayı ve `.claude/settings*.json`'ı asla doğrudan yazma. Değişiklik gerekiyorsa o turda numaralı onay al;
yazmayı `claude plugin …` komutuna ya da `update-config` built-in'ine bırak.

| Anahtar | Biçim | Kim yazar | Not |
|---|---|---|---|
| `enabledPlugins` | `{"<ad>@<market>": true\|false}` | `plugin install/enable/disable` | öncelik: altta |
| `extraKnownMarketplaces` | `{ad: {source, autoUpdate?}}` | `plugin marketplace add` | kalıcı ayar + ağ → onay |
| `skillOverrides` | `{ad: on\|name-only\|user-invocable-only\|off}` | `/skills` (kullanıcı) | plugin skill'ine işlemez |

`enabledPlugins` önceliği: `--add-dir` < user < project < local < `--settings` < managed; yalnız project dosyasında
`true` olan uzak plugin indirilmez. İlgili diğer anahtarlar: `skillListingBudgetFraction` (0.01),
`skillListingMaxDescChars` (1536), `syncClaudeAiSkills`/`syncClaudeAiPlugins` (`false` → `.trash/`),
`permissions.allow/deny` (`Skill(ad)` kuralları), `disableSkillShellExecution`. Diğer kayıt dosyaları:
`~/.claude/plugins/installed_plugins.json` (v2), `known_marketplaces.json` — ikisi de salt okunur.

## 5. claude.ai tarafı (kullanıcı yapar)

Claude hesap ayarını değiştiremez; yalnız kart gösterir (`SuggestSkills`/`SuggestPluginInstall`, öğe başına en fazla bir
kez) ve adımı söyler. Cümle: "Bunu ben açamam. claude.ai'de **Customize > Skills** (plugin için **Customize > Plugins**)
sayfasından `<ad>`'i aç; senkron yaklaşık 10 dakika sürer, gelmezse yeni oturum aç. Ben o sırada görevi doğrudan
sürdürüyorum."

- Skill açma: **Customize > Skills** → toggle. Ön koşul **Settings > Capabilities > Code execution and file creation**.
  "Disabled skills won't be available to Claude." Açık skill'ler aynı hesapla Claude Code'a da gelir (terminal
  ≥2.1.273).
- Skill yükleme: **Customize > Skills > + > Upload a skill** → zip; tepe klasör = skill adı (`<ad>/SKILL.md`).
- Plugin: **Customize > Plugins** → Discover / Add marketplace (`owner/repo`) / Upload plugin (.zip/.plugin; 25
  marketplace, 5.000 dosya / 200 MB). Claude Code'a `<ad>@synced` olarak gelir; CLI ile kurulanlar hesaba eklenmez.
- Platform: skill'ler her yerde; agent/hook yalnız Cowork + Claude Code; yerel MCP yalnız Cowork (yerel) + Claude Code;
  `bin/`, LSP, output style yalnız Claude Code.
- Konektör (claude.ai konektör dizini; `kaynaklar.md` satır 17): bağlamayı kullanıcı yapar, `suggest_connectors`
  kartındaki (görev başına en fazla bir kart) Connect ve hizmet gösterirse kendi izin (OAuth) ekranıyla (her hizmetin
  izin ekranı gösterdiği doğrulanmadı). Claude bağlamaz, açmaz, token ya da kimlik bilgisi istemez. Kartla bağlananın
  çalışan oturuma gelip gelmediği doğrulanmadı; gelmezse yeni oturum. Hesapta bağlı ama bu oturumda kapalıysa kullanıcı
  oturumun konektör ayarlarından ya da yeni oturumda açar (doğrulanmadı). Yetki bekleyen sunucu (sistem notundaki
  "require authentication"): claude.ai konektör ayarları ya da `/mcp` (SKILL.md Adım 1). Bağlanamayan sunucu (sistem
  notundaki "configured but failed to connect"): "<sunucu> bağlanamadı; `/mcp` ile ya da claude.ai konektör
  ayarlarından onar ya da yeniden dene" de; onarım `/mcp` ve `ai-tools-setup`'ındır; dizin araması ve kart yok.

`synced/` klasörü gerçekleri:
- Yol `~/.claude/skills/synced/<org>_<account>/<ad>/SKILL.md` + `manifest.json`
  (`skillId,name,description,source,updatedAt`); Skill listesinde `anthropic-skills:<ad>` olarak görünür.
- ~10 dk'da bir yenilenir (doküman değeri; ölçülmedi) ve senkron üzerine yazar → **asla elle düzenleme**,
  oraya skill kopyalama; `synced` ve `anthropic-skills` adları rezerve.
- Ölçüm ortamında `~/.claude/plugins/synced/` boş kaldı; claude.ai plugin'lerinin (ör. `legal:*`, `data:*`) terminale
  senkronu (doğrulanmadı). Terminal modunda bu skill'leri `<veri>/rpm/<account8>/<org8>/plugin_<id>/skills/<ad>/SKILL.md`
  (2026-10-22 gözlendi; `<account8>` / `<org8>` = kimliklerin ilk 8 onaltılık hanesi) ya da eski
  `LAMS/<account>/<org>/rpm/plugin_<id>/skills/<ad>/SKILL.md` yolundan oku (`LAMS` = `<veri>/local-agent-mode-sessions`,
  yukarıdaki dizin kuralı).
- Hesapta kapalı/yüklenmemiş skill'ler diskte yok; yalnız `SearchSkills` görür (`enabled:false`).

## 6. Skill klasörünü `~/.claude/skills/<ad>/` altına kopyalama

Kullanıcı dizinine yazmak onay ister: o turda numaralı seçenek sun, açık "evet" gelmeden kopyalama. Neden kişisel
katman? `~/.claude/skills/` oturum başında var ve canlı izleniyor; proje katmanı ise dizin sonradan oluşturulduğunda
canlı değil.

```bash
cp -r "<kaynak>" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/<ad>"            # Bash
```
```powershell
Copy-Item -Recurse "<kaynak>" "$env:USERPROFILE\.claude\skills\<ad>"   # PowerShell; CLAUDE_CONFIG_DIR ayarlıysa "$env:CLAUDE_CONFIG_DIR\skills\<ad>"
```
- İçerik: yalnız `SKILL.md` + `references/` + `scripts/` + `assets/`. `evals/` kopyalama. `.claude-plugin/plugin.json`
  EKLEME (`@skills-dir` plugin'e döner, sonraki oturuma kalır). Klasör adı = frontmatter `name` = kebab-case; listede
  klasör adı görünür.
- Yokla, varsayma: `Skill("<ad>")` ~10 sn aralıkla, en çok 60 sn (ölçüm ortamında: 12 sn'de bilinmiyor, 40 sn'de yüklü;
  diğerleri ≤25 sn).
  - `Launching skill: <ad>` → yüklendi; gövde `Base directory for this skill: <yol>` ile gelir.
  - `Unknown skill: <ad>` (öneri yok) → henüz kayıtlı değil, yoklamaya devam.
  - `Unknown skill: X. Did you mean Y?` → `Y` kayıtlı; yalnız kopyaladığın klasörün adıysa (önek farkı hariç) onu çağır;
    başka bir skill'se yoklamaya devam, 60 sn sonra A yolu.
  - "The following skills are available…" bildirimi → kayıtlı, hemen çağır.
- Proje katmanı yalnız `test -d "<cwd>/.claude/skills"` oturum başında doğruysa ve skill repo ile gitmeliyse; aksi halde
  C2.
- 60 sn içinde gelmezse: SKILL.md'yi oku, kendine `Base directory for this skill: <yol>` de, göreli yolları o dizine
  göre çöz ve uygula; kullanıcıya bir kez `/reload-skills`'i söyle.
- Düzenleme canlı (≤19 sn), silme canlı ve sessiz (~30 sn). Bare modda izleyici yok. `synced/` altına dokunma.

## 7. Windows tuzakları

Script çağrısının iki kabuktaki biçimi (başka biçim kullanma):
```text
Bash:       PYTHONUTF8=1 python "<skill_dir>/scripts/skill_ara.py" --query "..."
PowerShell: $env:PYTHONUTF8=1; python "<skill_dir>\scripts\skill_ara.py" --query "..."
```

| Tuzak | Belirti | Yap |
|---|---|---|
| Kodlama cp1254 | mojibake; `Ş`/`Ğ` → `UnicodeDecodeError` | her Python çağrısından önce `PYTHONUTF8=1` |
| `PYTHONIOENCODING` tek başına | stdout düzelir, `read_text()` düzelmez | yine `PYTHONUTF8=1` |
| `python3` | Microsoft Store stub'ı, "Python bulunamadı" | her sistemde sıra `python` → `python3`, Windows'ta en son `py -3`; `python` Python 2 ise (macOS / Linux) `python3`; ayrıntı aşağıda |
| Python içinde `/c/…` yolu | dosya bulunamaz | `C:/…` ileri eğik çizgi |
| Boşluklu yol | kabuk böler | her yolu çift tırnakla |
| PowerShell'de `VAR=x cmd` | sözdizimi hatası | `$env:VAR='x'; cmd` (üstteki blok) |
| PowerShell aracı | çıkış kodu 1, çıktı yok (ölçüm ortamında iki oturumda) | Bash'i tercih et (üstteki blok) |
| Bash heredoc `<<EOF` | `$` genişler, içerik bozulur | `<<'EOF'` tek tırnaklı sınırlayıcı |
| Bash aracı + apostroflu heredoc | "unexpected EOF" (ölçüm ortamında gözlendi) | uzun Türkçe metni Write aracıyla yaz |
| `open`/`xdg-open` | yok | `start "" "<dosya>"` |
| `subprocess.Popen(["claude"])` | `WinError 2` (`claude.CMD`) | `shutil.which("claude")` + `.cmd` çözümle |
| `select.select()` | borularda çalışmaz | okuyucu thread / `for line in proc.stdout` |
| `CLAUDE_CODE_PLUGIN_DIRS` | yol ayracı | `;` (≥2.1.280) |
| `pyyaml` yok | `quick_validate.py` → `No module named 'yaml'` | `pip install pyyaml` komutunu kullanıcı kendisi çalıştırır |

**Python bulunamazsa.** Her işletim sisteminde sırayla `python --version`, `python3 --version` dene. `python` Python 2
veriyorsa (macOS / Linux; doğrulanmadı) `python3`'e geç. Windows'ta yalnız Microsoft Store kısayolu yanıt veriyorsa
(sürüm yerine "Python bulunamadı" ya da Store açılıyor) ya da ikisi de yoksa en son `py -3 --version` dene. Python 3
veren ilk komutla script'leri aynı biçimde çağır (ör. `py -3`: Bash: `PYTHONUTF8=1 py -3 "<skill_dir>/scripts/skill_ara.py" …`;
PowerShell: `$env:PYTHONUTF8=1; py -3 "<skill_dir>\scripts\skill_ara.py" …`). Hiçbiri Python 3 vermiyorsa:
- 2. katmanı (`skill_ara.py`), 5. katmanı (`dis_kaynak_ara.py --query`) ve yıldız / yaş kontrolünü (`--repo`) atla;
  1, 3 ve 4. katmanla sürdür. Kurulu olmayan adayın yıldızı ve yaşı "doğrulanamadı" olur; `dis-kaynaklar.md` §3.1'in
  eleme kuralları aynen uygulanır (kurulumu eşiğin altındaki ya da sayaçsız kaynaktaki aday elenir).
- Teslim bloğunun Atlananlar satırına yaz, ör. `Atlananlar: yerel indeks (2. katman), üçüncü taraf araması (5. katman),
  yıldız/yaş kontrolü — Python bulunamadı`.
- Kullanıcıya Python 3.9 ya da üstünü kurmasını öner (`python` PATH'te olacak biçimde); kurulumu sen yapma, komut
  çalıştırma. Kurulumdan sonraki PATH değişikliği çoğunlukla yeni bir oturum ister (doğrulanmadı).
- Python'u başka yoldan arama (rastgele dizinlerde `python.exe` tarama, indirme); bulunamadı demek yeter.

## 8. İsteğe bağlı: her turda hatırlatma hook'u (doğrulanmadı)

Açıklama tek başına her turu garanti edemez: 2026-10-02 tetikleme ölçümünde (40 sorgu, `claude -p` 2.1.284) listede alan
skill'i açıkça uyan işlerde model "uygun skill'i bul ve kullan" dense bile doğrudan o skill'e gitti (pozitiflerin ~yarısı).
Resmi doküman kuralı: "her seferinde geçerli olması gereken kural → hook". Kullanıcı isterse `~/.claude/settings.json`
içine (yalnız kullanıcı yazar; bu skill settings dosyasına dokunmaz, bkz. §4) şu hook eklenebilir:

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command",
  "command": "echo Hatirlatma: cok adimli is ya da skill/plugin sorusuysa once skill-bulucu skill'ini cagir."}]}]}}
```

Notlar: `UserPromptSubmit` hook'unun stdout'u her istemde Claude'a bağlam olarak eklenir (doküman); denenmedi,
`echo` çıktısının Windows'ta hangi kabuktan geçtiği de doğrulanmadı. Hook kurulumu `update-config`
built-in'inin işidir; bu skill yalnız öneriyi gösterir.
