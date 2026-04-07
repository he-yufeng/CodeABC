"""CodeABC backend — FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import analyze, project
from backend.services.cache import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: init sqlite cache
    await init_db()
    yield
    # shutdown: nothing to clean up for now


app = FastAPI(
    title="CodeABC",
    description="AI-powered code reader for non-programmers",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # vite dev
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        os.getenv("FRONTEND_ORIGIN", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project.router, prefix="/api")
app.include_router(analyze.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
