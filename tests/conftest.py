import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import Database  # noqa: E402


@pytest.fixture
async def db(tmp_path):
    database = await Database(str(tmp_path / "test.db")).connect()
    yield database
    await database.close()
