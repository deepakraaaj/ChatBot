import logging
import hashlib
from typing import List, Dict, Any
from app.core.es import ElasticsearchClient
from app.core.cache import CacheClient
from app.llm.router import llm_router

logger = logging.getLogger(__name__)

INDEX_NAME = "vector_knowledge"

class VectorService:
    @staticmethod
    async def ensure_index():
        """
        Creates the vector index with dense_vector mapping.
        """
        mapping = {
            "mappings": {
                "properties": {
                    "content": {"type": "text"},
                    "metadata": {"type": "object"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": 384, # all-MiniLM-L6-v2 uses 384
                        "index": True,
                        "similarity": "cosine"
                    }
                }
            }
        }
        await ElasticsearchClient.create_index(INDEX_NAME, mapping)

    @staticmethod
    async def add_texts(texts: List[str], metadatas: List[Dict[str, Any]] = None, ids: List[str] = None):
        """
        Generates embeddings in batch and uses bulk indexing for speed.
        If 'ids' provided, uses them as document IDs (allows updates).
        """
        if not texts:
            return

        try:
            # Batch generate embeddings
            embeddings_model = llm_router.get_embeddings()
            embeddings = embeddings_model.embed_documents(texts)
            
            documents = []
            for i, text in enumerate(texts):
                meta = metadatas[i] if metadatas else {}
                doc = {
                    "content": text,
                    "metadata": meta,
                    "embedding": embeddings[i]
                }
                if ids and i < len(ids):
                   doc["_id"] = str(ids[i])
                
                documents.append(doc)
            
            # Use High-Performance Bulk API
            # Note: ElasticsearchClient.bulk_index needs to handle _id if present in doc
            success, failed = await ElasticsearchClient.bulk_index(INDEX_NAME, documents)
            logger.info(f"Successfully indexed {success} documents. Failed: {len(failed)}")
            
        except Exception as e:
            logger.error(f"Failed to add texts to vector index: {e}", exc_info=True)

    @staticmethod
    async def search(query: str, k: int = 3, filter: dict = None, offset: int = 0) -> tuple[List[Dict], int]:
        """
        Highly optimized semantic search with embedding caching and pagination support.
        Returns: (results, total_hits)
        """
        try:
            # 1. Check Cache for Embedding
            query_hash = hashlib.md5(query.encode()).hexdigest()
            cache_key = f"embed:{query_hash}"
            query_vector = await CacheClient.get(cache_key)
            
            if not query_vector:
                # 2. Cache Miss: Generate and Store
                embeddings_model = llm_router.get_embeddings()
                query_vector = embeddings_model.embed_query(query)
                await CacheClient.set(cache_key, query_vector, expire=300) # Cache for 5 mins
            
            # 3. Optimized ES Filter Logic
            es_filter = None
            if filter:
                must_clauses = []
                for key, val in filter.items():
                    # Check for "assignee_name", "status" etc.
                    # Support for list values (terms query)
                    if isinstance(val, list):
                        must_clauses.append({"terms": {f"metadata.{key}": val}})
                    else:
                        must_clauses.append({"term": {f"metadata.{key}": val}})
                
                if must_clauses:
                    es_filter = {"bool": {"filter": must_clauses}} # Use filter context (faster/cached)

            # 4. Perform Vector Search with pagination
            hits, total_hits = await ElasticsearchClient.vector_search(INDEX_NAME, query_vector, k, es_filter, offset)
            
            # 5. Fast Response Mapping
            results = [
                {
                    "text": hit['_source'].get("content"),
                    "metadata": hit['_source'].get("metadata", {}),
                    "score": hit['_score']
                }
                for hit in hits
            ]
            return results, total_hits

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return [], 0
