# Przełącznik walut na liście ofert — plan wdrożenia

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dodać na liście ofert (`oferty.html`) przełącznik waluty (PLN · USD · EUR · GBP), który przelicza ceny w przeglądarce na podstawie najświeższych kursów NBP z Supabase.

**Architecture:** Backend dostaje funkcję `store.read_latest_rates` (najnowszy kurs per waluta z tabeli `kursy_walut`) i endpoint `GET /api/rates`. Przeliczanie i formatowanie kwot to czyste funkcje w nowym module `currency.js` (wzorem `criteria.js`), testowane w Node. `oferty.html` pobiera kursy raz i przy kliknięciu waluty re-renderuje listę.

**Tech Stack:** Python (biblioteka standardowa, `unittest`), istniejący `db.py`/`store.py`, waniliowy JS w przeglądarce, Node do testów modułu JS.

## Global Constraints

- Tylko biblioteka standardowa Pythona — nic nie dopisujemy do `requirements.txt`.
- Odczyt kursów wyłącznie przez `db.py` (`db.enabled`, `db.select`); bez Supabase (lokalny SQLite) kursy są niedostępne i funkcje zwracają pustkę.
- Waluty: **PLN** (domyślna, oryginał) + **USD, EUR, GBP**.
- Przeliczenie: kwota_w_walucie = `round(cena_PLN / kurs)` (NBP podaje PLN za 1 jednostkę). Kwoty obcej waluty bez groszy, odstępy co tysiąc.
- Filtry kryteriów pozostają w PLN — nie zmieniamy logiki dopasowania (`criteria.js`).
- Moduł JS musi być testowalny w Node (wzór: `criteria.js` + `tests/criteria.test.mjs`).
- Wybrana waluta zapamiętywana w `localStorage` pod kluczem `oferty_waluta`; nieprawidłowa/niedostępna → powrót do PLN.

---

### Task 1: Backend — `store.read_latest_rates`

**Files:**
- Modify: `store.py` (dopisz funkcję na końcu pliku)
- Test: `tests/test_store.py` (dopisz testy)

**Interfaces:**
- Consumes: `db.enabled()`, `db.select(table, columns, order, filters)`, istniejący `_num` ze `store.py`.
- Produces: `read_latest_rates(codes) -> dict` — słownik `{kod: kurs_float}` z najnowszą datą dla podanych kodów; `{}` gdy Supabase wyłączone lub brak `codes`.

- [ ] **Step 1: Dopisz testy (najpierw padają)**

W `tests/test_store.py` dodaj do klasy `StoreTest` (tryb bez Supabase) metodę:

```python
    def test_read_latest_rates_empty_without_supabase(self):
        self.assertEqual(store.read_latest_rates(["USD", "EUR"]), {})
```

Oraz nową klasę na końcu pliku (przed `if __name__`):

```python
class StoreLatestRatesTest(unittest.TestCase):
    def setUp(self):
        _store_mod.DB = os.path.join(tempfile.mkdtemp(), "t.db")
        self.rows = []
        self._orig = _store_mod.db
        outer = self
        class FakeDb:
            @staticmethod
            def enabled():
                return True
            @staticmethod
            def select(table, columns="*", order=None, filters=None):
                outer.last = {"table": table, "columns": columns,
                              "order": order, "filters": filters}
                return list(outer.rows)
        _store_mod.db = FakeDb

    def tearDown(self):
        _store_mod.db = self._orig

    def test_picks_latest_date_per_code_and_coerces_float(self):
        # PostgREST zwraca numeric jako tekst; daty malejąco (order data.desc)
        self.rows = [
            {"kod": "USD", "kurs": "3.80", "data": "2026-06-24"},
            {"kod": "EUR", "kurs": "4.25", "data": "2026-06-24"},
            {"kod": "USD", "kurs": "3.70", "data": "2026-06-23"},
        ]
        out = _store_mod.read_latest_rates(["USD", "EUR"])
        self.assertEqual(out, {"USD": 3.80, "EUR": 4.25})
        self.assertIsInstance(out["USD"], float)
        self.assertEqual(self.last["order"], "data.desc")
        self.assertEqual(self.last["filters"], {"kod": "in.(USD,EUR)"})

    def test_empty_codes_returns_empty(self):
        self.assertEqual(_store_mod.read_latest_rates([]), {})
```

