"""
صَبا (Saba) — FastAPI application factory.
The database schema is managed outside this service.
The sweeper loop runs in the lifespan.
"""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.settings import settings
from app.services.sweeper import sweep_loop
from app.routers import catalog, checkout, events, contact, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.catalog_seed import sync_catalog

    sync_catalog()
    stop = asyncio.Event()
    task = asyncio.create_task(sweep_loop(stop))
    yield
    stop.set()
    await task


app = FastAPI(
    title="Saba API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

# CORS
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health checks
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/health/ready")
def health_ready():
    from app.db import engine
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True}
    except Exception as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})


# Routers
app.include_router(catalog.router)
app.include_router(checkout.router)
app.include_router(events.router)
app.include_router(contact.router)
app.include_router(admin.router)
