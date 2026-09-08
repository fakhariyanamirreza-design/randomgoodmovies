"""تست‌های Editorial Engine: محدودیت‌های تنوع (hard/soft) و انتخاب نهایی."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.history import HistoryMemory  # noqa: E402
from src.editorial import EditorialEngine  # noqa: E402
from src.scoring import ScoringEngine  # noqa: E402
from tests.helpers import base_config, base_history, make_candidate  # noqa: E402


def _cand(tmdb_id, title, gen, profile, director, era, rating=8.2):
    return make_candidate(
        tmdb_id=tmdb_id, title_fa=title, genres=gen, genre_names_fa=gen,
        profile=profile, profile_key=profile, director=director, era=era, rating=rating,
    )


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.config = base_config()
        self.history = base_history()
        self.mem = HistoryMemory(self.history, self.config)

    def test_drama_overrepresented_blocked(self):
        # ۳ پست اخیر همگی درام
        posts = []
        for i in range(3):
            posts.append({
                "id": i, "title": f"F{i}", "genres": [18], "profile": "درام‌های جایزه‌گرفته",
                "director": "X", "era": "2010s",
            })
        history = base_history(posts)
        mem = HistoryMemory(history, self.config)
        scorer = ScoringEngine(self.config, mem)
        eng = EditorialEngine(self.config, mem)

        drama = _cand(100, "درام جدید", [18], "درام‌های جایزه‌گرفته", "A", "2010s")
        comedy = _cand(200, "کمدی جدید", [35], "کمدی‌های محبوب", "B", "2010s")
        ranked = scorer.score_many([drama, comedy])

        # hard limit ژانر=3. با ۳ درامِ قبلی، درام candidate هنوز hard عبور می‌کند (3 >= 3 رد می‌شود)
        primary, ordered = eng.enforce(ranked, top_n=2)
        self.assertIsNotNone(primary)
        self.assertEqual(primary[2]["tmdb_id"], 200, "باید کمدی انتخاب شود نه درامِ تکراری")

    def test_hard_limit_no_survivors_falls_back_to_soft(self):
        # همه‌ی candidates درام با کارگردان‌های مختلف؛ hard ژانر همه را رد کند
        posts = []
        for i in range(5):
            posts.append({
                "id": i, "title": f"F{i}", "genres": [18], "profile": f"P{i}",
                "director": f"Dir{i}", "era": "2010s",
            })
        history = base_history(posts)
        mem = HistoryMemory(history, self.config)
        scorer = ScoringEngine(self.config, mem)
        eng = EditorialEngine(self.config, mem)

        only_drama = _cand(100, "درام", [18], "P3", "D", "2010s")
        ranked = scorer.score_many([only_drama])
        primary, ordered = eng.enforce(ranked, top_n=1)
        # در صورت خالی‌بودن hard_survivors، soft limit انتخاب می‌کند
        self.assertIsNotNone(primary)

    def test_max_consecutive_profile(self):
        posts = [
            {"id": 1, "title": "F1", "genres": [28], "profile": "اکشن", "director": "X", "era": "2010s"},
            {"id": 2, "title": "F2", "genres": [28], "profile": "اکشن", "director": "X", "era": "2010s"},
        ]
        history = base_history(posts)
        mem = HistoryMemory(history, self.config)
        acc = make_candidate(tmdb_id=100, profile="اکشن", profile_key="اکشن")
        self.assertEqual(mem.consecutive_count("profile", "اکشن"), 2)

    def test_no_back_to_back_same_category_or_genre(self):
        # شبیه‌سازی اونجرز→اسپایدرمن: پست قبلی اکشن/ماجراجویی/علمی-تخیلی است
        posts = [{
            "id": 1, "title": "Avengers", "genres": [28, 12, 878],
            "profile": "اکشن مدرن پرامتیاز", "director": "Whedon", "era": "2010s",
        }]
        history = base_history(posts)
        mem = HistoryMemory(history, self.config)
        scorer = ScoringEngine(self.config, mem)
        eng = EditorialEngine(self.config, mem)

        blockbuster = _cand(10, "Spider-Man", [28, 12, 878], "اکشن مدرن پرامتیاز", "Watts", "2020s")
        drama = _cand(20, "یک درام متفاوت", [18], "درام‌های جایزه‌گرفته", "Villeneuve", "2010s")
        ranked = scorer.score_many([blockbuster, drama])

        primary, ordered = eng.enforce(ranked, top_n=2)
        self.assertIsNotNone(primary)
        self.assertEqual(primary[2]["tmdb_id"], 20,
                         "نباید پشت‌سرهم فیلمی هم‌دسته/هم‌ژانر با پست قبل انتخاب شود")

    def test_soft_fallback_penalizes_back_to_back(self):
        # همه‌ی کاندیداها هم‌ژانر با پست قبل؛ soft باید کم‌تخلف‌ترین را انتخاب کند
        posts = [{
            "id": 1, "title": "Prev", "genres": [28], "profile": "P1", "director": "X", "era": "2010s",
        }]
        history = base_history(posts)
        mem = HistoryMemory(history, self.config)
        scorer = ScoringEngine(self.config, mem)
        eng = EditorialEngine(self.config, mem)

        shares_genre = _cand(10, "A", [28, 35], "P2", "D2", "2010s", rating=9.0)
        different = _cand(20, "B", [18], "P3", "D3", "2000s", rating=8.0)
        ranked = scorer.score_many([shares_genre, different])

        primary, ordered = eng.enforce(ranked, top_n=2)
        self.assertIsNotNone(primary)
        self.assertEqual(primary[2]["tmdb_id"], 20)


if __name__ == "__main__":
    unittest.main()