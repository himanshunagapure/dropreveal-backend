from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from database import get_db, Order
from services import drop_service
from config import WEBHOOK_SECRET
import hmac
import hashlib

router = APIRouter()

@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    # Validate webhook authenticity
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")

    if event == "payment.captured":
        order_id = payload["payload"]["payment"]["entity"]["order_id"]
        order = db.query(Order).filter_by(razorpay_order_id=order_id).first()
        if order and order.status != "paid":
            order.status = "paid"
            drop_service.unlock(db, order.id)
            db.commit()
            
    elif event == "payment.failed":
        order_id = payload["payload"]["payment"]["entity"]["order_id"]
        order = db.query(Order).filter_by(razorpay_order_id=order_id).first()
        if order and order.status != "paid":
            order.status = "failed"
            db.commit()

    return {"status": "ok"}
