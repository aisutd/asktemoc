import asyncio  
import json  
import os  
from pathlib import Path  
from urllib.parse import urlparse  
from datetime import datetime  
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig  
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy, DomainFilter, FilterChain, ContentTypeFilter, URLPatternFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from collections import defaultdict  

import logging  
 
logging.basicConfig(  
    level=logging.INFO,  
    format='%(asctime)s - %(levelname)s - %(message)s'  
)  
logger = logging.getLogger(__name__)  
  
class WebCrawlingPipeline:  
    def __init__(self, output_folder: str = "output"):  
        self.output_folder = Path(output_folder)  
        self.output_folder.mkdir(exist_ok=True)  
        self.index_file = self.output_folder / "index.json"  
        self.visited_urls = self._load_visited_urls()
        self.failed_domains = defaultdict(int)
          
    def _load_visited_urls(self) -> set:  
        """Load previously visited URLs from index file"""  
        if self.index_file.exists():  
            with open(self.index_file, 'r') as f:  
                data = json.load(f)  
                return set(data.get('visited_urls', []))  
        return set()  
      
    def _save_index(self, results: list):  
        """Save index file with all crawled URLs"""  
        index_data = {  
            'last_updated': datetime.now().isoformat(),  
            'total_pages': len(results),  
            'visited_urls': list(self.visited_urls),  
            'pages': []  
        }  
          
        for result in results:  
            if result.success:  
                filename = self._get_filename(result.url)  
                index_data['pages'].append({  
                    'url': result.url,  
                    'filename': filename,  
                    'status_code': result.status_code,  
                    'depth': result.metadata.get('depth', 0) if result.metadata else 0  
                })  
          
        with open(self.index_file, 'w') as f:  
            json.dump(index_data, f, indent=2)  
        logger.info(f"Index file saved: {self.index_file}")  
      
    def _get_filename(self, url: str) -> str:  
        """Generate safe filename from URL"""  
        parsed = urlparse(url)  
        path = parsed.path.strip('/').replace('/', '_') or 'index'  
        return f"{parsed.netloc}_{path}"  
      
    def _save_page_data(self, result):  
        """Save all page data (HTML, markdown, and metadata) in a single JSON file"""  
        if not result.success:
            error_msg = result.error_message or ""
            if "ERR_ABORTED" in error_msg or "Target page, context or browser has been closed" in error_msg:  
                logger.debug(f"Skipping {result.url} - limit reached during processing")  
                return 
            
            domain = urlparse(result.url).netloc  
            self.failed_domains[domain] += 1  
            logger.error(f"Failed to crawl {result.url}: {error_msg}")
     

        filename = self._get_filename(result.url)  
        
        # Extract markdown content  
        markdown_content = result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown)  
        
        # Consolidate all data into a single JSON structure  
        page_data = {  
            'url': result.url,  
            'status_code': result.status_code,  
            'crawled_at': datetime.now().isoformat(),  
            'depth': result.metadata.get('depth', 0) if result.metadata else 0,  
            'title': result.metadata.get('title') if result.metadata else None,  
            'html': result.html,  
            'markdown': markdown_content,  
            'cleaned_html': result.cleaned_html,  
            'links': {  
                'internal': result.links.get('internal', []),  
                'external': result.links.get('external', [])  
            },  
            'media': result.media,  
            'metadata': result.metadata  
        }  
        
        # Save single JSON file  
        json_file = self.output_folder / f"{filename}.json"  
        with open(json_file, 'w', encoding='utf-8') as f:  
            json.dump(page_data, f, indent=2, ensure_ascii=False)  
        logger.info(f"Saved all data to: {json_file}")  
        
        self.visited_urls.add(result.url) 
      
    def create_generic_filter_chain(self, base_url: str, allow_subdomains: bool = True, blocked_patterns: list[str] = None, blocked_domains: list[str] = None, allowed_content_types: list[str] = None):  
        """  
        Create a generic filter chain that works for any website.  
        
        Args:  
            base_url: Starting URL to extract domain from  
            allow_subdomains: Whether to allow subdomains of the base domain  
            blocked_patterns: URL patterns to exclude (e.g., ["*.zip", "*.pdf"])  
            allowed_content_types: Content types to allow (default: ["text/html"])  
        """  
        # Extract domain from base URL  
        parsed = urlparse(base_url)  
        base_domain = parsed.netloc  
        
        # Default blocked patterns for common non-HTML resources  
        if blocked_patterns is None:  
            blocked_patterns = [  
                "*.zip", "*.pdf", "*.exe", "*.tar.gz", "*.dmg",  
                "*.jpg", "*.jpeg", "*.png", "*.gif", "*.svg",  
                "*.mp4", "*.mp3", "*.avi", "*.mov"  
            ]  
        
        # Default to HTML content only  
        if allowed_content_types is None:  
            allowed_content_types = ["text/html", "application/xhtml+xml"]  
        
        filters = []  
        
        # Domain filter - allow base domain and optionally subdomains  
        if allow_subdomains:  
            # Use wildcard pattern to match subdomains  
            allowed_domains = [f"*.{base_domain}", base_domain]  
        else:  
            allowed_domains = [base_domain]  
        
        filters.append(DomainFilter(allowed_domains=allowed_domains, blocked_domains=blocked_domains or []))  
        
        # Content type filter  
        filters.append(ContentTypeFilter(allowed_types=allowed_content_types))  
        
        # URL pattern filter to exclude file downloads  
        if blocked_patterns:  
            filters.append(URLPatternFilter(  
                patterns=blocked_patterns,  
                reverse=True  # Exclude matches  
            ))  
        
        return FilterChain(filters)
    
    async def crawl(self, urls: list[str] | str, max_depth: int = 2, max_pages: int = 50, timeout: int = 120):  
        """Main crawling function"""  
        if isinstance(urls, str):  
            urls = [urls]  
          
        # Filter out already visited URLs  
        urls_to_crawl = [url for url in urls if url not in self.visited_urls]  
        if not urls_to_crawl:  
            logger.info("All URLs already visited")  
            return  
          
        # Extract domain for filtering  
        base_domain = urlparse(urls_to_crawl[0]).netloc  
          
        # Create generic filter chain automatically  
        filter_chain = self.create_generic_filter_chain(  
            base_url=urls_to_crawl[0],  
            allow_subdomains=True,  # Allow docs.example.com, blog.example.com, etc.  
            blocked_patterns=None,  # Use defaults
            blocked_domains=[],
            allowed_content_types=None  # Use defaults  
        )
          
        deep_crawl_strategy = BFSDeepCrawlStrategy(  
            max_depth=max_depth,  
            include_external=False,  
            max_pages=max_pages,  
            filter_chain=filter_chain  
        )  
          
        # Configure crawler  
        browser_config = BrowserConfig(  
            headless=True,  
            verbose=True,
            # text_mode=True  # Skips image dimension updates
        )  
          
        run_config = CrawlerRunConfig(  
            deep_crawl_strategy=deep_crawl_strategy,  
            scraping_strategy=LXMLWebScrapingStrategy(),  
            stream=True,  
            verbose=True,  
            page_timeout=90000,  
            word_count_threshold=10,
            wait_until="load",
            simulate_user=True,
            delay_before_return_html=3.0
        )  
          
        results = []
        start_time = datetime.now()  
        last_result_time = start_time 
        async with AsyncWebCrawler(config=browser_config) as crawler:  
            logger.info(f"Starting crawl of {len(urls_to_crawl)} URLs with max_depth={max_depth}")  
            
            try:
                # Stream results with explicit completion handling 
                async def crawl_task():                    
                    async for result in await crawler.arun(urls_to_crawl[0], config=run_config):  
                        logger.info(f"Processing: {result.url} (Depth: {result.metadata.get('depth', 0) if result.metadata else 0})")
                        
                        if not result.success:  
                            error_msg = result.error_message or ""  
                            if any(err in error_msg for err in [  
                                "ERR_ABORTED",  
                                "Target page, context or browser has been closed",  
                                "ERR_HTTP_RESPONSE_CODE_FAILURE"  # Server-side errors  
                            ]):  
                                logger.debug(f"Skipping {result.url} - expected error during cleanup or server issue")  
                                continue
                            
                        self._save_page_data(result)  
                        results.append(result)

                # Apply timeout to the task, not the context manager
                await asyncio.wait_for(crawl_task(), timeout=timeout)
                    
            except asyncio.TimeoutError:  
                logger.warning(f"Crawl timed out after {timeout}s. Processed {len(results)} pages") 
            except StopAsyncIteration:  
                logger.info("Stream completed normally")  
            except Exception as e:  
                logger.error(f"Error during crawl: {e}")  
            finally:  
                elapsed = (datetime.now() - start_time).total_seconds()  
                logger.info(f"Crawl finished. Total results: {len(results)}, elapsed: {elapsed:.1f}s")    
                
        # Save index file  
        self._save_index(results)  
        logger.info(f"Crawl complete. Processed {len(results)} pages")  
          
        return results  
  