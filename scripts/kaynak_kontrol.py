"""Kaynak listesini doğrular.

  python scripts/kaynak_kontrol.py                 # yalnız dosya yapısını denetler
  python scripts/kaynak_kontrol.py --canli         # tüm beslemeleri tek tek dener, rapor yazar
  python scripts/kaynak_kontrol.py --canli --taban eski.yaml
                                                   # yalnız eski.yaml'da olmayan (yeni eklenen) adresleri dener;
                                                   # biri çalışmıyor ya da Türkçe değilse hata koduyla çıkar (PR denetimi)
"""
import argparse
import asyncio
import sys
import warnings
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.kaynaklar import oku  # noqa: E402
from app.kontrol import toplu_kontrol  # noqa: E402

warnings.filterwarnings("ignore")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canli", action="store_true", help="beslemeleri ağ üzerinden dene")
    ap.add_argument("--taban", help="karşılaştırılacak eski kaynaklar.yaml")
    ap.add_argument("--esik", type=float, default=0.12, help="en düşük Türkçe puanı")
    a = ap.parse_args()

    try:
        veri = oku()
    except Exception as ex:
        print(f"HATA: kaynak dosyası geçersiz: {ex}")
        return 1
    kaynaklar = veri["kaynaklar"]
    print(f"Dosya geçerli: {len(kaynaklar)} kaynak, {len(veri['kategoriler'])} kategori.")
    if not a.canli:
        return 0

    hedef = kaynaklar
    if a.taban:
        eski = set()
        if Path(a.taban).exists() and Path(a.taban).stat().st_size:
            eski = {k["url"] for k in (yaml.safe_load(open(a.taban, encoding="utf-8")) or {}).get("kaynaklar", [])}
        hedef = [k for k in kaynaklar if k["url"] not in eski]
        print(f"Yeni eklenen {len(hedef)} kaynak denenecek.")
    if not hedef:
        return 0

    sonuclar = asyncio.run(toplu_kontrol([k["url"] for k in hedef], 10))
    sorunlu = []
    for k, s in zip(hedef, sonuclar):
        turkce = s.get("turkce") or 0
        ok = s["durum"] != "olu" and (k.get("tur") == "uretilen" or turkce >= a.esik)
        isaret = "✓" if ok else "✗"
        print(f"{isaret} {s['durum']:<7} tr={turkce:<4} {k['ad']} — {k['url']} {s.get('hata') or ''}")
        if not ok:
            sorunlu.append(k)
    print(f"\n{len(hedef) - len(sorunlu)} çalışıyor, {len(sorunlu)} sorunlu.")
    return 1 if (a.taban and sorunlu) else 0


if __name__ == "__main__":
    sys.exit(main())
