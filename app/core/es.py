import logging
from typing import List, Dict, Any
from elasticsearch import AsyncElasticsearch, helpers
from app.core.settings import settings

logger = logging.getLogger(__name__)

class ElasticsearchClient:
    client: AsyncElasticsearch = None

    @classmethod
    def get_client(cls) -> AsyncElasticsearch:
        if cls.client is None:
            logger.info(f"Initializing optimized Elasticsearch client at {settings.elasticsearch.url}")
            cls.client = AsyncElasticsearch(
                hosts=[settings.elasticsearch.url],
                retry_on_timeout=True,
                max_retries=3,
                request_timeout=30
            )
        return cls.client

    @classmethod
    async def create_index(cls, index_name: str, mapping: dict = None):
        client = cls.get_client()
        if not await client.indices.exists(index=index_name):
            await client.indices.create(index=index_name, body=mapping or {})
            logger.info(f"Created index: {index_name}")

    @classmethod
    async def index_document(cls, index_name: str, doc: dict, doc_id: str = None):
        client = cls.get_client()
        resp = await client.index(index=index_name, document=doc, id=doc_id)
        return resp

    @classmethod
    async def bulk_index(cls, index_name: str, documents: List[Dict[str, Any]]):
        """
        High-performance bulk indexing using async_bulk helper.
        """
        client = cls.get_client()
        
        async def actions():
            for doc in documents:
                action = {
                    "_index": index_name,
                    "_source": doc
                }
                # Support explicit ID if provided in doc (removed from source)
                if "_id" in doc:
                    action["_id"] = doc.pop("_id")
                
                yield action

        try:
            success, failed = await helpers.async_bulk(client, actions())
            logger.info(f"Bulk index complete: {success} succeeded, {len(failed)} failed.")
            return success, failed
        except Exception as e:
            logger.error(f"Bulk indexing failed: {e}", exc_info=True)
            return 0, []

    @classmethod
    async def search(cls, index_name: str, query: dict, size: int = 10):
        client = cls.get_client()
        if not await client.indices.exists(index=index_name):
            return []
        resp = await client.search(index=index_name, body=query, size=size)
        return resp['hits']['hits']

    @classmethod
    async def vector_search(cls, index_name: str, query_vector: list, k: int = 3, filter: dict = None, offset: int = 0):
        """
        Performs KNN search using vector/dense_vector field 'embedding' with pagination support.
        Returns: (hits, total_hits)
        """
        client = cls.get_client()
        if not await client.indices.exists(index=index_name):
            return []
            
        knn_query = {
            "field": "embedding",
            "query_vector": query_vector,
            "k": k,
            "num_candidates": max(k * 10, 100) # Ensure a reasonable number of candidates
        }
        
        if filter:
            knn_query["filter"] = filter

        try:
            resp = await client.search(
                index=index_name, 
                knn=knn_query,
                from_=offset,  # Pagination offset
                size=k,  # Page size
                source=["content", "metadata"],
                _source_includes=["content", "metadata"] # Redundant but explicit for speed
            )
            total_hits = resp['hits']['total']['value']
            return resp['hits']['hits'], total_hits
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return [], 0

    @classmethod
    async def close(cls):
        if cls.client:
            await cls.client.close()
            cls.client = None
