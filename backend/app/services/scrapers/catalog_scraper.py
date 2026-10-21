"""
UTD Catalog Scraper
Scrapes program requirements and example degree plans from UTD undergraduate catalog.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError

from . import scraper_state
from .publisher import publish_page

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCRAPER_NAME = "catalog"


class UTDCatalogScraper:
    """Scraper for UTD undergraduate catalog program pages."""

    BASE_URL = "https://catalog.utdallas.edu/2025/undergraduate/programs"

    def __init__(
        self,
        max_pages: Optional[int] = None,
        rate_limit: float = 1.0,
        max_parallel: int = 3,
        output_dir: str = "./output",
    ):
        self.max_pages = max_pages
        self.rate_limit = rate_limit
        self.max_parallel = max_parallel
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.semaphore = asyncio.Semaphore(max_parallel)
        self._last_request_time = 0
        self._state_lock = asyncio.Lock()

    async def _rate_limit(self):
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.rate_limit:
            await asyncio.sleep(self.rate_limit - time_since_last)
        self._last_request_time = asyncio.get_event_loop().time()

    def _sanitize_filename(self, name: str) -> str:
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[-\s]+', '_', name)
        return name.strip('_').lower()

    async def find_program_links(self, page: Page) -> List[Tuple[str, str]]:
        """Find all program links — returns list of (url, program_name)."""
        await page.goto(self.BASE_URL, wait_until="networkidle")
        await self._rate_limit()

        links = []
        seen_urls: set[str] = set()

        paragraphs = await page.query_selector_all('p')
        for p in paragraphs:
            p_text = await p.inner_text()
            if 'credit hours' in p_text.lower():
                p_links = await p.query_selector_all('a')
                for link in p_links:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    if href:
                        full_url = urljoin(self.BASE_URL, href)
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            links.append((full_url, text.strip()))

        all_links = await page.query_selector_all('a')
        for link in all_links:
            text = await link.inner_text()
            if 'concentration' in text.lower():
                href = await link.get_attribute('href')
                if href:
                    full_url = urljoin(self.BASE_URL, href)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        links.append((full_url, text.strip()))

        logger.info(f"Found {len(links)} program links")
        return links

    async def scrape_program_page(self, page: Page, url: str) -> Tuple[Optional[str], Optional[str]]:
        """Scrape a program page. Returns (requirements_text, example_url)."""
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self._rate_limit()

            main_content = await page.query_selector('main, .main-content, #content, .content')
            if main_content:
                requirements_text = await main_content.inner_text()
            else:
                body = await page.query_selector('body')
                if body:
                    await page.evaluate("""
                        () => {
                            document.querySelectorAll('script, style, nav, header, footer')
                                .forEach(el => el.remove());
                        }
                    """)
                    requirements_text = await body.inner_text()
                else:
                    requirements_text = await page.inner_text('body')

            example_url = None
            for link in await page.query_selector_all('a'):
                text = await link.inner_text()
                href = await link.get_attribute('href')
                if text and href:
                    text_lower = text.lower()
                    if 'example' in text_lower and 'degree requirements' in text_lower:
                        example_url = urljoin(url, href)
                        break

            return requirements_text, example_url

        except PlaywrightTimeoutError:
            logger.error(f"Timeout loading page: {url}")
            return None, None
        except Exception as e:
            logger.error(f"Error scraping program page {url}: {e}")
            return None, None

    async def scrape_example_page(self, page: Page, url: str) -> Optional[str]:
        """Scrape an example degree requirements page."""
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self._rate_limit()

            main_content = await page.query_selector('main, .main-content, #content, .content')
            if main_content:
                return await main_content.inner_text()

            body = await page.query_selector('body')
            if body:
                await page.evaluate("""
                    () => {
                        document.querySelectorAll('script, style, nav, header, footer')
                            .forEach(el => el.remove());
                    }
                """)
                return await body.inner_text()

            return await page.inner_text('body')

        except PlaywrightTimeoutError:
            logger.error(f"Timeout loading example page: {url}")
            return None
        except Exception as e:
            logger.error(f"Error scraping example page {url}: {e}")
            return None

    def _save_to_disk(self, major_name: str, requirements: Optional[str], example: Optional[str]):
        """Write scraped content to local text files (kept for local cache)."""
        safe_name = self._sanitize_filename(major_name)
        major_dir = self.output_dir / safe_name
        major_dir.mkdir(parents=True, exist_ok=True)

        if requirements:
            (major_dir / "requirements.txt").write_text(requirements, encoding='utf-8')
        if example:
            (major_dir / "example.txt").write_text(example, encoding='utf-8')

    async def _scrape_single_program(
        self, browser: Browser, url: str, name: str, state: dict
    ):
        """Scrape one program; publish changed pages and update state."""
        async with self.semaphore:
            try:
                context = await browser.new_context()
                page = await context.new_page()

                requirements, example_url = await self.scrape_program_page(page, url)
                example = None
                if example_url:
                    example = await self.scrape_example_page(page, example_url)

                await context.close()

                self._save_to_disk(name, requirements, example)

                # Combine both texts as the canonical content for hashing
                combined = "\n\n".join(filter(None, [requirements, example]))
                if combined and scraper_state.has_changed(url, combined, state):
                    logger.info(f"Content changed, publishing: {name}")
                    await publish_page(
                        url=url,
                        page_title=name,
                        text_content=combined,
                    )
                    async with self._state_lock:
                        scraper_state.record_scraped(url, combined, SCRAPER_NAME, state)

            except Exception as e:
                logger.error(f"Error scraping {name} ({url}): {e}")

    async def scrape(self, state: Optional[dict] = None) -> None:
        """Main scraping method. Loads/saves state automatically if not provided."""
        owns_state = state is None
        if owns_state:
            state = scraper_state.load()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                program_links = await self.find_program_links(page)
                await page.close()

                if self.max_pages:
                    program_links = program_links[:self.max_pages]

                logger.info(f"Scraping {len(program_links)} program pages...")

                tasks = [
                    self._scrape_single_program(browser, url, name, state)
                    for url, name in program_links
                ]
                await asyncio.gather(*tasks, return_exceptions=True)

            finally:
                await browser.close()

        if owns_state:
            scraper_state.save(state)

        logger.info("Catalog scraping completed.")


async def main():
    scraper = UTDCatalogScraper(
        max_pages=1,
        rate_limit=2.0,
        max_parallel=5,
        output_dir=str(Path(__file__).parent.parent / "data"),
    )
    await scraper.scrape()
    print("Done. Check ./data for results.")


if __name__ == "__main__":
    asyncio.run(main())
