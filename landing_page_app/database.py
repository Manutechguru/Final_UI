import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Load environment variables from .env (if present)
load_dotenv()

# Try reading from .env, else use a default connection string
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:Manu%405566@localhost:5432/Teetli"
)

# Print the connection URL for debugging (hide password)
safe_url = DATABASE_URL.replace(
    DATABASE_URL.split("@")[0], "postgresql+psycopg2://****:****"
)
print("🔗 DB URL seen by app:", safe_url)

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()

# Dependency to get DB session in FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
