
import asyncio
import json
import logging
import time
from uuid import UUID
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.services.history import HistoryService
from app.services.workflow_state import WorkflowStateService
from app.services.metrics import MetricsService
from app.core.codec import toon_codec

logger = logging.getLogger(__name__)

class StreamQueueHandler(AsyncCallbackHandler):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self.streaming_run_id = None

    async def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        pass

    async def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Optional[Any] = None,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        await self.queue.put(token)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        pass
        
    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        await self.queue.put(f"[ERROR: {error}]")


class ChatStreamManager:
    """
    Manages the lifecycle of a streaming chat request:
    1. Runs the LangGraph in a background task.
    2. Consumes tokens from the queue.
    3. Post-processes the final state (Save History, Save Workflow).
    4. Formats the final JSON response (including ToonCodec).
    """

    def __init__(self, app_graph, initial_state: Dict, queue: asyncio.Queue, request_info: Dict):
        self.app_graph = app_graph
        self.initial_state = initial_state
        self.queue = queue
        self.req = request_info 
        # req expected keys: session_id, user_id, user_role, message, trace_id
        
        # Determine config for callbacks
        self.handler = StreamQueueHandler(queue)
        self.config = {"callbacks": [self.handler]}

    async def generator(self):
        # 0. Start Timer
        start_time = time.time()
        
        # 1. Start Graph in Background
        task = asyncio.create_task(self._run_graph())
        
        full_response_text = ""
        
        # 2. Stream Tokens
        while True:
            token = await self.queue.get()
            if token is None:
                break
            full_response_text += token
            # Yield token event
            yield json.dumps({"type": "token", "content": token}) + "\n"
        
        # 3. Wait for Final State
        final_state = await task
        if not final_state:
            yield json.dumps({"type": "error", "message": "Processing failed"}) + "\n"
            return
            
        # 4. Post-Processing
        
        # Fallback if streaming was empty (non-streaming nodes)
        if not full_response_text and final_state.get("final_response"):
            full_response_text = final_state.get("final_response")
            yield json.dumps({"type": "token", "content": full_response_text}) + "\n"
        
        # Async Save History
        asyncio.create_task(HistoryService.save_interaction(
            session_id=self.req["session_id"],
            user_id=str(self.req["user_id"]),
            user_role=self.req["user_role"],
            user_msg=self.req["message"],
            ai_msg=full_response_text,
            trace_id=str(self.req["trace_id"])
        ))
        
        # Async Save Workflow State
        await WorkflowStateService.save_state(self.req["session_id"], final_state)
        
        # 4.5 Record Metrics
        latency_ms = (time.time() - start_time) * 1000
        feature = final_state.get("intent") or "chat"
        
        # Tokens
        # prompt_size can be estimated from context? Or from history. 
        # For simplicity, we use text length as a proxy for tokens (approx 4 chars / token)
        # But ToonCodec gives us "raw_tokens" which is basically string length.
        # We'll use string length for consistency with ToonCodec stats.
        tokens_in = len(self.req["message"])
        tokens_out = len(full_response_text)
        
        asyncio.create_task(MetricsService.record_usage(
            session_id=self.req["session_id"],
            user_id=str(self.req["user_id"]),
            user_role=self.req["user_role"],
            feature=feature,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms
        ))

        # 5. Format Final Data
        final_data = self._format_final_response(final_state)
        yield json.dumps(final_data) + "\n"

    async def _run_graph(self):
        try:
            final_state = await self.app_graph.ainvoke(self.initial_state, config=self.config)
            return final_state
        except Exception as e:
            logger.error(f"Graph execution error: {e}", exc_info=True)
            await self.queue.put(f"[ERROR: {str(e)}]")
            return None
        finally:
            await self.queue.put(None) # Sentinel

    def _format_final_response(self, final_state: Dict) -> Dict:
        # Workflow Response
        wf_resp = None
        if final_state.get("workflow_name"):
            wf_data = final_state.get("workflow_data", {})
            wf_resp = {
                "active": final_state.get("workflow_step") != "end",
                "name": final_state.get("workflow_name"),
                "step": final_state.get("workflow_step"),
                "view": wf_data
            }

        # SQL Response
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

        # Toon Metrics
        toon_metrics = None
        if sql_resp and sql_resp["rows_preview"]:
            toon_encoded = toon_codec.encode(sql_resp["rows_preview"])
            toon_metrics = toon_encoded["toon_meta"]
        else:
            toon_metrics = {"raw_tokens": 0, "toon_tokens": 0, "reduction_pct": 0.0}

        return {
            "type": "result",
            "session_id": self.req["session_id"],
            "status": "ok",
            "labels": [final_state.get("intent") or "unknown"],
            "workflow": wf_resp,
            "sql": sql_resp,
            "toon": toon_metrics,
            "provider_used": final_state.get("provider_used") or "unknown",
            "trace_id": self.req["trace_id"]
        }
