"""Core data models for the Terralink platform.

These classes define the fundamental entities that the platform
manages. They are deliberately lightweight and use Pydantic
for runtime validation.  Persistence is handled in the in-memory
store defined in :mod:`terralink_platform.data`.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    """A registered user of the platform.

    Parameters
    ----------
    user_id:
        A stable identifier for the user.  This should correspond to
        whatever identifier the client SDK uses to scope data.
    api_key:
        An opaque API key assigned to the user.  This must be
        provided in the ``X-API-Key`` header for authenticated
        requests.
    """

    user_id: str
    api_key: str


class Connection(BaseModel):
    """Represents an OAuth connection attempt.

    When a user wants to connect a toolkit (e.g. GitHub) to their
    account they initiate a connection.  The platform generates
    a connection identifier and redirect URL.  Once the user has
    completed the third‑party OAuth flow the connection transitions
    from ``pending`` to ``authorized`` and a connected account is
    created.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    toolkit: str
    status: str = Field(default="pending")
    connected_account_id: Optional[str] = None
    redirect_url: str = Field(default_factory=str)


class ConnectedAccount(BaseModel):
    """Represents a third‑party account connected to a user.

    Each connected account corresponds to a specific toolkit (e.g.
    GitHub) and contains any additional metadata or credentials
    required to perform authenticated operations.  In this
    simplified implementation the ``token`` field is merely a
    placeholder; in a real platform this would hold encrypted
    access/refresh tokens.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    toolkit: str
    display_name: str
    token: Optional[str] = None


class ToolSpec(BaseModel):
    """Describes a tool that can be executed by the platform.

    The Terralink SDK retrieves these specifications and uses
    them to render the proper function signature for LLMs.  See
    :mod:`terralink_platform.tools` for predefined tool specs.
    """

    slug: str
    description: str
    parameters: Dict[str, Any]
    toolkit: str
    requires_connection: bool = False


class ExecuteRequest(BaseModel):
    """Payload for executing a tool.

    This structure matches the schema expected by the Terralink
    SDK when invoking ``POST /v1/tools/{slug}/execute``.  The
    ``arguments`` key contains the tool parameters and ``context``
    indicates the user and optional connected account under which
    the tool should run.
    """

    arguments: Dict[str, Any]
    context: Dict[str, Any]


class ExecuteResponse(BaseModel):
    """Standardised response from a tool execution.

    ``ok`` indicates whether the call was successful.  If
    ``ok`` is ``False`` an error message may be provided in
    ``error``.  A ``trace_id`` may be included for audit and
    observability purposes.
    """

    ok: bool
    data: Any = None
    error: Optional[str] = None
    trace_id: Optional[str] = None


class Toolkit(BaseModel):
    """Metadata describing a toolkit.

    The platform can group related tools into toolkits (e.g.
    ``github``).  This model contains basic descriptive fields.
    """

    name: str
    description: str
    version: str = "1.0"
