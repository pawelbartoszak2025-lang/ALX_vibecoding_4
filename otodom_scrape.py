# -*- coding: utf-8 -*-
"""Otodom: parsowanie ofert do SQLite (domyślnie) oraz generowanie strony do przeglądania.

Użycie:
  python otodom_scrape.py          # parsuje pobrane strony i zapisuje do otodom.db
  python otodom_scrape.py --html   # czyta otodom.db i generuje oferty.html
"""
import re, json, sqlite3, os, sys, html as html_mod

# Liczba pokoi w danych Otodom jest słowna — mapowanie na cyfry do wyświetlania.
ROOMS_MAP = {
    "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
    "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9", "TEN": "10",
    "MORE": "10+",
}

# Każde miasto może mieć kilka plików (kolejne strony wyników),
# bo Otodom renderuje w HTML tylko część ofert.
PAGES = {
    "Gdańsk":   ["otodom_pages/gdansk.html"],
    "Kraków":   ["otodom_pages/krakow.html"],
    "Warszawa": ["otodom_pages/warszawa.html"],
    "Poznań":   ["otodom_pages/poznan.html"],
}
PER_CITY = 10
BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "otodom.db")


def money(node):
    """totalPrice / pricePerSquareMeter -> (value, currency)"""
    if not node or not isinstance(node, dict):
        return None, None
    return node.get("value"), node.get("currency")


def parse_file(path):
    html = open(os.path.join(BASE, path), encoding="utf-8").read()
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    data = json.loads(m.group(1))
    return data["props"]["pageProps"]["data"]["searchAds"]["items"]


def public_id(it):
    """Publiczny ID oferty z ze slug-a (np. ...-ID4umX2). Łączy duplikaty promowane."""
    slug = it.get("slug") or ""
    m = re.search(r"-(ID[0-9A-Za-z]+)$", slug)
    return m.group(1) if m else str(it.get("id"))


