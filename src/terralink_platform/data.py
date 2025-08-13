"""A very simple in‑memory store used by the Terralink platform.

This module defines global dictionaries that hold all user,
connection, connected account and tool definitions.  In a
production system these would be replaced by a database and
external secrets manager.  The store is not thread‑safe; the
FastAPI server should run in a single worker or use proper
locking if concurrency is enabled.
"""

from __future__ import annotations

from typing import Callable, Dict, List

from .models import Connection, ConnectedAccount, ToolSpec, Toolkit, User


# Maps API keys to user objects
USERS: Dict[str, User] = {}

# Maps connection identifiers to connection objects
CONNECTIONS: Dict[str, Connection] = {}

# Maps connected account identifiers to connected account objects
CONNECTED_ACCOUNTS: Dict[str, ConnectedAccount] = {}

# Registered tool specifications by slug
TOOLS: Dict[str, ToolSpec] = {}

# Toolkits metadata by name
TOOLKITS: Dict[str, Toolkit] = {}


def add_user(user: User) -> None:
    USERS[user.api_key] = user


def find_user_by_api_key(api_key: str) -> User | None:
    return USERS.get(api_key)


def add_connection(conn: Connection) -> None:
    CONNECTIONS[conn.id] = conn


def get_connection(conn_id: str) -> Connection | None:
    return CONNECTIONS.get(conn_id)


def add_connected_account(acc: ConnectedAccount) -> None:
    CONNECTED_ACCOUNTS[acc.id] = acc


def get_connected_account(acc_id: str) -> ConnectedAccount | None:
    return CONNECTED_ACCOUNTS.get(acc_id)


def get_connected_accounts_for_user(user_id: str, toolkit: str | None = None) -> List[ConnectedAccount]:
    return [
        acc
        for acc in CONNECTED_ACCOUNTS.values()
        if acc.user_id == user_id and (toolkit is None or acc.toolkit == toolkit)
    ]


def remove_connected_account(acc_id: str) -> ConnectedAccount | None:
    return CONNECTED_ACCOUNTS.pop(acc_id, None)


def register_tool(tool: ToolSpec) -> None:
    TOOLS[tool.slug] = tool


def get_tool(slug: str) -> ToolSpec | None:
    return TOOLS.get(slug)


def list_tools(toolkit: str | None = None) -> List[ToolSpec]:
    if toolkit is None:
        return list(TOOLS.values())
    return [t for t in TOOLS.values() if t.toolkit == toolkit]


def register_toolkit(meta: Toolkit) -> None:
    TOOLKITS[meta.name] = meta


def list_toolkits() -> List[Toolkit]:
    return list(TOOLKITS.values())
