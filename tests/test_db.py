import asyncio
import sys
from sqlalchemy import text
from app.database import engine  # Import your SQLAlchemy engine instance

# Fix for Windows asyncio event loop issue with psycopg/asyncpg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

async def test_connection():
    try:
        async with engine.connect() as conn:
            # Execute a lightweight query
            result = await conn.execute(text("SELECT 1"))
            print("✅ Database connection successful! Query result:", result.scalar())
    except Exception as e:
        print("❌ Database connection failed!")
        print("Error details:", e)

if __name__ == "__main__":
    asyncio.run(test_connection())
