from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, campaigns, creators, discovery, outreach, reports
from .core.config import config
from .core.db import Base, engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _add_missing_columns() -> None:
    """Tiny forward-only migration for columns added after the first release."""
    from sqlalchemy import inspect, text

    wanted = {"creators": {"reels_collected_at": "TIMESTAMP"}}
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in wanted.items():
            have = {c["name"] for c in inspector.get_columns(table)}
            for name, kind in columns.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {kind}"))


def _remove_demo_records() -> None:
    """Demo mode was removed. Delete the fictional demo creators and demo searches
    left in an existing database (with their contacts, notes, links and drafts)."""
    from .core.db import SessionLocal
    from .models import Creator, SearchResult, SearchRun, Setting

    db = SessionLocal()
    try:
        demo = db.query(Creator).filter(Creator.is_demo.is_(True)).all()
        if demo:
            ids = [c.id for c in demo]
            db.query(SearchResult).filter(SearchResult.creator_id.in_(ids)).delete(synchronize_session=False)
            for creator in demo:
                db.delete(creator)
        for run in db.query(SearchRun).filter(SearchRun.is_demo.is_(True)).all():
            db.delete(run)
        stale = db.get(Setting, "provider_mode")
        if stale:
            db.delete(stale)
        db.commit()
        if demo:
            logging.getLogger("creator_finder").info("Removed %d demo creator record(s)", len(demo))
    finally:
        db.close()


def create_app() -> FastAPI:
    Base.metadata.create_all(engine)
    _add_missing_columns()
    _remove_demo_records()
    app = FastAPI(title="Creator Finder API", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    for module in (auth, creators, discovery, campaigns, outreach, reports):
        app.include_router(module.router)

    @app.get("/api/health")
    def health():
        # "database" shows whether data will survive restarts: sqlite on a serverless
        # host is temporary, postgresql is permanent. No secrets are exposed here.
        import os

        return {"status": "ok", "database": engine.dialect.name,
                "signing_key": "environment" if os.getenv("SECRET_KEY") else "stored in database"}

    # Optional single-server deployment: serve the built React app if it exists.
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = (dist / path).resolve()
            if path and file.is_file() and dist in file.parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
