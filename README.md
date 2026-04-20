# hartecash

AutoCurb.io platform — private-party vehicle acquisition for franchise and
independent dealers.

## Layout

```
hartecash/
├── fsbo-data-platform/   # Data service: scrapes, classifies, serves listings
│                         # (Python / FastAPI / Postgres). Will be extracted
│                         # to its own repo once API contracts stabilize.
└── web/                  # AutoCurb dealer dashboard (Next.js 15). Consumes
                          # fsbo-data-platform via its REST API.
```

## Quickstart

In two terminals:

```bash
# Terminal 1 — data platform
cd fsbo-data-platform
cp .env.example .env
docker compose up -d postgres
pip install -e ".[dev]"
alembic upgrade head
uvicorn fsbo.api.main:app --reload
python -m fsbo.workers.poll --source craigslist --city tampa   # seed data

# Terminal 2 — dashboard
cd web
cp .env.example .env          # FSBO_API_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:3000
```

See each subdirectory's README for details.
