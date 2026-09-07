#!/usr/bin/env python3
"""
ربات انتخاب و انتشار فیلم رندوم در کانال تلگرام.
منابع رایگان استفاده‌شده: TMDb API (اطلاعات فیلم و پوستر) + Telegram Bot API (انتشار).
هیچ سرویس پولی یا LLM پولی در این نسخه استفاده نشده؛ متن معرفی به صورت قالب (template) از روی
داده‌های واقعی TMDb ساخته می‌شود (فکت‌محور، طبق درخواست).
"""

import os
import re
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

COUNTRY_FA = {
    "US": "آمریکا", "GB": "بریتانیا", "FR": "فرانسه", "DE": "آلمان", "IT": "ایتالیا",
    "JP": "ژاپن", "KR": "کره جنوبی", "CN": "چین", "IN": "هند", "CA": "کانادا",
    "ES": "اسپانیا", "RU": "روسیه", "AU": "استرالیا", "BR": "برزیل", "MX": "مکزیک",
    "IR": "ایران", "TR": "ترکیه", "SE": "سوئد", "NO": "نروژ", "DK": "دانمارک",
    "NL": "هلند", "BE": "بلژیک", "CH": "سوئیس", "AT": "اتریش", "PL": "لهستان",
    "HK": "هنگ‌کنگ", "TW": "تایوان", "TH": "تایلند", "NZ": "نیوزیلند", "IE": "ایرلند",
    "AR": "آرژانتین", "PT": "پرتغال", "GR": "یونان", "EG": "مصر", "IL": "اسرائیل",
    "SA": "عربستان سعودی", "AE": "امارات", "FI": "فنلاند", "CZ": "چک", "HU": "مجارستان",
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
        data = tmdb_get(f"person/{person_id}/external_ids")
        return data.get("imdb_id")
    except requests.RequestException:
        return None


def get_person_english_name(person_id):
    try:
        data = tmdb_get(f"person/{person_id}", {"language": "en-US"})
        return data.get("name")
    except requests.RequestException:
        return None


def get_clean_poster_path(movie_id):
    """
    پوستر رسمی/بین‌المللی فیلم را برمی‌گرداند (بر اساس بیشترین امتیاز کاربران TMDb)،
    نه یک پوستر جایگزین با کیفیت پایین یا نسخه‌ی محلی‌سازی‌شده.
    """
    try:
        data = tmdb_get(f"movie/{movie_id}/images", {"include_image_language": "null,en"})
        posters = data.get("posters", [])
        if posters:
            best = max(posters, key=lambda p: p.get("vote_average", 0))
            return best.get("file_path")
    except requests.RequestException:
        pass
    return None


def get_movie_keywords(movie_id):
    try:
        data = tmdb_get(f"movie/{movie_id}/keywords")
        return [k["name"] for k in data.get("keywords", [])]
    except requests.RequestException:
        return []


def keywords_to_hashtags(keywords, limit=5):
    hashtags = []
    for name in keywords[:limit]:
        cleaned = re.sub(r"[^\w\s]", "", name, flags=re.UNICODE).strip()
        cleaned = re.sub(r"\s+", "_", cleaned)
        if cleaned:
            hashtags.append(f"#{cleaned}")
    return " ".join(hashtags)


def format_runtime_fa(minutes):
    if not minutes:
        return None
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return f"{hours} ساعت و {mins} دقیقه"
    if hours:
        return f"{hours} ساعت"
    return f"{mins} دقیقه"


def get_countries_fa(details):
    names = []
    for c in details.get("production_countries", []):
        code = c.get("iso_3166_1")
        names.append(COUNTRY_FA.get(code, c.get("name")))
    return names


DEFAULT_CAPTION_TEMPLATE = [
    "title_fa", "title_en",
    "tagline",
    "blank", "category", "rating", "genres", "runtime", "country",
    "blank", "director_fa", "director_en",
    "blank", "overview",
    "blank", "imdb_link",
    "blank", "keywords",
    "blank", "footer",
]


def build_caption(details_fa, details_en, keywords, profile_name, config):
    title_fa = details_fa.get("title") or details_fa.get("original_title")
    title_en = details_en.get("title") or details_en.get("original_title")
    year = (details_fa.get("release_date") or details_en.get("release_date") or "----")[:4]
    rating = details_fa.get("vote_average", 0)
    genres = "، ".join(GENRE_FA.get(g["id"], g["name"]) for g in details_fa.get("genres", []))

    tagline = details_fa.get("tagline") or details_en.get("tagline") or ""
    runtime_text = format_runtime_fa(details_fa.get("runtime") or details_en.get("runtime"))
    countries_fa = get_countries_fa(details_fa) or get_countries_fa(details_en)
    hashtags = keywords_to_hashtags(keywords)

    director_fa = ""
    director_person_id = None
    for member in details_fa.get("credits", {}).get("crew", []):
        if member.get("job") == "Director":
            director_fa = member.get("name")
            director_person_id = member.get("id")
            break

    director_en = get_person_english_name(director_person_id) if director_person_id else None
    director_imdb_id = get_person_imdb_id(director_person_id) if director_person_id else None

    director_line_fa = f"🎬 کارگردان: {director_fa}" if director_fa else None

    director_line_en = None
    if director_en and director_en != director_fa:
        if director_imdb_id:
            director_line_en = f"↳ <a href=\"https://www.imdb.com/name/{director_imdb_id}/\">{director_en}</a>"
        else:
            director_line_en = f"↳ {director_en}"
    elif director_fa and director_imdb_id:
        # اگه اسم انگلیسی جدا پیدا نشد، حداقل خود اسم فارسی رو لینک کن
        director_line_fa = f"🎬 کارگردان: <a href=\"https://www.imdb.com/name/{director_imdb_id}/\">{director_fa}</a>"

    overview = details_fa.get("overview") or details_en.get("overview") or ""
    max_chars = config["posting"].get("overview_max_chars", 320)
    if len(overview) > max_chars:
        overview = textwrap.shorten(overview, width=max_chars, placeholder="…")

    imdb_id = details_fa.get("external_ids", {}).get("imdb_id") or details_en.get("external_ids", {}).get("imdb_id")
    imdb_link = f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else None

    footer = config["posting"].get("channel_footer")

    # هر «بلاک» یک تکه از پیام است. اسم هرکدوم داخل caption_template در config.json
    # قابل استفاده‌ست تا ترتیب و فاصله‌ها رو خودت کنترل کنی، بدون نیاز به تغییر کد.
    # توجه: title_fa/title_en و director_fa/director_en عمداً در دو بلاک/خط جدا نگه داشته شده‌اند
    # تا فارسی و انگلیسی در یک خط قاطی نشوند (مشکل نمایش دوجهته/bidi).
    blocks = {
        "title_fa": f"🎬 <b>{title_fa}</b> ({year})" if title_fa else None,
        "title_en": f"↳ {title_en} ({year})" if title_en and title_en != title_fa else None,
        "tagline": f"💬 «{tagline}»" if tagline else None,
        "category": f"🗂 دسته: {profile_name}",
        "rating": f"⭐ امتیاز: {rating:.1f}/10",
        "genres": f"🎭 ژانر: {genres}" if genres else None,
        "runtime": f"⏱ مدت‌زمان: {runtime_text}" if runtime_text else None,
        "country": f"🌍 کشور سازنده: {'، '.join(countries_fa)}" if countries_fa else None,
        "director_fa": director_line_fa,
        "director_en": director_line_en,
        "overview": f"📝 {overview}" if overview else None,
        "imdb_link": f"🔗 <a href=\"{imdb_link}\">صفحه فیلم در IMDB</a>" if imdb_link else None,
        "keywords": hashtags if hashtags else None,
        "footer": footer if footer else None,
    }

    template = config["posting"].get("caption_template", DEFAULT_CAPTION_TEMPLATE)

    lines = []
    for key in template:
        if key == "blank":
            lines.append("")
            continue
        value = blocks.get(key)
        if value:
            lines.append(value)

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

    movie = None
    profile_name = None
    details_fa = None
    excluded_ids = set(history_ids)

    for _ in range(6):  # حداکثر ۶ بار تلاش برای پیدا کردن فیلمی با ترجمه‌ی فارسی معتبر
        candidate, candidate_profile = pick_movie(config, excluded_ids)
        if not candidate:
            break
        candidate_details_fa = get_movie_details(candidate["id"], language)
        if candidate_details_fa.get("overview"):
            movie, profile_name, details_fa = candidate, candidate_profile, candidate_details_fa
            break
        # این فیلم ترجمه‌ی فارسی نداشت؛ برای این دور کنارش بگذار و یکی دیگه امتحان کن
        excluded_ids.add(candidate["id"])

    if not movie:
        print("هیچ فیلمی با خلاصه‌داستان فارسی معتبر پیدا نشد (شاید همه قبلاً پابلیش شده‌اند یا ترجمه ندارند).")
        sys.exit(0)

    details_en = get_movie_details(movie["id"], fallback_language)

    # اولویت با پوستر رسمی خودِ TMDb (همون که در صفحه‌ی خود فیلم هم دیده می‌شود).
    # فقط اگر این پوستر وجود نداشت، سراغ بهترین پوستر جایگزین می‌رویم.
    poster_path = (
        details_en.get("poster_path")
        or details_fa.get("poster_path")
        or get_clean_poster_path(movie["id"])
    )

    keywords = get_movie_keywords(movie["id"])

    caption = build_caption(details_fa, details_en, keywords, profile_name, config)
    send_to_telegram(caption, poster_path, config)

    history["posted"].append({
        "id": movie["id"],
        "title": details_en.get("title") or details_fa.get("title"),
        "profile": profile_name,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    })
    save_json(HISTORY_PATH, history)

    print(f"منتشر شد: {details_en.get('title') or details_fa.get('title')} (پروفایل: {profile_name})")


if __name__ == "__main__":
    main()
