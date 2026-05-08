import razorpay
import hmac
import hashlib
from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

# Initialize the Razorpay client
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
else:
    client = None

def create_order(amount: int, currency: str = "INR"):
    if not client:
        raise Exception("Razorpay keys not configured")
    data = {
        "amount": amount,
        "currency": currency,
        "payment_capture": "1"
    }
    order = client.order.create(data=data)
    return order

def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not RAZORPAY_KEY_SECRET:
        return False
    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
