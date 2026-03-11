## PhotoMeAI

PhotoMeAI is a small FastAPI service that wraps a Replicate image generation model and exposes a simple HTTP API for creating image predictions and inspecting their status/results.

### Features

- **Generate images** from a text prompt via `/generate`.
- **List predictions** with optional status filtering via `/predictions`.
- **List processing jobs** via `/processing`.
- **Inspect a single prediction** via `/predictions/{prediction_id}`.
- **Stream generated files** for a prediction via `/predictions/{prediction_id}/files/{index}.{ext}`.
- **Rate limiting** powered by `fastapi-limiter` and Redis.
- **API key protection** using the `X-API-Key` header.

### Requirements

- Python 3.10+
- Redis instance (for rate limiting)
- Replicate account and API token

### Environment variables

Set the following variables (for local dev you can use a `.env` file with `python-decouple`):

- **`REDIS_URL`** – Redis connection URL (e.g. `redis://localhost:6379/0`).
- **`API_ACCESS_KEY`** – value expected in the `X-API-Key` header.
- **`REPLICATE_API_TOKEN`** – your Replicate API token.
- **`REPLICATE_MODEL`** – Replicate model identifier.
- **`REPLICATE_MODEL_VERSION`** – specific version ID for the chosen model.

### Installation

```bash
pip install -r requirements.txt
```

### Running the API

From the project root:

```bash
uvicorn main:app --reload
```

The server will start on `http://127.0.0.1:8000` by default.

### Usage

**Generate an image**

```bash
curl -X POST "http://127.0.0.1:8000/generate" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"prompt": "TOK a portrait of a dog in a studio"}'
```

The response includes a prediction ID you can use with the other endpoints.

### Project structure

- **`main.py`** – FastAPI application, routes, middleware.
- **`helpers/_replicate.py`** – Replicate client helpers.
- **`helpers/schemas.py`** – Pydantic response models.
- **`helpers/fetchers.py`** – async HTTP file fetching.
- **`helpers/ratelimiting.py`** – rate limiting lifespan setup.
