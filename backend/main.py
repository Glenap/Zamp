"""VendorGate API and optional built React frontend, served from one origin."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from backend.db import BACKEND_DIR, connect, init_db
from backend.api import router


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="VendorGate", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health():
    with connect() as connection:
        connection.execute("SELECT 1 FROM settings LIMIT 1").fetchone()
    return {"ok": True}


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404, "API endpoint not found")
    directory = (BACKEND_DIR.parent / "frontend" / "dist").resolve()
    target = (directory / path).resolve()
    if not target.is_relative_to(directory):
        raise HTTPException(404, "File not found")
    if target.is_file():
        return FileResponse(target)
    if Path(path).suffix:
        raise HTTPException(404, "Asset not found")
    index = directory / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(404, "Frontend not built; run npm run build in frontend, or start Vite")
