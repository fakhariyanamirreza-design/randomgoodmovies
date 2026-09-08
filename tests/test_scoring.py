"""تست‌های Encoding: کیفیت، امتیازدهی و تفکیک معیارها."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.scoring import ScoringEngine  # noqa: E402
from src.history import HistoryMemory  # noqa: E402
from tests.helpers import base_config, base_history, make_candidate  # noqa: E402


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.config = base_config()
        self.history = base_history()
        self.mem = HistoryMemory(self.history, self.config)
        self.engine = ScoringEngine(self.config, self.mem)

    def test_novelty_punishes_published(self):
        published = make_candidate(tmdb_id=1)
        fresh = make_candidate(tmdb_id=2)
        hist = base_history([
            {"id": 1},
        ])
        mem = HistoryMemory(hist, self.config)
        engine = ScoringEngine(self.config, mem)
        t1, _ = engine.score_one(published)
        t2, _ = engine.score_one(fresh)
        self.assertGreater(t2, t1)

    def test_quality_reflects_rating_and_votes(self):
        high = make_candidate(rating=9.0, vote_count=9000)
        low = make_candidate(rating=6.5, vote_count=100)
        t_high, _ = self.engine.score_one(high)
        t_low, _ = self.engine.score_one(low)
        self.assertGreater(t_high, t_low)

    def test_breakdown_sum_equals_total(self):
        t, breakdown = self.engine.score_one(make_candidate())
        self.assertAlmostEqual(t, sum(breakdown.values()), places=5)

    def test_surprise_bonus_for_obscure_quality(self):
        obscure = make_candidate(rating=8.5, vote_count=500, tmdb_id=99)
        famous = make_candidate(rating=8.5, vote_count=8000, tmdb_id=100)
        mem = HistoryMemory(self.history, self.config)
        engine = ScoringEngine(self.config, mem)
        _, b_ob = engine.score_one(obscure)
        _, b_fa = engine.score_one(famous)
        # سهم surprise برای فیلم کم‌شناخته‌شده بیشتر است (کیفیت بالا ولی رأی کم)
        self.assertGreater(b_ob.get("surprise", 0), b_fa.get("surprise", 0))

    def test_trending_boost(self):
        trending = make_candidate(tmdb_id=10, trending=True)
        normal = make_candidate(tmdb_id=11, trending=False)
        t_tr, b_tr = self.engine.score_one(trending)
        t_no, b_no = self.engine.score_one(normal)
        self.assertGreater(t_tr, t_no)
        self.assertGreater(b_tr.get("trending", 0), 0)
        self.assertEqual(b_no.get("trending", 0), 0)

    def test_ranked_sorted_desc(self):
        c1 = make_candidate(rating=9.0, vote_count=9000, tmdb_id=1, title_fa="A")
        c2 = make_candidate(rating=6.0, vote_count=50, tmdb_id=2, title_fa="B")
        ranked = self.engine.score_many([c2, c1])
        scores = [r[0] for r in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()