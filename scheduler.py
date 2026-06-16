# -*- coding: utf-8 -*-
"""Harmonogram cyklicznego pobierania (wątek w tle uruchamiany przez server.py)."""
import time, threading
import store

MIN_INTERVAL = 10  # minut — nie częściej

CITY_WOJ = {"Poznań": "wielkopolskie", "Kraków": "małopolskie",
            "Warszawa": "mazowieckie", "Gdańsk": "pomorskie"}


def clamp_interval(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return MIN_INTERVAL
    return max(MIN_INTERVAL, n)


def should_run(cfg, now_epoch):
    if not cfg.get("enabled"):
        return False
    last = cfg.get("last_run")
    if not last:
        return True
    return (now_epoch - float(last)) >= clamp_interval(cfg.get("interval_min")) * 60


def run_cycle(server_module):
    """Jeden przebieg: scrapuje miasta z konfiguracji, zapisuje do bazy,
    opcjonalnie wysyła na Discord. Aktualizuje last_run/last_error."""
    cfg = store.get_settings("scheduler")
    error = None
    try:
        for miasto in cfg.get("cities", []):
            woj = CITY_WOJ.get(miasto, "")
            _url, offers = server_module.scrape(woj, miasto)
            store.save_offers(offers)
            if cfg.get("discord_autosend"):
                import discord_send
                discord_send.send_city(miasto, offers)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        print("[scheduler] błąd:", error)
    cfg["last_run"] = time.time()
    cfg["last_error"] = error
    store.save_settings("scheduler", cfg)


def scheduler_loop(server_module, stop_event):
    while not stop_event.is_set():
        try:
            cfg = store.get_settings("scheduler")
            if should_run(cfg, time.time()):
                print("[scheduler] uruchamiam cykl…")
                run_cycle(server_module)
        except Exception as e:
            print("[scheduler] pętla błąd:", e)
        stop_event.wait(30)  # sprawdzaj co 30 s


def start(server_module):
    stop_event = threading.Event()
    t = threading.Thread(target=scheduler_loop, args=(server_module, stop_event),
                         daemon=True, name="scheduler")
    t.start()
    return stop_event
