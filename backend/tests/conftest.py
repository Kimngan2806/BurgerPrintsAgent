"""Tests never use a developer's catalog, transaction database or network credentials."""
import os
import tempfile
from pathlib import Path

_test_root = tempfile.TemporaryDirectory(prefix='burgerprints-tests-')
root = Path(_test_root.name)
os.environ['DUCKDB_PATH'] = str(root / 'catalog.duckdb')
os.environ['WORKSPACE_DB_PATH'] = str(root / 'workspace.sqlite3')
os.environ['FILE_STORAGE_PATH'] = str(root / 'designs')
os.environ['BURGERPRINTS_API_KEY'] = ''
os.environ['GEMINI_API_KEY'] = ''
os.environ['SEEDANCE_API_KEY'] = ''
os.environ['HARNESS_FF_SDK_KEY'] = ''


def pytest_sessionfinish(session, exitstatus):
    from cache.duckdb_store import db_store
    db_store.close()
