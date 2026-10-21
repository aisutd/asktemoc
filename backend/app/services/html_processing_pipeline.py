import json  
import logging  
from io import BytesIO  
from pathlib import Path  
from typing import Any, Dict, List, Optional, Union  
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict  
from docling.backend.html_backend import HTMLDocumentBackend  
from docling.datamodel.base_models import InputFormat  
from docling.datamodel.document import InputDocument  
from docling.chunking import HybridChunker  
from docling_core.types.doc import DoclingDocument  

from transformers import AutoTokenizer  

logging.basicConfig(level=logging.INFO)  
logger = logging.getLogger(__name__)  
  
class ChunkMetadata(BaseModel):  
    """Metadata for a chunk of processed content."""  
    document_name: str = Field(..., description="Name of the source document")  
    headings: List[str] = Field(default_factory=list, description="Hierarchical headings context")  
    doc_items: List[str] = Field(default_factory=list, description="Document item references")  
    origin: Optional[Dict[str, str]] = Field(None, description="Origin information (filename, mimetype)")  
      
    model_config = ConfigDict(extra="allow")  
  
  
class ChunkResult(BaseModel):  
    """Represents a single chunk of processed content."""  
    content: str = Field(..., min_length=1, description="The chunked text content")  
    source: str = Field(..., description="Origin of the content (file path, raw HTML, or JSON)")  
    metadata: Optional[ChunkMetadata] = Field(None, description="Additional metadata about the chunk")  
      
    @field_validator('content')  
    @classmethod  
    def validate_content_not_empty(cls, v: str) -> str:  
        """Ensure content is not just whitespace."""  
        if not v.strip():  
            raise ValueError("Content cannot be empty or whitespace-only")  
        return v  
  
  
class PipelineConfig(BaseModel):  
    """Configuration for the HTML processing pipeline."""  
    chunker: Optional[HybridChunker] = Field(None, description="Custom chunker instance")  
    validate_html: bool = Field(True, description="Whether to validate HTML structure")  
    min_chunk_length: int = Field(1, ge=1, description="Minimum chunk length in characters")  
      
    model_config = ConfigDict(arbitrary_types_allowed=True)  
  
  
class HTMLInput(BaseModel):  
    """Validated input for HTML processing."""  
      
    html_content: str = Field(..., min_length=1, description="HTML content to process")  
    source: str = Field(..., description="Source identifier")  
      
    @field_validator('html_content')  
    @classmethod  
    def validate_html_tags(cls, v: str) -> str:  
        """Basic validation that content looks like HTML."""  
        if '<' not in v or '>' not in v:  
            raise ValueError("Content does not appear to be valid HTML")  
        return v  
  
  
