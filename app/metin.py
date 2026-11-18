"""Türkçe metin yardımcıları: normalleştirme, kök, başlık imzası, benzerlik."""
import html
import re

DURAK = set("""
acaba ama ancak artık aslında az bana bazı belki ben beni benim bile bir biraz birçok birkaç biri birisi
birşey biz bize bizi bizim bu buna bunda bundan bunu bunun burada çok çünkü da daha dahi de defa diye
diğer en gibi göre hem hep hepsi her hiç için ile ise işte kadar kendi ki kim mi mu mü mı nasıl ne neden
nerede niçin niye o olan olarak oldu olduğu olduğunu olmak olur ona ondan onlar onları onu onun orada
sadece sanki şey siz şu şuna şunu tüm ve veya ya yani yine yok zaten son dakika flaş haber haberi
haberleri açıklama açıkladı geldi yaptı etti eden edildi oldu olacak var yeni ilk sonra önce 'nin
ile' video foto galeri canlı izle tıkla işte bugün dün yarın saat yıl gün
""".split())

_KESME = re.compile(r"['’`´][a-zçğıöşü]+", re.IGNORECASE)
_KELIME = re.compile(r"[0-9a-zçğıöşüâîû]+")
_ETIKET = re.compile(r"<[^>]+>")
_BOSLUK = re.compile(r"\s+")


def tr_kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


_KATLA = str.maketrans("ıİIçÇğĞöÖşŞüÜâÂîÎûÛ", "iiiccggoossuuaaiiuu")


def katla(s: str) -> str:
    """Arama için: Türkçe küçük harf ve aksan katlama (Işık → isik)."""
    return s.translate(_KATLA).lower()


def duz_metin(s: str | None, sinir: int | None = None) -> str:
    if not s:
        return ""
    s = _BOSLUK.sub(" ", html.unescape(_ETIKET.sub(" ", s))).strip()
    if sinir and len(s) > sinir:
        s = s[:sinir].rsplit(" ", 1)[0] + "…"
    return s


def kelimeler(baslik: str) -> list[str]:
    return _KELIME.findall(tr_kucuk(_KESME.sub("", baslik)))


def kok(k: str) -> str:
    return k if k.isdigit() else k[:5]


def imza(baslik: str) -> set[str]:
    return {kok(k) for k in kelimeler(baslik) if k not in DURAK and len(k) > 1}


def benzer(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    ortak = len(a & b)
    jaccard = ortak / len(a | b)
    kapsama = ortak / min(len(a), len(b))
    return jaccard >= 0.5 or (ortak >= 4 and kapsama >= 0.7)


_SOZ = re.compile(r"[0-9A-Za-zÇĞİÖŞÜçğıöşüâîûÂÎÛ]+(?:['’][a-zçğıöşü]+)?")


def _ozel_mi(w: str) -> bool:
    return (w[0].isupper() and len(w) >= 3) or (w.isupper() and 2 <= len(w) <= 6)


def ozel_adlar(baslik: str) -> set[str]:
    """Başlıktaki kişi, kurum, yer adı adayları. Ardışık büyük harfli sözcükler tek ad sayılır
    (Serdal Adalı); her sözcüğü büyük harfle yazılmış başlıklarda sözcükler tek tek alınır."""
    sozler, kesik, onceki = [], [], 0
    for m in _SOZ.finditer(baslik):
        kesik.append(bool(baslik[onceki:m.start()].strip()))  # araya noktalama girdiyse ad biter
        sozler.append(re.split(r"['’]", m.group(0))[0])
        onceki = m.end()
        if "'" in m.group(0) or "’" in m.group(0):
            onceki = m.end()
            kesik.append(True)  # ek almış sözcük adı bitirir: "Güler'in sözleşmesi"
            sozler.append("")
    if not any(sozler):
        return set()
    gercek = [w for w in sozler if w]
    baslik_duzeni = sum(1 for w in gercek if w[0].isupper()) / len(gercek) > 0.6
    out, dizi = set(), []

    def bitir():
        if dizi:
            if baslik_duzeni or len(dizi) > 3:
                out.update(dizi)
            else:
                out.add(" ".join(dizi))
            dizi.clear()

    for w, k in zip(sozler, kesik):
        if k:
            bitir()
        if w and _ozel_mi(w) and tr_kucuk(w) not in DURAK and not w.isdigit():
            dizi.append(w)
        else:
            bitir()
    bitir()
    return out
