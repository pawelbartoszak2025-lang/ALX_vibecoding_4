# Harmonogram + Logowanie + Kryteria — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-user login, a configurable background scheduler (10–15 min auto-scrape), and saved search criteria that filter the offer list after login.

**Architecture:** Keep the stdlib `http.server` app. Offers become DB-backed (page fetches `/api/offers` instead of baked-in data). New small modules: `store.py` (settings + offers in SQLite), `auth.py` (password hashing + in-memory sessions), `scheduler.py` (background thread). `server.py` becomes the router and starts the scheduler thread. Criteria matching is a pure JS function (`criteria.js`) tested with Node.

**Tech Stack:** Python 3.14 stdlib (`http.server`, `sqlite3`, `hashlib`, `secrets`, `threading`), `unittest` for Python tests, Node for the JS matcher test, vanilla JS/HTML/CSS. No new pip installs.

---

## File Structure

- Create `store.py` — settings get/save (JSON in `app_settings`), offers read/save (SQLite).
- Create `auth.py` — password hashing, account create/verify, in-memory sessions.
- Create `scheduler.py` — interval clamp, `should_run`, `run_cycle`, `scheduler_loop`.
- Create `criteria.js` — pure `matchesCriteria(offer, criteria)` used by the page and tests.
- Create `login.html` — login / first-run register page.
- Modify `server.py` — cookies, auth guard, new endpoints, serve static, start scheduler.
- Modify `oferty.html` — fetch offers from API, criteria + scheduler panels, logout, drop baked-in data.
- Create `tests/test_store.py`, `tests/test_auth.py`, `tests/test_scheduler.py`, `tests/criteria.test.mjs`.
- Create `.gitignore` and init git (protect `discord_config.json`).

Shared interface names (use exactly):
- `store.get_settings(key) -> dict`, `store.save_settings(key, data)`, `store.read_offers() -> list[dict]`, `store.save_offers(offers) -> int`, `store.DEFAULTS`.
- `auth.hash_password(pw) -> (hash_hex, salt_hex)`, `auth.verify_password(pw, hash_hex, salt_hex) -> bool`, `auth.account_exists() -> bool`, `auth.create_account(username, pw)`, `auth.verify_login(username, pw) -> bool`, `auth.get_username() -> str|None`, `auth.create_session(username) -> token`, `auth.session_user(token) -> str|None`, `auth.delete_session(token)`.
- `scheduler.clamp_interval(n) -> int`, `scheduler.should_run(cfg, now_epoch) -> bool`, `scheduler.run_cycle()`, `scheduler.start(server_module)`.
- JS: `matchesCriteria(offer, criteria) -> bool` (CommonJS + browser global).

---

## Task 1: Initialize git and protect secrets

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Initialize repo**

Run: `git init`
Expected: "Initialized empty Git repository".

- [ ] **Step 2: Create `.gitignore`**

```gitignore
# sekrety i dane lokalne
discord_config.json
otodom.db
otodom_pages/
__pycache__/
*.pyc
```

- [ ] **Step 3: First commit (without the token file)**

```bash
git add .gitignore server.py discord_send.py discord_bot.py otodom_scrape.py oferty.html Oferty.vbs "Zatrzymaj serwer.vbs" docs
git commit -m "chore: init repo, ignore secrets and local data"
```
Expected: a commit is created; `git status` shows `discord_config.json` untracked/ignored.

---

## Task 2: `store.py` — settings and offers in SQLite

**Files:**
- Create: `store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_store.py
import os, tempfile, unittest
import store

class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store.DB = os.path.join(self.tmp, "t.db")  # przekieruj bazę na tymczasową

    def test_settings_defaults_when_absent(self):
        crit = store.get_settings("criteria")
        self.assertEqual(crit["owner_type"], "any")
        self.assertIsNone(crit["price_max"])

    def test_settings_roundtrip(self):
        store.save_settings("scheduler", {"enabled": True, "interval_min": 15,
            "cities": ["Poznań"], "discord_autosend": False,
            "last_run": None, "last_error": None})
        got = store.get_settings("scheduler")
        self.assertTrue(got["enabled"])
        self.assertEqual(got["cities"], ["Poznań"])

    def test_save_and_read_offers(self):
        n = store.save_offers([{
            "otodom_id": 1, "miasto": "Poznań", "title": "Test",
            "price": 500000.0, "currency": "PLN", "ppm": 10000.0,
            "area": 50.0, "rooms": "2", "private": False,
            "location": "Ul. X, Poznań, wielkopolskie",
            "url": "https://x/oferta/test-ID1",
        }])
        self.assertEqual(n, 1)
        offers = store.read_offers()
        self.assertEqual(len(offers), 1)
        o = offers[0]
        self.assertEqual(o["wojewodztwo"], "wielkopolskie")
        self.assertEqual(o["rooms"], "2")
        self.assertEqual(o["miasto"], "Poznań")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_store -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'store'`).

