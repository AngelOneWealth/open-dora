import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import job_store
from app.database import engine
import app.models  # noqa: F401 — registers all models with Base.metadata
from app.routers import orgs, repos, teams, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(job_store.periodic_cleanup_loop())
    yield
    cleanup_task.cancel()
    await engine.dispose()


app = FastAPI(title="Dora", lifespan=lifespan)

app.include_router(users.router)
app.include_router(repos.router)
app.include_router(teams.router)
app.include_router(orgs.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
