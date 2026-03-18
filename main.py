from pathlib import Path
from typing import Optional, List
import json
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
from sqlalchemy.orm import Session

import helpers
from helpers import schemas, fetchers
from helpers.auth import create_access_token, get_current_user, hash_password, verify_password
from helpers.database import get_db, init_db
from helpers.models import User, Prediction
from helpers.ratelimiting import lifespan as my_ratelimit_lifespan

BACKEND_DIR = Path(__file__).resolve().parent


REDIS_URL = config("REDIS_URL")
API_KEY_HEADER = "X-API-Key"
API_ACCESS_KEY = config("API_ACCESS_KEY")
API_KEY_EXEMPT_PATHS = {
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/me",
    "/api/auth/logout",
    "/docs",
    "/redoc",
    "/openapi.json",
}

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
    if request.url.path in API_KEY_EXEMPT_PATHS:
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # JWT-authenticated requests can skip API key.
        return await call_next(request)
    req_key_header = request.headers.get(API_KEY_HEADER)
    if f"{req_key_header}" != API_ACCESS_KEY:
        return JSONResponse(status_code=403, content={"detail": "Invalid Key, try again."})
    response = await call_next(request)
    return response


@app.on_event("startup")
def startup_init_db():
    init_db()


class LoginRequest(BaseModel):
    email: str
    password: str


class SignupRequest(BaseModel):
    name: str
    email: str
    password: str
    confirmPassword: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    createdAt: str


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


def serialize_user(user: User) -> UserResponse:
    fallback_name = user.email.split("@")[0] if user.email else "user"
    return UserResponse(
        id=str(user.id),
        name=(user.name or fallback_name).strip() or fallback_name,
        email=user.email,
        createdAt=user.created_at.isoformat() if user.created_at else "",
    )


@app.post("/api/auth/signup", response_model=AuthResponse)
def signup_view(payload: SignupRequest, db: Session = Depends(get_db)):
    if payload.password != payload.confirmPassword:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    normalized_email = payload.email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="Email is required")

    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        name=payload.name.strip() or None,
        email=normalized_email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(user=serialize_user(user), token=token)


@app.post("/api/auth/login", response_model=AuthResponse)
def login_view(payload: LoginRequest, db: Session = Depends(get_db)):
    normalized_email = payload.email.strip().lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": str(user.id)})
    return AuthResponse(user=serialize_user(user), token=token)


@app.get("/api/auth/me", response_model=UserResponse)
def me_view(current_user: User = Depends(get_current_user)):
    return serialize_user(current_user)


@app.post("/api/auth/logout")
def logout_view():
    # JWT auth is stateless; frontend clears token client-side.
    return {"message": "Logged out successfully"}

