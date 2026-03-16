from pathlib import Path

from openrelay.backends.registry import build_builtin_backend_descriptors


def test_builtin_backend_descriptors_keep_codex_metadata_without_runtime_instantiation(tmp_path: Path) -> None:
    _ = tmp_path
    descriptors = build_builtin_backend_descriptors()

    assert descriptors["codex"].transport == "cli-app-server"
