"""Test environment setup.

Runs before any test module imports cutlist_engine. The engine loads a
repo-root .env if present (for API tokens etc.) — tests must be hermetic and
never depend on a developer's local secrets, so disable that loading here.
"""
import os

os.environ.setdefault("CUTLIST_NO_DOTENV", "1")
os.environ.pop("CUTLIST_API_TOKEN", None)
