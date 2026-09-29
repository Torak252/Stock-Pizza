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
│   │   │                        # foot_traffic.py (synthetic, demo only), market.py (yfinance/EDGAR)
│   │   ├── vision/detector.py   # YOLO vehicle counting (optional extra)
│   │   ├── seed/fortune10.json  # starter set: 2025 Fortune 10
│   │   ├── pipeline.py          # jobs: map → collect → score, plus market ingestion
│   │   ├── study.py             # `cli study` research report
│   │   ├── models.py, db.py, config.py, cli.py
│   └── tests/
├── frontend/                    # Next.js + Tailwind + react-leaflet dashboard
├── infra/                       # TimescaleDB init + hypertable migration
└── docker-compose.yml
```

Runs locally on free data only, for research. There is no trading.

## 1. Try it offline (synthetic data)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
SPT_DATABASE_URL=sqlite:///./demo.db python -m pizza_tracker.cli demo
SPT_DATABASE_URL=sqlite:///./demo.db uvicorn pizza_tracker.api.main:app --reload
pytest

# new terminal
cd frontend && npm install && npm run dev               # http://localhost:3000
```

## 2. Collect real data

```bash
cd backend
cp .env.example .env                  # set SPT_CONTACT_EMAIL; add a free WSDOT code for Seattle
pip install -e ".[vision]"            # YOLO camera counting (CPU is fine)
python -m pizza_tracker.cli map       # find OSM venues + nearby Caltrans/WSDOT cameras
python -m pizza_tracker.cli worker    # leave running: counts every 5 min, scores every 10, market daily
uvicorn pizza_tracker.api.main:app    # dashboard API (separate terminal)
```

The real database (`pizza_tracker.db`) and the demo database are kept apart: `map`, `market` and `worker` refuse to run on demo data, and `demo` refuses to run on real data.

## 3. Research report

```bash
python -m pizza_tracker.cli market            # 2y daily bars, earnings dates, SEC filings
python -m pizza_tracker.cli study --horizon 5 # spike evenings vs |5-day return| and surprise 8-Ks
```

Cameras keep no archive, so the report only becomes meaningful after a few months of collection. Only Apple, Alphabet and Amazon have camera coverage so far; see docs/ARCHITECTURE.md §4.

Docker Compose (Postgres + TimescaleDB) is kept as an option: `docker compose up --build`.

> Research tool. Signals are statistical anomalies in public data, not investment advice.
