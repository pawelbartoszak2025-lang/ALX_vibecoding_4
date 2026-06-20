# Migracja SQLite → Supabase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strona na Vercelu ma trwałe dane (oferty, ustawienia, dedup Discord) dzięki przechowywaniu ich w Supabase zamiast w ulotnym SQLite w `/tmp`.

**Architecture:** Jeden „przełącznik" — gdy ustawione są zmienne `SUPABASE_URL` i `SUPABASE_KEY`, warstwa danych mówi do Supabase przez HTTP API (PostgREST) za pomocą biblioteki standardowej Pythona (`urllib`); w przeciwnym razie używa SQLite jak dotąd. Nowy moduł `db.py` jest jedynym miejscem komunikacji z Supabase. Funkcje w `store.py` i `discord_send.py` zyskują rozgałęzienie `if db.enabled(): ... else: <SQLite>`.

**Tech Stack:** Python 3 (tylko biblioteka standardowa: `urllib`, `json`, `os`), Supabase (Postgres + PostgREST), SQLite (lokalnie), `unittest` do testów.

## Global Constraints

- **Brak nowych zależności** — `requirements.txt` pozostaje pusty; tylko biblioteka standardowa Pythona.
- Klucz Supabase (`service_role`) **wyłącznie** ze zmiennej środowiskowej; nigdy w kodzie ani po stronie przeglądarki.
- Gałąź SQLite w każdej funkcji pozostaje **nietknięta** (lokalnie i w testach działa bez zmian).
- `enabled()` zwraca `True` tylko gdy ustawione są **oba** `SUPABASE_URL` i `SUPABASE_KEY`; w innym wypadku `False` (bezpieczny fallback do SQLite).
- Testy uruchamiane: `python -m unittest discover -s tests -v` z katalogu projektu.
- Tabele Supabase: `oferty` (unique `otodom_id`), `app_settings` (`key` PK, `value` text-JSON), `discord_sent` (unique `miasto,url`). `users` NIE jest tworzona.
- Komunikaty i komentarze po polsku (jak w istniejącym kodzie); kodowanie UTF-8.

---

### Task 1: Moduł `db.py` — czyste helpery składania żądań (bez sieci)

Najpierw budujemy i testujemy część czysto obliczeniową: rozpoznanie trybu oraz
składanie URL, nagłówków i payloadu. Brak realnych wywołań HTTP w tym tasku.

**Files:**
- Create: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: zmienne środowiskowe `SUPABASE_URL`, `SUPABASE_KEY`.
- Produces:
  - `enabled() -> bool`
  - `_base_url() -> str` — `SUPABASE_URL` bez końcowego `/`, z dopiętym `/rest/v1`
  - `_headers(prefer: str | None = None) -> dict` — `apikey`, `Authorization: Bearer <key>`, `Content-Type: application/json`, opcjonalnie `Prefer`
  - `_build_query(params: dict) -> str` — zwraca zakodowany query-string (bez wiodącego `?`) z zachowaniem wartości typu `eq.<v>`; pusty dict → `""`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db.py
# -*- coding: utf-8 -*-
import os, unittest

