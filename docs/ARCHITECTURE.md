# Stock Pizza Tracker: Architecture & Technical Spec

## 0. Goal and honest framing

**Operating constraints (decided):** free data only, research only (no trading), and it runs locally.

Detect **statistically unusual late-night activity** (7 PM to 3 AM, HQ local time) around Fortune 500 headquarters and test whether it **precedes** price volatility or unscheduled corporate events (8-K, M&A filings).

Three constraints shape the design:

1. **Scheduled events are priced in.** Late nights before a *known* earnings date are expected. The signal worth finding is a spike that no scheduled event explains. The correlation engine labels events as `scheduled` vs `surprise` and reports the two groups separately.
2. **Big campuses are noisy.** Apple Park and the Googleplex have in-house food, and Amazon HQ sits inside dense city blocks. The per-HQ baseline makes the index relative to the site's own normal, and camera ROIs (gate lanes, not the whole freeway) cut the noise further.
3. **No history comes back.** DOT cameras don't archive and live busyness is only live. A backtest needs months of self-collected data, so the pipeline has to start collecting on day 1 even before the model is good.

## 1. Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | **FastAPI** (Python 3.11+) | Same language as the data and ML code; async-ready; OpenAPI docs for free |
| Scheduling | **APScheduler** | One local process is enough for 10 HQs |
| Scraping / HTTP | **httpx** + shared `PoliteClient` | Per-host rate limit, backoff, `Retry-After`, honest UA. Every Phase 1 source is an API, so no headless browser is needed |
| Storage | **SQLite** by default; PostgreSQL + TimescaleDB optional via Docker | SQLite handles 10 HQs × a few metrics every 5 min for years. Switch when scaling to the Fortune 500 |
| ORM | **SQLAlchemy 2.0** | Works on both SQLite and Postgres |
| Computer vision | **Ultralytics YOLO11n** + **OpenCV** (optional `[vision]` extra) | Runs on CPU for stills every 2–5 min. Fine-tune later for a `delivery_vehicle` class |
| Market data | **yfinance** + **SEC EDGAR** submissions API | Both free. EDGAR is official and timestamped to the second, which makes it the best label source |
| Frontend | **Next.js 16 (App Router) + React 19 + Tailwind v4 + react-leaflet** | Leaflet + CARTO dark tiles need no API key. Swap to Mapbox GL later if you want 3D/heatmaps |
| Run | Local: `uvicorn` + `cli worker` + `npm run dev` | Docker Compose is kept as an option |

## 2. Data pipeline strategy: legal and reliable acquisition

**Principle: only use sources that allow automated access, so there's never anything to evade.** No proxy rotation, CAPTCHA solving or fingerprint spoofing. If a source needs those, it isn't a source we use.

| Signal | Source | Access status | Notes |
|---|---|---|---|
| Venue discovery | OpenStreetMap **Overpass API** | ✅ Open (ODbL, attribution required) | One-off mapping job. Cache results for weeks |
| HQ geocoding | OpenStreetMap **Nominatim** | ✅ Open; ≤ 1 req/s, real User-Agent | `cli verify`, run by hand |
| ~~Venue busyness~~ | BestTime / Advan / Dewey | 💲 Paid only | **Not used** (free-data constraint). There is no free, terms-compliant live busyness source. Only `cli demo` uses synthetic busyness |
| ~~Google Popular Times~~ | — | ❌ No API; scraping Maps violates Google ToS | Deliberately **not** implemented. `populartimes`-style scrapers break often and create legal exposure |
| ~~Domino's / Papa John's order data~~ | — | ❌ Private, ToS-protected | Not available. We watch the *venue's busyness*, not its orders |
| Traffic cameras (CA) | **Caltrans CWWP2** CCTV JSON | ✅ Public, documented | Stills refresh every 1–5 min. Poll no faster than that |
| Traffic cameras (WA) | **WSDOT Traveler API** | ✅ Free access code | |
| Traffic cameras (PA) | **511PA** developer API (shared "511" platform) | ✅ Free key | Parser handles both known payload shapes. Not yet run against the live API |
| Traffic cameras (TX, MN, RI, NE, AR) | Individual public stills, added with `cli add-camera` | ⚠️ Check each site's terms | Some states only allow embedding, not redistribution. Store counts, never frames |
| Traffic speed/density | TomTom / HERE traffic flow APIs | ⚠️ Free tiers exist, but their terms limit use | Not used yet. Candidate fallback where no camera sits near a gate |
| Prices | yfinance | ⚠️ Unofficial Yahoo wrapper | Fine for personal research, which is the scope |
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
- **Research only:** nothing here places trades. If that ever changes, get a securities lawyer to review the sources first; the `provider` column is the audit trail.

