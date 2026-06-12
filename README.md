# is-ilan

Terminalden LinkedIn iş ilanı arama aracı. Login gerektirmez, LinkedIn'in misafir API'sini kullanır.

## Kurulum

```bash
git clone git@github.com:furkandogmus/is-ilan.git
cd is-ilan
# Bağımlılık yok, sadece Python 3.7+
```

## Kullanım

```bash
# Temel arama
python3 is_ilan.py python

# Son 48 saat, uzaktan çalışma
python3 is_ilan.py "data engineer" --hours 48 --remote

# İstanbul'daki devops ilanları
python3 is_ilan.py devops --location Istanbul

# Başlıkta regex filtre
python3 is_ilan.py react --title-filter "senior|lead|staff"

# JSON çıktısı
python3 is_ilan.py java --json | jq '.'

# Birden çok sayfa
python3 is_ilan.py golang --pages 3

# Sadece URL'ler
python3 is_ilan.py nodejs --url-only

# Geçmişi sıfırla
python3 is_ilan.py --reset
```

## Parametreler

| Parametre             | Kısa | Açıklama                                | Varsayılan |
|-----------------------|------|-----------------------------------------|------------|
| `keywords`            |      | Aranacak kelime(ler)                    | `devops`   |
| `--hours`             | `-t` | Son kaç saat                            | `24`       |
| `--location`          | `-l` | Konum / şehir / ülke                    | `Turkey`   |
| `--remote`            | `-r` | Sadece remote ilanlar                   |            |
| `--title-filter`      | `-f` | Başlıkta regex filtre                   |            |
| `--pages`             | `-p` | Sayfa sayısı (×25 ilan)                 | `1`        |
| `--no-notify`         | `-n` | Bildirim gönderme                       |            |
| `--json`              | `-j` | JSON çıktı                              |            |
| `--url-only`          |      | Sadece URL listesi                      |            |
| `--all`               |      | Görüldü kaydını yoksay                  |            |
| `--stats`             |      | Sadece özet                             |            |
| `--reset`             |      | Görülen ilan kaydını sıfırla            |            |