- [ ] **Step 3: Implement `store.py`**

```python
# -*- coding: utf-8 -*-
"""Warstwa danych: ustawienia (JSON) oraz oferty w SQLite (otodom.db)."""
import os, json, sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "otodom.db")

ROOMS_MAP = {"ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
             "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9", "TEN": "10",
             "MORE": "10+"}

DEFAULTS = {
    "scheduler": {"enabled": False, "interval_min": 15, "cities": ["Poznań"],
                  "discord_autosend": False, "last_run": None, "last_error": None},
    "criteria": {"price_max": None, "ppm_max": None, "rooms_min": None,
                 "area_min": None, "area_max": None, "cities": [], "owner_type": "any"},
}


def _con():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("""CREATE TABLE IF NOT EXISTS oferty (
        id INTEGER PRIMARY KEY AUTOINCREMENT, miasto_wyszukiwania TEXT,
        otodom_id INTEGER, title TEXT, price REAL, currency TEXT,
        price_per_m2 REAL, area_m2 REAL, rooms TEXT, floor TEXT,
        is_private_owner INTEGER, location TEXT, url TEXT, UNIQUE(otodom_id))""")
    return con


def get_settings(key):
    con = _con()
    row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    con.close()
    data = dict(DEFAULTS.get(key, {}))
    if row:
        data.update(json.loads(row[0]))
    return data


def save_settings(key, data):
    merged = dict(DEFAULTS.get(key, {}))
    merged.update(data or {})
    con = _con()
    con.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
                (key, json.dumps(merged, ensure_ascii=False)))
    con.commit()
    con.close()
    return merged


def save_offers(offers):
    con = _con()
    n = 0
    for o in offers:
        con.execute("""INSERT OR REPLACE INTO oferty
            (miasto_wyszukiwania, otodom_id, title, price, currency,
             price_per_m2, area_m2, rooms, floor, is_private_owner, location, url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (o.get("miasto"), o.get("otodom_id"), o.get("title"), o.get("price"),
             o.get("currency") or "PLN", o.get("ppm"), o.get("area"),
             str(o.get("rooms")) if o.get("rooms") is not None else None, None,
             int(bool(o.get("private"))), o.get("location"), o.get("url")))
        n += 1
    con.commit()
    con.close()
    return n


def read_offers():
    con = _con()
    con.row_factory = sqlite3.Row
    rows = con.execute("""SELECT miasto_wyszukiwania, title, price, currency,
        price_per_m2, area_m2, rooms, is_private_owner, location, url
        FROM oferty ORDER BY miasto_wyszukiwania, price IS NULL, price""").fetchall()
    con.close()
    out = []
    for r in rows:
        loc = r["location"] or ""
        woj = loc.split(",")[-1].strip() if "," in loc else ""
        raw_rooms = r["rooms"]
        rooms = ROOMS_MAP.get(raw_rooms, raw_rooms) if raw_rooms else None
        out.append({
            "miasto": r["miasto_wyszukiwania"], "wojewodztwo": woj,
            "title": r["title"], "price": r["price"], "currency": r["currency"] or "PLN",
            "ppm": r["price_per_m2"], "area": r["area_m2"], "rooms": rooms,
            "private": bool(r["is_private_owner"]), "location": loc, "url": r["url"],
        })
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_store -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat: store module for settings and DB-backed offers"
```

---

## Task 3: `auth.py` — password hashing, account, sessions

**Files:**
- Create: `auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_auth.py
import os, tempfile, unittest
import auth

class AuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        auth.DB = os.path.join(self.tmp, "t.db")
        auth.SESSIONS.clear()

    def test_hash_verify(self):
        h, s = auth.hash_password("tajne123")
        self.assertTrue(auth.verify_password("tajne123", h, s))
        self.assertFalse(auth.verify_password("zle", h, s))

    def test_account_lifecycle(self):
        self.assertFalse(auth.account_exists())
        auth.create_account("pawel", "tajne123")
        self.assertTrue(auth.account_exists())
        self.assertEqual(auth.get_username(), "pawel")
        self.assertTrue(auth.verify_login("pawel", "tajne123"))
        self.assertFalse(auth.verify_login("pawel", "zle"))
        with self.assertRaises(Exception):
            auth.create_account("inny", "x")  # konto już istnieje

    def test_sessions(self):
        t = auth.create_session("pawel")
        self.assertEqual(auth.session_user(t), "pawel")
        auth.delete_session(t)
        self.assertIsNone(auth.session_user(t))
        self.assertIsNone(auth.session_user("nieistnieje"))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_auth -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'auth'`).

- [ ] **Step 3: Implement `auth.py`**

