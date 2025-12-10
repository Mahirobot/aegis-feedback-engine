import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, SQLModel

# --- CRITICAL SETUP ---
# We set the Environment Variable BEFORE importing the app.
# This ensures that when 'app.config' and 'app.database' are imported,
# they initialize the engine with the TEST URL, not the PROD URL.
os.environ["DATABASE_URL"] = "sqlite:///./test_feedback.db"

from app.database import engine

# Now imports will use the correct DB configuration
from app.main import app
from app.models import Feedback  # Registers metadata for create_all()


@pytest.fixture(scope="function", autouse=True)
def setup_db():
    """
    Creates tables on the ACTUAL engine used by the app.
    Runs before every test; cleans up after.
    """
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(name="session")
def session_fixture():
    """
    Provides a synchronous session for checking DB state in tests.
    """
    with Session(engine) as session:
        yield session


@pytest_asyncio.fixture(name="client")
async def client_fixture():
    """
    Async Client sharing the same app instance.
    No patching required because the app is already configured for tests.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
