"""CodeABC backend — FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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

# analyze router must come first: its /file/{path}/annotations route
# needs to match before project's greedy /file/{path:path} route
app.include_router(analyze.router, prefix="/api")
app.include_router(project.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve the built frontend from the same process, so the whole app is one
# command and one URL — no separate dev server for someone who just wants to
# run it. Skipped automatically when the frontend hasn't been built (e.g. in
# CI or a backend-only checkout), so imports and API tests are unaffected.
_FRONTEND_DIST = Path(
    os.getenv("CODEABC_FRONTEND_DIST")
    or Path(__file__).resolve().parent.parent / "frontend" / "dist"
)


def _mount_frontend() -> None:
    index = _FRONTEND_DIST / "index.html"
    if not index.is_file():
        return

    @app.get("/")
    async def _spa_root() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}")
    async def _spa_fallback(full_path: str) -> FileResponse:
        # API 404s stay 404s; never shadow them with the SPA shell.
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = (_FRONTEND_DIST / full_path).resolve()
        # serve a real built asset if it exists (and stays inside dist),
        # otherwise hand back index.html so client-side routes work on reload.
        if candidate.is_file() and candidate.is_relative_to(_FRONTEND_DIST):
            return FileResponse(candidate)
        return FileResponse(index)


_mount_frontend()
