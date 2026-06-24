# Import kursów walut NBP do Supabase — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jednorazowy skrypt `nbp_import.py`, który pobiera z `api.nbp.pl` kursy wszystkich walut (tabele A + B) za ostatnie 18 miesięcy i zapisuje je do nowej tabeli `kursy_walut` w Supabase.

**Architecture:** Czyste, testowalne funkcje pomocnicze (zakres dat, podział na kawałki ≤367 dni, przetworzenie odpowiedzi NBP) + pojedyncza funkcja `_get` izolująca I/O sieciowe (podmieniana w testach, wzorem `db._do`). Zapis do Supabase przez istniejący moduł `db.py` (`db.upsert`). Brak nowych zależności.

**Tech Stack:** Python (tylko biblioteka standardowa: `urllib`, `json`, `datetime`, `calendar`), `unittest`, istniejący `db.py` (PostgREST/Supabase).

## Global Constraints

- Tylko biblioteka standardowa Pythona — żadnych nowych pakietów w `requirements.txt`.
- Zapis do Supabase wyłącznie przez `db.py` (`db.upsert`, `db.enabled`).
- Komunikaty dla użytkownika po polsku, prostym językiem.
- I/O sieciowe musi być izolowane w jednej funkcji podmienialnej w testach; testy nie łączą się z internetem.
- Endpoint NBP: `https://api.nbp.pl/api/exchangerates/tables/{A|B}/{start}/{end}/?format=json`, daty w formacie `YYYY-MM-DD`, maks. 367 dni na jedno zapytanie.
- Tabela docelowa: `kursy_walut`, kolumny `kod` (text), `waluta` (text), `data` (date), `kurs` (numeric), z unikalnością pary `(kod, data)`; upsert `on_conflict="kod,data"`.

---

### Task 1: Tabela `kursy_walut` w schemacie Supabase

**Files:**
- Modify: `supabase_schema.sql` (dopisz na końcu, przed/obok bloków `enable row level security`)

**Interfaces:**
- Consumes: nic
- Produces: tabela `kursy_walut` z unikalnym ograniczeniem `(kod, data)` — wymagana przez `db.upsert(... on_conflict="kod,data")` w Task 5.

- [ ] **Step 1: Dopisz definicję tabeli do `supabase_schema.sql`**

Dodaj po definicji `discord_sent` (przed sekcją `alter table ... enable row level security`):

```sql
create table if not exists kursy_walut (
    kod    text,
    waluta text,
    data   date,
    kurs   numeric,
    unique (kod, data)
);
```

Oraz dopisz do sekcji RLS kolejną linię:

```sql
alter table kursy_walut enable row level security;
```

- [ ] **Step 2: Sprawdź spójność pliku**

Run: `python -c "print(open('supabase_schema.sql', encoding='utf-8').read())"`
Expected: wypisuje całość; widać blok `create table if not exists kursy_walut` z `unique (kod, data)` oraz `alter table kursy_walut enable row level security`.

- [ ] **Step 3: Commit**

```bash
git add supabase_schema.sql
git commit -m "feat(nbp): tabela kursy_walut w schemacie Supabase"
```

---

### Task 2: Funkcje dat i podziału na kawałki

**Files:**
- Create: `nbp_import.py`
- Test: `tests/test_nbp_import.py`

**Interfaces:**
- Consumes: nic
- Produces:
  - `months_back(d: date, n: int) -> date` — cofa datę o `n` miesięcy, przycinając dzień do długości miesiąca docelowego.
  - `chunk_ranges(start: date, end: date, max_days: int = 367) -> list[tuple[date, date]]` — dzieli zakres `[start, end]` (włącznie) na ciągłe kawałki, każdy obejmujący najwyżej `max_days` dni.
  - `batches(seq: list, size: int) -> Iterator[list]` — dzieli listę na partie o rozmiarze `size`.

- [ ] **Step 1: Napisz testy (najpierw padają)**

Utwórz `tests/test_nbp_import.py`:

