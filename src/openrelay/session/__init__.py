from __future__ import annotations

from importlib import import_module

__all__ = [
    "DEFAULT_BROWSE_LIMIT",
    "DEFAULT_BROWSE_SORT",
    "DEFAULT_SESSION_LIST_PAGE_SIZE",
    "DEFAULT_SESSION_LIST_SORT",
    "SESSION_SORT_ACTIVE",
    "SESSION_SORT_MODES",
    "SESSION_SORT_UPDATED",
    "DirectoryShortcutRepository",
    "MessageDedupRepository",
    "MessageRepository",
    "RelayScope",
    "RelaySessionBinding",
    "RelaySessionRepository",
    "SessionAliasRepository",
    "SessionBindingRepository",
    "SessionBindingStore",
    "SessionBrowser",
    "SessionDefaultsPolicy",
    "SessionLifecycleResolver",
    "SessionListEntry",
    "SessionListPage",
    "SessionMutationService",
    "SessionResumeResult",
    "SessionScopeResolver",
    "SessionShortcutService",
    "SessionSortMode",
    "SessionWorkspaceService",
]

_EXPORTS = {
    "DEFAULT_BROWSE_LIMIT": (".browser", "DEFAULT_BROWSE_LIMIT"),
    "DEFAULT_BROWSE_SORT": (".browser", "DEFAULT_BROWSE_SORT"),
    "DEFAULT_SESSION_LIST_PAGE_SIZE": (".browser", "DEFAULT_SESSION_LIST_PAGE_SIZE"),
    "DEFAULT_SESSION_LIST_SORT": (".browser", "DEFAULT_SESSION_LIST_SORT"),
    "SESSION_SORT_ACTIVE": (".browser", "SESSION_SORT_ACTIVE"),
    "SESSION_SORT_MODES": (".browser", "SESSION_SORT_MODES"),
    "SESSION_SORT_UPDATED": (".browser", "SESSION_SORT_UPDATED"),
    "DirectoryShortcutRepository": (".repositories", "DirectoryShortcutRepository"),
    "MessageDedupRepository": (".repositories", "MessageDedupRepository"),
    "MessageRepository": (".repositories", "MessageRepository"),
    "RelayScope": (".models", "RelayScope"),
    "RelaySessionBinding": (".models", "RelaySessionBinding"),
    "RelaySessionRepository": (".repositories", "RelaySessionRepository"),
    "SessionAliasRepository": (".repositories", "SessionAliasRepository"),
    "SessionBindingRepository": (".repositories", "SessionBindingRepository"),
    "SessionBindingStore": (".store", "SessionBindingStore"),
    "SessionBrowser": (".browser", "SessionBrowser"),
    "SessionDefaultsPolicy": (".defaults", "SessionDefaultsPolicy"),
    "SessionLifecycleResolver": (".lifecycle", "SessionLifecycleResolver"),
    "SessionListEntry": (".browser", "SessionListEntry"),
    "SessionListPage": (".browser", "SessionListPage"),
    "SessionMutationService": (".mutations", "SessionMutationService"),
    "SessionResumeResult": (".browser", "SessionResumeResult"),
    "SessionScopeResolver": (".scope", "SessionScopeResolver"),
    "SessionShortcutService": (".shortcuts", "SessionShortcutService"),
    "SessionSortMode": (".browser", "SessionSortMode"),
    "SessionWorkspaceService": (".workspace", "SessionWorkspaceService"),
}


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
