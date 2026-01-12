import asyncio
import sys
import os

sys.path.append(os.getcwd())

from app.db.session import AsyncSessionLocal
from app.db.models import User
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == 1))
        user = result.scalars().first()
        if user:
            print(f"Found User 1: {user.email}, Company: {user.company_id}")
        else:
            print("User 1 not found")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
