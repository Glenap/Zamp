"""Task 1 app: startup schema initialization and health check only."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

if __package__:
    from .db import connect, init_db
else:
    from db import connect, init_db


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title="VendorGate", lifespan=lifespan)


@app.get("/health")
def health():
    with connect() as connection:
        connection.execute("SELECT 1 FROM settings LIMIT 1").fetchone()
    return {"ok": True}
