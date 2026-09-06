#!/usr/bin/env python3
"""
ربات انتخاب و انتشار فیلم رندوم در کانال تلگرام.
منابع رایگان استفاده‌شده: TMDb API (اطلاعات فیلم و پوستر) + Telegram Bot API (انتشار).
هیچ سرویس پولی یا LLM پولی در این نسخه استفاده نشده؛ متن معرفی به صورت قالب (template) از روی
داده‌های واقعی TMDb ساخته می‌شود (فکت‌محور، طبق درخواست).
"""

import os
import sys
import json
import random
import textwrap
from datetime import datetime, timezone

import requests

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID")  # e.g. @yourchannel or -100123456789

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
HISTORY_PATH = os.environ.get("HISTORY_PATH", "data/posted.json")

TMDB_BASE = "https://api.themoviedb.org/3"

GENRE_FA = {
    28: "اکشن", 12: "ماجراجویی", 16: "انیمیشن", 35: "کمدی", 80: "جنایی",
    99: "مستند", 18: "درام", 10751: "خانوادگی", 14: "فانتزی", 36: "تاریخی",
    27: "ترسناک", 10402: "موزیکال", 9648: "معمایی", 10749: "عاشقانه",
    878: "علمی-تخیلی", 10770: "تلویزیونی", 53: "هیجان‌انگیز", 10752: "جنگی",
    37: "وسترن",
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def tmdb_get(endpoint, params=None):
    params = params or {}
    params["api_key"] = TMDB_API_KEY
    r = requests.get(f"{TMDB_BASE}/{endpoint}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def discover_movies(profile, language, page):
    params = {
        "language": language,
        "sort_by": "popularity.desc",
        "include_adult": "false",
        "page": page,
    }
    for key in ("with_genres", "vote_average_gte", "vote_count_gte",
                "release_date_gte", "release_date_lte"):
        if key in profile:
            tmdb_param = key.replace("_gte", ".gte")
            params[tmdb_param] = profile[key]
    return tmdb_get("discover/movie", params)


def pick_movie(config, history_ids):
    profiles = config["profiles"]
    random.shuffle(profiles)

    for profile in profiles:
        # اول یک درخواست برای فهمیدن تعداد صفحات
        first = discover_movies(profile, config["posting"]["language"], 1)
        total_pages = min(first.get("total_pages", 1), 500) or 1
        if total_pages == 0:
            continue

        tried_pages = set()
        for _ in range(5):  # حداکثر ۵ بار تلاش با صفحات مختلف
            page = random.randint(1, total_pages)
            if page in tried_pages:
                continue
            tried_pages.add(page)

            data = first if page == 1 else discover_movies(profile, config["posting"]["language"], page)
            results = [m for m in data.get("results", []) if m["id"] not in history_ids]
            if results:
                movie = random.choice(results)
                return movie, profile["name"]

    return None, None


def get_movie_details(movie_id, language):
    details = tmdb_get(f"movie/{movie_id}", {
        "language": language,
        "append_to_response": "credits,external_ids",
    })
    return details


def get_person_imdb_id(person_id):
    try:
