from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import orders, payments, webhooks, drop
from config import FRONTEND_URL

app = FastAPI(title="Razorpay Drop Reveal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "*"], # allow all for local dev, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router, tags=["Orders"])
app.include_router(payments.router, tags=["Payments"])
app.include_router(webhooks.router, tags=["Webhooks"])
app.include_router(drop.router, tags=["Drop"])

@app.get("/")
async def root():
    return {"status": "ok"}
