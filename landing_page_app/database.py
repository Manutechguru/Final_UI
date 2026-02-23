import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load .env for local development
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# HARD FAIL if missing (no silent fallback)
if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL not set in environment")

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()