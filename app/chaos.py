"""Lab-only failure switch: makes /api/quiz/sample fail at a chosen rate, independent of any release."""

import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()
_fail_rate = 0.0


class UpstreamUnavailable(Exception):
    pass


class ChaosRequest(BaseModel):
    fail_rate: float = Field(ge=0.0, le=1.0)


@router.post("/admin/chaos")
def set_chaos(req: ChaosRequest):
    global _fail_rate
    if not settings.enable_chaos:
        raise HTTPException(404, "Not found")
    _fail_rate = req.fail_rate
    return {"fail_rate": _fail_rate}


def maybe_fail() -> None:
    if _fail_rate > 0 and random.random() < _fail_rate:
        raise UpstreamUnavailable("ollama (simulated)")
