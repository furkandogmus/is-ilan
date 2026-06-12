# ⌖ İlanRotası

**İyi ilana giden yol.** LinkedIn iş ilanlarını web arayüzünden veya terminalden arar. Login gerektirmez.

[![Python](https://img.shields.io/badge/python-3.7%2B-3b8cf7?style=flat&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)
[![Dark Mode](https://img.shields.io/badge/dark%20mode-black?style=flat)](https://github.com/furkandogmus/is-ilan)

## 🚀 Hızlı Başlangıç

```bash
# Web arayüzü
python3 server.py
# → http://localhost:8080

# Terminal
python3 is_ilan.py devops --hours 48 --remote
```

## 🖥️ Web Arayüzü

Gerçek zamanlı arama, sort, export ve daha fazlası.

```bash
python3 server.py            # varsayılan port 8080
python3 server.py --port 3000
```

## ⌨️ Terminal Kullanımı

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

# Birden çok sayfa (25 × 3 = 75 ilan)
python3 is_ilan.py golang --pages 3

# Sadece URL'ler
python3 is_ilan.py nodejs --url-only

# Geçmişi sıfırla
python3 is_ilan.py --reset
```

## ⚙️ Parametreler

| Parametre | Kısa | Açıklama | Varsayılan |
|---|---|---|---|
| `keywords` | | Aranacak kelime(ler) | `devops` |
| `--hours` | `-t` | Son kaç saat | `24` |
| `--location` | `-l` | Konum / şehir / ülke | `Turkey` |
| `--remote` | `-r` | Sadece remote ilanlar | |
| `--title-filter` | `-f` | Başlıkta regex filtre | |
| `--no-title-filter` | | Otomatik başlık filtresini kapat | |
| `--pages` | `-p` | Sayfa sayısı (×25 ilan) | `1` |
| `--no-notify` | `-n` | Bildirim gönderme | |
| `--json` | `-j` | JSON çıktı | |
| `--url-only` | | Sadece URL listesi | |
| `--no-reposts` | | Repost ilanları gizle | |
| `--max-applicants` | `-a` | Maksimum başvuru filtresi | `0` |
| `--all` | | Görüldü kaydını yoksay | |
| `--stats` | | Sadece özet | |
| `--reset` | | Görülen ilan kaydını sıfırla | |
| `--install-scheduler` | | Zamanlanmış görev kur (macOS/Linux/Win) | |
| `--uninstall-scheduler` | | Zamanlanmış görevi kaldır | |
| `--scheduler-status` | | Zamanlanmış görev durumu | |
| `--version` | `-V` | Versiyon bilgisi | |

## 🐳 Docker

```bash
docker build -t is-ilan .
docker run -p 8080:8080 is-ilan
```

## 📊 Ücretsiz Uygulama Analitiği

Web arayüzü Google Analytics 4 entegrasyonuna hazırdır. GA4; ziyaret/sayfa görüntüleme,
şehir/ülke, cihaz türü ve tarayıcı bilgilerini otomatik raporlar. Uygulama ayrıca arama,
filtre, favori ve ilan etkileşimlerini özel olay olarak gönderir; arama kelimesi, yazılan
konum, ilan başlığı ve şirket adı gönderilmez.

1. Google Analytics'te ücretsiz bir GA4 property ve Web data stream oluşturun.
2. `index.html` içindeki `ga-measurement-id` meta etiketinin `content` alanına `G-...`
   ile başlayan Measurement ID'yi yazın.
3. Deploy sonrası GA4 Realtime ekranından kurulumu doğrulayın.

Measurement ID boş bırakılırsa analitik kodu yüklenmez ve hiçbir veri gönderilmez.

## 🛠 Geliştirme

```bash
pip install pytest ruff
pytest -v
ruff check .
```

## 📜 Lisans

MIT — [Furkan Doğmuş](https://github.com/furkandogmus)
