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
from datetime import date, datetime, timezone

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
        "rating": cand.get("rating"),
        "vote_count": cand.get("vote_count"),
        "popularity": cand.get("popularity"),
        "imdb_id": cand.get("imdb_id"),
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

    trailer_url = None
    try:
        trailer_key = client.movie_trailer(cand.get("tmdb_id"))
        if trailer_key:
            trailer_url = f"https://www.youtube.com/watch?v={trailer_key}"
    except Exception:
        trailer_url = None

    caption = content.build(cand, angle_decision, keywords, director_en, director_imdb_id,
                            similar=similar, reasons=reasons, trailer_url=trailer_url)
    return caption, angle_decision, keywords


def quote_posted_today(history, today):
    """آیا امروز نقل‌قولی منتشر شده؟"""
    for item in history.get("quotes_posted", []):
        try:
            posted = datetime.fromisoformat(str(item.get("posted_at", "")))
            if posted.date() == today:
                return True
        except (ValueError, TypeError):
            continue
    return False


def movie_posted_today(history, today):
    """آیا امروز فیلمی منتشر شده؟"""
    for entry in history.get("posted", []):
        if entry.get("status") != "published":
            continue
        try:
            posted = datetime.fromisoformat(str(entry.get("posted_at", "")))
            if posted.date() == today:
                return True
        except (ValueError, TypeError):
            continue
    return False


def decide_run_content(config, history, today=None, ignore_monthly=False):
    """روتاسیون «هر اجرا فقط یک نوع پست»: اگر نوبت لیست ماهانه باشد، آن؛ وگرنه اگر
    نقل‌قول امروز هنوز نرفته نوبت نقل‌قول است؛ وگرنه نوبت فیلم. اگر هر دو رفته‌اند «none»."""
    today = today or date.today()
    if not ignore_monthly and monthly_list_due(config, history, today):
        return "monthly_list"
    quotes_on = config.get("quotes", {}).get("enabled", True)
    if quotes_on and not quote_posted_today(history, today):
        return "quote"
    if movie_posted_today(history, today):
        return "none"
    return "movie"


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

    year = qe.get_movie_year(quote, client)
    caption = qe.build_caption(quote, footer, year=year)

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


def shift_month(d, delta):
    """جابه‌جایی ماه: می‌گیرد date، برمی‌گرداند رشته‌ی 'YYYY-MM'."""
    raw = d.year * 12 + d.month - 1 + delta
    return f"{raw // 12:04d}-{raw % 12 + 1:02d}"


def monthly_target_month(today, months_back):
    return shift_month(today, -max(int(months_back or 1), 0))


def monthly_list_due(config, history, today=None):
    """لیست ماهانه فقط در «اولین اجرای ماه» (زمانی که لیستِ ماهِ هدف هنوز ثبت نشده)."""
    today = today or date.today()
    ml = config.get("monthly_list", {}) or {}
    if not ml.get("enabled", False):
        return False
    target = monthly_target_month(today, ml.get("months_back", 1))
    posted = {item.get("year_month") for item in history.get("monthly_lists", []) if item.get("year_month")}
    return target not in posted


def editorial_metric(entry, ml):
    """امتیاز editorial یک پست قبلی: rating+vote_count (یا fallback به selected_score)."""
    rating = entry.get("rating")
    vote_count = entry.get("vote_count")
    if rating is not None:
        rw = float(ml.get("rating_weight", 0.7))
        vw = float(ml.get("vote_weight", 0.3))
        ref = float(ml.get("vote_count_reference", 5000))
        rating_share = max(0.0, min(float(rating) / 10, 1.0))
        votes_share = max(0.0, min(float(vote_count or 0) / ref, 1.0))
        return rw * rating_share + vw * votes_share
    score = entry.get("selected_score")
    if score is not None:
        return 0.7 * max(0.0, min(float(score) / 100, 1.0))
    return 0.0


def _parse_posted_at(item):
    try:
        return datetime.fromisoformat(str(item.get("posted_at", "")))
    except (ValueError, TypeError):
        return None


