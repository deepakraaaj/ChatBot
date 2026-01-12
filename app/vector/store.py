
import chromadb
from chromadb.config import Settings
import logging
import os
from typing import List, Dict, Optional, Any
import uuid

# Configure Logging
logger = logging.getLogger(__name__)

class VectorStore:
    """
    A robust wrapper around ChromaDB for semantic search.
    Singleton pattern usage recommended.
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(VectorStore, cls).__new__(cls)
        return cls._instance

    def __init__(self, persist_directory: str = "./chroma_db", collection_name: str = "remp_knowledge"):
        # Prevent re-initialization if already initialized
        if hasattr(self, "client"):
            return

        logger.info(f"Initializing VectorStore in {persist_directory}")
        
        # Ensure directory exists
        os.makedirs(persist_directory, exist_ok=True)

        try:
            # Initialize Persistent Client
            self.client = chromadb.PersistentClient(path=persist_directory)
            
            # Get or Create Collection
            # Uses default embedding model (all-MiniLM-L6-v2) implicitly if embedding_function not specified
            self.collection = self.client.get_or_create_collection(name=collection_name)
            
            logger.info(f"VectorStore ready. Collection '{collection_name}' loaded. Count: {self.collection.count()}")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}", exc_info=True)
            raise e

    def add_texts(self, texts: List[str], metadatas: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None) -> List[str]:
        """
        Add text documents to the vector store.
        """
        if not texts:
            return []

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        
        if metadatas is None:
            metadatas = [{} for _ in texts]

        try:
            self.collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            logger.info(f"Added {len(texts)} documents to VectorStore.")
            return ids
        except Exception as e:
            logger.error(f"Error adding texts to VectorStore: {e}", exc_info=True)
            return []

    def search(self, query: str, k: int = 3, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Semantic search for relevant documents.
        Returns a list of dicts with 'text', 'metadata', 'distance'.
        """
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=k,
                where=filter # Optional metadata filtering
            )

            # Reformat results for easier consumption
            # Chroma returns lists of lists (one list per query)
            structured_results = []
            
            if results and results['ids']:
                count = len(results['ids'][0])
                for i in range(count):
                    structured_results.append({
                        "id": results['ids'][0][i],
                        "text": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "distance": results['distances'][0][i] if results['distances'] else 0.0
                    })
            
            return structured_results

        except Exception as e:
            logger.error(f"Error searching VectorStore: {e}", exc_info=True)
            return []

    def count(self) -> int:
        return self.collection.count()

    def reset(self):
        """Dangerous: Clears the collection"""
        # self.client.delete_collection(self.collection.name) # If needed
        pass

# Global Instance
# Usage: from app.vector.store import vector_store
vector_store = VectorStore()
