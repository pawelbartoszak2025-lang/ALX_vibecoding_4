# tests/test_scheduler.py
import unittest, scheduler

class SchedulerLogicTest(unittest.TestCase):
    def test_clamp_interval(self):
        self.assertEqual(scheduler.clamp_interval(5), 10)
        self.assertEqual(scheduler.clamp_interval(10), 10)
        self.assertEqual(scheduler.clamp_interval(15), 15)
        self.assertEqual(scheduler.clamp_interval(None), 10)

    def test_should_run_disabled(self):
        cfg = {"enabled": False, "interval_min": 10, "last_run": None}
        self.assertFalse(scheduler.should_run(cfg, 1000))

    def test_should_run_first_time(self):
        cfg = {"enabled": True, "interval_min": 10, "last_run": None}
        self.assertTrue(scheduler.should_run(cfg, 1000))

    def test_should_run_respects_interval(self):
        cfg = {"enabled": True, "interval_min": 10, "last_run": 1000}
        self.assertFalse(scheduler.should_run(cfg, 1000 + 9 * 60))   # za wcześnie
        self.assertTrue(scheduler.should_run(cfg, 1000 + 10 * 60))   # czas minął

if __name__ == "__main__":
    unittest.main()
