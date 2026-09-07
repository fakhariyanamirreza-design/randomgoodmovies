"""تست‌های Content Builder: ساخت کپشن از روی قالب‌ها و angleها."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.angles import AngleEngine  # noqa: E402
from src.content import ContentBuilder  # noqa: E402
from src.content import format_runtime_fa, keywords_to_hashtags  # noqa: E402
from tests.helpers import base_config, make_candidate  # noqa: E402


class ContentBuilderTests(unittest.TestCase):
    def setUp(self):
        self.config = base_config()
        self.builder = ContentBuilder(self.config)
        self.angles = AngleEngine(self.config)

    def test_runtime_formatting(self):
        self.assertEqual(format_runtime_fa(90), "1 ساعت و 30 دقیقه")
        self.assertEqual(format_runtime_fa(60), "1 ساعت")
        self.assertEqual(format_runtime_fa(45), "45 دقیقه")
        self.assertIsNone(format_runtime_fa(0))

    def test_keywords_to_hashtags(self):
        result = keywords_to_hashtags(["Inception", "Dream Heist", "Sci-fi!"])
        self.assertIn("#Inception", result)
        self.assertIn("#Dream_Heist", result)
        self.assertIn("#Scifi", result)

    def test_caption_contains_title_and_rating(self):
        cand = make_candidate(title_fa="وردپرس", rating=8.2, year=2010)
        angle = self.angles.choose(cand, keywords=["drama"])
        caption = self.builder.build(cand, angle, ["عاشقانه"], director_en="Denis Villeneuve",
                                     director_imdb_id="nm0898288")
        self.assertIn("وردپرس", caption)
        self.assertIn("8.2", caption)
        self.assertIn("2010", caption)

    def test_hidden_gem_template_used(self):
        cand = make_candidate(rating=8.2, vote_count=1000, tmdb_id=999)
        angle = self.angles.choose(cand, keywords=[])
        self.assertEqual(angle.angle, "hidden_gem")
        caption = self.builder.build(cand, angle, ["drama"], director_en=None,
                                     director_imdb_id=None)
        self.assertIn("گوهر پنهان", caption)

    def test_empty_fields_are_skipped(self):
        cand = make_candidate(title_fa="", overview_fa="", runtime=None,
                              director=None, imdb_id=None, genres=[], genre_names_fa=[])
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        # بلاک‌های وابسته به مقدار خالی نباید نمایش داده شوند
        self.assertNotIn("کارگردان", caption)
        self.assertNotIn("ژانر:", caption)

    def test_caption_not_exceeding_max_chars(self):
        cand = make_candidate(overview_fa="x" * 1000)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, ["tag"] * 20, director_en=None,
                                     director_imdb_id=None)
        self.assertLessEqual(len(caption), 1024)


if __name__ == "__main__":
    unittest.main()