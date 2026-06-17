# -*- coding: utf-8 -*-
"""Logowanie: hasło haszowane (pbkdf2). Jedno konto.

Dwa tryby (wybierane automatycznie):
  • lokalnie — konto trzymane w bazie SQLite (rejestracja przez stronę),
  • na Vercelu — konto z zmiennych środowiskowych APP_USERNAME / APP_PASSWORD
    (filesystem chmury jest ulotny, więc konta nie da się tam zapisać na stałe).

Sesje są BEZSTANOWE (podpisane ciasteczko), więc działają też na Vercelu, gdzie
każde żądanie może trafić na świeżą instancję serwera.
"""
import os, sqlite3, hashlib, secrets, time, hmac, base64, json

BASE = os.path.dirname(os.path.abspath(__file__))
# Na Vercelu zapisywać można tylko w /tmp (i to ulotnie); lokalnie obok skryptu.
DB = os.environ.get("OTODOM_DB") or os.path.join(
    "/tmp" if os.environ.get("VERCEL") else BASE, "otodom.db")

# Konto przez zmienne środowiskowe (tryb chmury).
ENV_USER = os.environ.get("APP_USERNAME")
ENV_PASS = os.environ.get("APP_PASSWORD")

# Klucz do podpisywania sesji. Na Vercelu ustaw SESSION_SECRET (stały),
# żeby zalogowanie przetrwało uśpienie serwera. Lokalnie wystarczy losowy.
SESSION_SECRET = (os.environ.get("SESSION_SECRET") or secrets.token_hex(32)).encode("utf-8")
SESSION_TTL = 7 * 24 * 3600  # 7 dni


def _env_mode():
    return bool(ENV_USER and ENV_PASS)


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
    if _env_mode():
        return True
    con = _con()
    row = con.execute("SELECT COUNT(*) FROM users").fetchone()
    con.close()
    return row[0] > 0


def get_username():
    if _env_mode():
        return ENV_USER
    con = _con()
    row = con.execute("SELECT username FROM users ORDER BY id LIMIT 1").fetchone()
    con.close()
    return row[0] if row else None


def create_account(username, password):
    if _env_mode():
        raise RuntimeError("Konto jest skonfigurowane przez zmienne środowiskowe.")
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
    if _env_mode():
        return (secrets.compare_digest(username or "", ENV_USER)
                and secrets.compare_digest(password or "", ENV_PASS))
    con = _con()
    row = con.execute("SELECT pass_hash, salt FROM users WHERE username=?", (username,)).fetchone()
    con.close()
    if not row:
        return False
    return verify_password(password, row[0], row[1])


# --- Sesje bezstanowe (podpisane ciasteczko) ---------------------------------

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload: str) -> str:
    return _b64e(hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).digest())


def create_session(username):
    payload = _b64e(json.dumps({"u": username, "exp": time.time() + SESSION_TTL}).encode("utf-8"))
    return payload + "." + _sign(payload)


def session_user(token):
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        data = json.loads(_b64d(payload))
    except Exception:
        return None
    if float(data.get("exp", 0)) < time.time():
        return None
    return data.get("u")


def delete_session(token):
    # Sesja jest bezstanowa — wylogowanie realizujemy przez wyczyszczenie
    # ciasteczka w odpowiedzi HTTP (patrz server.py: /api/logout).
    pass