def extract(it):
    addr = (it.get("location") or {}).get("address") or {}
    city = (addr.get("city") or {}).get("name")
    street = (addr.get("street") or {}).get("name")
    province = (addr.get("province") or {}).get("name")
    location = ", ".join(x for x in [street, city, province] if x)
    price, cur = money(it.get("totalPrice"))
    ppsm, _ = money(it.get("pricePerSquareMeter"))
    return {
        "otodom_id": it.get("id"),
        "title": it.get("title"),
        "price": price,
        "currency": cur,
        "price_per_m2": ppsm,
        "area_m2": it.get("areaInSquareMeters"),
        "rooms": it.get("roomsNumber"),
        "floor": it.get("floorNumber"),
        "is_private_owner": int(bool(it.get("isPrivateOwner"))),
        "location": location,
        "url": "https://www.otodom.pl/pl/oferta/" + (it.get("slug") or ""),
    }


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("DROP TABLE IF EXISTS oferty")  # świeża, czysta tabela
    cur.execute("""
        CREATE TABLE IF NOT EXISTS oferty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            miasto_wyszukiwania TEXT,
            otodom_id INTEGER,
            title TEXT,
            price REAL,
            currency TEXT,
            price_per_m2 REAL,
            area_m2 REAL,
            rooms TEXT,
            floor TEXT,
            is_private_owner INTEGER,
            location TEXT,
            url TEXT,
            UNIQUE(otodom_id)
        )
    """)
    total = 0
    for miasto, paths in PAGES.items():
        # zbierz oferty z wszystkich stron danego miasta
        items = []
        for p in paths:
            items.extend(parse_file(p))
        # PER_CITY pierwszych RÓŻNYCH ofert (pomijamy pozycje bez id/tytułu
        # oraz powtórzone oferty promowane — dedup po publicznym ID ze slug-a)
        picked, seen = [], set()
        for it in items:
            if not (it.get("id") and it.get("title")):
                continue
            pid = public_id(it)
            if pid in seen:
                continue
            seen.add(pid)
            picked.append(it)
            if len(picked) == PER_CITY:
                break
        for it in picked:
            r = extract(it)
            cur.execute("""
                INSERT OR REPLACE INTO oferty
                (miasto_wyszukiwania, otodom_id, title, price, currency,
                 price_per_m2, area_m2, rooms, floor, is_private_owner, location, url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (miasto, r["otodom_id"], r["title"], r["price"], r["currency"],
                  r["price_per_m2"], r["area_m2"], str(r["rooms"]), str(r["floor"]),
                  r["is_private_owner"], r["location"], r["url"]))
            total += 1
    con.commit()

    # Podgląd
    print(f"Zapisano {total} ofert do {DB}\n")
    for row in cur.execute("""
        SELECT miasto_wyszukiwania, title, price, currency, area_m2, rooms,
               price_per_m2, location, url FROM oferty ORDER BY id
    """):
        miasto, title, price, curc, area, rooms, ppm, loc, url = row
        print(f"[{miasto}] {title}")
        pr = f"{int(price):,}".replace(",", " ") if price else "—"
        ppm_s = f"{int(ppm):,}".replace(",", " ") if ppm else "—"
        print(f"   {pr} {curc or ''} | {area} m² | {rooms} pok. | {ppm_s} {curc or ''}/m²")
        print(f"   {loc}")
        print(f"   {url}\n")
    con.close()


HTML_OUT = os.path.join(BASE, "oferty.html")


def build_html():
    """Czyta otodom.db i zapisuje samodzielny plik oferty.html z wbudowanymi danymi."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT miasto_wyszukiwania, title, price, currency, price_per_m2,
               area_m2, rooms, floor, is_private_owner, location, url
        FROM oferty ORDER BY miasto_wyszukiwania, price IS NULL, price
    """).fetchall()
    con.close()

    oferty = []
    for r in rows:
        oferty.append({
            "miasto": r["miasto_wyszukiwania"],
            "title": r["title"],
            "price": r["price"],
            "currency": r["currency"] or "PLN",
            "ppm": r["price_per_m2"],
            "area": r["area_m2"],
            "rooms": ROOMS_MAP.get(r["rooms"], None),
            "private": bool(r["is_private_owner"]),
            "location": r["location"],
            "url": r["url"],
        })

    miasta = sorted({o["miasto"] for o in oferty})
    data_json = json.dumps(oferty, ensure_ascii=False)
    miasta_json = json.dumps(miasta, ensure_ascii=False)

    page = HTML_TEMPLATE.replace("/*__DATA__*/", data_json) \
                        .replace("/*__CITIES__*/", miasta_json) \
                        .replace("__COUNT__", str(len(oferty)))
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"Zapisano {len(oferty)} ofert do {HTML_OUT}")
    print("Otwórz plik dwuklikiem w przeglądarce.")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oferty mieszkań — Otodom</title>
<style>
  :root { --bg:#0f1115; --card:#1a1d24; --card2:#21252e; --txt:#e7e9ee;
          --muted:#9aa3b2; --accent:#3b82f6; --line:#2b2f3a; --good:#22c55e; --inv:#f59e0b; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background:var(--bg); color:var(--txt); }
  header { padding:28px 20px 14px; max-width:1100px; margin:0 auto; }
  h1 { margin:0 0 4px; font-size:22px; letter-spacing:.3px; }
  .sub { color:var(--muted); font-size:14px; }
  .filters { position:sticky; top:0; z-index:5; background:rgba(15,17,21,.92);
             backdrop-filter:blur(6px); border-bottom:1px solid var(--line);
             padding:12px 20px; }
  .filters .wrap { max-width:1100px; margin:0 auto; display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
  .chip { border:1px solid var(--line); background:var(--card); color:var(--txt);
          padding:7px 14px; border-radius:999px; cursor:pointer; font-size:14px; transition:.15s; }
  .chip:hover { border-color:var(--accent); }
  .chip.active { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
  .chip .n { opacity:.7; font-size:12px; margin-left:5px; }
  main { max-width:1100px; margin:0 auto; padding:18px 20px 60px;
         display:grid; grid-template-columns:repeat(auto-fill, minmax(320px,1fr)); gap:14px; }
  .card { display:flex; flex-direction:column; background:var(--card); border:1px solid var(--line);
          border-radius:14px; padding:16px; text-decoration:none; color:inherit; transition:.15s; }
  .card:hover { transform:translateY(-2px); border-color:var(--accent); background:var(--card2); }
  .badges { display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap; }
  .badge { font-size:11px; padding:3px 8px; border-radius:6px; background:#2b2f3a; color:var(--muted); }
  .badge.city { background:#1e3a8a33; color:#93c5fd; }
  .badge.priv { background:#14532d33; color:#86efac; }
  .badge.inv { background:#78350f55; color:#fcd34d; }
  .title { font-size:15px; font-weight:600; line-height:1.35; margin:0 0 10px; }
  .price { font-size:20px; font-weight:700; }
  .price .cur { font-size:13px; color:var(--muted); font-weight:500; }
  .ppm { font-size:13px; color:var(--muted); margin-top:2px; }
  .meta { display:flex; gap:14px; margin-top:12px; padding-top:12px; border-top:1px solid var(--line);
          font-size:13px; color:var(--muted); flex-wrap:wrap; }
  .meta b { color:var(--txt); font-weight:600; }
  .loc { font-size:12px; color:var(--muted); margin-top:10px; }
  .empty { grid-column:1/-1; text-align:center; color:var(--muted); padding:40px; }
  footer { text-align:center; color:var(--muted); font-size:12px; padding:0 20px 30px; }
  a.card .go { margin-top:auto; }
</style>
</head>
<body>
<header>
  <h1>Oferty mieszkań — Otodom</h1>
  <div class="sub"><span id="shown">__COUNT__</span> z __COUNT__ ofert · dane lokalne z <code>otodom.db</code></div>
</header>
<div class="filters"><div class="wrap" id="chips"></div></div>
<main id="grid"></main>
<footer>Wygenerowano lokalnie · kliknij ofertę, aby otworzyć ogłoszenie na Otodom</footer>

<script>
const OFERTY = /*__DATA__*/;
const CITIES = /*__CITIES__*/;
let activeCity = "Wszystkie";

const fmt = n => n == null ? null : new Intl.NumberFormat("pl-PL").format(Math.round(n));

function countFor(city){
  return city === "Wszystkie" ? OFERTY.length : OFERTY.filter(o => o.miasto === city).length;
}

function renderChips(){
  const chips = document.getElementById("chips");
  const all = ["Wszystkie", ...CITIES];
  chips.innerHTML = all.map(c =>
    `<button class="chip ${c===activeCity?"active":""}" data-city="${c}">${c}<span class="n">${countFor(c)}</span></button>`
  ).join("");
  chips.querySelectorAll(".chip").forEach(b =>
    b.onclick = () => { activeCity = b.dataset.city; renderChips(); renderGrid(); });
}

function card(o){
  const inv = o.price == null;
  const price = inv
    ? `<div class="price" style="color:var(--inv)">Inwestycja</div>`
    : `<div class="price">${fmt(o.price)} <span class="cur">${o.currency}</span></div>` +
      (o.ppm ? `<div class="ppm">${fmt(o.ppm)} ${o.currency}/m²</div>` : "");
  const meta = [
    o.area  ? `<span><b>${(""+o.area).replace(".",",")}</b> m²</span>` : "",
    o.rooms ? `<span><b>${o.rooms}</b> pok.</span>` : "",
  ].filter(Boolean).join("");
  const badges = [
    `<span class="badge city">${o.miasto}</span>`,
    inv ? `<span class="badge inv">inwestycja</span>` : "",
    o.private ? `<span class="badge priv">prywatne</span>` : `<span class="badge">agencja</span>`,
  ].filter(Boolean).join("");
  return `<a class="card" href="${o.url}" target="_blank" rel="noopener">
      <div class="badges">${badges}</div>
      <div class="title">${o.title}</div>
      ${price}
      ${meta ? `<div class="meta">${meta}</div>` : ""}
      <div class="loc">📍 ${o.location || "—"}</div>
    </a>`;
}

function renderGrid(){
  const list = activeCity === "Wszystkie" ? OFERTY : OFERTY.filter(o => o.miasto === activeCity);
  const grid = document.getElementById("grid");
  grid.innerHTML = list.length
    ? list.map(card).join("")
    : `<div class="empty">Brak ofert dla: ${activeCity}</div>`;
  document.getElementById("shown").textContent = list.length;
}

renderChips();
renderGrid();
</script>
</body>
</html>"""


if __name__ == "__main__":
    if "--html" in sys.argv:
        build_html()
    else:
        main()
