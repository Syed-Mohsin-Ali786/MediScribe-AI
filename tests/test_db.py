import pytest
from sqlalchemy import text

from app.core.database import engine, run_async


@pytest.mark.asyncio
async def test_connection():
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
    except Exception as e:
        pytest.skip(f"Database not available: {e}")

if __name__ == "__main__":
    run_async(test_connection())
