"""Web API ve panel. Çalıştır: uvicorn app.api:app"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import Counter, defaultdict
from email.utils import formatdate
from xml.sax.saxutils import escape

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from . import ayarlar, metin
from .db import kur, oturum
from .kaynaklar import esitle, oku

app = FastAPI(title="Medya Takip", docs_url="/api/belgeler", redoc_url=None)
WEB = ayarlar.KOK / "web"


@app.on_event("startup")
async def basla():
    kur()
    esitle()
    if os.environ.get("MT_TOPLAYICI", "1") == "1":
        from .toplayici import dongu
        kayitci = logging.getLogger("toplayici")
        if not kayitci.handlers:
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
            kayitci.addHandler(h)
            kayitci.setLevel(logging.INFO)
        asyncio.create_task(dongu())


# ---------- yardımcılar ----------

def liste(deger: str | None) -> list[str]:
    return [x.strip() for x in (deger or "").split(",") if x.strip()]


def fts_sorgu(q: str | None, takip: list[str]) -> str | None:
    """Serbest arama (tüm sözcükler) VE takip terimlerinden en az biri."""
    parcalar = []
    sozcukler = metin.katla(q or "").split()
    if sozcukler:
        parcalar.append(" AND ".join(f'"{w.replace(chr(34), "")}"*' for w in sozcukler))
    ifadeler = []
    for t in takip:
        ws = metin.katla(t).replace('"', "").split()
        if ws:
            ifadeler.append('"' + " ".join(ws) + '"*')
    if ifadeler:
        parcalar.append("(" + " OR ".join(ifadeler) + ")")
    return " AND ".join(parcalar) or None


def filtre_sql(kat: list[str], kaynak: list[str], q: str | None, takip: list[str], bas: int | None, bit: int | None):
    kosul, arg = [], []
    if kat:
        kosul.append(f"k.kategori IN ({','.join('?' * len(kat))})")
        arg += kat
    if kaynak:
        kosul.append(f"h.kaynak_id IN ({','.join('?' * len(kaynak))})")
        arg += kaynak
    if bas:
        kosul.append("h.yayin >= ?")
        arg.append(bas)
    if bit:
        kosul.append("h.yayin < ?")
        arg.append(bit)
    fq = fts_sorgu(q, takip)
    if fq:
        kosul.append("h.id IN (SELECT rowid FROM haber_fts WHERE haber_fts MATCH ?)")
        arg.append(fq)
    return (" WHERE " + " AND ".join(kosul)) if kosul else "", arg


def haber_json(r) -> dict:
    return {"id": r["id"], "baslik": r["baslik"], "ozet": r["ozet"], "url": r["url"], "gorsel": r["gorsel"],
            "yayin": r["yayin"], "kaynak": {"id": r["kaynak_id"], "ad": r["kaynak_ad"], "kategori": r["kategori"]}}


# ---------- dizin ----------

@app.get("/api/kategoriler")
def kategoriler():
    veri = oku()
    with oturum() as con:
        say = dict(con.execute("SELECT kategori, COUNT(*) FROM kaynak WHERE aktif=1 GROUP BY 1").fetchall())
    return [{"id": k["id"], "ad": k["ad"], "kaynak_sayisi": say.get(k["id"], 0)} for k in veri["kategoriler"]]


@app.get("/api/kaynaklar")
def kaynaklar():
    gun = int(time.time()) - 86400
    with oturum() as con:
        satirlar = con.execute(
            """SELECT k.id, k.ad, k.url, k.kategori, k.tur, k.site, k.durum, k.hata, k.son_haber, k.son_kontrol,
                      (SELECT COUNT(*) FROM haber h WHERE h.kaynak_id=k.id AND h.yayin>=?) AS haber_24s
               FROM kaynak k WHERE k.aktif=1 ORDER BY k.ad COLLATE NOCASE""", (gun,)).fetchall()
    return [dict(r) for r in satirlar]


def secili_kaynaklar(k: str | None, kat: str | None):
    ids, kats = liste(k), liste(kat)
    if not ids and not kats:
        raise HTTPException(400, "k (kaynak kimlikleri) veya kat (kategori) gerekli")
    kosul, arg = [], []
    if ids:
        kosul.append(f"id IN ({','.join('?' * len(ids))})")
        arg += ids
    if kats:
        kosul.append(f"kategori IN ({','.join('?' * len(kats))})")
        arg += kats
    with oturum() as con:
        return con.execute(f"SELECT * FROM kaynak WHERE aktif=1 AND ({' OR '.join(kosul)}) ORDER BY ad", arg).fetchall()


@app.get("/api/opml")
def opml(k: str | None = None, kat: str | None = None):
    satirlar = secili_kaynaklar(k, kat)
    kat_ad = {x["id"]: x["ad"] for x in oku()["kategoriler"]}
    gruplar = defaultdict(list)
    for r in satirlar:
        gruplar[r["kategori"]].append(r)
    govde = []
    for kid, rs in gruplar.items():
        govde.append(f'    <outline text="{escape(kat_ad.get(kid, kid), {chr(34): "&quot;"})}">')
        for r in rs:
            a = escape(r["ad"], {'"': "&quot;"})
            govde.append(f'      <outline type="rss" text="{a}" title="{a}" xmlUrl="{escape(r["url"], {chr(34): "&quot;"})}"'
                         + (f' htmlUrl="{escape(r["site"], {chr(34): "&quot;"})}"' if r["site"] else "") + "/>")
        govde.append("    </outline>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0">\n  <head><title>Medya Takip</title>'
           f"<dateCreated>{formatdate(usegmt=True)}</dateCreated></head>\n  <body>\n"
           + "\n".join(govde) + "\n  </body>\n</opml>\n")
    return Response(xml, media_type="text/x-opml",
                    headers={"Content-Disposition": 'attachment; filename="medya-takip.opml"'})


@app.get("/api/liste", response_class=PlainTextResponse)
def url_listesi(k: str | None = None, kat: str | None = None):
    return "\n".join(r["url"] for r in secili_kaynaklar(k, kat)) + "\n"


@app.get("/feed")
def birlesik_besleme(request: Request, k: str | None = None, kat: str | None = None, q: str | None = None,
                     takip: str | None = None, tekil: int = 1, adet: int = Query(50, le=200)):
    """Seçili kaynak/kategori + anahtar kelimelerden tek RSS beslemesi üretir."""
    nerede, arg = filtre_sql(liste(kat), liste(k), q, liste(takip), int(time.time()) - 7 * 86400, None)
    grup = "GROUP BY COALESCE(h.olay_id, -h.id)" if tekil else "GROUP BY h.id"
    with oturum() as con:
        satirlar = con.execute(
            f"""SELECT h.*, MIN(h.yayin) ilk_yayin, k.ad kaynak_ad, k.kategori FROM haber h
                JOIN kaynak k ON k.id=h.kaynak_id {nerede} {grup} ORDER BY ilk_yayin DESC LIMIT ?""",
            [*arg, adet]).fetchall()
    taban = ayarlar.GENEL_ADRES or str(request.base_url).rstrip("/")
    ogeler = []
    for r in satirlar:
        ogeler.append(
            "<item>"
            f"<title>{escape(r['baslik'])}</title><link>{escape(r['url'])}</link>"
            f"<guid isPermaLink=\"false\">mt-{r['id']}</guid>"
            f"<pubDate>{formatdate(r['yayin'], usegmt=True)}</pubDate>"
            f"<source url=\"{escape(taban)}\">{escape(r['kaynak_ad'])}</source>"
            f"<description>{escape(r['ozet'] or '')}</description>"
            "</item>")
    baslik = "Medya Takip — " + (", ".join(filter(None, [kat, q, takip])) or "birleşik besleme")
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
           f"<title>{escape(baslik)}</title><link>{escape(taban)}</link>"
           "<description>Medya Takip birleşik beslemesi</description><language>tr</language>"
           f"<lastBuildDate>{formatdate(usegmt=True)}</lastBuildDate>" + "".join(ogeler) + "</channel></rss>")
    return Response(xml, media_type="application/rss+xml; charset=utf-8")


# ---------- takip merkezi ----------

@app.get("/api/olaylar")
def olaylar(kat: str | None = None, kaynak: str | None = None, q: str | None = None, takip: str | None = None,
            saat: int = 24, bas: int | None = None, bit: int | None = None, sayfa: int = 0,
            adet: int = Query(30, le=100), siralama: str = "son"):
    simdi = int(time.time())
    bas = bas or (simdi - saat * 3600 if saat else None)
    nerede, arg = filtre_sql(liste(kat), liste(kaynak), q, liste(takip), bas, bit)
    sira = "MAX(h.yayin) DESC" if siralama == "son" else "COUNT(DISTINCT h.kaynak_id) DESC, MAX(h.yayin) DESC"
    with oturum() as con:
        toplam = con.execute(
            f"SELECT COUNT(DISTINCT h.olay_id) FROM haber h JOIN kaynak k ON k.id=h.kaynak_id {nerede}", arg
        ).fetchone()[0]
        oids = [r[0] for r in con.execute(
            f"""SELECT h.olay_id FROM haber h JOIN kaynak k ON k.id=h.kaynak_id {nerede}
                GROUP BY h.olay_id ORDER BY {sira} LIMIT ? OFFSET ?""", [*arg, adet, sayfa * adet])]
        if not oids:
            return {"toplam": toplam, "olaylar": []}
        yer = ",".join("?" * len(oids))
        olay = {r["id"]: dict(r) for r in con.execute(f"SELECT * FROM olay WHERE id IN ({yer})", oids)}
        haberler = defaultdict(list)
        for r in con.execute(
                f"""SELECT h.id, h.baslik, h.ozet, h.url, h.gorsel, h.yayin, h.olay_id, h.kaynak_id,
                           k.ad kaynak_ad, k.kategori FROM haber h JOIN kaynak k ON k.id=h.kaynak_id
                    WHERE h.olay_id IN ({yer}) ORDER BY h.yayin""", oids):
            haberler[r["olay_id"]].append(haber_json(r))
    sonuc = []
    for oid in oids:
        o, hs = olay[oid], haberler[oid]
        ilk = hs[0] if hs else None
        ozet = next((h["ozet"] for h in hs if h["ozet"]), "")
        kats = Counter(h["kaynak"]["kategori"] for h in hs)
        sonuc.append({
            "id": oid, "baslik": ilk["baslik"] if ilk else o["baslik"], "ozet": ozet,
            "ilk": o["ilk"], "son": o["son"], "haber_sayisi": o["haber_sayisi"], "kaynak_sayisi": o["kaynak_sayisi"],
            "kategori": kats.most_common(1)[0][0] if kats else None,
            "gorsel": next((h["gorsel"] for h in hs if h["gorsel"]), None),
            "haberler": hs[-40:],
        })
    return {"toplam": toplam, "olaylar": sonuc}


_trend_onbellek: dict = {}


@app.get("/api/trendler")
def trendler(pencere_saat: int = 2, taban_saat: int = 24, adet: int = 10):
    anahtar = (pencere_saat, taban_saat, adet, int(time.time()) // 120)
    if anahtar in _trend_onbellek:
        return _trend_onbellek[anahtar]
    simdi = int(time.time())
    p_bas = simdi - pencere_saat * 3600
    t_bas = p_bas - taban_saat * 3600
    with oturum() as con:
        satirlar = con.execute(
            """SELECT h.baslik, h.yayin, h.olay_id, COALESCE(NULLIF(k.site, ''), k.id) site FROM haber h
               JOIN kaynak k ON k.id=h.kaynak_id WHERE h.yayin >= ?""", (t_bas,)).fetchall()
    simdi_say, taban_say, siteler, bicim = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(Counter)
    for r in satirlar:
        yeni = r["yayin"] >= p_bas
        hedef = simdi_say if yeni else taban_say
        for ad in metin.ozel_adlar(r["baslik"]):
            anahtar_k = metin.katla(ad)
            hedef[anahtar_k].add(r["olay_id"])
            bicim[anahtar_k][ad] += 1
            if yeni:
                siteler[anahtar_k].add(r["site"])
    sonuc = []
    for t, olaylar_ in simdi_say.items():
        n = len(olaylar_)
        if n < 3 or len(t) < 3 or len(siteler[t]) < 4:
            continue
        hiz_simdi = n / pencere_saat
        hiz_taban = (len(taban_say.get(t, ())) + 1) / taban_saat
        oran = hiz_simdi / hiz_taban
        if oran < 3:
            continue
        sonuc.append({"terim": bicim[t].most_common(1)[0][0], "olay": n, "oran": round(oran, 1), "site": len(siteler[t]),
                      "taban": len(taban_say.get(t, ()))})
    # Çok sözcüklü bir adın parçası olan tek sözcükleri ele (Serdal Adalı varken Adalı ayrıca görünmesin).
    coklu = [x for x in sonuc if " " in x["terim"]]
    sonuc = [x for x in sonuc if " " in x["terim"] or not any(
        x["terim"] in c["terim"].split() and c["site"] * 2 >= x["site"] for c in coklu)]
    sonuc.sort(key=lambda x: -math.log(x["oran"] + 1) * x["site"])
    sonuc = sonuc[:adet]
    _trend_onbellek.clear()
    _trend_onbellek[anahtar] = sonuc
    return sonuc


@app.get("/api/istatistik")
def istatistik(saat: int = 24, kat: str | None = None, kaynak: str | None = None, q: str | None = None,
               takip: str | None = None):
    simdi = int(time.time())
    bas = simdi - saat * 3600
    nerede, arg = filtre_sql(liste(kat), liste(kaynak), q, liste(takip), bas, None)
    with oturum() as con:
        ozet = con.execute(
            f"""SELECT COUNT(*) haber, COUNT(DISTINCT h.olay_id) olay, COUNT(DISTINCT h.kaynak_id) kaynak
                FROM haber h JOIN kaynak k ON k.id=h.kaynak_id {nerede}""", arg).fetchone()
        saatlik = con.execute(
            f"""SELECT (h.yayin - ?) / 3600 dilim, k.kategori, COUNT(*) n FROM haber h
                JOIN kaynak k ON k.id=h.kaynak_id {nerede} GROUP BY 1, 2""", [bas, *arg]).fetchall()
        en_kaynak = con.execute(
            f"""SELECT k.id, k.ad, COUNT(*) n FROM haber h JOIN kaynak k ON k.id=h.kaynak_id {nerede}
                GROUP BY k.id ORDER BY n DESC LIMIT 10""", arg).fetchall()
        kat_dagilim = con.execute(
            f"""SELECT k.kategori, COUNT(*) n FROM haber h JOIN kaynak k ON k.id=h.kaynak_id {nerede}
                GROUP BY 1 ORDER BY n DESC""", arg).fetchall()
        durum = dict(con.execute("SELECT durum, COUNT(*) FROM kaynak WHERE aktif=1 GROUP BY 1").fetchall())
        son_tur = con.execute("SELECT MAX(son_kontrol) FROM kaynak").fetchone()[0]
    dilimler = [defaultdict(int) for _ in range(saat)]
    for r in saatlik:
        if 0 <= r["dilim"] < saat:
            dilimler[r["dilim"]][r["kategori"]] += r["n"]
    return {
        "haber": ozet["haber"], "olay": ozet["olay"], "kaynak": ozet["kaynak"], "baslangic": bas,
        "saatlik": [dict(d) for d in dilimler],
        "kaynaklar": [dict(r) for r in en_kaynak],
        "kategoriler": [dict(r) for r in kat_dagilim],
        "kaynak_durum": durum, "son_tarama": son_tur,
    }


# ---------- site simgeleri ----------

@app.get("/simge/{kaynak_id}")
def simge(kaynak_id: str):
    from .simgeler import alan_adi, bul
    with oturum() as con:
        r = con.execute("SELECT ad, site, url FROM kaynak WHERE id=?", (kaynak_id,)).fetchone()
    if not r:
        raise HTTPException(404)
    sonuc = bul(alan_adi(r["site"] or r["url"])) or bul(alan_adi(r["url"]))
    onbellek = {"Cache-Control": "public, max-age=604800"}
    if sonuc:
        return FileResponse(sonuc[0], media_type=sonuc[1], headers=onbellek)
    # Simge yoksa kaynak adının baş harfiyle sade bir rozet
    harf = escape((r["ad"] or "?").strip()[:1].upper())
    renk = ["#378ADD", "#1D9E75", "#BA7517", "#7F77DD", "#D4537E", "#D85A30", "#534AB7", "#5F5E5A"][
        sum(map(ord, kaynak_id)) % 8]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="16" fill="{renk}"/>'
           f'<text x="16" y="21.5" font-family="system-ui,sans-serif" font-size="15" font-weight="600" fill="#fff" '
           f'text-anchor="middle">{harf}</text></svg>')
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})


# ---------- panel ----------

app.mount("/statik", StaticFiles(directory=WEB), name="statik")


@app.get("/")
def panel():
    return FileResponse(WEB / "index.html")
