import os
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./drop.db")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Minimum wall-clock seconds a house ad must play before /complete-ad is accepted.
AD_MIN_WATCH_SECONDS = float(os.getenv("AD_MIN_WATCH_SECONDS", "8"))


def house_ad_urls() -> list[str]:
    """Direct MP4/WebM URLs for the rewarded unlock player (not YouTube/Drive pages)."""
    urls: list[str] = []
    for i in range(1, 8):
        raw = (
            os.getenv(f"HOUSE_ADS_URL{i}")
            or os.getenv(f"VITE_HOUSE_ADS_URL{i}")
            or ""
        ).strip()
        if raw:
            urls.append(raw)
    return urls

