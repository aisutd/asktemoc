"""
UTD Housing Scraper
Scrapes housing information from housing.utdallas.edu including all internal subpages.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    async_playwright,
    Browser,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from . import scraper_state
from .publisher import publish_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPER_NAME = "housing"


class UTDHousingScraper:
    """Scrapes housing.utdallas.edu and all its internal subpages."""

    BASE_URL = "https://housing.utdallas.edu/"
    DOMAIN = "housing.utdallas.edu"

    def __init__(
        self,
        max_depth: int = 2,
        max_pages: Optional[int] = None,
        rate_limit: float = 1.0,
        max_parallel: int = 3,
        output_dir: str = "./output",
    ):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.rate_limit = rate_limit
        self.max_parallel = max_parallel
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._last_request_time = 0
        self.visited_urls: set[str] = set()
        self.results: list[dict] = []
        self._state_lock = asyncio.Lock()

    async def _rate_limit_wait(self):
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.rate_limit:
            await asyncio.sleep(self.rate_limit - time_since_last)
        self._last_request_time = asyncio.get_event_loop().time()

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        name = re.sub(r"[^\w\s-]", "", name)
        name = re.sub(r"[-\s]+", "_", name)
        return name.strip("_").lower() or "index"

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized.rstrip("/")

    def _is_valid_link(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.netloc and parsed.netloc != self.DOMAIN:
            return False
        skip_extensions = {
            ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg",
            ".mp4", ".mp3", ".zip", ".exe", ".doc", ".docx",
            ".xls", ".xlsx", ".ppt", ".pptx",
        }
        if any(parsed.path.lower().endswith(ext) for ext in skip_extensions):
            return False
        if url.startswith(("mailto:", "tel:", "javascript:")):
            return False
        return True

    async def _extract_links(self, page: Page, current_url: str) -> list[str]:
        links = []
        try:
            anchors = await page.query_selector_all("a[href]")
            for anchor in anchors:
                href = await anchor.get_attribute("href")
                if not href:
                    continue
                full_url = urljoin(current_url, href)
                normalized = self._normalize_url(full_url)
                if self._is_valid_link(normalized) and normalized not in self.visited_urls:
                    links.append(normalized)
        except Exception as e:
            logger.warning(f"Error extracting links from {current_url}: {e}")
        return list(set(links))

    async def _scrape_page(self, page: Page, url: str) -> Optional[dict]:
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self._rate_limit_wait()

            title = await page.title()
            content = await page.evaluate("""
                () => {
                    document.querySelectorAll(
                        'script, style, nav, header, footer, .menu, #menu, .nav, .navbar'
                    ).forEach(el => el.remove());
                    const main = document.querySelector(
                        'main, .main-content, #content, .content, .entry-content, article, .page-content'
                    );
                    return main ? main.innerText : document.body.innerText;
                }
            """)

            return {
                "url": url,
                "title": title.strip() if title else "",
                "content": content.strip() if content else "",
            }

        except PlaywrightTimeoutError:
            logger.error(f"Timeout loading: {url}")
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None

    async def _scrape_and_extract(
        self, browser: Browser, url: str
    ) -> tuple[Optional[dict], list[str]]:
        context = await browser.new_context()
        page = await context.new_page()
        child_links: list[str] = []
        data = None
        try:
            data = await self._scrape_page(page, url)
            await page.goto(url, wait_until="networkidle", timeout=30000)
            child_links = await self._extract_links(page, url)
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
        finally:
            await context.close()
        return data, child_links

    async def _bfs_crawl(self, browser: Browser, state: dict):
        queue: list[tuple[str, int]] = [(self.BASE_URL, 0)]
        self.visited_urls.add(self._normalize_url(self.BASE_URL))

        while queue:
            if self.max_pages and len(self.results) >= self.max_pages:
                break

            batch = queue[:]
            queue.clear()

            for i in range(0, len(batch), self.max_parallel):
                if self.max_pages and len(self.results) >= self.max_pages:
                    break

                chunk = batch[i: i + self.max_parallel]
                tasks = [self._scrape_and_extract(browser, url) for url, _ in chunk]
                raw_results = await asyncio.gather(*tasks, return_exceptions=True)

                for (url, depth), result in zip(chunk, raw_results):
                    if isinstance(result, Exception):
                        logger.error(f"Error crawling {url}: {result}")
                        continue

                    data, child_links = result
                    if data:
                        data["depth"] = depth
                        self.results.append(data)
                        logger.info(
                            f"[depth={depth}] Scraped: {data['title'] or url} "
                            f"({len(data['content'])} chars)"
                        )

                        content = data["content"]
                        if content and scraper_state.has_changed(url, content, state):
                            await publish_page(
                                url=url,
                                page_title=data["title"],
                                text_content=content,
                            )
                            async with self._state_lock:
                                scraper_state.record_scraped(
                                    url, content, SCRAPER_NAME, state
                                )

                    if depth < self.max_depth:
                        for link in child_links:
                            normalized = self._normalize_url(link)
                            if normalized not in self.visited_urls:
                                if self.max_pages and len(self.visited_urls) >= self.max_pages:
                                    break
                                self.visited_urls.add(normalized)
                                queue.append((link, depth + 1))
                        logger.info(f"  Queued {len(child_links)} links from depth {depth}")

                await self._rate_limit_wait()

    def _save_results(self):
        housing_dir = self.output_dir / "housing"
        housing_dir.mkdir(parents=True, exist_ok=True)

        for data in self.results:
            parsed = urlparse(data["url"])
            path_part = parsed.path.strip("/")
            filename = (
                "index"
                if not path_part
                else self._sanitize_filename(path_part.replace("/", "_"))
            )
            header = f"URL: {data['url']}\nTitle: {data['title']}\nDepth: {data['depth']}\n"
            (housing_dir / f"{filename}.txt").write_text(
                f"{header}\n{'-' * 60}\n\n{data['content']}",
                encoding="utf-8",
            )

        index = {
            "source": self.BASE_URL,
            "total_pages": len(self.results),
            "pages": [
                {"url": r["url"], "title": r["title"], "depth": r["depth"]}
                for r in self.results
            ],
        }
        with open(housing_dir / "index.json", "w") as f:
            json.dump(index, f, indent=2)

        logger.info(f"Saved {len(self.results)} pages to {housing_dir}")

    async def scrape(self, state: Optional[dict] = None) -> list[dict]:
        """Main entry point. Loads/saves state automatically if not provided."""
        owns_state = state is None
        if owns_state:
            state = scraper_state.load()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                await self._bfs_crawl(browser, state)
            finally:
                await browser.close()

        self._save_results()

        if owns_state:
            scraper_state.save(state)

        return self.results


async def main():
    scraper = UTDHousingScraper(
        max_depth=2,
        max_pages=50,
        rate_limit=1.5,
        max_parallel=3,
        output_dir=Path(__file__).parent.parent / "data",
    )
    results = await scraper.scrape()
    print(f"\nDone! Scraped {len(results)} pages.")
    for r in results:
        print(f"  [{r['depth']}] {r['title'] or r['url']}")


if __name__ == "__main__":
    asyncio.run(main())
