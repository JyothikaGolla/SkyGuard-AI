# Deploy SkyGuard AI on Render

This project can be deployed on Render as a single Python Web Service that serves both:
- Backend API (`/api/*`)
- Frontend website (`/`, `index.html`, `dashboard.html`, etc.)

## 1) Push code to GitHub

Make sure your latest branch is pushed.

## 2) Create Web Service on Render

1. Go to Render Dashboard.
2. Click **New +** -> **Blueprint**.
3. Connect your GitHub repository.
4. Render will detect `render.yaml` and create the `skyguard-ai` service.

If you prefer manual setup, use:
- Environment: `Python`
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn src.serving.api:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120`

## 3) Set required environment variables

In Render service settings, configure:
- `DATABASE_URL` (paste your Render Postgres connection string)
- `OPENWEATHER_API_KEY` (required for weather features)
- `JWT_SECRET_KEY` (auto-generated if using `render.yaml`)
- `SMTP_USER` and `SMTP_PASSWORD` (optional, for email alerts)
- `SMTP_FROM_EMAIL` and `SMTP_FROM_NAME` (optional)

Optional:
- `FLASK_ENV=production`
- `FLASK_DEBUG=False`

## 4) Migrate existing local data

If you want your current users and saved records to show up on the deployed website, run:

```bash
python migrate_sqlite_to_postgres.py --target "your-render-postgres-url"
```

Then set `DATABASE_URL` on Render to the same Postgres URL.

## 5) Deploy and verify

After deployment, open your Render URL:
- Homepage: `/`
- Health check: `/api/health`

You should be able to use login/signup and the flight dashboard from the same domain.

## Notes

- Local development uses SQLite by default.
- Render production should use Postgres so your data survives restarts and redeploys.
