from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db, Order
from models.schemas import VerifyPaymentRequest
from services import razorpay_service, drop_service

router = APIRouter()

@router.post("/verify-payment")
async def verify_payment(data: VerifyPaymentRequest, db: Session = Depends(get_db)):
    is_valid = razorpay_service.verify_signature(
        data.razorpay_order_id,
        data.razorpay_payment_id,
        data.razorpay_signature
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Mark order as paid
    order = db.query(Order).filter_by(razorpay_order_id=data.razorpay_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    order.status = "paid"
    db.commit()

    # Unlock drop and return access token
    drop_token = drop_service.unlock(db, order.id)
    return {"success": True, "drop_token": drop_token}
