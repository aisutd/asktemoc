"""
Test script to verify scraper works with a single page.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to allow importing scraper
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import UTDCatalogScraper


async def main():
    """Test scraper with 1 page."""
    scraper = UTDCatalogScraper(
        max_pages=None,
        rate_limit=2.0,
        max_parallel=5,
        output_dir="./test_output"
    )
    
    await scraper.scrape()
    print("Test completed! Check ./test_output for results.")


if __name__ == "__main__":
    asyncio.run(main())

