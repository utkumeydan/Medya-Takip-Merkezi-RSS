"""Besleme sağlık kontrolü: canlı mı, Türkçe mi, ne sıklıkla yazıyor."""
from __future__ import annotations

import asyncio
import re
import time
from calendar import timegm

import feedparser
import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130 Safari/537.36 MedyaTakip/0.1"
)
BASLIKLAR = {"User-Agent": UA, "Accept": "application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.8"}
TR_KELIMELER = {
    "ve", "bir", "bu", "için", "ile", "da", "de", "olarak", "çok", "daha", "gibi",
    "sonra", "kadar", "yeni", "oldu", "olan", "ne", "son", "dakika", "türkiye",
}
TR_HARF = set("çğıöşüÇĞİÖŞÜ")


def turkce_puani(metin: str) -> float:
    kelimeler = re.findall(r"[^\W\d_]+", metin.lower())
    if not kelimeler:
        return 0.0
    k = sum(1 for w in kelimeler if w in TR_KELIMELER) / len(kelimeler)
    harfler = [c for c in metin if c.isalpha()]
    h = sum(1 for c in harfler if c in TR_HARF) / max(len(harfler), 1)
    return round(min(1.0, k * 4 + h * 6), 2)


def zaman(e) -> int | None:
    t = e.get("published_parsed") or e.get("updated_parsed")
    return timegm(t) if t else None


async def kontrol_et(client: httpx.AsyncClient, url: str) -> dict:
    sonuc = {"url": url, "durum": "olu", "hata": None}
    try:
        r = await client.get(url)
        sonuc["http"] = r.status_code
        if r.status_code >= 400:
            sonuc["hata"] = f"HTTP {r.status_code}"
            return sonuc
        d = feedparser.parse(r.content)
        if not d.entries:
            sonuc["hata"] = "öğe yok"
            return sonuc
        metin = " ".join((e.get("title", "") + " " + e.get("summary", "")[:300]) for e in d.entries[:20])
        zamanlar = sorted([z for z in (zaman(e) for e in d.entries) if z], reverse=True)
        simdi = time.time()
        son = zamanlar[0] if zamanlar else None
        sonuc.update(
            baslik=(d.feed.get("title") or "").strip(),
            site=d.feed.get("link") or "",
            oge=len(d.entries),
            son=son,
            turkce=turkce_puani(metin),
            nihai_url=str(r.url),
        )
        if son is None:
            sonuc["durum"] = "canli"  # tarih vermeyen beslemeler
        elif simdi - son < 3 * 86400:
            sonuc["durum"] = "canli"
        elif simdi - son < 30 * 86400:
            sonuc["durum"] = "yavas"
        else:
            sonuc["durum"] = "durgun"
    except Exception as ex:  # ağ, zaman aşımı, ayrıştırma
        sonuc["hata"] = type(ex).__name__
    return sonuc


async def toplu_kontrol(urller: list[str], eszamanli: int = 30) -> list[dict]:
    sem = asyncio.Semaphore(eszamanli)
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers=BASLIKLAR, verify=False
    ) as client:
        async def tek(u):
            async with sem:
                return await kontrol_et(client, u)
        return await asyncio.gather(*(tek(u) for u in urller))
