import json
import logging
from typing import Optional, Any
import redis.asyncio as redis
from app.core.settings import settings

logger = logging.getLogger(__name__)

class CacheClient:
    _client: Optional[redis.Redis] = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._client is None:
            logger.info(f"Connecting to Redis at {settings.redis.url}")
            cls._client = redis.from_url(settings.redis.url, decode_responses=True)
        return cls._client

    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        try:
            client = cls.get_client()
            value = await client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    @classmethod
    async def set(cls, key: str, value: Any, expire: int = 3600):
        try:
            client = cls.get_client()
            await client.set(key, json.dumps(value), ex=expire)
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    @classmethod
    async def delete(cls, key: str):
        try:
            client = cls.get_client()
            await client.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

    @classmethod
    async def get_cache(cls, key: str) -> Optional[Any]:
        return await cls.get(key)

    @classmethod
    async def set_cache(cls, key: str, value: Any, expire: int = 3600):
        await cls.set(key, value, expire)

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.close()
            cls._client = None
