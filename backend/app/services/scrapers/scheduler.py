"""
Scraper scheduler.
Runs UTDCatalogScraper and WebCrawlingPipeline on weekly cron schedules and
processes the per-URL rescrape queue daily.

Start it standalone:
    python -m app.services.scrapers.scheduler

Or integrate it into FastAPI startup:
    from app.services.scrapers.scheduler import start, stop

    @app.on_event("startup")
    async def _start(): await start()

    @app.on_event("shutdown")
    async def _stop(): await stop()
"""

import asyncio
import logging
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import scraper_state
from .catalog_scraper import UTDCatalogScraper
from .general_webscraper import WebCrawlingPipeline, UTD_START_URL, UTD_ALLOWED_DOMAINS
from .housing_scraper import UTDHousingScraper

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

_scheduler: AsyncIOScheduler | None = None


# ---------------------------------------------------------------------------
# Individual job functions
# ---------------------------------------------------------------------------

async def run_catalog_scraper():
    logger.info("Cron: starting catalog scraper")
    scraper = UTDCatalogScraper(
        rate_limit=2.0,
        max_parallel=3,
        output_dir=str(DATA_DIR),
    )
    await scraper.scrape()
    logger.info("Cron: catalog scraper finished")


async def run_general_scraper():
    logger.info("Cron: starting general (UTD) scraper")
    pipeline = WebCrawlingPipeline(
        output_folder=str(DATA_DIR / "general"),
    )
    await pipeline.crawl_utd(max_depth=5, max_pages=500, timeout=3600)
    logger.info("Cron: general scraper finished")


async def run_housing_scraper():
    logger.info("Cron: starting housing scraper")
    scraper = UTDHousingScraper(
        max_depth=2,
        rate_limit=1.5,
        max_parallel=3,
        output_dir=str(DATA_DIR),
    )
    await scraper.scrape()
    logger.info("Cron: housing scraper finished")


async def process_rescrape_queue():
    """Re-scrape any URLs that are past their scheduled rescrape time."""
    state = scraper_state.load()

    for scraper_name, run_fn in [
        ("catalog", _rescrape_catalog),
        ("general", _rescrape_general),
        ("housing", _rescrape_housing),
    ]:
        due = scraper_state.get_due_urls(scraper_name, state)
        if due:
            logger.info(f"Queue: {len(due)} URLs due for '{scraper_name}'")
            await run_fn(due, state)

    scraper_state.save(state)


async def _rescrape_catalog(urls: list[str], state: dict):
    """Re-scrape specific catalog URLs that are due."""
    from .catalog_scraper import UTDCatalogScraper
    scraper = UTDCatalogScraper(
        rate_limit=2.0,
        max_parallel=3,
        output_dir=str(DATA_DIR),
    )
    async with __import__('playwright.async_api', fromlist=['async_playwright']).async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            for url in urls:
                # Find the program name from stored state
                name = state["pages"].get(url, {}).get("scraper", url)
                await scraper._scrape_single_program(browser, url, name, state)
        finally:
            await browser.close()


async def _rescrape_general(urls: list[str], state: dict):
    """Re-scrape specific general URLs that are due (individual pages via crawl4ai)."""
    pipeline = WebCrawlingPipeline(output_folder=str(DATA_DIR / "general"))
    for url in urls:
        await pipeline.crawl(
            urls=url,
            max_depth=0,
            max_pages=1,
            timeout=120,
            allowed_domains=UTD_ALLOWED_DOMAINS,
        )


async def _rescrape_housing(urls: list[str], state: dict):
    """Re-scrape specific housing URLs that are due."""
    scraper = UTDHousingScraper(
        max_depth=0,
        rate_limit=1.5,
        output_dir=str(DATA_DIR),
    )
    async with __import__('playwright.async_api', fromlist=['async_playwright']).async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            for url in urls:
                data, _ = await scraper._scrape_and_extract(browser, url)
                if data:
                    scraper.results.append(data)
                    from .publisher import publish_page
                    content = data["content"]
                    if content and scraper_state.has_changed(url, content, state):
                        await publish_page(url=url, page_title=data["title"], text_content=content)
                        scraper_state.record_scraped(url, content, "housing", state)
        finally:
            await browser.close()


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

async def start() -> AsyncIOScheduler:
    """Create and start the scheduler. Returns the scheduler instance."""
    global _scheduler

    if _scheduler and _scheduler.running:
        return _scheduler

    _scheduler = AsyncIOScheduler()

    # Catalog: every Sunday at 02:00 local time
    _scheduler.add_job(
        run_catalog_scraper,
        CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="catalog_weekly",
        replace_existing=True,
        name="UTD Catalog Scraper (weekly)",
    )

    # General/UTD: every Sunday at 04:00 (offset to avoid overlap)
    _scheduler.add_job(
        run_general_scraper,
        CronTrigger(day_of_week="sun", hour=4, minute=0),
        id="general_weekly",
        replace_existing=True,
        name="UTD General Scraper (weekly)",
    )

    # Housing: every Sunday at 06:00
    _scheduler.add_job(
        run_housing_scraper,
        CronTrigger(day_of_week="sun", hour=6, minute=0),
        id="housing_weekly",
        replace_existing=True,
        name="UTD Housing Scraper (weekly)",
    )

    # Rescrape queue: daily at 01:00
    _scheduler.add_job(
        process_rescrape_queue,
        CronTrigger(hour=1, minute=0),
        id="rescrape_queue_daily",
        replace_existing=True,
        name="Rescrape Queue Processor (daily)",
    )

    _scheduler.start()
    logger.info("Scraper scheduler started.")
    return _scheduler


async def stop():
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scraper scheduler stopped.")
    _scheduler = None


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    async def _main():
        await start()
        logger.info("Scheduler running. Press Ctrl+C to stop.")
        try:
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            await stop()

    asyncio.run(_main())
