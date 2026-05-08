from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from services import drop_service

router = APIRouter()

@router.get("/drop")
async def get_drop(token: str, db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
        
    is_valid = drop_service.verify_token(db, token)
    if not is_valid:
        raise HTTPException(status_code=403, detail="Invalid or expired token")
        
    return drop_service.get_drop_content()
