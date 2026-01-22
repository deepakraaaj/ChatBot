from typing import Dict, Any, List
from app.graph.state import GraphState
from app.services.vector import VectorService
from app.core.prompts import REPLY_SYSTEM_PROMPT
import logging
import json

logger = logging.getLogger(__name__)

PAGE_SIZE = 20  # Number of results per page

class VectorSearchNode:
    async def __call__(self, state: GraphState) -> GraphState:
        """
        Executes a search against the Vector Index with pagination support.
        Handles both "Fuzzy Search" and "Structured Filtering" (Hybrid).
        """
        try:
            messages = state["messages"]
            last_message = messages[-1].content
            user_id = state.get("user_id")
            company_id = state.get("company_id")
            
            # Check if this is a pagination request
            current_offset = state.get("pagination_offset", 0)
            last_query = state.get("last_query")
            
            # Determine the query to use
            query = last_query if current_offset > 0 else last_message
            
            logger.info(f"Vector Search Request: '{query}' (offset: {current_offset})")
            
            # 1. Prepare Filters (Hybrid Search)
            # We automatically filter by company_id for security
            filters = {}
            if company_id:
                filters["company_id"] = int(company_id)
            
            # TODO: Advanced filter extraction (e.g. "my tasks" -> assignee_name check?)
            # For now, we rely on Vector Semantic Match to handle "my tasks" mapping if the embedding is good.
            # But strict ID filtering is better. 
            
            # Simple heuristic for "My Tasks"
            if "my" in last_message.lower() and user_id:
                # We can't easily filter by user_id in vector metadata unless we synced it.
                # In SyncService we added 'assignee_name'. 
                # Ideally we synced 'assigned_user_id' too.
                # Let's check SyncService... we synced 'assignee_name' but not ID in metadata.
                # Update: We only put names in metadata in my previous step.
                pass 

            # 2. Execute Search with pagination
            # K=PAGE_SIZE to retrieve one page at a time
            results, total_hits = await VectorService.search(query, k=PAGE_SIZE, filter=filters, offset=current_offset)
            
            if not results:
                return {
                    "sql_result": [], # Using same key to keep ReplyNode compatible
                    "sql_error": None,
                    "provider_used": "elasticsearch",
                    "last_query": query,
                    "pagination_offset": 0,
                    "has_more_results": False
                }

            # 3. Format Results for Reply Node
            # We map ES results to the list-of-dicts format ReplyNode expects
            mapped_results = []
            for hit in results:
                meta = hit.get("metadata", {})
                # Flatten metadata + content
                item = {
                    "id": meta.get("task_id") or meta.get("facility_id") or meta.get("user_id"),
                    "content": hit.get("text"), # The full text description
                    "status": meta.get("status"), # Int status
                    "score": hit.get("score")
                }
                # Add all metadata fields for flexibility
                item.update(meta)
                mapped_results.append(item)
            
            # 4. Calculate pagination state
            new_offset = current_offset + PAGE_SIZE
            has_more = total_hits > new_offset
            
            logger.info(f"Vector Search found {len(mapped_results)} items (total: {total_hits}, has_more: {has_more}).")

            return {
                "sql_result": mapped_results,
                "sql_error": None,
                "provider_used": "elasticsearch",
                "last_query": query,
                "pagination_offset": new_offset,
                "has_more_results": has_more
            }
            
        except Exception as e:
            logger.error(f"Vector search node failed: {e}", exc_info=True)
            return {
                "sql_error": f"Search failed: {str(e)}",
                "sql_result": None,
                "has_more_results": False
            }
