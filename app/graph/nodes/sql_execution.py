
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.graph.state import GraphState
import logging
import re

logger = logging.getLogger(__name__)

class SQLExecutionNode:
    async def __call__(self, state: GraphState) -> GraphState:
        query = state.get("sql_query")
        if not query:
            return {"sql_error": "No query generated."}

        # 1. Strict Security Check
        clean_query = query.strip().lower()
        forbidden_keywords = ["insert", "update", "delete", "drop", "alter", "truncate", "grant", "revoke", "into outfile", "sleep", "benchmark"]
        if not clean_query.startswith("select"):
             return {"sql_error": "Security Alert: Only SELECT queries are allowed."}
        
        for word in forbidden_keywords:
            if word in clean_query:
                return {"sql_error": f"Security Alert: Forbidden keyword '{word}' detected."}

        # 2. Limit Enforcement
        if "limit" not in clean_query:
            query += " LIMIT 200"
        
        FACILITY_STATUS_LABELS = {
            0: "Assigned",
            1: "In Progress",
            2: "Overdue",
            3: "Delay In Progress",
            4: "Completed",
        }

        TASK_STATUS_LABELS = {
            0: "Pending",
            1: "In Progress",
            2: "Completed",
            3: "Overdue",
        }

        # 3. Execution
        try:
            async with AsyncSessionLocal() as session:
                # Primary Execution
                result = await session.execute(text(query))
                rows = result.mappings().all()
                
                # [ZERO HALLUCINATION STRATEGY]
                # Auto-Retry with Relaxed Query if 0 results found
                if len(rows) == 0:
                    relaxed_query = self._relax_query(query) # Pass original query (clean_query is lowercased)
                    if relaxed_query and relaxed_query != query:
                        logger.info(f"Zero results found. Retrying with relaxed query: {relaxed_query}")
                        result = await session.execute(text(relaxed_query))
                        rows = result.mappings().all()

                # Convert to list of dicts for JSON serialization
                result_data = [dict(row) for row in rows]
                
                # 4. Status Mapping
                # Determine context from query (heuristic)
                is_task_query = "task_transaction" in clean_query
                is_facility_query = "facility" in clean_query
                
                for row in result_data:
                    for key, val in row.items():
                        # Date Formatting
                        if hasattr(val, 'isoformat'): # simplistic check for date/datetime
                            row[key] = val.strftime("%Y-%m-%d %H:%M") 
                        
                        # Status Mapping
                        if key == "status" and isinstance(val, int):
                            if is_task_query:
                                row[key] = TASK_STATUS_LABELS.get(val, "Unknown")
                            elif is_facility_query:
                                row[key] = FACILITY_STATUS_LABELS.get(val, "Unknown")
                
                return {
                    "sql_result": result_data,
                    "sql_error": None
                }
                
        except Exception as e:
            logger.error(f"SQL Execution failed: {e}")
            return {
                "sql_result": None,
                "sql_error": str(e)
            }

    def _relax_query(self, query: str) -> str:
        """
        Relax strict equality checks to LIKE for Dates and Strings
        to handle format mismatches (Zero Hallucination Policy).
        """
        relaxed = query
        
        # 1. Date Relaxation: = 'YYYY-MM-DD'  ->  LIKE 'YYYY-MM-DD%'
        # This fixes "2025-12-01" failing to match "2025-12-01 10:00:00"
        date_pattern = re.compile(r"=\s*'(\d{4}-\d{2}-\d{2})'")
        relaxed = date_pattern.sub(r"LIKE '\1%'", relaxed)
        
        # 2. String Relaxation: = 'SomeString' -> LIKE '%SomeString%'
        # Only apply if it looks like a name/text (not ID). 
        # Heuristic: Apply to everything strictly quoted that wasn't a date.
        # This is aggressive but safe for SELECT statements in this context.
        # Regex looks for = 'Value' where Value is NOT just digits
        string_pattern = re.compile(r"=\s*'([^']*[a-zA-Z][^']*)'")
        relaxed = string_pattern.sub(r"LIKE '%\1%'", relaxed)

        return relaxed
