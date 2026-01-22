
import asyncio
import logging
import os
# Force offline usage for HuggingFace (use cached models)
os.environ["TRANSFORMERS_OFFLINE"] = "1"
# Also suppress symlink warnings
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.sync import SyncService
from app.services.vector import VectorService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def bulk_sync():
    print("--- Starting Bulk Sync (DB -> Elasticsearch) ---")
    
    # 1. Ensure Index Exists
    await VectorService.ensure_index()
    print("Index ensured.")

    # 2. Sync Tasks (Batched)
    print("Syncing Tasks (Batched Mode)...")
    await SyncService.sync_tasks_batched(batch_size=50)
    print("Task Sync Complete.")
    
    # 4. Fetch all Facility IDs
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id FROM facility"))
        facility_ids = [row["id"] for row in result.mappings().all()]
    
    print(f"\nFound {len(facility_ids)} facilities to sync.")
    
    # 5. Sync Each Facility
    facility_success = 0
    facility_error = 0
    
    for i, fid in enumerate(facility_ids):
        try:
            print(f"Syncing Facility {i+1}/{len(facility_ids)}: ID {fid}...", end="\r")
            await SyncService.sync_facility_to_es(fid)
            facility_success += 1
        except Exception as e:
            logger.error(f"\nFailed to sync Facility ID {fid}: {e}")
            facility_error += 1
            
    print(f"\n--- Facility Sync Complete: {facility_success} succeeded, {facility_error} failed ---")
    print(f"\n=== TOTAL: {success_count + facility_success} documents indexed ===")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(bulk_sync())
