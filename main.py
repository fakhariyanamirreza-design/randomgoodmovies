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


def build_caption(details, profile_name, config):
    title = details.get("title") or details.get("original_title")
    year = (details.get("release_date") or "----")[:4]
    rating = details.get("vote_average", 0)
    genres = "، ".join(GENRE_FA.get(g["id"], g["name"]) for g in details.get("genres", []))

    director = ""
    for member in details.get("credits", {}).get("crew", []):
        if member.get("job") == "Director":
            director = member.get("name")
            break

    overview = details.get("overview") or ""
    max_chars = config["posting"].get("overview_max_chars", 320)
    if len(overview) > max_chars:
        overview = textwrap.shorten(overview, width=max_chars, placeholder="…")

    imdb_id = details.get("external_ids", {}).get("imdb_id")
    imdb_link = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None

    lines = [
        f"🎬 <b>{title}</b> ({year})",
        f"🗂 دسته: {profile_name}",
        f"⭐ امتیاز: {rating:.1f}/10",
    ]
    if genres:
        lines.append(f"🎭 ژانر: {genres}")
    if director:
        lines.append(f"🎬 کارگردان: {director}")
    if overview:
        lines.append(f"\n📝 {overview}")
    if imdb_link:
        lines.append(f"\n🔗 <a href=\"{imdb_link}\">صفحه فیلم در IMDB</a>")

    return "\n".join(lines)


def send_to_telegram(caption, poster_path, config):
    if not poster_path:
        raise RuntimeError("پوستری برای این فیلم پیدا نشد.")

    photo_url = f"https://image.tmdb.org/t/p/w1280{poster_path}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": config["posting"].get("telegram_parse_mode", "HTML"),
    }
    r = requests.post(url, data=payload, timeout=30)
    if not r.ok:
        raise RuntimeError(f"ارسال به تلگرام شکست خورد: {r.status_code} {r.text}")
    return r.json()


def main():
    missing = [name for name, val in [
        ("TMDB_API_KEY", TMDB_API_KEY),
        ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN),
        ("TELEGRAM_CHANNEL_ID", TELEGRAM_CHANNEL_ID),
    ] if not val]
    if missing:
        print(f"متغیرهای محیطی زیر تنظیم نشده‌اند: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    config = load_json(CONFIG_PATH, {})
    history = load_json(HISTORY_PATH, {"posted": []})
    history_ids = {item["id"] for item in history["posted"]}

    language = config["posting"].get("language", "fa-IR")
    fallback_language = config["posting"].get("fallback_language", "en-US")

    movie, profile_name = pick_movie(config, history_ids)
    if not movie:
        print("هیچ فیلم جدیدی با این پروفایل‌ها پیدا نشد (شاید همه قبلاً پابلیش شده‌اند).")
        sys.exit(0)

    details = get_movie_details(movie["id"], language)
    if not details.get("overview"):
        details = get_movie_details(movie["id"], fallback_language)

    caption = build_caption(details, profile_name, config)
    send_to_telegram(caption, details.get("poster_path"), config)

    history["posted"].append({
        "id": movie["id"],
        "title": details.get("title"),
        "profile": profile_name,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    })
    save_json(HISTORY_PATH, history)

    print(f"منتشر شد: {details.get('title')} (پروفایل: {profile_name})")


if __name__ == "__main__":
    main()
