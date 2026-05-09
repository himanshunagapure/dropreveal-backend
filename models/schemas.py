from pydantic import BaseModel

class CreateOrderRequest(BaseModel):
    amount: int          # in paise (₹99 = 9900)
    currency: str = "INR"
    reel_id: str
    creator_id: str
    commission_rate: float  # 0.20 free plan, 0.10 pro plan

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class DropTokenRequest(BaseModel):
    token: str

class RestoreAccessRequest(BaseModel):
    reel_id: str
    email: str


class VerifyPasswordRequest(BaseModel):
    reel_id: str
    password: str
