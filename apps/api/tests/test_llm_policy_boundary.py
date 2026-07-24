from __future__ import annotations

import ast
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"
ALLOWED_DIRECT_PROVIDER_IMPORTS = {
    APP_DIR / "llm_provider.py",
    APP_DIR / "services" / "companion_response_service.py",
}


def test_direct_llm_provider_imports_are_policy_bounded():
    offenders: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        if path in ALLOWED_DIRECT_PROVIDER_IMPORTS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module.endswith("llm_provider") or module == "llm_provider":
                names = {alias.name for alias in node.names}
                if names & {"llm_chat", "llm_chat_json", "llm_chat_stream"}:
                    offenders.append(f"{path.relative_to(APP_DIR)} imports {sorted(names)}")

    assert offenders == []


def test_non_conversation_ui_copy_has_no_llm_dependency():
    ui_copy = APP_DIR / "services" / "ui_copy.py"
    tree = ast.parse(ui_copy.read_text(encoding="utf-8"))
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert all("llm" not in module.lower() for module in imported_modules)