```python
# -*- coding: utf-8 -*-
"""Logowanie: hasło haszowane (pbkdf2) + sesje w pamięci. Jedno konto."""
import os, sqlite3, hashlib, secrets, time

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "otodom.db")
SESSIONS = {}  # token -> {"user": str, "created": float}


def _con():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
        pass_hash TEXT, salt TEXT, created_at TEXT)""")
    return con


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                            bytes.fromhex(salt), 200_000).hex()
    return h, salt


def verify_password(password, hash_hex, salt_hex):
    calc, _ = hash_password(password, salt_hex)
    return secrets.compare_digest(calc, hash_hex)


def account_exists():
    con = _con()
    row = con.execute("SELECT COUNT(*) FROM users").fetchone()
    con.close()
    return row[0] > 0


def get_username():
    con = _con()
    row = con.execute("SELECT username FROM users ORDER BY id LIMIT 1").fetchone()
    con.close()
    return row[0] if row else None


def create_account(username, password):
    if account_exists():
        raise RuntimeError("Konto już istnieje.")
    if not username or not password:
        raise RuntimeError("Login i hasło są wymagane.")
    h, s = hash_password(password)
    con = _con()
    con.execute("INSERT INTO users (username, pass_hash, salt, created_at) VALUES (?,?,?,?)",
                (username, h, s, time.strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    con.close()


def verify_login(username, password):
    con = _con()
    row = con.execute("SELECT pass_hash, salt FROM users WHERE username=?", (username,)).fetchone()
    con.close()
    if not row:
        return False
    return verify_password(password, row[0], row[1])


def create_session(username):
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = {"user": username, "created": time.time()}
    return token


def session_user(token):
    s = SESSIONS.get(token or "")
    return s["user"] if s else None


def delete_session(token):
    SESSIONS.pop(token or "", None)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_auth -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "feat: auth module (pbkdf2 password + in-memory sessions)"
```

---

## Task 4: `scheduler.py` — interval logic and cycle

**Files:**
- Create: `scheduler.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests (pure logic only)**

```python
# tests/test_scheduler.py
import unittest, scheduler

class SchedulerLogicTest(unittest.TestCase):
    def test_clamp_interval(self):
        self.assertEqual(scheduler.clamp_interval(5), 10)
        self.assertEqual(scheduler.clamp_interval(10), 10)
        self.assertEqual(scheduler.clamp_interval(15), 15)
        self.assertEqual(scheduler.clamp_interval(None), 10)

    def test_should_run_disabled(self):
        cfg = {"enabled": False, "interval_min": 10, "last_run": None}
        self.assertFalse(scheduler.should_run(cfg, 1000))

    def test_should_run_first_time(self):
        cfg = {"enabled": True, "interval_min": 10, "last_run": None}
        self.assertTrue(scheduler.should_run(cfg, 1000))

    def test_should_run_respects_interval(self):
        cfg = {"enabled": True, "interval_min": 10, "last_run": 1000}
        self.assertFalse(scheduler.should_run(cfg, 1000 + 9 * 60))   # za wcześnie
        self.assertTrue(scheduler.should_run(cfg, 1000 + 10 * 60))   # czas minął

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_scheduler -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'scheduler'`).

- [ ] **Step 3: Implement `scheduler.py`**

```python
# -*- coding: utf-8 -*-
"""Harmonogram cyklicznego pobierania (wątek w tle uruchamiany przez server.py)."""
import time, threading
import store

MIN_INTERVAL = 10  # minut — nie częściej

CITY_WOJ = {"Poznań": "wielkopolskie", "Kraków": "małopolskie",
            "Warszawa": "mazowieckie", "Gdańsk": "pomorskie"}


