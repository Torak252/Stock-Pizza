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

## What's on screen

- **Overview** (`/`): DEFCON-style readiness, biggest all-nighters, HQ map, spike feed, watchlist.
- **HQ page** (`/hq/AAPL`, click any card): a YoshiTracker-style board, each panel live from a free source.

| Panel | Source | Refresh |
|---|---|---|
| Time since last 8-K · filings wire · informants (Form 4) · which day they file | SEC EDGAR | 5 min |
| Price · next earnings progress | Yahoo (yfinance) | 1 min |
| Traffic cams (auto-refreshing stills, lane editor) | Caltrans / WSDOT / 511PA / `cli add-camera` | 30 s |
| Pizza near HQ: today vs typical by hour; **short stops** at the gate (YOLO + frame-to-frame tracking) | cameras via the worker | 2 min |
| Skies over HQ: aircraft radar, private jets on approach | adsb.lol → airplanes.live (ADS-B) | 15 s |
| Environment: weather, AQI, sunset, moon · traffic vs free-flow | Open-Meteo · TomTom (free key) | 10 min · 2 min |

Run `python -m pizza_tracker.cli doctor` to see which of these work on your machine and what to fix.

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
cp .env.example .env                  # SPT_CONTACT_EMAIL; free keys: WSDOT (Seattle), 511PA (Conshohocken), TomTom (traffic)
python -m pizza_tracker.cli doctor    # checks every live source and says what to fix
pip install -e ".[vision]"            # YOLO camera counting (CPU is fine)
python -m pizza_tracker.cli verify    # geocode each HQ address; review shifts > 500 m on a map
python -m pizza_tracker.cli verify --apply
python -m pizza_tracker.cli map       # find OSM venues + nearby Caltrans/WSDOT cameras
uvicorn pizza_tracker.api.main:app    # dashboard API (separate terminal; keep it on localhost)
python -m pizza_tracker.cli worker    # leave running: counts every 5 min, scores every 10, market daily
```

**Mark the gate lanes** before trusting any counts. On the dashboard, open Apple, Alphabet or Amazon, click a camera, drag a box over only the lanes leading into the campus, and click **Save box**. **Preview detections** then runs YOLO on a live frame: green boxes are counted, grey are ignored. A camera with no box counts the whole frame, which mostly measures freeway traffic.

The real database (`pizza_tracker.db`) and the demo database are kept apart: `map`, `market` and `worker` refuse to run on demo data, and `demo` refuses to run on real data.

## 3. Research report

```bash
python -m pizza_tracker.cli market            # 2y daily bars, earnings dates, SEC filings
python -m pizza_tracker.cli study --horizon 5 # spike evenings vs |5-day return| and surprise 8-Ks
```

Cameras keep no archive, so the report only becomes meaningful after a few months of collection.

**Coverage.** `cli map` finds live cameras for 8 of the 10 HQs (Seattle city cameras beside Amazon; state DOT cameras elsewhere). See docs/ARCHITECTURE.md §4 for the per-HQ table, and add or exclude cameras in `backend/pizza_tracker/seed/cameras.json`.

Docker Compose (Postgres + TimescaleDB) is kept as an option: `docker compose up --build`.

> Research tool. Signals are statistical anomalies in public data, not investment advice.
