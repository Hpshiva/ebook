# Deployment

## Local (free)

```bash
./start.sh
```

Data is stored in `backend/data/creator_finder.db`. Back this file up to keep your creators.

## Environment variables

See `.env.example`. For anything beyond your own laptop set:

- `SECRET_KEY`: a long random value
- `DATABASE_URL`: a PostgreSQL URL (add `psycopg[binary]` to `backend/requirements.txt`)
- `APIFY_TOKEN`: only if you use live collection
- `CORS_ORIGINS`: only if the frontend is hosted on a different domain from the API

## One service (simplest)

The backend serves the built frontend, so a single web service is enough.

- **Build:** `cd frontend && npm ci && npm run build && cd ../backend && pip install -r requirements.txt`
- **Start:** `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Or use the included `Dockerfile` (it does both steps).

This fits Render, Railway, Fly.io or any VPS. Free tiers usually sleep when idle and have **no permanent disk**, so SQLite data is lost on restart there. Use a hosted PostgreSQL (for example the Supabase or Neon free tier) for anything you want to keep.

## Separate frontend

Host `frontend/dist` on any static host (Netlify, Vercel, Cloudflare Pages). Build with `VITE_API_URL=https://your-api-host` and add the frontend's origin to `CORS_ORIGINS` on the backend.

## PostgreSQL

Tables are created automatically on first start. `docker-compose.yml` runs the app with PostgreSQL locally (not tested on the build machine, which has no Docker). Before changing table definitions in production, add Alembic migrations.

## Before real client use

1. Serve over HTTPS only.
2. Set `SECRET_KEY` and a strong admin password.
3. Use PostgreSQL with backups.
4. Do one small confirmed Apify run and check the Cost & Usage page against your Apify console.
5. Review Instagram's terms and the data-protection rules for the countries you target.

Streamlit Community Cloud is not used: the product is a React + FastAPI app, which Streamlit does not host.
