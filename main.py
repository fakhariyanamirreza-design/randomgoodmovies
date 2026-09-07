#!/usr/bin/env python3
"""
Autonomous Movie Content System
سیستم خودمختار تولید و انتشار محتوای سینمایی؛ بدون LLM، بدون سرویس پولی، فقط rule-based.

گردش کار:
Discover → Filter → Score → Analyze History → Select → Choose Angle → Generate Content
→ Quality Check → Publish → Save Memory
"""

import os
import sys
from datetime import datetime, timezone

from src.angles import AngleEngine
from src.content import ContentBuilder
from src.discovery import CandidateDiscovery
from src.editorial import EditorialEngine
from src import explain
from src.history import HistoryMemory
from src.persistence import load_json, load_history, save_history
from src.publisher import TelegramPublisher
from src.quality import QualityGate
from src.scoring import ScoringEngine
from src.tmdb_client import TMDbClient, TMDbError

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
HISTORY_PATH = os.environ.get("HISTORY_PATH", "data/posted.json")


def get_env_or_exit():
    missing = [name for name, val in [
        ("TMDB_API_KEY", os.environ.get("TMDB_API_KEY")),
        ("TELEGRAM_BOT_TOKEN", os.environ.get("TELEGRAM_BOT_TOKEN")),
        ("TELEGRAM_CHANNEL_ID", os.environ.get("TELEGRAM_CHANNEL_ID")),
    ] if not val]
    if missing:
        explain.eprint(f"متغیرهای محیطی زیر تنظیم نشده‌اند: {', '.join(missing)}")
        sys.exit(1)


def save_history_safe(history, path):
    """ذخیره‌ی history با error handling: اگر ذخیره شکست خورد، لاگ روشن بده ولی crashing نکند."""
    try:
        save_history(path, history)
        return True
    except OSError as exc:
        explain.eprint(f"هشدار: ذخیره‌ی history شکست خورد: {exc}")
        return False


def record_history(history, cand, breakdown, total, angle_decision, caption, poster_path, status):
    entry = {
        "id": cand.get("tmdb_id"),
        "title": cand.get("title_fa") or cand.get("title_en"),
        "title_fa": cand.get("title_fa"),
        "title_en": cand.get("title_en"),
        "year": cand.get("year"),
        "profile": cand.get("profile") or cand.get("profile_key"),
        "genres": cand.get("genres") or [],
        "genre_names_fa": cand.get("genre_names_fa") or [],
        "director": cand.get("director"),
        "era": cand.get("era"),
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "selected_score": round(total, 2),
        "score_breakdown": {k: round(v, 2) for k, v in breakdown.items()},
        "editorial_angle": angle_decision.angle,
        "angle_reasons": angle_decision.reasons,
        "caption": caption,
        "poster": poster_path,
        "status": status,
    }
    history["posted"].append(entry)
    return entry


def build_attempt(client, angles, content, quality, cand):
    """برای یک کاندیدا: keywords → angle → caption.
    برمی‌گرداند (caption, angle_decision, keywords)."""
    try:
        keywords = client.movie_keywords(cand.get("tmdb_id"))
    except TMDbError:
        keywords = []

    angle_decision = angles.choose(cand, keywords)

    director_en = None
    director_imdb_id = None
    if cand.get("director_id"):
        director_en = client.person_english_name(cand["director_id"])
        director_imdb_id = client.person_imdb_id(cand["director_id"])

    caption = content.build(cand, angle_decision, keywords, director_en, director_imdb_id)
    return caption, angle_decision, keywords


