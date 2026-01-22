
from typing import TypedDict, List, Optional, Any, Dict, Annotated
from langchain_core.messages import BaseMessage
import operator

def merge_dicts(a: Dict, b: Dict) -> Dict:
    return {**a, **b}

class GraphState(TypedDict):
    """
    Represents the state of the conversation graph.
    """
    messages: Annotated[List[BaseMessage], operator.add]
    session_id: str
    
    # Classification results
    intent: Optional[str] # chat, sql, workflow
    parameters: Optional[Dict[str, Any]]
    
    # SQL specific
    sql_query: Optional[str]
    sql_result: Optional[List[Dict[str, Any]]]
    sql_error: Optional[str]

    # Workflow specific
    workflow_name: Optional[str]
    workflow_step: Optional[str]
    workflow_data: Optional[Dict[str, Any]]
    workflow_context: Optional[Dict[str, Any]] # Stores intermediate selections (facility_id, etc.)
    
    # Response generation
    final_response: Optional[str]
    
    # Metadata and Debugging
    provider_used: Optional[str]
    user_id: Optional[str]
    user_name: Optional[str]
    user_role: Optional[str]
    company_id: Optional[str]
    company_name: Optional[str]
    trace_id: Optional[str]
    error: Optional[str]
    
    # Pagination for Vector Search
    last_query: Optional[str]  # Track the last search query for pagination
    pagination_offset: Optional[int]  # Current offset for pagination (default 0)
    has_more_results: Optional[bool]  # Flag indicating if more results exist


