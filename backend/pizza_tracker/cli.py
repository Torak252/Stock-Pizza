"""Command-line entry point.

    python -m pizza_tracker.cli init          # create tables + seed Fortune 10
    python -m pizza_tracker.cli map           # discover nearby venues (OSM) and DOT cameras
    python -m pizza_tracker.cli demo          # synthetic history so the dashboard works offline
    python -m pizza_tracker.cli worker        # run the collection / scoring scheduler
"""
from __future__ import annotations

import argparse
import logging

from sqlalchemy.orm import Session

from . import pipeline
from .db import SessionLocal, init_db
from .seed import seed_companies

log = logging.getLogger("pizza_tracker")


def run_worker() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    from .collectors.foot_traffic import BestTimeProvider, SyntheticProvider
    from .config import get_settings

    provider = BestTimeProvider() if get_settings().besttime_api_key else SyntheticProvider()
    log.info("foot-traffic provider: %s", provider.name)

    def job(fn, *args):
        def run():
            with SessionLocal() as s:
                log.info("%s -> %s", fn.__name__, fn(s, *args))
        run.__name__ = fn.__name__
        return run

    sched = BlockingScheduler(timezone="UTC")
    sched.add_job(job(pipeline.collect_venue_busyness, provider), "interval", minutes=10, max_instances=1)
    sched.add_job(job(pipeline.score_all), "interval", minutes=10, max_instances=1)
    try:
        import ultralytics  # noqa: F401

        sched.add_job(job(pipeline.collect_camera_counts), "interval", minutes=5, max_instances=1)
    except ImportError:
        log.info("ultralytics not installed; camera counting disabled")
    sched.start()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="pizza_tracker")
    p.add_argument("command", choices=["init", "map", "demo", "worker"])
    args = p.parse_args()

    init_db()
    with SessionLocal() as s:  # type: Session
        if args.command == "init":
            print(f"seeded {seed_companies(s)} companies")
        elif args.command == "map":
            print(f"venues added: {pipeline.map_venues(s)}")
            print(f"cameras added: {pipeline.map_cameras(s)}")
        elif args.command == "demo":
            seed_companies(s)
            print(f"synthetic samples: {pipeline.seed_demo(s)}")
        elif args.command == "worker":
            seed_companies(s)
    if args.command == "worker":
        run_worker()


if __name__ == "__main__":
    main()
