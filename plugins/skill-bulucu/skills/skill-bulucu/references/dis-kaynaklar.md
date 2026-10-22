# Dış kaynaklar (katman 5): çekirdek

`dis_kaynak_ara.py` çalıştırmadan ve isabet göstermeden ÖNCE oku; katman 2-3 adayında yalnız §3.1 + §2 madde 4. Ayrıntı: `dis-kaynaklar-ayrinti.md`.

## 1. Kaynaklar

`scripts/dis_kaynak_ara.py` yalnız kimliksiz GET atar.
- skills.sh (T5): skill başına `installs` + denetim kaydı; açıklama, sha, yıldız, yaş yok.
- `claude-community` kataloğu (T4): açıklama, kaynak repo, çoğunda sabit sha; kurulum sayacı ve denetim yok.
- GitHub eksiği tamamlar; API 60 istek/saat (IP başına ortak).

## 2. Onay ve gizlilik

1. Ağa çıkan tek script bu; yalnız aşağıdaki onayla (istisna: madde 4).
2. Ne zaman çalışır:
   - **(a) Açık istek:** kullanıcı bu görevde üçüncü taraf aramasını (skills.sh, GitHub, topluluk) açıkça istedi ya da skill ararken "her yere bak" dedi → sorma; ÖNCE tek satır duyur, sonra çalıştır: `Üçüncü taraf kayıtlarına bakıyorum: "<anahtar kelimeler>" skills.sh'e gider; topluluk kataloğu raw.githubusercontent.com'dan bütün iner, yerelde aranır; GitHub'a yalnız isabet repo adı, yolu, sha'sı gider.` İstek değil: konuda GitHub / topluluk geçmesi, repo URL'si (doğrudan §4), önceki görevin isteği.
   - **(b) Açık skill araması + katman 1-4 boş + iş built-in'lerle düz bitmiyor** (ya da istek yalnız aramaydı) → TEK numaralı soru, turu bitir; "1" gelmeden script yok; "2" → fail-open; bir daha sorma, (c) satırını yazma:
     ```
     Kurulu ve resmi kaynaklarda uygun skill bulamadım. Üçüncü taraf kayıtlarına da bakayım mı? (skills.sh'i Anthropic incelemez; topluluk kataloğunu tarar, onaylar; kodu garanti etmez.)
     1. Bak (skills.sh + topluluk kataloğu; yalnız şu anahtar kelimeler gider: <anahtar kelimeler>)
     2. Bakma, eldekilerle devam
     ```
   - **(c) Örtük iş, built-in'lerin düz yettiği iş (skill sorulsa da), C / B modu, gözetimsiz koşu (istense de), "üçüncü taraf istemiyorum":** ne ara ne sor; ilk ikisinde en çok teslimde `Üçüncü taraf kayıtlarına bakılmadı; istersen bakarım.`
   - Onay o görev ve yalnız arama içindir; kullanım ayrı onaydır (§4).
3. Sorgu = 2-6 genel İNGİLİZCE yetenek kelimesi (ihtiyacı çevir, kopyalama); dosya adı / yolu, kişi / müşteri / proje adı, e-posta, URL, veriden sayı ya da metin ASLA girmez. İyi: `pdf table extract`. Kötü: `acme lojistik sozlesme` (müşteri adı; script yakalamaz). Neden: sorgu üçüncü tarafın günlüğüne düşer. Sorgu skills.sh'e gitmesin isteniyorsa `--source community`.
4. `--repo` arama onayı istemez: yalnız herkese açık repo adı gider; katman 2-3 adayının yıldızı / yaşı bununla alınır (göstereceğin aday başına bir kez, görevde en çok 3; C / B'de, örtük işte ve "ağa çıkma" dendiyse yok: `calisma-modlari.md`). `--query`, `--show`, `--audit` madde 2 onayını ister; kullanıcının verdiği repoda `--show`/`--audit` yok (ad skills.sh'e gider): `--repo` + sabit sha'da raw okuma.

## 3. Sonuç sunumu

Ham çıktıyı basma. §3.1 kurulu olmayan HER adayın (katman 2, 3, 5) etiket / eleme kuralının tek doğruluk kaynağıdır; katman 3 konektörü hariç: sayaç, repo yok → "Yayıncı/Popülerlik/Yaş: dizin vermiyor", `--repo` ve eleme yok.

