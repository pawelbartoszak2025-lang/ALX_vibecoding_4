# Przełącznik walut na liście ofert — projekt

Data: 2026-06-24

## Cel

Na liście ofert (`oferty.html`) dodać **przełącznik waluty** (PLN · USD · EUR ·
GBP). Domyślnie ceny są w PLN (oryginał z Otodom). Klik w inną walutę przelicza
**wszystkie** ceny na liście na wybraną walutę, używając najświeższych kursów
NBP zapisanych w Supabase (tabela `kursy_walut`).

## Zakres

- Waluty: **PLN** (domyślna, oryginał) + **USD, EUR, GBP**.
- Przeliczane: **cena główna** oferty oraz **cena za m²**.
- Przeliczanie odbywa się **w przeglądarce**; kursy pobierane raz przy wczytaniu
  strony z nowego endpointu `/api/rates`.

Poza zakresem: zmiana logiki kryteriów (filtry „cena maks." itd. pozostają w
PLN), tabela C, prezentacja historii kursów, automatyczne dogrywanie kursów.

## Architektura i przepływ danych

1. **Backend — odczyt kursów.** Nowa funkcja `store.read_latest_rates(codes)`
   zwraca słownik `{kod: kurs}` z **najnowszą** datą dla podanych kodów walut.
   - Gdy Supabase działa (`db.enabled()`): `db.select("kursy_walut",
     columns="kod,kurs,data", filters={"kod": "in.(USD,EUR,GBP)"},
     order="data.desc")`, następnie w Pythonie bierzemy **pierwszy** (najnowszy)
     wiersz dla każdego kodu.
   - Gdy Supabase nie jest skonfigurowane (lokalny SQLite — tabeli kursów nie
     ma): zwraca pusty słownik `{}`.
2. **Backend — endpoint.** `GET /api/rates` (tylko dla zalogowanych, jak inne
   `/api/*`) zwraca `json` ze słownikiem kursów, np.
   `{"USD": 3.7756, "EUR": 4.25, "GBP": 5.05}`. Gdy brak danych → `{}`.
3. **Frontend — pobranie.** Przy wczytaniu strony (obok `loadCriteria` itd.)
   pobieramy `/api/rates` do zmiennej `RATES`.
4. **Frontend — przeliczenie.** Klik waluty ustawia `activeCurrency` i ponownie
   renderuje listę. W renderze karty kwoty przeliczamy funkcją z osobnego,
   testowalnego modułu `currency.js`.

## Moduł `currency.js` (testowalny, wzorem `criteria.js`)

Serwowany pod `/currency.js` (jak `criteria.js`). Czyste funkcje:

- `convertAmount(pricePln, rate)` → `Math.round(pricePln / rate)`; gdy `rate`
  jest fałszywe (`0`/`undefined`) lub `pricePln == null` → zwraca `null`.
- `formatMoney(n)` → liczba całkowita z odstępami co tysiąc (np. `137600` →
  `"137 600"`), spójnie z istniejącą funkcją `fmt` w `oferty.html`.

`oferty.html` używa tych funkcji w `card()`. Dla PLN (`activeCurrency === "PLN"`)
zachowujemy dotychczasowe formatowanie bez przeliczania.

## Interfejs

- **Przełącznik**: pasek przycisków `PLN · USD · EUR · GBP` u góry listy ofert
  (przy nagłówku/filtrach). Aktywna waluta podświetlona; domyślnie PLN.
- **Przeliczane**: cena główna i cena za m². Format: pełne jednostki bez groszy,
  odstępy co tysiąc, kod waluty po liczbie (np. `137 600 USD`, `2 647 USD/m²`).
- **Oferty bez ceny („Inwestycja")**: bez zmian — nie ma czego przeliczać.
- **Filtry kryteriów**: pozostają w PLN (bez zmian w logice dopasowania).
- **Zapamiętywanie wyboru**: wybrana waluta zapisywana w `localStorage`
  (klucz np. `oferty_waluta`); po odświeżeniu strona przywraca wybór. Jeśli
  zapamiętana waluta nie ma kursu (np. kursy niedostępne) → wraca do PLN.

## Obsługa błędów / przypadki brzegowe

- **Kursy niedostępne** (lokalny SQLite albo pusta tabela): `/api/rates` zwraca
  `{}`. Przełącznik pokazuje aktywne tylko `PLN`; pozostałe przyciski nieaktywne
  (wyszarzone) z krótką informacją „kursy niedostępne". Aplikacja działa
  normalnie w PLN.
- **Brak kursu pojedynczej waluty** (np. jest USD i EUR, brak GBP): tylko ta
  jedna waluta nieaktywna; reszta działa.
- **`/api/rates` zwróci błąd / nie odpowie**: frontend traktuje to jak brak
  kursów (zostajemy na PLN), bez wywracania strony.

## Testy

- **Python** (`tests/test_store.py` lub nowy): `read_latest_rates` —
  - wybiera najnowszą datę per kod, gdy w danych jest kilka dat (mock
    `db.select` jak w istniejących testach),
  - zwraca `{}`, gdy `db.enabled()` jest fałszywe.
- **Node** (`tests/currency.test.mjs`, wzorem `criteria.test.mjs`):
  - `convertAmount` — poprawne dzielenie i zaokrąglenie; `null` dla ceny `null`
    i dla zerowego/braku kursu,
  - `formatMoney` — odstępy co tysiąc (np. `1000` → `1 000`, `137600` →
    `137 600`).

## Uruchomienie / wdrożenie

Bez nowej konfiguracji. Po wdrożeniu na Vercel (gdzie Supabase i kursy są)
przełącznik pokaże wszystkie waluty. Lokalnie bez Supabase — samo PLN.
