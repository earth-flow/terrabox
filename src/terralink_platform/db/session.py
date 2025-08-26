from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..core.utils.config import settings

engine = create_engine(settings.DB_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()