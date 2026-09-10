"""تست‌های Content Builder: ساخت کپشن از روی قالب‌ها و angleها."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.angles import AngleEngine  # noqa: E402
from src.content import ContentBuilder  # noqa: E402
from src.content import format_runtime_fa, keywords_to_hashtags  # noqa: E402
from tests.helpers import base_config, make_candidate  # noqa: E402


def _full_template_config():
    """config ای که قالب آن همه‌ی بلاک‌های اختیاری (teaser/why) را نیز دارد."""
    cfg = base_config()
    cfg["content"]["teaser_variants"] = [
        "حدس بزن این فیلم درباره‌ی چیه؟ 🧐",
        "اول حدس بزن، بعد بخون 👇",
    ]
    cfg["content"]["why_lines"] = {
        "trending_now": "چون همین حالا در ترند روز است 🌡️",
    }
    cfg["content"]["block_template"]["teaser_line"] = "{teaser_line}"
    cfg["content"]["block_template"]["why_line"] = "{why_line}"
    cfg["content"]["templates"]["genre_recommendation"] = [
        "title_fa", "title_en", "blank", "tagline", "trending_line",
        "occasion_line", "teaser_line",
        "blank", "category", "rating", "genres", "runtime", "country",
        "blank", "director_fa", "director_en", "blank", "overview",
        "blank", "similar_movies", "blank", "imdb_link", "audience_line",
        "blank", "hashtags", "blank", "why_line", "blank", "footer",
    ]
    return cfg


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
        self.assertIn("8.2", caption)

    def test_lead_sentence_removed(self):
        cand = make_candidate(rating=8.2)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertNotIn("گوهر پنهان", caption)
        self.assertNotIn("یک فیلم از", caption)

    def test_tagline_used_when_present(self):
        cand = make_candidate(tagline="Somewhere, something incredible is waiting to be known.")
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertIn("Somewhere, something incredible", caption)

    def test_tagline_skipped_when_missing(self):
        cand = make_candidate(tagline="")
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertNotIn("💬", caption)
        self.assertNotIn("«»", caption)

    def test_similar_movies_section_rendered(self):
        cand = make_candidate(title_fa="وردپرس")
        angle = self.angles.choose(cand, keywords=[])
        similar = [
            {"id": 1, "title": "Inception", "year": 2010},
            {"id": 2, "title": "Interstellar", "year": 2014},
            {"id": 3, "title": "The Prestige", "year": None},
        ]
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None,
                                     similar=similar)
        self.assertIn("فیلم‌های شبیه به این", caption)
        self.assertIn("Inception (2010)", caption)
        self.assertIn("Interstellar (2014)", caption)
        self.assertIn("The Prestige", caption)

    def test_similar_movies_section_hidden_when_empty(self):
        cand = make_candidate()
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None,
                                     similar=[])
        self.assertNotIn("فیلم‌های شبیه به این", caption)

    def test_trending_line_only_when_trending(self):
        trending = make_candidate(rating=8.5, vote_count=4000, trending=True)
        angle = self.angles.choose(trending, keywords=[])
        caption = self.builder.build(trending, angle, [], director_en=None,
                                     director_imdb_id=None)
        self.assertIn("فیلم‌های ترند روز TMDb", caption)
        self.assertIn("ترند", caption)

        normal = make_candidate(rating=8.5, vote_count=4000, trending=False)
        angle2 = self.angles.choose(normal, keywords=[])
        cap2 = self.builder.build(normal, angle2, [], director_en=None,
                                  director_imdb_id=None)
        self.assertNotIn("فیلم‌های ترند روز TMDb", cap2)

    def test_similar_header_is_bold_and_preceded_by_blank(self):
        cand = make_candidate(title_fa="وردپرس")
        angle = self.angles.choose(cand, keywords=[])
        similar = [{"id": 1, "title": "Inception", "year": 2010}]
        caption = self.builder.build(cand, angle, [], director_en=None,
                                     director_imdb_id=None, similar=similar)
        self.assertIn("<b>فیلم‌های شبیه به این:</b>", caption)
        lines = caption.split("\n")
        idx = next(i for i, l in enumerate(lines) if "فیلم‌های شبیه به این" in l)
        self.assertEqual(lines[idx - 1], "")
        self.assertEqual(lines[idx + 1], "• Inception (2010)")

    def test_empty_fields_are_skipped(self):
        cand = make_candidate(title_fa="", overview_fa="", runtime=None,
                              director=None, imdb_id=None, genres=[], genre_names_fa=[])
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        # بلاک‌های وابسته به مقدار خالی نباید نمایش داده شوند
        self.assertNotIn("کارگردان", caption)
        self.assertNotIn("ژانر:", caption)

    def test_genre_emoji_from_config(self):
        cand = make_candidate(genres=[28], genre_names_fa=["اکشن"], rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertIn("💥 <b>وردپرس</b>", caption)

    def test_genre_emoji_default_when_unknown(self):
        cand = make_candidate(genres=[9999], genre_names_fa=["عجیب"], rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertIn("🎬 <b>وردپرس</b>", caption)

    def test_title_has_flag_and_year(self):
        cand = make_candidate(countries_iso=["US"], countries_fa=["آمریکا"], rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertIn("<b>وردپرس</b> (2010) 🇺🇸", caption)

    def test_teaser_line_rotates_deterministically(self):
        cfg = _full_template_config()
        angles = AngleEngine(cfg)
        builder = ContentBuilder(cfg)
        a = angles.choose(make_candidate(tmdb_id=0, rating=8.5), keywords=[])
        b = angles.choose(make_candidate(tmdb_id=1, rating=8.5), keywords=[])
        c1 = builder.build(make_candidate(tmdb_id=0, rating=8.5), a, [], director_en=None,
                           director_imdb_id=None)
        c2 = builder.build(make_candidate(tmdb_id=0, rating=8.5), a, [], director_en=None,
                           director_imdb_id=None)
        c3 = builder.build(make_candidate(tmdb_id=1, rating=8.5), b, [], director_en=None,
                           director_imdb_id=None)
        self.assertEqual(c1, c2, "انتخاب تیزر باید قطعی باشد")
        self.assertNotEqual(c1.split("\n"), c3.split("\n"), "تیزر بین پست‌های مختلف باید بچرخد")

    def test_teaser_line_not_in_default_template(self):
        # پس از حذف تیزر از قالب پیش‌فرض هیچ تیزی نباید رندر شود
        cand = make_candidate(rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertNotIn("حدس بزن", caption)
        self.assertNotIn("بخون", caption)

    def test_teaser_absent_when_no_variants(self):
        cfg = _full_template_config()
        cfg["content"]["teaser_variants"] = []
        builder = ContentBuilder(cfg)
        angle = AngleEngine(cfg).choose(make_candidate(rating=8.5), keywords=[])
        caption = builder.build(make_candidate(rating=8.5), angle, [], director_en=None,
                                director_imdb_id=None)
        self.assertNotIn("حدس بزن", caption)

    def test_structured_hashtags(self):
        cand = make_candidate(genres=[18], genre_names_fa=["درام"], year=2010, era="2010s")
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, ["whatever"], director_en=None, director_imdb_id=None)
        self.assertIn("#درام #2010 #دهه_۲۰۱۰", caption)
        self.assertNotIn("#whatever", caption)

    def test_audience_line_from_top_similar(self):
        cand = make_candidate()
        angle = self.angles.choose(cand, keywords=[])
        similar = [{"id": 1, "title": "Inception", "year": 2010}]
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None,
                                     similar=similar)
        self.assertIn("🎯 اگر «Inception» را دوست داشتی، این فیلم همان حال و هواست.", caption)

    def test_why_line_from_angle_mapping(self):
        cfg = _full_template_config()
        cfg["content"]["why_lines"] = {
            "trending_now": "چون همین حالا در ترند روز است 🌡️",
        }
        builder = ContentBuilder(cfg)
        angle = AngleEngine(cfg).choose(make_candidate(rating=8.5, trending=True), keywords=[])
        self.assertEqual(angle.angle, "trending_now")
        caption = builder.build(make_candidate(rating=8.5, trending=True), angle, [],
                                director_en=None, director_imdb_id=None)
        self.assertIn("چون همین حالا در ترند روز است 🌡️", caption)

    def test_why_line_not_in_default_template(self):
        cand = make_candidate(rating=8.5, trending=True)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertNotIn("چون امتیاز", caption)
        self.assertNotIn("چون همین حالا", caption)

    def test_why_line_falls_back_to_reason(self):
        cfg = _full_template_config()
        cfg["content"]["why_lines"] = {}
        builder = ContentBuilder(cfg)
        cand = make_candidate(rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = builder.build(cand, angle, [], director_en=None, director_imdb_id=None,
                                reasons=["اولین دلیل", "دلیل دوم"])
        self.assertIn("اولین دلیل", caption)

    def test_why_line_skips_duplicate_reason(self):
        cfg = _full_template_config()
        cfg["content"]["why_lines"] = {}
        builder = ContentBuilder(cfg)
        cand = make_candidate(rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = builder.build(cand, angle, [], director_en=None, director_imdb_id=None,
                                reasons=["قبلاً منتشر نشده", "دلیل دوم"])
        self.assertIn("دلیل دوم", caption)

    def test_occasion_line_renders(self):
        cand = make_candidate(_occasion="🎂 امروز تولد کارگردانش است.", rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertIn("🎂 امروز تولد کارگردانش است.", caption)

    def test_occasion_line_absent_when_none(self):
        cand = make_candidate(rating=8.5)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertNotIn("🎂", caption)

    def test_audio_line_absent_when_no_similar(self):
        cand = make_candidate()
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, [], director_en=None, director_imdb_id=None,
                                     similar=[])
        self.assertNotIn("اگر", caption)

    def test_caption_not_exceeding_max_chars(self):
        cand = make_candidate(overview_fa="x" * 1000)
        angle = self.angles.choose(cand, keywords=[])
        caption = self.builder.build(cand, angle, ["tag"] * 20, director_en=None,
                                     director_imdb_id=None)
        self.assertLessEqual(len(caption), 1024)

    def test_overflow_keeps_layout_and_blocks(self):
        # کپشنی که ذاتاً از ۱۰۲۴ بیشتر باشد نباید flatten شود (مشکل پست 31)
        cand = make_candidate(
            overview_fa="ز" * 600,
            tagline="A very long tagline about movies and storytelling " * 3,
        )
        angle = self.angles.choose(cand, keywords=[])
        similar = [
            {"id": 1, "title": "The Lord of the Rings: The Return of the King", "year": 2003},
            {"id": 2, "title": "The Lord of the Rings: The Fellowship of the Ring", "year": 2001},
            {"id": 3, "title": "The Lord of the Rings: The Two Towers", "year": 2002},
        ]
        caption = self.builder.build(cand, angle, [], director_en=None,
                                     director_imdb_id=None, similar=similar)
        self.assertLessEqual(len(caption), 1024)
        self.assertIn("\n\n", caption, "خط خالی باید حفظ شود، نه این‌که همه‌چیز یک خط شود")
        self.assertGreater(len(caption.split("\n")), 5)
        self.assertIn("فیلم‌های شبیه به این", caption)
        self.assertIn("#درام", caption)
        self.assertIn("کانال تست", caption, "footer نباید با کوتاه‌کردن از بین برود")

    # بلاک‌های جدید هم config-driven هستند: اگر قالب خالی/حذف شد هیچ بلاکی نشکند
    def test_blocks_work_without_new_config_keys(self):
        cfg = base_config()
        builder = ContentBuilder(cfg)
        cand = make_candidate()
        angle = AngleEngine(cfg).choose(cand, keywords=[])
        caption = builder.build(cand, angle, [], director_en=None, director_imdb_id=None)
        self.assertIn("وردپرس", caption)
        self.assertNotIn("{", caption, "هیچ جای‌گزینه‌ی باز باید بماند")


if __name__ == "__main__":
    unittest.main()