```python
# tests/test_nbp_import.py
# -*- coding: utf-8 -*-
import unittest
from datetime import date, timedelta
import nbp_import as nbp


class DateHelpersTest(unittest.TestCase):
    def test_months_back_simple(self):
        self.assertEqual(nbp.months_back(date(2026, 6, 24), 18), date(2024, 12, 24))

    def test_months_back_clamps_day(self):
        # 31 sierpnia minus 6 miesięcy -> luty nie ma 31 dni -> 28
        self.assertEqual(nbp.months_back(date(2026, 8, 31), 6), date(2026, 2, 28))

    def test_chunk_ranges_splits_18_months(self):
        start, end = date(2024, 12, 24), date(2026, 6, 24)
        chunks = nbp.chunk_ranges(start, end, max_days=367)
        # każdy kawałek <= 367 dni (włącznie)
        for s, e in chunks:
            self.assertLessEqual((e - s).days + 1, 367)
        # ciągłość: następny zaczyna się dzień po końcu poprzedniego
        for (s1, e1), (s2, e2) in zip(chunks, chunks[1:]):
            self.assertEqual(s2, e1 + timedelta(days=1))
        # pokrycie całego zakresu
        self.assertEqual(chunks[0][0], start)
        self.assertEqual(chunks[-1][1], end)

    def test_chunk_ranges_single_when_small(self):
        start, end = date(2026, 1, 1), date(2026, 1, 31)
        self.assertEqual(nbp.chunk_ranges(start, end), [(start, end)])

    def test_batches_divides(self):
        self.assertEqual(list(nbp.batches([1, 2, 3, 4, 5], 2)),
                         [[1, 2], [3, 4], [5]])

    def test_batches_empty(self):
        self.assertEqual(list(nbp.batches([], 2)), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Uruchom testy — mają paść (brak modułu/funkcji)**

Run: `python -m unittest tests.test_nbp_import -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'nbp_import'`.

- [ ] **Step 3: Utwórz `nbp_import.py` z funkcjami pomocniczymi**

```python
# -*- coding: utf-8 -*-
"""Jednorazowy import kursów walut NBP (tabele A i B) do Supabase.

Pobiera średnie kursy wszystkich dostępnych walut za ostatnie 18 miesięcy
z api.nbp.pl i zapisuje do tabeli `kursy_walut`. Uruchamiany lokalnie:

    python nbp_import.py

Wymaga ustawionych SUPABASE_URL i SUPABASE_KEY (te same co aplikacja).
"""
import json, calendar, urllib.request, urllib.error
from datetime import date, timedelta

import db

NBP_BASE = "https://api.nbp.pl/api/exchangerates/tables"
MAX_DAYS = 367          # limit NBP na jedno zapytanie o zakres
MONTHS = 18             # ile miesięcy wstecz
BATCH = 500             # ile wierszy na jedną wysyłkę do Supabase


def months_back(d, n):
    """Cofa datę o n miesięcy, przycinając dzień do długości miesiąca docelowego."""
    m = d.month - 1 - n
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def chunk_ranges(start, end, max_days=MAX_DAYS):
    """Dzieli [start, end] (włącznie) na ciągłe kawałki <= max_days dni."""
    chunks, cur = [], start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def batches(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m unittest tests.test_nbp_import -v`
Expected: PASS (6 testów).

- [ ] **Step 5: Commit**

```bash
git add nbp_import.py tests/test_nbp_import.py
git commit -m "feat(nbp): funkcje dat i podzialu na kawalki"
```

---

### Task 3: Przetworzenie odpowiedzi NBP na wiersze

**Files:**
- Modify: `nbp_import.py`
- Test: `tests/test_nbp_import.py`

**Interfaces:**
- Consumes: nic
- Produces: `parse_tables(tables: list[dict]) -> list[dict]` — zamienia listę dni z NBP (każdy z `effectiveDate` i `rates`) na listę wierszy `{"kod", "waluta", "data", "kurs"}`.

- [ ] **Step 1: Dopisz test (najpierw pada)**

Dodaj do `tests/test_nbp_import.py` nową klasę:

```python
class ParseTablesTest(unittest.TestCase):
    SAMPLE = [
        {
            "table": "A",
            "no": "120/A/NBP/2026",
            "effectiveDate": "2026-06-23",
            "rates": [
                {"currency": "dolar amerykański", "code": "USD", "mid": 4.0150},
                {"currency": "euro", "code": "EUR", "mid": 4.2500},
            ],
        },
        {
            "table": "A",
            "no": "121/A/NBP/2026",
            "effectiveDate": "2026-06-24",
            "rates": [
                {"currency": "dolar amerykański", "code": "USD", "mid": 4.0200},
            ],
        },
    ]

    def test_parse_tables_flattens_rows(self):
        rows = nbp.parse_tables(self.SAMPLE)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], {"kod": "USD", "waluta": "dolar amerykański",
                                   "data": "2026-06-23", "kurs": 4.0150})
        self.assertEqual(rows[2], {"kod": "USD", "waluta": "dolar amerykański",
                                   "data": "2026-06-24", "kurs": 4.0200})

    def test_parse_tables_empty(self):
        self.assertEqual(nbp.parse_tables([]), [])
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `python -m unittest tests.test_nbp_import.ParseTablesTest -v`
Expected: FAIL — `AttributeError: module 'nbp_import' has no attribute 'parse_tables'`.

