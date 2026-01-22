
import asyncio
import logging
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

    # 2. Fetch all Task IDs
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id FROM task_transaction"))
        task_ids = [row["id"] for row in result.mappings().all()]
    
    print(f"Found {len(task_ids)} tasks to sync.")
    
    # 3. Sync Each Task
    success_count = 0
    error_count = 0
    
    for i, tid in enumerate(task_ids):
        try:
            print(f"Syncing Task {i+1}/{len(task_ids)}: ID {tid}...", end="\r")
            await SyncService.sync_task_to_es(tid)
            success_count += 1
        except Exception as e:
            logger.error(f"\nFailed to sync Task ID {tid}: {e}")
            error_count += 1
    
    print(f"\n--- Task Sync Complete: {success_count} succeeded, {error_count} failed ---")
    
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
