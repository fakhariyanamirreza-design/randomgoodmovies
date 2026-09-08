"""تست‌های Angle Selection: انتخاب زاویه بر اساس metadata و keywords."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.angles import AngleEngine  # noqa: E402
from tests.helpers import base_config, make_candidate  # noqa: E402


class AngleTests(unittest.TestCase):
    def setUp(self):
        self.config = base_config()
        self.engine = AngleEngine(self.config)

    def test_trending_now_when_trending(self):
        cand = make_candidate(rating=7.0, vote_count=100, trending=True, year=2015)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "trending_now")
        self.assertTrue(len(result.reasons) > 0)

    def test_highly_rated_picked_for_quality(self):
        cand = make_candidate(rating=9.0, vote_count=5000, year=2010)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "highly_rated")
        self.assertTrue(len(result.reasons) > 0)

    def test_hidden_gem_when_low_votes(self):
        cand = make_candidate(rating=8.2, vote_count=1000, tmdb_id=999, year=2010,
                              director=None)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "hidden_gem")

    def test_director_spotlight_when_high_rating(self):
        # vote_count بالا (>=3000) تا hidden_gem رد شود؛ director_spotlight برنده است
        cand = make_candidate(rating=8.0, vote_count=3500, year=2010,
                              director="تارانتینو")
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "director_spotlight")

    def test_award_recognition_when_keywords_match(self):
        # director=None تا director_spotlight گرفته نشود
        cand = make_candidate(rating=7.9, vote_count=2000, year=2010, director=None)
        result = self.engine.choose(cand, keywords=["cannes", "ocean"])
        self.assertEqual(result.angle, "award_recognition")

    def test_award_recognition_ignores_unrelated_keywords(self):
        cand = make_candidate(rating=7.9, vote_count=2000, year=2010, director=None)
        result = self.engine.choose(cand, keywords=["space", "alien"])
        self.assertNotEqual(result.angle, "award_recognition")

    def test_classic_when_old_year_and_not_highly_rated(self):
        # rating 7.9 < 8.3 → highly_rated و modern_classic و hidden_gem رد می‌شوند
        # director=None تا director_spotlight گرفته نشود
        cand = make_candidate(rating=7.9, vote_count=3000, year=1980, director=None)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "classic_recommendation")

    def test_short_runtime_picked(self):
        cand = make_candidate(rating=7.5, vote_count=3500, year=2000, runtime=85,
                              director=None)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "short_runtime")

    def test_default_angle_when_no_rule_matches(self):
        cand = make_candidate(rating=6.5, vote_count=500, year=2000)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "genre_recommendation")

    def test_influential_film_when_no_director_high_votes_popularity(self):
        # director=None → director_spotlight رد. vote>=3000 → hidden_gem رد. year=2000 → classic رد.
        cand = make_candidate(rating=7.9, vote_count=3500, year=2000,
                              popularity=25.0, director=None, runtime=None)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "influential_film")


if __name__ == "__main__":
    unittest.main()