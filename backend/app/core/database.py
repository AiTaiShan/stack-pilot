from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import redis
from app.core.config import settings

# PostgreSQL
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis():
    return redis_client
