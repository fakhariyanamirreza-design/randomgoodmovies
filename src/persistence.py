"""پایداری تاریخچه و memory روی JSON با schema سازگار و ارتقاپذیر."""

import copy
import os
import json


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return copy.deepcopy(default)
    return copy.deepcopy(default)


def save_json(path, data):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


DEFAULT_HISTORY = {
    "schema_version": 2,
    "posted": [],
    "monthly_lists": [],
    "meta": {
        "performance": {
            "enabled": False,
            "note": "Engagement واقعی تلگرام هنوز در دسترس نیست. این بخش placeholder است و فقط schema دارد."
        }
    },
}


def load_history(path):
    data = load_json(path, DEFAULT_HISTORY)
    if "posted" not in data:
        data["posted"] = []
    if "monthly_lists" not in data:
        data["monthly_lists"] = []
    if "meta" not in data:
        data["meta"] = {}
    if "performance" not in data["meta"]:
        data["meta"]["performance"] = {
            "enabled": False,
            "note": "Engagement واقعی تلگرام هنوز در دسترس نیست."
        }
    data["schema_version"] = data.get("schema_version", 2)
    normalize_entries(data)
    return data


def normalize_entries(data):
    """backward compatibility: ورودی‌های قدیمی (فقط id/title/profile/posted_at)
    به schema جدید mapping می‌شوند تا تحلیل حافظه نشکند."""
    for item in data.get("posted", []):
        if not isinstance(item, dict):
            continue
        item.setdefault("title_fa", item.get("title"))
        item.setdefault("title_en", item.get("title"))
        item.setdefault("genres", [])
        item.setdefault("genre_names_fa", [])
        item.setdefault("director", None)
        item.setdefault("era", None)
        item.setdefault("year", None)
        item.setdefault("rating", None)
        item.setdefault("vote_count", None)
        item.setdefault("popularity", None)
        item.setdefault("imdb_id", None)
        item.setdefault("selected_score", None)
        item.setdefault("score_breakdown", {})
        item.setdefault("editorial_angle", None)
        item.setdefault("status", "published")


def save_history(path, data):
    save_json(path, data)


def history_ids(history):
    return {item.get("id") for item in history.get("posted", []) if item.get("id") is not None}