### 3.1 Sinyaller, etiketler, eleme

Her aday üç satır taşır: Popülerlik (kurulum + yıldız), Yaş (repo oluşturulma + son güncelleme), Etiket (ölçülen değeriyle). Alınamayan sinyal "doğrulanamadı", sayaçsız kaynakta "kurulum verisi yok"; tahmin etme, atlama.

| Etiket | Koşul (varsayılan) |
|---|---|
| `YENI` | repo 90 günden yeni |
| `AZ-KURULUM` | kurulum biliniyor, 1.000'in altında |
| `AZ-YILDIZ` | yıldız 100'ün altında |
| `BAYAT` | son güncelleme 365 günden eski |
| `SKILL-YENI` | yalnız `--show`: skill dosyası 90 günden yeni |
| `ARSIV` | repo arşivlenmiş |

**Elenen** = beş durumdan biri; öteki her etiket ve tek başına "doğrulanamadı" yumuşak uyarıdır:
1. `ARSIV`;
2. `YENI` + `AZ-KURULUM` ya da `AZ-YILDIZ`;
3. `AZ-KURULUM` + `AZ-YILDIZ`;
4. `AZ-KURULUM` + yıldız ya da repo yaşı alınamıyor (GitHub dışı kaynak, sınır, ağ);
5. sayaçsız kaynakta (topluluk kataloğu; `unique_installs` alanı olmayan resmi giriş) `AZ-YILDIZ` ya da yıldız doğrulanamadı.

- Eleneni önerme: seçme, "Adaylar"a yazma, §4'ü açma; eşiği gevşetme, `--all` verme.
- Yumuşak uyarılı aday gösterilebilir, etiketi değeriyle ("41 günlük repo, 12 yıldız"); etiketsiz alternatif varken varsayılan olamaz.
- Katman 2-3: `unique_installs` / `last_updated` + `--repo` (`./plugins/…` kaynağında "ayrı repo yok" yaz). `--repo` kurulumu bilmez: `AZ-KURULUM`'u sen ekle, beş durumu yeniden uygula.

### 3.2 Ham satır eşlemesi

Ham satırın alanları bloğun aynı adlı alanına gider (`dogrulanamadi` → "doğrulanamadı"). `-- elenenler … --` ayracının altındakiler elenmiştir. `bakilmadi` = bakılmadı ("denetlenmemiş" değil): göstereceksen önce `--show <id>` (en çok 3). `kur (…)` satırı bloğa girmez. `GitHub kalan: R/60`, R ≤ 5: ek `--show` / `--repo` yok. Başka belirteç, `not:` → ayrıntı §3.2.

### 3.3 İsabet bloğu, dolu örnek

Her isabet bu blokla (tablo değil); elenenler altta tek satır:

```
<n>. <ad>
   Ne yapar: <tek cümle Türkçe özet> (yazarın kendi beyanı | denetçi özeti: <sağlayıcı>)
   Kaynak: <repo URL> @<sha12> | sabit commit yok · Kayıt: skills.sh | topluluk kataloğu
   Popülerlik: <N> kurulum | kurulum verisi yok · <S> yıldız[ (repo geneli)]
   Yaş: repo <tarih> (<yaş>) · son güncelleme <tarih>
   Etiket: yok | <ETIKET (ölçülen değer)> · …
   Denetim: <sağlayıcı> pass|warn|fail[ (risk; yalnız --show)], … | denetlenmemiş | alınamadı
   Katman: üçüncü taraf — T5: Anthropic incelemedi | T4: Anthropic tarayıp onayladı; kodu garanti etmez · kullanım ayrı onay ister
Elenenler: <ad>[ (<kayıt>)] — <neden: düz Türkçe, ölçülen değerle>; …
```

Örnek:

```
1. git-commit
   Ne yapar: Diff'ten Conventional Commits biçiminde commit mesajı üretir (yazarın kendi beyanı).
   Kaynak: https://github.com/github/awesome-copilot @143a3d976b3c · Kayıt: skills.sh
   Popülerlik: 46.359 kurulum · 39.713 yıldız (repo geneli)
   Yaş: repo 2025-06-11 (16 ay) · son güncelleme 2026-10-04
   Etiket: yok
   Denetim: Gen Agent Trust Hub pass, Socket pass, Snyk pass
Elenenler: commit-plugin (topluluk kataloğu) — kurulum sayacı yok, 0 yıldız
```

Özel durumlar:
- Adıyla istendi: eleneni gizleme: tam blok, üstüne `**Uyarı: <ad> eleme ölçütüne takılıyor (<neden>); kendiliğimden önermezdim.**`
- Hepsi elendi: "güvenilir popülerlikte aday yok" de, `Elenenler:` satırını yaz, listedeki / resmi adayla ya da fail-open ile sür (ayrıntı §5).
- Doğrulanamadı eşiği geçirmez; 4. ve 5. durumda eler: `Elenenler: <ad> — 269 kurulum; yıldız / yaş doğrulanamadı`.

### 3.4 Sunum kuralları

- Her aramada bir kez yaz, blok olsa da; Elenenler'de topluluk varsa şart: `Üçüncü taraf: Anthropic skills.sh'i incelemedi, topluluk kataloğunu taradı ve onayladı; kodu garanti etmez; kullanım ayrı onay ister.`
- Yanıta yalnız bu çalıştırmada script'in bastığı kayıt, sayı, tarih girer; örnekteki ad / sayıyı taşıma, aramada çıkmayanı anma.
- "Ne yapar" yazarın metninin özetidir, senin hükmün değil. Neden: açıklama kanıt değil.
- En çok 3 isabet; kalanı "<k> isabet daha var; istersen gösteririm" (elenenler sayılmaz; `(+N isabet sigmadi…)` sayılır).
- Açıklaması ihtiyaçla eşleşmeyen isabeti gösterme. Tekrarı düşür: sahibi `anthropics/*` olan (`resmi sahip` eki) ya da adı katman 1-2'de bulunan isabet gösterilmez; listedeki / resmi olan "Seçilen"dir.
- `--show`'dan sonra da `@<sha>` yoksa `sabit commit yok` yaz: Claude kurmaz.
- Sunumdan sonra: tek uygun isabet → aynı turda §4; birden çok → "Hangisini inceleyeyim? 1/2/3 · 4. Hiçbiri", turu bitir.

## 4. Kullanım yolları

Kullanım kendi numaralı onayını ister (arama onayı ve "kur" sözü onay değil); bir seferde TEK isabet. Önce ayrıntı §4'ü oku; onay şablonunun (`guvenlik-kontrol-listesi.md`) üçüncü taraf varyantının altına şunu aynen yaz (1. seçenekte yalnız isabetin katmanına uyan yarı; alt ajan: `calisma-modlari.md`), turu bitir:

```
Nasıl devam edelim?
1. Kalıcı kur — T4: ben kurarım (önce marketplace ekleme onayı, sonra kurulum onayı) / T5: komutu veriyorum, kendi terminalinde sen çalıştırırsın
2. Atla
```

- Uzaktaki SKILL.md elle izlenmez; yalnız inceleme için `--show`'un sabit sha'lı raw URL'sinden veri olarak okunur. Üçüncü taraf script, hook, `bin/`, kurulum komutunu ASLA çalıştırma.
- Risk düzeyi: herhangi bir etiket ya da "doğrulanamadı" → en az Orta. `ARSIV` ya da elenen (adıyla istenen) isabet → 1. seçenek `Önerilmiyor — <neden>` diye başlar, varsayılan 2. Sert engel: SKILL.md Adım 4.

## 5. Hata durumları

- Çıkış 2 (argüman / gizlilik koruması): gösterdiğin kelimelerin alt kümesiyle BİR kez yeniden; yine 2 → atla.
- Çıkış 3 (kaynaklara ulaşılamadı): katmanı atla, teslimde söyle.
- GitHub sınırı (çıkış 0 + sıfırlanma saatini veren not): geleni sun; yıldız / yaş "doğrulanamadı".
- Sıfır isabet: "üçüncü taraf kayıtlarında da uygun aday yok" de, fail-open.

Görev başına `--query` en çok iki kez. Tam tablo: ayrıntı §5.
