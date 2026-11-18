# Medya Takip

Türkçe haber kaynakları için açık kaynak bir **RSS dizini** ve **medya takip merkezi**.

- **RSS dizini:** 535 doğrulanmış Türkçe besleme, 14 kategoride. Tek beslemeyi kopyala, birden çoğunu seçip URL listesi ya da OPML olarak al, seçtiklerinden ve anahtar kelimelerden **tek bir birleşik RSS adresi** üret.
- **Takip merkezi:** Tüm kaynaklardan canlı akış. Aynı haberin farklı sitelerdeki kopyaları tek **olay** altında toplanır, her olayın kaynaklarını zaman çizelgesinde görürsün. Takip listesi, trend tespiti, tam metin arama, grafikler.
- **Kayıtlar tarayıcıda:** Kaydetme, etiketleme ve notlar yalnızca kullanıcının tarayıcısında tutulur. Üyelik yok, sunucuda kişisel veri yok.

## Hızlı başlangıç

```bash
docker compose up -d
```

Panel `http://localhost:8000` adresinde açılır. İlk tarama yaklaşık bir dakika sürer, sonra beslemeler her 10 dakikada bir taranır.

### Docker olmadan

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.api:app --port 8000
```

Python 3.10 veya üstü gerekir. Veritabanı `data/medya.db` dosyasıdır (SQLite, ek kurulum yok).

## Ayarlar

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `MT_ARALIK_DK` | `10` | Tarama aralığı (dakika) |
| `MT_SAKLAMA_GUN` | `30` | Haberlerin tutulacağı gün |
| `MT_TAM_METIN` | `1` | Yeni haberlerin tam metnini arama için çek (`0` kapatır) |
| `MT_TAM_METIN_GUN` | `7` | Tam metnin tutulacağı gün |
| `MT_ESZAMANLI` / `MT_SITE_BASINA` | `20` / `2` | Aynı anda en fazla istek / aynı siteye en fazla istek |
| `MT_GENEL_ADRES` | — | Birleşik beslemelerde görünecek adres, ör. `https://medya.ornek.org` |
| `MT_TOPLAYICI` | `1` | `0` yaparsan API toplayıcıyı başlatmaz (toplayıcıyı ayrı çalıştırmak için `python -m app.toplayici`) |
| `MT_VERI` / `MT_KAYNAKLAR` / `MT_SIMGELER` | `data/medya.db` / `sources/kaynaklar.yaml` / `simgeler/` | Dosya yolları |

## Birleşik besleme ve API

Hepsi herkese açık, anahtar gerekmez.

| Adres | Ne verir |
|---|---|
| `/feed?kat=spor&takip=transfer` | Spor kategorisinde "transfer" geçen haberlerin RSS'i |
| `/feed?k=ntv-spor-futbol,a-spor&q=derbi` | Seçili kaynaklarda "derbi" geçenler |
| `/feed?takip=Galatasaray,Okan Buruk&tekil=1` | Terimlerden biri geçen haberler; `tekil=1` (varsayılan) her olaydan yalnız ilk haberi verir |
| `/api/opml?kat=gundem,ekonomi` veya `/api/opml?k=...` | OPML dosyası |
| `/api/liste?kat=teknoloji` | Düz metin URL listesi |
| `/api/kaynaklar`, `/api/kategoriler` | Dizin verisi (JSON) |
| `/api/olaylar?q=&takip=&kat=&kaynak=&saat=24` | Olaylar ve kaynakları |
| `/api/trendler`, `/api/istatistik` | Trendler ve grafik verisi |

Tüm uç noktalar: `/api/belgeler`.

## Kaynak eklemek

Kaynaklar [`sources/kaynaklar.yaml`](sources/kaynaklar.yaml) dosyasında durur. Yeni kaynak için listeye bir giriş ekleyip PR gönder:

```yaml
- ad: Örnek Haber — Spor
  url: https://www.ornekhaber.com/rss/spor
  kategori: spor          # kategoriler dosyanın başında
  tur: rss                # rss: sitenin kendi beslemesi, uretilen: Google Haberler sorgusu, RSSHub vb.
  kaynak: [katkı]
```

PR açıldığında GitHub Actions yalnız yeni eklenen adresleri dener: besleme çalışmıyor ya da içerik Türkçe değilse kontrol başarısız olur. Yerelde aynı denetim:

```bash
.venv/bin/python scripts/kaynak_kontrol.py --canli
```

Kendi sitesinde RSS olmayan kurumlar (ör. kulüp siteleri) için `tur: uretilen` ile Google Haberler sorgusu ya da kendi [RSSHub](https://docs.rsshub.app) kurulumundaki bir adres eklenebilir.

## Nasıl çalışır

- **Toplayıcı** (`app/toplayici.py`): Beslemeleri `ETag` / `Last-Modified` ile koşullu çeker, aynı siteye aynı anda en fazla iki istek gönderir.
- **Olay kümeleme:** Başlıklar Türkçeye uygun biçimde sadeleştirilir (kesme ekleri atılır, sözcükler 5 harfe kısaltılır) ve son 48 saatteki olaylarla benzerliğe göre eşleştirilir.
- **Trendler:** Başlıklardaki özel adların (kişi, kurum, yer) son 2 saatteki geçme hızı önceki 24 saatle karşılaştırılır. En az 4 farklı sitede geçen adlar listelenir.
- **Site simgeleri:** Kaynakların simgeleri 64 piksellik PNG olarak `simgeler/` klasöründe tutulur ve `/simge/<kaynak-id>` adresinden verilir; okuyucunun tarayıcısı hiçbir dış servise istek atmaz. Yeni eklenen kaynakların simgeleri tarama sırasında indirilir (`python -m app.simgeler` ile elle de çalıştırılabilir).
- **Görseller:** Haber görseli beslemenin medya alanından, yoksa özet ya da içerik HTML'indeki ilk görselden alınır. Görseller kaynağın kendi sunucusundan yüklenir, kopyalanmaz.
- **Arama:** SQLite FTS5. Türkçe karakterler katlanır, "ısınma" araması "Isınma"yı da bulur.

## Telif

Panel haberlerin yalnız başlığını, beslemedeki kısa özetini ve orijinal habere bağlantıyı gösterir. Tam metin yalnız sunucuda, arama dizini için ve sınırlı süre tutulur, hiçbir yerde yeniden yayımlanmaz. Kendi kurulumunda tam metni kapatmak için `MT_TAM_METIN=0`.

## Teşekkür

İlk kaynak listesi şu açık listelerden derlenip tek tek doğrulandı:

- [bakinazik/rss](https://github.com/bakinazik/rss)
- [feeder.co Türkiye](https://feeder.co/discover/turkey)
- [wordpresshabertemasi.com RSS adresleri](https://wordpresshabertemasi.com/blog/turkiye-haber-siteleri-rss-adresleri)
- [fatihdx/tr-rss-haber-akisi-verisi](https://huggingface.co/datasets/fatihdx/tr-rss-haber-akisi-verisi) (Hugging Face)

## Lisans

[MIT](LICENSE)
