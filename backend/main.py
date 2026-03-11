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

# Same layout as notebooks: data/generated/{prediction_id}/{index}.{ext}
BACKEND_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BACKEND_DIR / "data" / "generated"


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
def prediction_detail_view(prediction_id:str):
    result, status = helpers.get_prediction_detail(prediction_id)
    if status == 404:
        raise HTTPException(status_code=404, detail="Prediction not found")
    elif status == 500:
        raise HTTPException(status_code=500, detail="Server error")
    return schemas.PredictionDetailModel.from_replicate(result.dict())


@app.post(
    "/predictions/{prediction_id}/save",
    dependencies=[Depends(RateLimiter(times=100, seconds=20))],
)
async def save_prediction_outputs_view(prediction_id: str):
    """Save this prediction's output files to data/generated/{prediction_id}/ (same as notebooks)."""
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
    out_dir = GENERATED_DIR / prediction_id
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for i, url in enumerate(outputs):
        ext = Path(url).suffix or ".jpg"
        out_path = out_dir / f"{i}{ext}"
        content = await fetchers.fetch_file_async(url)
        out_path.write_bytes(content)
        saved.append(str(out_path.relative_to(BACKEND_DIR)))
    return {"saved": saved, "directory": str(out_dir.relative_to(BACKEND_DIR))}


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