def main():
    get_env_or_exit()

    config = load_json(CONFIG_PATH, {})
    history = load_history(HISTORY_PATH)
    dry_run = bool(config.get("posting", {}).get("dry_run", False))

    explain.print_header("Autonomous Movie Content System")
    if dry_run:
        explain.print_message("DRY-RUN: اجرای شبیه‌سازی‌شده — هیچ پستی به تلگرام فرستاده نمی‌شود.")

    client = TMDbClient(os.environ["TMDB_API_KEY"], config.get("tmdb", {}))
    discovery = CandidateDiscovery(client, config, history)
    history_mem = HistoryMemory(history, config)
    scoring = ScoringEngine(config, history_mem)
    editorial = EditorialEngine(config, history_mem)
    angles = AngleEngine(config)
    content = ContentBuilder(config)
    quality = QualityGate(config)
    publisher = TelegramPublisher(
        os.environ.get("TELEGRAM_BOT_TOKEN"),
        os.environ.get("TELEGRAM_CHANNEL_ID"),
        config,
    )

    # --- Discover ---
    candidates, _excluded, stats = discovery.discover()
    candidates = [c for c in candidates if c.get("overview_fa")]

    explain.print_stats(stats.get("discovered", 0), len(candidates))

    if not candidates:
        explain.print_no_candidate("هیچ کاندیدایی با خلاصه‌ی فارسی معتبر پیدا نشد.")
        sys.exit(0)

    # --- History summary ---
    explain.print_recent_history(history_mem.summary())

    # --- Score ---
    ranked = scoring.score_many(candidates)
    top_n = config.get("weighted_selection", {}).get("top_n", 5)
    explain.print_top_candidates(ranked, top_n)

    # --- Editorial decision + fallbacks ---
    primary, ordered_survivors = editorial.enforce(ranked, top_n=top_n)
    if not ordered_survivors:
        explain.print_no_candidate("همه‌ی کاندیداهای برتر به دلیل محدودیت‌های تنوع رد شدند.")
        sys.exit(0)

    explain.print_selection(primary[2], primary[0], primary[1],
                            primary[3] or ["انتخاب بر اساس امتیاز و تنوع"],
                            None)  # angle بعداً برای منتخب چاپ می‌شود

    published_title = None
    for idx, (total, breakdown, cand, reasons) in enumerate(ordered_survivors):
        caption, angle_decision, keywords = build_attempt(client, angles, content, quality, cand)

        qr = quality.check(cand, caption)
        if not qr.passed:
            print(f"\nکاندیدا: {cand.get('title_fa') or cand.get('title_en')}")
            explain.print_quality(qr)
            print("گیت کیفیت رد شد؛ امتحان کاندیدای بعدی...")
            continue

        # زاویه‌ی منتخب نهایی را چاپ کن
        if idx == 0:
            print("\nEditorial angle:")
            print(f"  {angle_decision.angle}")
            for reason in angle_decision.reasons:
                print(f"  - {reason}")

        print(f"\nکاندیدا: {cand.get('title_fa') or cand.get('title_en')}")
        explain.print_quality(qr)

        try:
            resp = publisher.send_photo(caption, cand.get("poster_path"), dry_run=dry_run)
            msg_id = ""
            if isinstance(resp, dict):
                if resp.get("dry_run"):
                    msg_id = "(dry-run)"
                elif resp.get("result"):
                    msg_id = f"(message_id={resp['result'].get('message_id', '?')})"
            explain.print_publish_status(True, msg_id)
        except Exception as exc:
            explain.eprint(f"انتشار به تلگرام شکست خورد: {exc}")
            explain.print_publish_status(False)
            record_history(history, cand, breakdown, total, angle_decision,
                           caption, cand.get("poster_path"), "publish_failed")
            save_history_safe(history, HISTORY_PATH)
            print("وضعیت publish_failed در تاریخچه ثبت شد تا در اجرای بعدی تکرار نشود.")
            continue

        record_history(history, cand, breakdown, total, angle_decision,
                       caption, cand.get("poster_path"), "published")
        save_history_safe(history, HISTORY_PATH)
        published_title = cand.get("title_fa") or cand.get("title_en")
        explain.print_memory_status()
        break

    if published_title is None:
        explain.print_no_candidate("گیت کیفیت برای همه‌ی کاندیداها شکست خورد یا انتشار تلگرام ناموفق بود.")
        sys.exit(0)

    print(f"\nمنتشر شد: {published_title}")


if __name__ == "__main__":
    main()