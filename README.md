# Razorpay Drop Reveal — FastAPI Backend

A minimal Python backend to handle Razorpay payments for a drop reveal project.
Handles order creation, payment verification, webhook events, and drop access control.

---

## Project Structure

```
drop-reveal-backend/
│
├── main.py                  # App entry point, route registration
├── config.py                # Env vars and settings
├── routes/
│   ├── orders.py            # POST /create-order
│   ├── payments.py          # POST /verify-payment
│   └── webhooks.py          # POST /webhook
├── services/
│   ├── razorpay_service.py  # Razorpay SDK wrapper
│   └── drop_service.py      # Drop unlock / access logic
├── models/
│   └── schemas.py           # Pydantic request/response models
├── database.py              # SQLite / Postgres setup (SQLAlchemy)
├── .env                     # Secret keys (never commit this)
├── .env.example             # Template for env vars
├── requirements.txt
├── Dockerfile               # For Railway / Render deployment
└── README.md
```

---

## What Each File Does

### `main.py`
- Creates the FastAPI app instance
- Registers all routers (`/orders`, `/payments`, `/webhook`)
- Adds CORS middleware (so your frontend can call this backend)
- Health check route `GET /` returns `{ "status": "ok" }`

### `config.py`
- Loads `.env` variables using `python-dotenv`
- Exposes `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `WEBHOOK_SECRET`, `DATABASE_URL`
- Single source of truth — never import `os.environ` directly elsewhere

### `routes/orders.py` — `POST /create-order`
**Purpose:** Creates a Razorpay order before the checkout modal opens.

What it does:
1. Receives `amount` and `currency` from your frontend
2. Calls Razorpay Orders API → gets back an `order_id`
3. Saves the order to your DB with status `"created"`
4. Returns `{ order_id, amount, currency, key_id }` to frontend

Your frontend needs the `order_id` to open the Razorpay checkout modal.

### `routes/payments.py` — `POST /verify-payment`
**Purpose:** Verifies the payment is genuine after the user pays.

What it does:
1. Receives `razorpay_order_id`, `razorpay_payment_id`, `razorpay_signature` from frontend
2. Recomputes the expected HMAC-SHA256 signature using your `KEY_SECRET`
3. If signatures match → payment is genuine
4. Updates order status to `"paid"` in DB
5. Calls `drop_service.unlock(order_id)` to reveal drop content
6. Returns `{ success: true, drop_token: "..." }` — a one-time token your frontend uses to show the reveal

If signatures don't match → returns `400 Bad Request`. **Never skip this step.**

### `routes/webhooks.py` — `POST /webhook`
**Purpose:** Backup listener — Razorpay calls this directly even if the user closes the browser.

What it does:
1. Validates the `X-Razorpay-Signature` header against your `WEBHOOK_SECRET`
2. Handles `payment.captured` event → marks order paid if not already done
3. Handles `payment.failed` event → marks order failed, logs reason
4. Returns `200 OK` immediately (Razorpay retries if it gets anything else)

> Set your webhook URL in Razorpay Dashboard → Settings → Webhooks → Add New Webhook.
> Select events: `payment.captured` and `payment.failed`.

### `services/razorpay_service.py`
- Wraps the `razorpay` Python SDK
- Functions: `create_order(amount, currency)`, `verify_signature(order_id, payment_id, signature)`
- Keeps all Razorpay logic out of routes

### `services/drop_service.py`
- `unlock(order_id)` → generates a signed one-time drop token (use `secrets.token_urlsafe`)
- `verify_token(token)` → checks if token is valid and not yet used
- `get_drop_content(token)` → returns the actual drop reveal data (URL, image, password, etc.)
- Store tokens in DB with `used=False`, expire after 24 hours

### `models/schemas.py`
Pydantic models for request validation:

```python
class CreateOrderRequest(BaseModel):
    amount: int          # in paise (₹499 = 49900)
    currency: str = "INR"

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

class DropTokenRequest(BaseModel):
    token: str
```

### `database.py`
- SQLAlchemy setup with two tables:
  - `orders` — id, razorpay_order_id, amount, status, created_at
  - `drop_tokens` — token, order_id, used, expires_at
- Use SQLite locally, Postgres in production
- `DATABASE_URL` in `.env` switches between them automatically

---

## The Full Payment Flow

```
[User clicks "Buy Drop"]
        │
        ▼
Frontend → POST /create-order
        │   { amount: 49900, currency: "INR" }
        │
        ▼
Backend creates Razorpay order → returns order_id
        │
        ▼
Frontend opens Razorpay checkout modal (with order_id)
        │
User pays via UPI / Card / Net banking
        │
        ▼
Razorpay returns { payment_id, order_id, signature } to frontend
        │
        ▼
