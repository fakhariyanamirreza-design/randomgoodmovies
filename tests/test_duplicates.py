"""تست‌های Duplicate Detection و رفتار history حول تکرار."""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.persistence import history_ids, load_history, save_history, DEFAULT_HISTORY  # noqa: E402
from src.history import HistoryMemory  # noqa: E402
from tests.helpers import base_config, base_history  # noqa: E402

import tempfile


class DuplicateTests(unittest.TestCase):
    def test_history_ids_include_all_statuses(self):
        history = {
            "posted": [
                {"id": 1, "status": "published"},
                {"id": 2, "status": "publish_failed"},
                {"id": 3, "status": "draft"},
                {"id": None},
            ]
        }
        ids = history_ids(history)
        self.assertEqual(ids, {1, 2, 3})

    def test_is_published_any_status_blocked(self):
        history = base_history([
            {"id": 1, "status": "publish_failed"},
        ])
        mem = HistoryMemory(history, base_config())
        self.assertFalse(mem.is_published(2))
        self.assertTrue(mem.is_published(1), "حتی publish_failed هم نباید دوباره انتخاب شود")

    def test_save_and_reload_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "posted.json")
            data = base_history([{"id": 1, "title": "A"}])
            save_history(path, data)
            loaded = load_history(path)
            self.assertEqual(loaded["posted"][0]["id"], 1)

    def test_load_missing_file_gives_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            loaded = load_history(os.path.join(tmp, "nope.json"))
            self.assertIn("posted", loaded)
            self.assertEqual(loaded["schema_version"], DEFAULT_HISTORY["schema_version"])


if __name__ == "__main__":
    unittest.main()