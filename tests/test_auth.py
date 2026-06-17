# tests/test_auth.py
import os, tempfile, unittest
import auth

class AuthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        auth.DB = os.path.join(self.tmp, "t.db")

    def test_hash_verify(self):
        h, s = auth.hash_password("tajne123")
        self.assertTrue(auth.verify_password("tajne123", h, s))
        self.assertFalse(auth.verify_password("zle", h, s))

    def test_account_lifecycle(self):
        self.assertFalse(auth.account_exists())
        auth.create_account("pawel", "tajne123")
        self.assertTrue(auth.account_exists())
        self.assertEqual(auth.get_username(), "pawel")
        self.assertTrue(auth.verify_login("pawel", "tajne123"))
        self.assertFalse(auth.verify_login("pawel", "zle"))
        with self.assertRaises(Exception):
            auth.create_account("inny", "x")  # konto już istnieje

    def test_sessions(self):
        # Sesja bezstanowa: poprawny token rozwiązuje się na użytkownika.
        t = auth.create_session("pawel")
        self.assertEqual(auth.session_user(t), "pawel")
        # Token pusty/nieprawidłowy -> brak użytkownika.
        self.assertIsNone(auth.session_user("nieistnieje"))
        self.assertIsNone(auth.session_user(None))
        # Token z podmienionym podpisem -> odrzucony.
        payload, _sig = t.rsplit(".", 1)
        self.assertIsNone(auth.session_user(payload + ".zlypodpis"))

if __name__ == "__main__":
    unittest.main()
