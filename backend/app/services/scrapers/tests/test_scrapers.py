"""
Integration-style tests for the three scrapers.
All browser and HTTP calls are mocked — no network access needed.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.services.scrapers import scraper_state
from app.services.scrapers.catalog_scraper import UTDCatalogScraper
from app.services.scrapers.housing_scraper import UTDHousingScraper
from app.services.scrapers.general_webscraper import (
    WebCrawlingPipeline,
    UTD_START_URL,
    UTD_ALLOWED_DOMAINS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_state():
    return {"pages": {}, "queue": []}


# ===========================================================================
# UTDCatalogScraper
# ===========================================================================

class TestUTDCatalogScraper:
    def test_sanitize_filename(self):
        scraper = UTDCatalogScraper()
        assert scraper._sanitize_filename("Bachelor of Science in CS!") == "bachelor_of_science_in_cs"
        assert scraper._sanitize_filename("  leading spaces  ") == "leading_spaces"

    def test_output_dir_created(self, tmp_path):
        target = tmp_path / "catalog_out"
        UTDCatalogScraper(output_dir=str(target))
        assert target.exists()

    @pytest.mark.asyncio
    async def test_save_to_disk_writes_files(self, tmp_path):
        scraper = UTDCatalogScraper(output_dir=str(tmp_path))
        scraper._save_to_disk("Computer Science", "CS requirements text", "CS example text")

        major_dir = tmp_path / "computer_science"
        assert (major_dir / "requirements.txt").read_text() == "CS requirements text"
        assert (major_dir / "example.txt").read_text() == "CS example text"

    @pytest.mark.asyncio
    async def test_save_to_disk_skips_none_fields(self, tmp_path):
        scraper = UTDCatalogScraper(output_dir=str(tmp_path))
        scraper._save_to_disk("Biology", None, None)

        major_dir = tmp_path / "biology"
        # Directory should still be created
        assert major_dir.exists()
        assert not (major_dir / "requirements.txt").exists()
        assert not (major_dir / "example.txt").exists()

    @pytest.mark.asyncio
    async def test_scrape_single_program_publishes_on_change(self, tmp_path):
        scraper = UTDCatalogScraper(output_dir=str(tmp_path))
        state = _empty_state()

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.query_selector_all = AsyncMock(return_value=[])
        mock_page.inner_text = AsyncMock(return_value="Program requirements content")
        mock_page.evaluate = AsyncMock()

        mock_context = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()

        mock_browser = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)

        with (
            patch.object(scraper, "scrape_program_page", AsyncMock(return_value=("Requirements text", None))),
            patch("app.services.scrapers.catalog_scraper.publish_page", AsyncMock(return_value=True)) as mock_pub,
        ):
            await scraper._scrape_single_program(mock_browser, "https://catalog.utdallas.edu/cs", "Computer Science", state)

        mock_pub.assert_called_once()
        call_kwargs = mock_pub.call_args[1]
        assert call_kwargs["url"] == "https://catalog.utdallas.edu/cs"
        assert "Requirements text" in call_kwargs["text_content"]

    @pytest.mark.asyncio
    async def test_scrape_single_program_skips_publish_when_unchanged(self, tmp_path):
        scraper = UTDCatalogScraper(output_dir=str(tmp_path))
        content = "Same content"
        state = _empty_state()
        scraper_state.record_scraped("https://catalog.utdallas.edu/cs", content, "catalog", state)

        with (
            patch.object(scraper, "scrape_program_page", AsyncMock(return_value=(content, None))),
            patch("app.services.scrapers.catalog_scraper.publish_page", AsyncMock()) as mock_pub,
        ):
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_context.new_page = AsyncMock(return_value=AsyncMock())
            mock_context.close = AsyncMock()
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            await scraper._scrape_single_program(mock_browser, "https://catalog.utdallas.edu/cs", "CS", state)

        mock_pub.assert_not_called()


# ===========================================================================
# UTDHousingScraper
# ===========================================================================

class TestUTDHousingScraper:
    def test_sanitize_filename(self):
        assert UTDHousingScraper._sanitize_filename("Apply for Housing!") == "apply_for_housing"
        assert UTDHousingScraper._sanitize_filename("") == "index"

    def test_normalize_url_strips_fragments(self):
        scraper = UTDHousingScraper()
        result = scraper._normalize_url("https://housing.utdallas.edu/page#section")
        assert "#" not in result
        assert result == "https://housing.utdallas.edu/page"

    def test_normalize_url_strips_trailing_slash(self):
        scraper = UTDHousingScraper()
        assert scraper._normalize_url("https://housing.utdallas.edu/") == "https://housing.utdallas.edu"

    def test_is_valid_link_rejects_external(self):
        scraper = UTDHousingScraper()
        assert scraper._is_valid_link("https://google.com/page") is False

    def test_is_valid_link_rejects_binary_extensions(self):
        scraper = UTDHousingScraper()
        for ext in [".pdf", ".jpg", ".zip", ".mp4"]:
            assert scraper._is_valid_link(f"https://housing.utdallas.edu/file{ext}") is False

    def test_is_valid_link_rejects_mailto(self):
        scraper = UTDHousingScraper()
        assert scraper._is_valid_link("mailto:info@utdallas.edu") is False

    def test_is_valid_link_accepts_internal_html_page(self):
        scraper = UTDHousingScraper()
        assert scraper._is_valid_link("https://housing.utdallas.edu/apply") is True

    @pytest.mark.asyncio
    async def test_bfs_crawl_publishes_new_page(self, tmp_path):
        scraper = UTDHousingScraper(output_dir=str(tmp_path), max_depth=0, max_pages=1)
        state = _empty_state()

        fake_data = {"url": "https://housing.utdallas.edu", "title": "Housing", "content": "Housing content"}

        with (
            patch.object(scraper, "_scrape_and_extract", AsyncMock(return_value=(fake_data, []))),
            patch("app.services.scrapers.housing_scraper.publish_page", AsyncMock(return_value=True)) as mock_pub,
        ):
            mock_browser = AsyncMock()
            await scraper._bfs_crawl(mock_browser, state)

        mock_pub.assert_called_once()
        assert "housing.utdallas.edu" in mock_pub.call_args[1]["url"]

    @pytest.mark.asyncio
    async def test_save_results_writes_txt_and_index(self, tmp_path):
        scraper = UTDHousingScraper(output_dir=str(tmp_path))
        scraper.results = [
            {"url": "https://housing.utdallas.edu", "title": "Home", "content": "Welcome", "depth": 0},
        ]
        scraper._save_results()

        housing_dir = tmp_path / "housing"
        assert (housing_dir / "index.txt").exists() or (housing_dir / "index.json").exists()
        index = json.loads((housing_dir / "index.json").read_text())
        assert index["total_pages"] == 1


# ===========================================================================
# WebCrawlingPipeline (general_webscraper)
# ===========================================================================

class TestWebCrawlingPipeline:
    def test_get_filename_from_url(self, tmp_path):
        pipeline = WebCrawlingPipeline(output_folder=str(tmp_path))
        name = pipeline._get_filename("https://www.utdallas.edu/about/mission")
        assert "utdallas.edu" in name
        assert "about" in name

    def test_get_filename_root_url(self, tmp_path):
        pipeline = WebCrawlingPipeline(output_folder=str(tmp_path))
        name = pipeline._get_filename("https://www.utdallas.edu/")
        assert name.endswith("index")

    def test_visited_urls_loaded_from_existing_index(self, tmp_path):
        index = {
            "visited_urls": ["https://www.utdallas.edu", "https://housing.utdallas.edu"],
            "pages": [],
        }
        (tmp_path / "index.json").write_text(json.dumps(index))
        pipeline = WebCrawlingPipeline(output_folder=str(tmp_path))
        assert "https://www.utdallas.edu" in pipeline.visited_urls
        assert "https://housing.utdallas.edu" in pipeline.visited_urls

    def test_utd_start_url_is_main_page(self):
        assert "utdallas.edu" in UTD_START_URL

    def test_utd_allowed_domains_includes_key_subdomains(self):
        required = {"housing.utdallas.edu", "catalog.utdallas.edu", "www.utdallas.edu"}
        assert required.issubset(set(UTD_ALLOWED_DOMAINS))

    def test_build_filter_chain_returns_filter_chain(self, tmp_path):
        pipeline = WebCrawlingPipeline(output_folder=str(tmp_path))
        chain = pipeline._build_filter_chain(UTD_ALLOWED_DOMAINS)
        assert chain is not None

    @pytest.mark.asyncio
    async def test_save_page_data_skips_aborted_result(self, tmp_path):
        pipeline = WebCrawlingPipeline(output_folder=str(tmp_path))

        result = MagicMock()
        result.success = False
        result.error_message = "ERR_ABORTED - something"
        result.url = "https://www.utdallas.edu/page"

        content, title = pipeline._save_page_data(result)
        assert content == ""
        assert title == ""
        # No JSON file should be written
        assert not list(tmp_path.glob("*.json"))

    @pytest.mark.asyncio
    async def test_save_page_data_writes_json_on_success(self, tmp_path):
        pipeline = WebCrawlingPipeline(output_folder=str(tmp_path))

        mock_markdown = MagicMock()
        mock_markdown.raw_markdown = "# Page Content"

        result = MagicMock()
        result.success = True
        result.url = "https://www.utdallas.edu/about"
        result.status_code = 200
        result.html = "<html></html>"
        result.cleaned_html = "<p></p>"
        result.markdown = mock_markdown
        result.links = {"internal": [], "external": []}
        result.media = {}
        result.metadata = {"depth": 1, "title": "About UTD"}

        content, title = pipeline._save_page_data(result)
        assert content == "# Page Content"
        assert title == "About UTD"

        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text())
        assert data["url"] == "https://www.utdallas.edu/about"
        assert data["markdown"] == "# Page Content"

    @pytest.mark.asyncio
    async def test_crawl_skips_already_visited_urls(self, tmp_path):
        pipeline = WebCrawlingPipeline(output_folder=str(tmp_path))
        pipeline.visited_urls.add("https://www.utdallas.edu")

        with patch("app.services.scrapers.general_webscraper.AsyncWebCrawler") as mock_crawler_cls:
            result = await pipeline.crawl("https://www.utdallas.edu")

        # Should return None/empty without starting crawl
        assert result == [] or result is None
        mock_crawler_cls.assert_not_called()
