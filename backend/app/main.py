from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.api.v1.router import router
from backend.app.db.base import Base
from backend.app.db.session import engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="LH-PREDICT RESILIENCE — SEOUL API", version="1.0.0", lifespan=lifespan)
app.include_router(router)

@app.get("/health")
def health():
    try:
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except SQLAlchemyError:
        return {"status": "degraded", "database": "unavailable"}
