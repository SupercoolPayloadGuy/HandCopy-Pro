"""
app.py — FastAPI application factory
Serves the frontend at / and the API at /api/...
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db
from routers import profiles, documents, robot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)

os.makedirs("uploads", exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    logging.getLogger(__name__).info("✅ Database ready (SQLite)")
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Handwriting Robot API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(profiles.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(robot.router, prefix="/api")

    @app.get("/api/health")
    async def health():
        from services.robot_service import get_robot_status
        rs = await get_robot_status()
        return {"api": "ok", "robot": rs.get("state", "unknown")}

    @app.post("/api/shutdown")
    async def shutdown():
        import asyncio, os, signal
        async def _stop():
            await asyncio.sleep(0.3)
            os.kill(os.getpid(), signal.SIGTERM)
        asyncio.create_task(_stop())
        return {"message": "Shutting down…"}

    # Serve the frontend (index.html) at /
    @app.get("/")
    async def frontend():
        return FileResponse(os.path.join(os.path.dirname(__file__), "static", "index.html"))

    # Serve any other static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    return app
