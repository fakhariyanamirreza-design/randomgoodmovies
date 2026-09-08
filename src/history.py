"""آنالیز تاریخچه/حافظه: توزیع ژانر، کارگردان، دهه، پروفایل، آخرین استفاده و streakها.

همه‌چیز از listing استخراج می‌شود؛ تاريخچه‌ی JSON ساده برای این کار کافی است و پیچیدگی SQLite لازم نیست.
"""

from datetime import datetime, timezone


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_posted(history):
    return history.get("posted", [])


def recent_posts(history, window):
    return get_posted(history)[-window:]


def count_fields(posts, field):
    """شمارش فراوانی یک فیلد (ژانر/کارگردان/پروفایل/دهه) با پشتیبانی مقادیر لیستی."""
    counts = {}
    for item in posts:
        value = item.get(field)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v is None:
                continue
            counts[v] = counts.get(v, 0) + 1
    return counts


def counts_in_window(history, window, field="genres"):
    return count_fields(recent_posts(history, window), field)


def latest_use_dates(history, field="genres", now=None):
    """آخرین باری که هر مقدار استفاده شده (به‌صورت ISO)."""
    now = now or _now_iso()
    last = {}
    for item in get_posted(history):
        value = item.get(field)
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        for v in values:
            if v is None:
                continue
            last[v] = item.get("posted_at") or now
    return last


def max_consecutive(posts, field="profile", value=None):
    """بیشترین رشته‌ی پشت‌سرهم مقداری (یا از آخر در صورت value معین).

    برای فیلدهای لیستی (مثل genres) اگر value معین باشد، «پشت‌سرهم» یعنی پست‌هایی
    که مقدار در لیستشان باشد.
    """
    values = [item.get(field) for item in posts]
    if value is None:
        best = cur = 0
        prev = None
        for v in values:
            if v == prev:
                cur += 1
            else:
                cur = 1
            prev = v
            best = max(best, cur)
        return best

    def is_match(v):
        if isinstance(v, list):
            return value in v
        return v == value

    n = 0
    for v in reversed(values):
        if is_match(v):
            n += 1
        else:
            break
    return n


class HistoryMemory:
    """کاربردی‌ترین سطح: همه‌ی سوال‌های 'محتوایی' که موتور نیاز دارد."""

    def __init__(self, history, config):
        self.history = history
        self.posted = get_posted(history)
        self.cfg = config
        self.diversity_cfg = config.get("diversity", {})
        self.window = self.diversity_cfg.get("history_window", 10)
        self.recent_window = self.diversity_cfg.get("recent_window", 5)
        self.now = _now_iso()

    def recent(self, window=None):
        return recent_posts(self.history, window or self.window)

    def very_recent(self, window=None):
        return recent_posts(self.history, window or self.recent_window)

    def genre_counts(self, window=None):
        return counts_in_window(self.history, window or self.window, "genres")

    def director_counts(self, window=None):
        return counts_in_window(self.history, window or self.window, "director")

    def profile_counts(self, window=None):
        return counts_in_window(self.history, window or self.window, "profile")

    def era_counts(self, window=None):
        return counts_in_window(self.history, window or self.window, "era")

    def last_use(self, field, value):
        last = latest_use_dates(self.history, field, now=self.now)
        return last.get(value)

    def is_published(self, movie_id):
        return any(item.get("id") == movie_id for item in self.posted)

    def consecutive_count(self, field, value):
        return max_consecutive(self.recent(), field, value)

    def summary(self):
        """خلاصه برای لاگ توضیحی."""
        return {
            "genres": self.genre_counts(),
            "directors": self.director_counts(),
            "profiles": self.profile_counts(),
            "eras": self.era_counts(),
        }