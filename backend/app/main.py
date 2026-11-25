from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.dives import router
from app.checklist.service import DiveService


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dives = DiveService()
    yield
    await app.state.dives.close()


app = FastAPI(
    title="Divepoint API",
    version="0.2.0",
    lifespan=lifespan,
    description="Occurrence-backed playable prototype. Monterey starter pack + live marine search.",
)
app.include_router(router)


@app.exception_handler(httpx.HTTPError)
async def upstream_error(request, error):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The biodiversity service is unavailable. Retry, or explore the recorded Monterey Bay dive."
        },
    )


@app.get("/health")
def health():
    return {"status": "ok", "stage": "playable-prototype"}
