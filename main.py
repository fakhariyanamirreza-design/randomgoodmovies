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
from datetime import date, datetime, timedelta, timezone

from src.angles import AngleEngine
from src.content import ContentBuilder
from src.discovery import CandidateDiscovery
from src.editorial import EditorialEngine
from src import explain
from src.history import HistoryMemory
from src.persistence import load_json, load_history, save_history
from src.publisher import TelegramPublisher
from src.quality import QualityGate
from src.quotes import QuoteEngine
from src.scoring import ScoringEngine
from src.tmdb_client import TMDbClient, TMDbError

CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
HISTORY_PATH = os.environ.get("HISTORY_PATH", "data/posted.json")
QUOTES_PATH = os.environ.get("QUOTES_PATH", "data/movie_quotes.json")


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


def record_history(history, cand, breakdown, total, angle_decision, caption, poster_path, status,
                   message_id=None):
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
    if status == "published" and message_id:
        entry["message_id"] = message_id
    history["posted"].append(entry)
    return entry


def build_attempt(client, angles, content, quality, cand, reasons=None, today=None):
    """برای یک کاندیدا: keywords → رویدادهای تاریخ‌محور → angle → caption.
    برمی‌گرداند (caption, angle_decision, keywords)."""
    try:
        keywords = client.movie_keywords(cand.get("tmdb_id"))
    except TMDbError:
        keywords = []

    today = today or date.today()

    # رویدادهای تاریخ‌محور (ایده ۸): سالگرد اکران و تولد کارگردان
    rdate = None
    try:
        rd = cand.get("release_date") or ""
        if rd:
            rdate = date.fromisoformat(rd[:10])
    except ValueError:
        rdate = None
    cand["_anniversary_today"] = bool(rdate and (rdate.month, rdate.day) == (today.month, today.day))
    cand["_anniversary_years"] = today.year - rdate.year if (rdate and cand["_anniversary_today"]) else None

    birthday = None
    if cand.get("director_id"):
        try:
            birthday = client.person_birthday(cand["director_id"])
        except Exception:
            birthday = None
    cand["_director_birthday"] = birthday
    bdate = None
    try:
        if birthday:
            bdate = date.fromisoformat(birthday[:10])
    except ValueError:
        bdate = None
    cand["_birthday_today"] = bool(bdate and (bdate.month, bdate.day) == (today.month, today.day))

    if cand["_anniversary_today"]:
        cand["_occasion"] = f"🎂 امروز {cand['_anniversary_years']} سال از اکران این فیلم می‌گذرد."
    elif cand["_birthday_today"]:
        cand["_occasion"] = f"🎂 امروز تولد {cand.get('director') or 'کارگردان'} است."
    else:
        cand["_occasion"] = ""

    angle_decision = angles.choose(cand, keywords, today=today)

    director_en = None
    director_imdb_id = None
    if cand.get("director_id"):
        director_en = client.person_english_name(cand["director_id"])
        director_imdb_id = client.person_imdb_id(cand["director_id"])

    try:
        similar = client.movie_similar(cand.get("tmdb_id"), genres=cand.get("genres") or [])
    except Exception:
        similar = []

    caption = content.build(cand, angle_decision, keywords, director_en, director_imdb_id,
                            similar=similar, reasons=reasons)
    return caption, angle_decision, keywords


def trailer_post_link(config, message_id):
    """لینک مستقیم پستِ تریلهرونده: t.me/<handle>/<message_id> (مناسب کانال عمومی)."""
    handle = config.get("trailer", {}).get("channel_handle")
    if not handle:
        cid = str(os.environ.get("TELEGRAM_CHANNEL_ID", "")).strip()
        if cid.startswith("@"):
            handle = cid[1:]
        elif cid.isdigit():
            number = cid.lstrip("-100")
            handle = f"c/{number}"
        else:
            handle = ""
    return f"https://t.me/{handle}/{message_id}" if handle else ""


def build_trailer_caption(config, entry, trailer_key, post_link):
    """کپشن پست تریلر: نام فیلم، لینک پست معرفی، لینک تریلر و footer."""
    tcfg = config.get("trailer", {})
    footer = config.get("posting", {}).get("channel_footer") or ""
    template = tcfg.get("caption") or [
        "🎬 تریلر فیلم {title_fa}",
        "",
        "📄 پست معرفی فیلم: {post_link}",
        "🎬 تماشای تریلر: {trailer_url}",
        "",
        "{footer}",
    ]
    values = {
        "title_fa": entry.get("title_fa") or entry.get("title") or "",
        "title_en": entry.get("title_en") or "",
        "post_link": (f"<a href='{post_link}'>مشاهده پست</a>" if post_link else "در دسترس نیست"),
        "trailer_url": f"<a href='https://www.youtube.com/watch?v={trailer_key}'>YouTube</a>",
        "footer": footer,
    }
    lines = []
    for line in template:
        try:
            rendered = line.format(**values)
        except (KeyError, IndexError, ValueError):
            continue
        lines.append(rendered)
    return "\n".join(lines).strip()


