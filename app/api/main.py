
from fastapi import FastAPI, HTTPException, Request, Depends
from typing import Annotated
from fastapi.middleware.cors import CORSMiddleware
from app.core.settings import settings
from app.core.logging import setup_logging
from app.api.schemas import ChatRequest, ChatResponse, WorkflowResponse, SQLResponse, ToonMetrics
from app.graph.main import app_graph
from app.core.codec import toon_codec
from langchain_core.messages import HumanMessage
import uuid
import logging
import time
import json
from fastapi.responses import StreamingResponse
from app.core.observability import TraceManager
from app.core.guardrails import Guardrails, SafetyViolation
from app.core.es import ElasticsearchClient
from app.core.cache import CacheClient
from app.services.history import HistoryService
from app.services.vector import VectorService
from app.services.user_context import UserContextService
from app.services.workflow_state import WorkflowStateService
from app.services.metrics import MetricsService
from contextlib import asynccontextmanager

# Setup
setup_logging()
logger = logging.getLogger(__name__)

from app.db.session import AsyncSessionLocal, get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import ChatHistory, WorkflowState, User
from sqlalchemy import select, text
from langchain_core.messages import HumanMessage, AIMessage
from app.core.security import create_access_token, verify_password
from app.api.deps import get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure ES index exists
    try:
        await ElasticsearchClient.create_index("chat_history", mapping={
            "mappings": {
                "properties": {
                    "session_id": {"type": "keyword"},
                    "role": {"type": "keyword"},
                    "content": {"type": "text"},
                    "user_id": {"type": "keyword"},
                    "timestamp": {"type": "date"}
                }
            }
        })
        # Ensure Vector Index
        await VectorService.ensure_index()
        
        # Trigger Redis init
        CacheClient.get_client()
    except Exception as e:
        logger.error(f"Startup error: {e}")
    
    yield
    
    # Shutdown
    await ElasticsearchClient.close()
    await CacheClient.close()

app = FastAPI(title="Facility Ops Assistant", version="1.0.0", lifespan=lifespan)

# Security & CORS
# In production, this should be set to specific origins via settings.
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8000",
]
if settings.env != "development":
    # If strictly needed, we can pull from env var, but for now defaults valid for dev
    pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Keeping * for dev simplicity per user request but marked for change if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware for Trace ID
@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
    TraceManager.set_trace_id(trace_id)
    request.state.trace_id = trace_id
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    response.headers["X-Trace-Id"] = trace_id
    TraceManager.info(f"Request: {request.method} {request.url.path}", status=response.status_code, duration_ms=duration*1000)
    return response

# Routes
@app.post("/login")
async def login_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    stmt = select(User).where(User.email == form_data.username)
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.auth.access_token_expire_minutes)
    access_token = create_access_token(
        subject=user.email, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/session/start")
async def start_session(
    current_user: Annotated[User, Depends(get_current_user)]
):
    return {"session_id": str(uuid.uuid4()), "message": "Session started", "user": current_user.email}

@app.post("/session/end")
async def end_session(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    # In real app, clear state from DB
    return {"status": "ok", "message": "Session ended"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "env": settings.env}

@app.get("/metrics/sql")
async def sql_metrics(current_user: Annotated[User, Depends(get_current_user)]):
    try:
        # Example Redis check
        info = await CacheClient.get_client().info()
        return {
            "status": "connected", 
            "redis_version": info.get("redis_version"), 
            "used_memory_human": info.get("used_memory_human")
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/metrics/analytics")
async def get_analytics(hours: float = 1.0):
    """
    Expose aggregated metric data for the Streamlit dashboard.
    """
    try:
        data = await MetricsService.get_aggregates(hours_back=hours)
        return {"status": "ok", "data": data}
    except Exception as e:
        logger.error(f"Analytics fetch error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")

# Vector demo endpoint removed

@app.post("/chat")
async def chat_endpoint(
    chat_request: ChatRequest, 
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)]
):
    logger.info(f"Received chat request from user {current_user.email} (session: {chat_request.session_id})")
    
    # 1. Guardrails Input Check
    is_safe, violation = Guardrails.validate_input(chat_request.message)
    if not is_safe:
        TraceManager.error(f"Guardrail violation: {violation}", user_id=str(current_user.id))
        return ChatResponse(
            session_id=chat_request.session_id,
            message=f"I cannot process that request. {violation}",
            status="error",
            provider_used="guardrail",
            trace_id=request.state.trace_id
        )

    # OVERRIDE user_id from token, do not trust body
    chat_request.user_id = str(current_user.id)
    
    try:
        # 1. Load Chat History via Service
        history_messages = await HistoryService.get_history(chat_request.session_id, chat_request.message)

        # Add current user message
        current_user_msg = HumanMessage(content=chat_request.message)
        history_messages.append(current_user_msg)

        # 1.5 Load User Context & Workflow State (Parallelizable in future, mostly async db calls)
        user_ctx = {}
        if chat_request.user_id:
             user_ctx = await UserContextService.get_user_context(int(chat_request.user_id))
        
        workflow_from_db = await WorkflowStateService.load_state(chat_request.session_id)

        # Prepare Graph Input
        initial_state = {
            "messages": history_messages,
            "session_id": chat_request.session_id,
            "user_id": chat_request.user_id,
            "user_role": chat_request.user_role,
            "user_role": chat_request.user_role,
            "user_name": user_ctx.get("user_name"),
            "company_id": user_ctx.get("company_id"),
            "company_name": user_ctx.get("company_name"),
            "trace_id": request.state.trace_id,
            **workflow_from_db 
        }

        # STREAMING MANAGER
        from app.core.streaming import ChatStreamManager
        import asyncio
        
        queue = asyncio.Queue()
        
        request_info = {
            "session_id": chat_request.session_id,
            "user_id": chat_request.user_id,
            "user_role": chat_request.user_role,
            "message": chat_request.message,
            "trace_id": request.state.trace_id
        }
        
        manager = ChatStreamManager(
            app_graph=app_graph,
            initial_state=initial_state,
            queue=queue,
            request_info=request_info
        )

        return StreamingResponse(manager.generator(), media_type="application/x-ndjson")
        

    except Exception as e:
        logger.error(f"Chat endpoint exception: {e}")
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        # Fallback error response (can't stream if we haven't started, or if exception happens early)
        return ChatResponse(
            session_id=chat_request.session_id,
            message="An internal error occurred.",
            status="error",
            provider_used="system",
            trace_id=request.state.trace_id
        )

@app.post("/groq/chat")
async def groq_chat_direct():
    # Placeholder for specific provider endpoint if needed by ops
    return {"message": "Direct Groq access not fully implemented in demo, uses main /chat"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
