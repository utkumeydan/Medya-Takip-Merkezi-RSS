"""sources/kaynaklar.yaml dosyasını okur ve veritabanıyla eşitler."""
import re

import yaml

from .ayarlar import KAYNAK_DOSYASI
from .db import oturum

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")


def kisa_ad(ad: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", ad.translate(_TR).lower()).strip("-")
    return s[:60] or "kaynak"


def oku() -> dict:
    with open(KAYNAK_DOSYASI, encoding="utf-8") as f:
        veri = yaml.safe_load(f)
    kimlikler = {k["id"] for k in veri["kategoriler"]}
    goruldu: dict[str, int] = {}
    urller: set[str] = set()
    for k in veri["kaynaklar"]:
        for alan in ("ad", "url", "kategori"):
            if not k.get(alan):
                raise ValueError(f"Eksik alan '{alan}': {k}")
        if k["url"] in urller:
            raise ValueError(f"Aynı adres iki kez var: {k['url']}")
        urller.add(k["url"])
        if k.get("tur", "rss") not in ("rss", "uretilen"):
            raise ValueError(f"Geçersiz tur: {k.get('tur')} ({k['ad']})")
        if k["kategori"] not in kimlikler:
            raise ValueError(f"Bilinmeyen kategori: {k['kategori']} ({k['ad']})")
        temel = k.get("id") or kisa_ad(k["ad"])
        n = goruldu.get(temel, 0)
        goruldu[temel] = n + 1
        k["id"] = temel if n == 0 else f"{temel}-{n + 1}"
    return veri


def esitle() -> int:
    veri = oku()
    with oturum() as con:
        urller = []
        for k in veri["kaynaklar"]:
            urller.append(k["url"])
            deger = (k["ad"], k["url"], k["kategori"], k.get("tur", "rss"))
            var = con.execute(
                "SELECT id FROM kaynak WHERE url=? OR id=? ORDER BY url=? DESC LIMIT 1",
                (k["url"], k["id"], k["url"]),
            ).fetchone()
            if var:
                con.execute(
                    "UPDATE kaynak SET ad=?, url=?, kategori=?, tur=?, aktif=1 WHERE id=?",
                    (*deger, var["id"]),
                )
            else:
                con.execute(
                    "INSERT INTO kaynak(id, ad, url, kategori, tur) VALUES (?,?,?,?,?)",
                    (k["id"], *deger),
                )
        con.execute(
            f"UPDATE kaynak SET aktif=0 WHERE url NOT IN ({','.join('?' * len(urller))})", urller
        )
    return len(veri["kaynaklar"])
