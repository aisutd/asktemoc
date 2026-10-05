# UTD Catalog Scraper

A Python web scraper using Playwright to extract program requirements and example
degree plans from the UTD undergraduate catalog. It produces the plain-text corpus
the assistant answers from.

> The committed corpus lives in `data/catalog/` at the repo root, and
> `backend/scripts/seed_catalog.py` loads it into the vector store. Rerun the
> scraper only to refresh that snapshot.

## Installation

1. Create a virtual environment and install dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-scrape.txt
```

2. Install the browser build matching the installed Playwright version:

```bash
playwright install chromium
```

Run this from the activated venv. Playwright pins an exact browser build, so a
Chromium installed by a different Playwright version won't be used and launching
fails with `Executable doesn't exist`.

## Usage

```python
import asyncio
from scraper import UTDCatalogScraper

asyncio.run(UTDCatalogScraper().scrape())
```

### With Configuration

```python
scraper = UTDCatalogScraper(
    max_pages=10,          # Limit to 10 programs
    rate_limit=2.0,        # 2 second delay between requests
    max_parallel=5,        # 5 concurrent browser contexts
    output_dir="./data"    # Custom output directory
)
asyncio.run(scraper.scrape())
```

### Full run

```bash
python test_scraper.py
```

Run from `backend/scrapers/catalog/`. Despite the name, this scrapes **every**
program (`max_pages=None`) into `./test_output` (gitignored) with `rate_limit=2.0` and `max_parallel=5`. Expect roughly 115
programs and several minutes. Pass `max_pages` to try a handful first.

## Configuration Options

- `max_pages`: Limit number of programs to scrape (None for all)
- `rate_limit`: Delay between requests in seconds (default: 1.0)
- `max_parallel`: Number of concurrent browser contexts (default: 3)
- `output_dir`: Output directory path (default: `./output`)

## How Programs Are Discovered

From the catalog's program index, the scraper collects links inside any `<p>`
mentioning "credit hours", plus any link whose text mentions "Concentration".
Footnote anchors (`…/programs#footnote-1`, link text `1`) and the index page itself
are skipped. URL fragments are kept, since concentrations of the same degree differ
only by fragment.

## Output Structure

```
output/
  {major_name}/
    requirements.txt    program page text
    example.txt         example degree plan, when the program links to one
```

`example.txt` is absent for programs with no "example degree requirements" link —
most double majors, for instance. Extracted text currently includes some page
chrome (for example "Download page as a PDF"), because the catalog's markup doesn't
match the `main`/`#content` selectors the scraper prefers.

`data/catalog/` at the repo root is a committed snapshot of a previous full run.
To refresh it, copy a new `test_output/` over `data/catalog/` and re-seed.