def build_monthly_list_caption(config, top_entries, title=None, channel=None):
    """پست واحد «۱۰ فیلم برتر ماه گذشته»: لیست شماره‌دار + لینک به پست قبلی (در صورت امکان)."""
    ml = config.get("monthly_list", {}) or {}
    caption_lines = [f"<b>{title or ml.get('title', '۱۰ فیلم برتر ماه گذشته')}</b> 🔝", ""]
    handle = (channel or "").strip()
    for i, entry in enumerate(top_entries, 1):
        label = entry.get("title_fa") or entry.get("title_en") or "؟"
        year = entry.get("year")
        label = f"{label} ({year})" if year else label
        rating = entry.get("rating")
        star = f" ⭐ {float(rating):.1f}" if rating is not None else ""
        message_id = entry.get("message_id")
        if handle.startswith("@") and message_id:
            link = f"https://t.me/{handle[1:]}/{message_id}"
            caption_lines.append(f"{i}. <a href=\"{link}\">{label}</a>{star}")
        else:
            caption_lines.append(f"{i}. {label}{star}")
    caption_lines.append("")
    caption_lines.append(config.get("posting", {}).get("channel_footer") or "")
    return "\n".join(caption_lines)


def publish_monthly_list(client, publisher, config, history, dry_run=False, today=None):
    """پست ماهانه: ۱۰ فیلم برترِ منتشرشده در ماهِ هدف + پوستر فیلم اول.
    ثبت در history.monthly_lists به‌صورت جداگانه (نوع متمایز، نه posted)."""
    ml = config.get("monthly_list", {}) or {}
    if not ml.get("enabled", False):
        return False

    today = today or date.today()
    target = monthly_target_month(today, ml.get("months_back", 1))
    size = int(ml.get("size", 10))

    month_entries = []
    for entry in history.get("posted", []):
        if entry.get("status") != "published":
            continue
        posted = _parse_posted_at(entry)
        if posted and posted.strftime("%Y-%m") == target:
            month_entries.append(entry)

    if not month_entries:
        explain.eprint("لیست ماهانه: هیچ فیلمی در ماه هدف منتشر نشده بود.")
        return False

    scored = [(editorial_metric(e, ml), e) for e in month_entries]
    scored.sort(key=lambda x: (-x[0], _parse_posted_at(x[1]) or datetime.min, x[1].get("title", "")))
    top = [e for _, e in scored[:size]]

    poster_path = next((e.get("poster") for e in top if e.get("poster")), None)
    if not poster_path:
        explain.eprint("لیست ماهانه: هیچ پوستری در لیست برترها نبود.")
        return False

    caption = build_monthly_list_caption(
        config, top,
        channel=os.environ.get("TELEGRAM_CHANNEL_ID", ""))

    try:
        resp = publisher.send_photo(caption, poster_path, dry_run=dry_run)
    except Exception as exc:
        explain.eprint(f"انتشار لیست ماهانه شکست خورد: {exc}")
        return False

    message_id = None
    if isinstance(resp, dict):
        if resp.get("dry_run"):
            message_id = "(dry-run)"
        elif resp.get("result"):
            message_id = resp["result"].get("message_id")

    history.setdefault("monthly_lists", []).append({
        "type": "monthly_list",
        "year_month": target,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "message_id": message_id,
        "count": len(top),
    })
    explain.print_publish_status(True, f"لیست ماهانه: {target} ({len(top)} فیلم)")
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

    # --- روتاسیون: هر اجرا فقط یک نوع پست (صبح نقل‌قول، شب فیلم؛ اول لیست ماهانه) ---
    slot = decide_run_content(config, history)
    if slot == "monthly_list":
        explain.print_message("نوبت این اجرا: لیست ماهانه (پست فیلم/نقل‌قول به اجرای بعدی موکول شد).")
        if publish_monthly_list(client, publisher, config, history, dry_run=dry_run):
            save_history_safe(history, HISTORY_PATH)
            return
        explain.eprint("لیست ماهانه منتشر نشد؛ ادامه با روتاسیون عادی.")
        slot = decide_run_content(config, history, ignore_monthly=True)
    if slot == "quote":
        explain.print_message("نوبت این اجرا: نقل‌قول روزانه (پست فیلم به اجرای بعدی موکول شد).")
        if publish_daily_quote(client, publisher, config, history, dry_run=dry_run):
            save_history_safe(history, HISTORY_PATH)
        else:
            explain.eprint("نقل‌قول امروز منتشر نشد؛ این اجرا پستی ندارد.")
        return
    if slot == "none":
        explain.print_message("امروز نقل‌قول و فیلم هر دو منتشر شده‌اند؛ این اجرا پستی ندارد.")
        return

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