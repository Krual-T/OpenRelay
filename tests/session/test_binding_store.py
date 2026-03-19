from pathlib import Path

from openrelay.session.store import SessionBindingStore
from openrelay.session.models import RelaySessionBinding
from openrelay.storage import StateStore
from tests.support.app import make_app_config, prepare_app_dirs


def test_session_binding_store_persists_and_reads_binding_as_runtime_source(tmp_path: Path) -> None:
    config = make_app_config(tmp_path, max_session_messages=3)
    prepare_app_dirs(config, include_data_dir=False)
    store = StateStore(config)
    session = store.load_session("group:chat_1:sender:ou_1")
    bindings = SessionBindingStore(store)

    binding = RelaySessionBinding(
        relay_session_id=session.session_id,
        backend="codex",
        native_session_id="thread_1",
        cwd=str(config.main_workspace_dir),
        model="gpt-test",
        safety_mode="danger-full-access",
        feishu_chat_id="chat_1",
        feishu_thread_id="thread_scope_1",
    )
    bindings.save(binding)
    bindings.update_native_session_id(session.session_id, "thread_2")

    saved = bindings.get(session.session_id)
    scoped = bindings.find_by_feishu_scope("chat_1", "thread_scope_1")
    synced_session = store.get_session(session.session_id)
    persisted_row = store.connection.execute(
        "SELECT native_session_id, model_override, safety_mode FROM sessions WHERE session_id = ?",
        (session.session_id,),
    ).fetchone()

    assert saved is not None
    assert scoped is not None
    assert saved.native_session_id == "thread_2"
    assert scoped.relay_session_id == session.session_id
    assert synced_session.native_session_id == "thread_2"
    assert synced_session.model_override == "gpt-test"
    assert synced_session.safety_mode == "danger-full-access"
    assert persisted_row is not None
    assert persisted_row["native_session_id"] == ""
    assert persisted_row["model_override"] == config.backend.default_model
    assert persisted_row["safety_mode"] == config.backend.default_safety_mode
    store.close()


def test_session_binding_store_lists_recent_by_backend(tmp_path: Path) -> None:
    config = make_app_config(tmp_path, max_session_messages=3)
    prepare_app_dirs(config, include_data_dir=False)
    store = StateStore(config)
    first = store.load_session("group:chat_1:sender:ou_1")
    second = store.create_next_session(first.base_key, first, backend="claude")
    bindings = SessionBindingStore(store)
    bindings.save(
        RelaySessionBinding(
            relay_session_id=first.session_id,
            backend="codex",
            native_session_id="thread_1",
            cwd=first.cwd,
            model="",
            safety_mode=first.safety_mode,
            feishu_chat_id="chat_1",
            feishu_thread_id="",
        )
    )
    bindings.save(
        RelaySessionBinding(
            relay_session_id=second.session_id,
            backend="claude",
            native_session_id="thread_2",
            cwd=second.cwd,
            model="",
            safety_mode=second.safety_mode,
            feishu_chat_id="chat_1",
            feishu_thread_id="thread_2",
        )
    )

    recent = bindings.list_recent(backend="claude")

    assert [entry.relay_session_id for entry in recent] == [second.session_id]
    store.close()