- [ ] **Step 2: Uruchom testy — mają paść**

Run: `python -m unittest tests.test_store -v`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'read_latest_rates'`.

- [ ] **Step 3: Dopisz funkcję do `store.py`**

Na końcu `store.py`:

```python
def read_latest_rates(codes):
    """Najnowszy kurs (PLN za 1 jednostkę) dla podanych kodów walut z tabeli
    kursy_walut. Zwraca {kod: kurs}. Bez Supabase (lokalny SQLite) → {}."""
    codes = list(codes or [])
    if not codes or not db.enabled():
        return {}
    rows = db.select("kursy_walut", columns="kod,kurs,data",
                     filters={"kod": "in.(" + ",".join(codes) + ")"},
                     order="data.desc")
    latest = {}
    for r in rows:
        kod = r["kod"]
        if kod not in latest:        # rows malejąco po dacie → pierwszy = najnowszy
            latest[kod] = _num(r["kurs"])
    return latest
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `python -m unittest tests.test_store -v`
Expected: PASS (istniejące + 3 nowe).

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat(waluty): store.read_latest_rates - najnowsze kursy z Supabase"
```

---

### Task 2: Frontend — moduł `currency.js`

**Files:**
- Create: `currency.js`
- Test: `tests/currency.test.mjs`

**Interfaces:**
- Consumes: nic.
- Produces (globalnie w przeglądarce i przez `require` w Node):
  - `convertAmount(pricePln, rate) -> number|null` — `Math.round(pricePln / rate)`; `null` gdy `pricePln == null` lub `rate` fałszywe (`0`/`undefined`).
  - `formatMoney(n) -> string|null` — liczba całkowita z odstępami co tysiąc (zwykła spacja), `null` dla `null`.

- [ ] **Step 1: Napisz test (najpierw pada)**

Utwórz `tests/currency.test.mjs`:

```javascript
// tests/currency.test.mjs
import assert from "node:assert";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { convertAmount, formatMoney } = require("../currency.js");

// convertAmount: dzielenie i zaokrąglenie
assert.strictEqual(convertAmount(377560, 3.7756), 100000);
assert.strictEqual(convertAmount(520000, 4.25), 122353);   // 122352.9 -> 122353
assert.strictEqual(convertAmount(null, 4.25), null);        // inwestycja bez ceny
assert.strictEqual(convertAmount(100000, 0), null);         // brak kursu
assert.strictEqual(convertAmount(100000, undefined), null);

// formatMoney: odstępy co tysiąc, zwykła spacja
assert.strictEqual(formatMoney(999), "999");
assert.strictEqual(formatMoney(1000), "1 000");
assert.strictEqual(formatMoney(137600), "137 600");
assert.strictEqual(formatMoney(null), null);

