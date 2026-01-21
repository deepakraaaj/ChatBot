
import logging
import datetime
from langchain_core.messages import HumanMessage, AIMessage
from sqlalchemy import select
from app.api.schemas import ChatRequest
from app.db.session import AsyncSessionLocal
from app.db.models import ChatHistory
from app.api.schemas import ChatRequest
from app.db.session import AsyncSessionLocal
from app.db.models import ChatHistory
from app.services.vector import VectorService
from app.core.es import ElasticsearchClient

logger = logging.getLogger(__name__)

class HistoryService:
    @staticmethod
    async def get_history(session_id: str, message: str = "") -> list:
        """
        Retrieves chat history using a tiered approach:
        1. Elasticsearch (Fastest, full context)
        2. Vector Store + DB (Fallback)
        """
        history_messages = []
        
        # 1. Try Elasticsearch
        try:
            es_results = await ElasticsearchClient.search("chat_history", query={
                "bool": {
                    "must": [
                        {"term": {"session_id": session_id}}
                    ]
                }
            }, size=10)
            
            if es_results:
                # Sort by timestamp
                es_results.sort(key=lambda x: x['_source'].get('timestamp', 0))
                
                for hit in es_results:
                    data = hit['_source']
                    if data['role'] == 'user':
                        history_messages.append(HumanMessage(content=data['content']))
                    elif data['role'] == 'assistant':
                        history_messages.append(AIMessage(content=data['content']))
                
                return history_messages # Return early if ES succeeds
        except Exception as e:
            logger.warning(f"ES History fetch failed: {e}")

        # 2. Fallback: Vector + DB
        # This logic is legacy but kept for resilience
        relevant_docs = []
        try:
            if message:
                search_results = await VectorService.search(
                    query=message, 
                    k=3, 
                    filter={"session_id": session_id}
                )
                for res in search_results:
                    relevant_docs.append(res)
        except Exception as e:
            logger.warning(f"Vector search failed (ignoring): {e}")

        seen_contents = set()
        for doc in relevant_docs:
            content = doc["text"]
            role = doc["metadata"].get("role", "user")
            if content not in seen_contents:
                seen_contents.add(content)
                history_messages.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))
        
        # Recent DB
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(ChatHistory).where(ChatHistory.session_id == session_id).order_by(ChatHistory.created_at.desc()).limit(4)
                result = await session.execute(stmt)
                recent_records = result.scalars().all()
                recent_records.reverse()
                for record in recent_records:
                    if record.content not in seen_contents:
                        history_messages.append(HumanMessage(content=record.content) if record.role == "user" else AIMessage(content=record.content))
        except Exception as e:
            logger.warning(f"DB fallback failed: {e}")
            
        return history_messages

    @staticmethod
    async def save_interaction(session_id: str, user_id: str, user_role: str, user_msg: str, ai_msg: str, trace_id: str = None):
        """
        Saves the interaction to:
        1. Database (Persistent Record)
        2. Elasticsearch (Searchable History)
        3. Vector Store (Semantic Recall)
        """
        # 1. DB Save
        try:
            async with AsyncSessionLocal() as session:
                # User
                u_db = ChatHistory(
                    session_id=session_id, role="user", user_id=user_id,
                    user_role=user_role, content=user_msg, trace_id=trace_id
                )
                session.add(u_db)
                
                # AI
                a_db = ChatHistory(
                    session_id=session_id, role="assistant", user_id=user_id,
                    user_role=user_role, content=ai_msg, trace_id=trace_id
                )
                session.add(a_db)
                await session.commit()
        except Exception as e:
            logger.error(f"DB Save failed: {e}")

        # 2. Elasticsearch Indexing
        try:
            now_ts = datetime.datetime.now().isoformat()
            await ElasticsearchClient.index_document("chat_history", {
                "session_id": session_id, "role": "user", "user_id": user_id,
                "content": user_msg, "timestamp": now_ts
            })
            await ElasticsearchClient.index_document("chat_history", {
                "session_id": session_id, "role": "assistant", "user_id": user_id,
                "content": ai_msg, "timestamp": now_ts
            })
        except Exception as e:
            logger.error(f"ES Index failed: {e}")
            
        # 3. Vector Store (Legacy/Semantic Support)
        try:
            # Only if vector store is enabled/configured to handle this
            await VectorService.add_texts(
                texts=[user_msg, ai_msg],
                metadatas=[
                    {"role": "user", "session_id": session_id, "user_id": user_id},
                    {"role": "assistant", "session_id": session_id, "user_id": user_id}
                ]
            )
        except Exception as e:
             logger.warning(f"Vector Index failed: {e}")
