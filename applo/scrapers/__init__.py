from pathlib import Path
import importlib

for _f in Path(__file__).parent.glob("*.py"):
    if _f.stem not in ("__init__", "base", "registry"):
        importlib.import_module(f"applo.scrapers.{_f.stem}")

from .registry import ScraperRegistry
from .base import BaseScraper
