"""
Data ingestion service for loading university program data into ChromaDB.
This service processes all program requirement files and stores them as embeddings.
"""

import os
import logging
from typing import List, Dict, Any
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
from langchain_community.embeddings import OllamaEmbeddings
from langchain_chroma import Chroma

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataIngestionService:
    def __init__(self):
        """Initialize the data ingestion service with ChromaDB and embeddings."""
        self.data_dir = "services/data"
        self.chroma_persist_dir = os.getenv("CHROMA_PERSIST_DIRECTORY")
        self.collection_name = os.getenv("CHROMA_COLLECTION_NAME")
        
        # Initialize embeddings
        self.embeddings = OllamaEmbeddings(
            model=os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        )
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(path=self.chroma_persist_dir)
        self.vector_store = Chroma(
            client=self.client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
        )
        
        # Text splitter for chunking documents
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

    def get_program_files(self) -> List[str]:
        """Get all program requirement file paths."""
        program_files = []
        for root, dirs, files in os.walk(self.data_dir):
            for file in files:
                if file == "requirements.txt":
                    program_files.append(os.path.join(root, file))
        return program_files

    def extract_program_metadata(self, file_path: str) -> Dict[str, Any]:
        """Extract metadata from the file path and content."""
        # Get program name from directory structure
        rel_path = os.path.relpath(file_path, self.data_dir)
        dir_parts = rel_path.split(os.sep)
        
        # Program name is the directory containing requirements.txt
        program_name = dir_parts[-2] if len(dir_parts) > 1 else "unknown"
        
        # Try to determine program type from name
        program_type = "unknown"
        if "bachelor_of_science" in program_name:
            program_type = "bachelor_science"
        elif "bachelor_of_arts" in program_name:
            program_type = "bachelor_arts"
        elif "certificate" in program_name:
            program_type = "certificate"
        elif "minor" in program_name:
            program_type = "minor"
        elif "double_major" in program_name:
            program_type = "double_major"
        
        return {
            "source": program_name,
            "program_type": program_type,
            "file_path": rel_path,
        }

    def process_program_file(self, file_path: str) -> List[Document]:
        """Process a single program file and convert it to documents."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            metadata = self.extract_program_metadata(file_path)
            
            # Create documents with metadata
            document = Document(
                page_content=content,
                metadata=metadata
            )
            
            # Split into chunks
            chunks = self.text_splitter.split_documents([document])
            return chunks
        
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            return []

    def ingest_all_data(self) -> bool:
        """Ingest all program data into ChromaDB."""
        try:
            program_files = self.get_program_files()
            logger.info(f"Found {len(program_files)} program files to process")
            
            all_chunks = []
            for file_path in program_files:
                chunks = self.process_program_file(file_path)
                all_chunks.extend(chunks)
                logger.info(f"Processed {file_path}: {len(chunks)} chunks")
            
            if not all_chunks:
                logger.error("No chunks were processed successfully")
                return False
            
            # Add documents to ChromaDB
            self.vector_store.add_documents(all_chunks)
            logger.info(f"Successfully ingested {len(all_chunks)} document chunks into ChromaDB")
            
            # Test retrieval
            test_results = self.vector_store.similarity_search("computer science requirements", k=2)
            logger.info(f"Test retrieval successful: Found {len(test_results)} relevant documents")
            
            return True
            
        except Exception as e:
            logger.error(f"Error during data ingestion: {e}")
            return False

    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the ChromaDB collection."""
        try:
            collection = self.client.get_collection(self.collection_name)
            return {
                "collection_name": self.collection_name,
                "document_count": collection.count(),
                "metadata": collection.metadata or {}
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {"error": str(e)}


def main():
    """Main function to run data ingestion."""
    service = DataIngestionService()
    
    logger.info("Starting data ingestion...")
    success = service.ingest_all_data()
    
    if success:
        logger.info("Data ingestion completed successfully!")
        info = service.get_collection_info()
        logger.info(f"Collection info: {info}")
    else:
        logger.error("Data ingestion failed!")


if __name__ == "__main__":
    main()