- [ ] **Step 3: Dopisz `parse_tables` do `nbp_import.py`**

Dodaj poniżej `batches`:

```python
def parse_tables(tables):
    """Lista dni z NBP -> lista wierszy {kod, waluta, data, kurs}."""
    rows = []
    for t in tables:
        data = t.get("effectiveDate")
        for r in t.get("rates", []):
            rows.append({
                "kod": r.get("code"),
                "waluta": r.get("currency"),
                "data": data,
                "kurs": r.get("mid"),
            })
    return rows
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m unittest tests.test_nbp_import -v`
Expected: PASS (8 testów).

- [ ] **Step 5: Commit**

```bash
git add nbp_import.py tests/test_nbp_import.py
git commit -m "feat(nbp): przetworzenie odpowiedzi NBP na wiersze"
```

---

### Task 4: Pobranie tabeli z NBP (izolacja I/O)

**Files:**
- Modify: `nbp_import.py`
- Test: `tests/test_nbp_import.py`

**Interfaces:**
- Consumes: `parse_tables` (Task 3)
- Produces:
  - `_get(url: str) -> tuple[int, str]` — jedyne miejsce realnego I/O sieciowego (status, treść); podmieniane w testach.
  - `fetch_table(letter: str, start: str, end: str) -> list[dict]` — pobiera tabelę `letter` dla zakresu dat (stringi `YYYY-MM-DD`), zwraca wiersze z `parse_tables`; przy 404 (brak danych) zwraca `[]`, przy innym błędzie podnosi `RuntimeError`.

- [ ] **Step 1: Dopisz testy (najpierw padają)**

Dodaj do `tests/test_nbp_import.py`:

```python
class FetchTableTest(unittest.TestCase):
    def setUp(self):
        self._orig_get = nbp._get
        self.calls = []

    def tearDown(self):
        nbp._get = self._orig_get

    def test_fetch_table_builds_url_and_parses(self):
        sample = json.dumps([
            {"effectiveDate": "2026-06-23",
             "rates": [{"currency": "euro", "code": "EUR", "mid": 4.25}]},
        ])
        def fake_get(url):
            self.calls.append(url)
            return 200, sample
        nbp._get = fake_get
        rows = nbp.fetch_table("A", "2026-06-01", "2026-06-23")
        self.assertEqual(self.calls[0],
            "https://api.nbp.pl/api/exchangerates/tables/A/2026-06-01/2026-06-23/?format=json")
        self.assertEqual(rows, [{"kod": "EUR", "waluta": "euro",
                                 "data": "2026-06-23", "kurs": 4.25}])

    def test_fetch_table_404_returns_empty(self):
        nbp._get = lambda url: (404, "404 NotFound - Not Found")
        self.assertEqual(nbp.fetch_table("B", "2024-12-25", "2024-12-26"), [])

    def test_fetch_table_raises_on_other_error(self):
        nbp._get = lambda url: (500, "server error")
        with self.assertRaises(RuntimeError) as ctx:
            nbp.fetch_table("A", "2026-06-01", "2026-06-23")
        self.assertIn("500", str(ctx.exception))
```

Dodaj `import json` na górze pliku testowego, jeśli go nie ma.

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `python -m unittest tests.test_nbp_import.FetchTableTest -v`
Expected: FAIL — `AttributeError: module 'nbp_import' has no attribute '_get'` / `fetch_table`.

- [ ] **Step 3: Dopisz `_get` i `fetch_table` do `nbp_import.py`**

