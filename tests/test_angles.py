"""تست‌های Angle Selection: انتخاب زاویه بر اساس metadata و keywords."""

import sys
import os
import unittest
from datetime import date

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

    def test_release_anniversary_takes_priority(self):
        cand = make_candidate(rating=9.0, vote_count=5000, year=2005,
                              _anniversary_today=True, _anniversary_years=21)
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 8))
        self.assertEqual(result.angle, "release_anniversary")
        self.assertEqual(result.reasons[0], "سالگرد اکران: 21 سال پیش در چنین روزی")

    def test_release_anniversary_not_chosen_otherwise(self):
        cand = self.engine
        normal = make_candidate(rating=9.0, vote_count=5000, year=2005,
                                _anniversary_today=False)
        result = self.engine.choose(normal, keywords=[], today=date(2026, 9, 8))
        self.assertNotEqual(result.angle, "release_anniversary")

    def test_director_birthday_takes_priority(self):
        cand = make_candidate(rating=9.0, vote_count=5000, year=2005,
                              director="نیکولاس کیج", _birthday_today=True)
        result = self.engine.choose(cand, keywords=[], today=date(2026, 1, 7))
        self.assertEqual(result.angle, "director_birthday")
        self.assertIn("تولد", result.reasons[0])

    def test_director_birthday_not_chosen_otherwise(self):
        normal = make_candidate(rating=9.0, vote_count=5000, year=2005,
                                _birthday_today=False)
        result = self.engine.choose(normal, keywords=[], today=date(2026, 9, 8))
        self.assertNotEqual(result.angle, "director_birthday")

    def test_today_defaults_to_real_today(self):
        cand = make_candidate(trending=False, rating=6.5, vote_count=500, year=2000)
        result = self.engine.choose(cand, keywords=[])
        self.assertEqual(result.angle, "genre_recommendation")

    # -- weekend_recommendation (فقط جمعه/شنبه) و mood_based --

    @staticmethod
    def _light_candidate(**overrides):
        # کاندیدایی که به هیچ rule قبلی نرسد (جز weekend/mood)
        base = dict(rating=7.6, vote_count=1500, tmdb_id=500, year=2000,
                    director=None, runtime=None, popularity=10.0,
                    genres=[18], genre_names_fa=["درام"])
        base.update(overrides)
        return make_candidate(**base)

    def test_weekend_recommendation_on_saturday(self):
        cand = self._light_candidate(genres=[18])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 19))
        self.assertEqual(result.angle, "weekend_recommendation")

    def test_weekend_recommendation_on_friday(self):
        cand = self._light_candidate(genres=[18])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 18))
        self.assertEqual(result.angle, "weekend_recommendation")

    def test_weekend_not_on_weekday(self):
        cand = self._light_candidate(genres=[18])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 15))
        self.assertNotEqual(result.angle, "weekend_recommendation")

    def test_weekend_requires_min_rating(self):
        cand = self._light_candidate(rating=7.0, genres=[18])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 19))
        self.assertNotEqual(result.angle, "weekend_recommendation")

    def test_mood_based_for_romance(self):
        cand = self._light_candidate(genres=[10749], genre_names_fa=["عاشقانه"])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 15))
        self.assertEqual(result.angle, "mood_based")

    def test_mood_based_rejects_drama(self):
        cand = self._light_candidate(genres=[18], genre_names_fa=["درام"])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 15))
        self.assertNotEqual(result.angle, "mood_based")

    def test_mood_based_requires_min_rating(self):
        cand = self._light_candidate(rating=7.0, genres=[10749], genre_names_fa=["عاشقانه"])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 15))
        self.assertNotEqual(result.angle, "mood_based")

    def test_weekend_beats_mood_based_priority(self):
        # کمدی با امتیاز کافی: آخر هفته اولویت بیشتری از mood_based دارد
        cand = self._light_candidate(genres=[35], genre_names_fa=["کمدی"])
        result = self.engine.choose(cand, keywords=[], today=date(2026, 9, 19))
        self.assertEqual(result.angle, "weekend_recommendation")


if __name__ == "__main__":
    unittest.main()