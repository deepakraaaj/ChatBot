
import asyncio
from app.db.session import engine
from app.db.models import Base
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def init_models():
    async with engine.begin() as conn:
        logger.info("Dropping tables...")
        await conn.run_sync(Base.metadata.drop_all)
        logger.info("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created successfully.")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(init_models())
