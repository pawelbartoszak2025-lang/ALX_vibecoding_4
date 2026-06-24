# Import kursów walut NBP do Supabase — projekt

Data: 2026-06-24

## Cel

Jednorazowy skrypt, który pobiera ze strony `api.nbp.pl` kursy **wszystkich
dostępnych walut** (tabele A + B, średni kurs) za **ostatnie 18 miesięcy** i
zapisuje je do **nowej tabeli w istniejącym projekcie Supabase** (tym samym,
którego używa aplikacja otodom).

Uruchamiany ręcznie z komputera użytkownika. Późniejsze automatyczne dogrywanie
nowych dni (np. Vercel Cron) to osobny temat — poza zakresem tego projektu.

## Zakres danych

- **Źródło:** NBP Web API, tabele kursowe **A** (waluty popularne) i **B**
  (waluty rzadsze). Razem ok. 140+ walut, średni kurs (`mid`).
- **Okres:** od dnia uruchomienia cofając się o 18 miesięcy.
- **Pomijane:** dni bez notowań (weekendy, święta) — NBP ich nie zwraca,
  skrypt traktuje to jako normę, nie błąd.

## Tabela w Supabase

Nowa tabela `kursy_walut`:

| Kolumna  | Typ            | Opis                                    | Przykład              |
|----------|----------------|-----------------------------------------|-----------------------|
| `kod`    | text           | 3-literowy kod waluty                   | `USD`                 |
| `waluta` | text           | pełna nazwa waluty                      | `dolar amerykański`   |
| `data`   | date           | dzień, którego dotyczy kurs             | `2026-06-23`          |
| `kurs`   | numeric        | średni kurs (PLN za 1 jednostkę waluty) | `4.0150`              |

- **Unikalność:** para (`kod`, `data`) jest unikalna → jedna waluta ma jeden
  kurs na dany dzień. Umożliwia bezpieczne ponowne uruchomienie (upsert
  nadpisuje istniejący wpis zamiast tworzyć duplikat).
- Tabelę tworzy użytkownik raz, wklejając gotowy SQL w panelu Supabase
  (PostgREST/`db.py` nie potrafi tworzyć tabel — tylko zapis/odczyt). SQL
  trafia do pliku `supabase_schema.sql` (dopisany do istniejącego) oraz do
  instrukcji krok po kroku.

## Skrypt `nbp_import.py`

Przebieg:

1. **Zakres dat** — `dziś` oraz `dziś − 18 miesięcy`.
2. **Podział na kawałki** — dla tabel A/B NBP pozwala na maks. 93 dni na jedno
   zapytanie o zakres; 18 miesięcy (~548 dni) dzielone jest na kolejne
   podzakresy ≤ 90 dni (z zapasem względem limitu 93).
3. **Pobranie** — dla każdego kawałka osobno tabela A i tabela B:
   `https://api.nbp.pl/api/exchangerates/tables/{A|B}/{start}/{end}/?format=json`
4. **Przetworzenie** — z odpowiedzi (lista dni, każdy z `effectiveDate` i listą
   `rates`) budowane są wiersze `{kod, waluta, data, kurs}`.
5. **Zapis do Supabase** — partiami (np. po ~500 wierszy) przez
   `db.upsert("kursy_walut", rows, on_conflict="kod,data")`.
6. **Postęp i podsumowanie** — czytelne komunikaty tekstowe (ile dni, ile
   kursów dla tabeli A i B, łączna liczba zapisanych wierszy).

### Obsługa błędów

- **Brak danych dla kawałka** (HTTP 404 z NBP) — pomijany z komunikatem,
  bez przerywania całości.
- **Błąd sieci / NBP** — czytelny komunikat z informacją, na którym kawałku/
  tabeli wystąpił; skrypt nie kończy się cichą awarią.
- **Brak `SUPABASE_URL`/`SUPABASE_KEY`** — skrypt od razu informuje, że trzeba
  ustawić zmienne, i kończy działanie (nie próbuje zapisywać „w próżnię").

### Zależności i styl

- Tylko biblioteka standardowa Pythona (zgodnie z resztą projektu).
- Zapis przez istniejący moduł `db.py` (ten sam co aplikacja) — bez
  duplikowania logiki połączenia z Supabase.

## Testy

W stylu reszty projektu (`tests/`), **bez łączenia się z internetem**:

- podział zakresu 18 miesięcy na kawałki ≤ 367 dni (granice, brzegi);
- przetworzenie przykładowej odpowiedzi NBP (A i B) na wiersze tabeli;
- pominięcie pustej/404 odpowiedzi bez błędu.

I/O sieciowe i zapis do Supabase są podmieniane (mock) — jak w istniejących
testach `db`/`store`.

## Uruchomienie (dla użytkownika)

1. Wklej SQL z instrukcji w panelu Supabase → powstaje tabela `kursy_walut`.
2. Ustaw zmienne `SUPABASE_URL` i `SUPABASE_KEY` (te same co dla otodom).
3. `python nbp_import.py` → skrypt pobiera i zapisuje dane, pokazując postęp.

## Poza zakresem (na później)

- Automatyczne codzienne dogrywanie nowych dni (Vercel Cron).
- Prezentacja kursów na stronie / w aplikacji.
- Tabela C (kursy kupna/sprzedaży).
