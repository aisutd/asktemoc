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

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UTDCatalogScraper:
    """Scraper for UTD undergraduate catalog program pages."""
    
    BASE_URL = "https://catalog.utdallas.edu/2025/undergraduate/programs"
    
    def __init__(
        self,
        max_pages: Optional[int] = None,
        rate_limit: float = 1.0,
        max_parallel: int = 3,
        output_dir: str = "./output"
    ):
        """
        Initialize the scraper.
        
        Args:
            max_pages: Maximum number of pages to scrape (None for all)
            rate_limit: Delay between requests in seconds
            max_parallel: Maximum number of concurrent browser instances
            output_dir: Directory to save scraped data
        """
        self.max_pages = max_pages
        self.rate_limit = rate_limit
        self.max_parallel = max_parallel
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.semaphore = asyncio.Semaphore(max_parallel)
        self._last_request_time = 0
        
    async def _rate_limit(self):
        """Apply rate limiting between requests."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self.rate_limit:
            await asyncio.sleep(self.rate_limit - time_since_last)
        self._last_request_time = asyncio.get_event_loop().time()
    
    def _sanitize_filename(self, name: str) -> str:
        """Convert a name to a safe filename."""
        # Remove special characters and replace spaces with underscores
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'[-\s]+', '_', name)
        return name.strip('_').lower()
    
    async def find_program_links(self, page: Page) -> List[Tuple[str, str]]:
        """
        Find all program links matching the criteria.
        
        Returns:
            List of tuples (url, program_name)
        """
        await page.goto(self.BASE_URL, wait_until="networkidle")
        await self._rate_limit()
        
        links = []
        seen_urls = set()
        
        # Find all <p> tags that contain "credit hours" (case-insensitive)
        paragraphs = await page.query_selector_all('p')
        for p in paragraphs:
            p_text = await p.inner_text()
            if 'credit hours' in p_text.lower():
                # Find all <a> tags within this paragraph
                p_links = await p.query_selector_all('a')
                for link in p_links:
                    href = await link.get_attribute('href')
                    text = await link.inner_text()
                    if href:
                        full_url = urljoin(self.BASE_URL, href)
                        if full_url not in seen_urls:
                            seen_urls.add(full_url)
                            links.append((full_url, text.strip()))
        
        # Find <a> tags containing "Concentration" (case-insensitive)
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
        """
        Scrape a program page to extract requirements and find example link.
        
        Returns:
            Tuple of (requirements_text, example_url)
        """
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self._rate_limit()
            
            # Extract requirements text (body content, excluding nav/header/footer)
            # Try to get main content area
            main_content = await page.query_selector('main, .main-content, #content, .content')
            if main_content:
                requirements_text = await main_content.inner_text()
            else:
                # Fallback to body but exclude common nav/header/footer elements
                body = await page.query_selector('body')
                if body:
                    # Remove script and style elements
                    await page.evaluate("""
                        () => {
                            const scripts = document.querySelectorAll('script, style, nav, header, footer');
                            scripts.forEach(el => el.remove());
                        }
                    """)
                    requirements_text = await body.inner_text()
                else:
                    requirements_text = await page.inner_text('body')
            
            # Find example link containing "example" and "degree requirements" (case-insensitive)
            example_url = None
            example_links = await page.query_selector_all('a')
            for link in example_links:
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
        """
        Scrape an example degree requirements page.
        
        Returns:
            Text content of the example page
        """
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await self._rate_limit()
            
            # Extract text content
            main_content = await page.query_selector('main, .main-content, #content, .content')
            if main_content:
                example_text = await main_content.inner_text()
            else:
                body = await page.query_selector('body')
                if body:
                    await page.evaluate("""
                        () => {
                            const scripts = document.querySelectorAll('script, style, nav, header, footer');
                            scripts.forEach(el => el.remove());
                        }
                    """)
                    example_text = await body.inner_text()
                else:
                    example_text = await page.inner_text('body')
            
            return example_text
            
        except PlaywrightTimeoutError:
            logger.error(f"Timeout loading example page: {url}")
            return None
        except Exception as e:
            logger.error(f"Error scraping example page {url}: {e}")
            return None
    
    def save_program_data(self, major_name: str, requirements: Optional[str], example: Optional[str]):
        """
        Save program data to files.
        
        Args:
            major_name: Name of the major (will be sanitized for folder name)
            requirements: Requirements text content
            example: Example degree requirements text content
        """
        safe_name = self._sanitize_filename(major_name)
        major_dir = self.output_dir / safe_name
        major_dir.mkdir(parents=True, exist_ok=True)
        
        # Save requirements
        if requirements:
            requirements_file = major_dir / "requirements.txt"
            requirements_file.write_text(requirements, encoding='utf-8')
            logger.info(f"Saved requirements to {requirements_file}")
        else:
            logger.warning(f"No requirements found for {major_name}")
        
        # Save example
        if example:
            example_file = major_dir / "example.txt"
            example_file.write_text(example, encoding='utf-8')
            logger.info(f"Saved example to {example_file}")
        else:
            logger.warning(f"No example found for {major_name}")
    
    async def _scrape_single_program(self, browser: Browser, url: str, name: str):
        """Scrape a single program page with semaphore control."""
        async with self.semaphore:
            try:
                context = await browser.new_context()
                page = await context.new_page()
                
                # Scrape program page
                requirements, example_url = await self.scrape_program_page(page, url)
                
                # Scrape example page if found
                example = None
                if example_url:
                    example = await self.scrape_example_page(page, example_url)
                
                # Save data
                self.save_program_data(name, requirements, example)
                
                await context.close()
                
            except Exception as e:
                logger.error(f"Error scraping {name} ({url}): {e}")
    
    async def scrape(self):
        """Main scraping method."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            try:
                # Create a page to find all program links
                page = await browser.new_page()
                program_links = await self.find_program_links(page)
                await page.close()
                
                # Limit pages if specified
                if self.max_pages:
                    program_links = program_links[:self.max_pages]
                
                logger.info(f"Scraping {len(program_links)} program pages...")
                
                # Scrape all programs in parallel (with semaphore limit)
                tasks = [
                    self._scrape_single_program(browser, url, name)
                    for url, name in program_links
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                
            finally:
                await browser.close()
            
            logger.info("Scraping completed!")

"""
Test script to verify scraper works with a single page.
"""


import sys
from pathlib import Path

# Add parent directory to path to allow importing scraper
sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    scraper = UTDCatalogScraper(
        max_pages=1,
        rate_limit=2.0,
        max_parallel=5,
        output_dir="./data"
    )
    
    await scraper.scrape()
    print("Test completed! Check ./data for results.")


if __name__ == "__main__":
    asyncio.run(main())