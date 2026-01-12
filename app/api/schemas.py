
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any, Literal

class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: Optional[str] = None
    user_role: Optional[str] = "user" # default to user if not specified
    mode: Literal["chat", "sql", "workflow"] = "chat"
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

class WorkflowView(BaseModel):
    type: Literal["menu", "input", "confirmation", "end"]
    payload: Dict[str, Any]

class WorkflowResponse(BaseModel):
    active: bool
    name: Optional[str] = None
    step: Optional[str] = None
    view: Optional[WorkflowView] = None

class SQLResponse(BaseModel):
    ran: bool
    cached: bool
    query: Optional[str]
    row_count: Optional[int]
    rows_preview: Optional[List[Dict[str, Any]]]

class ToonMetrics(BaseModel):
    raw_tokens: int
    toon_tokens: int
    reduction_pct: float

class ChatResponse(BaseModel):
    session_id: str
    message: str
    status: Literal["ok", "needs_filters", "workflow_active", "cancelled", "error"]
    labels: List[str] = []
    workflow: Optional[WorkflowResponse] = None
    sql: Optional[SQLResponse] = None
    toon: Optional[ToonMetrics] = None
    provider_used: str
    trace_id: str