def clamp_interval(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return MIN_INTERVAL
    return max(MIN_INTERVAL, n)


def should_run(cfg, now_epoch):
    if not cfg.get("enabled"):
        return False
    last = cfg.get("last_run")
    if not last:
        return True
    return (now_epoch - float(last)) >= clamp_interval(cfg.get("interval_min")) * 60


def run_cycle(server_module):
    """Jeden przebieg: scrapuje miasta z konfiguracji, zapisuje do bazy,
    opcjonalnie wysyła na Discord. Aktualizuje last_run/last_error."""
    cfg = store.get_settings("scheduler")
    error = None
    try:
        for miasto in cfg.get("cities", []):
            woj = CITY_WOJ.get(miasto, "")
            _url, offers = server_module.scrape(woj, miasto)
            store.save_offers(offers)
            if cfg.get("discord_autosend"):
                import discord_send
                discord_send.send_city(miasto, offers)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print("[scheduler] błąd:", error)
    cfg["last_run"] = time.time()
    cfg["last_error"] = error
    store.save_settings("scheduler", cfg)


def scheduler_loop(server_module, stop_event):
    while not stop_event.is_set():
        try:
            cfg = store.get_settings("scheduler")
            if should_run(cfg, time.time()):
                print("[scheduler] uruchamiam cykl…")
                run_cycle(server_module)
        except Exception as e:
            print("[scheduler] pętla błąd:", e)
        stop_event.wait(30)  # sprawdzaj co 30 s


def start(server_module):
    stop_event = threading.Event()
    t = threading.Thread(target=scheduler_loop, args=(server_module, stop_event),
                         daemon=True, name="scheduler")
    t.start()
    return stop_event
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_scheduler -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: scheduler module (interval clamp, should_run, run_cycle)"
```

---

## Task 5: `criteria.js` — pure matcher + Node test

**Files:**
- Create: `criteria.js`
- Test: `tests/criteria.test.mjs`

- [ ] **Step 1: Write failing test**

```javascript
// tests/criteria.test.mjs
import assert from "node:assert";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { matchesCriteria } = require("../criteria.js");

const base = { price: 500000, ppm: 10000, area: 50, rooms: "2",
               miasto: "Poznań", private: false };

// brak kryteriów -> pasuje wszystko
assert.strictEqual(matchesCriteria(base, {}), true);
// cena maks.
assert.strictEqual(matchesCriteria(base, { price_max: 400000 }), false);
assert.strictEqual(matchesCriteria(base, { price_max: 600000 }), true);
// cena/m2 maks.
assert.strictEqual(matchesCriteria(base, { ppm_max: 9000 }), false);
// min pokoi (z obsługą "10+")
assert.strictEqual(matchesCriteria(base, { rooms_min: 3 }), false);
assert.strictEqual(matchesCriteria(base, { rooms_min: 2 }), true);
// powierzchnia
assert.strictEqual(matchesCriteria(base, { area_min: 60 }), false);
assert.strictEqual(matchesCriteria(base, { area_max: 40 }), false);
// miasto
assert.strictEqual(matchesCriteria(base, { cities: ["Kraków"] }), false);
assert.strictEqual(matchesCriteria(base, { cities: ["Poznań"] }), true);
// typ
assert.strictEqual(matchesCriteria(base, { owner_type: "private" }), false);
assert.strictEqual(matchesCriteria(base, { owner_type: "agency" }), true);
// inwestycja (brak ceny) odpada gdy ustawiono limit ceny
assert.strictEqual(matchesCriteria({ ...base, price: null }, { price_max: 600000 }), false);
console.log("criteria.test.mjs: OK");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node tests/criteria.test.mjs`
Expected: FAIL (cannot find module `../criteria.js`).

- [ ] **Step 3: Implement `criteria.js`**

```javascript
// Czysta funkcja dopasowania oferty do kryteriów. Używana w przeglądarce
// (przez <script src>) oraz w teście Node (przez require).
(function (root) {
  function roomsToInt(r) {
    if (r == null) return null;
    const n = parseInt(String(r), 10);
    return Number.isNaN(n) ? null : n;  // "10+" -> 10
  }

  function matchesCriteria(o, c) {
    c = c || {};
    const hasPriceLimit = c.price_max != null || c.ppm_max != null;
    if (hasPriceLimit && o.price == null) return false;        // inwestycja bez ceny
    if (c.price_max != null && !(o.price != null && o.price <= c.price_max)) return false;
    if (c.ppm_max != null && !(o.ppm != null && o.ppm <= c.ppm_max)) return false;
    if (c.rooms_min != null) {
      const r = roomsToInt(o.rooms);
      if (r == null || r < c.rooms_min) return false;
    }
    if (c.area_min != null && !(o.area != null && o.area >= c.area_min)) return false;
    if (c.area_max != null && !(o.area != null && o.area <= c.area_max)) return false;
    if (Array.isArray(c.cities) && c.cities.length && !c.cities.includes(o.miasto)) return false;
    if (c.owner_type === "private" && !o.private) return false;
    if (c.owner_type === "agency" && o.private) return false;
    return true;
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { matchesCriteria };
  else root.matchesCriteria = matchesCriteria;
})(typeof window !== "undefined" ? window : globalThis);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node tests/criteria.test.mjs`
Expected: prints `criteria.test.mjs: OK` and exits 0.

- [ ] **Step 5: Commit**

```bash
git add criteria.js tests/criteria.test.mjs
git commit -m "feat: pure criteria matcher with node test"
```

---

## Task 6: `server.py` — auth, sessions, new endpoints, DB-backed scrape

**Files:**
- Modify: `server.py` (imports near top; `Handler` methods; `__main__`)

- [ ] **Step 1: Add imports and helpers**

At the top of `server.py`, after the existing `import` lines, add:

```python
import auth, store, scheduler
from http.cookies import SimpleCookie

def _session_token(handler):
    raw = handler.headers.get("Cookie")
    if not raw:
        return None
    ck = SimpleCookie()
    ck.load(raw)
    return ck["session"].value if "session" in ck else None

def _current_user(handler):
    return auth.session_user(_session_token(handler))
```

- [ ] **Step 2: Add a JSON-body helper and a cookie-setting send**

Inside the `Handler` class, add these methods (next to `_send`):

```python
    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_with_cookie(self, code, body, token):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", f"session={token}; Path=/; HttpOnly; SameSite=Lax")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
```

- [ ] **Step 3: Rewrite `do_GET` to gate pages and add data endpoints**

Replace the body of `do_GET` so it handles auth. Use this exact structure (keep existing static file read style):

```python
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        user = _current_user(self)

        if path == "/login":
            self._serve_file("login.html", "text/html; charset=utf-8")
            return
        if path == "/criteria.js":
            self._serve_file("criteria.js", "application/javascript; charset=utf-8")
            return
        if path in ("/", "/oferty.html"):
            if not user:
                self.send_response(302)
                self.send_header("Location", "/login")
                self.end_headers()
                return
            self._serve_file("oferty.html", "text/html; charset=utf-8")
            return

        if path == "/api/me":
            self._send(200, json.dumps({"logged_in": bool(user),
                "account_exists": auth.account_exists(), "username": user}))
            return

        # poniżej: tylko dla zalogowanych
        if path.startswith("/api/"):
            if not user:
                self._send(401, json.dumps({"error": "Niezalogowany"}))
                return
            if path == "/api/offers":
                self._send(200, json.dumps(store.read_offers(), ensure_ascii=False))
                return
            if path == "/api/criteria":
                self._send(200, json.dumps(store.get_settings("criteria"), ensure_ascii=False))
                return
            if path == "/api/scheduler":
                self._send(200, json.dumps(store.get_settings("scheduler"), ensure_ascii=False))
                return
            if path == "/api/scrape":
                q = parse_qs(parsed.query)
                woj = (q.get("woj", [""])[0]).strip()
                miasto = (q.get("miasto", [""])[0]).strip()
                if not woj and not miasto:
                    self._send(400, json.dumps({"error": "Wybierz województwo lub miasto."}))
                    return
                try:
                    url, offers = scrape(woj, miasto)
                    store.save_offers(offers)
                    self._send(200, json.dumps(
                        {"offers": offers, "label": miasto or woj, "url": url}, ensure_ascii=False))
                except Exception as e:
                    self._send(502, json.dumps({"error": f"{type(e).__name__}: {e}"}))
                return

        self._send(404, json.dumps({"error": "not found"}))

    def _serve_file(self, name, ctype):
        try:
            with open(os.path.join(BASE, name), encoding="utf-8") as f:
                self._send(200, f.read(), ctype)
        except FileNotFoundError:
            self._send(404, f"{name} nie znaleziony", "text/plain; charset=utf-8")
```

Note: ensure `BASE` exists in `server.py` (it does). Remove the old inline `/` and `/api/scrape` handling that this replaces.

- [ ] **Step 4: Rewrite `do_POST` for auth + settings + discord**

Replace `do_POST` with:

```python
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            body = self._read_json()
        except Exception:
            self._send(400, json.dumps({"error": "Zły format żądania."}))
            return

        if path == "/api/register":
            if auth.account_exists():
                self._send(409, json.dumps({"error": "Konto już istnieje."}))
                return
            try:
                auth.create_account((body.get("username") or "").strip(), body.get("password") or "")
                token = auth.create_session(auth.get_username())
                self._send_with_cookie(200, json.dumps({"ok": True}), token)
            except Exception as e:
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False))
            return

        if path == "/api/login":
            u = (body.get("username") or "").strip()
            if auth.verify_login(u, body.get("password") or ""):
                token = auth.create_session(u)
                self._send_with_cookie(200, json.dumps({"ok": True}), token)
            else:
                self._send(401, json.dumps({"error": "Błędny login lub hasło."}))
            return

        if path == "/api/logout":
            auth.delete_session(_session_token(self))
            self._send(200, json.dumps({"ok": True}))
            return

        # poniżej: tylko dla zalogowanych
        if not _current_user(self):
            self._send(401, json.dumps({"error": "Niezalogowany"}))
            return

        if path == "/api/criteria":
            saved = store.save_settings("criteria", body)
            self._send(200, json.dumps(saved, ensure_ascii=False))
            return

        if path == "/api/scheduler":
            body["interval_min"] = scheduler.clamp_interval(body.get("interval_min"))
            saved = store.save_settings("scheduler", body)
            self._send(200, json.dumps(saved, ensure_ascii=False))
            return

        if path == "/api/discord":
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
                res = discord_send.send_city(miasto, offers)
                self._send(200, json.dumps(res, ensure_ascii=False))
            except Exception as e:
                self._send(502, json.dumps({"error": str(e)}, ensure_ascii=False))
            return

        self._send(404, json.dumps({"error": "not found"}))
