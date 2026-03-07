import redis.asyncio as redis

from contextlib import asynccontextmanager
from typing import Union

from decouple import config
from fastapi import (
    FastAPI,
    Depends,
    HTTPException)
from pyrate_limiter import Duration, Limiter, Rate
from fastapi_limiter.depends import RateLimiter

from pydantic import BaseModel

import helpers

REDIS_URL = config("REDIS_URL")

app = FastAPI()

@app.get("/",
    dependencies=[
        Depends(RateLimiter(limiter=Limiter(Rate(2, Duration.SECOND*5)))),
        Depends(RateLimiter(limiter=Limiter(Rate(10, Duration.MINUTE*1))))
    ]
)
def read_root():
    # helpers.generate_image()
    return {"Hello": "World"}

class ImageGenerationRequest(BaseModel):
    prompt: str

@app.post("/generate")
def create_image(data: ImageGenerationRequest):
    try:
        pred_result = helpers.generate_image(data.prompt)
        return pred_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