@app.get("/", dependencies=[
    Depends(get_current_user),
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


class GeneratedImageResponse(BaseModel):
    id: str
    url: str
    prompt: str
    negativePrompt: Optional[str] = None
    triggerWord: Optional[str] = None
    modelId: Optional[str] = None
    userId: str
    createdAt: str


class ImageHistoryResponse(BaseModel):
    images: List[GeneratedImageResponse]
    total: int
    page: int
    limit: int


def _load_output_urls(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, str)]
    except Exception:
        return []
    return []


def _prediction_to_generated_images(prediction: Prediction) -> List[GeneratedImageResponse]:
    urls = _load_output_urls(prediction.output_urls_json)
    if not urls and prediction.thumbnail_url:
        urls = [prediction.thumbnail_url]

    created_at = prediction.created_at.isoformat() if prediction.created_at else ""
    return [
        GeneratedImageResponse(
            id=f"{prediction.id}:{idx}",
            url=url,
            prompt=prediction.prompt or "",
            triggerWord=prediction.trigger_word,
            userId=str(prediction.user_id),
            createdAt=created_at,
        )
        for idx, url in enumerate(urls)
    ]

@app.post('/generate', 
        dependencies=[
            Depends(get_current_user),
            Depends(RateLimiter(times=2, seconds=5)),
            Depends(RateLimiter(times=10, minutes=1))
        ],
        response_model=schemas.PredictionCreateModel
)
def create_image(
    data: ImageGenerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        pred_result = helpers.generate_image(
            data.prompt,
            require_trigger_word=data.require_trigger_word,
            trigger_word=data.trigger_word,
            num_outputs=data.num_outputs,
            output_format=data.output_format,
        )
        pred_dict = pred_result.dict()
        prediction = Prediction(
            user_id=current_user.id,
            prediction_id=pred_dict.get("id"),
            status=pred_dict.get("status") or "starting",
            prompt=data.prompt,
            num_outputs=data.num_outputs,
            output_format=data.output_format,
            require_trigger_word=data.require_trigger_word,
            trigger_word=data.trigger_word,
            create_payload_json=json.dumps(pred_dict, default=str),
        )
        db.add(prediction)
        db.commit()

        return schemas.PredictionCreateModel.from_replicate(pred_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@app.get("/processing", dependencies=[
    Depends(get_current_user),
    Depends(RateLimiter(times=1000, seconds=20))
],
response_model=List[schemas.PredictionListModel]

)
def list_processing_view():
    results = helpers.list_prediction_results(status="processing")
    return [schemas.PredictionListModel.from_replicate(x.dict()) for x in results]


@app.get("/predictions", 
         dependencies=[
            Depends(get_current_user),
            Depends(RateLimiter(times=1000, seconds=20))
        ],
        response_model=List[schemas.PredictionListModel]
)
def list_predictions_view(status:Optional[str] = None):
    results = helpers.list_prediction_results(status=status)
    return [schemas.PredictionListModel.from_replicate(x.dict()) for x in results]


@app.get("/predictions/{prediction_id}", dependencies=[
    Depends(get_current_user),
    Depends(RateLimiter(times=1000, seconds=20))
    ],
    response_model=schemas.PredictionDetailModel
)
async def prediction_detail_view(
    prediction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prediction_row = (
        db.query(Prediction)
        .filter(Prediction.prediction_id == prediction_id, Prediction.user_id == current_user.id)
        .first()
    )
    if prediction_row is None:
        raise HTTPException(status_code=404, detail="Prediction not found")

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

    output_urls = result_dict.get("output") or []
    if isinstance(output_urls, list):
        prediction_row.output_urls_json = json.dumps(output_urls)
        prediction_row.thumbnail_url = output_urls[0] if output_urls else None
    prediction_row.status = result_dict.get("status") or prediction_row.status
    prediction_row.detail_payload_json = json.dumps(result_dict, default=str)
    db.add(prediction_row)
    db.commit()

    return schemas.PredictionDetailModel.from_replicate(result_dict)


@app.get("/api/images/history", response_model=ImageHistoryResponse)
def image_history_view(
    page: int = 1,
    limit: int = 50,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    safe_page = max(1, page)
    safe_limit = max(1, min(limit, 100))

    query = db.query(Prediction).filter(Prediction.user_id == current_user.id)
    query = query.filter(Prediction.status == "succeeded")

    if keyword:
        query = query.filter(Prediction.prompt.ilike(f"%{keyword}%"))

    query = query.order_by(Prediction.created_at.desc())
    predictions = query.offset((safe_page - 1) * safe_limit).limit(safe_limit).all()

    images: List[GeneratedImageResponse] = []
    for pred in predictions:
        images.extend(_prediction_to_generated_images(pred))

    return ImageHistoryResponse(
        images=images,
        total=len(images),
        page=safe_page,
        limit=safe_limit,
    )


@app.get("/api/images/{image_id}", response_model=GeneratedImageResponse)
def image_detail_view(
    image_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        prediction_db_id_raw, output_index_raw = image_id.split(":", 1)
        prediction_db_id = int(prediction_db_id_raw)
        output_index = int(output_index_raw)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image id")

    prediction = (
        db.query(Prediction)
        .filter(Prediction.id == prediction_db_id, Prediction.user_id == current_user.id)
        .first()
    )
    if prediction is None:
        raise HTTPException(status_code=404, detail="Image not found")

    urls = _load_output_urls(prediction.output_urls_json)
    if output_index < 0 or output_index >= len(urls):
        raise HTTPException(status_code=404, detail="Image not found")

    created_at = prediction.created_at.isoformat() if prediction.created_at else ""
    return GeneratedImageResponse(
        id=image_id,
        url=urls[output_index],
        prompt=prediction.prompt or "",
        triggerWord=prediction.trigger_word,
        userId=str(prediction.user_id),
        createdAt=created_at,
    )


@app.post(
    "/predictions/{prediction_id}/save",
    dependencies=[Depends(get_current_user), Depends(RateLimiter(times=100, seconds=20))],
)
async def save_prediction_outputs_view(
    prediction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload this prediction's output files to S3 (bucket/data/{prediction_id}/)."""
    owns_prediction = (
        db.query(Prediction)
        .filter(Prediction.prediction_id == prediction_id, Prediction.user_id == current_user.id)
        .first()
    )
    if owns_prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")

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
    Depends(get_current_user),
    Depends(RateLimiter(times=1000, seconds=20))
    ],
    response_model=schemas.PredictionDetailModel
)
async def prediction_file_output_view(
    prediction_id: str,
    index_id: int,
    ext: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    owns_prediction = (
        db.query(Prediction)
        .filter(Prediction.prediction_id == prediction_id, Prediction.user_id == current_user.id)
        .first()
    )
    if owns_prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")

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