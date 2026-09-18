"""تست‌های پست لیست ماهانه (اسلأم ۵): روتاسیون، ساخت کپشن، انتشار و ثبت نوع جداگانه + آمار (اسلأم ۴)."""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main as main_module  # noqa: E402
from src.persistence import load_history  # noqa: E402


def make_ml_config(enabled=True, size=10, months_back=1):
    return {
        "quotes": {"enabled": True},
        "posting": {"channel_footer": "📢 @test"},
        "monthly_list": {
            "enabled": enabled,
            "size": size,
            "title": "۱۰ فیلم برتر ماه گذشته",
            "rating_weight": 0.7,
            "vote_weight": 0.3,
            "vote_count_reference": 5000,
            "months_back": months_back,
            "max_caption_length": 1800,
        },
    }


def _entry(i, day, rating, votes, title="فیلم", poster="/p.jpg", status="published"):
    return {
        "id": i, "title_fa": f"{title} {i}", "title_en": f"F{i}",
        "year": 2000 + i, "poster": poster,
        "posted_at": f"2026-08-{day:02d}T10:00:00+00:00",
        "status": status, "rating": rating, "vote_count": votes,
        "selected_score": 50 + i, "profile": "درام‌های جایزه‌گرفته",
        "genres": [18], "genre_names_fa": ["درام"], "director": "ویلنوو", "era": "2010s",
    }


class ShiftMonthTests(unittest.TestCase):
    def test_shift_month(self):
        self.assertEqual(main_module.shift_month(date(2026, 1, 15), -1), "2025-12")
        self.assertEqual(main_module.shift_month(date(2026, 3, 1), -1), "2026-02")
        self.assertEqual(main_module.shift_month(date(2026, 9, 18), -1), "2026-08")
        self.assertEqual(main_module.shift_month(date(2026, 9, 18), 0), "2026-09")


class DecideMonthlyTests(unittest.TestCase):
    def test_decide_monthly_list_when_due(self):
        cfg = make_ml_config(enabled=True)
        history = {"quotes_posted": [], "posted": [], "monthly_lists": []}
        self.assertEqual(main_module.decide_run_content(cfg, history, today=date(2026, 9, 6)),
                         "monthly_list")

    def test_decide_not_monthly_when_disabled(self):
        cfg = make_ml_config(enabled=False)
        history = {"quotes_posted": [], "posted": [], "monthly_lists": []}
        self.assertEqual(main_module.decide_run_content(cfg, history, today=date(2026, 9, 6)),
                         "quote")

    def test_decide_not_monthly_when_already_posted(self):
        cfg = make_ml_config(enabled=True)
        history = {"quotes_posted": [], "posted": [],
                   "monthly_lists": [{"year_month": "2026-08"}]}
        self.assertEqual(main_module.decide_run_content(cfg, history, today=date(2026, 9, 6)),
                         "quote")

    def test_ignore_monthly_falls_through(self):
        cfg = make_ml_config(enabled=True)
        history = {"quotes_posted": [], "posted": [], "monthly_lists": []}
        self.assertEqual(main_module.decide_run_content(cfg, history, today=date(2026, 9, 6),
                                                        ignore_monthly=True), "quote")


class PublishMonthlyTests(unittest.TestCase):
    def _history(self):
        return {
            "posted": [
                _entry(3, 3, 9.0, 200),
                _entry(2, 2, 8.5, 5000),
                _entry(1, 1, 8.0, 100),
            ],
            "monthly_lists": [],
        }

    def test_publish_records_separate_type(self):
        class FakePublisher:
            def __init__(self):
                self.calls = []

            def send_photo(self, caption, poster, dry_run=False, photo_url=None):
                self.calls.append((caption, poster))
                return {"ok": True, "dry_run": True}

        pub = FakePublisher()
        history = self._history()
        ok = main_module.publish_monthly_list(None, pub, make_ml_config(),
                                              history, dry_run=True, today=date(2026, 9, 6))
        self.assertTrue(ok)
        self.assertEqual(len(history["monthly_lists"]), 1)
        rec = history["monthly_lists"][0]
        self.assertEqual(rec["type"], "monthly_list")
        self.assertEqual(rec["year_month"], "2026-08")
        self.assertEqual(rec["message_id"], "(dry-run)")
        self.assertEqual(rec["count"], 3)

        caption, poster = pub.calls[0]
        self.assertEqual(poster, "/p.jpg")
        # ترتیب بر اساس امتیاز editorial: فیلم 2 (8.5/5000) > فیلم 3 (9.0/200) > فیلم 1 (8.0/100)
        self.assertLess(caption.index("فیلم 2 (2002)"), caption.index("فیلم 3 (2003)"))
        self.assertLess(caption.index("فیلم 3 (2003)"), caption.index("فیلم 1 (2001)"))
        self.assertIn("۱۰ فیلم برتر ماه گذشته", caption)
        self.assertIn("📢 @test", caption)

    def test_publish_size_limit(self):
        class FakePublisher:
            def send_photo(self, caption, poster, dry_run=False, photo_url=None):
                return {"ok": True, "dry_run": True}

        history = self._history()
        ok = main_module.publish_monthly_list(None, FakePublisher(),
                                              make_ml_config(size=2),
                                              history, dry_run=True, today=date(2026, 9, 6))
        self.assertTrue(ok)
        self.assertEqual(history["monthly_lists"][0]["count"], 2)

    def test_publish_false_when_no_posts_in_target_month(self):
        class FakePublisher:
            def send_photo(self, *a, **k):
                return {"ok": True, "dry_run": True}

        history = {"posted": [], "monthly_lists": []}
        ok = main_module.publish_monthly_list(None, FakePublisher(),
                                              make_ml_config(),
                                              history, dry_run=True, today=date(2026, 9, 6))
        self.assertFalse(ok)
        self.assertEqual(history["monthly_lists"], [])

    def test_publish_false_when_disabled(self):
        history = {"posted": [], "monthly_lists": []}
        ok = main_module.publish_monthly_list(None, None, make_ml_config(enabled=False),
                                              history, dry_run=True, today=date(2026, 9, 6))
        self.assertFalse(ok)


class PersistenceMonthlyTests(unittest.TestCase):
    def test_load_history_has_monthly_lists(self):
        h = load_history(os.path.join(os.path.dirname(__file__), "no_such_history.json"))
        self.assertIn("monthly_lists", h)
        self.assertEqual(h["monthly_lists"], [])

    def test_editorial_metric_fallback_to_score(self):
        from main import editorial_metric
        cfg = make_ml_config()["monthly_list"]
        self.assertAlmostEqual(
            editorial_metric({"rating": 8.0, "vote_count": 5000}, cfg),
            0.7 * 0.8 + 0.3 * 1.0, places=5)
        self.assertAlmostEqual(
            editorial_metric({"rating": None, "selected_score": 80}, cfg),
            0.7 * 0.8, places=5)
        self.assertEqual(editorial_metric({"rating": None, "selected_score": None}, cfg), 0.0)


if __name__ == "__main__":
    unittest.main()