
from fastapi import FastAPI, HTTPException, Request, Depends
from typing import Annotated
from fastapi.middleware.cors import CORSMiddleware
from app.core.settings import settings
from app.core.logging import setup_logging
from app.api.schemas import ChatRequest, ChatResponse, WorkflowResponse, SQLResponse, ToonMetrics
from app.graph.main import app_graph
from app.toon.codec import toon_codec
from app.vector.store import vector_store
from langchain_core.messages import HumanMessage
import uuid
import logging
import time
import json
from fastapi.responses import StreamingResponse
from app.core.observability import TraceManager
from app.core.guardrails import Guardrails, SafetyViolation

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

app = FastAPI(title="Facility Ops Assistant", version="1.0.0")

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
    # Placeholder for SQL Cache metrics
    return {"hits": 10, "misses": 2, "avg_latency_ms": 120}

@app.post("/vector/demo")
async def vector_demo(
    current_user: Annotated[User, Depends(get_current_user)],
    text: str = "This is a test document", 
    query: str = "test"
):
# ... (vector demo continued)
    """
    Demo endpoint to verify ChromaDB integration.
    """
    try:
        doc_id = str(uuid.uuid4())
        # Use user_id in metadata
        vector_store.add_texts(
            texts=[text], 
            metadatas=[{"source": "demo", "user_id": str(current_user.id)}], 
            ids=[doc_id]
        )
        results = vector_store.search(query=query, k=2)
        return {
            "status": "success", 
            "added_id": doc_id, 
            "search_results": results,
            "total_docs": vector_store.count()
        }
    except Exception as e:
        logger.error(f"Vector demo error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_endpoint(
    chat_request: ChatRequest, 
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)]
):
    print(f"DEBUG: Received chat request: {chat_request} from user {current_user.email}")
    
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
        # 1. Load Chat History (Hybrid: Recent + Relevant)
        history_messages = []
        
        # A. Short-Term Memory: Fetch last 4 messages from SQL (Try/Except for Stateless)
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ChatHistory).where(ChatHistory.session_id == chat_request.session_id).order_by(ChatHistory.created_at.desc()).limit(4)
                result = await session.execute(stmt)
                recent_records = result.scalars().all()
                recent_records.reverse() # Chronological
        except Exception as e:
            logger.warning(f"DB History load failed (stateless mode): {e}")
            recent_records = []
            
        # B. Long-Term Memory: Fetch relevant past messages via Vector Search
        relevant_docs = []
        try:
            search_results = vector_store.search(
                query=chat_request.message, 
                k=3, 
                filter={"session_id": chat_request.session_id}
            )
            for res in search_results:
                relevant_docs.append(res)
        except Exception as e:
            logger.warning(f"Vector search failed (ignoring): {e}")

        # C. Combine & Deduplicate
        seen_contents = set()
        final_history_objects = []

        # Add Relevant first (History)
        for doc in relevant_docs:
            content = doc["text"]
            role = doc["metadata"].get("role", "user")
            if content not in seen_contents:
                seen_contents.add(content)
                if role == "user":
                    final_history_objects.append(HumanMessage(content=content))
                else:
                    final_history_objects.append(AIMessage(content=content))

        # Add Recent (Immediate Context)
        for record in recent_records:
            if record.content not in seen_contents:
                seen_contents.add(record.content)
                if record.role == "user":
                    final_history_objects.append(HumanMessage(content=record.content))
                elif record.role == "assistant":
                    final_history_objects.append(AIMessage(content=record.content))
        
        history_messages = final_history_objects

        # Add current user message
        current_user_msg = HumanMessage(content=chat_request.message)
        history_messages.append(current_user_msg)

        # 0. Lookup User's Company & Name
        user_company_id = None
        user_name = None
        user_company_name = None
        if chat_request.user_id:
            async with AsyncSessionLocal() as session:
                try:
                    uid = int(chat_request.user_id) 
                    query = text(f"""
                        SELECT u.first_name, u.company_id, c.name as company_name 
                        FROM `user` u 
                        LEFT JOIN company c ON u.company_id = c.id 
                        WHERE u.id = {uid}
                    """)
                    result = await session.execute(query)
                    row = result.mappings().first()
                    if row:
                        user_company_id = str(row["company_id"])
                        user_name = row["first_name"]
                        user_company_name = row["company_name"]
                except ValueError:
                    pass 
        
        # 1.5 Load Workflow State
        workflow_from_db = {}
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(WorkflowState).where(WorkflowState.session_id == chat_request.session_id)
                result = await session.execute(stmt)
                wf_state_record = result.scalars().first()
                if wf_state_record and wf_state_record.active:
                    workflow_from_db = {
                        "workflow_name": wf_state_record.workflow_name,
                        "workflow_step": wf_state_record.current_step,
                        "workflow_context": wf_state_record.state_data or {}
                    }
        except Exception as e:
            logger.warning(f"Workflow state load failed: {e}")

        # Prepare Graph Input
        initial_state = {
            "messages": history_messages,
            "session_id": chat_request.session_id,
            "user_id": chat_request.user_id,
            "user_role": chat_request.user_role,
            "user_name": user_name,
            "company_id": user_company_id,
            "company_name": user_company_name,
            "trace_id": request.state.trace_id,
            **workflow_from_db 
        }

        # STREAMING SETUP
        from app.core.streaming import StreamQueueHandler
        import asyncio
        
        queue = asyncio.Queue()
        handler = StreamQueueHandler(queue)
        config = {"callbacks": [handler]}
        
        async def run_graph():
            try:
                final_state = await app_graph.ainvoke(initial_state, config=config)
                return final_state
            except Exception as e:
                logger.error(f"Graph execution error: {e}", exc_info=True)
                await queue.put(f"[ERROR: {str(e)}]")
                return None
            finally:
                await queue.put(None) # Sentinel

        task = asyncio.create_task(run_graph())

        async def stream_generator():
            full_response_text = ""
            
            # 1. Stream Tokens
            while True:
                token = await queue.get()
                if token is None:
                    break
                full_response_text += token
                # Yield token event
                yield json.dumps({"type": "token", "content": token}) + "\n"
            
            # 2. Wait for Final State
            final_state = await task
            if not final_state:
                # Error happened
                yield json.dumps({"type": "error", "message": "Processing failed"}) + "\n"
                return

            # 3. Post-Processing & DB Save
            try:
                async with AsyncSessionLocal() as session:
                    # Save User Message
                    user_msg_db = ChatHistory(
                        session_id=chat_request.session_id,
                        role="user",
                        user_id=chat_request.user_id,
                        user_role=chat_request.user_role,
                        content=chat_request.message,
                        trace_id=request.state.trace_id
                    )
                    session.add(user_msg_db)
                    
                    # Save AI Response (Aggregated)
                    # Fallback if streaming was empty but final_response is set (e.g. non-streaming node)
                    if not full_response_text and final_state.get("final_response"):
                        full_response_text = final_state.get("final_response")
                        # Yield it as one chunk if missed
                        yield json.dumps({"type": "token", "content": full_response_text}) + "\n"

                    ai_msg_db = ChatHistory(
                        session_id=chat_request.session_id,
                        role="assistant",
                        user_id=chat_request.user_id,
                        user_role=chat_request.user_role, 
                        content=full_response_text,
                        trace_id=request.state.trace_id
                    )
                    session.add(ai_msg_db)
                    
                    # Save/Update Workflow State
                    if final_state.get("workflow_name"):
                         stmt = select(WorkflowState).where(WorkflowState.session_id == chat_request.session_id)
                         result = await session.execute(stmt)
                         wf_record = result.scalars().first()
                         
                         is_active = final_state.get("workflow_step") != "end"
                         
                         if wf_record:
                             wf_record.workflow_name = final_state.get("workflow_name")
                             wf_record.current_step = final_state.get("workflow_step")
                             wf_record.state_data = final_state.get("workflow_context")
                             wf_record.active = is_active
                         else:
                             wf_record = WorkflowState(
                                 session_id=chat_request.session_id,
                                 workflow_name=final_state.get("workflow_name"),
                                 current_step=final_state.get("workflow_step"),
                                 state_data=final_state.get("workflow_context"),
                                 active=is_active
                             )
                             session.add(wf_record)

                    await session.commit()
            except Exception as e:
                logger.error(f"DB Save failed (stateless mode): {e}")
                
                # Save to Vector Store
                try:
                    vector_store.add_texts(
                        texts=[chat_request.message, full_response_text],
                        metadatas=[
                            {"role": "user", "session_id": chat_request.session_id, "timestamp": str(time.time()), "user_id": str(chat_request.user_id)},
                            {"role": "assistant", "session_id": chat_request.session_id, "timestamp": str(time.time()), "user_id": str(chat_request.user_id)}
                        ]
                    )
                except Exception as ve:
                    logger.error(f"Failed to save to vector store: {ve}")
            
            # 4. Yield Structured Data (Workflow, SQL, etc.)
            wf_resp = None
            if final_state.get("workflow_name"):
                wf_data = final_state.get("workflow_data", {})
                wf_resp = {
                    "active": final_state.get("workflow_step") != "end",
                    "name": final_state.get("workflow_name"),
                    "step": final_state.get("workflow_step"),
                    "view": wf_data
                }

            sql_resp = None
            if final_state.get("sql_query"):
                res = final_state.get("sql_result")
                sql_resp = {
                    "ran": res is not None,
                    "cached": False, 
                    "query": final_state.get("sql_query"),
                    "row_count": len(res) if res else 0,
                    "rows_preview": res if res else [] 
                }

            toon_metrics = None
            if sql_resp and sql_resp["rows_preview"]:
                toon_encoded = toon_codec.encode(sql_resp["rows_preview"])
                toon_metrics = toon_encoded["toon_meta"]
            else:
                toon_metrics = {"raw_tokens": 0, "toon_tokens": 0, "reduction_pct": 0.0}

            final_data = {
                "type": "result",
                "session_id": chat_request.session_id,
                "status": "ok",
                "labels": [final_state.get("intent") or "unknown"],
                "workflow": wf_resp,
                "sql": sql_resp,
                "toon": toon_metrics,
                "provider_used": final_state.get("provider_used") or "unknown",
                "trace_id": request.state.trace_id
            }
            yield json.dumps(final_data) + "\n"

        return StreamingResponse(stream_generator(), media_type="application/x-ndjson")

    except Exception as e:
        print(f"DEBUG: Chat endpoint exception: {e}")
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
