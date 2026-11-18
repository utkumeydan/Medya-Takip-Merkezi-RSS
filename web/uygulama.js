"use strict";
/* Medya Takip paneli — derleme adımı yok, bağımlılık yok. */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const sayi = (n) => new Intl.NumberFormat("tr-TR").format(n ?? 0);
const TABAN = location.origin;

/* ---------- simgeler (elle çizilmiş, 24x24) ---------- */
const IK = {
  rss: '<path d="M5 19h.01M4 4a16 16 0 0 1 16 16M4 11a9 9 0 0 1 9 9"/>',
  ara: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 20 20"/>',
  kopya: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  indir: '<path d="M12 4v11m-4.5-4.5L12 15l4.5-4.5M5 19.5h14"/>',
  yukle: '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M5 19.5h14"/>',
  kaydet: '<path d="M7 4h10a1 1 0 0 1 1 1v15l-6-4-6 4V5a1 1 0 0 1 1-1z"/>',
  not: '<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M9 9h6M9 13h6M9 17h3"/>',
  arti: '<path d="M12 5v14M5 12h14"/>',
  kapat: '<path d="m6 6 12 12M18 6 6 18"/>',
  liste: '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
  dis: '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
  github: '<path d="M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21"/>',
};
const ik = (ad) => `<span class="ik"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IK[ad]}</svg></span>`;
const simgeleriDoldur = (el = document) => $$("[data-ik]", el).forEach((s) => { s.outerHTML = ik(s.dataset.ik); });
const simge = (kaynakId) => `/simge/${encodeURIComponent(kaynakId)}`;

/* ---------- tarayıcı deposu ---------- */
const depo = {
  oku(k, v) { try { const x = localStorage.getItem("mt." + k); return x == null ? v : JSON.parse(x); } catch { return v; } },
  yaz(k, v) { try { localStorage.setItem("mt." + k, JSON.stringify(v)); } catch {} },
};
let takipListesi = depo.oku("takip", ["Galatasaray", "Fenerbahçe", "Beşiktaş"]);
let takipKapali = new Set(depo.oku("takipKapali", ["Galatasaray", "Fenerbahçe", "Beşiktaş"]));
let kayitlar = depo.oku("kayit", {});   // olayId -> {olay, etiketler, not, tarih}
let secili = new Set(depo.oku("secili", []));

