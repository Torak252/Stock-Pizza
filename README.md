# 🍕 Stock Pizza Tracker

An OSINT pipeline and dashboard that watches off-hours activity around Fortune 500 headquarters and tests whether it precedes stock moves. It is inspired by the "Pentagon Pizza Index".

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full Phase 1 spec, the data-source legality matrix, and the scoring math.

```
stock_pizza_tracker/
├── backend/
│   ├── pizza_tracker/
│   │   ├── api/main.py          # FastAPI: /companies, /spikes, /companies/{t}/readings|samples|sources
│   │   ├── analytics/           # baseline.py (median/MAD), scoring.py (POI), correlation.py (event study)
│   │   ├── collectors/          # http.py (polite client), places.py (OSM), cameras.py (Caltrans/WSDOT),
│   │   │                        # foot_traffic.py (BestTime/synthetic), market.py (yfinance/EDGAR)
│   │   ├── vision/detector.py   # YOLO vehicle counting (optional extra)
│   │   ├── seed/fortune10.json  # starter set: 2025 Fortune 10
│   │   ├── pipeline.py          # jobs: map → collect → score
│   │   ├── models.py, db.py, config.py, cli.py
│   └── tests/
├── frontend/                    # Next.js + Tailwind + react-leaflet dashboard
├── infra/                       # TimescaleDB init + hypertable migration
└── docker-compose.yml
```

## Quick start (no API keys, synthetic data)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pizza_tracker.cli demo          # seeds Fortune 10 + 6 weeks of synthetic activity
uvicorn pizza_tracker.api.main:app --reload
pytest

# frontend (new terminal)
cd frontend
npm install
npm run dev                               # http://localhost:3000
```

## Real data

```bash
cp .env.example .env                      # add SPT_CONTACT_EMAIL, and optionally WSDOT / BestTime keys
docker compose up -d db
python -m pizza_tracker.cli init
python -m pizza_tracker.cli map           # OSM venues + nearby DOT cameras
pip install -e ".[vision]"                # optional: YOLO camera counting
python -m pizza_tracker.cli worker        # collect every 10 min, score every 10 min
```

Or run everything with `docker compose up --build`.

> Research tool. Signals are statistical anomalies in public data, not investment advice.
