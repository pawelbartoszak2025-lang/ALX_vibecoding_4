# -*- coding: utf-8 -*-
"""Warstwa danych: ustawienia (JSON) oraz oferty w SQLite (otodom.db)."""
import os, json, sqlite3

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "otodom.db")

ROOMS_MAP = {"ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
             "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9", "TEN": "10",
             "MORE": "10+"}

DEFAULTS = {
    "scheduler": {"enabled": False, "interval_min": 15, "cities": ["Poznań"],
                  "discord_autosend": False, "last_run": None, "last_error": None},
    "criteria": {"price_max": None, "ppm_max": None, "rooms_min": None,
                 "area_min": None, "area_max": None, "cities": [], "owner_type": "any"},
}


def _con():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("""CREATE TABLE IF NOT EXISTS oferty (
        id INTEGER PRIMARY KEY AUTOINCREMENT, miasto_wyszukiwania TEXT,
        otodom_id INTEGER, title TEXT, price REAL, currency TEXT,
        price_per_m2 REAL, area_m2 REAL, rooms TEXT, floor TEXT,
        is_private_owner INTEGER, location TEXT, url TEXT, UNIQUE(otodom_id))""")
    return con


def get_settings(key):
    con = _con()
    row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    con.close()
    data = dict(DEFAULTS.get(key, {}))
    if row:
        data.update(json.loads(row[0]))
    return data


def save_settings(key, data):
    merged = dict(DEFAULTS.get(key, {}))
    merged.update(data or {})
    con = _con()
    con.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
                (key, json.dumps(merged, ensure_ascii=False)))
    con.commit()
    con.close()
    return merged


def save_offers(offers):
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
    con = _con()
    con.row_factory = sqlite3.Row
    rows = con.execute("""SELECT miasto_wyszukiwania, title, price, currency,
        price_per_m2, area_m2, rooms, is_private_owner, location, url
        FROM oferty ORDER BY miasto_wyszukiwania, price IS NULL, price""").fetchall()
    con.close()
    out = []
    for r in rows:
        loc = r["location"] or ""
        woj = loc.split(",")[-1].strip() if "," in loc else ""
        raw_rooms = r["rooms"]
        rooms = ROOMS_MAP.get(raw_rooms, raw_rooms) if raw_rooms else None
        out.append({
            "miasto": r["miasto_wyszukiwania"], "wojewodztwo": woj,
            "title": r["title"], "price": r["price"], "currency": r["currency"] or "PLN",
            "ppm": r["price_per_m2"], "area": r["area_m2"], "rooms": rooms,
            "private": bool(r["is_private_owner"]), "location": loc, "url": r["url"],
        })
    return out