function bildir(m) {
  const b = $("#bildirim"); b.textContent = m; b.classList.add("goster");
  clearTimeout(bildir.t); bildir.t = setTimeout(() => b.classList.remove("goster"), 1700);
}
async function kopyala(metin, mesaj = "Kopyalandı") {
  try { await navigator.clipboard.writeText(metin); }
  catch { const t = document.createElement("textarea"); t.value = metin; document.body.append(t); t.select(); document.execCommand("copy"); t.remove(); }
  bildir(mesaj);
}
async function api(yol, params = {}) {
  const u = new URL(yol, TABAN);
  Object.entries(params).forEach(([k, v]) => { if (v !== "" && v != null) u.searchParams.set(k, v); });
  const r = await fetch(u);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

/* ---------- zaman ---------- */
function once(t) {
  const s = Math.max(0, Date.now() / 1000 - t);
  if (s < 60) return "az önce";
  if (s < 3600) return Math.floor(s / 60) + " dk önce";
  if (s < 86400) return Math.floor(s / 3600) + " sa önce";
  return Math.floor(s / 86400) + " gün önce";
}
const saatDk = (t) => new Date(t * 1000).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
const tarihSaat = (t) => new Date(t * 1000).toLocaleString("tr-TR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/* ---------- Türkçe vurgulama ---------- */
const HARF = { i: "[iİıI]", ı: "[iİıI]", s: "[sşSŞ]", ş: "[sşSŞ]", c: "[cçCÇ]", ç: "[cçCÇ]", g: "[gğGĞ]", ğ: "[gğGĞ]", o: "[oöOÖ]", ö: "[oöOÖ]", u: "[uüUÜ]", ü: "[uüUÜ]" };
function vurguDeseni(terimler) {
  const parca = terimler.filter(Boolean).map((t) =>
    [...t.toLocaleLowerCase("tr")].map((c) => HARF[c] || c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join(""));
  return parca.length ? new RegExp("(" + parca.join("|") + ")", "gi") : null;
}
const vurgula = (metin, desen) => desen ? esc(metin).replace(desen, "<mark>$1</mark>") : esc(metin);

/* ---------- veri ---------- */
let KATEGORILER = [], KAT_AD = {}, KAYNAKLAR = [], KAYNAK = {};
const RENK = { gundem: "#378ADD", spor: "#1D9E75", ekonomi: "#BA7517", teknoloji: "#7F77DD", bilim: "#0F6E56", "kultur-sanat": "#D4537E",
  yasam: "#639922", eglence: "#D85A30", "is-dunyasi": "#993C1D", savunma: "#5F5E5A", resmi: "#185FA5", yerel: "#534AB7", video: "#E24B4A", sorgu: "#888780" };
const katRenk = (id) => RENK[id] || "#888780";

async function temelVeri() {
  [KATEGORILER, KAYNAKLAR] = await Promise.all([api("/api/kategoriler"), api("/api/kaynaklar")]);
  KAT_AD = Object.fromEntries(KATEGORILER.map((k) => [k.id, k.ad]));
  KAYNAK = Object.fromEntries(KAYNAKLAR.map((k) => [k.id, k]));
  $("#f-kaynak").insertAdjacentHTML("beforeend", [...KAYNAKLAR].sort((a, b) => a.ad.localeCompare(b.ad, "tr"))
    .map((k) => `<option value="${k.id}">${esc(k.ad)}</option>`).join(""));
}

/* =====================================================================
   PARÇALAR
   ===================================================================== */
const etk = (k) => k ? `<span class="etk"><i style="background:${katRenk(k)}"></i>${esc(KAT_AD[k] || k)}</span>` : "";
function farkliKaynaklar(o) {
  return [...new Map(o.haberler.map((h) => [h.kaynak.id, h.kaynak])).values()];
}
function yuzler(o, n = 4) {
  return `<span class="yuzler">${farkliKaynaklar(o).slice(0, n).map((k) =>
    `<img src="${simge(k.id)}" alt="" title="${esc(k.ad)}" loading="lazy">`).join("")}</span>`;
}
function gorselYuklendi(img) { img.classList.add("yuklendi"); }
function gorselHatasi(img) {
  const kap = img.closest("[data-yedek]");
  if (kap) kap.insertAdjacentHTML("beforeend", kap.dataset.yedek);
  img.remove();
}
window.gorselYuklendi = gorselYuklendi; window.gorselHatasi = gorselHatasi;

function resimsiz(o) {
  const k = o.haberler[0]?.kaynak || {};
  return `<div class="resimsiz" style="--k:${katRenk(o.kategori)}"><img src="${simge(k.id)}" alt="">${esc(k.ad || "")}</div>`;
}
function resimAlani(o, ek = "") {
  const yedek = esc(resimsiz(o));
  return `<div class="resim" data-yedek="${yedek}">${o.gorsel
    ? `<img src="${esc(o.gorsel)}" alt="" loading="lazy" referrerpolicy="no-referrer" onload="gorselYuklendi(this)" onerror="gorselHatasi(this)">`
    : resimsiz(o)}${ek}</div>`;
}

function kart(o, i, desen) {
  const ilk = o.haberler[0] || {};
  const kayit = kayitlar[o.id];
  const dugmeler = `<div class="kart-dugmeler">
      <button data-kaydet class="${kayit ? "acik" : ""}" aria-label="Kaydet" title="Kaydet">${ik("kaydet")}</button>
      <button data-not class="${kayit?.not ? "acik" : ""}" aria-label="Not ve etiket" title="Not ve etiket">${ik("not")}</button></div>`;
  const kayitEk = kayit && (kayit.etiketler?.length || kayit.not)
    ? `<div class="kayit-ek">${(kayit.etiketler || []).map((e) => `<span class="hap mavi">#${esc(e)}</span>`).join("")}</div>${kayit.not ? `<p class="kayit-not">${esc(kayit.not)}</p>` : ""}` : "";
  return `<article class="kart" tabindex="0" data-olay="${o.id}" style="animation-delay:${Math.min(i, 12) * 40}ms">
    ${resimAlani(o, etk(o.kategori) + dugmeler)}
    <div class="govde">
      <h4>${vurgula(o.baslik, desen)}</h4>
      ${o.ozet ? `<p class="ozet">${vurgula(o.ozet, desen)}</p>` : ""}
      ${kayitEk}
      <div class="alt">${yuzler(o)}<span>${o.kaynak_sayisi > 1 ? `<span class="kaynak-say">${o.kaynak_sayisi} kaynak</span> · ` : esc(ilk.kaynak?.ad || "") + " · "}${once(o.son)}</span></div>
    </div>
  </article>`;
}

function gkart(o, buyuk, i) {
  return `<article class="gkart ${buyuk ? "buyuk" : ""} ${o.gorsel ? "" : "resimsiz-g"}" tabindex="0" data-olay="${o.id}" style="--k:${katRenk(o.kategori)};animation-delay:${i * 90}ms">
    ${o.gorsel ? `<img class="zemin" src="${esc(o.gorsel)}" alt="" referrerpolicy="no-referrer" onerror="this.parentNode.classList.add('resimsiz-g');this.remove()">` : ""}
    <div class="ic">${etk(o.kategori)}<h3>${esc(o.baslik)}</h3>${buyuk && o.ozet ? `<p class="ozet">${esc(o.ozet)}</p>` : ""}
    <div class="alt">${yuzler(o, 5)}<span>${o.kaynak_sayisi} kaynak · ${once(o.son)}</span></div></div>
  </article>`;
}

/* =====================================================================
   AKIŞ
   ===================================================================== */
const durum = { sayfa: 0, olaylar: [], manset: [], enYeni: 0, kat: depo.oku("akisKat", "") };
const etkinTakip = () => takipListesi.filter((t) => !takipKapali.has(t));
function filtreler() {
  return { q: $("#ara").value.trim(), takip: etkinTakip().join(","), kat: durum.kat, kaynak: $("#f-kaynak").value,
    saat: $("#f-saat").value, siralama: $("#f-sira").value };
}
const desenAl = () => vurguDeseni([...etkinTakip(), ...$("#ara").value.trim().split(/\s+/)]);

function takipCizimi() {
  $("#takip-cipler").innerHTML = takipListesi.map((t) =>
    `<button class="cip ${takipKapali.has(t) ? "" : "acik"}" data-terim="${esc(t)}" title="Aç / kapat">${esc(t)}<span class="sil" data-sil="${esc(t)}" aria-label="${esc(t)} terimini sil">${ik("kapat")}</span></button>`).join("");
}
$("#takip-cipler").addEventListener("click", (e) => {
  const sil = e.target.closest("[data-sil]");
  if (sil) { takipListesi = takipListesi.filter((t) => t !== sil.dataset.sil); takipKapali.delete(sil.dataset.sil); }
  else {
    const c = e.target.closest("[data-terim]"); if (!c) return;
    const t = c.dataset.terim; takipKapali.has(t) ? takipKapali.delete(t) : takipKapali.add(t);
  }
  depo.yaz("takip", takipListesi); depo.yaz("takipKapali", [...takipKapali]);
  takipCizimi(); akisYukle();
});
$("#takip-ekle").addEventListener("submit", (e) => {
  e.preventDefault();
  const g = $("#takip-girdi"), t = g.value.trim();
  if (!t) { g.focus(); return; }
  if (!takipListesi.some((x) => x.toLocaleLowerCase("tr") === t.toLocaleLowerCase("tr"))) takipListesi.push(t);
  takipKapali.delete(t); g.value = "";
  depo.yaz("takip", takipListesi); depo.yaz("takipKapali", [...takipKapali]);
  takipCizimi(); akisYukle();
});

function katFiltreCiz() {
  const gizli = ["sorgu", "video", "resmi"];
  $("#kat-filtre").innerHTML = `<button class="${durum.kat ? "" : "on"}" data-k="">Tümü</button>` +
    KATEGORILER.filter((k) => !gizli.includes(k.id) || durum.kat === k.id)
      .map((k) => `<button class="${durum.kat === k.id ? "on" : ""}" data-k="${k.id}"><i style="background:${katRenk(k.id)}"></i>${esc(k.ad)}</button>`).join("");
}
$("#kat-filtre").addEventListener("click", (e) => {
  const b = e.target.closest("[data-k]"); if (!b) return;
  durum.kat = b.dataset.k; depo.yaz("akisKat", durum.kat);
  katFiltreCiz(); akisYukle({ mansetsiz: false, kaydir: true });
});

async function mansetYukle() {
  const f = filtreler();
  const bolum = $("#manset-bolum");
  if (f.q) { bolum.hidden = true; durum.manset = []; return; }
  bolum.hidden = false;
  try {
    const d = await api("/api/olaylar", { ...f, saat: Math.min(+f.saat, 6) || 6, siralama: "kaynak", adet: 15 });
    const gorselli = d.olaylar.filter((o) => o.gorsel && o.kaynak_sayisi > 1);
    durum.manset = (gorselli.length >= 3 ? gorselli : d.olaylar).slice(0, 3);
    if (!durum.manset.length) { bolum.hidden = true; return; }
    $("#manset").innerHTML = durum.manset.map((o, i) => gkart(o, i === 0, i)).join("");
  } catch { bolum.hidden = true; }
}

async function olaylariYukle(ekle = false) {
  const f = filtreler();
  if (!ekle) durum.sayfa = 0;
  const liste = $("#olaylar");
  if (!ekle) liste.innerHTML = Array.from({ length: 6 }, () => '<div class="yer kart-yer"></div>').join("");
  try {
    const d = await api("/api/olaylar", { ...f, sayfa: durum.sayfa, adet: 30 });
    durum.olaylar = ekle ? durum.olaylar.concat(d.olaylar) : d.olaylar;
    if (!ekle) durum.enYeni = Math.max(0, ...d.olaylar.map((o) => o.son));
    const desen = desenAl();
    const html = d.olaylar.map((o, i) => kart(o, i, desen)).join("");
    if (ekle) liste.insertAdjacentHTML("beforeend", html);
    else liste.innerHTML = html || '<div class="bos">Bu filtrelerle haber bulunamadı. Zaman aralığını genişletmeyi ya da takip terimlerini kapatmayı dene.</div>';
    $("#daha").hidden = durum.olaylar.length >= d.toplam;
    $("#yeni-bant").hidden = true;
    $("#akis-sayi").textContent = d.toplam ? `${sayi(d.toplam)} gelişme` : "";
  } catch {
    liste.innerHTML = '<div class="bos">Haberler yüklenemedi. Sunucuya ulaşılamıyor olabilir.</div>';
  }
}

function kivilcim(x) {
  const once_ = x.taban / 24 + 0.2, simdi = x.olay / 2 + 0.2, m = Math.max(once_, simdi);
  const y = [once_, once_, once_ * 1.1, simdi * .7, simdi].map((v, i) => `${i * 10.5 + 1},${17 - (v / m) * 14}`).join(" ");
  return `<svg viewBox="0 0 44 18" aria-hidden="true"><polyline points="${y}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

async function istatistikYukle() {
  const f = filtreler();
  const [s, t] = await Promise.all([api("/api/istatistik", { ...f }), api("/api/trendler")]).catch(() => [null, null]);
  if (t) {
    $("#serit").innerHTML = t.length ? t.map((x, i) =>
      `<button class="trend" data-trend="${esc(x.terim)}" style="animation-delay:${i * 50}ms" title="${x.site} sitede, ${x.olay} olay — bununla ara"><span class="sira">${i + 1}</span><span class="ad">${esc(x.terim)}</span>${kivilcim(x)}<span class="x">×${String(x.oran).replace(".", ",")}</span></button>`).join("")
      : '<span class="sakin">Şu an belirgin bir sıçrama yok. Trendler veri biriktikçe burada görünür.</span>';
  }
  if (!s) return;
  const sure = { 1: "son 1 saat", 6: "son 6 saat", 24: "son 24 saat", 168: "son 7 gün", 720: "son 30 gün" }[f.saat];
  $("#canli-yazi").textContent = `Canlı · ${sure} ${sayi(s.haber)} haber`;
  $("#grafik-aciklama").textContent = sure;
  $("#m-haber").textContent = sayi(s.haber);
  $("#m-olay").textContent = sayi(s.olay);
  $("#m-kaynak").textContent = sayi(s.kaynak);
  grafikCiz(s, +f.saat);
  const enCok = Math.max(1, ...s.kaynaklar.map((k) => k.n));
  $("#en-kaynak").innerHTML = s.kaynaklar.slice(0, 8).map((k) =>
    `<div class="cubuk-satir"><img src="${simge(k.id)}" alt=""><span title="${esc(k.ad)}">${esc(k.ad)}</span><div class="cubuk-yol"><div class="cubuk" data-w="${(k.n / enCok) * 100}"></div></div><span class="n">${sayi(k.n)}</span></div>`).join("");
  const katCok = Math.max(1, ...s.kategoriler.map((k) => k.n));
  $("#kat-dagilim").innerHTML = s.kategoriler.slice(0, 8).map((k) =>
    `<div class="cubuk-satir kat"><span>${esc(KAT_AD[k.kategori] || k.kategori)}</span><div class="cubuk-yol"><div class="cubuk" data-w="${(k.n / katCok) * 100}" style="background:${katRenk(k.kategori)}"></div></div><span class="n">${sayi(k.n)}</span></div>`).join("");
  requestAnimationFrame(() => requestAnimationFrame(() => $$(".cubuk[data-w]").forEach((c) => c.style.width = c.dataset.w + "%")));
}

function grafikCiz(s, saat) {
  const adim = saat > 48 ? 24 : 1;
  const dilim = [];
  for (let i = 0; i < s.saatlik.length; i += adim) {
    const d = {}; s.saatlik.slice(i, i + adim).forEach((x) => Object.entries(x).forEach(([k, n]) => d[k] = (d[k] || 0) + n));
    dilim.push(d);
  }
  const kats = s.kategoriler.map((k) => k.kategori);
  const W = 300, H = 110, alt = 14, gen = W / dilim.length;
  const enCok = Math.max(1, ...dilim.map((d) => Object.values(d).reduce((a, b) => a + b, 0)));
  let svg = "";
  dilim.forEach((d, i) => {
    let y = H - alt, parca = "";
    const toplam = Object.values(d).reduce((a, b) => a + b, 0);
    kats.forEach((k) => {
      const h = ((d[k] || 0) / enCok) * (H - alt - 6); if (!h) return;
      y -= h; parca += `<rect x="${i * gen + 1}" y="${y}" width="${Math.max(1, gen - 2)}" height="${h}" fill="${katRenk(k)}"><title>${esc(KAT_AD[k] || k)}: ${d[k]}</title></rect>`;
    });
    svg += `<g class="c" style="animation-delay:${i * 18}ms">${parca}</g>`;
    const t = s.baslangic + i * adim * 3600;
    if (i % Math.ceil(dilim.length / 6) === 0) {
      const et = adim > 1 ? new Date(t * 1000).toLocaleDateString("tr-TR", { day: "numeric", month: "short" }) : saatDk(t).slice(0, 2) + ":00";
      svg += `<text class="eksen" x="${i * gen + 1}" y="${H - 2}">${et}</text>`;
    }
    svg += `<rect x="${i * gen}" y="0" width="${gen}" height="${H - alt}" fill="transparent"><title>${toplam} haber</title></rect>`;
  });
  $("#grafik").innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Zamana göre haber sayısı">${svg}</svg>`;
  $("#grafik-lejant").innerHTML = kats.slice(0, 7).map((k) => `<span><i style="background:${katRenk(k)}"></i>${esc(KAT_AD[k] || k)}</span>`).join("");
}

function akisYukle({ kaydir = false } = {}) {
  mansetYukle(); olaylariYukle(); istatistikYukle(); beslemeKutusu();
  if (kaydir) $(".akis-baslik").scrollIntoView({ behavior: "smooth", block: "start" });
}

function beslemeAdresi(p) {
  const u = new URL("/feed", TABAN);
  Object.entries(p).forEach(([k, v]) => v && u.searchParams.set(k, v));
  return u.toString().replace(/%2C/g, ",");
}
function beslemeKutusu() {
  const kutu = $("#besleme-kutu"); if (kutu.hidden) return;
  const f = filtreler();
  const url = beslemeAdresi({ kat: f.kat, k: f.kaynak, q: f.q, takip: f.takip });
  kutu.innerHTML = `<span>Bu görünümün RSS adresi</span><code>${esc(url)}</code><button class="ikon" data-kopyala="${esc(url)}" aria-label="Kopyala">${ik("kopya")}</button>`;
}
$("#besleme-yap").addEventListener("click", () => { const k = $("#besleme-kutu"); k.hidden = !k.hidden; beslemeKutusu(); });
document.addEventListener("click", (e) => { const b = e.target.closest("[data-kopyala]"); if (b) { e.preventDefault(); kopyala(b.dataset.kopyala, "Adres kopyalandı"); } });

["#f-kaynak", "#f-saat", "#f-sira"].forEach((s) => $(s).addEventListener("change", () => akisYukle()));
$("#daha").addEventListener("click", () => { durum.sayfa++; olaylariYukle(true); });
$("#serit").addEventListener("click", (e) => { const b = e.target.closest("[data-trend]"); if (b) { $("#ara").value = b.dataset.trend; akisYukle({ kaydir: true }); } });
$("#yeni-bant").addEventListener("click", () => { window.scrollTo({ top: 0, behavior: "smooth" }); akisYukle(); });

setInterval(async () => {
  if (sekme.aktif() !== "takip" || durum.sayfa > 0 || document.hidden) return;
  try {
    const d = await api("/api/olaylar", { ...filtreler(), adet: 30 });
    const yeni = d.olaylar.filter((o) => o.son > durum.enYeni).length;
    if (yeni) { const b = $("#yeni-bant"); b.textContent = `${yeni} yeni gelişme · göster`; b.hidden = false; }
  } catch {}
}, 60000);

/* =====================================================================
   OLAY ÇEKMECESİ
   ===================================================================== */
let acikOlay = null;
function olayBul(id) {
  return durum.olaylar.find((o) => o.id === id) || durum.manset.find((o) => o.id === id) || kayitlar[id]?.olay;
}
function kayitDegisti() {
  depo.yaz("kayit", kayitlar);
  $("#kayit-sayac").textContent = Object.keys(kayitlar).length || "";
  $$(`[data-olay]`).forEach((el) => {
    const k = kayitlar[+el.dataset.olay];
    $("[data-kaydet]", el)?.classList.toggle("acik", !!k);
    $("[data-not]", el)?.classList.toggle("acik", !!k?.not);
  });
}
function kaydetDegistir(o) {
  if (kayitlar[o.id]) { delete kayitlar[o.id]; bildir("Kayıttan çıkarıldı"); }
  else { kayitlar[o.id] = { olay: o, etiketler: [], not: "", tarih: Date.now() }; bildir("Kaydedildi"); }
  kayitDegisti();
  if (sekme.aktif() === "kayit") kayitlariCiz();
}

function cekmeceAc(o, notaOdaklan = false) {
  acikOlay = o;
  const k = kayitlar[o.id] || {};
  const ilk = o.haberler[0] || {};
  const desen = desenAl();
  $("#cekmece-ic").innerHTML = `
    ${o.gorsel ? `<div class="c-resim"><img src="${esc(o.gorsel)}" alt="" referrerpolicy="no-referrer" onerror="this.parentNode.remove()"></div>` : '<div style="height:56px"></div>'}
    <div class="c-ic">
      ${etk(o.kategori)}
      <h2 id="c-baslik">${vurgula(o.baslik, desen)}</h2>
      ${o.ozet ? `<p class="ozet">${vurgula(o.ozet, desen)}</p>` : ""}
      <div class="c-ozet">${yuzler(o, 8)}<span>${o.kaynak_sayisi} kaynak · ${o.haber_sayisi} haber · ilk ${tarihSaat(o.ilk)}</span></div>
      <div class="c-dugmeler">
        <a class="dugme ana" href="${esc(ilk.url)}" target="_blank" rel="noopener">${ik("dis")} Habere git</a>
        <button data-c-kaydet class="${kayitlar[o.id] ? "acik" : ""}">${ik("kaydet")} ${kayitlar[o.id] ? "Kaydedildi" : "Kaydet"}</button>
      </div>
      <h3>Zaman çizelgesi</h3>
      <ol class="cizelge">${o.haberler.map((h, i) => `<li style="animation-delay:${Math.min(i, 15) * 30}ms"><img src="${simge(h.kaynak.id)}" alt=""><div>
        <div class="c-kaynak"><b>${esc(h.kaynak.ad)}</b> · <time title="${tarihSaat(h.yayin)}">${saatDk(h.yayin)}</time></div>
        <a href="${esc(h.url)}" target="_blank" rel="noopener">${vurgula(h.baslik, desen)}</a></div></li>`).join("")}</ol>
      <h3>Not ve etiketler</h3>
      <div class="not-alani">
        <textarea placeholder="Bu gelişmeyle ilgili notun" data-not-metin>${esc(k.not || "")}</textarea>
        <div class="satir"><input placeholder="Etiketler, virgülle: transfer, röportaj" data-etiket value="${esc((k.etiketler || []).join(", "))}">
        <button data-not-kaydet>Kaydet</button></div>
      </div>
    </div>`;
  const c = $("#cekmece"); c.hidden = false; c.classList.remove("kapaniyor");
  document.body.style.overflow = "hidden";
  $(".cekmece-panel").scrollTop = 0;
  setTimeout(() => (notaOdaklan ? $("[data-not-metin]") : $(".cekmece-kapat")).focus({ preventScroll: !notaOdaklan }), 50);
}
function cekmeceKapat() {
  const c = $("#cekmece"); if (c.hidden) return;
  c.classList.add("kapaniyor");
  setTimeout(() => { c.hidden = true; c.classList.remove("kapaniyor"); document.body.style.overflow = ""; }, 280);
  acikOlay = null;
}
$("#cekmece").addEventListener("click", (e) => {
  if (e.target.closest("[data-kapat]")) return cekmeceKapat();
  const o = acikOlay; if (!o) return;
  const kb = e.target.closest("[data-c-kaydet]");
  if (kb) {
    kaydetDegistir(o);
    kb.classList.toggle("acik", !!kayitlar[o.id]);
    kb.innerHTML = `${ik("kaydet")} ${kayitlar[o.id] ? "Kaydedildi" : "Kaydet"}`;
  }
  if (e.target.closest("[data-not-kaydet]")) {
    const not = $("[data-not-metin]").value.trim();
    const etiketler = $("[data-etiket]").value.split(",").map((x) => x.trim()).filter(Boolean);
    kayitlar[o.id] = { ...(kayitlar[o.id] || { olay: o, tarih: Date.now() }), not, etiketler };
    kayitDegisti(); bildir("Not kaydedildi");
    const kb2 = $("[data-c-kaydet]"); kb2.classList.add("acik"); kb2.innerHTML = `${ik("kaydet")} Kaydedildi`;
    if (sekme.aktif() === "kayit") kayitlariCiz();
  }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") cekmeceKapat(); });

function kartEtkilesim(kap) {
  kap.addEventListener("click", (e) => {
    const el = e.target.closest("[data-olay]"); if (!el) return;
    const o = olayBul(+el.dataset.olay); if (!o) return;
    if (e.target.closest("[data-kaydet]")) { e.stopPropagation(); kaydetDegistir(o); return; }
    cekmeceAc(o, !!e.target.closest("[data-not]"));
  });
  kap.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || e.target.closest("button")) return;
    const el = e.target.closest("[data-olay]"); if (!el) return;
    const o = olayBul(+el.dataset.olay); if (o) cekmeceAc(o);
  });
}
kartEtkilesim($("#olaylar")); kartEtkilesim($("#manset")); kartEtkilesim($("#kayitlar"));

/* =====================================================================
   RSS DİZİNİ
   ===================================================================== */
let dizinKat = depo.oku("dizinKat", "");
function dizinFiltre() {
  const q = $("#ara").value.trim().toLocaleLowerCase("tr"), d = $("#d-durum").value, t = $("#d-tur").value;
  return KAYNAKLAR.filter((k) =>
    (!dizinKat || k.kategori === dizinKat) && (!t || k.tur === t) &&
    (!d || (d === "sorun" ? ["olu", "durgun"].includes(k.durum) : k.durum === d)) &&
    (!q || k.ad.toLocaleLowerCase("tr").includes(q) || k.url.toLowerCase().includes(q)));
}
function durumHap(k) {
  const m = { canli: ["yesil", "canlı"], yavas: ["sari", "yavaş"], durgun: ["sari", "durgun"], olu: ["kirmizi", "erişilemiyor"], bilinmiyor: ["notr", "bekliyor"] }[k.durum] || ["notr", k.durum];
  return `<span class="hap ${m[0]}" title="${esc(k.hata || "")}">${m[1]}</span>`;
}
function dizinCiz() {
  const sayac = {}; KAYNAKLAR.forEach((k) => sayac[k.kategori] = (sayac[k.kategori] || 0) + 1);
  $("#kat-cipler").innerHTML = `<button class="${dizinKat ? "" : "on"}" data-kat="">Tümü <small>${KAYNAKLAR.length}</small></button>` +
    KATEGORILER.map((k) => `<button class="${dizinKat === k.id ? "on" : ""}" data-kat="${k.id}"><i style="background:${katRenk(k.id)}"></i>${esc(k.ad)} <small>${sayac[k.id] || 0}</small></button>`).join("");
  const liste = dizinFiltre();
  $("#d-sayi").textContent = `${sayi(liste.length)} kaynak`;
  $("#d-hepsi").checked = liste.length > 0 && liste.every((k) => secili.has(k.id));
  const gruplar = {}; liste.forEach((k) => (gruplar[k.kategori] ||= []).push(k));
  const q = $("#ara").value.trim();
  const desen = q ? vurguDeseni([q]) : null;
  $("#kaynak-liste").innerHTML = KATEGORILER.filter((c) => gruplar[c.id]).map((c) =>
    `<div class="grup-baslik"><i style="background:${katRenk(c.id)}"></i><b>${esc(c.ad)}</b><span>${gruplar[c.id].length}</span><span class="bosluk"></span>
      <button data-kat-liste="${c.id}" title="Bu kategorideki tüm adresleri kopyala">${ik("liste")} Tümünü kopyala</button>
      <a class="dugme" href="/api/opml?kat=${c.id}" download title="Bu kategorinin OPML dosyası">${ik("indir")} OPML</a></div>` +
    gruplar[c.id].map((k) => `<label class="kaynak">
      <input type="checkbox" data-sec="${k.id}" ${secili.has(k.id) ? "checked" : ""}>
      <img class="simge" src="${simge(k.id)}" alt="" loading="lazy">
      <div class="bilgi"><div class="ad">${vurgula(k.ad, desen)}</div><div class="url">${esc(k.url)}</div></div>
      <span class="meta">${k.son_haber ? "son haber " + once(k.son_haber) : ""}${k.haber_24s ? ` · 24 saatte ${sayi(k.haber_24s)}` : ""}</span>
      ${durumHap(k)}
      <span class="hap ${k.tur === "uretilen" ? "mavi" : "notr"}">${k.tur === "uretilen" ? "üretilen" : "RSS"}</span>
      <button class="ikon" data-kopyala="${esc(k.url)}" aria-label="${esc(k.ad)} adresini kopyala">${ik("kopya")}</button>
    </label>`).join("")).join("") || '<div class="bos">Eşleşen kaynak yok.</div>';
  secimCubugu();
}
$("#kat-cipler").addEventListener("click", (e) => { const b = e.target.closest("[data-kat]"); if (!b) return; dizinKat = b.dataset.kat; depo.yaz("dizinKat", dizinKat); dizinCiz(); });
["#d-durum", "#d-tur"].forEach((s) => $(s).addEventListener("change", dizinCiz));
$("#kaynak-liste").addEventListener("click", (e) => {
  const kl = e.target.closest("[data-kat-liste]");
  if (kl) { e.preventDefault(); kopyala(KAYNAKLAR.filter((k) => k.kategori === kl.dataset.katListe).map((k) => k.url).join("\n"), "Kategorinin adresleri kopyalandı"); }
});
$("#kaynak-liste").addEventListener("change", (e) => {
  const c = e.target.closest("[data-sec]"); if (!c) return;
  c.checked ? secili.add(c.dataset.sec) : secili.delete(c.dataset.sec);
  depo.yaz("secili", [...secili]); secimCubugu();
  $("#d-hepsi").checked = dizinFiltre().every((k) => secili.has(k.id));
});
$("#d-hepsi").addEventListener("change", (e) => {
  dizinFiltre().forEach((k) => e.target.checked ? secili.add(k.id) : secili.delete(k.id));
  depo.yaz("secili", [...secili]); dizinCiz();
});

function secimCubugu() {
  const n = [...secili].filter((id) => KAYNAK[id]).length;
  $("#secim-cubugu").hidden = !n || sekme.aktif() !== "dizin";
  $("#secim-sayi").textContent = `${n} kaynak seçili`;
  $("#birlesik-url").textContent = birlesikUrl();
}
function birlesikUrl() {
  const ids = [...secili].filter((id) => KAYNAK[id]);
  return beslemeAdresi({ k: ids.join(","), takip: $("#birlesik-kelime").value.trim() });
}
$("#birlesik-kelime").addEventListener("input", () => $("#birlesik-url").textContent = birlesikUrl());
$("#birlesik-kopyala").addEventListener("click", () => kopyala(birlesikUrl(), "Birleşik besleme adresi kopyalandı"));
$("#secim-temizle").addEventListener("click", () => { secili.clear(); depo.yaz("secili", []); dizinCiz(); });
$("#kopyala-liste").addEventListener("click", () => {
  const urller = [...secili].map((id) => KAYNAK[id]?.url).filter(Boolean);
  kopyala(urller.join("\n"), `${urller.length} adres kopyalandı`);
});
$("#indir-opml").addEventListener("click", () => {
  const ids = [...secili].filter((id) => KAYNAK[id]);
  if (ids.join(",").length < 6000) { location.href = "/api/opml?k=" + encodeURIComponent(ids.join(",")); return; }
  const govde = ids.map((id) => KAYNAK[id]).map((k) => `    <outline type="rss" text="${esc(k.ad)}" title="${esc(k.ad)}" xmlUrl="${esc(k.url)}"/>`).join("\n");
  const blob = new Blob([`<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0">\n  <head><title>Medya Takip</title></head>\n  <body>\n${govde}\n  </body>\n</opml>\n`], { type: "text/x-opml" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "medya-takip.opml"; a.click();
});

/* =====================================================================
   KAYDEDİLENLER
   ===================================================================== */
let etiketFiltre = "";
function kayitlariCiz() {
  const hepsi = Object.values(kayitlar).sort((a, b) => b.tarih - a.tarih);
  const etiketler = [...new Set(hepsi.flatMap((k) => k.etiketler || []))].sort((a, b) => a.localeCompare(b, "tr"));
  if (etiketFiltre && !etiketler.includes(etiketFiltre)) etiketFiltre = "";
  $("#etiket-cipler").innerHTML = etiketler.length ? `<button class="cip ${etiketFiltre ? "" : "acik"}" data-etiket-f="">Tümü</button>` +
    etiketler.map((e) => `<button class="cip ${etiketFiltre === e ? "acik" : ""}" data-etiket-f="${esc(e)}">#${esc(e)}</button>`).join("") : "";
  const q = $("#ara").value.trim().toLocaleLowerCase("tr");
  const liste = hepsi.filter((k) => (!etiketFiltre || (k.etiketler || []).includes(etiketFiltre)) &&
    (!q || (k.olay.baslik + " " + (k.not || "")).toLocaleLowerCase("tr").includes(q)));
  $("#kayitlar").innerHTML = liste.map((k, i) => kart(k.olay, i, null)).join("")
    || '<div class="bos">Kaydettiğin gelişmeler burada görünür. Akışta bir kartın üstündeki kaydet düğmesine bas.</div>';
}
$("#etiket-cipler").addEventListener("click", (e) => { const b = e.target.closest("[data-etiket-f]"); if (b) { etiketFiltre = b.dataset.etiketF; kayitlariCiz(); } });
$("#disa-aktar").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify({ surum: 1, takip: takipListesi, kayitlar }, null, 2)], { type: "application/json" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = `medya-takip-kayitlar-${new Date().toISOString().slice(0, 10)}.json`; a.click();
});
$("#ice-aktar").addEventListener("change", async (e) => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const d = JSON.parse(await f.text());
    if (!d || typeof d.kayitlar !== "object") throw new Error();
    Object.assign(kayitlar, d.kayitlar);
    (d.takip || []).forEach((t) => takipListesi.includes(t) || takipListesi.push(t));
    depo.yaz("takip", takipListesi); kayitDegisti(); takipCizimi(); kayitlariCiz();
    bildir(`${Object.keys(d.kayitlar).length} kayıt içe aktarıldı`);
  } catch { bildir("Dosya okunamadı. Medya Takip'ten dışa aktarılmış bir JSON seç."); }
  e.target.value = "";
});

