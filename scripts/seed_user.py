
import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def seed_user():
    async with AsyncSessionLocal() as session:
        print("Seeding test user...")
        try:
            # Check if user 11784578 exists
            result = await session.execute(text("SELECT id FROM `user` WHERE id = 11784578"))
            user = result.mappings().first()
            if not user:
                # Insert User 11784578 (Vinothini)
                stmt = text("""
                    INSERT INTO `user` (id, first_name, last_name, email_id, is_active, company_id, date_created, date_updated)
                    VALUES (11784578, 'Vinothini', 'V', 'vinothini.v@kritilabs.com', 1, 56942686, NOW(), NOW())
                """)
                await session.execute(stmt)
                await session.commit()
                print("✅ User 11784578 (Vinothini) created.")
            else:
                print("ℹ️ User 11784578 already exists.")
                
        except Exception as e:
            print(f"❌ Error seeding user: {e}")

if __name__ == "__main__":
    asyncio.run(seed_user())
