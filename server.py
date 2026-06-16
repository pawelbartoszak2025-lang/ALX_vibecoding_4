# -*- coding: utf-8 -*-
"""Lokalny serwer dla oferty.html — scraping ofert Otodom na żądanie z przeglądarki.

Użycie:
  python server.py            # start serwera na http://localhost:8000
Następnie otwórz http://localhost:8000 w przeglądarce, wybierz województwo
i miasto z list rozwijanych i kliknij "Pobierz 10 najnowszych ofert".
"""
import re, json, sqlite3, os, unicodedata, urllib.request, ssl, threading, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "otodom.db")
HTML = os.path.join(BASE, "oferty.html")
PORT = 8000
PER_CITY = 10

ROOMS_MAP = {"ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
             "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9", "TEN": "10", "MORE": "10+"}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def slug(s):
    """Polska nazwa -> slug Otodom: 'Gdańsk' -> 'gdansk', 'małopolskie' -> 'malopolskie'."""
    s = (s or "").strip().lower().replace("ł", "l")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def build_url(woj, miasto):
    """Buduje URL wyszukiwania Otodom (10 najnowszych: by=LATEST)."""
    base = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie"
    w = slug(woj)
    c = slug(miasto)
    if c:               # wyszukiwanie po mieście
        path = f"{base}/{w}/{c}/{c}/{c}"
    else:               # wyszukiwanie na poziomie województwa
        path = f"{base}/{w}"
    return path + "?limit=36&ownerTypeSingleSelect=ALL&by=LATEST&direction=DESC"


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9",
    })
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def parse_items(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    return data["props"]["pageProps"]["data"]["searchAds"]["items"]


def public_id(it):
    slug_ = it.get("slug") or ""
    m = re.search(r"-(ID[0-9A-Za-z]+)$", slug_)
    return m.group(1) if m else str(it.get("id"))


def money(node):
    if not node or not isinstance(node, dict):
        return None, None
    return node.get("value"), node.get("currency")


def to_offer(it, search_woj, search_city):
    addr = (it.get("location") or {}).get("address") or {}
    city = (addr.get("city") or {}).get("name")
    street = (addr.get("street") or {}).get("name")
    province = (addr.get("province") or {}).get("name")
    location = ", ".join(x for x in [street, city, province] if x)
    price, cur = money(it.get("totalPrice"))
    ppsm, _ = money(it.get("pricePerSquareMeter"))
    return {
        "otodom_id": it.get("id"),
        # Grupujemy pod wybrane w formularzu miasto/województwo (jeśli podane),
        # żeby pasowało do list rozwijanych; inaczej bierzemy z adresu oferty.
        "miasto": search_city or city,
        "wojewodztwo": search_woj or province,
        "title": it.get("title"),
        "price": price,
        "currency": cur or "PLN",
        "ppm": ppsm,
        "area": it.get("areaInSquareMeters"),
        "rooms": ROOMS_MAP.get(it.get("roomsNumber")),
        "private": bool(it.get("isPrivateOwner")),
        "location": location,
        "url": "https://www.otodom.pl/pl/oferta/" + (it.get("slug") or ""),
    }


def scrape(woj, miasto):
    url = build_url(woj, miasto)
    html = fetch(url)
    items = parse_items(html)
    picked, seen = [], set()
    for it in items:
        if not (it.get("id") and it.get("title")):
            continue
        pid = public_id(it)
        if pid in seen:
            continue
        seen.add(pid)
        picked.append(to_offer(it, woj, miasto))
        if len(picked) == PER_CITY:
            break
    return url, picked


def save_to_db(offers):
    """Zapisuje pobrane oferty do otodom.db (ta sama tabela co otodom_scrape.py)."""
    try:
        con = sqlite3.connect(DB)
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS oferty (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                miasto_wyszukiwania TEXT, otodom_id INTEGER, title TEXT,
                price REAL, currency TEXT, price_per_m2 REAL, area_m2 REAL,
                rooms TEXT, floor TEXT, is_private_owner INTEGER,
                location TEXT, url TEXT, UNIQUE(otodom_id))
        """)
        for o in offers:
            cur.execute("""
                INSERT OR REPLACE INTO oferty
                (miasto_wyszukiwania, otodom_id, title, price, currency,
                 price_per_m2, area_m2, rooms, floor, is_private_owner, location, url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (o["miasto"], o["otodom_id"], o["title"], o["price"], o["currency"],
                  o["ppm"], o["area"], o["rooms"], None, int(o["private"]),
                  o["location"], o["url"]))
        con.commit()
        con.close()
    except Exception as e:
        print("Ostrzeżenie: nie zapisano do DB:", e)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/oferty.html"):
            try:
                with open(HTML, encoding="utf-8") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, "oferty.html nie znaleziony", "text/plain; charset=utf-8")
            return

        if parsed.path == "/api/scrape":
            q = parse_qs(parsed.query)
            woj = (q.get("woj", [""])[0]).strip()
            miasto = (q.get("miasto", [""])[0]).strip()
            if not woj and not miasto:
                self._send(400, json.dumps({"error": "Wybierz województwo lub miasto."}))
                return
            try:
                print(f"[scrape] woj={woj!r} miasto={miasto!r}")
                url, offers = scrape(woj, miasto)
                save_to_db(offers)
                label = miasto or woj
                print(f"[scrape] {url} -> {len(offers)} ofert")
                self._send(200, json.dumps(
                    {"offers": offers, "label": label, "url": url}, ensure_ascii=False))
            except Exception as e:
                print("[scrape] błąd:", e)
                self._send(502, json.dumps({"error": f"{type(e).__name__}: {e}"}))
            return

        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/discord":
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            except Exception:
                self._send(400, json.dumps({"error": "Zły format żądania."}))
                return
            miasto = (body.get("miasto") or "").strip()
            offers = body.get("oferty") or []
            if not miasto:
                self._send(400, json.dumps({"error": "Wybierz miasto, aby wysłać na Discord."}))
                return
            if not offers:
                self._send(400, json.dumps({"error": "Brak ofert — najpierw pobierz oferty."}))
                return
            try:
                import discord_send
                print(f"[discord] miasto={miasto!r} ofert={len(offers)}")
                res = discord_send.send_city(miasto, offers)
                print(f"[discord] kanał #{res['channel']} (nowy={res['created']}) "
                      f"wysłano={res['sent']} pominięto={res['skipped']}")
                self._send(200, json.dumps(res, ensure_ascii=False))
            except Exception as e:
                print("[discord] błąd:", e)
                self._send(502, json.dumps({"error": str(e)}, ensure_ascii=False))
            return

        self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *a):
        pass  # ciszej — własne logi w do_GET


if __name__ == "__main__":
    url = f"http://localhost:{PORT}"
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        # Port zajęty = serwer już działa. Otwórz tylko stronę i zakończ.
        webbrowser.open(url)
        raise SystemExit(0)
    print(f"Serwer działa: {url}")
    print("Strona otworzy się w przeglądarce. Ctrl+C aby zatrzymać.")
    # Otwórz przeglądarkę chwilę po starcie serwera.
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nZatrzymano.")
