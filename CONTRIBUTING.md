# Katkı Rehberi

is-ilan projesine katkıda bulunmak istediğiniz için teşekkürler!

## Geliştirme Ortamı

```bash
git clone https://github.com/furkandogmus/is-ilan.git
cd is-ilan
```

Bağımlılık yok — sadece Python 3.7+ yeterli.

## Test

```bash
pip install pytest ruff
pytest -v
ruff check .
```

## Kod Standartları

- Python 3.7+ uyumlu
- Type hint kullan
- ruff lint kurallarına uy
- Her yeni özellik için test ekle

## PR Süreci

1. Branch aç (`feat/`, `fix/`, `refactor/`)
2. Değişiklikleri yap
3. Testleri çalıştır (hepsi yeşil olmalı)
4. PR aç ve ne yaptığını açıkla
