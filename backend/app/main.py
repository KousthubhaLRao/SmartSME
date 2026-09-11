"""FastAPI entrypoint.

On startup it verifies the database connection, optionally seeds the demo
tenant, and starts the background event worker. The SPA talks to this over
cookie-authenticated JSON on /api/*.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .core.config import settings
from .core.db import SessionLocal, engine
from .routers import auth, catalog, ops, purchases, reports, sales
from .routers import input as input_router
from .worker import start_worker, stop_worker

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("smartsme")


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    log.info("database connected")

    if settings.seed_demo_data:
        # Best-effort: a seed hiccup must never stop the API from serving.
        try:
            from .seed import seed_if_empty

            with SessionLocal() as db:
                if seed_if_empty(db):
                    log.info("seeded the demo business")
        except Exception:
            log.exception("demo seed skipped")

    start_worker()
    try:
        yield
    finally:
        stop_worker()


app = FastAPI(
    title="SmartSME API",
    description="AI-assisted, event-driven business management for SMEs.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,  # required for the session cookie
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    """Domain validation errors surface as readable 400s rather than 500s."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health", tags=["meta"])
def health() -> dict:
    return {"ok": True, "service": "smartsme-api"}


for r in (
    auth.router,
    reports.router,
    sales.router,
    purchases.router,
    catalog.router,
    input_router.router,
    ops.router,
):
    app.include_router(r)
