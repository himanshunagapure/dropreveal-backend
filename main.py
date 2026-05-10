import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import orders, payments, webhooks, drop, payouts
from config import FRONTEND_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

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
app.include_router(payouts.router, tags=["Payouts"])

@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
