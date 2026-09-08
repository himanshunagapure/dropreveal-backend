import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session
from supabase import create_client

from database import AdSession
from services import drop_service
from config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    AD_MIN_WATCH_SECONDS,
    house_ad_urls,
)

logger = logging.getLogger(__name__)
supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def ads_required_for_reel(reel: dict) -> int:
    if not reel.get("ad_unlock_enabled"):
        return 0
    unlock_type = reel.get("unlock_type") or "free"
    if unlock_type == "free":
        return 1
    if unlock_type == "password":
        return 3
    return 0


def fetch_reel(reel_id: str) -> dict:
    try:
        res = (
            supabase_client.table("reels")
            .select("id, unlock_type, ad_unlock_enabled")
            .eq("id", reel_id)
            .single()
            .execute()
        )
        if res.data:
            return res.data
    except Exception as e:
        logger.warning("ad_unlock_enabled select failed | reel_id=%s error=%s", reel_id, e)

    try:
        res = (
            supabase_client.table("reels")
            .select("id, unlock_type")
            .eq("id", reel_id)
            .single()
            .execute()
        )
    except Exception as e:
        logger.error("fetch reel for ads failed | reel_id=%s error=%s", reel_id, e, exc_info=True)
        raise HTTPException(status_code=502, detail="Could not fetch reel")
    if not res.data:
        raise HTTPException(status_code=404, detail="Reel not found")
    data = dict(res.data)
    data["ad_unlock_enabled"] = False
    return data


def video_url_for_index(index: int) -> str:
    urls = house_ad_urls()
    if not urls:
        raise HTTPException(
            status_code=503,
            detail="House ads are not configured. Set HOUSE_ADS_URL1 (and URL2/URL3) on the backend.",
        )
    return urls[index % len(urls)]


def _session_payload(session: AdSession, include_content: bool = False) -> dict:
    payload = {
        "session_id": session.id,
        "ads_required": session.ads_required,
        "completed": session.completed,
        "unlocked": session.unlocked,
        "drop_token": session.drop_token,
        "video_url": None if session.unlocked else video_url_for_index(session.completed),
    }
    if include_content and session.unlocked:
        try:
            content = drop_service.get_reel_content(session.reel_id)
            payload["prompt"] = content["prompt"]
            payload["files"] = content["files"]
        except Exception:
            logger.exception("Could not load reel content after ad unlock | reel_id=%s", session.reel_id)
    return payload


def start_session(db: Session, reel_id: str, viewer_id: str) -> dict:
    reel_id = reel_id.strip()
    viewer_id = viewer_id.strip()
    if not reel_id or not viewer_id:
        raise HTTPException(status_code=400, detail="reel_id and viewer_id are required")

    reel = fetch_reel(reel_id)
    required = ads_required_for_reel(reel)
    if required < 1:
        raise HTTPException(status_code=400, detail="Ads are not enabled for this reel")

    existing = (
        db.query(AdSession)
        .filter_by(reel_id=reel_id, viewer_id=viewer_id)
        .order_by(AdSession.created_at.desc())
        .first()
    )
    if existing:
        if existing.ads_required != required and not existing.unlocked:
            existing.ads_required = required
            db.commit()
        if not existing.unlocked and existing.completed >= existing.ads_required:
            return _finalize_unlock(db, existing)
        return _session_payload(existing, include_content=existing.unlocked)

    session = AdSession(
        id=str(uuid.uuid4()),
        reel_id=reel_id,
        viewer_id=viewer_id,
        ads_required=required,
        completed=0,
        unlocked=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_payload(session)


def _get_owned_session(db: Session, session_id: str, viewer_id: str) -> AdSession:
    session = db.query(AdSession).filter_by(id=session_id.strip()).first()
    if not session or session.viewer_id != viewer_id.strip():
        raise HTTPException(status_code=404, detail="Ad session not found")
    return session


def start_play(db: Session, session_id: str, viewer_id: str) -> dict:
    session = _get_owned_session(db, session_id, viewer_id)
    if session.unlocked:
        return _session_payload(session, include_content=True)
    session.play_started_at = datetime.utcnow()
    db.commit()
    return _session_payload(session)


def _min_watch_seconds(duration_sec: float | None) -> float:
    """Never require watching longer than the actual video (short house ads were failing)."""
    if duration_sec and duration_sec > 0:
        required = max(3.0, duration_sec * 0.8)
        return min(required, max(0.5, duration_sec - 0.2))
    return AD_MIN_WATCH_SECONDS


def _finalize_unlock(db: Session, session: AdSession) -> dict:
    viewer_hash = hashlib.sha256(f"{session.viewer_id}:{session.reel_id}".encode()).hexdigest()
    token = drop_service.issue_unlock_token(session.reel_id, "ad", viewer_hash)
    session.unlocked = True
    session.drop_token = token
    session.play_started_at = None
    db.commit()
    return _session_payload(session, include_content=True)


def complete_ad(db: Session, session_id: str, viewer_id: str, duration_sec: float | None) -> dict:
    session = _get_owned_session(db, session_id, viewer_id)
    if session.unlocked:
        return _session_payload(session, include_content=True)

    if session.play_started_at is None:
        raise HTTPException(status_code=400, detail="Start the ad before completing it")

    elapsed = (datetime.utcnow() - session.play_started_at).total_seconds()
    min_required = _min_watch_seconds(duration_sec)
    if elapsed + 0.15 < min_required:
        raise HTTPException(status_code=400, detail="Watch the full ad to continue")

    session.completed += 1
    session.play_started_at = None

    if session.completed >= session.ads_required:
        return _finalize_unlock(db, session)

    db.commit()
    return _session_payload(session)
