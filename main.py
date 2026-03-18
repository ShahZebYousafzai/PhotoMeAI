from pathlib import Path
from typing import Optional, List
from decouple import config
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi_limiter.depends import RateLimiter
import mimetypes

from pydantic import BaseModel

import helpers
from helpers import schemas, fetchers
from helpers.ratelimiting import lifespan as my_ratelimit_lifespan

BACKEND_DIR = Path(__file__).resolve().parent


REDIS_URL = config("REDIS_URL")
API_KEY_HEADER = "X-API-Key"
API_ACCESS_KEY = config("API_ACCESS_KEY")

app = FastAPI(lifespan=my_ratelimit_lifespan)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def custom_api_key_middleware(request: Request, call_next):
    # Let OPTIONS (CORS preflight) through without API key so the browser can complete preflight
    if request.method == "OPTIONS":
        return await call_next(request)
    req_key_header = request.headers.get(API_KEY_HEADER)
    if f"{req_key_header}" != API_ACCESS_KEY:
        return JSONResponse(status_code=403, content={"detail": "Invalid Key, try again."})
    response = await call_next(request)
    return response

@app.get("/", dependencies=[
    Depends(RateLimiter(times=2, seconds=5)),
    Depends(RateLimiter(times=4, seconds=20))
])
def read_root():
    # helpers.generate_image()
    return {"Hello": "World"}


class ImageGenerationRequest(BaseModel):
    prompt: str
    num_outputs: int = 2
    output_format: str = "jpg"
    require_trigger_word: bool = True
    trigger_word: str = "TOK"

@app.post('/generate', 
        dependencies=[
            Depends(RateLimiter(times=2, seconds=5)),
            Depends(RateLimiter(times=10, minutes=1))
        ],
        response_model=schemas.PredictionCreateModel
)
def create_image(data: ImageGenerationRequest):
    try:
        pred_result = helpers.generate_image(
            data.prompt,
            require_trigger_word=data.require_trigger_word,
            trigger_word=data.trigger_word,
            num_outputs=data.num_outputs,
            output_format=data.output_format,
        )
        return schemas.PredictionCreateModel.from_replicate(pred_result.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@app.get("/processing", dependencies=[
    Depends(RateLimiter(times=1000, seconds=20))
],
response_model=List[schemas.PredictionListModel]

)
def list_processing_view():
    results = helpers.list_prediction_results(status="processing")
    return [schemas.PredictionListModel.from_replicate(x.dict()) for x in results]


@app.get("/predictions", 
         dependencies=[
            Depends(RateLimiter(times=1000, seconds=20))
        ],
        response_model=List[schemas.PredictionListModel]
)
def list_predictions_view(status:Optional[str] = None):
    results = helpers.list_prediction_results(status=status)
    return [schemas.PredictionListModel.from_replicate(x.dict()) for x in results]


@app.get("/predictions/{prediction_id}", dependencies=[
    Depends(RateLimiter(times=1000, seconds=20))
    ],
    response_model=schemas.PredictionDetailModel
)
async def prediction_detail_view(prediction_id: str):
    result, status = helpers.get_prediction_detail(prediction_id)
    if status == 404:
        raise HTTPException(status_code=404, detail="Prediction not found")
    elif status == 500:
        raise HTTPException(status_code=500, detail="Server error")
    result_dict = result.dict()
    # When generation succeeded, auto-upload to S3 and return presigned URLs so images load (bucket can stay private)
    if result.status == "succeeded":
        outputs = getattr(result, "output", None) or []
        if outputs:
            from helpers import s3
            ext = Path(outputs[0]).suffix or ".jpg"
            presigned = s3.get_presigned_urls_for_prediction(prediction_id, len(outputs), ext)
            if presigned is None:
                files_to_upload = []
                for i, url in enumerate(outputs):
                    e = Path(url).suffix or ".jpg"
                    content = await fetchers.fetch_file_async(url)
                    files_to_upload.append((i, content, e))
                presigned = s3.upload_prediction_outputs(prediction_id, files_to_upload)
            result_dict["output"] = presigned
    return schemas.PredictionDetailModel.from_replicate(result_dict)


@app.post(
    "/predictions/{prediction_id}/save",
    dependencies=[Depends(RateLimiter(times=100, seconds=20))],
)
async def save_prediction_outputs_view(prediction_id: str):
    """Upload this prediction's output files to S3 (bucket/data/{prediction_id}/)."""
    result, status = helpers.get_prediction_detail(prediction_id)
    if status == 404:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if status == 500:
        raise HTTPException(status_code=500, detail="Server error")
    if result.status != "succeeded":
        raise HTTPException(
            status_code=400,
            detail=f"Prediction not ready to save (status: {result.status})",
        )
    outputs = getattr(result, "output", None) or []
    if not outputs:
        raise HTTPException(status_code=404, detail="No output files to save")
    files_to_upload = []
    for i, url in enumerate(outputs):
        ext = Path(url).suffix or ".jpg"
        content = await fetchers.fetch_file_async(url)
        files_to_upload.append((i, content, ext))
    from helpers import s3
    saved_urls = s3.upload_prediction_outputs(prediction_id, files_to_upload)
    return {"saved": saved_urls, "directory": f"s3://{s3.S3_BUCKET}/{s3.S3_PREFIX}/{prediction_id}/"}


@app.get("/predictions/{prediction_id}/files/{index_id}.{ext}", dependencies=[
    Depends(RateLimiter(times=1000, seconds=20))
    ],
    response_model=schemas.PredictionDetailModel
)
async def prediction_file_output_view(prediction_id:str, index_id:int, ext:str):
    result, status = helpers.get_prediction_detail(prediction_id)
    if status == 404:
        raise HTTPException(status_code=status, detail="Prediction not found")
    elif status == 500:
        raise HTTPException(status_code=status, detail="Server error")
    outputs = result.output
    if outputs is None:
        raise HTTPException(status_code=404, detail="Prediction output not found")
    len_outputs = len(outputs)
    if index_id > len_outputs:
        raise HTTPException(status_code=404, detail="File at index not found")
    try:
        file_url = result.output[index_id]
    except Exception as e:
         raise HTTPException(status_code=500, detail=f"Server error {e}")
    media_type, _ = mimetypes.guess_type(file_url)
    content = await fetchers.fetch_file_async(file_url)
    return StreamingResponse(
        iter([content]),
        media_type=media_type or "image/jpeg"
    )