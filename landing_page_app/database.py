from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Use your real DB name: mydb
DATABASE_URL = "postgresql+psycopg2://postgres:Manu%405566@localhost:5432/Teetli"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
