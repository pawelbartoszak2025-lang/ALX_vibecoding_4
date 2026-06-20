# -*- coding: utf-8 -*-
"""Warstwa danych: ustawienia (JSON) oraz oferty w SQLite (otodom.db)."""
import os, json, sqlite3
import db

BASE = os.path.dirname(os.path.abspath(__file__))
# Na Vercelu zapisywać można tylko w /tmp (ulotnie); lokalnie obok skryptu.
DB = os.environ.get("OTODOM_DB") or os.path.join(
    "/tmp" if os.environ.get("VERCEL") else BASE, "otodom.db")

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
    data = dict(DEFAULTS.get(key, {}))
    if db.enabled():
        rows = db.select("app_settings", columns="value",
                         filters={"key": "eq." + key})
        if rows:
            data.update(json.loads(rows[0]["value"]))
        return data
    con = _con()
    row = con.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    con.close()
    if row:
        data.update(json.loads(row[0]))
    return data


def save_settings(key, data):
    merged = dict(DEFAULTS.get(key, {}))
    merged.update(data or {})
    if db.enabled():
        db.upsert("app_settings",
                  [{"key": key, "value": json.dumps(merged, ensure_ascii=False)}],
                  on_conflict="key")
        return merged
    con = _con()
    con.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
                (key, json.dumps(merged, ensure_ascii=False)))
    con.commit()
    con.close()
    return merged


def _row_to_offer(r):
    """Mapuje wiersz (SQLite Row lub dict z Supabase) na słownik oferty."""
    loc = r["location"] or ""
    woj = loc.split(",")[-1].strip() if "," in loc else ""
    raw_rooms = r["rooms"]
    rooms = ROOMS_MAP.get(raw_rooms, raw_rooms) if raw_rooms else None
    return {
        "miasto": r["miasto_wyszukiwania"], "wojewodztwo": woj,
        "title": r["title"], "price": r["price"], "currency": r["currency"] or "PLN",
        "ppm": r["price_per_m2"], "area": r["area_m2"], "rooms": rooms,
        "private": bool(r["is_private_owner"]), "location": loc, "url": r["url"],
    }


def save_offers(offers):
    if db.enabled():
        rows = [{
            "miasto_wyszukiwania": o.get("miasto"), "otodom_id": o.get("otodom_id"),
            "title": o.get("title"), "price": o.get("price"),
            "currency": o.get("currency") or "PLN", "price_per_m2": o.get("ppm"),
            "area_m2": o.get("area"),
            "rooms": str(o.get("rooms")) if o.get("rooms") is not None else None,
            "floor": None, "is_private_owner": bool(o.get("private")),
            "location": o.get("location"), "url": o.get("url"),
        } for o in offers]
        db.upsert("oferty", rows, on_conflict="otodom_id")
        return len(rows)
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
    if db.enabled():
        rows = db.select("oferty",
            columns="miasto_wyszukiwania,title,price,currency,price_per_m2,"
                    "area_m2,rooms,is_private_owner,location,url",
            order="miasto_wyszukiwania.asc,price.asc.nullslast")
        return [_row_to_offer(r) for r in rows]
    con = _con()
    con.row_factory = sqlite3.Row
    rows = con.execute("""SELECT miasto_wyszukiwania, title, price, currency,
        price_per_m2, area_m2, rooms, is_private_owner, location, url
        FROM oferty ORDER BY miasto_wyszukiwania, price IS NULL, price""").fetchall()
    con.close()
    return [_row_to_offer(r) for r in rows]
