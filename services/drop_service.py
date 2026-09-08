import secrets
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from supabase import create_client

from database import DropToken, Order
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

_supabase = None


def _client():
    global _supabase
    if _supabase is None:
        _supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


def unlock(db: Session, order_id: int) -> str:
    # Generate a secure one-time token
    token = secrets.token_urlsafe(32)
    # Expiry 24 hours from now
    expires_at = datetime.utcnow() + timedelta(hours=24)

    db_token = DropToken(token=token, order_id=order_id, used=False, expires_at=expires_at)
    db.add(db_token)
    db.commit()

    return token


def verify_token(db: Session, token: str) -> bool:
    """
    Checks whether a drop token exists and has not expired.
    Tokens are valid for their full 24-hour window and may be re-validated
    on every modal open (the viewer should not lose access mid-session).
    """
    return resolve_reel_id(db, token) is not None


def resolve_reel_id(db: Session, token: str) -> str | None:
    """Paid tokens live in drop_tokens (24h). Password/ad tokens live in reel_unlocks."""
    if not token:
        return None

    db_token = db.query(DropToken).filter_by(token=token, used=False).first()
    if db_token and db_token.expires_at >= datetime.utcnow():
        order = db.query(Order).filter_by(id=db_token.order_id).first()
        if order and order.reel_id:
            return order.reel_id

    try:
        result = (
            _client()
            .table("reel_unlocks")
            .select("reel_id")
            .eq("drop_token", token)
            .limit(1)
            .execute()
        )
    except Exception:
        return None

    if result.data:
        return result.data[0].get("reel_id")
    return None


def issue_unlock_token(reel_id: str, unlock_type: str, viewer_identifier: str | None = None) -> str:
    """Mint a long-lived access token stored on reel_unlocks (password / ad unlocks)."""
    token = secrets.token_urlsafe(32)
    row = {
        "reel_id": reel_id,
        "unlock_type": unlock_type,
        "drop_token": token,
    }
    if viewer_identifier:
        row["viewer_identifier"] = viewer_identifier
    _client().table("reel_unlocks").insert(row).execute()
    return token


def get_reel_content(reel_id: str) -> dict:
    res = (
        _client()
        .table("reels")
        .select("prompt, files(id, file_url, label)")
        .eq("id", reel_id)
        .single()
        .execute()
    )
    data = res.data or {}
    files = []
    for f in data.get("files") or []:
        url = (f.get("file_url") or "").strip()
        if not url:
            continue
        files.append({
            "id": f.get("id"),
            "file_url": url,
            "label": (f.get("label") or "").strip() or None,
        })
    return {
        "prompt": data.get("prompt") or "",
        "files": files,
    }


def get_drop_content():
    return {
        "title": "Secret Drop Reveal!",
        "content": "Here is your exclusive content...",
        "image_url": "https://example.com/secret.png",
        "download_url": "https://example.com/download.zip"
    }
