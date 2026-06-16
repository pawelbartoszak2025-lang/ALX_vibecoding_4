# -*- coding: utf-8 -*-
"""Bot Discord ze slash-komendami: /poznan, /krakow, /warszawa, /gdansk.

Po wpisaniu np. /poznan bot:
  1) pobiera 10 najnowszych ofert TĄ SAMĄ logiką co aplikacja (server.scrape),
  2) wysyła je na kanał #poznan (tworzy go przy pierwszym razie),
  3) pomija oferty już wcześniej wysłane (dedup w otodom.db).

Uruchamiany w tle przez Oferty.vbs. Wymaga: pip install discord.py
oraz tokenu w discord_config.json.
"""
import asyncio, socket
import discord
from discord import app_commands

import server          # istniejąca logika pobierania (scrape)
import discord_send    # wysyłka + tworzenie kanału + dedup

# slug komendy -> (nazwa miasta, województwo)
CITIES = {
    "poznan":   ("Poznań",   "wielkopolskie"),
    "krakow":   ("Kraków",   "małopolskie"),
    "warszawa": ("Warszawa", "mazowieckie"),
    "gdansk":   ("Gdańsk",   "pomorskie"),
}

intents = discord.Intents.default()      # tylko nieuprzywilejowane (Guilds) — wystarcza
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def make_callback(miasto, woj):
    async def callback(interaction: discord.Interaction):
        # Discord wymaga odpowiedzi w 3 s — najpierw "myślę…", potem właściwa praca.
        await interaction.response.defer(thinking=True, ephemeral=True)
        loop = asyncio.get_running_loop()
        try:
            # Operacje sieciowe (blokujące) puszczamy poza pętlę zdarzeń.
            _url, offers = await loop.run_in_executor(None, server.scrape, woj, miasto)
            res = await loop.run_in_executor(None, discord_send.send_city, miasto, offers)
            akcja = f"utworzono kanał #{res['channel']}" if res["created"] else f"kanał #{res['channel']}"
            msg = (f"✅ **{miasto}** — pobrano {len(offers)} najnowszych ofert.\n"
                   f"{akcja} · nowych wysłano: **{res['sent']}**, pominięto (już były): {res['skipped']}.")
        except Exception as e:
            msg = f"❌ Błąd dla {miasto}: {e}"
        await interaction.followup.send(msg, ephemeral=True)
    return callback


for slug_name, (miasto, woj) in CITIES.items():
    tree.add_command(app_commands.Command(
        name=slug_name,
        description=f"Pobierz i wyślij 10 najnowszych ofert: {miasto}",
        callback=make_callback(miasto, woj),
    ))


@client.event
async def on_ready():
    # Synchronizacja komend per-serwer = pojawiają się natychmiast (globalne do ~1h).
    total = 0
    for g in client.guilds:
        tree.copy_global_to(guild=g)
        cmds = await tree.sync(guild=g)
        total += len(cmds)
        print(f"Zsynchronizowano {len(cmds)} komend na serwerze: {g.name}")
    print(f"Bot zalogowany jako {client.user}. Komendy gotowe ({total}).")


def _single_instance():
    """Pilnuje, by działała tylko jedna kopia bota (blokada na lokalnym porcie)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 8765))
    except OSError:
        raise SystemExit(0)  # bot już działa — nic nie rób
    return s  # referencja musi żyć przez cały czas działania


if __name__ == "__main__":
    _guard = _single_instance()
    token, _server_id = discord_send.load_config()
    client.run(token)