def publish_pending_trailers(client, publisher, config, history, now=None):
    """تری‌لر پست‌های قدیمی‌تر از `after_days` روز را به‌صورت پست جدا منتشر می‌کند.

    تاریخچه را درجا آپدیت می‌کند (trailer_posted_at / trailer_skipped)؛ ذخیره با caller.
    برمی‌گرداند تعداد تری‌لرِ منتشرشده.
    """
    tcfg = config.get("trailer", {})
    if not tcfg.get("enabled", True):
        return 0
    after_days = int(tcfg.get("after_days", 1))
    max_per_run = int(tcfg.get("max_per_run", 1))
    dry_run = bool(config.get("posting", {}).get("dry_run", False))
    now = now or datetime.now(timezone.utc)

    pending = []
    for entry in history.get("posted", []):
        if entry.get("status") != "published" or not entry.get("message_id"):
            continue
        if entry.get("trailer_posted_at") or entry.get("trailer_skipped"):
            continue
        posted_at = None
        try:
            posted_at = datetime.fromisoformat(entry.get("posted_at", ""))
        except (ValueError, TypeError):
            continue
        if posted_at and posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)
        if posted_at and now - posted_at >= timedelta(days=after_days):
            pending.append(entry)

    published = 0
    for entry in pending[:max_per_run]:
        trailer_key = client.movie_trailer(entry.get("id"))
        if not trailer_key:
            entry["trailer_skipped"] = "no_trailer"
            continue
        caption = build_trailer_caption(config, entry, trailer_key,
                                        trailer_post_link(config, entry.get("message_id")))
        try:
            resp = publisher.send_photo(caption, entry.get("poster"), dry_run=dry_run)
        except Exception as exc:
            explain.eprint(f"انتشار تری‌لر به تلگرام شکست خورد: {exc}")
            continue
        entry["trailer_posted_at"] = now.replace(microsecond=0).isoformat()
        if isinstance(resp, dict):
            if resp.get("dry_run"):
                entry["trailer_message_id"] = "(dry-run)"
            elif resp.get("result"):
                entry["trailer_message_id"] = resp["result"].get("message_id")
        explain.print_publish_status(True, f"تری‌لر: {entry.get('title_fa') or entry.get('title')}")
        published += 1
    return published


def publish_daily_quote(client, publisher, config, history, dry_run=False, today=None):
    """انتشار یک نقل قول سینمایی در روز (اگر امروز قبلاً منتشر نشده باشد)."""
    tcfg = config.get("quotes", {})
    if not tcfg.get("enabled", True):
        return False

    today = today or date.today()
    # اگر امروز قبلاً نقل قول منتشر شده، دوباره منتشر نمی‌کنیم
    quotes_posted = history.get("quotes_posted", [])
    for item in quotes_posted:
        posted_at = item.get("posted_at", "")
        try:
            if datetime.fromisoformat(posted_at).date() == today:
                return False
        except (ValueError, TypeError):
            continue

    quotes_path = os.environ.get("QUOTES_PATH", "data/movie_quotes.json")
    if not os.path.exists(quotes_path):
        return False

    qe = QuoteEngine(quotes_path, history)
    index, quote = qe.next_quote()
    if quote is None:
        return False

    footer = config.get("posting", {}).get("channel_footer") or ""
    photo_size = config.get("publisher", {}).get("photo_size", "w1280")
    backdrop_url = qe.get_backdrop_url(quote, client, photo_size=photo_size)
    if not backdrop_url:
        explain.eprint(f"نقل قول «{quote.get('movie')}» رد شد: عکس افقی پیدا نشد.")
        return False

    caption = qe.build_caption(quote, footer)

    try:
        resp = publisher.send_photo(caption, backdrop_url.split("/")[-1],
                                    dry_run=dry_run, photo_url=backdrop_url)
    except Exception as exc:
        explain.eprint(f"انتشار نقل قول شکست خورد: {exc}")
        return False

    message_id = None
    if isinstance(resp, dict):
        if resp.get("dry_run"):
            message_id = "(dry-run)"
        elif resp.get("result"):
            message_id = resp["result"].get("message_id")

    qe.record_published(index, message_id)
    explain.print_publish_status(True, f"نقل قول: {quote.get('movie')}")
    return True


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

    # --- Trailer posts: پست جدا برای تریلرِ پست‌های یک‌روز قدیمی‌تر ---
    published_trailers = publish_pending_trailers(client, publisher, config, history)
    if published_trailers:
        save_history_safe(history, HISTORY_PATH)

    # --- Daily quote: نقل قول سینمایی روزانه ---
    if publish_daily_quote(client, publisher, config, history, dry_run=dry_run):
        save_history_safe(history, HISTORY_PATH)

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
        caption, angle_decision, keywords = build_attempt(
            client, angles, content, quality, cand, reasons=reasons)

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

        real_message_id = None
        if isinstance(resp, dict) and not resp.get("dry_run") and resp.get("result"):
            real_message_id = resp["result"].get("message_id")
        record_history(history, cand, breakdown, total, angle_decision,
                       caption, cand.get("poster_path"), "published",
                       message_id=real_message_id)
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