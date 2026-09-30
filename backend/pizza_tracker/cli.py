"""Command-line entry point.

    python -m pizza_tracker.cli doctor        # test every live data source, with a fix for each failure
    python -m pizza_tracker.cli init          # create tables + seed Fortune 10
    python -m pizza_tracker.cli verify        # geocode HQ addresses vs stored coords (--apply to save)
    python -m pizza_tracker.cli map           # discover nearby venues (OSM) and DOT cameras
    python -m pizza_tracker.cli add-camera --ticker XOM --name "I-45 at Rayford" --url https://...jpg
    python -m pizza_tracker.cli market        # daily bars, earnings dates, SEC filings
    python -m pizza_tracker.cli worker        # camera counting + scoring + daily market refresh
    python -m pizza_tracker.cli study         # spike vs. price / filing report
    python -m pizza_tracker.cli demo          # synthetic data so the dashboard works offline
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import pipeline
from .db import SessionLocal, init_db
from .models import SignalSource
from .seed import seed_companies

log = logging.getLogger("pizza_tracker")


def _has_demo_data(session: Session) -> bool:
    return session.scalar(select(SignalSource.id).where(SignalSource.provider == "synthetic").limit(1)) is not None


def _has_real_data(session: Session) -> bool:
    return session.scalar(select(SignalSource.id).where(SignalSource.provider != "synthetic").limit(1)) is not None


def format_verify(rows: list[dict], applied: bool) -> str:
    lines = [f"{'ticker':<7}{'shift':>9}  geocoder match"]
    for r in rows:
        shift = "no hit" if r["shift_m"] is None else f"{r['shift_m']:,} m"
        flag = "  <-- check" if r["shift_m"] is None or r["shift_m"] > 500 else ""
        lines.append(f"{r['ticker']:<7}{shift:>9}  {(r['match'] or r['address'])[:80]}{flag}")
    lines.append("Saved geocoded coordinates." if applied else
                 "Dry run. Shifts > 500 m deserve a look on a map; rerun with --apply to save.")
    return "\n".join(lines)


def run_worker() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    try:
        import ultralytics  # noqa: F401
    except ImportError:
        sys.exit('Camera counting needs the vision extra: pip install -e ".[vision]"')

    def job(fn, *args):
        def run():
            with SessionLocal() as s:
                log.info("%s -> %s", fn.__name__, fn(s, *args))
        run.__name__ = fn.__name__
        return run

    with SessionLocal() as s:
        if not s.scalar(select(SignalSource.id).where(SignalSource.kind == "camera").limit(1)):
            log.info("no cameras yet: mapping cameras near each HQ (one-off, ~1 min)")
            log.info("cameras mapped: %s", pipeline.map_cameras(s))

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    sched = BlockingScheduler(timezone="UTC")

    def every(fn, minutes: int, first_in_s: int = 0):
        sched.add_job(job(fn), "interval", minutes=minutes, max_instances=1, coalesce=True,
                      name=fn.__name__, next_run_time=now + timedelta(seconds=first_in_s))

    # Cameras every 2 min: most DOT stills refresh every 1-5 min, and short stops need consecutive frames.
    every(pipeline.collect_camera_counts, 2)
    every(pipeline.collect_skies, 2, first_in_s=20)
    every(pipeline.score_all, 5, first_in_s=240)
    # Market data once a day after the US close (22:30 UTC), plus once at startup.
    sched.add_job(job(pipeline.ingest_market), "cron", hour=22, minute=30, name="ingest_market")
    sched.add_job(job(pipeline.ingest_market), name="ingest_market (startup)", next_run_time=now + timedelta(seconds=60))
    sched.start()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="pizza_tracker")
    p.add_argument("command", choices=["doctor", "init", "verify", "map", "add-camera", "market", "worker", "study", "demo"])
    p.add_argument("--horizon", type=int, default=5, help="study: forward-return horizon in trading days")
    p.add_argument("--apply", action="store_true", help="verify: save geocoded coordinates")
    p.add_argument("--ticker", help="add-camera: company ticker")
    p.add_argument("--name", help="add-camera: label, e.g. the cross streets")
    p.add_argument("--url", help="add-camera: public still-image URL")
    p.add_argument("--lat", type=float, help="add-camera: camera latitude (defaults to the HQ)")
    p.add_argument("--lon", type=float, help="add-camera: camera longitude (defaults to the HQ)")
    args = p.parse_args()

    if args.command == "doctor":
        from .doctor import format_checks, run_checks

        results = run_checks()
        print(format_checks(results))
        sys.exit(1 if any(r.status == "fail" for r in results) else 0)

    init_db()
    with SessionLocal() as s:  # type: Session
        seed_companies(s)
        if args.command in ("verify", "map", "add-camera", "market", "worker") and _has_demo_data(s):
            sys.exit("This database holds synthetic demo data. Point SPT_DATABASE_URL at a separate DB for real collection.")
        if args.command == "demo" and _has_real_data(s):
            sys.exit("demo wipes readings and samples; refusing to run on a database with real sources.")
        if args.command == "init":
            print("database ready")
        elif args.command == "verify":
            print(format_verify(pipeline.verify_hqs(s, apply=args.apply), args.apply))
        elif args.command == "map":
            print(f"venues added: {pipeline.map_venues(s)}")
            print(f"cameras added: {pipeline.map_cameras(s)}")
        elif args.command == "add-camera":
            if not (args.ticker and args.name and args.url):
                p.error("add-camera needs --ticker, --name and --url")
            try:
                src = pipeline.add_manual_camera(s, args.ticker, args.name, args.url, args.lat, args.lon)
            except ValueError as exc:
                sys.exit(str(exc))
            print(f"added camera {src.id} ({src.distance_m:.0f} m from HQ). Mark its gate lanes on the dashboard.")
        elif args.command == "market":
            print(pipeline.ingest_market(s))
        elif args.command == "study":
            from .study import format_report, run_study

            print(format_report(run_study(s, horizon=args.horizon), args.horizon))
        elif args.command == "demo":
            print(f"synthetic samples: {pipeline.seed_demo(s)}")
    if args.command == "worker":
        run_worker()


if __name__ == "__main__":
    main()
