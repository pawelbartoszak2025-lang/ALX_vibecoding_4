# Migracja SQLite → Supabase (Postgres) — specyfikacja

Data: 2026-06-20

## Cel

Strona wdrożona na Vercelu (https://alx-vibecoding-4.vercel.app/) ma mieć te same
funkcjonalności co wersja lokalna. Obecnie na Vercelu dane nie przetrwają, bo
aplikacja zapisuje je do pliku SQLite (`otodom.db`) w katalogu `/tmp`, który na
serverless jest **ulotny** (kasowany między żądaniami i niedzielony między
instancjami). Skutek: znikają zapisane oferty, ustawienia (kryteria, harmonogram)
oraz pamięć wysyłek na Discord.

Rozwiązanie: trwałe dane w **Supabase** (baza Postgres + wbudowane API HTTP /
PostgREST). Logowanie już działa w chmurze przez zmienne środowiskowe i nie wymaga
zmian.

## Decyzje (ustalone z użytkownikiem)

1. **Połączenie:** HTTP API Supabase (PostgREST) przez bibliotekę standardową
   Pythona (`urllib`). **Brak nowych zależności** — zgodne z filozofią projektu
   (`requirements.txt` pozostaje pusty). Dobre dla serverless (brak problemu z
   pulą połączeń Postgresa).
2. **Tryb lokalny vs chmura:** jeden „przełącznik". Gdy ustawione są zmienne
   `SUPABASE_URL` i `SUPABASE_KEY` → tryb Supabase. W przeciwnym razie → SQLite
   (jak dotąd). Lokalnie nic się nie zmienia, działa offline.
3. **Konto Supabase:** użytkownik ma już projekt; potrzebuje tylko instrukcji
   konfiguracji kluczy.
4. **Harmonogram automatyczny w chmurze:** poza zakresem tej migracji (wymaga
   Vercel Cron). Do zrobienia osobno w przyszłości.

## Zakres

W zakresie (ma działać w chmurze po migracji):
- trwałe oferty (`oferty`),
- kryteria i konfiguracja harmonogramu (`app_settings`),
- ręczne „Pobierz 10 najnowszych ofert",
- wysyłka na Discord wraz z pamięcią dedupu (`discord_sent`),
- logowanie (już działa przez zmienne env — bez zmian).

Poza zakresem:
- automatyczne odpalanie harmonogramu w chmurze (Vercel Cron) — do zrobienia
  później,
- migracja istniejących danych z lokalnego `otodom.db` do Supabase (nie jest
  potrzebna — dane na produkcji budują się od nowa).

## Architektura

### Nowy moduł `db.py`
Jedyne miejsce komunikacji z Supabase REST. Bez nowych bibliotek (`urllib`).

Odpowiedzialności:
- `enabled()` → `bool` — czy ustawione są `SUPABASE_URL` i `SUPABASE_KEY`.
- `_request(method, path, *, params=None, body=None, prefer=None)` — wewnętrzny
  helper budujący URL `{SUPABASE_URL}/rest/v1/{path}`, nagłówki (`apikey`,
  `Authorization: Bearer <key>`, `Content-Type: application/json`, opcjonalnie
  `Prefer`) i parsujący odpowiedź JSON. Mapuje błędy HTTP na czytelny wyjątek.
- `select(table, *, columns="*", order=None, filters=None)` → lista wierszy.
- `upsert(table, rows, *, on_conflict, ignore_duplicates=False)` — POST z
  nagłówkiem `Prefer: resolution=merge-duplicates` (lub `ignore-duplicates`) i
  parametrem `on_conflict`.

Klucz API: `service_role` (po stronie serwera, omija RLS). Trzymany wyłącznie w
zmiennych środowiskowych, nigdy w kodzie ani po stronie przeglądarki.

Funkcje czysto składające URL/parametry/payload (bez sieci) wydzielone tak, by dało
się je testować jednostkowo bez połączenia.

### Zmiany w istniejących modułach
W każdej funkcji dotykającej bazy proste rozgałęzienie:
`if db.enabled(): <Supabase> else: <SQLite jak dotąd>`. Gałąź SQLite pozostaje
nietknięta (lokalnie i w testach działa bez zmian).

- `store.py`:
  - `get_settings(key)` — Supabase: `select("app_settings", filters={"key": key})`,
    odczyt kolumny `value` (tekst JSON) → `json.loads`; scalenie z `DEFAULTS`.
  - `save_settings(key, data)` — Supabase: `upsert("app_settings", [...],
    on_conflict="key")`, `value` jako `json.dumps`.
  - `save_offers(offers)` — Supabase: `upsert("oferty", [...],
    on_conflict="otodom_id")`.
  - `read_offers()` — Supabase: `select("oferty", order="miasto_wyszukiwania.asc,
    price.asc.nullslast")`; dalsze przetwarzanie (woj., mapowanie pokoi) wspólne
    dla obu gałęzi.
- `discord_send.py`:
  - `filter_new(miasto, offers)` — Supabase: `select("discord_sent",
    columns="url", filters={"miasto": miasto})`.
  - `mark_sent(miasto, offers)` — Supabase: `upsert("discord_sent", [...],
    on_conflict="miasto,url", ignore_duplicates=True)`.
- `auth.py`: **bez zmian** (w chmurze tryb `APP_USERNAME`/`APP_PASSWORD`).

### Schemat bazy — `supabase_schema.sql`
Plik do jednorazowego wklejenia w SQL Editor w Supabase. Tabele 1:1 z SQLite:

- `oferty` — `id bigserial primary key`, `miasto_wyszukiwania text`,
  `otodom_id bigint unique`, `title text`, `price numeric`, `currency text`,
  `price_per_m2 numeric`, `area_m2 numeric`, `rooms text`, `floor text`,
  `is_private_owner boolean`, `location text`, `url text`.
- `app_settings` — `key text primary key`, `value text` (JSON jako tekst, by
  kod był identyczny w obu gałęziach).
- `discord_sent` — `miasto text`, `url text`, `sent_at timestamptz default now()`,
  `unique (miasto, url)`.

`users` nie jest tworzona (konto w chmurze z env). RLS może pozostać włączone —
klucz `service_role` go omija.

## Konfiguracja (Vercel)

Zmienne środowiskowe w ustawieniach projektu na Vercelu:
- `SUPABASE_URL` — np. `https://<projekt>.supabase.co`
- `SUPABASE_KEY` — klucz `service_role` (Project Settings → API).

Lokalnie zmiennych nie ustawiamy → automatycznie tryb SQLite.

Instrukcja konfiguracji zostanie dopisana do `instrukcja_vercel.html`
(gdzie znaleźć URL i klucz, jak dodać zmienne, jak wkleić schemat SQL).

## Obsługa błędów

- `db._request` zamienia błędy HTTP Supabase na wyjątek z czytelnym komunikatem
  (kod + treść). Wywołania w `server.py` są już owinięte w `try/except` i zwracają
  502 z opisem — zachowujemy ten wzorzec.
- Brak/niepełna konfiguracja: jeśli ustawiony jest tylko jeden z `SUPABASE_URL` /
  `SUPABASE_KEY`, `enabled()` zwraca `False` (bezpieczny fallback do SQLite),
  a sytuacja jest logowana ostrzeżeniem.

## Testy

- Istniejące testy (`tests/test_store.py` itd.) działają dalej bez zmian — w
  testach brak zmiennych Supabase, więc używana jest gałąź SQLite.
- Nowe testy jednostkowe dla czystych helperów w `db.py` (budowanie URL,
  parametrów `order`/`on_conflict`, nagłówka `Prefer`, payloadu upsert) — bez
  sieci, przez podstawienie zmiennych środowiskowych i sprawdzenie składanego
  żądania (np. monkeypatch warstwy HTTP).

## Kryteria akceptacji

1. Lokalnie (bez zmiennych Supabase) wszystko działa jak dotąd; wszystkie testy
   przechodzą.
2. Po ustawieniu zmiennych i wklejeniu schematu w chmurze: pobrane oferty,
   kryteria, konfiguracja harmonogramu i pamięć Discord są trwałe między
   żądaniami.
3. `requirements.txt` pozostaje bez zależności zewnętrznych.
