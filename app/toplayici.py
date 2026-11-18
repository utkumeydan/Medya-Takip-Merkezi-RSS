"""Beslemeleri tarar, yeni haberleri kaydeder, olaylara kümeler, tam metni çeker.

Tek tur:   python -m app.toplayici --tek
Sürekli:   python -m app.toplayici
"""
from __future__ import annotations

import asyncio
import html
import re
import logging
import sys
import time
from calendar import timegm
from collections import defaultdict
from urllib.parse import urljoin, urlparse

import feedparser
import httpx

from . import ayarlar, metin
from .db import fts_yaz, kur, oturum
from .kaynaklar import esitle
from .kontrol import BASLIKLAR

log = logging.getLogger("toplayici")
_IMG = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.I)


def site_adi(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


class SiteKilidi:
    """Aynı siteye aynı anda giden istek sayısını sınırlar."""

    def __init__(self, sinir: int):
        self.sinir = sinir
        self.kilitler: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(self.sinir))

    def __call__(self, url: str) -> asyncio.Semaphore:
        return self.kilitler[site_adi(url)]


# ---------- besleme okuma ----------

async def besleme_getir(client, genel, site, k) -> dict:
    basliklar = {}
    if k["etag"]:
        basliklar["If-None-Match"] = k["etag"]
    if k["last_modified"]:
        basliklar["If-Modified-Since"] = k["last_modified"]
    sonuc = {"kaynak": k, "ogeler": [], "hata": None, "degismedi": False}
    async with genel, site(k["url"]):
        for deneme in range(2):
            try:
                r = await client.get(k["url"], headers=basliklar)
                break
            except httpx.TransportError as ex:
                if deneme:
                    sonuc["hata"] = type(ex).__name__
                    return sonuc
                await asyncio.sleep(2)
    if r.status_code == 304:
        sonuc["degismedi"] = True
        return sonuc
    if r.status_code >= 400:
        sonuc["hata"] = f"HTTP {r.status_code}"
        return sonuc
    d = feedparser.parse(r.content)
    if not d.entries and d.bozo:
        sonuc["hata"] = "ayrıştırılamadı"
        return sonuc
    sonuc["etag"] = r.headers.get("etag")
    sonuc["last_modified"] = r.headers.get("last-modified")
    sonuc["site"] = d.feed.get("link") or ""
    simdi = int(time.time())
    for e in d.entries:
        link = e.get("link") or ""
        baslik = metin.duz_metin(e.get("title"))
        if not link or not baslik:
            continue
        t = e.get("published_parsed") or e.get("updated_parsed")
        yayin = min(timegm(t), simdi) if t else None
        gorsel = None
        for m in (e.get("media_content") or []) + (e.get("media_thumbnail") or []):
            if m.get("url"):
                gorsel = m["url"]
                break
        if not gorsel:
            for enc in e.get("enclosures") or []:
                if (enc.get("type") or "").startswith("image"):
                    gorsel = enc.get("href")
                    break
        if not gorsel:
            # Bazı siteler görseli ayrı alanda değil, özet ya da içerik HTML'inin içinde verir
            govde = (e.get("summary") or "") + " ".join(c.get("value", "") for c in e.get("content") or [])
            m = _IMG.search(govde)
            if m and not m.group(1).startswith("data:"):
                gorsel = urljoin(link, html.unescape(m.group(1)))
        sonuc["ogeler"].append({
            "guid": (e.get("id") or link)[:500],
            "url": link,
            "baslik": baslik[:300],
            "ozet": metin.duz_metin(e.get("summary"), 400),
            "gorsel": gorsel,
            "yayin": yayin,
        })
    # Bazı beslemeler her istekte tüm öğelere o anın tarihini yazar (ör. 1000 makalenin hepsi son bir saat).
    # Ortalama 20 saniyeden sık yayın tek bir site için gerçekçi değil; böyle tarihler tarihsiz sayılır:
    # ilk taramada eski, sonra ilk görüldüğü an.
    tarihler = [o["yayin"] for o in sonuc["ogeler"] if o["yayin"]]
    if len(tarihler) >= 10 and max(tarihler) - min(tarihler) < max(300, len(tarihler) * 20):
        for o in sonuc["ogeler"]:
            o["yayin"] = None
        sonuc["sahte_tarih"] = True
    return sonuc


# ---------- kümeleme ----------