```

- [ ] **Step 5: Start the scheduler thread in `__main__`**

In the `if __name__ == "__main__":` block, after `srv` is created and before `serve_forever()`, add:

```python
    scheduler.start(__import__("server"))
    print("Harmonogram: wątek uruchomiony.")
```

(Use `__import__("server")` so the scheduler receives the module object exposing `scrape`.)

- [ ] **Step 6: Verify Python still parses**

Run: `python -c "import ast; ast.parse(open('server.py',encoding='utf-8').read()); print('server.py OK')"`
Expected: `server.py OK`.

- [ ] **Step 7: Manual endpoint smoke test**

Run (PowerShell), starting the server then exercising auth:

```powershell
$env:PYTHONIOENCODING="utf-8"; Start-Process python "server.py"
Start-Sleep 3
$s = New-Object Microsoft.PowerShell.Commands.WebRequestSession
# brak konta -> /api/me
(Invoke-WebRequest "http://localhost:8000/api/me" -WebSession $s -UseBasicParsing).Content
# rejestracja
Invoke-WebRequest "http://localhost:8000/api/register" -Method POST -WebSession $s -Body '{"username":"pawel","password":"tajne123"}' -ContentType "application/json" -UseBasicParsing | Out-Null
# offers dostępne po zalogowaniu (sesja w $s)
(Invoke-WebRequest "http://localhost:8000/api/offers" -WebSession $s -UseBasicParsing).StatusCode
# bez sesji -> 401
try { Invoke-WebRequest "http://localhost:8000/api/offers" -UseBasicParsing } catch { "offers bez sesji: $($_.Exception.Response.StatusCode.value__)" }
```
Expected: `/api/me` shows `account_exists:false` initially; after register, `/api/offers` returns `200`; without session returns `401`. Then stop the test server (`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? { $_.CommandLine -like '*server.py*' } | % { Stop-Process -Id $_.ProcessId -Force }`).

- [ ] **Step 8: Commit**

```bash
git add server.py
git commit -m "feat: auth gate, sessions, offers/criteria/scheduler endpoints, DB-backed scrape"
```

---

## Task 7: `login.html` — login / first-run register

**Files:**
- Create: `login.html`

- [ ] **Step 1: Create `login.html`**

```html
<!DOCTYPE html>
<html lang="pl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Logowanie — Oferty</title>
<style>
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f1ede2;
       font-family:system-ui,sans-serif;color:#221d16}
  .card{background:#fff;border:1px solid #cabda3;border-radius:8px;padding:32px;width:320px}
  h1{font-size:22px;margin:0 0 4px}
  p{color:#7c7263;font-size:14px;margin:0 0 20px}
  label{display:block;font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:#7c7263;margin:14px 0 4px}
  input{width:100%;padding:10px;border:1px solid #cabda3;border-radius:4px;font-size:15px}
  button{width:100%;margin-top:20px;padding:11px;background:#b8462b;color:#fff;border:none;
         border-radius:4px;font-size:15px;font-weight:600;cursor:pointer}
  button:hover{background:#8c3219}
  .msg{margin-top:14px;font-size:13px;min-height:1em}
  .msg.err{color:#8c3219}
</style></head>
<body>
  <div class="card">
    <h1 id="title">Logowanie</h1>
    <p id="sub">Zaloguj się, aby zobaczyć oferty.</p>
    <label>Login</label><input id="u" autocomplete="username">
    <label>Hasło</label><input id="p" type="password" autocomplete="current-password">
    <button id="go">Zaloguj</button>
    <div class="msg" id="msg"></div>
  </div>
<script>
let registerMode = false;
async function init(){
  const me = await (await fetch("/api/me")).json();
  if (me.logged_in){ location.href = "/"; return; }
  registerMode = !me.account_exists;
  if (registerMode){
    document.getElementById("title").textContent = "Utwórz konto";
    document.getElementById("sub").textContent = "Pierwsze uruchomienie — ustaw login i hasło.";
    document.getElementById("go").textContent = "Utwórz konto";
  }
}
document.getElementById("go").addEventListener("click", async () => {
  const username = document.getElementById("u").value.trim();
  const password = document.getElementById("p").value;
  const url = registerMode ? "/api/register" : "/api/login";
  const res = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({username, password})});
  const data = await res.json();
  if (res.ok && data.ok){ location.href = "/"; }
  else { const m=document.getElementById("msg"); m.textContent = data.error || "Błąd."; m.className="msg err"; }
});
document.getElementById("p").addEventListener("keydown", e => { if(e.key==="Enter") document.getElementById("go").click(); });
init();
</script>
</body></html>
```

- [ ] **Step 2: Manual verification**

Run: start server, open `http://localhost:8000` in a browser.
Expected: redirect to `/login`; first time shows "Utwórz konto"; after creating account you land on the app; logging out and revisiting shows "Logowanie".

- [ ] **Step 3: Commit**

```bash
git add login.html
git commit -m "feat: login/register page"
```

---

## Task 8: `oferty.html` — DB-backed data, criteria + scheduler panels, logout

**Files:**
- Modify: `oferty.html`

- [ ] **Step 1: Include the matcher and remove baked-in data**

In `<head>`, before the closing `</style>`'s following content, add a script include just after `<body>` opening is not required; instead add in `<head>`:

```html
<script src="/criteria.js"></script>
```

Then in the main `<script>` at the bottom, **replace** the line that defines the data:

```javascript
const OFERTY = [ ... duża wklejona tablica ... ];
```

with an empty, mutable array (data now comes from the API):

```javascript
let OFERTY = [];
```

- [ ] **Step 2: Add logout + view toggle controls to the header**

In the `.filters .wrap` (next to the buttons), add a logout button and a "tylko pasujące" toggle:

```html
  <button id="btnAll" class="btn-scrape" type="button">Pokaż wszystkie</button>
  <button id="btnLogout" class="btn-discord" type="button" style="background:#5d6a38;border-color:#46532b">Wyloguj</button>
```

- [ ] **Step 3: Add criteria + scheduler panels markup**

Immediately after the `</nav>` (filters) element, add:

```html
<section id="panels" style="padding:14px var(--pad);display:grid;gap:18px;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--line)">
  <form id="formCriteria">
    <h3 style="margin:0 0 8px;font-family:'Fraunces',serif">Moje kryteria</h3>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
      <label>Cena maks. (PLN)<input name="price_max" type="number" min="0"></label>
      <label>Cena/m² maks.<input name="ppm_max" type="number" min="0"></label>
      <label>Min. pokoi<input name="rooms_min" type="number" min="0"></label>
      <label>Pow. min (m²)<input name="area_min" type="number" min="0"></label>
      <label>Pow. maks (m²)<input name="area_max" type="number" min="0"></label>
      <label>Typ
        <select name="owner_type"><option value="any">dowolny</option>
          <option value="private">prywatne</option><option value="agency">agencja</option></select>
      </label>
    </div>
    <div id="critCities" style="margin-top:8px;font-size:13px"></div>
    <button type="submit" class="btn-scrape" style="margin-top:10px">Zapisz kryteria</button>
  </form>
  <form id="formScheduler">
    <h3 style="margin:0 0 8px;font-family:'Fraunces',serif">Harmonogram</h3>
    <label><input name="enabled" type="checkbox"> Włącz automatyczne pobieranie</label>
    <label style="display:block;margin-top:8px">Co ile minut
      <select name="interval_min"><option>10</option><option>15</option><option>30</option><option>60</option></select>
    </label>
    <div id="schedCities" style="margin-top:8px;font-size:13px"></div>
    <label style="display:block;margin-top:8px"><input name="discord_autosend" type="checkbox"> Wysyłaj też na Discord</label>
    <button type="submit" class="btn-scrape" style="margin-top:10px">Zapisz harmonogram</button>
    <div id="schedStatus" style="margin-top:8px;font-size:12px;color:var(--ink-soft)"></div>
  </form>
</section>
```

- [ ] **Step 4: Replace the bottom init block with API-driven init + criteria filtering**

At the very bottom of the main `<script>`, **replace**:

```javascript
renderChips();
renderGrid();
```

with:

```javascript
const ALL_CITIES = ["Gdańsk", "Kraków", "Warszawa", "Poznań"];
let CRITERIA = {};
let onlyMatching = true;

// Filtr kryteriów nakładany na renderGrid: zawężamy OFERTY do pasujących.
const _renderGridBase = renderGrid;
renderGrid = function(){
  const source = onlyMatching ? OFERTY.filter(o => matchesCriteria(o, CRITERIA)) : OFERTY;
  const saved = OFERTY; OFERTY = source; _renderGridBase(); OFERTY = saved;
};

function fillCityChecks(elId, selected){
  document.getElementById(elId).innerHTML = "Miasta: " + ALL_CITIES.map(c =>
    `<label style="margin-right:10px"><input type="checkbox" value="${c}" ${selected.includes(c)?"checked":""}> ${c}</label>`).join("");
}

async function loadCriteria(){
  CRITERIA = await (await fetch("/api/criteria")).json();
  const f = document.getElementById("formCriteria");
  ["price_max","ppm_max","rooms_min","area_min","area_max"].forEach(k => f[k].value = CRITERIA[k] ?? "");
  f.owner_type.value = CRITERIA.owner_type || "any";
  fillCityChecks("critCities", CRITERIA.cities || []);
}

async function loadScheduler(){
  const s = await (await fetch("/api/scheduler")).json();
  const f = document.getElementById("formScheduler");
  f.enabled.checked = !!s.enabled;
  f.interval_min.value = String(s.interval_min || 15);
  f.discord_autosend.checked = !!s.discord_autosend;
  fillCityChecks("schedCities", s.cities || []);
  document.getElementById("schedStatus").textContent =
    "Ostatni cykl: " + (s.last_run ? new Date(s.last_run*1000).toLocaleString("pl-PL") : "—") +
    (s.last_error ? " · błąd: " + s.last_error : "");
}

function readCities(elId){
  return [...document.querySelectorAll(`#${elId} input:checked`)].map(i => i.value);
}
function numOrNull(v){ return v === "" ? null : Number(v); }

document.getElementById("formCriteria").addEventListener("submit", async e => {
  e.preventDefault(); const f = e.target;
  CRITERIA = { price_max:numOrNull(f.price_max.value), ppm_max:numOrNull(f.ppm_max.value),
    rooms_min:numOrNull(f.rooms_min.value), area_min:numOrNull(f.area_min.value),
    area_max:numOrNull(f.area_max.value), cities:readCities("critCities"), owner_type:f.owner_type.value };
  await fetch("/api/criteria", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(CRITERIA)});
  onlyMatching = true; renderChips(); renderGrid();
});

document.getElementById("formScheduler").addEventListener("submit", async e => {
  e.preventDefault(); const f = e.target;
  const cfg = { enabled:f.enabled.checked, interval_min:Number(f.interval_min.value),
    cities:readCities("schedCities"), discord_autosend:f.discord_autosend.checked };
  await fetch("/api/scheduler", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(cfg)});
  loadScheduler();
});

document.getElementById("btnAll").addEventListener("click", () => {
  onlyMatching = !onlyMatching;
  document.getElementById("btnAll").textContent = onlyMatching ? "Pokaż wszystkie" : "Tylko pasujące";
  renderGrid();
});

document.getElementById("btnLogout").addEventListener("click", async () => {
  await fetch("/api/logout", {method:"POST"}); location.href = "/login";
});

async function loadOffers(){
  OFERTY = await (await fetch("/api/offers")).json();
  renderChips(); renderGrid();
}

(async function init(){
  await loadCriteria();
  await loadScheduler();
  await loadOffers();
})();
```

- [ ] **Step 5: Make the existing "Pobierz" handler refresh from DB**

Find the scrape button success branch that calls `mergeOffers(data.offers)` and **replace** that call with a DB refresh so the DB stays the source of truth:

```javascript
    await loadOffers();
    setStatus(`Pobrano ${data.offers.length} najnowszych ofert: ${data.label}.`, "ok");
```

(Remove the now-unused `mergeOffers` function if nothing else uses it.)

- [ ] **Step 6: Validate JS syntax**

Run:
```powershell
$html=[System.IO.File]::ReadAllText((Join-Path (Get-Location) "oferty.html"))
$m=[regex]::Matches($html,'<script>(.*?)</script>',[System.Text.RegularExpressions.RegexOptions]::Singleline)
[System.IO.File]::WriteAllText((Join-Path (Get-Location) "_check.js"), $m[$m.Count-1].Groups[1].Value, (New-Object System.Text.UTF8Encoding $false))
node --check _check.js; if($?){ "JS OK" }; Remove-Item _check.js
```
Expected: `JS OK`.

- [ ] **Step 7: Manual end-to-end verification**

Run: start server (`Oferty.vbs` or `python server.py`), open `http://localhost:8000`, log in.
Expected: panels show; saving criteria (e.g. min pokoi=3) filters the list to matching only; "Pokaż wszystkie" toggles; saving scheduler with Poznań + enabled shows a "last cycle" timestamp within ~30–60 s and new offers appear after reloading; "Wyloguj" returns to login.

- [ ] **Step 8: Commit**

```bash
git add oferty.html
git commit -m "feat: DB-backed offers, criteria filter + scheduler config panels, logout"
```

---

## Task 9: Final integration check

- [ ] **Step 1: Run all Python tests**

Run: `python -m unittest discover -s tests -v`
Expected: all tests PASS.

- [ ] **Step 2: Run the JS matcher test**

Run: `node tests/criteria.test.mjs`
Expected: `criteria.test.mjs: OK`.

- [ ] **Step 3: Full manual pass**

Launch via `Oferty.vbs`. Confirm: login gate works; offers load from DB; criteria filter; scheduler runs a cycle and updates `last_run`; Discord button + `/poznan` slash command still work.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "test: full integration pass for scheduler/auth/criteria"
```

---

## Notes for the implementer

- `discord_config.json` must stay untracked (it holds the bot token). The `.gitignore` from Task 1 covers it.
- The scheduler thread shares `otodom.db`; each function opens/closes its own connection, so concurrent access from the HTTP handlers and the thread is safe for this small workload.
- `oferty.html` keeps its existing `card`, `renderChips`, and `renderGrid` functions; tasks only change data loading, add panels, and wrap `renderGrid` for filtering.
- Minimum scrape interval is enforced server-side (`scheduler.clamp_interval`), so the UI cannot set it below 10 minutes.