class DbHelpersTest(unittest.TestCase):
    def setUp(self):
        self._old = {k: os.environ.get(k) for k in ("SUPABASE_URL", "SUPABASE_KEY")}
        for k in ("SUPABASE_URL", "SUPABASE_KEY"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _reload(self):
        import importlib, db
        return importlib.reload(db)

    def test_enabled_false_when_unset(self):
        db = self._reload()
        self.assertFalse(db.enabled())

    def test_enabled_false_when_only_one_set(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        db = self._reload()
        self.assertFalse(db.enabled())

    def test_enabled_true_when_both_set(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        self.assertTrue(db.enabled())

    def test_base_url_strips_trailing_slash(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co/"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        self.assertEqual(db._base_url(), "https://x.supabase.co/rest/v1")

    def test_headers_contain_auth_and_prefer(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        h = db._headers(prefer="resolution=merge-duplicates")
        self.assertEqual(h["apikey"], "secret")
        self.assertEqual(h["Authorization"], "Bearer secret")
        self.assertEqual(h["Content-Type"], "application/json")
        self.assertEqual(h["Prefer"], "resolution=merge-duplicates")

    def test_headers_no_prefer_key_when_none(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        db = self._reload()
        self.assertNotIn("Prefer", db._headers())

    def test_build_query_encodes_and_keeps_operators(self):
        db = self._reload()
        q = db._build_query({"select": "url", "miasto": "eq.Poznań"})
        self.assertIn("select=url", q)
        self.assertIn("miasto=eq.Pozna", q)  # ń zakodowane procentowo
        self.assertNotIn(" ", q)

    def test_build_query_empty(self):
        db = self._reload()
        self.assertEqual(db._build_query({}), "")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_db -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`.

- [ ] **Step 3: Write minimal implementation**

```python
# db.py
# -*- coding: utf-8 -*-
"""Warstwa Supabase (PostgREST) przez bibliotekę standardową — bez zależności.

Włącza się tylko gdy ustawione są zmienne SUPABASE_URL i SUPABASE_KEY
(na Vercelu). Lokalnie pozostają puste, więc warstwa danych używa SQLite.
"""
import os, json, urllib.parse, urllib.request, urllib.error


def _url():
    return (os.environ.get("SUPABASE_URL") or "").strip()


def _key():
    return (os.environ.get("SUPABASE_KEY") or "").strip()


def enabled():
    return bool(_url() and _key())


def _base_url():
    return _url().rstrip("/") + "/rest/v1"


def _headers(prefer=None):
    h = {
        "apikey": _key(),
        "Authorization": "Bearer " + _key(),
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _build_query(params):
    if not params:
        return ""
    # quote_via=quote_plus koduje spacje jako '+'; wartości typu 'eq.x' zachowane.
    return urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_db -v`
Expected: PASS (7 testów).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat(db): helpery Supabase REST (enabled/base_url/headers/query)"
```

---

### Task 2: `db.py` — operacje `select` i `upsert` (z testem przez podstawienie HTTP)

Dokładamy warstwę wykonującą żądania. Sieć podmieniamy w teście, podstawiając
`db._do(...)`, więc nie ma realnych połączeń.

**Files:**
- Modify: `db.py`
- Test: `tests/test_db.py` (dopisanie klasy testów)

**Interfaces:**
- Consumes: `_base_url()`, `_headers()`, `_build_query()` z Tasku 1.
- Produces:
  - `_do(method, url, headers, body=None) -> (status:int, text:str)` — cienka warstwa nad `urllib` (jedyne miejsce realnego I/O; podmieniane w testach).
  - `_request(method, path, *, params=None, body=None, prefer=None) -> list|dict` — składa URL/nagłówki, woła `_do`, parsuje JSON, błędy ≥400 → `RuntimeError("Supabase <code>: <text>")`.
  - `select(table, *, columns="*", order=None, filters=None) -> list[dict]`
  - `upsert(table, rows, *, on_conflict, ignore_duplicates=False) -> None` — POST z `Prefer: resolution=merge-duplicates|ignore-duplicates` i parametrem `on_conflict`.

- [ ] **Step 1: Write the failing tests**

```python
# dopisz na końcu tests/test_db.py (przed blokiem __main__)
class DbRequestTest(unittest.TestCase):
    def setUp(self):
        os.environ["SUPABASE_URL"] = "https://x.supabase.co"
        os.environ["SUPABASE_KEY"] = "secret"
        import importlib, db
        self.db = importlib.reload(db)
        self.calls = []
        def fake_do(method, url, headers, body=None):
            self.calls.append({"method": method, "url": url,
                               "headers": headers, "body": body})
            return 200, "[]"
        self.db._do = fake_do

    def tearDown(self):
        for k in ("SUPABASE_URL", "SUPABASE_KEY"):
            os.environ.pop(k, None)

    def test_select_builds_get_with_params(self):
        self.db.select("discord_sent", columns="url",
                       filters={"miasto": "eq.Poznań"})
        c = self.calls[0]
        self.assertEqual(c["method"], "GET")
        self.assertTrue(c["url"].startswith(
            "https://x.supabase.co/rest/v1/discord_sent?"))
        self.assertIn("select=url", c["url"])
        self.assertIn("miasto=eq.Pozna", c["url"])

    def test_select_includes_order(self):
        self.db.select("oferty", order="price.asc.nullslast")
        self.assertIn("order=price.asc.nullslast", self.calls[0]["url"])

    def test_upsert_sets_prefer_and_on_conflict(self):
        self.db.upsert("oferty", [{"otodom_id": 1}], on_conflict="otodom_id")
        c = self.calls[0]
        self.assertEqual(c["method"], "POST")
        self.assertIn("on_conflict=otodom_id", c["url"])
        self.assertEqual(c["headers"]["Prefer"], "resolution=merge-duplicates")
        self.assertEqual(json.loads(c["body"].decode("utf-8")), [{"otodom_id": 1}])

    def test_upsert_ignore_duplicates(self):
        self.db.upsert("discord_sent", [{"miasto": "a", "url": "u"}],
                       on_conflict="miasto,url", ignore_duplicates=True)
        self.assertEqual(self.calls[0]["headers"]["Prefer"],
                         "resolution=ignore-duplicates")

    def test_upsert_empty_rows_no_call(self):
        self.db.upsert("oferty", [], on_conflict="otodom_id")
        self.assertEqual(self.calls, [])

    def test_request_raises_on_http_error(self):
        self.db._do = lambda *a, **k: (409, "conflict detail")
        with self.assertRaises(RuntimeError) as ctx:
            self.db.select("oferty")
        self.assertIn("409", str(ctx.exception))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_db -v`
Expected: FAIL — `AttributeError: module 'db' has no attribute 'select'` (i pokrewne).

- [ ] **Step 3: Write minimal implementation**

```python
# dopisz na końcu db.py

def _do(method, url, headers, body=None):
    """Jedyne miejsce realnego I/O — podmieniane w testach."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _request(method, path, *, params=None, body=None, prefer=None):
    url = _base_url() + "/" + path
    q = _build_query(params or {})
    if q:
        url += "?" + q
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    status, text = _do(method, url, _headers(prefer), data)
    if status >= 400:
        raise RuntimeError(f"Supabase {status}: {text}")
    return json.loads(text) if text else []


def select(table, *, columns="*", order=None, filters=None):
    params = {"select": columns}
    if order:
        params["order"] = order
    if filters:
        params.update(filters)
    return _request("GET", table, params=params)


def upsert(table, rows, *, on_conflict, ignore_duplicates=False):
    if not rows:
        return
    resolution = "ignore-duplicates" if ignore_duplicates else "merge-duplicates"
    _request("POST", table, params={"on_conflict": on_conflict},
             body=rows, prefer="resolution=" + resolution)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_db -v`
Expected: PASS (wszystkie testy `db`).

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat(db): select/upsert/_request przez PostgREST"
```

---

### Task 3: Schemat bazy `supabase_schema.sql`

Plik SQL do jednorazowego wklejenia w SQL Editor w Supabase. Tabele 1:1 z SQLite.

**Files:**
- Create: `supabase_schema.sql`

**Interfaces:**
- Produces: tabele `oferty`, `app_settings`, `discord_sent` z ograniczeniami
  unikalności wymaganymi przez `upsert` (`on_conflict`): `oferty.otodom_id`,
  `app_settings.key` (PK), `discord_sent (miasto, url)`.

- [ ] **Step 1: Utwórz plik schematu**

```sql
-- supabase_schema.sql
-- Wklej całość w Supabase: SQL Editor -> New query -> Run. Uruchom raz.
-- Tabele odpowiadają tym z lokalnego SQLite (otodom.db).

create table if not exists oferty (
    id                  bigint generated always as identity primary key,
    miasto_wyszukiwania text,
    otodom_id           bigint unique,
    title               text,
    price               numeric,
    currency            text,
    price_per_m2        numeric,
    area_m2             numeric,
    rooms               text,
    floor               text,
    is_private_owner    boolean,
    location            text,
    url                 text
);

create table if not exists app_settings (
    key   text primary key,
    value text                  -- JSON przechowywany jako tekst (jak w SQLite)
);

create table if not exists discord_sent (
    miasto  text,
    url     text,
    sent_at timestamptz default now(),
    unique (miasto, url)
);
```

- [ ] **Step 2: Commit**

```bash
git add supabase_schema.sql
git commit -m "feat(supabase): schemat tabel (oferty, app_settings, discord_sent)"
```

---

### Task 4: `store.py` — `get_settings` / `save_settings` przez Supabase

**Files:**
- Modify: `store.py` (import `db`; rozgałęzienie w `get_settings`, `save_settings`)
- Test: `tests/test_store.py` (dopisanie testów z podstawionym `db`)

**Interfaces:**
- Consumes: `db.enabled()`, `db.select(...)`, `db.upsert(...)` z Tasków 1–2.
- Produces: zachowane sygnatury `get_settings(key) -> dict`, `save_settings(key, data) -> dict` (scalone z `DEFAULTS`, identyczny wynik w obu trybach).

- [ ] **Step 1: Write the failing tests**

```python
# dopisz do tests/test_store.py nową klasę (zachowaj istniejące testy SQLite)
import store as _store_mod

class StoreSupabaseSettingsTest(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.upserts = []
        store_mod = _store_mod
        self._orig = store_mod.db
        class FakeDb:
            @staticmethod
            def enabled():
                return True
            @staticmethod
            def select(table, columns="*", order=None, filters=None):
                return list(self.rows)
            @staticmethod
            def upsert(table, rows, on_conflict, ignore_duplicates=False):
                self.upserts.append({"table": table, "rows": rows,
                                     "on_conflict": on_conflict})
        store_mod.db = FakeDb

    def tearDown(self):
        _store_mod.db = self._orig

    def test_get_settings_merges_defaults(self):
        import json
        self.rows = [{"value": json.dumps({"interval_min": 30})}]
        cfg = _store_mod.get_settings("scheduler")
        self.assertEqual(cfg["interval_min"], 30)
        self.assertIn("cities", cfg)  # z DEFAULTS

    def test_get_settings_empty_returns_defaults(self):
        self.rows = []
        cfg = _store_mod.get_settings("criteria")
        self.assertEqual(cfg, _store_mod.DEFAULTS["criteria"])

    def test_save_settings_upserts_with_key_conflict(self):
        import json
        self._save = _store_mod.save_settings("criteria", {"price_max": 500000})
        self.assertEqual(len(self.upserts), 1)
        up = self.upserts[0]
        self.assertEqual(up["table"], "app_settings")
        self.assertEqual(up["on_conflict"], "key")
        row = up["rows"][0]
        self.assertEqual(row["key"], "criteria")
        self.assertEqual(json.loads(row["value"])["price_max"], 500000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_store -v`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'db'`.

- [ ] **Step 3: Write minimal implementation**

W `store.py` dodaj import na górze (obok istniejących):

```python
import os, json, sqlite3
import db
```

Zamień `get_settings` i `save_settings` na wersje z rozgałęzieniem:

```python
def get_settings(key):
    data = dict(DEFAULTS.get(key, {}))
    if db.enabled():
        rows = db.select("app_settings", columns="value",
                         filters={"key": "eq." + key})
        if rows:
            data.update(json.loads(rows[0]["value"]))
        return data
    con = _con()
    row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    con.close()
    if row:
        data.update(json.loads(row[0]))
    return data


def save_settings(key, data):
    merged = dict(DEFAULTS.get(key, {}))
    merged.update(data or {})
    if db.enabled():
        db.upsert("app_settings",
                  [{"key": key, "value": json.dumps(merged, ensure_ascii=False)}],
                  on_conflict="key")
        return merged
    con = _con()
    con.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
                (key, json.dumps(merged, ensure_ascii=False)))
    con.commit()
    con.close()
    return merged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_store -v`
Expected: PASS (testy SQLite oraz nowe Supabase).

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat(store): ustawienia przez Supabase (get/save_settings)"
```

---

### Task 5: `store.py` — `save_offers` / `read_offers` przez Supabase

**Files:**
- Modify: `store.py` (`save_offers`, `read_offers`)
- Test: `tests/test_store.py` (dopisanie testów; reużyj `FakeDb` ze wzorca z Tasku 4)

**Interfaces:**
- Consumes: `db.enabled()`, `db.select(...)`, `db.upsert(...)`.
- Produces: zachowane `save_offers(offers) -> int`, `read_offers() -> list[dict]`.
  W trybie Supabase `read_offers` używa `order="miasto_wyszukiwania.asc,price.asc.nullslast"`;
  `is_private_owner` zapisywane jako `bool`.

- [ ] **Step 1: Write the failing tests**

```python
# dopisz do tests/test_store.py
class StoreSupabaseOffersTest(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.upserts = []
        self._orig = _store_mod.db
        outer = self
        class FakeDb:
            @staticmethod
            def enabled():
                return True
            @staticmethod
            def select(table, columns="*", order=None, filters=None):
                outer.last_order = order
                return list(outer.rows)
            @staticmethod
            def upsert(table, rows, on_conflict, ignore_duplicates=False):
                outer.upserts.append({"table": table, "rows": rows,
                                      "on_conflict": on_conflict})
        _store_mod.db = FakeDb

    def tearDown(self):
        _store_mod.db = self._orig

    def test_save_offers_upserts_on_otodom_id(self):
        n = _store_mod.save_offers([{
            "miasto": "Poznań", "otodom_id": 7, "title": "M",
            "price": 100, "currency": "PLN", "ppm": 5, "area": 20,
            "rooms": 2, "private": True, "location": "X, wielkopolskie",
            "url": "http://u"}])
        self.assertEqual(n, 1)
        up = self.upserts[0]
        self.assertEqual(up["table"], "oferty")
        self.assertEqual(up["on_conflict"], "otodom_id")
        row = up["rows"][0]
        self.assertEqual(row["otodom_id"], 7)
        self.assertEqual(row["is_private_owner"], True)
        self.assertEqual(row["rooms"], "2")

    def test_read_offers_uses_order_and_maps_fields(self):
        self.rows = [{
            "miasto_wyszukiwania": "Poznań", "title": "M", "price": 100,
            "currency": "PLN", "price_per_m2": 5, "area_m2": 20,
            "rooms": "THREE", "is_private_owner": True,
            "location": "Ul. X, Poznań, wielkopolskie", "url": "http://u"}]
        out = _store_mod.read_offers()
        self.assertEqual(self.last_order,
                         "miasto_wyszukiwania.asc,price.asc.nullslast")
        self.assertEqual(out[0]["miasto"], "Poznań")
        self.assertEqual(out[0]["wojewodztwo"], "wielkopolskie")
        self.assertEqual(out[0]["rooms"], "3")  # ROOMS_MAP THREE -> 3
        self.assertIs(out[0]["private"], True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_store -v`
Expected: FAIL — Supabase branch jeszcze nie istnieje w `save_offers`/`read_offers` (upsert pusty / brak `order`).

- [ ] **Step 3: Write minimal implementation**

Zamień `save_offers` i `read_offers`. Wydziel wspólne mapowanie wiersza do dict
oferty, by gałęzie SQLite i Supabase nie dublowały logiki:

```python
def _row_to_offer(r):
    """Mapuje wiersz (SQLite Row lub dict z Supabase) na słownik oferty."""
    loc = r["location"] or ""
    woj = loc.split(",")[-1].strip() if "," in loc else ""
    raw_rooms = r["rooms"]
    rooms = ROOMS_MAP.get(raw_rooms, raw_rooms) if raw_rooms else None
    return {
        "miasto": r["miasto_wyszukiwania"], "wojewodztwo": woj,
        "title": r["title"], "price": r["price"], "currency": r["currency"] or "PLN",
        "ppm": r["price_per_m2"], "area": r["area_m2"], "rooms": rooms,
        "private": bool(r["is_private_owner"]), "location": loc, "url": r["url"],
    }


def save_offers(offers):
    if db.enabled():
        rows = [{
            "miasto_wyszukiwania": o.get("miasto"), "otodom_id": o.get("otodom_id"),
            "title": o.get("title"), "price": o.get("price"),
            "currency": o.get("currency") or "PLN", "price_per_m2": o.get("ppm"),
            "area_m2": o.get("area"),
            "rooms": str(o.get("rooms")) if o.get("rooms") is not None else None,
            "floor": None, "is_private_owner": bool(o.get("private")),
            "location": o.get("location"), "url": o.get("url"),
        } for o in offers]
        db.upsert("oferty", rows, on_conflict="otodom_id")
        return len(rows)
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
    if db.enabled():
        rows = db.select("oferty",
            columns="miasto_wyszukiwania,title,price,currency,price_per_m2,"
                    "area_m2,rooms,is_private_owner,location,url",
            order="miasto_wyszukiwania.asc,price.asc.nullslast")
        return [_row_to_offer(r) for r in rows]
    con = _con()
    con.row_factory = sqlite3.Row
    rows = con.execute("""SELECT miasto_wyszukiwania, title, price, currency,
        price_per_m2, area_m2, rooms, is_private_owner, location, url
        FROM oferty ORDER BY miasto_wyszukiwania, price IS NULL, price""").fetchall()
    con.close()
    return [_row_to_offer(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_store -v`
Expected: PASS (SQLite + Supabase).

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat(store): oferty przez Supabase (save/read_offers, wspolne mapowanie)"
```

---

### Task 6: `discord_send.py` — `filter_new` / `mark_sent` przez Supabase

**Files:**
- Modify: `discord_send.py` (import `db`; rozgałęzienie w `filter_new`, `mark_sent`)
- Test: `tests/test_discord_send.py` (nowy plik)

**Interfaces:**
- Consumes: `db.enabled()`, `db.select(...)`, `db.upsert(...)`.
- Produces: zachowane `filter_new(miasto, offers) -> list`, `mark_sent(miasto, offers) -> None`.
  W trybie Supabase dedup po `discord_sent` z `on_conflict="miasto,url"`, `ignore_duplicates=True`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discord_send.py
# -*- coding: utf-8 -*-
import unittest
import discord_send as ds

class DiscordSupabaseTest(unittest.TestCase):
    def setUp(self):
        self.sent_urls = []
        self.upserts = []
        self._orig = ds.db
        outer = self
        class FakeDb:
            @staticmethod
            def enabled():
                return True
            @staticmethod
            def select(table, columns="*", order=None, filters=None):
                return [{"url": u} for u in outer.sent_urls]
            @staticmethod
            def upsert(table, rows, on_conflict, ignore_duplicates=False):
                outer.upserts.append({"table": table, "rows": rows,
                                      "on_conflict": on_conflict,
                                      "ignore": ignore_duplicates})
        ds.db = FakeDb

    def tearDown(self):
        ds.db = self._orig

    def test_filter_new_drops_already_sent_and_dupes(self):
        self.sent_urls = ["http://a"]
        offers = [{"url": "http://a"}, {"url": "http://b"}, {"url": "http://b"}]
        new = ds.filter_new("Poznań", offers)
        self.assertEqual([o["url"] for o in new], ["http://b"])

    def test_mark_sent_upserts_ignore_duplicates(self):
        ds.mark_sent("Poznań", [{"url": "http://b"}])
        up = self.upserts[0]
        self.assertEqual(up["table"], "discord_sent")
        self.assertEqual(up["on_conflict"], "miasto,url")
        self.assertTrue(up["ignore"])
        self.assertEqual(up["rows"][0]["miasto"], "Poznań")
        self.assertEqual(up["rows"][0]["url"], "http://b")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_discord_send -v`
Expected: FAIL — `AttributeError: module 'discord_send' has no attribute 'db'`.

- [ ] **Step 3: Write minimal implementation**

W `discord_send.py` dodaj import obok istniejących:

```python
import os, re, json, time, sqlite3, unicodedata
import urllib.request, urllib.error
import db
```

Zamień `filter_new` i `mark_sent`:

```python
def filter_new(miasto, offers):
    if db.enabled():
        rows = db.select("discord_sent", columns="url",
                         filters={"miasto": "eq." + miasto})
        sent = {r["url"] for r in rows}
    else:
        con = sqlite3.connect(DB)
        _ensure_table(con)
        sent = {r[0] for r in con.execute(
            "SELECT url FROM discord_sent WHERE miasto=?", (miasto,))}
        con.close()
    seen, new = set(), []
    for o in offers:
        u = o.get("url")
        if u and u not in sent and u not in seen:
            seen.add(u)
            new.append(o)
    return new


def mark_sent(miasto, offers):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    if db.enabled():
        rows = [{"miasto": miasto, "url": o.get("url"), "sent_at": ts}
                for o in offers if o.get("url")]
        db.upsert("discord_sent", rows, on_conflict="miasto,url",
                  ignore_duplicates=True)
        return
    con = sqlite3.connect(DB)
    _ensure_table(con)
    for o in offers:
        con.execute("INSERT OR IGNORE INTO discord_sent (miasto, url, sent_at) VALUES (?,?,?)",
                    (miasto, o.get("url"), ts))
    con.commit()
    con.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_discord_send -v`
Expected: PASS (2 testy).

- [ ] **Step 5: Commit**

```bash
git add discord_send.py tests/test_discord_send.py
git commit -m "feat(discord): dedup wysylek przez Supabase (filter_new/mark_sent)"
```

---

### Task 7: Pełny zestaw testów + instrukcja konfiguracji na Vercelu

Weryfikacja całości oraz dopisanie instrukcji ustawienia zmiennych i schematu.

**Files:**
- Modify: `instrukcja_vercel.html`
- Modify: `DO_ZROBIENIA.md`

**Interfaces:**
- Consumes: wszystko z poprzednich tasków.
- Produces: dokumentacja kroków konfiguracji Supabase (zmienne `SUPABASE_URL`,
  `SUPABASE_KEY`, wklejenie `supabase_schema.sql`).

- [ ] **Step 1: Uruchom wszystkie testy (lokalnie = tryb SQLite)**

Run: `python -m unittest discover -s tests -v`
Expected: PASS — istniejące testy (store/auth/scheduler) + nowe (db/store-supabase/discord).

Run: `node tests/criteria.test.mjs`
Expected: brak błędu (test kryteriów jak dotąd).

- [ ] **Step 2: Dopisz sekcję konfiguracji Supabase do `instrukcja_vercel.html`**

Odczytaj `instrukcja_vercel.html`, znajdź sekcję ze zmiennymi środowiskowymi
i dodaj (dopasuj styl/HTML do istniejącego dokumentu) treść zawierającą:

```
Trwałe dane (Supabase)
1. W panelu Supabase: SQL Editor -> New query -> wklej zawartość pliku
   supabase_schema.sql -> Run (raz).
2. Project Settings -> API: skopiuj "Project URL" oraz klucz "service_role".
3. Na Vercelu: Project Settings -> Environment Variables dodaj:
   - SUPABASE_URL = <Project URL>
   - SUPABASE_KEY = <service_role key>
4. Redeploy. Od teraz oferty, kryteria, harmonogram i pamiec Discord sa trwale.
Uwaga: klucz service_role to sekret - tylko w zmiennych srodowiskowych.
```

- [ ] **Step 3: Zaktualizuj `DO_ZROBIENIA.md`**

Dodaj w sekcji stanu adnotację, że dane w chmurze idą do Supabase (gdy ustawione
`SUPABASE_URL`/`SUPABASE_KEY`), lokalnie nadal SQLite; automatyczny harmonogram w
chmurze pozostaje do zrobienia (Vercel Cron).

- [ ] **Step 4: Commit**

```bash
git add instrukcja_vercel.html DO_ZROBIENIA.md
git commit -m "docs: instrukcja konfiguracji Supabase na Vercelu"
```

---

## Notatki wdrożeniowe

- Kolejność tasków jest istotna: `db.py` (1–2) przed konsumentami (4–6). Task 3
  (schemat) niezależny, ale wymagany do realnego działania w chmurze.
- Po wdrożeniu: weryfikacja ręczna w chmurze wg kryteriów akceptacji ze specyfikacji
  (pobierz oferty → odśwież stronę → oferty zostają; zmień kryteria → zostają).
