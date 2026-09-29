# Stock Pizza Tracker: Phase 1 Architecture & Technical Spec

## 0. Goal and honest framing

Detect **statistically unusual late-night activity** (7 PM to 3 AM, HQ local time) around Fortune 500 headquarters and test whether it **precedes** price volatility or unscheduled corporate events (8-K, M&A filings).

Three constraints shape the design:

1. **Scheduled events are priced in.** Late nights before a *known* earnings date are expected. The signal worth finding is a spike that no scheduled event explains. The correlation engine labels events as `scheduled` vs `surprise` and reports the two groups separately.
2. **Big campuses are noisy.** Apple Park and the Googleplex have in-house food, and Amazon HQ sits inside dense city blocks. The per-HQ baseline makes the index relative to the site's own normal, and camera ROIs (gate lanes, not the whole freeway) cut the noise further.
3. **No history comes back.** DOT cameras don't archive and live busyness is only live. A backtest needs months of self-collected data, so the pipeline has to start collecting on day 1 even before the model is good.

## 1. Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI** (Python 3.11+) | Same language as the data and ML code; async-ready; OpenAPI docs for free |
| Scheduling | **APScheduler** (Phase 1) → **Prefect** or **Celery + Redis** (Phase 2+) | One process is enough for 10 HQs. Move to a queue once camera/CV fan-out needs workers |
| Scraping / HTTP | **httpx** + shared `PoliteClient` | Per-host rate limit, backoff, `Retry-After`, honest UA. Every Phase 1 source is an API, so no headless browser is needed |
| Storage | **PostgreSQL 16 + TimescaleDB** (SQLite for dev/tests) | Hypertables for time series, retention policies, continuous aggregates for hourly rollups |
| ORM | **SQLAlchemy 2.0** | Works on both SQLite and Postgres |
| Computer vision | **Ultralytics YOLO11n** + **OpenCV** (optional `[vision]` extra) | Runs on CPU for stills every 2–5 min. Fine-tune later for a `delivery_vehicle` class |
| Market data | **yfinance** (research) → Polygon / Alpaca (prod); **SEC EDGAR** submissions API | EDGAR is official, free and timestamped to the second, which makes it the best label source |
| Frontend | **Next.js 16 (App Router) + React 19 + Tailwind v4 + react-leaflet** | Leaflet + CARTO dark tiles need no API key. Swap to Mapbox GL later if you want 3D/heatmaps |
| Deploy | **Docker Compose** (db, api, worker, web) | One command locally; the same images deploy to Fly.io / Render / a single VPS |

## 2. Data pipeline strategy: legal and reliable acquisition

**Principle: only use sources that allow automated access, so there's never anything to evade.** No proxy rotation, CAPTCHA solving or fingerprint spoofing. If a source needs those, it isn't a source we use.

| Signal | Source | Access status | Notes |
|---|---|---|---|
| Venue discovery | OpenStreetMap **Overpass API** | ✅ Open (ODbL, attribution required) | One-off mapping job. Cache results for weeks |
| Venue busyness | **BestTime.app** (or Advan/Dewey for historical foot traffic) | ✅ Licensed, paid | This replaces Google Popular Times |
| ~~Google Popular Times~~ | — | ❌ No API; scraping Maps violates Google ToS | Deliberately **not** implemented. `populartimes`-style scrapers break often and create legal exposure |
| ~~Domino's / Papa John's order data~~ | — | ❌ Private, ToS-protected | Not available. We watch the *venue's busyness*, not its orders |
| Traffic cameras (CA) | **Caltrans CWWP2** CCTV JSON | ✅ Public, documented | Stills refresh every 1–5 min. Poll no faster than that |
| Traffic cameras (WA) | **WSDOT Traveler API** | ✅ Free access code | |
| Traffic cameras (TX, MN, AR, NE, RI, PA) | State 511 / DOT feeds | ⚠️ To be added per state; check each one's terms | Some states only allow embedding, not redistribution. Store counts, never frames |
| Traffic speed/density | TomTom / HERE traffic flow APIs | ✅ Paid, free tier | Good fallback where no camera sits near a gate |
| Prices | yfinance → Polygon/Alpaca | ⚠️ yfinance is unofficial | OK for research. Use a licensed feed for anything live |
| Filings | **SEC EDGAR** | ✅ Official; ≤10 req/s; UA must include a contact email | `SPT_CONTACT_EMAIL` is required |

**Reliability tactics** (in `collectors/http.py`):
- Per-host minimum interval (e.g. 5 s for Overpass, 0.15 s for EDGAR, and each camera's own refresh rate).
- Exponential backoff that respects `Retry-After` on 429/503.
- Short response cache so one scheduler cycle never reads the same URL twice.
- Each collector fails independently and logs the error; it never takes down the job.
- A provider with no credentials is skipped, not crashed.

**Privacy & compliance:**
- Camera frames are decoded in memory, counted, and discarded (`SPT_STORE_CAMERA_FRAMES=false`). No plates, faces or images are stored.
- We aggregate at the campus level only and never track individuals.
- **MNPI:** observing public roads and public busyness data is generally treated as alternative data, not inside information. Before any live trading use, get a securities lawyer to review the sources, and keep a source log (the `provider` column) for audit.

## 3. Analytics

**Normal Activity Index (baseline):** for each `(company, metric, local weekday, local hour)`, take the median and MAD over the last 8 weeks. Scale = `max(1.4826·MAD, per-metric noise floor, 10% of median)`. Median/MAD means past crunches don't inflate the baseline and hide future ones. A partial current hour is compared only with the same elapsed minutes of past hours.

**Pizza & Overtime Index (POI):** a weighted Stouffer combination of per-metric robust z-scores:
`POI = Σ wᵢ·zᵢ / √Σ wᵢ²` with weights delivery vehicles 1.5, parking 1.2, venue busyness 1.0, general traffic 0.8.
Levels are elevated ≥ 2, high ≥ 3, extreme ≥ 4. **Alerts only fire during off-hours** (19:00–03:00 HQ local).

**Correlation engine** (`analytics/correlation.py`):
- *Volatility study:* mean |h-day forward log return| after spike nights vs a permutation null of random nights. A weekend spike maps to Monday's session.
- *Precedence:* the share of spikes followed by an 8-K/M&A filing within k days, compared with the base rate.
- Planned for Phase 3: control for the market (SPY-adjusted abnormal returns), apply Benjamini–Hochberg correction across the 10 tickers × horizons, and use walk-forward evaluation only.

## 4. Phase roadmap

| Phase | Deliverable |
|---|---|
| **1 (this PR)** | Schema, collectors, baseline + POI scoring, event-study code, REST API, dashboard, synthetic demo, tests |
| 2 | Verify HQ coordinates and draw gate ROIs; add BestTime key; add TX/MN/PA/RI/NE/AR camera providers; enable YOLO counting; start the 24/7 collector |
| 3 | EDGAR + earnings ingestion job; SPY-adjusted event study; predictive dashboard page |
| 4 | Scale to Fortune 500 (CSV import + geocoding); queue-based workers; alerting (Discord, reusing `reporting/discord.py`) |
| 5 | Optional: expose POI as a feature to the existing Algotrader strategies, paper-trading only |
