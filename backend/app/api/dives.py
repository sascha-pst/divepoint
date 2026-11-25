import asyncio
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints

from app.rag.guide import answer_question

router = APIRouter(prefix="/v1")


class PlanRequest(BaseModel):
    text: str = Field(min_length=2, max_length=300)
    depth_m: float = Field(default=30, ge=1, le=60)
    month: int | None = Field(default=None, ge=1, le=12)
    place_id: int | None = None
    allow_sparse: bool = False


@router.post("/dives/plan")
async def plan(body: PlanRequest, request: Request):
    try:
        async with asyncio.timeout(45):
            return await request.app.state.dives.plan(body)
    except TimeoutError as error:
        raise HTTPException(
            503, "This live search took too long. Retry a smaller place, or explore Monterey Bay."
        ) from error


@router.get("/dives/{dive_id}")
def dive(dive_id: str, request: Request):
    return request.app.state.dives.dive(dive_id)


@router.get("/species/{aphia_id}")
async def card(aphia_id: int, dive_id: str, request: Request):
    return await request.app.state.dives.card(dive_id, aphia_id)


class AskRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
    aphia_id: int | None = Field(default=None, gt=0)


@router.post("/dives/{dive_id}/ask")
async def ask(dive_id: str, body: AskRequest, request: Request):
    dives = request.app.state.dives
    manifest = dives.dive(dive_id)
    return await answer_question(dives, manifest, body.question, body.aphia_id)
