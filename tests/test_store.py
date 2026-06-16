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

if __name__ == "__main__":
    unittest.main()
