"""Ortam değişkenleriyle yapılandırma."""
import os
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent


def _int(ad: str, varsayilan: int) -> int:
    return int(os.environ.get(ad, varsayilan))


VERI_YOLU = Path(os.environ.get("MT_VERI", KOK / "data" / "medya.db"))
KAYNAK_DOSYASI = Path(os.environ.get("MT_KAYNAKLAR", KOK / "sources" / "kaynaklar.yaml"))
TOPLAMA_ARALIGI_DK = _int("MT_ARALIK_DK", 10)      # beslemeler kaç dakikada bir taransın
SAKLAMA_GUN = _int("MT_SAKLAMA_GUN", 30)            # haberler kaç gün tutulsun
TAM_METIN = os.environ.get("MT_TAM_METIN", "1") == "1"  # makale tam metni arama için çekilsin mi
TAM_METIN_SAKLAMA_GUN = _int("MT_TAM_METIN_GUN", 7)
ESZAMANLI = _int("MT_ESZAMANLI", 20)
SITE_BASINA = _int("MT_SITE_BASINA", 2)            # aynı siteye aynı anda en fazla istek
OLAY_PENCERESI_SAAT = _int("MT_OLAY_SAAT", 48)      # kümeleme için geriye bakılacak süre
GENEL_ADRES = os.environ.get("MT_GENEL_ADRES", "")  # birleşik beslemelerdeki mutlak adres, ör. https://ornek.org
SIMGE_KLASORU = Path(os.environ.get("MT_SIMGELER", KOK / "simgeler"))  # site simgeleri (favicon)
