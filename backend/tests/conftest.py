from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


_TEST_DATA_ROOT = Path(tempfile.mkdtemp(prefix="quantforge-tests-"))
os.environ.setdefault(
    "QUANTFORGE_METERING_DB",
    str(_TEST_DATA_ROOT / "metering.sqlite3"),
)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    """Remove the isolated test database after each pytest invocation."""

    shutil.rmtree(_TEST_DATA_ROOT, ignore_errors=True)
