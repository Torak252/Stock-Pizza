"""Runtime configuration, loaded from environment variables / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SPT_", extra="ignore")

    # SQLite keeps local dev and tests dependency-free; docker-compose points this at TimescaleDB.
    database_url: str = "sqlite:///./pizza_tracker.db"

    # Identify ourselves honestly to every upstream we poll.
    user_agent: str = "StockPizzaTracker/0.1 (research; contact: set SPT_CONTACT_EMAIL)"
    contact_email: str = ""

    # Free upstream credentials (optional; collectors that lack one are skipped).
    wsdot_access_code: str = ""      # free: https://wsdot.wa.gov/traffic/api/
    pa511_api_key: str = ""          # free developer key: https://www.511pa.com/developers

    # Politeness defaults applied by the shared HTTP client.
    default_min_interval_s: float = 2.0   # per-host minimum spacing between requests
    http_timeout_s: float = 15.0
    http_max_retries: int = 3

    # Anomaly thresholds.
    z_threshold: float = 2.0
    off_hours_start: int = 19   # 7 PM local
    off_hours_end: int = 3      # 3 AM local
    baseline_weeks: int = 8
    min_baseline_samples: int = 4

    # Only store derived counts from camera frames, never the images themselves.
    store_camera_frames: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
