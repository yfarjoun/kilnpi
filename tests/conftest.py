"""Shared test fixtures — must run before any backend imports."""

import os
import tempfile

# Use a temp file for test DB (aiosqlite handles this better than :memory:)
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _test_db.name
os.environ["MOCK_CONTROLLER"] = "1"
