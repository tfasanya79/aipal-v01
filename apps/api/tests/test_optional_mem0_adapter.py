from types import SimpleNamespace

from app import memory


def test_mem0_enabled_without_credentials_is_quietly_skipped(monkeypatch, caplog):
    caplog.set_level("INFO", logger="aipal.memory")
    monkeypatch.setattr(memory, "_settings", SimpleNamespace(mem0_enabled=True))
    monkeypatch.setattr(memory, "_memory", None)
    monkeypatch.setattr(memory, "_mem0_disabled_notice_logged", False)
    monkeypatch.delenv("MEM0_API_KEY", raising=False)
    monkeypatch.delenv("MEM0_ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)

    assert memory.get_memory() is None
    assert memory.get_memory() is None

    warnings = [record for record in caplog.records if record.levelname == "WARNING"]
    notices = [
        record
        for record in caplog.records
        if "skipping optional Mem0 memory adapter" in record.getMessage()
    ]
    assert warnings == []
    assert len(notices) == 1


def test_mem0_disabled_does_not_check_credentials(monkeypatch):
    monkeypatch.setattr(memory, "_settings", SimpleNamespace(mem0_enabled=False))
    monkeypatch.setattr(memory, "_memory", None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert memory.get_memory() is None
