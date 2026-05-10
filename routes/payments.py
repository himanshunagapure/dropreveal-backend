import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import razorpay
from supabase import create_client
import bcrypt

from database import get_db, Order
from models.schemas import VerifyPaymentRequest, RestoreAccessRequest, VerifyPasswordRequest
from services import razorpay_service, drop_service
from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

logger = logging.getLogger(__name__)
router = APIRouter()

rz_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


@router.post("/verify-payment")
async def verify_payment(data: VerifyPaymentRequest, db: Session = Depends(get_db)):
    logger.info("verify-payment | order_id=%s payment_id=%s", data.razorpay_order_id, data.razorpay_payment_id)

    # 1. Verify HMAC signature
    is_valid = razorpay_service.verify_signature(
        data.razorpay_order_id,
        data.razorpay_payment_id,
        data.razorpay_signature,
    )
    if not is_valid:
        logger.warning("Invalid signature | order_id=%s payment_id=%s", data.razorpay_order_id, data.razorpay_payment_id)
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # 2. Mark order paid
    order = db.query(Order).filter_by(razorpay_order_id=data.razorpay_order_id).first()
    if not order:
        logger.error("Order not found in DB | order_id=%s", data.razorpay_order_id)
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = "paid"
    db.commit()
    logger.info("Order marked paid | order_id=%s reel_id=%s", data.razorpay_order_id, order.reel_id)

    # 3. Generate drop token
    try:
        drop_token = drop_service.unlock(db, order.id)
        logger.info("Drop token generated | order_id=%s", data.razorpay_order_id)
    except Exception as e:
        logger.error("drop_service.unlock failed | order_id=%s error=%s", data.razorpay_order_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Could not generate drop token: {e}")

    # 4. Fetch viewer email + phone from Razorpay — captured automatically during checkout
    try:
        payment_details = rz_client.payment.fetch(data.razorpay_payment_id)
        viewer_email = (payment_details.get("email") or "").lower().strip() or None
        viewer_phone = payment_details.get("contact") or None
        logger.info("Fetched viewer contact | email=%s phone=%s", viewer_email, viewer_phone)
    except Exception as e:
        logger.warning("Could not fetch payment details from Razorpay | payment_id=%s error=%s", data.razorpay_payment_id, e)
        viewer_email = None
        viewer_phone = None

    # 5. Transfer creator's share via Razorpay Route (if creator has a fund account)
    if order.creator_id and order.commission_rate is not None:
        try:
            result = (
                supabase_client.table("creators")
                .select("razorpay_fund_account_id, is_pro")
                .eq("id", order.creator_id)
                .single()
                .execute()
            )
            creator = result.data or {}
            fund_account_id = creator.get("razorpay_fund_account_id")
            if fund_account_id:
                creator_share_paise = int(order.amount * (1 - order.commission_rate))
                rz_client.transfers.create({
                    "account": fund_account_id,
                    "amount": creator_share_paise,
                    "currency": "INR",
                    "notes": {
                        "reel_id": order.reel_id,
                        "payment_id": data.razorpay_payment_id,
                    },
                })
                logger.info("Creator transfer initiated | creator_id=%s amount_paise=%s", order.creator_id, creator_share_paise)
            else:
                logger.info("No fund_account_id for creator | creator_id=%s — skipping transfer", order.creator_id)
        except Exception as e:
            logger.warning("Creator transfer failed (non-fatal) | creator_id=%s error=%s", order.creator_id, e, exc_info=True)

    # 6. Record unlock in Supabase reel_unlocks
    viewer_hash = hashlib.sha256(data.razorpay_payment_id.encode()).hexdigest()
    try:
        supabase_client.table("reel_unlocks").insert({
            "reel_id": order.reel_id,
            "viewer_email": viewer_email,
            "viewer_phone": viewer_phone,
            "viewer_identifier": viewer_hash,
            "unlock_type": "paid",
            "razorpay_payment_id": data.razorpay_payment_id,
            "drop_token": drop_token,
            "amount_paid_inr": order.amount / 100,
        }).execute()
        logger.info("reel_unlocks row inserted | reel_id=%s payment_id=%s", order.reel_id, data.razorpay_payment_id)
    except Exception as e:
        logger.warning("reel_unlocks insert failed (non-fatal) | reel_id=%s error=%s", order.reel_id, e, exc_info=True)

    return {"success": True, "drop_token": drop_token}


@router.post("/restore-access")
async def restore_access(data: RestoreAccessRequest):
    """Cross-device recovery: looks up an existing paid unlock by reel + email."""
    logger.info("restore-access | reel_id=%s email=%s", data.reel_id, data.email.lower().strip())
    try:
        result = (
            supabase_client.table("reel_unlocks")
            .select("drop_token")
            .eq("reel_id", data.reel_id)
            .eq("viewer_email", data.email.lower().strip())
            .eq("unlock_type", "paid")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.error("restore-access Supabase query failed | reel_id=%s error=%s", data.reel_id, e, exc_info=True)
        raise HTTPException(status_code=502, detail="Could not query unlock records")

    if result.data:
        logger.info("restore-access found unlock | reel_id=%s", data.reel_id)
        return {"unlocked": True, "drop_token": result.data[0]["drop_token"]}
    logger.info("restore-access no unlock found | reel_id=%s email=%s", data.reel_id, data.email.lower().strip())
    return {"unlocked": False}


@router.post("/verify-password")
async def verify_password(data: VerifyPasswordRequest):
    """
    Password unlock (no payment).
    Uses Supabase service-role to fetch the reel's bcrypt hash, compares server-side,
    and returns { success: boolean }.
    """
    reel_id = data.reel_id.strip()
    password = data.password
    if not reel_id or not password:
        raise HTTPException(status_code=400, detail="reel_id and password are required")

    try:
        res = (
            supabase_client.table("reels")
            .select("unlock_password, unlock_type")
            .eq("id", reel_id)
            .single()
            .execute()
        )
    except Exception as e:
        logger.error("verify-password Supabase query failed | reel_id=%s error=%s", reel_id, e, exc_info=True)
        raise HTTPException(status_code=502, detail="Could not fetch reel password")

    reel = res.data or {}
    if not reel:
        raise HTTPException(status_code=404, detail="Reel not found")

    if (reel.get("unlock_type") or "free") != "password":
        return {"success": False}

    hashed = reel.get("unlock_password") or ""
    if not hashed:
        return {"success": False}

    try:
        ok = bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception as e:
        logger.warning("bcrypt.checkpw failed | reel_id=%s error=%s", reel_id, e)
        ok = False

    return {"success": bool(ok)}
