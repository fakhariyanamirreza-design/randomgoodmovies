"""تست‌های Quality Gate: بررسی فیلدهای مناسب قبل از publish."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.quality import QualityGate  # noqa: E402
from tests.helpers import base_config, make_candidate  # noqa: E402


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.config = base_config()
        self.gate = QualityGate(self.config)

    def test_valid_candidate_passes(self):
        cand = make_candidate()
        result = self.gate.check(cand, caption="✅ caption")
        self.assertTrue(result.passed)

    def test_fails_without_overview(self):
        cand = make_candidate(overview_fa="", overview_en="")
        result = self.gate.check(cand, caption="caption")
        self.assertFalse(result.passed)
        self.assertTrue(any("overview" in e for e in result.errors))

    def test_fails_without_poster(self):
        cand = make_candidate(poster_path=None)
        result = self.gate.check(cand, caption="caption")
        self.assertFalse(result.passed)
        self.assertTrue(any("پوستر" in e for e in result.errors))

    def test_fails_with_low_rating(self):
        cand = make_candidate(rating=5.0)
        result = self.gate.check(cand, caption="caption")
        self.assertFalse(result.passed)
        self.assertTrue(any("امتیاز" in e for e in result.errors))

    def test_fails_without_title(self):
        cand = make_candidate(title_fa="")
        result = self.gate.check(cand, caption="caption")
        self.assertFalse(result.passed)
        self.assertTrue(any("عنوان" in e for e in result.errors))

    def test_caption_too_long_fails(self):
        cand = make_candidate()
        long_caption = "x" * 1100
        result = self.gate.check(cand, caption=long_caption)
        self.assertFalse(result.passed)
        self.assertTrue(any("کپشن" in e for e in result.errors))

    def test_valid_caption_passes(self):
        cand = make_candidate()
        result = self.gate.check(cand, caption="Some caption under 1024 chars.")
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()