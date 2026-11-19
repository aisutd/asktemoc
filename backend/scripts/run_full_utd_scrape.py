#!/usr/bin/env python3
"""
Run all three UTD scrapers at full scale against the local ingest URL.
Logs to stdout; run with nohup if needed.

Order: catalog → general (broad crawl) → housing (housing. subdomain BFS).
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Project root / data
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "app/services/data"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


async def run_catalog() -> None:
    from app.services.scrapers.catalog_scraper import UTDCatalogScraper

    logging.info("=== CATALOG (all program pages) ===")
    scraper = UTDCatalogScraper(
        max_pages=None,  # all links from program listing
        rate_limit=2.0,
        max_parallel=3,
        output_dir=str(DATA),
    )
    await scraper.scrape()
    logging.info("=== CATALOG DONE ===")


async def run_general() -> None:
    from app.services.scrapers.general_webscraper import WebCrawlingPipeline

    # Broad crawl across allowlisted *.utd domains (see general_webscraper.py)
    logging.info("=== GENERAL (site crawl) ===")
    pipeline = WebCrawlingPipeline(output_folder=str(DATA / "general"))
    await pipeline.crawl_utd(
        max_depth=5,
        max_pages=2500,
        timeout=28800,  # 8h wall-clock per run (crawl stops early when exhausted)
    )
    logging.info("=== GENERAL DONE ===")


async def run_housing() -> None:
    from app.services.scrapers.housing_scraper import UTDHousingScraper

    logging.info("=== HOUSING (full housing.ut BFS within depth) ===")
    scraper = UTDHousingScraper(
        max_depth=6,
        max_pages=None,  # no cap until BFS + depth exhausted
        rate_limit=1.2,
        max_parallel=3,
        output_dir=str(DATA),
    )
    await scraper.scrape()
    logging.info("=== HOUSING DONE ===")


async def main() -> None:
    await run_catalog()
    await run_general()
    await run_housing()


if __name__ == "__main__":
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    asyncio.run(main())
