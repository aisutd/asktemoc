import asyncio
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import logging

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.deep_crawling import (
    BFSDeepCrawlStrategy,
    DomainFilter,
    FilterChain,
    ContentTypeFilter,
    URLPatternFilter,
)
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy

from . import scraper_state
from .publisher import publish_page

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCRAPER_NAME = "general"

# UTD entry point and allowed domains
UTD_START_URL = "https://www.utdallas.edu"
UTD_ALLOWED_DOMAINS = [
    "utdallas.edu",
    "www.utdallas.edu",
    "housing.utdallas.edu",
    "catalog.utdallas.edu",
    "financial.utdallas.edu",
    "bursar.utdallas.edu",
    "registrar.utdallas.edu",
    "admissions.utdallas.edu",
    "engineering.utdallas.edu",
    "jindal.utdallas.edu",
    "arts.utdallas.edu",
    "atec.utdallas.edu",
    "epps.utdallas.edu",
    "ecs.utdallas.edu",
    "behavior.utdallas.edu",
    "library.utdallas.edu",
]

_BLOCKED_PATTERNS = [
    "*.zip", "*.pdf", "*.exe", "*.tar.gz", "*.dmg",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.svg",
    "*.mp4", "*.mp3", "*.avi", "*.mov",
]

_ALLOWED_CONTENT_TYPES = ["text/html", "application/xhtml+xml"]


