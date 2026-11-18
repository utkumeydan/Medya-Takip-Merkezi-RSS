"""SQLite şeması ve bağlantı. Tam metin arama FTS5 ile yapılır."""
import sqlite3
from contextlib import contextmanager

from .ayarlar import VERI_YOLU

SEMA = """
CREATE TABLE IF NOT EXISTS kaynak (
    id TEXT PRIMARY KEY,
    ad TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    kategori TEXT NOT NULL,
    tur TEXT NOT NULL DEFAULT 'rss',
    site TEXT,
    durum TEXT DEFAULT 'bilinmiyor',
    hata TEXT,
    son_haber INTEGER,
    son_kontrol INTEGER,
    etag TEXT,
    last_modified TEXT,
    aktif INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS olay (
    id INTEGER PRIMARY KEY,
    baslik TEXT NOT NULL,
    imza TEXT NOT NULL,
    ilk INTEGER NOT NULL,
    son INTEGER NOT NULL,
    haber_sayisi INTEGER DEFAULT 0,
    kaynak_sayisi INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS olay_son ON olay(son);
CREATE TABLE IF NOT EXISTS haber (
    id INTEGER PRIMARY KEY,
    kaynak_id TEXT NOT NULL REFERENCES kaynak(id),
    guid TEXT NOT NULL,
    url TEXT NOT NULL,
    baslik TEXT NOT NULL,
    ozet TEXT,
    gorsel TEXT,
    yayin INTEGER NOT NULL,
    toplandi INTEGER NOT NULL,
    tam_metin TEXT,
    tam_metin_durum INTEGER DEFAULT 0,
    olay_id INTEGER REFERENCES olay(id),
    UNIQUE(kaynak_id, guid)
);
CREATE INDEX IF NOT EXISTS haber_yayin ON haber(yayin);
CREATE INDEX IF NOT EXISTS haber_olay ON haber(olay_id);
CREATE INDEX IF NOT EXISTS haber_kaynak ON haber(kaynak_id, yayin);
CREATE INDEX IF NOT EXISTS haber_url ON haber(url);
-- Arama dizini Türkçe katlanmış metinle (ı→i, ş→s ...) Python tarafından doldurulur.
CREATE VIRTUAL TABLE IF NOT EXISTS haber_fts USING fts5(
    baslik, govde, tokenize='unicode61 remove_diacritics 2'
);
"""


def baglan() -> sqlite3.Connection:
    VERI_YOLU.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(VERI_YOLU, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def kur() -> None:
    with baglan() as con:
        con.executescript(SEMA)


@contextmanager
def oturum():
    con = baglan()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def fts_yaz(con, hid: int, baslik: str, ozet: str | None, tam: str | None) -> None:
    from .metin import katla
    con.execute("DELETE FROM haber_fts WHERE rowid=?", (hid,))
    con.execute("INSERT INTO haber_fts(rowid, baslik, govde) VALUES (?,?,?)",
                (hid, katla(baslik), katla((ozet or "") + " " + (tam or ""))))
