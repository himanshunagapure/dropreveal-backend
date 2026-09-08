from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models.schemas import StartAdSessionRequest, AdSessionActionRequest
from services import ad_service

router = APIRouter()


@router.post("/start-ad-session")
async def start_ad_session(data: StartAdSessionRequest, db: Session = Depends(get_db)):
    return ad_service.start_session(db, data.reel_id, data.viewer_id)


@router.post("/start-ad-play")
async def start_ad_play(data: AdSessionActionRequest, db: Session = Depends(get_db)):
    return ad_service.start_play(db, data.session_id, data.viewer_id)


@router.post("/complete-ad")
async def complete_ad(data: AdSessionActionRequest, db: Session = Depends(get_db)):
    return ad_service.complete_ad(db, data.session_id, data.viewer_id, data.duration_sec)
