"""
crawl4ai scraper — sample UTD pages.
Scrapes 3 UTD pages and saves each as markdown plus a summary JSON.

Usage (from repo root):
    pip install crawl4ai
    crawl4ai-setup          # first time only — downloads the browser
    python backend/crawl4ai_scraper.py

Output lands in backend/crawl4ai_output/.
"""
import asyncio
import json
from pathlib import Path

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

URLS = [
    ("utd_home",          "https://www.utdallas.edu/"),
    ("utd_academics",     "https://www.utdallas.edu/academics/"),
    ("utd_tuition_rates", "https://bursar.utdallas.edu/tuition/tuition-rates/"),
]

# Output sits next to this file so it's easy to find and gitignore-safe
OUTPUT_DIR = Path(__file__).parent / "crawl4ai_output"
OUTPUT_DIR.mkdir(exist_ok=True)


async def scrape_page(crawler: AsyncWebCrawler, name: str, url: str) -> dict:
    print(f"\n→ [{name}] {url}")
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=10,
        remove_overlay_elements=True,
    )
    result = await crawler.arun(url=url, config=config)

    md_path = OUTPUT_DIR / f"{name}.md"
    md_path.write_text(result.markdown or "", encoding="utf-8")

    markdown = result.markdown or ""
    return {
        "name": name,
        "url": url,
        "success": result.success,
        "status_code": result.status_code,
        "word_count": len(markdown.split()),
        "internal_links": len(result.links.get("internal", [])),
        "external_links": len(result.links.get("external", [])),
        "images": len(result.media.get("images", [])),
        "output_file": str(md_path),
        "preview": markdown[:400].replace("\n", " "),
    }


async def main():
    summaries = []

    async with AsyncWebCrawler() as crawler:
        for name, url in URLS:
            summary = await scrape_page(crawler, name, url)
            summaries.append(summary)
            status = "✓" if summary["success"] else "✗"
            print(f"  {status} HTTP {summary['status_code']} | "
                  f"{summary['word_count']} words | "
                  f"{summary['internal_links']} internal links | "
                  f"{summary['images']} images")

    summary_path = OUTPUT_DIR / "summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    for s in summaries:
        print(f"\n[{s['name']}]")
        print(f"  URL:     {s['url']}")
        print(f"  Status:  {'OK' if s['success'] else 'FAILED'} (HTTP {s['status_code']})")
        print(f"  Words:   {s['word_count']}")
        print(f"  Links:   {s['internal_links']} internal / {s['external_links']} external")
        print(f"  Output:  {s['output_file']}")

    print(f"\nMarkdown files: {OUTPUT_DIR}/")
    print(f"Summary JSON:   {summary_path}")


asyncio.run(main())
