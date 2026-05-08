from pydantic import BaseModel

class CreateOrderRequest(BaseModel):
    amount: int          # in paise (₹499 = 49900)
    currency: str = "INR"

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class DropTokenRequest(BaseModel):
    token: str