Dodaj poniżej `parse_tables`:

```python
def _get(url):
    """Jedyne miejsce realnego I/O sieciowego — podmieniane w testach."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"NBP: błąd połączenia: {e.reason}")


def fetch_table(letter, start, end):
    """Pobiera tabelę letter (A/B) dla zakresu dat; 404 = brak danych -> []."""
    url = f"{NBP_BASE}/{letter}/{start}/{end}/?format=json"
    status, text = _get(url)
    if status == 404:
        return []
    if status >= 400:
        raise RuntimeError(f"NBP {letter} {start}..{end}: {status}: {text}")
    return parse_tables(json.loads(text))
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m unittest tests.test_nbp_import -v`
Expected: PASS (11 testów).

- [ ] **Step 5: Commit**

```bash
git add nbp_import.py tests/test_nbp_import.py
git commit -m "feat(nbp): pobranie tabeli NBP z izolacja I/O"
```

---

### Task 5: Orkiestracja `run()` + punkt wejścia

**Files:**
- Modify: `nbp_import.py`
- Test: `tests/test_nbp_import.py`

**Interfaces:**
- Consumes: `months_back`, `chunk_ranges`, `batches` (Task 2), `fetch_table` (Task 4), `db.enabled`, `db.upsert` (`db.py`)
- Produces: `run(today: date | None = None) -> int` — pełny przebieg importu; zwraca łączną liczbę zapisanych wierszy. Gdy `db.enabled()` jest fałszywe, wypisuje instrukcję i zwraca `0` bez sięgania do sieci.

- [ ] **Step 1: Dopisz testy (najpierw padają)**

Dodaj do `tests/test_nbp_import.py`:

```python
class RunTest(unittest.TestCase):
    def setUp(self):
        self._orig = (nbp.fetch_table, nbp.db.enabled, nbp.db.upsert)
        self.upserts = []

    def tearDown(self):
        nbp.fetch_table, nbp.db.enabled, nbp.db.upsert = self._orig

    def test_run_aborts_when_db_disabled(self):
        nbp.db.enabled = lambda: False
        called = []
        nbp.fetch_table = lambda *a, **k: called.append(a) or []
        self.assertEqual(nbp.run(today=date(2026, 6, 24)), 0)
        self.assertEqual(called, [])  # nie sięga do sieci

    def test_run_fetches_chunks_and_upserts(self):
        nbp.db.enabled = lambda: True
        def fake_fetch(letter, start, end):
            return [{"kod": "EUR", "waluta": "euro", "data": end, "kurs": 4.25}]
        nbp.fetch_table = fake_fetch
        def fake_upsert(table, rows, on_conflict):
            self.upserts.append((table, list(rows), on_conflict))
        nbp.db.upsert = fake_upsert

        total = nbp.run(today=date(2026, 6, 24))

        # 2 kawałki (18 mies. > 367 dni) x 2 tabele (A, B) = 4 wiersze
        self.assertEqual(total, 4)
        self.assertTrue(self.upserts)
        for table, rows, on_conflict in self.upserts:
            self.assertEqual(table, "kursy_walut")
            self.assertEqual(on_conflict, "kod,data")
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `python -m unittest tests.test_nbp_import.RunTest -v`
Expected: FAIL — `AttributeError: module 'nbp_import' has no attribute 'run'`.

- [ ] **Step 3: Dopisz `run()` i blok `__main__` do `nbp_import.py`**

Dodaj poniżej `fetch_table`:

```python
def run(today=None):
    """Pobiera kursy A i B za ostatnie MONTHS miesięcy i zapisuje do Supabase.
    Zwraca łączną liczbę zapisanych wierszy."""
    if not db.enabled():
        print("Brak konfiguracji Supabase. Ustaw zmienne SUPABASE_URL i "
              "SUPABASE_KEY (te same, których używa aplikacja) i spróbuj ponownie.")
        return 0

    today = today or date.today()
    start = months_back(today, MONTHS)
    chunks = chunk_ranges(start, today)
    print(f"Pobieram kursy od {start.isoformat()} do {today.isoformat()} "
          f"({len(chunks)} zakres(y)).")

    total = 0
    for s, e in chunks:
        for letter in ("A", "B"):
            rows = fetch_table(letter, s.isoformat(), e.isoformat())
            for batch in batches(rows, BATCH):
                db.upsert("kursy_walut", batch, on_conflict="kod,data")
            total += len(rows)
            print(f"  Tabela {letter} {s.isoformat()}..{e.isoformat()}: "
                  f"{len(rows)} kursów.")
    print(f"Gotowe. Zapisano łącznie {total} kursów do tabeli kursy_walut.")
    return total


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Uruchom cały zestaw testów modułu — mają przejść**

