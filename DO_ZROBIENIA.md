# Stan projektu i co dalej

Data: 2026-06-16

## ✅ Co już działa
- **Strona z ofertami** (`oferty.html`) serwowana przez `server.py`; filtrowanie po
  **województwie** i **mieście** (listy rozwijane).
- **Ręczne pobieranie** „Pobierz 10 najnowszych ofert" (scraping Otodom na żywo).
- **Wysyłka na Discord** przyciskiem → tworzy kanał `#miasto` i dokłada tylko nowe
  oferty (bez powtórek).
- **Bot Discord** (`discord_bot.py`) ze slash-komendami: `/poznan`, `/krakow`,
  `/warszawa`, `/gdansk`. Token czytany ze zmiennej środowiskowej `Discord_bot_token`.
- **Uruchamianie bez okna**: dwuklik `Oferty.vbs` (start serwera + bota),
  `Zatrzymaj serwer.vbs` (stop).
- Dane w bazie `otodom.db` (tabele `oferty`, `discord_sent`, `app_settings`, `users`).
- **Git**: repozytorium zainicjowane; `discord_config.json` i `otodom.db` poza repo.
- **Logowanie** (`auth.py`, `login.html`): jedno konto (login + hasło, pbkdf2),
  sesje w ciasteczku `HttpOnly`. Bez zalogowania `/` przekierowuje na `/login`.
- **Kryteria** (`criteria.js`, panel w `oferty.html`): cena maks., cena/m² maks.,
  min. pokoi, powierzchnia min/maks, miasta, typ. Lista pokazuje **tylko pasujące**
  z przełącznikiem „Pokaż wszystkie".
- **Harmonogram** (`scheduler.py`, panel w `oferty.html`): wątek w tle pobiera co
  10–15 min (min. 10), konfigurowalny (włącz/wyłącz, częstotliwość, miasta, opcja
  wysyłki na Discord); pokazuje czas ostatniego cyklu i ewentualny błąd.
- Oferty na stronie pochodzą teraz **z bazy** (`GET /api/offers`) — harmonogram
  i ręczne „Pobierz" zapisują do bazy, strona czyta z bazy.

## 🧪 Testy
- `python -m unittest discover -s tests -v` — 10 testów (store, auth, scheduler).
- `node tests/criteria.test.mjs` — test logiki dopasowania kryteriów.

Plan wdrożenia: `docs/superpowers/plans/2026-06-15-scheduler-auth-criteria.md`
Specyfikacja: `docs/superpowers/specs/2026-06-15-scheduler-auth-criteria-design.md`

## ▶️ Pierwsze uruchomienie po zmianach
1. Uruchom `Oferty.vbs` (albo `python server.py`) i wejdź na `http://localhost:8000`.
2. Przy pierwszym wejściu pojawi się ekran **„Utwórz konto"** — ustaw login i hasło.
3. Po zalogowaniu skonfiguruj panele **Kryteria** i **Harmonogram**.

## 🔒 Bezpieczeństwo — HTTP vs HTTPS
Aplikacja działa po **HTTP**, ale serwer nasłuchuje wyłącznie na pętli zwrotnej
(`ThreadingHTTPServer(("127.0.0.1", PORT), ...)` w `server.py`). Ruch **nie opuszcza
komputera**, więc nie da się go podsłuchać z sieci — dla lokalnej, jednoosobowej
aplikacji HTTP jest tu w porządku (HTTPS chroni dane *w drodze przez sieć*, a takiej
drogi tu nie ma).

Co już chroni dostęp:
- hasło: pbkdf2-HMAC-SHA256, 200 000 iteracji, sól per-konto (w bazie tylko hash);
- ciasteczko sesji: `HttpOnly` + `SameSite=Lax`, token = 32 losowe bajty;
- brak flagi `Secure` jest **celowy** — wymagałaby HTTPS i zablokowała logowanie na `localhost`.

⚠️ **Kiedy trzeba dodać HTTPS** — dopiero gdy aplikacja wyjdzie poza `localhost`:
- zmiana bindowania na `0.0.0.0` lub udostępnienie w sieci/Wi-Fi,
- port-forwarding / wystawienie na świat,
- uruchamianie na **współdzielonym** komputerze (inny użytkownik OS może wejść na `127.0.0.1:8000`).

Wtedy: postaw reverse-proxy z TLS (np. Caddy/nginx) i ustaw flagę `Secure` na ciasteczku.
Świadomie pominięte (projekt do nauki, lokalnie): token CSRF (łagodzi `SameSite=Lax`),
trwałość sesji (giną przy restarcie serwera — to cecha, nie luka).