/* =====================================================================
   YÖNLENDİRME VE ARAMA
   ===================================================================== */
function sekme() {
  const gecerli = sekme.aktif();
  $$(".bolum").forEach((b) => b.hidden = b.id !== gecerli);
  $$(".sekmeler a").forEach((a) => a.classList.toggle("aktif", a.dataset.sekme === gecerli));
  $("#ara").placeholder = { takip: "Haber, kişi, kurum ara", dizin: "Kaynak adı veya adres ara", kayit: "Kaydedilenlerde ara" }[gecerli];
  if (gecerli === "dizin") dizinCiz();
  if (gecerli === "kayit") kayitlariCiz();
  secimCubugu();
  window.scrollTo({ top: 0 });
}
sekme.aktif = () => { const a = location.hash.replace("#/", ""); return ["takip", "dizin", "kayit"].includes(a) ? a : "takip"; };
window.addEventListener("hashchange", sekme);
let araZaman;
$("#ara").addEventListener("input", () => {
  clearTimeout(araZaman);
  araZaman = setTimeout(() => {
    const s = sekme.aktif();
    if (s === "takip") akisYukle(); else if (s === "dizin") dizinCiz(); else kayitlariCiz();
  }, 320);
});

(async function basla() {
  simgeleriDoldur();
  takipCizimi(); kayitDegisti();
  try { await temelVeri(); } catch { $("#olaylar").innerHTML = '<div class="bos">Sunucuya ulaşılamadı.</div>'; return; }
  katFiltreCiz();
  sekme();
  akisYukle();
  setInterval(() => { if (!document.hidden) api("/api/kaynaklar").then((k) => { KAYNAKLAR = k; KAYNAK = Object.fromEntries(k.map((x) => [x.id, x])); }).catch(() => {}); }, 300000);
})();
