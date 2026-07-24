import os
import tempfile
from pathlib import Path

import pytest
import aiosqlite.core as aiosqlite_core

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(prefix="aipal-test-", suffix=".db")
os.close(_TEST_DB_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TEST_DB_PATH}")
os.environ.setdefault("JWT_SECRET", "phase10-test-secret-at-least-32-bytes")
os.environ.setdefault("MAGIC_LINK_DEV_RETURN_TOKEN", "true")
os.environ.setdefault("MEM0_ENABLED", "false")
os.environ.setdefault("EMBEDDING_PROVIDER", "deterministic")
os.environ.setdefault("LIVE_VOICE_V2", "true")
os.environ.setdefault("WHISPER_MODEL", "base")
os.environ.setdefault("TTS_PROVIDER", "edge")
os.environ.setdefault("AI_REASONING_ENABLED", "false")


_orig_conn_await = aiosqlite_core.Connection.__await__


def _daemon_conn_await(self):
    if hasattr(self, "_thread"):
        self._thread.daemon = True
    return _orig_conn_await(self)


aiosqlite_core.Connection.__await__ = _daemon_conn_await


@pytest.fixture(scope="session", autouse=True)
async def _init_test_db():
    from app.db import engine, init_db

    await init_db()
    yield
    await engine.dispose()
    Path(_TEST_DB_PATH).unlink(missing_ok=True)


def pytest_sessionfinish(session, exitstatus):
    import threading

    alive = [t for t in threading.enumerate() if t.is_alive() and t.name != "MainThread"]
    if alive:
        print(f"PYTEST_THREADS: {[(t.name, t.daemon) for t in alive]}")
