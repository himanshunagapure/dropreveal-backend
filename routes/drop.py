from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from services import drop_service

router = APIRouter()


@router.get("/drop")
async def get_drop(token: str, reel_id: str | None = None, db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    resolved = drop_service.resolve_reel_id(db, token)
    if not resolved:
        raise HTTPException(status_code=403, detail="Invalid or expired token")
    if reel_id and reel_id.strip() != resolved:
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    return drop_service.get_reel_content(resolved)