## 3. Analytics

**Normal Activity Index (baseline):** for each `(company, metric, local weekday, local hour)`, take the median and MAD over the last 8 weeks. Scale = `max(1.4826·MAD, per-metric noise floor, 10% of median)`. Median/MAD means past crunches don't inflate the baseline and hide future ones. A partial current hour is compared only with the same elapsed minutes of past hours.

**Pizza & Overtime Index (POI):** a weighted Stouffer combination of per-metric robust z-scores:
`POI = Σ wᵢ·zᵢ / √Σ wᵢ²` with weights delivery vehicles 1.5, parking 1.2, venue busyness 1.0, general traffic 0.8.
Levels are elevated ≥ 2, high ≥ 3, extreme ≥ 4. **Alerts only fire during off-hours** (19:00–03:00 HQ local).

**Correlation engine** (`analytics/correlation.py`):
- *Volatility study:* mean |h-day forward log return| after spike evenings vs a permutation null of random days. Returns are measured from the last close *before* the spike (a Monday-night spike from Monday's close, a Saturday spike from Friday's), so the test never uses a price set after the spike.
- *Scheduled vs surprise:* earnings dates, 10-Qs and 10-Ks are marked scheduled. The report counts spike evenings with no scheduled event in the next 10 days ("unexplained"), and compares how often 8-Ks and M&A forms follow a spike against how often they follow any trading day.
- Run it with `python -m pizza_tracker.cli study`.
- *Precedence:* the share of spikes followed by an 8-K/M&A filing within k days, compared with the base rate.
- Planned for Phase 3: control for the market (SPY-adjusted abnormal returns), apply Benjamini–Hochberg correction across the 10 tickers × horizons, and use walk-forward evaluation only.

## 4. Signal coverage with free data

Live signals come from **DOT cameras only**, counted with YOLO:

| HQ | Free camera feed | Status |
|---|---|---|
| Apple (Cupertino), Alphabet (Mountain View) | Caltrans District 4 | ✅ Implemented |
| Amazon (Seattle) | WSDOT (free access code) | ✅ Implemented |
| Cencora (Conshohocken) | 511PA (free developer key) | ✅ Implemented, not yet run live |
| Exxon Mobil, McKesson (TX) | TxDOT / DriveTexas | ✍️ Manual: `cli add-camera` |
| UnitedHealth (MN) | MnDOT / 511MN | ✍️ Manual: `cli add-camera` |
| CVS (RI) | RIDOT | ✍️ Manual: `cli add-camera` |
| Berkshire (NE), Walmart (AR) | Nebraska 511 / IDriveArkansas | ✍️ Manual; freeway cameras may be too far from the HQ to help |

"Manual" means: find a public camera still near the campus on the state DOT's traveller map, copy its image URL, and register it:

```bash
python -m pizza_tracker.cli add-camera --ticker XOM --name "I-45 at Rayford Rd" \
    --url https://.../camera.jpg --lat 30.09 --lon -95.43
```

Every camera, found automatically or added by hand, can be turned off on the dashboard if it shows no campus entrance; its past counts are kept.

## 5. Phase roadmap

| Phase | Deliverable |
|---|---|
| **1** | Schema, collectors, baseline + POI scoring, event-study code, REST API, dashboard, synthetic demo, tests |
| **2** | Free-data, local-first mode; daily market + EDGAR ingestion; `cli study` report; demo/real database guards |
| **3a** | Tooling for the manual checks: `cli verify` (Nominatim geocoding), a gate-lane (ROI) editor with live YOLO preview on the dashboard |
| **3b** | 511PA provider; `cli add-camera` for any public still; per-camera on/off switch |
| 3c | Run the manual checks locally, add cameras for the remaining HQs, start collecting 24/7 |
| 4 | After ~3 months of data: SPY-adjusted returns, Benjamini–Hochberg correction across tickers, predictive dashboard page |
| 5 | Scale toward the Fortune 500 (CSV import + geocoding, Postgres, queue-based workers) |