class WebCrawlingPipeline:
    def __init__(self, output_folder: str = "output"):
        self.output_folder = Path(output_folder)
        self.output_folder.mkdir(exist_ok=True)
        self.index_file = self.output_folder / "index.json"
        self.visited_urls = self._load_visited_urls()
        self.failed_domains: dict[str, int] = defaultdict(int)
        self._state_lock = asyncio.Lock()

    def _load_visited_urls(self) -> set:
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                data = json.load(f)
                return set(data.get('visited_urls', []))
        return set()

    def _save_index(self, results: list):
        index_data = {
            'last_updated': datetime.now().isoformat(),
            'total_pages': len(results),
            'visited_urls': list(self.visited_urls),
            'pages': [],
        }
        for result in results:
            if result.success:
                index_data['pages'].append({
                    'url': result.url,
                    'filename': self._get_filename(result.url),
                    'status_code': result.status_code,
                    'depth': result.metadata.get('depth', 0) if result.metadata else 0,
                })
        with open(self.index_file, 'w') as f:
            json.dump(index_data, f, indent=2)
        logger.info(f"Index saved: {self.index_file}")

    def _get_filename(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.strip('/').replace('/', '_') or 'index'
        return f"{parsed.netloc}_{path}"

    def _save_page_data(self, result) -> tuple[str, str]:
        """
        Persist page JSON to disk and return (content, title) for hash/publish.
        Also tracks failed domains.
        """
        if not result.success:
            error_msg = result.error_message or ""
            if "ERR_ABORTED" in error_msg or "Target page, context or browser has been closed" in error_msg:
                logger.debug(f"Skipping {result.url} - limit reached during processing")
                return "", ""
            domain = urlparse(result.url).netloc
            self.failed_domains[domain] += 1
            logger.error(f"Failed to crawl {result.url}: {error_msg}")
            return "", ""

        markdown_content = (
            result.markdown.raw_markdown
            if hasattr(result.markdown, 'raw_markdown')
            else str(result.markdown)
        )
        title = result.metadata.get('title') if result.metadata else None

        page_data = {
            'url': result.url,
            'status_code': result.status_code,
            'crawled_at': datetime.now().isoformat(),
            'depth': result.metadata.get('depth', 0) if result.metadata else 0,
            'title': title,
            'html': result.html,
            'markdown': markdown_content,
            'cleaned_html': result.cleaned_html,
            'links': {
                'internal': result.links.get('internal', []),
                'external': result.links.get('external', []),
            },
            'media': result.media,
            'metadata': result.metadata,
        }

        json_file = self.output_folder / f"{self._get_filename(result.url)}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(page_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved: {json_file}")

        self.visited_urls.add(result.url)
        return markdown_content, title or ""

    def _build_filter_chain(
        self,
        allowed_domains: list[str],
        blocked_domains: list[str] | None = None,
    ) -> FilterChain:
        return FilterChain([
            DomainFilter(
                allowed_domains=allowed_domains,
                blocked_domains=blocked_domains or [],
            ),
            ContentTypeFilter(allowed_types=_ALLOWED_CONTENT_TYPES),
            URLPatternFilter(patterns=_BLOCKED_PATTERNS, reverse=True),
        ])

    async def crawl(
        self,
        urls: list[str] | str,
        max_depth: int = 5,
        max_pages: int = 500,
        timeout: int = 3600,
        allowed_domains: list[str] | None = None,
    ) -> list:
        """
        Crawl one or more URLs to the given depth.

        Args:
            urls: Starting URL(s).
            max_depth: BFS depth limit (default 5).
            max_pages: Maximum pages per run (default 500).
            timeout: Wall-clock timeout in seconds (default 3600).
            allowed_domains: Explicit domain allowlist. When None, derived from
                             the first URL's domain plus all its subdomains.
        """
        if isinstance(urls, str):
            urls = [urls]

        urls_to_crawl = [u for u in urls if u not in self.visited_urls]
        if not urls_to_crawl:
            logger.info("All URLs already visited")
            return []

        if allowed_domains is None:
            base_domain = urlparse(urls_to_crawl[0]).netloc
            allowed_domains = [base_domain, f"*.{base_domain}"]

        filter_chain = self._build_filter_chain(allowed_domains)

        deep_crawl_strategy = BFSDeepCrawlStrategy(
            max_depth=max_depth,
            include_external=False,
            max_pages=max_pages,
            filter_chain=filter_chain,
        )

        browser_config = BrowserConfig(headless=True, verbose=True)
        run_config = CrawlerRunConfig(
            deep_crawl_strategy=deep_crawl_strategy,
            scraping_strategy=LXMLWebScrapingStrategy(),
            stream=True,
            verbose=True,
            page_timeout=90000,
            word_count_threshold=10,
            wait_until="load",
            simulate_user=True,
            delay_before_return_html=3.0,
        )

        state = scraper_state.load()
        results = []
        start_time = datetime.now()

        async with AsyncWebCrawler(config=browser_config) as crawler:
            logger.info(
                f"Starting crawl of {urls_to_crawl[0]} "
                f"(max_depth={max_depth}, max_pages={max_pages})"
            )
            try:
                async def crawl_task():
                    async for result in await crawler.arun(urls_to_crawl[0], config=run_config):
                        depth = result.metadata.get('depth', 0) if result.metadata else 0
                        logger.info(f"Processing: {result.url} (depth={depth})")

                        if not result.success:
                            error_msg = result.error_message or ""
                            if any(e in error_msg for e in [
                                "ERR_ABORTED",
                                "Target page, context or browser has been closed",
                                "ERR_HTTP_RESPONSE_CODE_FAILURE",
                            ]):
                                logger.debug(f"Skipping {result.url} - expected error")
                                continue

                        content, title = self._save_page_data(result)
                        results.append(result)

                        if content and scraper_state.has_changed(result.url, content, state):
                            await publish_page(
                                url=result.url,
                                page_title=title,
                                text_content=content,
                            )
                            async with self._state_lock:
                                scraper_state.record_scraped(
                                    result.url, content, SCRAPER_NAME, state
                                )

                await asyncio.wait_for(crawl_task(), timeout=timeout)

            except asyncio.TimeoutError:
                logger.warning(f"Crawl timed out after {timeout}s — processed {len(results)} pages")
            except StopAsyncIteration:
                logger.info("Stream completed normally")
            except Exception as e:
                logger.error(f"Error during crawl: {e}")
            finally:
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"Crawl finished. Pages: {len(results)}, elapsed: {elapsed:.1f}s")

        self._save_index(results)
        scraper_state.save(state)
        return results

    async def crawl_utd(
        self,
        max_depth: int = 5,
        max_pages: int = 500,
        timeout: int = 3600,
    ) -> list:
        """Convenience method: crawl all UTD domains starting from the main page."""
        return await self.crawl(
            urls=UTD_START_URL,
            max_depth=max_depth,
            max_pages=max_pages,
            timeout=timeout,
            allowed_domains=UTD_ALLOWED_DOMAINS,
        )


async def main():
    pipeline = WebCrawlingPipeline(
        output_folder=str(Path(__file__).parent.parent / "data" / "general")
    )
    results = await pipeline.crawl_utd()
    print(f"Done. Crawled {len(results)} pages.")


if __name__ == "__main__":
    asyncio.run(main())
