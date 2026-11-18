"""Kaynak sitelerin simgelerini (favicon) indirip proje içinde saklar.

Simgeler `simgeler/<alan-adı>.<uzantı>` olarak tutulur ve /simge/<kaynak-id> adresinden verilir.
Okuyucunun tarayıcısı hiçbir dış servise istek atmaz.

Eksikleri indir:  python -m app.simgeler
"""
from __future__ import annotations

import asyncio
import re
import sys
from urllib.parse import urljoin, urlparse

import httpx

from .ayarlar import SIMGE_KLASORU
from .kontrol import BASLIKLAR

TURLER = {"image/png": "png", "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico", "image/svg+xml": "svg",
          "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
MEDYA = {"png": "image/png", "ico": "image/x-icon", "svg": "image/svg+xml", "jpg": "image/jpeg",
         "webp": "image/webp", "gif": "image/gif"}
_LINK = re.compile(r"<link\b[^>]*>", re.I)
_OZ = re.compile(r'(\w[\w-]*)\s*=\s*["\']([^"\']*)["\']')


def alan_adi(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").split(":")[0]


def bul(alan: str):
    for uz in MEDYA:
        p = SIMGE_KLASORU / f"{alan}.{uz}"
        if p.exists():
            return p, MEDYA[uz]
    return None


BOYUT = 64


def kucult(veri: bytes, hedef) -> bool:
    """Simgeyi 64 piksellik PNG'ye çevirir; bozuk ya da çok küçük görselleri reddeder."""
    from io import BytesIO

    from PIL import Image
    try:
        im = Image.open(BytesIO(veri))
        if getattr(im, "n_frames", 1) > 1 and im.format == "ICO":
            im.size = max(im.info.get("sizes", [im.size]))
        im = im.convert("RGBA")
        if min(im.size) < 12:
            return False
        im.thumbnail((BOYUT, BOYUT), Image.LANCZOS)
        im.save(hedef, "PNG", optimize=True)
        return True
    except Exception:
        return False


def _uzanti(r: httpx.Response, url: str) -> str | None:
    tur = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if tur in TURLER:
        return TURLER[tur]
    m = re.search(r"\.(png|ico|svg|jpe?g|webp|gif)(?:\?|$)", url.lower())
    if m and r.content[:4] not in (b"<!DO", b"<htm", b"<HTM"):
        return {"jpeg": "jpg"}.get(m.group(1), m.group(1))
    return None


async def indir(client: httpx.AsyncClient, site_url: str) -> str | None:
    """Sitenin ana sayfasından simge bağlantısını bulur, yoksa /favicon.ico dener."""
    alan = alan_adi(site_url)
    if not alan or bul(alan):
        return alan
    kok = f"https://{urlparse(site_url).netloc}/"
    adaylar: list[tuple[int, str]] = []
    try:
        r = await client.get(kok)
        govde = r.text[:200_000]
        taban = str(r.url)
        for etiket in _LINK.findall(govde):
            oz = {k.lower(): v for k, v in _OZ.findall(etiket)}
            rel = oz.get("rel", "").lower()
            if "icon" not in rel or not oz.get("href"):
                continue
            boyut = 0
            m = re.search(r"(\d+)x\d+", oz.get("sizes", ""))
            if m:
                boyut = int(m.group(1))
            elif "apple-touch" in rel:
                boyut = 180
            # 32-192 piksel arası en iyisi; çok büyükler gereksiz yer kaplar
            puan = 1000 - abs(min(boyut or 32, 512) - 96)
            adaylar.append((puan, urljoin(taban, oz["href"])))
    except Exception:
        pass
    adaylar.sort(reverse=True)
    for _, url in [*adaylar[:3], (0, urljoin(kok, "/favicon.ico"))]:
        if url.startswith("data:"):
            continue
        try:
            r = await client.get(url)
            if r.status_code != 200 or not (80 < len(r.content) < 300_000):
                continue
            uz = _uzanti(r, url)
            if not uz:
                continue
            SIMGE_KLASORU.mkdir(parents=True, exist_ok=True)
            if uz == "svg":
                (SIMGE_KLASORU / f"{alan}.svg").write_bytes(r.content)
            elif not kucult(r.content, SIMGE_KLASORU / f"{alan}.png"):
                continue
            return alan
        except Exception:
            continue
    return None


async def eksikleri_indir(site_urlleri: list[str], eszamanli: int = 12) -> tuple[int, int]:
    alanlar = {}
    for u in site_urlleri:
        a = alan_adi(u)
        if a and a not in alanlar and not bul(a):
            alanlar[a] = u
    sem = asyncio.Semaphore(eszamanli)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=BASLIKLAR, verify=False) as client:
        async def tek(u):
            async with sem:
                return await indir(client, u)
        sonuc = await asyncio.gather(*(tek(u) for u in alanlar.values()))
    return sum(1 for s in sonuc if s), len(alanlar)


def kaynak_siteleri() -> list[str]:
    from .db import oturum
    with oturum() as con:
        return [r[0] or r[1] for r in con.execute("SELECT NULLIF(site, ''), url FROM kaynak WHERE aktif=1")]


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    ok, toplam = asyncio.run(eksikleri_indir(kaynak_siteleri()))
    print(f"{toplam} eksik alandan {ok} simge indirildi.", file=sys.stderr)
