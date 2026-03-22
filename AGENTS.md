# AGENTS.md

## Cursor Cloud specific instructions

### Overview

PhotoMeAI is a full-stack AI image generation app with two services:
- **Backend**: Python FastAPI (port 8000) — wraps the Replicate API for image generation, with Redis-based rate limiting and optional S3 storage.
- **Frontend**: React + Vite + TypeScript (port 5173) — prompt UI that talks to the backend.

### Required secrets (injected as env vars)

`REPLICATE_API_TOKEN`, `REPLICATE_MODEL`, `REPLICATE_MODEL_VERSION`, `REDIS_URL`, `API_ACCESS_KEY`, `VITE_API_KEY`. AWS creds (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are optional but needed for S3 upload in prediction detail view.

### .env files

Both services read config from `.env` files (via `python-decouple` / Vite). Before starting services, generate `.env` files from the injected env vars:
- `backend/.env` — needs `REPLICATE_API_TOKEN`, `REPLICATE_MODEL`, `REPLICATE_MODEL_VERSION`, `REDIS_URL`, `API_ACCESS_KEY`, and optionally `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
- `frontend/.env` — needs `VITE_API_BASE_URL=http://localhost:8000` and `VITE_API_KEY` (must match backend `API_ACCESS_KEY`).

### Running services

See `README.md` for standard commands. Start order: backend first, then frontend.

- **Backend**: `cd backend && source .venv/bin/activate && uvicorn main:app --reload`
- **Frontend**: `cd frontend && npm run dev`

### Gotchas

- The `redis` Python package is **not listed** in `requirements.txt` but is required by `helpers/ratelimiting.py` (`import redis.asyncio`). The update script installs it explicitly.
- `fastapi-limiter` must be pinned to `<0.2` — version 0.2.0 removed the `FastAPILimiter` class that the codebase imports.
- `REDIS_URL` is a hosted Upstash Redis (`rediss://`). No local Redis server is needed.
- `tsc --noEmit` reports errors on `import.meta.env` because `src/vite-env.d.ts` is missing. This is a pre-existing issue; `npm run build` (Vite) succeeds regardless.
- The frontend has no dedicated lint script or ESLint config. `npm run build` is the primary quality check.
