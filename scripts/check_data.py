
import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def check_data():
    async with AsyncSessionLocal() as session:
        # Query sample data
        # Inspect Task Transaction
        res = await session.execute(text("SELECT * FROM task_transaction LIMIT 1"))
        print("\n--- task_transaction columns ---")
        print(res.keys())
        
        # Inspect Task Description (or Project) if it exists
        try:
            res = await session.execute(text("SELECT * FROM task_description LIMIT 1"))
            print("\n--- task_description columns ---")
            print(res.keys())
        except Exception as e:
            print(f"\nNo task_description table: {e}")
            
        try:
            res = await session.execute(text("SELECT * FROM project LIMIT 1"))
            print("\n--- project columns ---")
            print(res.keys())
        except Exception as e:
            print(f"\nNo project table: {e}")

if __name__ == "__main__":
    asyncio.run(check_data())
