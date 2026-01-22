
import asyncio
import logging
from app.services.vector import VectorService
from app.core.es import ElasticsearchClient

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_hybrid_search():
    print("--- Testing Hybrid Metadata Filtering ---")
    
    # 1. Test Case: Active Facilities
    print("\n1. Query: 'active facilities' (Filter: is_active=True)")
    # We simulate what Understanding Node would pass
    filters = {"is_active": True} 
    results, total = await VectorService.search("facility", k=5, filter=filters)
    
    print(f"Found {len(results)} results.")
    for res in results:
        meta = res['metadata']
        status = "Active" if meta.get('is_active') else "Inactive"
        print(f"- {res['text'][:50]}... | Status: {status} | ID: {meta.get('facility_id')}")
        
        if not meta.get('is_active'):
             print("❌ FAILURE: Found inactive facility when filtering for active!")
             
    # 2. Test Case: Completed Tasks
    print("\n2. Query: 'completed tasks' (Filter: status=2)")
    filters = {"status": 2} # 2 = Completed
    results, total = await VectorService.search("task", k=5, filter=filters)
    
    print(f"Found {len(results)} results.")
    for res in results:
        meta = res['metadata']
        print(f"- {res['text'][:50]}... | Status: {meta.get('status')} | ID: {meta.get('task_id')}")
        
        if meta.get('status') != 2:
             print("❌ FAILURE: Found non-completed task!")

    await ElasticsearchClient.close()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_hybrid_search())
