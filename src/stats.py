"""آمار ساده از history (فقط مشاهده‌ی دستی — روی workflow تأثیر ندارد).

توزیع ژانر، دسته، کارگردان و دهه برای پنجره‌های زمانی اخیر (پیش‌فرض ۳۰ و ۷ روز).

استفاده:
    python -m src.stats                # از data/posted.json، خروجی روی ترمینال + data/stats_latest.json
    python -m src.stats masir.json     # از فایل دلخواه
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

from .common import GENRE_FA
from .persistence import load_history

DEFAULT_WINDOWS = (30, 7)


def _as_aware(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _in_window(item, limit_dt):
    try:
        dt = _as_aware(datetime.fromisoformat(str(item.get("posted_at", ""))))
    except (ValueError, TypeError):
        return False
    return dt >= limit_dt


def genre_names(entry):
    """نام‌های ژانر یک پست (genre_names_fa یا نگاشت id از GENRE_FA)."""
    names = entry.get("genre_names_fa") or []
    if names:
        return names
    return [GENRE_FA.get(g, str(g)) for g in (entry.get("genres") or [])]


def distribution(posts, keyfn):
    counts = {}
    for post in posts:
        for v in keyfn(post):
            if v is None:
                continue
            v = str(v).strip()
            if v:
                counts[v] = counts.get(v, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def compute_stats(history, windows=DEFAULT_WINDOWS):
    """محاسبه‌ی توزیع‌ها برای هر پنجره. برمی‌گرداند dict قابل ذخیره در JSON."""
    now = datetime.now(timezone.utc)
    stats = {}
    for days in windows:
        limit = now - timedelta(days=days)
        posts = [p for p in history.get("posted", [])
                 if (p.get("status") or "published") == "published" and _in_window(p, limit)]
        stats[str(days)] = {
            "count": len(posts),
            "genres": distribution(posts, genre_names),
            "categories": distribution(posts, lambda p: [p.get("profile")]),
            "directors": distribution(posts, lambda p: [p.get("director")]),
            "decades": distribution(posts, lambda p: [p.get("era")]),
        }
    return stats


def render_text(stats):
    lines = []
    for days, data in stats.items():
        lines.append(f"=== آخرین {days} روز ({data['count']} پست) ===")
        for label, key in [("ژانر", "genres"), ("دسته", "categories"),
                           ("کارگردان", "directors"), ("دهه", "decades")]:
            items = data[key]
            if items:
                lines.append("  " + label + ": " +
                             "، ".join(f"{k}: {v}" for k, v in items.items()))
            else:
                lines.append(f"  {label}: (خالی)")
    return "\n".join(lines)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path = argv[0] if argv else os.environ.get("HISTORY_PATH", "data/posted.json")
    history = load_history(path)
    stats = compute_stats(history)
    print(render_text(stats))

    out_path = os.environ.get("STATS_OUTPUT", "data/stats_latest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "windows": DEFAULT_WINDOWS,
            "stats": stats,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nذخیره شد: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())