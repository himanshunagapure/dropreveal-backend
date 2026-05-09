import hashlib
import hmac
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from supabase import create_client

from database import get_db, Order
from services import drop_service
from config import WEBHOOK_SECRET, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

router = APIRouter()

supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    expected = hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # Parse body once (body stream already consumed above)
    payload = json.loads(body)
    event = payload.get("event")

    if event == "payment.captured":
        payment_entity = payload["payload"]["payment"]["entity"]
        order_id = payment_entity["order_id"]
        payment_id = payment_entity["id"]

        # Email and phone come directly in the webhook payload — no extra API call needed
        viewer_email = (payment_entity.get("email") or "").lower().strip() or None
        viewer_phone = payment_entity.get("contact") or None

        order = db.query(Order).filter_by(razorpay_order_id=order_id).first()
        if order and order.status != "paid":
            order.status = "paid"
            drop_token = drop_service.unlock(db, order.id)
            db.commit()

            viewer_hash = hashlib.sha256(payment_id.encode()).hexdigest()
            try:
                supabase_client.table("reel_unlocks").insert({
                    "reel_id": order.reel_id,
                    "viewer_email": viewer_email,
                    "viewer_phone": viewer_phone,
                    "viewer_identifier": viewer_hash,
                    "unlock_type": "paid",
                    "razorpay_payment_id": payment_id,
                    "drop_token": drop_token,
                    "amount_paid_inr": order.amount / 100,
                }).execute()
            except Exception:
                pass  # Non-fatal backup insert

    elif event == "payment.failed":
        order_id = payload["payload"]["payment"]["entity"]["order_id"]
        order = db.query(Order).filter_by(razorpay_order_id=order_id).first()
        if order and order.status != "paid":
            order.status = "failed"
            db.commit()

    return {"status": "ok"}
