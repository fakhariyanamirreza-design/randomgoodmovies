"""انتشاردهنده‌ی تلگرام (Telegram Publisher) — با retry محدود، timeout و خطای صریح.

مهم: اگر publish fail شود، exception می‌دهد تا تاریخچه آپدیت نشود (هرگز فیلم شکست‌خورده
به‌عنوان منتشرشده ثبت نمی‌شود).
"""

import time

import requests


class TelegramPublishError(Exception):
    pass


class TelegramPublisher:
    def __init__(self, bot_token, channel_id, config):
        if not bot_token:
            raise TelegramPublishError("TELEGRAM_BOT_TOKEN تنظیم نشده است.")
        if not channel_id:
            raise TelegramPublishError("TELEGRAM_CHANNEL_ID تنظیم نشده است.")
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.cfg = config.get("publisher", {})
        self.parse_mode = config.get("posting", {}).get("telegram_parse_mode", "HTML")
        self.photo_size = self.cfg.get("photo_size", "w1280")
        self.timeout = self.cfg.get("timeout_seconds", 30)
        self.max_retries = self.cfg.get("max_retries", 2)
        self.rate_limit_sleep = self.cfg.get("rate_limit_sleep_seconds", 1.0)

    def send_photo(self, caption, poster_path, dry_run=False, photo_url=None):
        if not poster_path and not photo_url:
            raise TelegramPublishError("پوستری برای این فیلم پیدا نشد.")

        if not photo_url:
            photo_url = f"https://image.tmdb.org/t/p/{self.photo_size}{poster_path}"
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
        payload = {
            "chat_id": self.channel_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": self.parse_mode,
        }

        if dry_run:
            print("[DRY-RUN] ارسال به تلگرام شبیه‌سازی شد (چیزی ارسال نشد).")
            print(f"[DRY-RUN] photo_url: {photo_url}")
            return {"ok": True, "dry_run": True}

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(url, data=payload, timeout=self.timeout)
                if r.status_code == 429:
                    # rate limit: wait کمی و retry
                    last_error = TelegramPublishError(f"تلگرام rate-limit: {r.status_code}")
                    time.sleep(self.rate_limit_sleep * (attempt + 1))
                    continue
                if not r.ok:
                    last_error = TelegramPublishError(f"تلگرام خطا: {r.status_code} {r.text}")
                    if attempt < self.max_retries:
                        time.sleep(self.rate_limit_sleep * (attempt + 1))
                    continue
                return r.json()
            except requests.RequestException as exc:
                last_error = TelegramPublishError(f"خطای شبکه در ارسال تلگرام: {exc}")
                if attempt < self.max_retries:
                    time.sleep(self.rate_limit_sleep * (attempt + 1))
        raise last_error