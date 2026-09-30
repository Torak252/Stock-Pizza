"""Near-real-time panels for the per-HQ page.

Each module fetches on demand and caches briefly (see cache.py), so the page stays as fresh
as its upstream allows without hammering anyone. Nothing here is stored unless the worker
explicitly records it as an ActivitySample.
"""
