"""
api/app.py — FastAPI application factory.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from utils.logger import get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("🚀 MLB Betting Analysis API starting up…")
    yield
    log.info("🛑 MLB Betting Analysis API shutting down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="MLB Betting Analysis API",
        description=(
            "Ingests MLB Stats API + Statcast data, scrapes PrizePicks and "
            "DraftKings lines, scores props with weighted signal models, and "
            "surfaces high-confidence picks + correlation-aware parlays."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    return app


app = create_app()
