
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
    async def add_texts(texts: List[str], metadatas: List[Dict[str, Any]] = None):
        """
        Generates embeddings in batch and uses bulk indexing for speed.
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
                documents.append({
                    "content": text,
                    "metadata": meta,
                    "embedding": embeddings[i]
                })
            
            # Use High-Performance Bulk API
            success, failed = await ElasticsearchClient.bulk_index(INDEX_NAME, documents)
            logger.info(f"Successfully indexed {success} documents. Failed: {len(failed)}")
            
        except Exception as e:
            logger.error(f"Failed to add texts to vector index: {e}", exc_info=True)

    @staticmethod
    async def search(query: str, k: int = 3, filter: dict = None) -> List[Dict]:
        """
        Highly optimized semantic search with embedding caching.
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
                must_clauses = [{"term": {f"metadata.{key}": val}} for key, val in filter.items()]
                if must_clauses:
                    es_filter = {"bool": {"must": must_clauses}}

            # 4. Perform Vector Search
            hits = await ElasticsearchClient.vector_search(INDEX_NAME, query_vector, k, es_filter)
            
            # 5. Fast Response Mapping
            return [
                {
                    "text": hit['_source'].get("content"),
                    "metadata": hit['_source'].get("metadata", {}),
                    "score": hit['_score']
                }
                for hit in hits
            ]

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []
