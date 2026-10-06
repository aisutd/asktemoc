"""
Write data/catalog/sources.json: program folder name -> catalog URL and title.

Reuses the scraper's own link discovery and folder naming, so the keys match the
folders a full scrape produces. Folders with no discovered link are left out;
seeding falls back to the catalog's programs index URL for those.

Run from backend/scrapers/catalog/ after `playwright install chromium`:
    python build_sources.py
"""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from scraper import UTDCatalogScraper

CATALOG_DIR = Path(__file__).resolve().parents[3] / "data" / "catalog"


async def main():
    scraper = UTDCatalogScraper(output_dir=str(Path(__file__).parent / "output"))
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            links = await scraper.find_program_links(page)
        finally:
            await browser.close()

    existing = {d.name for d in CATALOG_DIR.iterdir() if d.is_dir()}
    sources = {}
    collisions = []
    for url, name in links:
        folder = scraper._sanitize_filename(name)
        if folder not in existing:
            continue
        # Links with the same name share one folder in a scrape (whichever page
        # finished last wins), so the URL is ambiguous; keep the first, report it.
        if folder in sources:
            collisions.append(folder)
            continue
        sources[folder] = {"url": url, "title": " ".join(name.split())}

    out = CATALOG_DIR / "sources.json"
    out.write_text(json.dumps(dict(sorted(sources.items())), indent=2) + "\n", encoding="utf-8")
    missing = sorted(existing - sources.keys())
    print(f"Discovered {len(links)} links; mapped {len(sources)}/{len(existing)} folders -> {out}")
    if missing:
        print("No link found for:", ", ".join(missing))
    if collisions:
        print("Ambiguous (several links share a name):", ", ".join(sorted(set(collisions))))


if __name__ == "__main__":
    asyncio.run(main())