Run: `python -m unittest tests.test_nbp_import -v`
Expected: PASS (13 testów).

- [ ] **Step 5: Uruchom pełny zestaw testów projektu — nic nie zepsute**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (wszystkie dotychczasowe testy + nowe).

- [ ] **Step 6: Commit**

```bash
git add nbp_import.py tests/test_nbp_import.py
git commit -m "feat(nbp): orkiestracja importu run() + punkt wejscia"
```

---

### Task 6: Instrukcja uruchomienia + aktualizacja notatek

**Files:**
- Modify: `instrukcja_vercel.html` (nowa sekcja o imporcie kursów NBP)
- Modify: `DO_ZROBIENIA.md` (dopisek o nowym skrypcie)

**Interfaces:**
- Consumes: nic (dokumentacja)
- Produces: nic

- [ ] **Step 1: Znajdź sekcję Supabase w `instrukcja_vercel.html`**

Run: `python -c "import re,io; s=open('instrukcja_vercel.html',encoding='utf-8').read(); print(s.find('Supabase'))"`
Expected: liczba > -1 (znaleziono sekcję, w pobliżu której dodamy nową).

- [ ] **Step 2: Dodaj sekcję instrukcji (po sekcji o Supabase)**

Wstaw blok HTML opisujący krok po kroku (dopasuj znaczniki do stylu sąsiednich sekcji w pliku — nagłówek + lista kroków):

```html
<h2>Import kursów walut NBP (kursy_walut)</h2>
<ol>
  <li>W panelu Supabase otwórz <strong>SQL Editor → New query</strong>,
      wklej całość pliku <code>supabase_schema.sql</code> i kliknij
      <strong>Run</strong>. Powstanie m.in. tabela <code>kursy_walut</code>
      (jeśli już raz uruchamiałeś ten plik, nic złego się nie stanie —
      tabele tworzone są tylko, gdy ich nie ma).</li>
  <li>Na komputerze ustaw zmienne <code>SUPABASE_URL</code> i
      <code>SUPABASE_KEY</code> (te same, co dla aplikacji).</li>
  <li>Uruchom: <code>python nbp_import.py</code>. Skrypt pobierze kursy
      wszystkich walut (tabele A i B) za ostatnie 18 miesięcy i zapisze je
      do tabeli <code>kursy_walut</code>, pokazując postęp.</li>
  <li>Skrypt można uruchomić ponownie — istniejące kursy zostaną nadpisane,
      bez duplikatów.</li>
</ol>
```

- [ ] **Step 3: Dopisz wzmiankę do `DO_ZROBIENIA.md`**

Dodaj w sekcji „Co już działa" punkt:

```markdown
- **Import kursów walut NBP** (`nbp_import.py`): jednorazowe pobranie średnich
  kursów wszystkich walut (tabele A + B) za ostatnie 18 miesięcy do tabeli
  Supabase `kursy_walut`. Uruchamiane lokalnie: `python nbp_import.py`.
```

- [ ] **Step 4: Sprawdź, że pliki się otwierają / są spójne**

Run: `python -c "open('instrukcja_vercel.html',encoding='utf-8').read(); open('DO_ZROBIENIA.md',encoding='utf-8').read(); print('OK')"`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add instrukcja_vercel.html DO_ZROBIENIA.md
git commit -m "docs(nbp): instrukcja importu kursow walut NBP"
```

---

## Uwagi końcowe

- Po wykonaniu całości: opcjonalna ręczna próba na żywo — ustaw `SUPABASE_URL`/`SUPABASE_KEY`, uruchom `python nbp_import.py`, sprawdź w panelu Supabase, że tabela `kursy_walut` ma dane.
- Poza zakresem tego planu (na później): automatyczne codzienne dogrywanie (Vercel Cron), prezentacja kursów w aplikacji, tabela C (kupno/sprzedaż).
