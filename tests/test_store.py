# tests/test_store.py
import os, tempfile, unittest
import store

class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store.DB = os.path.join(self.tmp, "t.db")  # przekieruj bazę na tymczasową

    def test_settings_defaults_when_absent(self):
        crit = store.get_settings("criteria")
        self.assertEqual(crit["owner_type"], "any")
        self.assertIsNone(crit["price_max"])

    def test_settings_roundtrip(self):
        store.save_settings("scheduler", {"enabled": True, "interval_min": 15,
            "cities": ["Poznań"], "discord_autosend": False,
            "last_run": None, "last_error": None})
        got = store.get_settings("scheduler")
        self.assertTrue(got["enabled"])
        self.assertEqual(got["cities"], ["Poznań"])

    def test_save_and_read_offers(self):
        n = store.save_offers([{
            "otodom_id": 1, "miasto": "Poznań", "title": "Test",
            "price": 500000.0, "currency": "PLN", "ppm": 10000.0,
            "area": 50.0, "rooms": "2", "private": False,
            "location": "Ul. X, Poznań, wielkopolskie",
            "url": "https://x/oferta/test-ID1",
        }])
        self.assertEqual(n, 1)
        offers = store.read_offers()
        self.assertEqual(len(offers), 1)
        o = offers[0]
        self.assertEqual(o["wojewodztwo"], "wielkopolskie")
        self.assertEqual(o["rooms"], "2")
        self.assertEqual(o["miasto"], "Poznań")

import store as _store_mod

class StoreSupabaseSettingsTest(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.upserts = []
        store_mod = _store_mod
        self._orig = store_mod.db
        class FakeDb:
            @staticmethod
            def enabled():
                return True
            @staticmethod
            def select(table, columns="*", order=None, filters=None):
                return list(self.rows)
            @staticmethod
            def upsert(table, rows, on_conflict, ignore_duplicates=False):
                self.upserts.append({"table": table, "rows": rows,
                                     "on_conflict": on_conflict})
        store_mod.db = FakeDb

    def tearDown(self):
        _store_mod.db = self._orig

    def test_get_settings_merges_defaults(self):
        import json
        self.rows = [{"value": json.dumps({"interval_min": 30})}]
        cfg = _store_mod.get_settings("scheduler")
        self.assertEqual(cfg["interval_min"], 30)
        self.assertIn("cities", cfg)  # z DEFAULTS

    def test_get_settings_empty_returns_defaults(self):
        self.rows = []
        cfg = _store_mod.get_settings("criteria")
        self.assertEqual(cfg, _store_mod.DEFAULTS["criteria"])

    def test_save_settings_upserts_with_key_conflict(self):
        import json
        self._save = _store_mod.save_settings("criteria", {"price_max": 500000})
        self.assertEqual(len(self.upserts), 1)
        up = self.upserts[0]
        self.assertEqual(up["table"], "app_settings")
        self.assertEqual(up["on_conflict"], "key")
        row = up["rows"][0]
        self.assertEqual(row["key"], "criteria")
        self.assertEqual(json.loads(row["value"])["price_max"], 500000)

if __name__ == "__main__":
    unittest.main()
