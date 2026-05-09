from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, Order
from models.schemas import CreateOrderRequest
from services import razorpay_service
from config import RAZORPAY_KEY_ID

router = APIRouter()

@router.post("/create-order")
async def create_order(data: CreateOrderRequest, db: Session = Depends(get_db)):
    try:
        order = razorpay_service.create_order(data.amount, data.currency)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    db_order = Order(
        razorpay_order_id=order["id"],
        amount=data.amount,
        status="created",
        reel_id=data.reel_id,
        creator_id=data.creator_id,
        commission_rate=data.commission_rate,
    )
    db.add(db_order)
    db.commit()

    return {"order_id": order["id"], "amount": data.amount, "key_id": RAZORPAY_KEY_ID}
