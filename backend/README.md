# UTD Catalog Scraper

A Python web scraper using Playwright to extract program requirements and example degree plans from the UTD undergraduate catalog.

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:
```bash
playwright install
```

## Usage

### Basic Usage

```python
from scraper import UTDCatalogScraper

scraper = UTDCatalogScraper()
await scraper.scrape()
```

### With Configuration

```python
scraper = UTDCatalogScraper(
    max_pages=10,          # Limit to 10 pages
    rate_limit=2.0,        # 2 second delay between requests
    max_parallel=5,        # 5 concurrent browser instances
    output_dir="./data"    # Custom output directory
)
await scraper.scrape()
```

### Testing with Single Page

```bash
python test_scraper.py
```

## Configuration Options

- `max_pages`: Limit number of pages to scrape (None for all)
- `rate_limit`: Delay between requests in seconds (default: 1.0)
- `max_parallel`: Number of concurrent browser instances (default: 3)
- `output_dir`: Output directory path (default: `./output`)

## Output Structure

```
output/
  {major_name}/
    requirements.txt
    example.txt
```