class HTMLProcessingPipeline:  
    """  
    Flexible pipeline for processing HTML from multiple input formats.  
    Handles HTML files, raw HTML text, and JSON objects with HTML content.  
    """  
      
    def __init__(self, config: Optional[PipelineConfig] = None):  
        """  
        Initialize the pipeline.  
          
        Args:  
            config: Optional PipelineConfig instance. If None, uses defaults.  
        """  
        self.config = config or PipelineConfig()  
        self.chunker = self.config.chunker or HybridChunker()  
        logger.info("HTMLProcessingPipeline initialized with Pydantic models")  
      
    def process(  
        self,  
        input_data: Union[str, Path, Dict[str, Any]],  
        source_name: Optional[str] = None  
    ) -> List[ChunkResult]:  
        """  
        Process HTML content from various input formats.  
          
        Args:  
            input_data: Can be:  
                - Path or str (file path)  
                - str (raw HTML text)  
                - Dict with 'html' field (JSON object)  
            source_name: Optional name to identify the source  
              
        Returns:  
            List of validated ChunkResult objects containing chunked content  
              
        Raises:  
            ValueError: If input format is invalid or HTML content is missing  
            ValidationError: If Pydantic validation fails  
        """  
        try:   
            html_input = self._extract_and_validate_html(input_data, source_name)  
              
            doc = self._html_to_document(html_input.html_content, html_input.source)  
              
            chunks = self._chunk_document(doc, html_input.source)  
              
            logger.info(f"Successfully processed {len(chunks)} chunks from {html_input.source}")  
            return chunks  
              
        except Exception as e:  
            logger.error(f"Pipeline failed for source '{source_name}': {str(e)}")  
            raise  
      
    def _extract_and_validate_html(  
        self,  
        input_data: Union[str, Path, Dict[str, Any]],  
        source_name: Optional[str]  
    ) -> HTMLInput:  
        """  
        Extract HTML content and validate using Pydantic.  
          
        Returns:  
            Validated HTMLInput object  
        """  
        # Case 1: Dictionary/JSON input  
        if isinstance(input_data, dict):    
            html_content = input_data.get('cleaned_html', '')  
            if not html_content:  
                html_content = input_data.get('html', '')  
            if not html_content:      
                html_content = input_data.get('content', '') or input_data.get('html_content', '')    
            if not html_content:    
                raise ValueError("JSON object missing 'cleaned_html', 'html' field or valid fallback")
            
            datetime_value = input_data.get('crawled_at')     
                
            source = source_name or "JSON object"    
            logger.info(f"Extracted HTML from JSON object (length: {len(html_content)})")    
                
            return html_content, source, datetime_value
          
        # Case 2: File path  
        if isinstance(input_data, (Path, str)):  
            path = Path(input_data)  
  
            if path.exists() and path.is_file():  
                html_content = path.read_text(encoding='utf-8')  
                source = str(path)  
                logger.info(f"Read HTML from file: {source}")  
                
                return html_content, source, datetime.now().isoformat()
              
            # Case 3: Raw HTML text (not a valid file path)  
            html_content = str(input_data)  
            source = source_name or "raw HTML text"  
            logger.info(f"Processing raw HTML text (length: {len(html_content)})")  
              
            return html_content, source, datetime.now().isoformat() 
          
        raise ValueError(f"Unsupported input type: {type(input_data)}")  
      
    def _html_to_document(self, html_content: str, source: str) -> DoclingDocument:  
        """  
        Convert HTML content to DoclingDocument using HTMLDocumentBackend.  
        """  
        try:    
            html_bytes = html_content.encode('utf-8')  
            stream = BytesIO(html_bytes)  
                
            in_doc = InputDocument(  
                path_or_stream=stream,  
                format=InputFormat.HTML,  
                backend=HTMLDocumentBackend,  
                filename=source  
            )  
              
            backend = HTMLDocumentBackend(  
                in_doc=in_doc,  
                path_or_stream=stream  
            )  
              
            if self.config.validate_html and not backend.is_valid():  
                raise ValueError(f"Invalid HTML document from source: {source}")  
              
            doc = backend.convert()  
            logger.info(f"Converted HTML to DoclingDocument: {doc.name}")  
            return doc  
              
        except Exception as e:  
            logger.error(f"Failed to convert HTML to document: {str(e)}")  
            raise  
      
    def _chunk_document(  
        self,  
        doc: DoclingDocument,  
        source: str,
        datetime_value: Optional[str] = None 
    ) -> List[ChunkResult]:  
        """  
        Chunk the DoclingDocument into validated ChunkResult objects.  
        """  
        try:  
            chunks = []   
            for chunk in self.chunker.chunk(doc):   
                metadata = {  
                    'document_name': doc.name,  
                    'headings': chunk.meta.headings if hasattr(chunk.meta, 'headings') else [],  
                    'doc_items': [str(item) for item in (chunk.meta.doc_items if hasattr(chunk.meta, 'doc_items') else [])]  
                }  
                   
                if doc.origin:  
                    metadata['origin'] = {  
                        'filename': doc.origin.filename,  
                        'mimetype': doc.origin.mimetype  
                    } 
                    
                if datetime_value:  
                    metadata['datetime'] = datetime_value 
                   
                    
                chunk_result = ChunkResult(  
                    content=chunk.text,  
                    source=source,  
                    metadata=metadata  
                )  
                   
                if len(chunk_result.content) >= self.config.min_chunk_length:  
                    chunks.append(chunk_result)  
                else:  
                    logger.debug(f"Skipping chunk below minimum length: {len(chunk_result.content)} chars")  
              
            return chunks  
              
        except Exception as e:  
            logger.error(f"Failed to chunk document: {str(e)}")  
            raise  
  