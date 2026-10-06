import hashlib
from html.parser import HTMLParser
from typing import Optional, List, Dict, Any

class _HTMLTextExtractor(HTMLParser):
    """Simple HTML to text extractor using the standard library."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._chunks.append(data)

    def get_text(self) -> str:
        return " ".join(part.strip() for part in self._chunks if part.strip())


class IngestService():
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize the IngestService.

        Args:
            chunk_size: Maximum size of text chunks in characters (default: 1000).
            chunk_overlap: Number of characters to overlap between chunks (default: 200).
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _split_text(self, text: str) -> List[str]:
        """
        Split text into chunks with overlap.

        Args:
            text: Text to split.

        Returns:
            List of text chunks.
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            
            # Try to break at sentence boundary if not at the end
            if end < len(text):
                # Look for sentence endings near the end
                for break_char in ['. ', '.\n', '! ', '!\n', '? ', '?\n']:
                    last_break = chunk.rfind(break_char)
                    if last_break > self.chunk_size // 2:  # Only break if reasonable
                        chunk = chunk[:last_break + 1]
                        end = start + len(chunk)
                        break
            
            chunks.append(chunk.strip())
            start = end - self.chunk_overlap

        return chunks

    def _create_chunks(self, text: str, source_url: str, base_chunk_id: str = "1") -> List[Dict[str, Any]]:
        """
        Create chunk dictionaries from text.

        Args:
            text: Text to chunk.
            source_url: Source URL for the chunks.
            base_chunk_id: Base ID for chunk numbering.

        Returns:
            List of chunk dictionaries with chunk_id, text, and source_url.
        """
        text_chunks = self._split_text(text)
        chunks: List[Dict[str, Any]] = []

        for i, chunk_text in enumerate(text_chunks):
            if not chunk_text.strip():
                continue
            
            chunk_id = f"{base_chunk_id}_{i+1}" if len(text_chunks) > 1 else base_chunk_id
            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "source_url": source_url
            })

        return chunks

    def process_HTML(self, html_content: str, source_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Convert basic HTML to plain text and return as JSON chunks.

        Args:
            html_content: The HTML string to process.
            source_url: Optional source URL. If not provided, generates a hash-based URL.

        Returns:
            List of dictionaries with chunk_id, text, and source_url fields.
        """
        parser = _HTMLTextExtractor()
        parser.feed(html_content)
        text = parser.get_text()

        if not source_url:
            # Generate a hash-based identifier
            content_hash = hashlib.md5(html_content.encode()).hexdigest()[:8]
            source_url = f"html://content/{content_hash}"

        return self._create_chunks(text, source_url, base_chunk_id="html")
    
    def process_html_from_url(self, url: str, timeout: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch HTML content from a URL and return as JSON chunks.

        Args:
            url: The URL to fetch HTML content from.
            timeout: Request timeout in seconds (default: 30).

        Returns:
            List of dictionaries with chunk_id, text, and source_url fields.

        Raises:
            requests.RequestException: If the request fails (connection error, timeout, etc.).
            RuntimeError: If requests library is not installed.
        """
        try:
            import requests  # type: ignore
        except ImportError:
            raise RuntimeError(
                "requests is required for URL HTML ingestion. Add 'requests' to requirements and install."
            )

        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()  # Raises an HTTPError for bad responses
            html_content = response.text
        except requests.RequestException as e:
            raise requests.RequestException(
                f"Failed to fetch HTML from URL '{url}': {str(e)}"
            ) from e

        # Use the URL as the source_url
        return self.process_HTML(html_content, source_url=url)
    
    def process_pdf(self, file_path: str, source_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract text from a PDF file and return as JSON chunks.

        Args:
            file_path: Path to the PDF file on disk.
            source_url: Optional source URL. If not provided, uses file:// path.

        Returns:
            List of dictionaries with chunk_id, text, and source_url fields.

        Raises:
            RuntimeError: If PyPDF2 is not installed.
        """
        try:
            import PyPDF2  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "PyPDF2 is required for PDF ingestion. Add 'PyPDF2' to requirements and install."
            )

        if not source_url:
            source_url = f"file://{file_path}"

        text_chunks: list[str] = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text: Optional[str] = page.extract_text()
                if page_text:
                    text_chunks.append(page_text)
        
        full_text = "\n".join(text_chunks)
        return self._create_chunks(full_text, source_url, base_chunk_id="pdf")

    def process_word(self, file_path: str, source_url: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Extract text from a DOCX file and return as JSON chunks.

        Args:
            file_path: Path to the .docx file on disk.
            source_url: Optional source URL. If not provided, uses file:// path.

        Returns:
            List of dictionaries with chunk_id, text, and source_url fields.

        Raises:
            RuntimeError: If python-docx is not installed.
        """
        try:
            import docx  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "python-docx is required for DOCX ingestion. Add 'python-docx' to requirements and install."
            ) from exc

        if not source_url:
            source_url = f"file://{file_path}"

        document = docx.Document(file_path)
        paragraphs = [p.text.strip() for p in document.paragraphs if p.text and p.text.strip()]
        full_text = "\n".join(paragraphs)
        
        return self._create_chunks(full_text, source_url, base_chunk_id="docx")

    