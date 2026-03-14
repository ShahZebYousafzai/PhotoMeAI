# PhotoMeAI

PhotoMeAI is a full-stack application for AI-powered image generation. It uses [Replicate](https://replicate.com) to run an image generation model and exposes a FastAPI backend with a React + Vite frontend.

## How to run the project

1. **Prerequisites**: Python 3.10+, Node.js (v18+), Redis, and a [Replicate](https://replicate.com/account/api-tokens) API token.
2. **Backend**: From project root, run:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   # source .venv/bin/activate     # macOS/Linux
   pip install -r requirements.txt
   ```
   Create `backend/.env` with your Replicate token, Redis URL, and `API_ACCESS_KEY` (see [Environment variables](#environment-variables)).
   ```bash
   uvicorn main:app --reload
   ```
   API: **http://127.0.0.1:8000**
3. **Frontend**: In a new terminal:
   ```bash
   cd frontend
   npm install
   ```
   Create `frontend/.env` with `VITE_API_BASE_URL=http://localhost:8000` and `VITE_API_KEY` matching backend `API_ACCESS_KEY`.
   ```bash
   npm run dev
   ```
   App: **http://localhost:5173**
4. **Use**: Ensure Redis is running, then open **http://localhost:5173** in your browser.

Detailed setup (virtual env, env files, optional Redis) is in [Quick start](#quick-start) below.

## Features

- **Generate images** from text prompts via the API or UI
- **List and inspect predictions** (status, output files)
- **Stream generated images** from prediction results
- **Rate limiting** (Redis + fastapi-limiter)
- **API key protection** via `X-API-Key` header

## Project structure

```
PhotoMeAI/
├── backend/          # FastAPI API (Python)
│   ├── main.py       # App, routes, middleware
│   ├── helpers/      # Replicate client, schemas, fetchers, rate limiting
│   ├── data/         # Generated images (created at runtime)
│   └── notebooks/    # Jupyter notebooks
├── frontend/         # React + Vite + TypeScript
│   └── src/
└── README.md
```

## Prerequisites

- **Python 3.10+**
- **Node.js** (v18+ recommended) and npm
- **Redis** (for rate limiting; e.g. [Upstash](https://upstash.com) for a hosted option)
- **Replicate account** and [API token](https://replicate.com/account/api-tokens)

## Quick start

### 1. Backend

1. **Create and activate a virtual environment** (recommended):

   ```bash
   cd backend
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

2. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment** – create a `.env` file in `backend/` with:

   ```env
   REPLICATE_API_TOKEN=your_replicate_api_token
   REPLICATE_MODEL=shahzebyousafzai/super-shah
   REPLICATE_MODEL_VERSION=664a305263b83d16bfc59abe7e75253be4d01544f9416a0179cf25ace9aec69c
   REDIS_URL=redis://localhost:6379/0
   API_ACCESS_KEY=your-secret-api-key
   ```

   Replace with your Replicate token, Redis URL, and a secret value for `API_ACCESS_KEY` (the frontend will send this in `X-API-Key`).

4. **Run the API** (from the `backend/` directory):

   ```bash
   uvicorn main:app --reload
   ```

   The API will be available at **http://127.0.0.1:8000**.

### 2. Frontend

1. **Install dependencies**:

   ```bash
   cd frontend
   npm install
   ```

2. **Configure environment** – create a `.env` file in `frontend/` (or copy from `.env.example`):

   ```env
   VITE_API_BASE_URL=http://localhost:8000
   VITE_API_KEY=your-secret-api-key
   ```

   `VITE_API_KEY` must match the backend `API_ACCESS_KEY`.

3. **Run the dev server** (from the `frontend/` directory):

   ```bash
   npm run dev
   ```

   The app will be at **http://localhost:5173**.

### 3. Run order

Run services in this order:

1. **Redis** – Start Redis if you’re running locally (or use a hosted URL like Upstash in `.env`).
2. **Backend** – From `backend/`: `uvicorn main:app --reload`. API at **http://127.0.0.1:8000**.
3. **Frontend** – From `frontend/`: `npm run dev`. App at **http://localhost:5173**.
4. Open **http://localhost:5173** in your browser to use the app.

## Environment variables

### Backend (`backend/.env`)

| Variable | Description |
|----------|-------------|
| `REPLICATE_API_TOKEN` | Replicate API token |
| `REPLICATE_MODEL` | Replicate model identifier (e.g. `owner/model-name`) |
| `REPLICATE_MODEL_VERSION` | Model version ID |
| `REDIS_URL` | Redis connection URL (e.g. `redis://localhost:6379/0` or Upstash URL) |
| `API_ACCESS_KEY` | Secret key; clients must send this in the `X-API-Key` header |
| `AWS_ACCESS_KEY_ID` | AWS access key (for S3 uploads) |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (for S3 uploads) |
| `S3_BUCKET` | S3 bucket name (default: `photome-ai-bucket`) |
| `S3_REGION` | AWS region (default: `us-east-1`) |
| `S3_PREFIX` | Key prefix under bucket (default: `data`) |

### Frontend (`frontend/.env`)

| Variable | Description |
|----------|-------------|
| `VITE_API_BASE_URL` | Backend API base URL (e.g. `http://localhost:8000`) |
| `VITE_API_KEY` | Must match backend `API_ACCESS_KEY` |

## API overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/generate` | Create an image generation prediction (body: `prompt`, `num_outputs`, etc.) |
| `GET` | `/predictions` | List all predictions (optional `?status=`) |
| `GET` | `/processing` | List predictions with status `processing` |
| `GET` | `/predictions/{id}` | Get prediction details and output file URLs |
| `POST` | `/predictions/{id}/save` | Upload prediction outputs to S3 (`bucket/data/{prediction_id}/`) |
| `GET` | `/predictions/{id}/files/{index}.{ext}` | Stream a generated image file |

All requests (except CORS preflight) require the header: `X-API-Key: <your API_ACCESS_KEY>`.

For more details and examples, see [backend/README.md](backend/README.md).

## Scripts

**Frontend**

- `npm run dev` – Start Vite dev server
- `npm run build` – Production build
- `npm run preview` – Preview production build

**Backend**

- Run with: `uvicorn main:app --reload` (from `backend/`)