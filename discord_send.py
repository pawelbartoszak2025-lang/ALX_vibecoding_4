# -*- coding: utf-8 -*-
"""Wysyłanie ofert na Discord przez REST API bota (bez dodatkowych bibliotek).

Logika:
  - kanał ma nazwę = slug miasta (np. "poznan");
  - przy pierwszym wysłaniu kanał jest tworzony, potem używany ponownie;
  - wysyłane są tylko oferty, których jeszcze nie było (dedup po URL w tabeli
    discord_sent w otodom.db) -> kolejne wysłania dokładają wyłącznie nowości.
"""
import os, re, json, time, sqlite3, unicodedata
import urllib.request, urllib.error
import db

API = "https://discord.com/api/v10"
BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(BASE, "discord_config.json")
# Na Vercelu zapisywać można tylko w /tmp (ulotnie); lokalnie obok skryptu.
DB = os.environ.get("OTODOM_DB") or os.path.join(
    "/tmp" if os.environ.get("VERCEL") else BASE, "otodom.db")
CLAY = 0xB8462B  # kolor paska embedu


def slug(s):
    s = (s or "").strip().lower().replace("ł", "l")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def load_config():
    # Tryb chmury (np. Vercel): brak pliku konfiguracyjnego -> token z env.
    if not os.path.exists(CONFIG):
        token = (os.environ.get("DISCORD_BOT_TOKEN")
                 or os.environ.get("Discord_bot_token") or "").strip()
        server_id = (os.environ.get("DISCORD_SERVER_ID") or "").strip()
        if not token:
            raise RuntimeError(
                "Brak tokenu bota. Ustaw zmienną środowiskową DISCORD_BOT_TOKEN.")
        return token, server_id
    with open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    raw = (cfg.get("bot_token") or "").strip()
    server_id = (cfg.get("server_id") or "").strip()
    # Pole bot_token to NAZWA zmiennej środowiskowej, w której trzymany jest
    # token (sekret nie leży w pliku). Dla zgodności wstecznej: jeśli ktoś
    # wkleił token wprost do pliku, użyj go bez zmian.
    token = (os.environ.get(raw) or "").strip()
    if not token and raw and raw != "Discord_bot_token":
        token = raw
    if not token:
        raise RuntimeError(
            f"Brak tokenu bota. Ustaw zmienną środowiskową '{raw or 'Discord_bot_token'}' "
            "z tokenem (albo wpisz token wprost w discord_config.json)."
        )
    return token, server_id


def _api(method, path, token, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": "Bot " + token,
        "Content-Type": "application/json",
        "User-Agent": "OfertyBot (lokalny, 1.0)",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if e.code == 401:
            raise RuntimeError("Token bota jest nieprawidłowy (401). Sprawdź discord_config.json.")
        if e.code == 403:
            raise RuntimeError("Bot nie ma uprawnień (403). Nadaj mu rolę z uprawnieniem "
                               "„Zarządzanie kanałami” / Administrator.")
        raise RuntimeError(f"Discord API {e.code}: {detail}")


def resolve_guild(token, server_id):
    guilds = _api("GET", "/users/@me/guilds", token)
    if not guilds:
        raise RuntimeError("Bot nie należy do żadnego serwera. Wpuść go przez link OAuth2 → Autoryzuj.")
    if server_id:
        for g in guilds:
            if str(g.get("id")) == server_id:
                return server_id
        raise RuntimeError("Bot nie jest na serwerze o podanym server_id (zostaw to pole puste = auto).")
    return str(guilds[0]["id"])


def find_or_create_channel(token, guild_id, name):
    channels = _api("GET", f"/guilds/{guild_id}/channels", token)
    for c in channels:
        if c.get("type") == 0 and c.get("name") == name:  # 0 = kanał tekstowy
            return c["id"], False
    created = _api("POST", f"/guilds/{guild_id}/channels", token, {"name": name, "type": 0})
    return created["id"], True


def _ensure_table(con):
    con.execute("""CREATE TABLE IF NOT EXISTS discord_sent (
        miasto TEXT, url TEXT, sent_at TEXT, UNIQUE(miasto, url))""")


def filter_new(miasto, offers):
    if db.enabled():
        rows = db.select("discord_sent", columns="url",
                         filters={"miasto": "eq." + miasto})
        sent = {r["url"] for r in rows}
    else:
        con = sqlite3.connect(DB)
        _ensure_table(con)
        sent = {r[0] for r in con.execute(
            "SELECT url FROM discord_sent WHERE miasto=?", (miasto,))}
        con.close()
    seen, new = set(), []
    for o in offers:
        u = o.get("url")
        if u and u not in sent and u not in seen:
            seen.add(u)
            new.append(o)
    return new


def mark_sent(miasto, offers):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    if db.enabled():
        rows = [{"miasto": miasto, "url": o.get("url"), "sent_at": ts}
                for o in offers if o.get("url")]
        db.upsert("discord_sent", rows, on_conflict="miasto,url",
                  ignore_duplicates=True)
        return
    con = sqlite3.connect(DB)
    _ensure_table(con)
    for o in offers:
        con.execute("INSERT OR IGNORE INTO discord_sent (miasto, url, sent_at) VALUES (?,?,?)",
                    (miasto, o.get("url"), ts))
    con.commit()
    con.close()


def _money(n):
    return f"{int(n):,}".replace(",", " ")


def offer_embed(o):
    line = []
    if o.get("price") is not None:
        line.append(f"**{_money(o['price'])} {o.get('currency') or 'PLN'}**")
    else:
        line.append("**Cena: zapytaj** (inwestycja)")
    if o.get("area"):
        line.append(str(o["area"]).replace(".", ",") + " m²")
    if o.get("rooms"):
        line.append(str(o["rooms"]) + " pok.")
    desc = " · ".join(line)
    if o.get("ppm"):
        desc += f"\n{_money(o['ppm'])} {o.get('currency') or 'PLN'}/m²"
    if o.get("location"):
        desc += f"\n📍 {o['location']}"
    return {
        "title": (o.get("title") or "Oferta")[:250],
        "url": o.get("url"),
        "description": desc[:4000],
        "color": CLAY,
    }


def post_offers(token, channel_id, offers):
    # Discord: maks. 10 embedów w jednej wiadomości -> dzielimy na paczki.
    for i in range(0, len(offers), 10):
        chunk = offers[i:i + 10]
        _api("POST", f"/channels/{channel_id}/messages", token,
             {"embeds": [offer_embed(o) for o in chunk]})
        time.sleep(0.4)  # delikatnie pod limit zapytań


def send_city(miasto, offers):
    """Tworzy/odnajduje kanał #<miasto> i wysyła tylko nowe oferty."""
    token, server_id = load_config()
    name = slug(miasto)
    guild_id = resolve_guild(token, server_id)
    channel_id, created = find_or_create_channel(token, guild_id, name)
    new = filter_new(miasto, offers)
    if new:
        post_offers(token, channel_id, new)
        mark_sent(miasto, new)
    return {"channel": name, "created": created,
            "sent": len(new), "skipped": len(offers) - len(new)}


if __name__ == "__main__":
    # Szybki test konfiguracji: sprawdza token i serwer (nic nie wysyła).
    tok, sid = load_config()
    gid = resolve_guild(tok, sid)
    me = _api("GET", "/users/@me", tok)
    print(f"OK — bot: {me.get('username')} | guild_id: {gid}")
