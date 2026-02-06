import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.store import job_store


@pytest.fixture(autouse=True)
def _clear_store():
    """Reset the job store between tests."""
    job_store._jobs.clear()
    yield
    job_store._jobs.clear()


@pytest.fixture()
def api_key() -> str:
    return settings.api_key


@pytest.fixture()
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
