from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import razorpay
import bcrypt
from supabase import create_client

from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

router = APIRouter()

rz_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ── Creator bank account setup ─────────────────────────────────────────────────

class BankAccountRequest(BaseModel):
    creator_id: str
    account_holder_name: str
    account_number: str
    ifsc_code: str


@router.post("/setup-payout")
async def setup_payout(data: BankAccountRequest):
    """Register a creator's bank account with Razorpay and store the fund account ID."""
    try:
        contact = rz_client.contacts.create({
            "name": data.account_holder_name,
            "type": "vendor",
            "reference_id": data.creator_id,
        })
        fund_account = rz_client.fund_account.create({
            "contact_id": contact["id"],
            "account_type": "bank_account",
            "bank_account": {
                "name": data.account_holder_name,
                "ifsc": data.ifsc_code,
                "account_number": data.account_number,
            },
        })
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e}")

    supabase_client.table("creators").update({
        "razorpay_contact_id": contact["id"],
        "razorpay_fund_account_id": fund_account["id"],
        "payouts_enabled": True,
    }).eq("id", data.creator_id).execute()

    return {"success": True}


# ── Password hashing for creator-set reel passwords ───────────────────────────

class SetPasswordRequest(BaseModel):
    reel_id: str
    creator_id: str
    password: str


@router.post("/set-reel-password")
async def set_reel_password(data: SetPasswordRequest):
    """Hash and store the unlock password for a reel. Password never sent to frontend."""
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters")

    hashed = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    supabase_client.table("reels").update({
        "unlock_password": hashed,
    }).eq("id", data.reel_id).eq("creator_id", data.creator_id).execute()

    return {"success": True}