Frontend → POST /verify-payment
        │   { razorpay_order_id, razorpay_payment_id, razorpay_signature }
        │
        ▼
Backend verifies signature → unlocks drop → returns drop_token
        │
        ▼
Frontend uses drop_token → GET /drop?token=xxx → shows reveal
        │
        ▼ (parallel, as backup)
Razorpay → POST /webhook (payment.captured)
        │
Backend marks order paid (idempotent — safe if already done)
```

---

## Installation

```bash
# 1. Clone and enter the project
git clone https://github.com/yourname/drop-reveal-backend
cd drop-reveal-backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env and add your Razorpay keys

# 5. Run the server
uvicorn main:app --reload --port 8000
```

---

## Environment Variables

Create a `.env` file (never commit this):

```env
RAZORPAY_KEY_ID=rzp_test_XXXXXXXXXXXXXXXX
RAZORPAY_KEY_SECRET=your_secret_key_here
WEBHOOK_SECRET=your_webhook_secret_here
DATABASE_URL=sqlite:///./drop.db
FRONTEND_URL=http://localhost:3000
```

For production, replace `rzp_test_` keys with `rzp_live_` keys and set `DATABASE_URL` to your Postgres URL.

---

## `requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
razorpay==1.4.1
python-dotenv==1.0.1
sqlalchemy==2.0.35
pydantic==2.9.2
httpx==0.27.2
python-jose==3.3.0
```

---

## Key Code Snippets

### Create order (routes/orders.py)

```python
@router.post("/create-order")
async def create_order(data: CreateOrderRequest, db: Session = Depends(get_db)):
    order = razorpay_service.create_order(data.amount, data.currency)
    db_order = Order(razorpay_order_id=order["id"], amount=data.amount, status="created")
    db.add(db_order)
    db.commit()
    return {"order_id": order["id"], "amount": data.amount, "key_id": settings.RAZORPAY_KEY_ID}
```

### Verify payment (routes/payments.py)

```python
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
    order.status = "paid"
    db.commit()

    # Unlock drop and return access token
    drop_token = drop_service.unlock(order.id)
    return {"success": True, "drop_token": drop_token}
```

### Signature verification (services/razorpay_service.py)

```python
import hmac, hashlib

def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Webhook handler (routes/webhooks.py)

```python
@router.post("/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    # Validate webhook authenticity
    expected = hmac.new(
        settings.WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")

    if event == "payment.captured":
        order_id = payload["payload"]["payment"]["entity"]["order_id"]
        order = db.query(Order).filter_by(razorpay_order_id=order_id).first()
        if order and order.status != "paid":
            order.status = "paid"
            drop_service.unlock(order.id)
            db.commit()

    return {"status": "ok"}
```

---

## Deploying for Free

### Railway (recommended — easiest)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

Add your `.env` variables in Railway dashboard → Variables tab.
Railway auto-detects Python and runs `uvicorn main:app --host 0.0.0.0 --port $PORT`.

### Render

1. Push code to GitHub
2. New Web Service → connect repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add env vars under Environment tab
6. Free tier spins down after inactivity — use Railway for always-on

### Dockerfile (for both)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Testing Locally

Use Razorpay test cards:

| Payment method | Details |
|---|---|
| Card (success) | 4111 1111 1111 1111, any future date, any CVV |
| Card (failure) | 4000 0000 0000 0002 |
| UPI (success) | success@razorpay |
| UPI (failure) | failure@razorpay |

Test webhooks locally using [ngrok](https://ngrok.com):

```bash
ngrok http 8000
# Copy the https URL → paste into Razorpay Dashboard → Webhooks
```

---

## Security Checklist Before Going Live

- [ ] Switch `rzp_test_` keys to `rzp_live_` keys in `.env`
- [ ] Never expose `RAZORPAY_KEY_SECRET` in frontend code
- [ ] Always verify payment signature server-side — never trust frontend alone
- [ ] Validate webhook `X-Razorpay-Signature` on every request
- [ ] Use HTTPS in production (Railway and Render provide this automatically)
- [ ] Set `FRONTEND_URL` in CORS to your actual domain (not `*`)
- [ ] Make webhook handler idempotent (safe to call twice for same payment)
- [ ] Add rate limiting to `/create-order` to prevent abuse

---

## API Reference

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/create-order` | Create Razorpay order, returns order_id |
| `POST` | `/verify-payment` | Verify signature, unlock drop, return token |
| `POST` | `/webhook` | Razorpay event listener (payment.captured / failed) |
| `GET` | `/drop` | Return drop content for valid token |

---

## Questions?

- Razorpay Docs: https://razorpay.com/docs
- FastAPI Docs: https://fastapi.tiangolo.com
- Railway Docs: https://docs.railway.app