class OlayDizini:
    def __init__(self, con, simdi: int):
        self.imzalar: dict[int, set[str]] = {}
        self.ters: dict[str, set[int]] = defaultdict(set)
        sinir = simdi - ayarlar.OLAY_PENCERESI_SAAT * 3600
        for r in con.execute("SELECT id, imza FROM olay WHERE son >= ?", (sinir,)):
            self.ekle(r["id"], set(r["imza"].split()))

    def ekle(self, oid: int, imza: set[str]) -> None:
        self.imzalar[oid] = imza
        for t in imza:
            self.ters[t].add(oid)

    def bul(self, imza: set[str]) -> int | None:
        adaylar: dict[int, int] = defaultdict(int)
        for t in imza:
            for oid in self.ters.get(t, ()):
                adaylar[oid] += 1
        for oid, _ in sorted(adaylar.items(), key=lambda x: -x[1])[:30]:
            if metin.benzer(imza, self.imzalar[oid]):
                return oid
        return None


def kaydet(con, dizin: OlayDizini, sonuc: dict, simdi: int) -> list[int]:
    k = sonuc["kaynak"]
    if sonuc["hata"]:
        con.execute("UPDATE kaynak SET hata=?, son_kontrol=?, durum='olu' WHERE id=?",
                    (sonuc["hata"], simdi, k["id"]))
        return []
    if sonuc["degismedi"]:
        con.execute("UPDATE kaynak SET son_kontrol=?, hata=NULL WHERE id=?", (simdi, k["id"]))
        return []
    eski_sinir = simdi - ayarlar.SAKLAMA_GUN * 86400
    ilk_tarama = k["son_kontrol"] is None
    if sonuc.get("sahte_tarih") and not ilk_tarama:
        # Sahte tarihli beslemenin ilk taramada "yeni" sanılan öğelerini geriye çek (bir kez)
        ilk = con.execute("SELECT MIN(toplandi) FROM haber WHERE kaynak_id=?", (k["id"],)).fetchone()[0]
        kosul = "kaynak_id=? AND toplandi=? AND yayin > toplandi - 86400"
        etkilenen = [r[0] for r in con.execute(f"SELECT DISTINCT olay_id FROM haber WHERE {kosul}", (k["id"], ilk))]
        if etkilenen:
            con.execute(f"UPDATE haber SET yayin = toplandi - 3*86400 WHERE {kosul}", (k["id"], ilk))
            for oid in etkilenen:
                olay_guncelle(con, oid)
    yeni_idler, degisen_olaylar = [], set()
    for o in sonuc["ogeler"]:
        if o["yayin"] is None:
            # Tarih vermeyen beslemeler: ilk taramada eski sayılır, sonra görüldüğü an yayın anıdır.
            o["yayin"] = simdi - 3 * 86400 if ilk_tarama else simdi
        if o["yayin"] < eski_sinir:
            continue
        cur = con.execute(
            """INSERT OR IGNORE INTO haber(kaynak_id, guid, url, baslik, ozet, gorsel, yayin, toplandi)
               VALUES (?,?,?,?,?,?,?,?)""",
            (k["id"], o["guid"], o["url"], o["baslik"], o["ozet"], o["gorsel"], o["yayin"], simdi),
        )
        if not cur.rowcount:
            if o["gorsel"]:  # önceden görselsiz kaydedilmiş haberleri tamamla
                con.execute("UPDATE haber SET gorsel=? WHERE kaynak_id=? AND guid=? AND gorsel IS NULL",
                            (o["gorsel"], k["id"], o["guid"]))
            continue
        hid = cur.lastrowid
        fts_yaz(con, hid, o["baslik"], o["ozet"], None)
        imza = metin.imza(o["baslik"])
        oid = dizin.bul(imza) if len(imza) >= 2 else None
        if oid is None:
            oid = con.execute(
                "INSERT INTO olay(baslik, imza, ilk, son) VALUES (?,?,?,?)",
                (o["baslik"], " ".join(sorted(imza)), o["yayin"], o["yayin"]),
            ).lastrowid
            if len(imza) >= 2:
                dizin.ekle(oid, imza)
        con.execute("UPDATE haber SET olay_id=? WHERE id=?", (oid, hid))
        degisen_olaylar.add(oid)
        yeni_idler.append(hid)
    for oid in degisen_olaylar:
        olay_guncelle(con, oid)
    son = max((o["yayin"] for o in sonuc["ogeler"] if o["yayin"]), default=None)
    son = max(filter(None, [son, k["son_haber"]]), default=None)
    yas = simdi - son if son else None
    durum = "canli" if yas is None or yas < 3 * 86400 else "yavas" if yas < 30 * 86400 else "durgun"
    con.execute(
        """UPDATE kaynak SET durum=?, hata=NULL, son_haber=?, son_kontrol=?, etag=?, last_modified=?,
           site=COALESCE(NULLIF(?, ''), site) WHERE id=?""",
        (durum, son, simdi, sonuc.get("etag"), sonuc.get("last_modified"), sonuc.get("site"), k["id"]),
    )
    return yeni_idler


