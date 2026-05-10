import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import get_db, Order
from models.schemas import CreateOrderRequest
from services import razorpay_service
from config import RAZORPAY_KEY_ID

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/create-order")
async def create_order(data: CreateOrderRequest, db: Session = Depends(get_db)):
    logger.info(
        "create-order request | reel_id=%s creator_id=%s amount=%s currency=%s commission=%.2f",
        data.reel_id, data.creator_id, data.amount, data.currency, data.commission_rate,
    )

    # Reuse an existing open order for the same reel to avoid Razorpay rate limits
    # caused by rapid / repeated clicks before the checkout modal opens.
    try:
        existing = (
            db.query(Order)
            .filter_by(reel_id=data.reel_id, status="created")
            .order_by(Order.created_at.desc())
            .first()
        )
    except Exception as e:
        logger.error("DB error querying existing order | reel_id=%s error=%s", data.reel_id, e, exc_info=True)
        existing = None

    if existing:
        logger.info("Reusing existing order | reel_id=%s order_id=%s", data.reel_id, existing.razorpay_order_id)
        return {"order_id": existing.razorpay_order_id, "amount": existing.amount, "key_id": RAZORPAY_KEY_ID}

    logger.info("Creating new Razorpay order | reel_id=%s amount=%s", data.reel_id, data.amount)
    try:
        order = razorpay_service.create_order(data.amount, data.currency)
        logger.info("Razorpay order created | order_id=%s", order.get("id"))
    except Exception as e:
        logger.error("Razorpay create_order failed | reel_id=%s error=%s", data.reel_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Razorpay error: {e}")

    db_order = Order(
        razorpay_order_id=order["id"],
        amount=data.amount,
        status="created",
        reel_id=data.reel_id,
        creator_id=data.creator_id,
        commission_rate=data.commission_rate,
    )
    db.add(db_order)
    try:
        db.commit()
        logger.info("Order saved to DB | order_id=%s reel_id=%s", order["id"], data.reel_id)
    except IntegrityError:
        db.rollback()
        logger.warning("IntegrityError saving order | order_id=%s reel_id=%s", order["id"], data.reel_id)
        raise HTTPException(
            status_code=409,
            detail="Order already recorded. Please refresh and try again.",
        )
    except Exception as e:
        db.rollback()
        logger.error("DB error saving order | order_id=%s error=%s", order["id"], e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    return {"order_id": order["id"], "amount": data.amount, "key_id": RAZORPAY_KEY_ID}
