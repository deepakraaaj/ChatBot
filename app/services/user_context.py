
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
import logging

logger = logging.getLogger(__name__)

class UserContextService:
    @staticmethod
    async def get_user_context(user_id: int) -> dict:
        """
        Fetches enriched user context including company name.
        Returns dict: {user_name, company_id, company_name}
        """
        ctx = {
            "user_name": None,
            "company_id": None,
            "company_name": None
        }
        
        try:
            async with AsyncSessionLocal() as session:
                query = text(f"""
                    SELECT u.first_name, u.company_id, c.name as company_name 
                    FROM `user` u 
                    LEFT JOIN company c ON u.company_id = c.id 
                    WHERE u.id = {user_id}
                """)
                result = await session.execute(query)
                row = result.mappings().first()
                if row:
                    ctx["user_name"] = row["first_name"]
                    ctx["company_id"] = str(row["company_id"]) if row["company_id"] else None
                    ctx["company_name"] = row["company_name"]
        except Exception as e:
            logger.error(f"Failed to fetch user context for {user_id}: {e}")
            
        return ctx
