import logging
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.services.vector import VectorService

logger = logging.getLogger(__name__)

class SyncService:
    @staticmethod
    async def sync_task_to_es(task_id: int):
        """
        Fetches a single task by ID (with joined details) and syncs it to Elasticsearch.
        IDEMPOTENT: Can be called on Create or Update.
        """
        logger.info(f"Syncing Task ID {task_id} to Elasticsearch...")
        
        async with AsyncSessionLocal() as session:
            try:
                # 1. Fetch Task Details (Join ALL relevant tables)
                # We need: Task Name, Facility Name, Assignee Name, Priority, Status, Date
                query = text("""
                    SELECT 
                        t.id, 
                        t.status, 
                        t.priority, 
                        t.remarks, 
                        t.scheduled_date,
                        t.date_created,
                        td.name as task_name,
                        f.name as facility_name,
                        u.first_name as assignee_first,
                        u.last_name as assignee_last,
                        t.company_id
                    FROM task_transaction t
                    LEFT JOIN task_description td ON t.task_id = td.id
                    LEFT JOIN facility f ON t.facility_id = f.id
                    LEFT JOIN user u ON t.assigned_user_id = u.id
                    WHERE t.id = :tid
                """)
                
                result = await session.execute(query, {"tid": task_id})
                row = result.mappings().first()
                
                if not row:
                    logger.warning(f"Sync failed: Task ID {task_id} not found in DB.")
                    return

                # 2. Construct Rich Text for Vector Embedding
                # "Task: Fix AC. Facility: Main Building. Assigned to: John Doe. Status: Pending. Remarks: high priority"
                assignee_name = f"{row['assignee_first'] or ''} {row['assignee_last'] or ''}".strip() or "Unassigned"
                
                status_map = {0: "Pending", 1: "In Progress", 2: "Completed", 3: "Overdue"}
                status_str = status_map.get(row['status'], "Unknown")
                
                content_text = (
                    f"Task: {row['task_name'] or 'General Task'}. "
                    f"Facility: {row['facility_name'] or 'Unknown Facility'}. "
                    f"Assigned to: {assignee_name}. "
                    f"Status: {status_str}. "
                    f"Remarks: {row['remarks'] or ''}. "
                    f"Priority: {row['priority']}."
                )

                # 3. Construct Metadata (for filtering)
                metadata = {
                    "task_id": row['id'],
                    "company_id": int(row['company_id']) if row['company_id'] else 0,
                    "status": row['status'],
                    "assignee_name": assignee_name,
                    "facility_name": row['facility_name'],
                    "facility_name": row['facility_name'],
                    "scheduled_date": str(row['scheduled_date']) if row['scheduled_date'] else None,
                    "doc_type": "task"
                }
                
                # 4. Push to Vector Service (Explicit ID Update)
                await VectorService.add_texts(
                    texts=[content_text],
                    metadatas=[metadata],
                    ids=[str(task_id)]
                )
                
                logger.info(f"Successfully synced Task {task_id} to Vector Index.")

            except Exception as e:
                logger.error(f"Error syncing Task {task_id}: {e}", exc_info=True)

    @staticmethod
    async def sync_facility_to_es(facility_id: int):
        """
        Fetches a single facility by ID and syncs it to Elasticsearch.
        IDEMPOTENT: Can be called on Create or Update.
        """
        logger.info(f"Syncing Facility ID {facility_id} to Elasticsearch...")
        
        async with AsyncSessionLocal() as session:
            try:
                # 1. Fetch Facility Details
                query = text("""
                    SELECT 
                        f.id,
                        f.name,
                        f.code,
                        f.company_id,
                        f.is_active,
                        ft.type_name as facility_type,
                        ll.location_name as location
                    FROM facility f
                    LEFT JOIN facility_types ft ON f.facility_types_id = ft.id
                    LEFT JOIN location_levels ll ON f.location_levels_id = ll.id
                    WHERE f.id = :fid
                """)
                
                result = await session.execute(query, {"fid": facility_id})
                row = result.mappings().first()
                
                if not row:
                    logger.warning(f"Sync failed: Facility ID {facility_id} not found in DB.")
                    return

                # 2. Construct Rich Text for Vector Embedding
                content_text = (
                    f"Facility: {row['name'] or 'Unknown Facility'}. "
                    f"Code: {row['code'] or 'N/A'}. "
                    f"Type: {row['facility_type'] or 'Unknown Type'}. "
                    f"Location: {row['location'] or 'Unknown Location'}. "
                    f"Status: {'Active' if row['is_active'] else 'Inactive'}."
                )

                # 3. Construct Metadata (for filtering)
                metadata = {
                    "facility_id": row['id'],
                    "company_id": int(row['company_id']) if row['company_id'] else 0,
                    "facility_name": row['name'],
                    "facility_type": row['facility_type'],
                    "facility_type": row['facility_type'],
                    "location": row['location'],
                    "is_active": bool(row['is_active']),
                    "doc_type": "facility"
                }
                
                # 4. Push to Vector Service (Explicit ID Update)
                await VectorService.add_texts(
                    texts=[content_text],
                    metadatas=[metadata],
                    ids=[f"facility_{facility_id}"]
                )
                
                logger.info(f"Successfully synced Facility {facility_id} to Vector Index.")

            except Exception as e:
                logger.error(f"Error syncing Facility {facility_id}: {e}", exc_info=True)

    @staticmethod
    async def sync_tasks_batched(batch_size: int = 50):
        """
        Syncs ALL tasks in batches to optimize network/embedding overhead.
        """
        logger.info("Starting Batched Task Sync...")
        
        async with AsyncSessionLocal() as session:
            try:
                # 1. Fetch joined data for ALL tasks
                query = text("""
                    SELECT 
                        t.id, 
                        t.status, 
                        t.priority, 
                        t.remarks, 
                        t.scheduled_date,
                        t.date_created,
                        td.name as task_name,
                        f.name as facility_name,
                        u.first_name as assignee_first,
                        u.last_name as assignee_last,
                        t.company_id
                    FROM task_transaction t
                    LEFT JOIN task_description td ON t.task_id = td.id
                    LEFT JOIN facility f ON t.facility_id = f.id
                    LEFT JOIN user u ON t.assigned_user_id = u.id
                """)
                
                result = await session.execute(query)
                rows = result.mappings().all()
                total = len(rows)
                logger.info(f"Fetched {total} tasks for batch sync.")
                
                batch_texts = []
                batch_metas = []
                batch_ids = []
                
                for i, row in enumerate(rows):
                    # Construct Text
                    assignee_name = f"{row['assignee_first'] or ''} {row['assignee_last'] or ''}".strip() or "Unassigned"
                    status_map = {0: "Pending", 1: "In Progress", 2: "Completed", 3: "Overdue"}
                    status_str = status_map.get(row['status'], "Unknown")
                    
                    content_text = (
                        f"Task: {row['task_name'] or 'General Task'}. "
                        f"Facility: {row['facility_name'] or 'Unknown Facility'}. "
                        f"Assigned to: {assignee_name}. "
                        f"Status: {status_str}. "
                        f"Remarks: {row['remarks'] or ''}. "
                        f"Priority: {row['priority']}."
                    )
                    
                    # Construct Metadata
                    metadata = {
                        "task_id": row['id'],
                        "company_id": int(row['company_id']) if row['company_id'] else 0,
                        "status": row['status'],
                        "assignee_name": assignee_name,
                        "facility_name": row['facility_name'],
                        "scheduled_date": str(row['scheduled_date']) if row['scheduled_date'] else None,
                        "doc_type": "task"
                    }
                    
                    batch_texts.append(content_text)
                    batch_metas.append(metadata)
                    batch_ids.append(str(row['id']))
                    
                    # Flush Batch
                    if len(batch_texts) >= batch_size:
                        logger.info(f"Flushing batch {len(batch_texts)} items (Progress: {i+1}/{total})...")
                        await VectorService.add_texts(batch_texts, batch_metas, ids=batch_ids)
                        batch_texts = []
                        batch_metas = []
                        batch_ids = []
                
                # Flush Remaining
                if batch_texts:
                    logger.info(f"Flushing final batch {len(batch_texts)} items...")
                    await VectorService.add_texts(batch_texts, batch_metas, ids=batch_ids)
                    
                logger.info("Batched Task Sync Complete.")
                
            except Exception as e:
                logger.error(f"Batched Sync Failed: {e}", exc_info=True)
