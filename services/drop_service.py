import secrets
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database import DropToken

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
    db_token = db.query(DropToken).filter_by(token=token, used=False).first()
    if not db_token:
        return False
    if db_token.expires_at < datetime.utcnow():
        return False
    
    # Mark token as used
    db_token.used = True
    db.commit()
    return True

def get_drop_content():
    return {
        "title": "Secret Drop Reveal!",
        "content": "Here is your exclusive content...",
        "image_url": "https://example.com/secret.png",
        "download_url": "https://example.com/download.zip"
    }