console.log("currency.test.mjs: OK");
```

- [ ] **Step 2: Uruchom test — ma paść**

Run: `node tests/currency.test.mjs`
Expected: FAIL — `Cannot find module '../currency.js'`.

- [ ] **Step 3: Utwórz `currency.js`**

```javascript
// Czyste funkcje przeliczania i formatowania kwot. Używane w przeglądarce
// (przez <script src>) oraz w teście Node (przez require). Wzór: criteria.js.
(function (root) {
  function convertAmount(pricePln, rate) {
    if (pricePln == null || !rate) return null;
    return Math.round(pricePln / rate);
  }

  function formatMoney(n) {
    if (n == null) return null;
    // zwykła spacja co tysiąc — deterministycznie (niezależnie od locale Node)
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  if (typeof module !== "undefined" && module.exports)
    module.exports = { convertAmount, formatMoney };
  else { root.convertAmount = convertAmount; root.formatMoney = formatMoney; }
})(typeof window !== "undefined" ? window : globalThis);
```

- [ ] **Step 4: Uruchom test — ma przejść**

Run: `node tests/currency.test.mjs`
Expected: `currency.test.mjs: OK`.

- [ ] **Step 5: Commit**

```bash
git add currency.js tests/currency.test.mjs
git commit -m "feat(waluty): modul currency.js (convertAmount, formatMoney) + test"
```

---

### Task 3: Backend — endpoint `/api/rates` i serwowanie `/currency.js`

**Files:**
- Modify: `server.py` (w `do_GET`: nowa trasa pliku `/currency.js` przy `/criteria.js`; nowa trasa API `/api/rates` przy `/api/offers`)

**Interfaces:**
- Consumes: `store.read_latest_rates` (Task 1), istniejące `self._serve_file`, `self._send`.
- Produces: `GET /api/rates` → JSON `{"USD": 3.78, ...}` (dla zalogowanych); `GET /currency.js` → plik modułu.

- [ ] **Step 1: Dodaj trasę `/currency.js`**

W `server.py`, w metodzie `do_GET`, zaraz po bloku obsługującym `/criteria.js`:

```python
        if path == "/criteria.js":
            self._serve_file("criteria.js", "application/javascript; charset=utf-8")
            return
```

dopisz:

```python
        if path == "/currency.js":
            self._serve_file("currency.js", "application/javascript; charset=utf-8")
            return
```

- [ ] **Step 2: Dodaj trasę `/api/rates`**

W `server.py`, w sekcji dla zalogowanych (po bloku `if path == "/api/offers": ...`), dopisz:

```python
            if path == "/api/rates":
                rates = store.read_latest_rates(["USD", "EUR", "GBP"])
                self._send(200, json.dumps(rates, ensure_ascii=False))
                return
```

- [ ] **Step 3: Sprawdź, że serwer importuje się bez błędu**

Run: `python -c "import server; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Uruchom pełny zestaw testów — nic nie zepsute**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (wszystkie dotychczasowe).

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat(waluty): endpoint /api/rates + serwowanie /currency.js"
```

---

### Task 4: Frontend — przełącznik walut w `oferty.html`

**Files:**
- Modify: `oferty.html` (dołączenie modułu, HTML przełącznika, logika JS)

**Interfaces:**
- Consumes: `convertAmount`, `formatMoney` (z `/currency.js`), `GET /api/rates`, istniejące `fmt`, `card`, `renderGrid`, `init`.
- Produces: globalne `activeCurrency`, `RATES`; funkcje `priceParts`, `renderCurrencySwitch`, `loadRates`.

- [ ] **Step 1: Dołącz moduł `currency.js`**

W `oferty.html`, zaraz po linii (ok. 7):

```html
<script src="/criteria.js"></script>
```

dodaj:

```html
<script src="/currency.js"></script>
```

- [ ] **Step 2: Dodaj HTML przełącznika do paska filtrów**

W `<nav class="filters"><div class="wrap">` (ok. linii 227–232), tuż przed `<span id="scrapeStatus" ...>`, wstaw:

```html
  <div class="fdiv"></div>
  <span class="fgroup" style="display:flex;gap:6px;align-items:center">
    <span class="flabel">Waluta</span>
    <span id="currencyButtons" style="display:flex;gap:4px"></span>
  </span>
```

- [ ] **Step 3: Dodaj stan i logikę przełącznika (JS)**

W bloku `<script>`, zaraz po linii `const fmt = n => ...` (ok. 289), dodaj:

```javascript
const CURRENCIES = ["PLN", "USD", "EUR", "GBP"];
let RATES = {};                 // {USD: 3.78, ...} — puste gdy kursy niedostępne
let activeCurrency = "PLN";

// Kwoty do wyświetlenia dla danej oferty wg aktywnej waluty.
function priceParts(o){
  if (activeCurrency === "PLN" || !RATES[activeCurrency]){
    return { main: fmt(o.price), cur: o.currency,
             ppm: o.ppm != null ? fmt(o.ppm) : null };
  }
  const rate = RATES[activeCurrency];
  return { main: formatMoney(convertAmount(o.price, rate)), cur: activeCurrency,
           ppm: o.ppm != null ? formatMoney(convertAmount(o.ppm, rate)) : null };
}

function renderCurrencySwitch(){
  const box = document.getElementById("currencyButtons");
  box.innerHTML = CURRENCIES.map(c => {
    const avail = c === "PLN" || RATES[c] != null;
    const on = c === activeCurrency;
    const style = "padding:3px 8px;border:1px solid var(--line);border-radius:6px;"
      + "cursor:" + (avail ? "pointer" : "not-allowed") + ";"
      + (on ? "background:var(--ink);color:#fff;" : "background:#fff;")
      + (avail ? "" : "opacity:.4;");
    const title = avail ? "" : ' title="kurs niedostępny"';
    return `<button type="button" class="cur-btn" data-cur="${c}"${avail?"":" disabled"}`
      + `${title} style="${style}">${c}</button>`;
  }).join("");
  box.querySelectorAll(".cur-btn").forEach(b => b.addEventListener("click", () => {
    activeCurrency = b.dataset.cur;
    try { localStorage.setItem("oferty_waluta", activeCurrency); } catch (e) {}
    renderCurrencySwitch(); renderGrid();
  }));
}

async function loadRates(){
  try {
    const r = await fetch("/api/rates");
    RATES = r.ok ? await r.json() : {};
  } catch (e) { RATES = {}; }      // błąd kursów nie może wywalić strony
  let saved = "PLN";
  try { saved = localStorage.getItem("oferty_waluta") || "PLN"; } catch (e) {}
  activeCurrency = (saved === "PLN" || RATES[saved] != null) ? saved : "PLN";
  renderCurrencySwitch();
  renderGrid();
}
```

- [ ] **Step 4: Użyj `priceParts` w `card()`**

W funkcji `card(o, i)` zastąp blok budujący `price` (ok. linii 429–432):

```javascript
  const price = inv
    ? `<div class="price-main price-inv">Inwestycja</div>`
    : `<div class="price-main">${fmt(o.price)}<span class="price-cur">${o.currency}</span></div>` +
      (o.ppm ? `<div class="price-ppm">${fmt(o.ppm)} ${o.currency}/m²</div>` : "");
```

nową wersją:

```javascript
  const pp = priceParts(o);
  const price = inv
    ? `<div class="price-main price-inv">Inwestycja</div>`
    : `<div class="price-main">${pp.main}<span class="price-cur">${pp.cur}</span></div>` +
      (pp.ppm ? `<div class="price-ppm">${pp.ppm} ${pp.cur}/m²</div>` : "");
```

- [ ] **Step 5: Wczytaj kursy przy starcie**

W funkcji `init()` (ok. linii 535–539) dodaj `await loadRates();` po `await loadOffers();`:

```javascript
(async function init(){
  await loadCriteria();
  await loadScheduler();
  await loadOffers();
  await loadRates();
})();
```

- [ ] **Step 6: Sprawdź testy modułu JS i pełny zestaw (nic nie zepsute)**

Run: `node tests/currency.test.mjs`
Expected: `currency.test.mjs: OK`

Run: `python -m unittest discover -s tests`
Expected: `OK`

- [ ] **Step 7: Sprawdź spójność `oferty.html` (statyczny odczyt)**

Run: `python -c "s=open('oferty.html',encoding='utf-8').read(); assert '/currency.js' in s and 'currencyButtons' in s and 'priceParts' in s and 'loadRates' in s; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add oferty.html
git commit -m "feat(waluty): przelacznik walut na liscie ofert (PLN/USD/EUR/GBP)"
```

---

## Weryfikacja końcowa (po wszystkich zadaniach)

Wzrokowa próba na żywo (poza automatycznymi testami): uruchom `python server.py`,
zaloguj się, otwórz listę ofert. Oczekiwane:
- pasek „Waluta: PLN USD EUR GBP"; domyślnie PLN;
- klik USD/EUR/GBP przelicza wszystkie ceny i ceny/m²; „Inwestycja" bez zmian;
- po odświeżeniu wybór waluty pamiętany;
- lokalnie bez Supabase (brak kursów) aktywne tylko PLN, reszta wyszarzona.

## Poza zakresem (na później)

- Automatyczne dogrywanie kursów (Vercel Cron), historia kursów, tabela C,
  przeliczanie limitów w kryteriach.
