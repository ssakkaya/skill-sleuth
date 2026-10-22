# Security policy

Türkçesi aşağıda.

## Reporting a vulnerability

Report security problems privately: [Report a vulnerability](https://github.com/ssakkaya/skill-sleuth/security/advisories/new) (the **Security and quality** tab of this repository). Please do not use public issues for them. This is a one-person project; reports are read as soon as possible.

In scope:

- the skill installing, enabling, copying or changing settings without the numbered consent it promises, or at all in an unattended run (`claude -p`, scheduled task, subagent);
- `scripts/dis_kaynak_ara.py` sending anything beyond what the README lists, or contacting hosts other than `skills.sh`, `api.github.com` and `raw.githubusercontent.com`;
- text inside a third-party skill's description, SKILL.md, catalog entry or tool output that makes the skill follow it (prompt injection);
- a script trusting a cache folder or file that another local user could plant or replace (cache poisoning), or following a symlinked temporary file;
- a script writing outside its cache folder (or the folder you name with `--out`, `--cache-dir` or `$DIS_KAYNAK_CACHE_DIR`, or the folder of the file you name with `--cache` or `$SKILL_ARA_CACHE`), or into a Claude config tree (`.claude`, `~/.claude.json`, `$CLAUDE_CONFIG_DIR`, `$CLAUDE_CODE_PLUGIN_CACHE_DIR`), or `skill_ara.py` replacing a file that is not its own index, or starting any program at all (no script starts one).

Out of scope: problems in third-party skills that this skill shows you. Report those to their authors.

Only the latest release is supported.

## Güvenlik açığı bildirme

Güvenlik sorunlarını gizli bildirin: [Report a vulnerability](https://github.com/ssakkaya/skill-sleuth/security/advisories/new) (bu reponun **Security and quality** sekmesi). Lütfen herkese açık issue kullanmayın. Projeyi tek kişi yürütüyor; bildirimler en kısa sürede okunur.

Kapsamda:

- skill'in söz verdiği numaralı onay olmadan kurması, etkinleştirmesi, kopyalaması ya da ayar değiştirmesi, ya da gözetimsiz bir koşuda (`claude -p`, zamanlanmış görev, alt ajan) bunlardan birini yapması;
- `scripts/dis_kaynak_ara.py`'nin README'de belirtilenden fazlasını göndermesi ya da `skills.sh`, `api.github.com` ve `raw.githubusercontent.com` dışında bir host'a bağlanması;
- skill'in, üçüncü taraf bir skill'in açıklamasındaki, SKILL.md'sindeki, katalog kaydındaki ya da araç çıktısındaki bir metni talimat sayıp izlemesi (prompt injection);
- bir script'in, aynı makinedeki başka bir kullanıcının bırakabileceği ya da değiştirebileceği bir önbellek klasörüne veya dosyasına güvenmesi (önbellek zehirlenmesi) ya da sembolik bağlantılı bir geçici dosyayı izlemesi;
- bir script'in önbellek klasörü (ya da `--out`, `--cache-dir` veya `$DIS_KAYNAK_CACHE_DIR` ile verdiğiniz klasör ya da `--cache` veya `$SKILL_ARA_CACHE` ile verdiğiniz dosyanın klasörü) dışına ya da bir Claude ayar ağacına (`.claude`, `~/.claude.json`, `$CLAUDE_CONFIG_DIR`, `$CLAUDE_CODE_PLUGIN_CACHE_DIR`) yazması, `skill_ara.py`'nin kendi indeksi olmayan bir dosyanın üzerine yazması ya da herhangi bir program başlatması (hiçbir script program başlatmaz).

Kapsam dışı: bu skill'in size gösterdiği üçüncü taraf skill'lerdeki sorunlar. Onları yazarlarına bildirin.

Yalnız son sürüm desteklenir.
