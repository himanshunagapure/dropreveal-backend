from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
from config import DATABASE_URL

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL.startswith(("postgres://", "postgresql://")):
    # Supabase Postgres requires SSL. If your DATABASE_URL already includes
    # `?sslmode=require` this is harmless.
    connect_args = {"sslmode": "require"}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    razorpay_order_id = Column(String, unique=True, index=True)
    amount = Column(Integer)
    status = Column(String)  # 'created', 'paid', 'failed'
    reel_id = Column(String, nullable=True)        # Supabase reel UUID
    creator_id = Column(String, nullable=True)     # Supabase creator UUID
    commission_rate = Column(Float, nullable=True) # 0.20 free plan, 0.10 pro plan
    created_at = Column(DateTime, default=datetime.utcnow)

class DropToken(Base):
    __tablename__ = "drop_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, index=True)
    order_id = Column(Integer)
    used = Column(Boolean, default=False)
    expires_at = Column(DateTime)


class AdSession(Base):
    __tablename__ = "ad_sessions"

    id = Column(String, primary_key=True)
    reel_id = Column(String, index=True)
    viewer_id = Column(String, index=True)
    ads_required = Column(Integer)
    completed = Column(Integer, default=0)
    play_started_at = Column(DateTime, nullable=True)
    unlocked = Column(Boolean, default=False)
    drop_token = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