def olay_guncelle(con, oid: int) -> None:
    r = con.execute(
        """SELECT COUNT(*) n, MIN(h.yayin) ilk, MAX(h.yayin) son,
                  COUNT(DISTINCT COALESCE(NULLIF(k.site, ''), k.url)) ks
           FROM haber h JOIN kaynak k ON k.id = h.kaynak_id WHERE h.olay_id=?""",
        (oid,),
    ).fetchone()
    con.execute("UPDATE olay SET haber_sayisi=?, ilk=?, son=?, kaynak_sayisi=? WHERE id=?",
                (r["n"], r["ilk"], r["son"], r["ks"], oid))


# ---------- tam metin ----------

async def tam_metin_cek(client, genel, site, idler: list[int]) -> None:
    if not idler:
        return
    import trafilatura

    with oturum() as con:
        satirlar = con.execute(
            f"SELECT id, url, baslik, ozet FROM haber WHERE id IN ({','.join('?' * len(idler))}) AND tam_metin_durum=0",
            idler,
        ).fetchall()
    dongu = asyncio.get_running_loop()

    async def tek(s):
        try:
            async with genel, site(s["url"]):
                r = await client.get(s["url"])
            if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
                return s, None
            govde = await dongu.run_in_executor(
                None, lambda: trafilatura.extract(r.text, include_comments=False, favor_precision=True)
            )
            return s, govde
        except Exception:
            return s, None

    for i in range(0, len(satirlar), 200):
        sonuclar = await asyncio.gather(*(tek(s) for s in satirlar[i:i + 200]))
        with oturum() as con:
            for s, govde in sonuclar:
                con.execute("UPDATE haber SET tam_metin=?, tam_metin_durum=? WHERE id=?",
                            (govde, 1 if govde else 2, s["id"]))
                if govde:
                    fts_yaz(con, s["id"], s["baslik"], s["ozet"], govde)


# ---------- temizlik ----------

def temizle(con, simdi: int) -> None:
    eski = simdi - ayarlar.SAKLAMA_GUN * 86400
    con.execute("DELETE FROM haber_fts WHERE rowid IN (SELECT id FROM haber WHERE yayin < ?)", (eski,))
    con.execute("DELETE FROM haber WHERE yayin < ?", (eski,))
    tam_sinir = simdi - ayarlar.TAM_METIN_SAKLAMA_GUN * 86400
    for r in con.execute("SELECT id, baslik, ozet FROM haber WHERE tam_metin IS NOT NULL AND yayin < ?",
                         (tam_sinir,)).fetchall():
        fts_yaz(con, r["id"], r["baslik"], r["ozet"], None)
    con.execute("UPDATE haber SET tam_metin=NULL WHERE tam_metin IS NOT NULL AND yayin < ?", (tam_sinir,))
    con.execute("DELETE FROM olay WHERE id NOT IN (SELECT DISTINCT olay_id FROM haber WHERE olay_id IS NOT NULL)")


# ---------- tur ----------

async def bir_tur() -> dict:
    baslangic = time.time()
    esitle()
    with oturum() as con:
        kaynaklar = [dict(r) for r in con.execute("SELECT * FROM kaynak WHERE aktif=1")]
    genel = asyncio.Semaphore(ayarlar.ESZAMANLI)
    site = SiteKilidi(ayarlar.SITE_BASINA)
    yeni: list[int] = []
    async with httpx.AsyncClient(timeout=25, follow_redirects=True, headers=BASLIKLAR, verify=False) as client:
        gorevler = [asyncio.create_task(besleme_getir(client, genel, site, k)) for k in kaynaklar]
        simdi = int(time.time())
        with oturum() as con:
            dizin = OlayDizini(con, simdi)
            for g in asyncio.as_completed(gorevler):
                try:
                    sonuc = await g
                except Exception as ex:
                    log.warning("besleme hatası: %s", ex)
                    continue
                yeni += kaydet(con, dizin, sonuc, simdi)
                con.commit()
            temizle(con, simdi)
        if ayarlar.TAM_METIN:
            await tam_metin_cek(client, genel, site, yeni)
    try:
        from .simgeler import eksikleri_indir, kaynak_siteleri
        await eksikleri_indir(kaynak_siteleri())
    except Exception:
        log.warning("simgeler indirilemedi", exc_info=True)
    ozet = {"kaynak": len(kaynaklar), "yeni_haber": len(yeni), "sure_sn": round(time.time() - baslangic, 1)}
    log.info("tur bitti: %s", ozet)
    return ozet


async def dongu() -> None:
    kur()
    while True:
        try:
            await bir_tur()
        except Exception:
            log.exception("tur başarısız")
        await asyncio.sleep(ayarlar.TOPLAMA_ARALIGI_DK * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    import warnings
    warnings.filterwarnings("ignore")
    if "--tek" in sys.argv:
        kur()
        print(asyncio.run(bir_tur()))
    else:
        asyncio.run(dongu())
