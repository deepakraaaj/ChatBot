
import logging
from sqlalchemy import inspect
from app.db.session import engine
from app.core.cache import CacheClient

logger = logging.getLogger(__name__)

class SchemaService:
    @staticmethod
    async def get_schema() -> str:
        """
        Retrieves database schema.
        1. Checks Redis cache.
        2. If miss, reflects via SQLAlchemy Inspector.
        3. Formats for LLM.
        4. Caches result.
        """
        # 1. Check Cache
        try:
            cached_schema = await CacheClient.get_cache("db_schema_llm")
            if cached_schema:
                return cached_schema
        except Exception as e:
            logger.warning(f"Schema cache read failed: {e}")

        # 2. Reflect DB (Expensive)
        logger.info("Reflecting DB schema (Cache Miss)...")
        schema_text = ""
        try:
            # SQLAlchemy sync inspector needs sync engine, or run_sync
            # Using async engine run_sync
            def inspect_schema(connection):
                inspector = inspect(connection)
                tables = inspector.get_table_names()
                
                output = ["DATABASE SCHEMA:"]
                
                # Priority Tables (Hardcoded ordering for relevance)
                # Sort tables so critical ones are first context
                priority = ["task_transaction", "scheduler", "facility", "user", "asset"]
                tables.sort(key=lambda t: priority.index(t) if t in priority else 999)

                for table_name in tables:
                    columns = inspector.get_columns(table_name)
                    col_strings = [f"{c['name']} ({c['type']})" for c in columns]
                    
                    # Add Foreign Keys hint
                    fks = inspector.get_foreign_keys(table_name)
                    fk_strings = [f"FK -> {fk['referred_table']}.{fk['referred_columns'][0]}" for fk in fks]
                    
                    table_desc = f"Table: {table_name}\nColumns: {', '.join(col_strings)}"
                    if fk_strings:
                        table_desc += f"\nRelations: {', '.join(fk_strings)}"
                    
                    output.append(table_desc)
                    output.append("---")
                
                return "\n".join(output)

            async with engine.connect() as conn:
                schema_text = await conn.run_sync(inspect_schema)

            # 3. Cache Result (TTL 1 hour)
            await CacheClient.set_cache("db_schema_llm", schema_text, expire=3600)
            
        except Exception as e:
            logger.error(f"Schema reflection failed: {e}")
            # Fallback to a minimal or error message? 
            # Better to return empty so LLM knows it has no tools, or raise
            return "Error retrieving schema."

        return schema_text
