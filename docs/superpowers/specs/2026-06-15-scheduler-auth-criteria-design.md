# Specyfikacja: harmonogram + logowanie + kryteria użytkownika

Data: 2026-06-15
Projekt: lokalna aplikacja do przeglądania ofert Otodom (nauka).

## Cel

Rozszerzyć istniejącą aplikację o trzy funkcje:

1. **Cykliczne pobieranie** ofert według harmonogramu (10–15 min, nie częściej),
   z ręcznym konfiguratorem (częstotliwość, wybór miast, włącz/wyłącz,
   przełącznik wysyłki na Discord).
2. **Logowanie** (login + hasło) — jedno konto użytkownika.
3. **Kryteria użytkownika** zapisywane w bazie; po zalogowaniu lista pokazuje
   **tylko pasujące** oferty (z możliwością przełączenia na wszystkie).

## Założenia i zakres

- Aplikacja lokalna, jeden użytkownik (projekt do nauki). Bezpieczeństwo
  „rozsądne", nie produkcyjne. Bez dodatkowych instalacji poza już obecnymi
  (`discord.py`); reszta na bibliotece standardowej Pythona.
- Bot Discord (`discord_bot.py`) działa bez zmian.
- Decyzje potwierdzone z użytkownikiem:
  - jedno konto (nie wielu userów),
  - akcja cyklu konfigurowalna (przełącznik „wysyłaj na Discord"),
  - miasta w cyklu konfigurowalne (domyślnie testowo: Poznań),
  - widok kryteriów = filtr (tylko pasujące) z przełącznikiem na wszystkie,
  - kryteria: cena maks., cena/m² maks., liczba pokoi (min), powierzchnia
    (min/maks), miasto, typ (prywatne/agencja).

## Kluczowa zmiana architektoniczna

Dziś `oferty.html` ma dane ofert wpisane na stałe (tablica `OFERTY`).
Aby harmonogram cokolwiek zmieniał, strona musi **pobierać oferty z bazy**
przez `GET /api/offers`. To spina całość: harmonogram pisze do bazy →
strona czyta z bazy → kryteria filtrują wynik po stronie przeglądarki.

## Schemat bazy (`otodom.db`)

Nowe tabele:

- `users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
  pass_hash TEXT, salt TEXT, created_at TEXT)` — w praktyce jeden rekord.
- `app_settings(key TEXT PRIMARY KEY, value TEXT)` — wartości jako JSON:
  - klucz `scheduler`:
    `{enabled:false, interval_min:15, cities:["Poznań"],
      discord_autosend:false, last_run:null, last_error:null}`
  - klucz `criteria`:
    `{price_max:null, ppm_max:null, rooms_min:null, area_min:null,
      area_max:null, cities:[], owner_type:"any"}`

Bez zmian: `oferty`, `discord_sent`.

Sesje: trzymane w pamięci serwera (słownik `token -> {username, created}`),
przekazywane ciasteczkiem `session=<token>` z flagą `HttpOnly`.

## Moduły (małe, jednozadaniowe)

- `auth.py` — rejestracja konta, weryfikacja hasła (pbkdf2_hmac z biblioteki
  `hashlib`, sól per-konto z `secrets`), tworzenie/odczyt/kasowanie sesji.
- `store.py` — odczyt/zapis ustawień (JSON w `app_settings`), odczyt ofert
  z bazy (kształt jak `OFERTY`, z polem `wojewodztwo`), **zapis ofert do bazy**
  (upsert po `otodom_id`/URL; współdzielony przez ręczne `scrape` i harmonogram).
- `scheduler.py` — `run_cycle()` (jeden cykl) i `scheduler_loop()` (pętla),
  uruchamiana jako wątek-demon w `server.py`.
- `server.py` — routing HTTP + start wątku harmonogramu.
- `login.html` — logowanie / rejestracja (pierwsze uruchomienie).
- `oferty.html` — aplikacja po zalogowaniu (pobiera dane z API, panele
  Kryteria i Harmonogram).

## Endpointy

Wszystkie `/api/*` poza `login`/`register` wymagają ważnej sesji (inaczej `401`).

- `GET /` → zalogowany: serwuje `oferty.html`; niezalogowany → przekierowanie na `/login`.
- `GET /login` → `login.html` (pokazuje „Utwórz konto", gdy konta jeszcze nie ma).
- `POST /api/register` → tworzy jedyne konto (działa tylko gdy konta brak); ustawia sesję.
- `POST /api/login` → weryfikuje hasło, ustawia ciasteczko sesji.
- `POST /api/logout` → kasuje sesję.
- `GET /api/me` → `{logged_in:bool, account_exists:bool, username?:str}`.
- `GET /api/offers` → lista ofert z bazy (JSON).
- `GET /api/criteria` · `POST /api/criteria` → odczyt/zapis kryteriów.
- `GET /api/scheduler` · `POST /api/scheduler` → odczyt/zapis konfiguracji harmonogramu.
- Istniejące: `GET /api/scrape` (teraz **zapisuje też do bazy**), `POST /api/discord` —
  oba za loginem. Po ręcznym „Pobierz" strona ponownie pobiera `/api/offers`
  z bazy (zamiast doklejać dane tylko po stronie przeglądarki jak obecnie),
  dzięki czemu źródłem prawdy jest zawsze baza.

## Przepływ użytkownika

1. Wejście na `http://localhost:8000` → brak sesji → `/login`. Pierwszy raz:
   formularz „Utwórz konto" (login + hasło). Kolejne razy: logowanie.
2. Po zalogowaniu strona pobiera `/api/offers` + `/api/criteria` i pokazuje
   **tylko pasujące** oferty. Przełącznik „Tylko pasujące / Wszystkie".
   Nagłówek: nazwa użytkownika + przycisk „Wyloguj".
3. Panel **Kryteria**: cena maks., cena/m² maks., min. pokoi, powierzchnia
   min/maks, miasta (wielokrotny wybór), typ (dowolny/prywatne/agencja).
   Zapis → `POST /api/criteria`.
4. Panel **Harmonogram**: włącz/wyłącz, częstotliwość (10/15/30/60 min),
   miasta (checkboxy, domyślnie Poznań), „wysyłaj na Discord", oraz status
   (ostatni cykl, ewentualny błąd). Zapis → `POST /api/scheduler`.
5. Wątek harmonogramu co cykl: dla każdego zaznaczonego miasta `server.scrape`
   → zapis do bazy → (jeśli włączone) `discord_send.send_city`. Aktualne dane
   pojawią się przy odświeżeniu listy.

## Harmonogram — szczegóły

- Wątek-demon startuje wraz z serwerem.
- Pętla budzi się co ~30 s i sprawdza konfigurację; uruchamia cykl, gdy
  `enabled=true` i minął `interval_min` od `last_run`.
- Minimalny odstęp wymuszony na **10 min** (wartości < 10 podnoszone do 10).
- Mapowanie miasto → województwo dla scrapera: Poznań→wielkopolskie,
  Kraków→małopolskie, Warszawa→mazowieckie, Gdańsk→pomorskie.
- Po cyklu zapis `last_run` (znacznik czasu) oraz `last_error` (lub `null`).

## Kryteria — logika dopasowania

Oferta pasuje, gdy spełnia wszystkie ustawione (niepuste) warunki:

- `price <= price_max` (jeśli ustawione i oferta ma cenę),
- `ppm <= ppm_max`,
- `rooms >= rooms_min`,
- `area >= area_min` oraz `area <= area_max`,
- `miasto ∈ cities` (jeśli lista niepusta),
- typ: `owner_type` = `any` | `private` | `agency`.

Oferty bez ceny (inwestycje) są traktowane jako **niepasujące**, gdy ustawiono
limit ceny lub ceny/m² (brak danych do porównania). Filtrowanie wykonywane jest
po stronie przeglądarki na danych z `/api/offers`.

## Obsługa błędów

- Żądanie `/api/*` bez sesji → `401`; strona aplikacji przekierowuje na `/login`.
- Błędne hasło / rejestracja gdy konto istnieje → czytelny komunikat na stronie.
- Błąd cyklu harmonogramu → złapany, zapisany w `scheduler.last_error`,
  pętla działa dalej (nie przerywa serwera).
- Częstotliwość < 10 min → automatycznie ustawiana na 10.
- Błędy `scrape`/Discord → jak obecnie (komunikat w odpowiedzi / w statusie).

## Poza zakresem (YAGNI)

- Wielu użytkowników, role, reset hasła e-mailem.
- Szyfrowanie TLS (lokalny serwer na `127.0.0.1`).
- Powiadomienia push w przeglądarce, automatyczne odświeżanie listy w tle
  (lista odświeża się przy przeładowaniu/akcji; ewentualnie do rozważenia później).

## Uwaga dot. git

Katalog projektu nie jest repozytorium git (`git init` nie był wykonywany).
Dokument zapisany lokalnie; commit pominięty (brak repo). Można zainicjować
repozytorium na życzenie.
