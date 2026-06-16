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
